"""Current content must not depend on Git's stat-cache promises."""
import importlib.util
import json
import os
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/confidence.py'
spec = importlib.util.spec_from_file_location('confidence_content', SCRIPT)
confidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(confidence)


class ContentBindingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / '.confidence'
        self.git('init', '-q')
        (self.root / 'source').write_text('good')
        self.git('add', '.')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def commit(self):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture')

    def fingerprint(self, cwd=None):
        return confidence.git_workspace_fingerprint(cwd or self.root, self.directory)

    def test_unborn_and_metadata_only_commit_bind_same_content(self):
        before = self.fingerprint()
        self.assertEqual(before['kind'], 'git-content-v1')
        self.commit()
        self.assertEqual(before, self.fingerprint())
        self.commit()
        self.assertEqual(before, self.fingerprint())

    def test_git_index_flags_do_not_hide_command_mutation(self):
        self.commit()
        for flag in ('assume-unchanged', 'skip-worktree'):
            with self.subTest(flag=flag):
                (self.root / 'source').write_text('good')
                self.git('update-index', '--' + flag, 'source')
                result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--directory', str(self.directory), '--cwd', str(self.root), '--id', flag, '--', sys.executable, '-c', "from pathlib import Path; assert Path('source').read_text()=='good'; Path('source').write_text('broken')"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                record, errors = confidence.validate_run_record(self.directory, flag)
                self.assertEqual(errors, [])
                self.assertNotEqual(record['workspace_start'], record['workspace'])
                self.assertTrue(any('changed during' in e for e in confidence.validate_supporting_workspace(record, self.directory)))
                self.git('update-index', '--no-' + flag, 'source')

    def test_nested_cwd_covers_source_outside_subdirectory(self):
        (self.root / 'sub').mkdir()
        (self.root / 'sub/inner').write_text('inner')
        before = self.fingerprint(self.root / 'sub')
        self.assertEqual(before, self.fingerprint())
        (self.root / 'source').write_text('broken')
        self.assertNotEqual(before, self.fingerprint(self.root / 'sub'))

    def test_newline_root_is_not_confused_with_trimmed_sibling(self):
        for name in ('repo', 'repo\n'):
            root = self.root / name
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'value').write_text('before')
        actual = self.root / 'repo\n'
        before = confidence.git_workspace_fingerprint(actual, actual / '.confidence')
        self.assertEqual(Path(before['root']), actual.resolve())
        (actual / 'value').write_text('after')
        self.assertNotEqual(before, confidence.git_workspace_fingerprint(actual, actual / '.confidence'))

    def test_routing_environment_cannot_hide_tracked_ignored_source(self):
        (self.root / '.gitignore').write_text('source\n')
        self.commit()
        alternate = self.root / '.git/alternate-index'
        with patch.dict(os.environ, {'GIT_INDEX_FILE': str(alternate)}):
            self.git('read-tree', '--empty')
            self.assertIsNone(self.fingerprint())
            (self.root / 'source').write_text('hidden mutation')
            self.assertIsNone(self.fingerprint())
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
            with self.subTest(key=key), patch.dict(os.environ, {key: str(self.root)}):
                self.assertIsNone(self.fingerprint())

    def test_core_worktree_routing_is_unknown_even_when_root_contains_cwd(self):
        self.git('config', 'core.worktree', str(self.root.parent))
        self.assertIsNone(self.fingerprint())
        self.git('config', '--unset', 'core.worktree')
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.worktree', 'GIT_CONFIG_VALUE_0': str(self.root.parent)}):
            self.assertIsNone(self.fingerprint())

    def test_conventional_linked_worktree_is_supported(self):
        self.commit()
        target = self.root / 'linked'
        self.git('worktree', 'add', '--detach', str(target))
        before = confidence.git_workspace_fingerprint(target, target / '.confidence')
        self.assertEqual(before['kind'], 'git-content-v1')
        (target / 'source').write_text('changed')
        self.assertNotEqual(before, confidence.git_workspace_fingerprint(target, target / '.confidence'))

    def test_legacy_digest_is_readable_but_not_current_proof(self):
        legacy = {'kind': 'git', 'root': str(self.root), 'sha256': 'a' * 64}
        record = {'version': 2, 'id': 'legacy', 'cwd': str(self.root), 'workspace': legacy, 'workspace_start': legacy}
        self.assertTrue(any('legacy' in e for e in confidence.validate_supporting_workspace(record, self.directory)))
        self.assertEqual(confidence.validate_supporting_workspace(record, self.directory, require_binding=False), [])

    def test_evidence_case_alias_does_not_self_stale(self):
        self.directory.mkdir()
        alias = self.root / '.CONFIDENCE'
        if not alias.exists():
            self.skipTest('filesystem has case-sensitive directory names')
        before = confidence.git_workspace_fingerprint(self.root, alias)
        (self.directory / 'report.json').write_text('{}')
        self.assertEqual(before, confidence.git_workspace_fingerprint(self.root, alias))

    def test_tracked_evidence_and_ignored_tracked_source_are_bound(self):
        self.directory.mkdir()
        (self.directory / 'report.json').write_text('{}')
        self.git('add', '.')
        (self.root / '.git/info/exclude').write_text('source\n.confidence/\n')
        before = self.fingerprint()
        (self.directory / 'report.json').write_text('{"changed":true}')
        self.assertNotEqual(before, self.fingerprint())
        before = self.fingerprint()
        (self.root / 'source').write_text('changed')
        self.assertNotEqual(before, self.fingerprint())

if __name__ == '__main__':
    unittest.main()
