"""Independent regression tests for run-to-code binding, using real Git state."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import SCRIPT, load_confidence

confidence = load_confidence('confidence_integrity')


class IntegrityTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='confidence-integrity-test-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.directory = self.root / '.confidence'

    def git_fixture(self):
        def git(*args):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        git('init', '-q')
        (self.root / 'source.txt').write_text('good')
        git('add', '.')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')

    def capture(self, code, run_id='check'):
        result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--directory', str(self.directory), '--cwd', str(self.root), '--id', run_id, '--', sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record, errors = confidence.validate_run_record(self.directory, run_id)
        self.assertEqual(errors, [])
        return record

    def test_changed_during_run_cannot_support_final_state(self):
        self.git_fixture()
        record = self.capture("from pathlib import Path; p=Path('source.txt'); assert p.read_text()=='good'; p.write_text('broken')")
        self.assertNotEqual(record['workspace_start'], record['workspace'])
        self.assertTrue(any('during execution' in e for e in confidence.validate_supporting_workspace(record, self.directory)))
        # Opting out of required binding does not hide observed mutation.
        self.assertTrue(confidence.validate_supporting_workspace(record, self.directory, require_binding=False))

    def test_unchanged_run_is_supported_until_source_changes(self):
        self.git_fixture()
        record = self.capture("from pathlib import Path; assert Path('source.txt').read_text()=='good'")
        self.assertEqual(record['version'], 2)
        self.assertEqual(record['workspace_start'], record['workspace'])
        self.assertEqual(confidence.validate_supporting_workspace(record, self.directory), [])
        (self.root / 'source.txt').write_text('broken')
        self.assertTrue(any('stale' in e for e in confidence.validate_supporting_workspace(record, self.directory)))

    def test_new_verification_after_mutation_can_support_final_state(self):
        self.git_fixture()
        self.capture("from pathlib import Path; Path('source.txt').write_text('new')", 'generator')
        verified = self.capture("from pathlib import Path; assert Path('source.txt').read_text()=='new'", 'verify')
        self.assertEqual(confidence.validate_supporting_workspace(verified, self.directory), [])

    def test_non_git_run_remains_valid_diagnostic_but_not_current_code_proof(self):
        record = self.capture("print('research diagnostic')")
        self.assertIsNone(record['workspace_start'])
        self.assertTrue(any('unknown' in e for e in confidence.validate_supporting_workspace(record, self.directory)))
        self.assertEqual(confidence.validate_supporting_workspace(record, self.directory, require_binding=False), [])

    def test_legacy_record_is_readable_but_requires_rerun_for_code_proof(self):
        self.git_fixture()
        record = self.capture("print('legacy')")
        record['version'] = 1
        del record['workspace_start']
        (self.directory / 'runs/check.json').write_text(json.dumps(record))
        legacy, errors = confidence.validate_run_record(self.directory, 'check')
        self.assertEqual(errors, [])
        self.assertTrue(any('start-state provenance' in e for e in confidence.validate_supporting_workspace(legacy, self.directory)))

    def test_version_two_requires_explicit_start_field_and_valid_shape(self):
        self.git_fixture()
        record = self.capture("print('shape')")
        path = self.directory / 'runs/check.json'
        del record['workspace_start']
        path.write_text(json.dumps(record))
        self.assertTrue(any('workspace_start is required' in e for e in confidence.validate_run_record(self.directory, 'check')[1]))
        record['workspace_start'] = {'kind': 'git', 'root': 'relative', 'sha256': 'bad'}
        path.write_text(json.dumps(record))
        errors = confidence.validate_run_record(self.directory, 'check')[1]
        self.assertTrue(any('workspace_start.root' in e for e in errors))
        self.assertTrue(any('workspace_start.sha256' in e for e in errors))

if __name__ == '__main__':
    unittest.main()
