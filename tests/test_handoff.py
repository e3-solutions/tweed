import importlib.machinery
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("tweed_runner", str(ROOT / "tweed"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
TWEED = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(TWEED)


def issue(kind="Bug"):
    return {
        "id": "LIN-123",
        "title": "Example",
        "url": "https://linear.app/example/issue/LIN-123/example",
        "description": f"## What\n**Kind:** {kind}\n\nExact intake",
        "labels": [],
    }


def comment(header, marker, created_at, parent_id=None):
    return {
        "body": f"{header}\n\n{marker}",
        "createdAt": created_at,
        "parentId": parent_id,
    }


class DeterministicHandoffTests(unittest.TestCase):
    def setUp(self):
        self.comments = [
            comment(TWEED.PHASE_HEADERS["rca"], "RCA", "2026-01-01T00:00:00Z"),
            comment(TWEED.PHASE_HEADERS["scope"], "SCOPE", "2026-01-02T00:00:00Z"),
            comment(
                TWEED.PHASE_HEADERS["implement"],
                "IMPLEMENTATION",
                "2026-01-03T00:00:00Z",
            ),
            comment(TWEED.PHASE_HEADERS["review"], "REVIEW", "2026-01-04T00:00:00Z"),
            comment("## Unrelated", "FLUFF", "2026-01-05T00:00:00Z"),
        ]

    def test_each_phase_receives_only_its_required_artifacts(self):
        cases = {
            "rca": (issue(), [], ["intake"]),
            "scope": (
                issue(),
                self.comments[0:1] + self.comments[4:],
                [TWEED.PHASE_HEADERS["rca"]],
            ),
            "implement": (
                issue(),
                self.comments[1:2] + self.comments[4:],
                [TWEED.PHASE_HEADERS["scope"]],
            ),
            "review": (
                issue(),
                self.comments[1:3] + self.comments[4:],
                [TWEED.PHASE_HEADERS["scope"], TWEED.PHASE_HEADERS["implement"]],
            ),
            "publish": (issue(), self.comments[3:], [TWEED.PHASE_HEADERS["review"]]),
        }
        for phase, (linear_issue, comments, expected) in cases.items():
            with self.subTest(phase=phase):
                handoff = TWEED.select_handoff(linear_issue, comments, phase)
                self.assertEqual(
                    [item["type"] for item in handoff["artifacts"]], expected
                )
                self.assertNotIn("FLUFF", str(handoff))

    def test_feature_scope_receives_intake_instead_of_rca(self):
        handoff = TWEED.select_handoff(
            issue("Feature"), self.comments[0:1] + self.comments[4:], "scope"
        )
        self.assertEqual(
            handoff["artifacts"],
            [{"type": "intake", "content": issue("Feature")["description"]}],
        )

    def test_latest_existing_phase_result_replaces_predecessors(self):
        comments = self.comments + [
            comment(TWEED.PHASE_HEADERS["scope"], "LATEST", "2026-02-01T00:00:00Z")
        ]
        handoff = TWEED.select_handoff(issue(), comments, "scope")
        self.assertIn("LATEST", handoff["existing_result"])
        self.assertEqual(handoff["artifacts"], [])
        self.assertNotIn("RCA", str(handoff))

    def test_missing_predecessor_is_named_without_other_comments(self):
        handoff = TWEED.select_handoff(issue(), self.comments[-1:], "implement")
        self.assertEqual(handoff["missing"], TWEED.PHASE_HEADERS["scope"])
        self.assertEqual(handoff["artifacts"], [])
        self.assertNotIn("FLUFF", str(handoff))


if __name__ == "__main__":
    unittest.main()
