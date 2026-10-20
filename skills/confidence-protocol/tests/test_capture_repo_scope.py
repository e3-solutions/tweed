"""Capture must not certify a different repository's evidence."""
import os
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import load_confidence, run_cli, write_documents

confidence = load_confidence('confidence_capture_scope')


class CaptureRepoScopeTest(unittest.TestCase):
    def test_cross_repository_cwd_is_rejected_before_command_runs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            repo_a, repo_b = root / 'a', root / 'b'
            for repo in (repo_a, repo_b):
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                (repo / 'source').write_text('original')
            directory = repo_a / '.confidence'
            write_documents(confidence, directory)
            marker = root / 'executed'
            result = run_cli('run', '--directory', str(directory), '--cwd', str(repo_b),
                             '--id', 'tests', '--', sys.executable, '-c',
                             f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')")
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertIn('same Git repository', result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((directory / 'runs/tests.json').exists())

    def test_subdirectory_cwd_stays_valid_and_covers_parent_source(self):
        with tempfile.TemporaryDirectory() as name:
            repo = Path(name)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'source').write_text('original')
            subdir = repo / 'subdir'
            subdir.mkdir()
            directory = repo / '.confidence'
            write_documents(confidence, directory)
            result = run_cli('run', '--directory', str(directory), '--cwd', str(subdir),
                             '--id', 'tests', '--', sys.executable, '-c', 'pass')
            self.assertEqual(result.returncode, 0, result.stderr)
            validation = run_cli('validate', '--directory', str(directory))
            self.assertEqual(validation.returncode, 0, validation.stderr)
            (repo / 'source').write_text('broken')
            validation = run_cli('validate', '--directory', str(directory))
            self.assertEqual(validation.returncode, 1, validation.stderr)
            self.assertIn('stale', validation.stderr)

    def test_evidence_git_probe_errors_fail_closed_before_launch(self):
        for error in (OSError("git unavailable"), subprocess.TimeoutExpired("git", 5)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                directory = root / '.confidence'
                args = confidence.parser().parse_args([
                    'run', '--directory', str(directory), '--cwd', str(root),
                    '--id', 'tests', '--', sys.executable, '-c', 'pass'])
                with patch.object(confidence, 'git_workspace_fingerprint', return_value=None), \
                        patch.object(confidence.subprocess, 'run', side_effect=error), \
                        patch.object(confidence.subprocess, 'Popen', side_effect=AssertionError('command launched')) as launch:
                    self.assertEqual(confidence.command_run(args), 125)
                self.assertEqual(args.diagnostic_error_code, 'RUN_EVIDENCE_DIRECTORY_INVALID')
                launch.assert_not_called()
                self.assertFalse((directory / 'runs/tests.json').exists())

    def test_git_dir_cannot_redirect_evidence_probe_to_command_repository(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            repo_a, repo_b = root / 'a', root / 'b'
            for repo in (repo_a, repo_b):
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            directory = repo_a / '.confidence'
            marker = root / 'executed'
            env = dict(os.environ, GIT_DIR=str(repo_b / '.git'), GIT_WORK_TREE=str(repo_b))
            result = run_cli('run', '--directory', str(directory), '--cwd', str(repo_b),
                             '--id', 'tests', '--', sys.executable, '-c',
                             f"from pathlib import Path; Path({str(marker)!r}).touch()", env=env)
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertFalse(marker.exists())
