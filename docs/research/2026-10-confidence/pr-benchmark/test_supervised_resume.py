"""Boundary checks for interruption accounting; no provider calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("supervised_resume", Path(__file__).with_name("supervised_resume.py"))
resume = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resume)


class ResumeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.specs = [{"trial_id": identity, "request_sha256": "frozen"}
                      for identity in ("done", "begun", "new")]
        (self.root / "trials" / "done").mkdir(parents=True)
        (self.root / "trials" / "done" / "receipt.json").write_text("{}")
        (self.root / "trials" / "begun").mkdir()

    def test_empty_existing_directory_is_interrupted_not_new(self):
        rows = resume.classify(self.root, self.specs)
        self.assertEqual([row["state"] for row in rows],
                         ["completed_receipt", "interrupted_no_receipt", "never_started"])

    def test_interrupted_model_emission_is_unknown(self):
        self.assertEqual(resume.classify(self.root, self.specs)[1]["model_emission"], "unknown")

    def test_retains_original_receipt_digest(self):
        row = resume.classify(self.root, self.specs)[0]
        self.assertEqual(row["files"][0]["sha256"],
                         resume.sha(self.root / "trials" / "done" / "receipt.json"))

    def test_symlink_material_is_refused(self):
        (self.root / "trials" / "begun" / "escape").symlink_to(self.root / "trials" / "done" / "receipt.json")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            resume.classify(self.root, self.specs)

    def test_immutable_source_mismatch_is_refused_before_import(self):
        with self.assertRaisesRegex(ValueError, "hash changed"):
            resume.load_module(Path(__file__), "untrusted", "0" * 64)

    def test_first_grade_output_change_is_explicitly_separate(self):
        output = self.root / "trials" / "done" / "grader.stdout"
        output.write_text("")
        inventory = resume.classify(self.root, self.specs)
        output.write_text("First grade completed")
        violations, grading = resume.check_preservation(self.root, inventory)
        self.assertEqual(violations, [])
        self.assertEqual([row["path"] for row in grading], ["grader.stdout"])

    def test_preexisting_completed_grade_output_change_is_refused(self):
        directory = self.root / "trials" / "done"
        (directory / "graded-receipt.json").write_text("{}")
        (directory / "grader.stdout").write_text("Completed grade")
        inventory = resume.classify(self.root, self.specs)
        (directory / "grader.stdout").write_text("Different grade")
        violations, grading = resume.check_preservation(self.root, inventory)
        self.assertEqual(grading, [])
        self.assertEqual([row["path"] for row in violations], ["grader.stdout"])

    def test_raw_receipt_change_is_refused_even_with_first_grade_pending(self):
        inventory = resume.classify(self.root, self.specs)
        (self.root / "trials" / "done" / "receipt.json").write_text('{"changed":true}')
        violations, grading = resume.check_preservation(self.root, inventory)
        self.assertEqual(grading, [])
        self.assertEqual([row["path"] for row in violations], ["receipt.json"])


if __name__ == "__main__":
    unittest.main()
