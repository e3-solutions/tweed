"""An evidence exclusion must never hide the entire verified source tree."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import SCRIPT, load_confidence

confidence = load_confidence('confidence_evidence_root')


class EvidenceRootTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-root-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'source.txt').write_text('original')
        subprocess.run(['git', '-C', str(self.root), 'add', 'source.txt'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)

    def test_root_evidence_is_rejected_before_command_runs(self):
        result = subprocess.run([
            sys.executable, str(SCRIPT), 'run', '--cwd', str(self.root),
            '--directory', str(self.root), '--id', 'root', '--', sys.executable,
            '-c', "from pathlib import Path; Path('executed').write_text('yes')",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 125)
        self.assertIn('use --directory .confidence', result.stderr)
        self.assertFalse((self.root / 'executed').exists())
        self.assertFalse((self.root / 'runs/root.json').exists())

    def test_preexisting_root_record_cannot_hide_persistent_source_edit(self):
        # This is the old accepted record layout. Its digest omits every source file.
        fingerprint = confidence.git_workspace_fingerprint(self.root, self.root)
        record = {'version': 2, 'id': 'old', 'cwd': str(self.root),
                  'workspace': fingerprint, 'workspace_start': fingerprint}
        (self.root / 'source.txt').write_text('persistent regression')
        errors = confidence.validate_supporting_workspace(record, self.root)
        self.assertTrue(any('excludes all source' in error for error in errors), errors)

    def test_normal_subdirectory_still_detects_persistent_source_edit(self):
        directory = self.root / '.confidence'
        fingerprint = confidence.git_workspace_fingerprint(self.root, directory)
        record = {'version': 2, 'id': 'normal', 'cwd': str(self.root),
                  'workspace': fingerprint, 'workspace_start': fingerprint}
        self.assertEqual(confidence.validate_supporting_workspace(record, directory), [])
        (self.root / 'source.txt').write_text('persistent regression')
        self.assertTrue(any('stale' in error for error in confidence.validate_supporting_workspace(record, directory)))


if __name__ == '__main__':
    unittest.main()
