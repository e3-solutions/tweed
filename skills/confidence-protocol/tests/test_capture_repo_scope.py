"""Capture must not certify a different repository's evidence."""
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
