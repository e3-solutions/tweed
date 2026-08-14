import runpy
import unittest
from pathlib import Path


RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "bonaparte"))
HEADERS = RUNNER["PHASE_HEADERS"]
select_handoff = RUNNER["select_handoff"]


def issue(kind="Bug"):
    return {
        "identifier": "LIN-1",
        "title": "Example",
        "url": "https://linear.test/LIN-1",
        "description": f"**Kind:** {kind}\n\nIntake",
        "gitBranchName": "arya/lin-1-example",
        "labels": [],
    }


def comment(phase, marker, date, **extra):
    return {
        "id": marker,
        "body": f"{HEADERS.get(phase, phase)}\n\n{marker}",
        "createdAt": date,
        "parentId": None,
    } | extra


class HandoffTests(unittest.TestCase):
    def test_phase_matrix_passes_only_required_context(self):
        rca = comment("rca", "RCA", "1")
        scope = comment("scope", "SCOPE", "2")
        implementation = comment("implement", "CODE", "3")
        review = comment("review", "REVIEW", "4")
        unrelated = comment("other", "UNRELATED", "9")
        cases = [
            ("rca", issue(), [], {"intake"}),
            ("scope", issue(), [rca, unrelated], {"rca"}),
            ("scope", issue("Feature"), [unrelated], {"intake"}),
            ("implement", issue(), [rca, scope, unrelated], {"scope"}),
            ("review", issue(), [scope, implementation], {"implement"}),
            ("publish", issue(), [review], {"review"}),
        ]
        for phase, linear_issue, comments, expected in cases:
            with self.subTest(phase=phase):
                handoff = select_handoff(linear_issue, comments, phase)
                self.assertEqual(set(handoff["context"]), expected)
                self.assertEqual(
                    handoff["issue"]["git_branch_name"], "arya/lin-1-example"
                )
                self.assertNotIn("UNRELATED", str(handoff))

    def test_latest_exact_top_level_result_wins(self):
        comments = [
            comment("scope", "OLD", "3", id="a"),
            comment("scope", "NEW", "3", id="z"),
            comment("scope", "REPLY", "4", parentId="parent"),
            comment("scope", "INLINE", "5", quotedText="anchor"),
            comment(HEADERS["scope"] + " ", "NEAR", "6"),
        ]
        handoff = select_handoff(issue(), comments, "implement")
        self.assertEqual(handoff["context"], {"scope": f"{HEADERS['scope']}\n\nNEW"})

        existing = select_handoff(
            issue(), comments + [comment("implement", "CURRENT", "7")], "implement"
        )
        self.assertEqual(set(existing["context"]), {"existing"})
        self.assertIn("CURRENT", existing["context"]["existing"])

    def test_existing_rca_keeps_original_intake_for_reinvestigation(self):
        prior = comment("rca", "WEAK-RCA", "3")
        handoff = select_handoff(issue(), [prior], "rca")

        self.assertEqual(
            set(handoff["context"]),
            {"intake", "existing", "existing_comment_id"},
        )
        self.assertIn("Intake", handoff["context"]["intake"])
        self.assertIn("WEAK-RCA", handoff["context"]["existing"])
        self.assertEqual(handoff["context"]["existing_comment_id"], "WEAK-RCA")

    def test_immediately_preceding_legacy_handoffs_reach_the_upgrade_workflow(self):
        legacy_sections = {
            "scope": "### Outcome\nPrior scope\n\n### Validation\n- old check",
            "implement": (
                "### Review contract\nPrior contract\n\n### Verification\n- old check"
            ),
            "review": "### Review basis\nPrior review\n\n### Verification\n- old check",
        }
        for phase, sections in legacy_sections.items():
            with self.subTest(phase=phase):
                body = f"{HEADERS[phase]}\n\n{sections}"
                prior = {
                    "id": f"legacy-{phase}",
                    "body": body,
                    "createdAt": "3",
                    "parentId": None,
                }
                handoff = select_handoff(issue(), [prior], phase)
                self.assertEqual(handoff["context"], {"existing": body})
                self.assertNotIn("### Evidence ledger", body)

    def test_missing_or_ambiguous_input_fails_closed(self):
        ambiguous = issue()
        ambiguous["description"] += "\n**Kind:** Feature"
        self.assertEqual(
            select_handoff(ambiguous, [], "scope")["context"],
            {"missing": "**Kind:** Bug | Feature"},
        )
        self.assertEqual(
            select_handoff(issue(), [], "implement")["context"],
            {"missing": HEADERS["scope"]},
        )


if __name__ == "__main__":
    unittest.main()
