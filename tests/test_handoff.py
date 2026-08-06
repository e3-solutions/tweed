import runpy
import unittest
from pathlib import Path


TWEED = runpy.run_path(Path(__file__).resolve().parents[1] / "tweed")
HEADERS = TWEED["PHASE_HEADERS"]
select_handoff = TWEED["select_handoff"]


def issue(kind="Bug"):
    return {"id": "LIN-1", "title": "Example", "url": "linear.test/LIN-1", "description": f"**Kind:** {kind}\n\nIntake"}


def comment(phase, marker, date, **extra):
    return {"id": marker, "body": f"{HEADERS.get(phase, phase)}\n\n{marker}", "createdAt": date, "parentId": None} | extra


class HandoffTests(unittest.TestCase):
    def test_phase_matrix(self):
        fluff = comment("other", "FLUFF", "9")
        cases = [
            ("rca", issue(), [], {"intake"}),
            ("scope", issue(), [comment("rca", "RCA", "1"), fluff], {"rca"}),
            ("scope", issue("Feature"), [fluff], {"intake"}),
            ("implement", issue(), [comment("scope", "SCOPE", "2"), fluff], {"scope"}),
            ("review", issue(), [comment("scope", "SCOPE", "2"), comment("implement", "CODE", "3")], {"scope", "implement"}),
            ("publish", issue(), [comment("review", "REVIEW", "4")], {"review"}),
        ]
        for phase, linear_issue, comments, expected in cases:
            handoff = select_handoff(linear_issue, comments, phase)
            self.assertEqual(set(handoff["context"]), expected)
            self.assertNotIn("FLUFF", str(handoff))

    def test_latest_current_result_wins(self):
        comments = [comment("scope", "OLD", "1"), comment("rca", "RCA", "2"), comment("scope", "NEW", "3")]
        context = select_handoff(issue(), comments, "scope")["context"]
        self.assertEqual(set(context), {"existing"})
        self.assertIn("NEW", context["existing"])

    def test_replies_inline_and_near_matches_are_ignored(self):
        comments = [
            comment("scope", "REPLY", "1", parentId="parent"),
            comment("scope", "INLINE", "2", quotedText="anchor"),
            comment(HEADERS["scope"] + " ", "SPACE", "3"),
        ]
        context = select_handoff(issue(), comments, "implement")["context"]
        self.assertEqual(context, {"missing": HEADERS["scope"]})


if __name__ == "__main__":
    unittest.main()
