"""Public CLI receipt contract, including real capture and failure exit codes."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'confidence.py'


class RunReceiptTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-receipt-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.directory = self.root / '.confidence'
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'source.txt').write_text('stable\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'source.txt'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)

    def capture(self, code, *, json_mode=True, extra=(), cwd=None):
        return subprocess.run([
            sys.executable, str(SCRIPT), 'run', '--id', 'check',
            '--directory', str(self.directory), '--cwd', str(cwd or self.root),
            *(['--json'] if json_mode else []), *extra,
            '--', sys.executable, '-c', code,
        ], capture_output=True)

    def record(self):
        return json.loads((self.directory / 'runs/check.json').read_text())

    def test_default_output_still_replays_stdout_and_stderr(self):
        result = self.capture("import os; os.write(1,b'out\\n'); os.write(2,b'err\\n')", json_mode=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'out\nerr\n')
        self.assertEqual((self.directory / 'runs/check.log').read_bytes(), result.stdout)

    def test_json_is_small_while_full_binary_output_and_hash_are_preserved(self):
        result = self.capture("import os; os.write(1,b'X'*131072+b'\\xff\\x00END')")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertLess(len(result.stdout), 1024)
        self.assertEqual(receipt['id'], 'check')
        self.assertEqual(receipt['exit_code'], 0)
        self.assertEqual(receipt['workspace_binding'], 'unchanged')
        record = self.record()
        self.assertEqual(receipt['record'], 'runs/check.json')
        self.assertEqual(receipt['log'], record['log'])
        expected = b'X' * 131072 + b'\xff\x00END'
        self.assertEqual((self.directory / receipt['log']).read_bytes(), expected)
        self.assertEqual(record['log_sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(record['version'], 2)
        self.assertEqual(record['workspace_start'], record['workspace'])

    def test_failed_command_returns_failure_with_receipt(self):
        result = self.capture("import sys; print('failing evidence'); sys.exit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(json.loads(result.stdout)['exit_code'], 7)
        self.assertEqual(self.record()['exit_code'], 7)

    def test_child_exit_125_still_has_a_valid_capture_receipt(self):
        result = self.capture("import sys; sys.exit(125)")
        self.assertEqual(result.returncode, 125)
        self.assertEqual(json.loads(result.stdout)['exit_code'], 125)
        self.assertEqual(self.record()['exit_code'], 125)

    @unittest.skipUnless(os.name == 'posix', 'signal exit mapping is POSIX-specific')
    def test_signal_failure_keeps_signed_record_and_shell_exit_mapping(self):
        result = self.capture('import os, signal; os.kill(os.getpid(), signal.SIGTERM)')
        self.assertEqual(result.returncode, 128 + signal.SIGTERM)
        self.assertEqual(json.loads(result.stdout)['exit_code'], -signal.SIGTERM)
        self.assertEqual(self.record()['exit_code'], -signal.SIGTERM)

    def test_launch_failure_returns_125_without_receipt_or_record(self):
        result = subprocess.run([
            sys.executable, str(SCRIPT), 'run', '--json', '--id', 'check',
            '--directory', str(self.directory), '--cwd', str(self.root),
            '--', str(self.root / 'missing-executable'),
        ], capture_output=True)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.stdout, b'')
        self.assertFalse((self.directory / 'runs/check.json').exists())
        self.assertFalse((self.directory / 'runs/check.log').exists())

    def test_timeout_retains_nonzero_status_and_reason(self):
        result = self.capture('import time; time.sleep(10)', extra=('--timeout-seconds', '0.05'))
        self.assertEqual(result.returncode, 124)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['exit_code'], 124)
        self.assertEqual(receipt['termination_reason'], 'timeout')

    def test_mutation_is_reported_as_changed_not_proven(self):
        result = self.capture("from pathlib import Path; Path('source.txt').write_text('changed')")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['workspace_binding'], 'changed')
        self.assertNotEqual(self.record()['workspace_start'], self.record()['workspace'])

    def test_non_git_workspace_binding_is_explicitly_unknown(self):
        with tempfile.TemporaryDirectory(prefix='confidence-unbound-') as location:
            result = self.capture("print('diagnostic')", cwd=Path(location))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['workspace_binding'], 'unknown')


if __name__ == '__main__':
    unittest.main()
