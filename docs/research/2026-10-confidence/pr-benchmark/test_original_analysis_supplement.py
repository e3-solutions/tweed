"""Controls for missing-data bounds, declaration separation, and clustering."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("supplement", Path(__file__).with_name("original_analysis_supplement.py"))
supplement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supplement)


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"trial_id": f"{task}--{arm}--r{repeat}", "task_id": task,
                      "arm_id": arm, "repeat": repeat, "passed": False,
                      "oracle_passed": False, "harness_invalid": False,
                      "declared_complete": False, "remaining": ["unfinished"]}
                     for task in ("task1", "task2") for arm in ("original_cp_05", "alternative")
                     for repeat in (1, 2)]
        self.schedule = [{name: row[name] for name in ("trial_id", "task_id", "arm_id", "repeat")}
                         for row in self.rows]

    def row(self, task, arm, repeat):
        return next(row for row in self.rows if (row["task_id"], row["arm_id"], row["repeat"]) == (task, arm, repeat))

    def test_accepted_artifact_without_final_declaration_is_not_closed(self):
        row = self.row("task1", "alternative", 1)
        row.update(passed=True, declared_complete=None, remaining=None)
        result = supplement.analyze(self.rows, self.schedule, [])
        self.assertEqual(result["arms"]["alternative"]["verified_acceptance_lower_bound_count"], 1)
        self.assertEqual(result["arms"]["alternative"]["terminal_closed_lower_bound_count"], 0)

    def test_complete_declaration_with_listed_gaps_is_not_closed(self):
        row = self.row("task1", "alternative", 1)
        row.update(passed=True, declared_complete=True)
        self.assertFalse(supplement.terminal_closed(row))
        row["remaining"] = []
        self.assertTrue(supplement.terminal_closed(row))

    def test_invalid_harness_does_not_receive_verified_acceptance(self):
        row = self.row("task1", "alternative", 1)
        row.update(passed=True, declared_complete=True, remaining=[], harness_invalid=True)
        result = supplement.analyze(self.rows, self.schedule, [])
        self.assertEqual(result["arms"]["alternative"]["verified_acceptance_lower_bound_count"], 0)
        self.assertEqual(result["arms"]["alternative"]["terminal_closed_lower_bound_count"], 0)

    def test_missing_baseline_bounds_without_input_imputation(self):
        unknown = self.row("task2", "original_cp_05", 2)
        unknown.update(passed=None, declared_complete=None, remaining=None)
        self.row("task1", "alternative", 1)["passed"] = True
        original = copy.deepcopy(self.rows)
        result = supplement.analyze(self.rows, self.schedule, [unknown["trial_id"]])
        self.assertEqual(result["arms"]["original_cp_05"]["verified_acceptance_identification_count_bounds"], [0, 1])
        self.assertEqual(result["arms"]["alternative"]["verified_acceptance_delta_identification_bounds_vs_original"], [0, .25])
        self.assertEqual(self.rows, original)

    def test_two_unknown_paired_outcomes_allow_both_delta_directions(self):
        missing = []
        for arm in ("original_cp_05", "alternative"):
            row = self.row("task2", arm, 2)
            row.update(passed=None, declared_complete=None, remaining=None)
            missing.append(row["trial_id"])
        result = supplement.analyze(self.rows, self.schedule, missing)
        self.assertEqual(result["arms"]["alternative"]["verified_acceptance_delta_identification_bounds_vs_original"], [-.25, .25])

    def test_complete_pairs_average_within_tasks_before_between_tasks(self):
        unknown = self.row("task2", "original_cp_05", 2)
        unknown["passed"] = None
        self.row("task1", "alternative", 1)["passed"] = True
        result = supplement.analyze(self.rows, self.schedule, [unknown["trial_id"]])
        pairs = result["arms"]["alternative"]["complete_pair_secondary"]
        self.assertEqual(pairs["matched_trial_pairs"], 3)
        self.assertEqual(pairs["pairs_per_task"], {"task1": 2, "task2": 1})
        self.assertEqual(pairs["mean_task_acceptance_delta"], .25)
        self.assertNotEqual(pairs["mean_task_acceptance_delta"], 1 / 3)

    def test_unknown_inventory_mismatch_is_rejected(self):
        self.rows[0]["passed"] = None
        with self.assertRaisesRegex(ValueError, "interruption inventory"):
            supplement.analyze(self.rows, self.schedule, [])

    def test_subset_secondary_audit_is_rejected(self):
        audit = [{**row, "oracle_passed": True} for row in self.rows if row["task_id"] == "task1"]
        with self.assertRaisesRegex(ValueError, "every scheduled task"):
            supplement.analyze(self.rows, self.schedule, [], {"task1": audit[:-1]})

    def test_secondary_workflow_audit_does_not_change_primary_scores(self):
        audit = [{**row, "oracle_passed": True} for row in self.rows if row["task_id"] == "task1"]
        result = supplement.analyze(self.rows, self.schedule, [], {"task1": audit})
        self.assertEqual(result["arms"]["original_cp_05"]["verified_acceptance_lower_bound_count"], 0)
        self.assertEqual(result["retrospective_workflow_audits"][0]["registered_oracle_acceptances"], 0)
        self.assertEqual(result["retrospective_workflow_audits"][0]["retrospective_workflow_acceptances"], 4)

    def test_duplicate_or_outside_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            supplement.analyze(self.rows + [self.rows[0]], self.schedule, [])
        changed = copy.deepcopy(self.rows)
        changed[0]["trial_id"] = "other"
        with self.assertRaisesRegex(ValueError, "Trial ID"):
            supplement.analyze(changed, self.schedule, [])


if __name__ == "__main__":
    unittest.main()
