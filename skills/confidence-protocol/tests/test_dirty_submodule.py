"""Dirty gitlinks must not masquerade as fully enumerated source state."""
import importlib.util
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/confidence.py'
SPEC = importlib.util.spec_from_file_location('confidence_dirty_submodule', SCRIPT)
confidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(confidence)


class DirtySubmoduleTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-gitlink-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.component = self.root / 'component'
        self.component.mkdir()
        self.git(self.component, 'init', '-q')
        (self.component / 'source.txt').write_text('initial')
        self.commit(self.component)
        self.git(self.root, 'init', '-q')
        (self.root / 'README.md').write_text('fixture')
        self.commit(self.root)
        self.directory = self.root / '.confidence'

    def git(self, root, *args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)

    def commit(self, root):
        self.git(root, 'add', '.')
        self.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')

    def test_preexisting_dirty_gitlink_cannot_certify_changed_contents(self):
        source = self.component / 'source.txt'
        source.write_text('good')
        result = subprocess.run([
            sys.executable, str(SCRIPT), 'run', '--id', 'check', '--cwd', str(self.root),
            '--directory', str(self.directory), '--', sys.executable, '-c',
            "from pathlib import Path; assert Path('component/source.txt').read_text() == 'good'",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record, errors = confidence.validate_run_record(self.directory, 'check')
        self.assertEqual(errors, [])
        source.write_text('broken')
        self.assertIsNone(record['workspace_start'])
        self.assertIsNone(record['workspace'])
        self.assertTrue(confidence.validate_supporting_workspace(record, self.directory))

    def test_ignore_all_configuration_does_not_hide_dirty_gitlink(self):
        for key in ('diff.ignoreSubmodules', 'submodule.component.ignore'):
            self.git(self.root, 'config', key, 'all')
        (self.component / 'source.txt').write_text('dirty')
        self.assertIsNone(confidence.git_workspace_fingerprint(self.root, self.directory))

    def test_clean_gitlink_is_unknown_and_later_dirt_is_rejected(self):
        before = confidence.git_workspace_fingerprint(self.root, self.directory)
        self.assertIsNone(before)
        record = {'version': 2, 'id': 'clean', 'cwd': str(self.root), 'workspace_start': before, 'workspace': before}
        self.assertTrue(confidence.validate_supporting_workspace(record, self.directory))
        (self.component / 'source.txt').write_text('dirty')
        self.assertTrue(confidence.validate_supporting_workspace(record, self.directory))

    def test_untracked_file_inside_gitlink_is_unknown(self):
        (self.component / 'new.py').write_text('new source')
        self.assertIsNone(confidence.git_workspace_fingerprint(self.root, self.directory))

    def test_gitlink_under_reserved_evidence_filename_is_not_excluded(self):
        target = self.directory / 'runs' / 'dependency.json'
        target.parent.mkdir(parents=True)
        self.git(self.root, 'mv', 'component', str(target.relative_to(self.root)))
        self.commit(self.root)
        (target / 'source.txt').write_text('dirty nested source')
        self.assertIsNone(confidence.git_workspace_fingerprint(self.root, self.directory))

    def test_rename_source_looking_like_status_is_not_an_untracked_record(self):
        # Rename parsing is independent of unsupported submodule enumeration.
        self.git(self.root, 'update-index', '--force-remove', 'component')
        shutil.rmtree(self.component)
        original = self.root / '?? misleading'
        original.write_text('tracked source')
        self.commit(self.root)
        self.git(self.root, 'mv', '?? misleading', 'renamed.txt')
        fingerprint = confidence.git_workspace_fingerprint(self.root, self.directory)
        self.assertIsNotNone(fingerprint)
        (self.root / 'renamed.txt').write_text('edited after rename')
        self.assertNotEqual(fingerprint, confidence.git_workspace_fingerprint(self.root, self.directory))


if __name__ == '__main__':
    unittest.main()
