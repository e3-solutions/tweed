"""Fingerprint failures stay unknown; capture requires a successful evidence-root probe."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from support import SCRIPT, load_confidence

confidence = load_confidence('confidence_git_availability')


class GitAvailabilityTest(unittest.TestCase):
    def test_missing_git_rejects_capture_before_launch(self):
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
                    self.assertEqual(result.returncode, 125, result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('could not determine evidence directory Git repository', result.stderr)
                    self.assertFalse((directory / 'runs' / f'{run_id}.json').exists())
                    self.assertFalse((directory / 'runs' / f'{run_id}.log').exists())

    def test_each_git_command_failure_or_timeout_becomes_unknown(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            successful = [
                subprocess.CompletedProcess([], 0, str(root).encode() + b'\n'),
                subprocess.CompletedProcess([], 1, b''),
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
