import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('export_results', Path(__file__).with_name('export_results.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicationControls(unittest.TestCase):
    def fixture(self, root):
        study, destination = root / 'study', root / 'public'
        trial = study / 'trials' / 'task--arm--r1'
        trial.mkdir(parents=True)
        patch = b'diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n'
        row = dict(trial_id='task--arm--r1', task_id='task', arm_id='arm', repeat=1,
                   status='terminal_missing', passed=False, declared_complete=None,
                   total_cost_usd=None, known_cost_subtotal=0, false_completion=False,
                   patch_sha256=hashlib.sha256(patch).hexdigest(),
                   completion_summary='PRIVATE_SUMMARY', remaining=['PRIVATE_REMAINING'],
                   tool_errors=[dict(error='PRIVATE_ERROR', error_kind='tool_input')])
        (trial / 'submitted.patch').write_bytes(patch)
        (trial / 'receipt.json').write_text(json.dumps({'status': 'terminal_missing', 'secret': 'PRIVATE_RECEIPT'}))
        (trial / 'graded-receipt.json').write_text(json.dumps({'normalized': row}))
        (trial / 'grader.stdout').write_text('PRIVATE_LOG')
        (trial / 'grader.stderr').write_text('')
        (study / 'results-normalized.json').write_text(json.dumps([row]))
        schedule = root / 'schedule.json'
        schedule.write_text(json.dumps([dict(task_id='task', arm_id='arm', repeat=1)]))
        return study, schedule, destination, trial, row

    def test_projection_preserves_unknowns_and_excludes_free_text(self):
        with tempfile.TemporaryDirectory() as name:
            study, schedule, out, _, _ = self.fixture(Path(name))
            module.export(study, schedule, out)
            rendered = (out / 'results.json').read_text()
            self.assertNotIn('PRIVATE_', rendered)
            row = json.loads(rendered)[0]
            self.assertIsNone(row['total_cost_usd'])
            self.assertIsNone(row['declared_complete'])
            self.assertEqual(row['tool_input_error_count'], 1)
            self.assertNotIn('false_completion', row)
            self.assertFalse(row['oracle_false_completion'])

    def test_incomplete_cohort_refused(self):
        with tempfile.TemporaryDirectory() as name:
            study, schedule, out, _, row = self.fixture(Path(name))
            row['status'] = 'missing_receipt'
            (study / 'results-normalized.json').write_text(json.dumps([row]))
            with self.assertRaisesRegex(ValueError, 'complete scheduled cohort'):
                module.export(study, schedule, out)

    def test_tampered_patch_refused(self):
        with tempfile.TemporaryDirectory() as name:
            study, schedule, out, trial, _ = self.fixture(Path(name))
            (trial / 'submitted.patch').write_text('different patch')
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                module.export(study, schedule, out)

    def test_stale_aggregate_refused(self):
        with tempfile.TemporaryDirectory() as name:
            study, schedule, out, trial, row = self.fixture(Path(name))
            row['passed'] = True
            (trial / 'graded-receipt.json').write_text(json.dumps({'normalized': row}))
            with self.assertRaisesRegex(ValueError, 'Aggregate differs'):
                module.export(study, schedule, out)

    def test_symlink_patch_refused(self):
        with tempfile.TemporaryDirectory() as name:
            study, schedule, out, trial, _ = self.fixture(Path(name))
            patch = trial / 'submitted.patch'
            saved = trial / 'saved.patch'
            patch.rename(saved)
            patch.symlink_to(saved)
            with self.assertRaisesRegex(ValueError, 'regular submitted patch'):
                module.export(study, schedule, out)


if __name__ == '__main__':
    unittest.main()
