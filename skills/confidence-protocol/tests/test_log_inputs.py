"""Damaged captured logs must not block evidence consumers or escape by symlink."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/confidence.py'


@unittest.skipUnless(os.name == 'posix', 'nonblocking no-follow file descriptors require Unix')
class LogInputTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-log-input-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.directory = self.root / '.confidence'
        self.env = dict(os.environ, CONFIDENCE_DISABLE_DIAGNOSTICS='1', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, env=self.env)
        (self.root / 'source.txt').write_text('stable\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'source.txt'], check=True, env=self.env)
        contract = json.loads((SCRIPT.parent.parent / 'assets/contract.example.json').read_text())
        result = self.cli('init', '--title', contract['task']['title'], '--mode', contract['task']['mode'])
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.directory / 'contract.json').write_text(json.dumps(contract))
        result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--json', '--id', 'probe', '--directory', str(self.directory), '--cwd', str(self.root), '--', sys.executable, '-c', "print('captured log')"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.log = self.directory / 'runs/probe.log'
        self.original = self.log.read_bytes()
        self.before = (self.directory / 'report.json').read_bytes()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, '--directory', str(self.directory)], env=self.env, capture_output=True, text=True, timeout=3)

    def record(self, diagnostic=False):
        return self.cli('record', '--obligation', 'P1', '--status', 'partial', '--details', 'Explicit retained observation', '--diagnostic-run' if diagnostic else '--run', 'probe')

    def assert_rejected(self, diagnostic=False):
        result = self.record(diagnostic)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)['code'], 'RESULT_INVALID', result.stdout)
        self.assertEqual(self.before, (self.directory / 'report.json').read_bytes())
        self.assertNotIn('internal error', result.stderr)
        return result

    def test_regular_log_keeps_hash_and_partial_recording(self):
        record = json.loads((self.directory / 'runs/probe.json').read_text())
        self.assertEqual(record['log_sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.record().returncode, 0)
        self.assertEqual(self.log.read_bytes(), self.original)

    def test_missing_log_is_structured_invalid_evidence(self):
        self.log.unlink()
        self.assertIn('missing file', self.assert_rejected().stdout)

    def test_directory_log_is_structured_invalid_evidence(self):
        self.log.unlink(); self.log.mkdir()
        self.assert_rejected()

    def test_symlink_log_is_rejected_even_with_matching_bytes(self):
        target = self.root / 'outside.log'
        target.write_bytes(self.original)
        self.log.unlink(); self.log.symlink_to(target)
        self.assert_rejected()
        self.assertEqual(target.read_bytes(), self.original)

    def test_fifo_log_is_bounded_for_record_validate_and_render(self):
        # Attach while valid so all public consumers actually reach the log.
        self.assertEqual(self.record().returncode, 0)
        self.before = (self.directory / 'report.json').read_bytes()
        self.log.unlink(); os.mkfifo(self.log)
        self.assert_rejected()
        for command in ('validate', 'render'):
            with self.subTest(command=command):
                result = self.cli(command)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('regular log file', result.stderr)
                self.assertNotIn('internal error', result.stderr)
        self.assertFalse((self.directory / 'REPORT.md').exists())

    def test_fifo_diagnostic_log_is_also_bounded(self):
        self.log.unlink(); os.mkfifo(self.log)
        self.assert_rejected(diagnostic=True)

    def test_symlink_to_fifo_is_rejected_without_opening_target(self):
        target = self.root / 'outside.fifo'; os.mkfifo(target)
        self.log.unlink(); self.log.symlink_to(target)
        self.assert_rejected()


if __name__ == '__main__':
    unittest.main()
