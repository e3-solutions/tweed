"""Optional Git must not prevent an otherwise runnable command from being captured."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts/confidence.py'
SPEC = importlib.util.spec_from_file_location('confidence_git_availability', SCRIPT)
confidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(confidence)


class GitAvailabilityTest(unittest.TestCase):
    def test_missing_git_preserves_actual_command_result_and_unknown_binding(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / '.confidence'
            for code in (0, 7):
                with self.subTest(exit_code=code):
                    run_id = f'without-git-{code}'
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), 'run', '--id', run_id,
                         '--directory', str(directory), '--cwd', str(root), '--',
                         sys.executable, '-c', f"print('actual command'); raise SystemExit({code})"],
                        env={**os.environ, 'PATH': '', 'CONFIDENCE_DISABLE_DIAGNOSTICS': '1'},
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(result.stdout, 'actual command\n')
                    record = json.loads((directory / 'runs' / f'{run_id}.json').read_text())
                    self.assertEqual(record['exit_code'], code)
                    self.assertEqual(record['version'], 2)
                    self.assertIsNone(record['workspace_start'])
                    self.assertIsNone(record['workspace'])
                    self.assertEqual(confidence.validate_run_record(directory, run_id)[1], [])
                    self.assertTrue(any('unknown' in e for e in confidence.validate_supporting_workspace(record, directory)))

    def test_each_git_command_failure_or_timeout_becomes_unknown(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            successful = [
                subprocess.CompletedProcess([], 0, str(root).encode() + b'\n'),
                subprocess.CompletedProcess([], 0, b'a' * 40 + b'\n'),
                subprocess.CompletedProcess([], 0, b''),
                subprocess.CompletedProcess([], 0, b''),
            ]
            for position in range(4):
                for failure in (FileNotFoundError('missing Git'), PermissionError('cannot execute Git'), subprocess.TimeoutExpired(['git'], 5), subprocess.CompletedProcess([], 128, b'')):
                    with self.subTest(position=position, failure=type(failure).__name__):
                        with patch.object(confidence.subprocess, 'run', side_effect=successful[:position] + [failure]) as run:
                            self.assertIsNone(confidence.git_workspace_fingerprint(root, root / '.confidence'))
                            self.assertEqual(run.call_count, position + 1)
                            for call in run.call_args_list:
                                self.assertEqual(call.kwargs['timeout'], 5)
                                self.assertFalse(call.kwargs.get('shell', False))

    def test_unrelated_programming_error_is_not_hidden(self):
        with patch.object(confidence.subprocess, 'run', side_effect=TypeError('programmer error')):
            with self.assertRaisesRegex(TypeError, 'programmer error'):
                confidence.git_workspace_fingerprint(Path('/tmp'), Path('/tmp/.confidence'))

if __name__ == '__main__':
    unittest.main()
