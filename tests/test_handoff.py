import runpy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "bonaparte"))
RUNNER_GLOBALS = RUNNER["run_phase"].__globals__
HEADERS = RUNNER["PHASE_HEADERS"]
select_handoff = RUNNER["select_handoff"]
recover_terminal_receipt = RUNNER["recover_terminal_receipt"]
trusted_git_target = RUNNER["trusted_git_target"]


def live_pr(
    branch="arya/lin-1-example", commit="b" * 40, base="main", draft=True
):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "headRefName": branch,
                "headRefOid": commit,
                "baseRefName": base,
                "isDraft": draft,
                "state": "OPEN",
                "url": "https://github.com/o/r/pull/1",
            }
        ),
    )


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
    def test_trusted_git_target_uses_origin_and_default_base(self):
        def output(_repository, *arguments):
            if arguments == ("remote", "get-url", "origin"):
                return "git@github.com:e3-solutions/tweed.git"
            if arguments == (
                "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"
            ):
                return "origin/main"
            return None

        with mock.patch.dict(RUNNER_GLOBALS, {"git_output": output}):
            self.assertEqual(
                trusted_git_target(Path(".")),
                ("e3-solutions/tweed", "main"),
            )

    def test_current_or_downstream_terminal_evidence_recovers_without_driver(self):
        git_handoff = (
            "\n\n**Verdict:** Ready to publish\n\n### Git handoff\n"
            "- Branch: `arya/lin-1-example`\n"
            "- Implementation commit: `" + "a" * 40 + "`\n"
            "- Reviewed commit: `" + "b" * 40 + "`\n"
            "- Draft PR: `https://github.com/o/r/pull/1`\n"
            "- Base: `main`"
        )
        review = comment("review", "unused", "5")
        review["body"] = HEADERS["review"] + git_handoff
        stale = comment("implement", "### Evidence ledger\nlegacy", "4")
        driver = mock.Mock()

        with (
            mock.patch.dict(
                RUNNER_GLOBALS,
                {"call_linear": mock.Mock(return_value=(issue(), [stale, review]))},
            ),
            mock.patch.dict(
                RUNNER_GLOBALS,
                {
                    "AppServerPhaseDriver": driver,
                    "_SUBPROCESS_RUN": mock.Mock(return_value=live_pr()),
                    "trusted_git_target": mock.Mock(return_value=("o/r", "main")),
                },
            ),
        ):
            receipt = RUNNER["run_phase"](Path(__file__).resolve().parents[1], "implement", "LIN-1")

        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["result"], "implemented")
        self.assertEqual(receipt["commit"], "b" * 40)
        driver.assert_not_called()

    def test_terminal_recovery_fails_closed_on_missing_git_provenance(self):
        review = comment("review", "unused", "5")
        review["body"] = (
            HEADERS["review"]
            + "\n\n**Verdict:** Ready to publish\n\n### Git handoff\n"
            + "- Branch: `arya/lin-1-example`"
        )
        recovered = recover_terminal_receipt(issue(), [review], "implement")
        self.assertEqual(recovered["state"], "blocked")
        self.assertIn("missing or stale", recovered["summary"])

    def test_terminal_guard_ignores_replies_inline_near_matches_and_legacy(self):
        candidates = [
            comment("scope", "**Status:** Scoped", "1", parentId="parent"),
            comment("scope", "**Status:** Scoped", "2", quotedText="anchor"),
            comment(HEADERS["scope"] + " ", "**Status:** Scoped", "3"),
            comment("scope", "### Proof obligations\nlegacy", "4"),
        ]
        self.assertIsNone(recover_terminal_receipt(issue(), candidates, "scope"))

    def test_downstream_phase_order_wins_over_stale_requested_terminal(self):
        implementation = comment("implement", "unused", "9")
        implementation["body"] = HEADERS["implement"] + "\n\n**Status:** Implemented"
        published = comment("publish", "unused", "2")
        published["body"] = (
            HEADERS["publish"]
            + "\n\n**Status:** Ready for review\n\n### Delivery\n"
            + "- Pull request: https://github.com/o/r/pull/1\n"
            + "- Branch: `arya/lin-1-example`\n"
            + "- Reviewed commit: `" + "c" * 40 + "`\n"
            + "- Base: `main`"
        )
        with mock.patch.dict(
            RUNNER_GLOBALS,
            {
                "_SUBPROCESS_RUN": mock.Mock(
                    return_value=live_pr(commit="c" * 40, draft=False)
                )
            },
        ):
            recovered = recover_terminal_receipt(
                issue(), [implementation, published], "implement", ("o/r", "main")
            )
        self.assertEqual(recovered["state"], "completed")
        self.assertEqual(recovered["commit"], "c" * 40)

    def test_terminal_recovery_blocks_when_live_pull_request_head_advanced(self):
        review = comment("review", "unused", "5")
        review["body"] = (
            HEADERS["review"]
            + "\n\n**Verdict:** Ready to publish\n\n### Git handoff\n"
            + "- Branch: `arya/lin-1-example`\n"
            + "- Reviewed commit: `" + "b" * 40 + "`\n"
            + "- Draft PR: `https://github.com/o/r/pull/1`\n"
            + "- Base: `main`"
        )
        with mock.patch.dict(
            RUNNER_GLOBALS,
            {"_SUBPROCESS_RUN": mock.Mock(return_value=live_pr(commit="c" * 40))},
        ):
            recovered = recover_terminal_receipt(
                issue(), [review], "implement", ("o/r", "main")
            )

        self.assertEqual(recovered["state"], "blocked")
        self.assertIn("stale", recovered["summary"])

    def test_terminal_recovery_blocks_retargeted_or_redrafted_publish(self):
        published = comment("publish", "unused", "5")
        published["body"] = (
            HEADERS["publish"]
            + "\n\n**Status:** Ready for review\n\n### Delivery\n"
            + "- Branch: `arya/lin-1-example`\n"
            + "- Reviewed commit: `" + "b" * 40 + "`\n"
            + "- Pull request: https://github.com/o/r/pull/1\n"
            + "- Base: `main`"
        )
        for current in (
            live_pr(base="staging", draft=False),
            live_pr(base="main", draft=True),
        ):
            with self.subTest(current=current.stdout), mock.patch.dict(
                RUNNER_GLOBALS,
                {"_SUBPROCESS_RUN": mock.Mock(return_value=current)},
            ):
                recovered = recover_terminal_receipt(
                    issue(), [published], "publish", ("o/r", "main")
                )
                self.assertEqual(recovered["state"], "blocked")

    def test_terminal_recovery_blocks_other_repository(self):
        review = comment("review", "unused", "5")
        review["body"] = (
            HEADERS["review"]
            + "\n\n**Verdict:** Ready to publish\n\n### Git handoff\n"
            + "- Branch: `arya/lin-1-example`\n"
            + "- Reviewed commit: `" + "b" * 40 + "`\n"
            + "- Draft PR: `https://github.com/o/r/pull/1`\n"
            + "- Base: `main`"
        )
        recovered = recover_terminal_receipt(
            issue(), [review], "implement", ("other/repository", "main")
        )
        self.assertEqual(recovered["state"], "blocked")

    def test_supplemental_guidance_disables_terminal_fast_path(self):
        review = comment("review", "unused", "5")
        review["body"] = HEADERS["review"] + "\n\n**Verdict:** Ready to publish"
        recovery = mock.Mock()
        with (
            mock.patch.dict(
                RUNNER_GLOBALS,
                {
                    "call_linear": mock.Mock(return_value=(issue(), [review])),
                    "recover_terminal_receipt": recovery,
                    "AppServerPhaseDriver": mock.Mock(
                        side_effect=RuntimeError("coordinator started")
                    ),
                },
            ),
            self.assertRaisesRegex(RuntimeError, "coordinator started"),
        ):
            RUNNER["run_phase"](
                Path(__file__).resolve().parents[1],
                "implement",
                "LIN-1 Expected pull-request base: staging",
            )
        recovery.assert_not_called()

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

    def test_existing_publish_keeps_latest_review_for_safe_reconciliation(self):
        review = comment("review", "REVIEWED-DESCENDANT", "4")
        published = comment("publish", "STALE-PUBLISH", "5")

        handoff = select_handoff(issue(), [review, published], "publish")

        self.assertEqual(
            handoff["context"],
            {
                "existing": published["body"],
                "review": review["body"],
                "existing_comment_id": "STALE-PUBLISH",
            },
        )

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

    def test_existing_rca_selects_bug_scope_for_legacy_untyped_issue(self):
        legacy = issue()
        legacy["description"] = "Legacy issue without a kind marker"
        rca = comment("rca", "ESTABLISHED-RCA", "1")

        handoff = select_handoff(legacy, [rca], "scope")

        self.assertEqual(handoff["issue"]["kind"], "bug")
        self.assertEqual(handoff["context"], {"rca": rca["body"]})


if __name__ == "__main__":
    unittest.main()
