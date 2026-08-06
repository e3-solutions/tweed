import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TWEED = runpy.run_path(str(ROOT / "tweed"), run_name="tweed_module")


def normalized(path):
    return " ".join((ROOT / path).read_text().split()).casefold()


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
    def test_implementation_owns_safe_repository_bound_draft_kickoff(self):
        workflow = normalized("workflows/implement.md")

        required = (
            "only allowed github writes",
            "candidate from an interrupted attempt",
            "recorded pr belongs to the github repository derived from `origin`",
            "gh pr list --repo <host>/<owner>/<repo> --state all --head <branch>",
            "git commit --allow-empty --only",
            "git diff-tree --quiet head^ head",
            "gh pr create --draft",
            "with explicit `--repo <host>/<owner>/<repo>`, `--base <base>`, "
            "and `--head <branch>` arguments",
            "push the implementation commit",
            "full implementation commit, and draft pr url",
        )
        for contract in required:
            with self.subTest(contract=contract):
                self.assertIn(contract, workflow)
        self.assertNotIn("do not push, open a pull request", workflow)
        self.assertNotIn("pushes, pr creation, and deployment belong", workflow)
        self.assertNotIn("--head <owner>:<branch>", workflow)

    def test_review_preserves_pr_without_remote_delivery(self):
        workflow = normalized("workflows/review.md")

        self.assertIn(
            "preserve the implementation draft pr without pushing, changing its "
            "metadata or readiness",
            workflow,
        )
        self.assertIn("draft pr: `[url from the implementation handoff", workflow)
        self.assertIn("unchanged draft pr url when present", workflow)
        self.assertNotIn("mark that exact draft ready", workflow)

    def test_publish_promotes_exact_repository_draft_after_review_push(self):
        workflow = normalized("workflows/publish.md")

        required = (
            "derive one canonical `<host>/<owner>/<repo>` selector from `origin`",
            "scope every `gh` read and write explicitly to that selector",
            "when a legacy handoff has no pr url",
            "gh pr list --repo <host>/<owner>/<repo> --state all --head <branch>",
            "url and head repository both use the exact canonical host",
            "cross-host, cross-repository",
            "already non-draft",
            "mark that exact draft ready for review",
        )
        for contract in required:
            with self.subTest(contract=contract):
                self.assertIn(contract, workflow)
        self.assertLess(
            workflow.index("push the reviewed head"),
            workflow.index("mark that exact draft ready for review"),
        )
        self.assertNotIn("--head <owner>:<branch>", workflow)

    def test_ci_runs_contract_tests(self):
        workflow = normalized(".github/workflows/ci.yml")

        self.assertIn("python -m unittest discover -s tests -v", workflow)


if __name__ == "__main__":
    unittest.main()
