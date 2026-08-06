import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TWEED = runpy.run_path(str(ROOT / "tweed"), run_name="tweed_module")


def completed_receipt(phase):
    return {
        "phase": phase,
        "state": "completed",
        "issue": "COR-3371",
        "linear_url": "https://linear.example/COR-3371",
        "result": TWEED["COMPLETED_RESULTS"][phase],
        "summary": "done",
        "question": None,
        "next_action": None,
        "branch": "tweed/cor-3371-draft-kickoff",
        "commit": "a" * 40,
        "pull_request_url": "https://github.example/pull/1",
    }


class ReceiptContractTests(unittest.TestCase):
    def test_completed_implementation_requires_draft_pr(self):
        receipt = completed_receipt("implement")
        receipt["pull_request_url"] = None

        with self.assertRaisesRegex(RuntimeError, "missing its pull request"):
            TWEED["validate_receipt"](receipt, "implement")

    def test_completed_implementation_accepts_draft_pr(self):
        receipt = completed_receipt("implement")

        self.assertEqual(TWEED["validate_receipt"](receipt, "implement"), receipt)

    def test_review_receipt_can_preserve_legacy_null_pr(self):
        receipt = completed_receipt("review")
        receipt["pull_request_url"] = None

        self.assertEqual(TWEED["validate_receipt"](receipt, "review"), receipt)


class WorkflowContractTests(unittest.TestCase):
    def test_implementation_owns_draft_pr_kickoff(self):
        workflow = (ROOT / "workflows" / "implement.md").read_text()

        self.assertIn("`gh pr create --draft`", workflow)
        self.assertIn("only allowed GitHub writes", workflow)
        self.assertIn("candidate from an interrupted attempt", workflow)
        self.assertIn("whether it is\n   still draft or was later published", workflow)
        self.assertNotIn("do not push, open\na pull request", workflow)

    def test_publish_promotes_existing_draft(self):
        workflow = (ROOT / "workflows" / "publish.md").read_text()

        self.assertIn("mark the exact draft ready for review", workflow)
        self.assertIn("implementation draft PR", workflow)
        self.assertIn("already non-draft", workflow)


if __name__ == "__main__":
    unittest.main()
