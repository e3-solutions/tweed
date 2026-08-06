import importlib.machinery
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("tweed_runner", str(ROOT / "tweed"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
TWEED = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(TWEED)


def ready_handoff(phase="scope", kind="bug", artifact_types=None):
    artifact_types = artifact_types or TWEED.EXPECTED_ARTIFACTS[phase][kind]
    return {
        "phase": phase,
        "state": "ready",
        "issue": "LIN-123",
        "linear_url": "https://linear.app/example/issue/LIN-123/example",
        "title": "Example issue",
        "kind": kind,
        "artifacts": [
            {"type": artifact_type, "content": f"EXACT_{artifact_type.upper()}"}
            for artifact_type in artifact_types
        ],
        "existing_result": None,
        "summary": "READY_SUMMARY_SENTINEL",
        "question": None,
        "next_action": "READY_NEXT_ACTION_SENTINEL",
    }


def completed_receipt(phase):
    needs_git = phase in {"implement", "review", "publish"}
    return {
        "phase": phase,
        "state": "completed",
        "issue": "LIN-123",
        "linear_url": "https://linear.app/example/issue/LIN-123/example",
        "result": TWEED.COMPLETED_RESULTS[phase],
        "summary": "completed",
        "question": None,
        "next_action": None,
        "branch": "tweed/lin-123-example" if needs_git else None,
        "commit": "a" * 40 if needs_git else None,
        "pull_request_url": "https://github.com/example/repo/pull/1"
        if phase == "publish"
        else None,
    }


class HandoffSelectionTests(unittest.TestCase):
    def test_each_phase_has_an_exact_typed_artifact_contract(self):
        self.assertEqual(TWEED.EXPECTED_ARTIFACTS["rca"]["bug"], ["intake"])
        self.assertEqual(TWEED.EXPECTED_ARTIFACTS["scope"]["bug"], ["rca"])
        self.assertEqual(TWEED.EXPECTED_ARTIFACTS["scope"]["feature"], ["intake"])
        self.assertEqual(TWEED.EXPECTED_ARTIFACTS["implement"]["bug"], ["scope"])
        self.assertEqual(
            TWEED.EXPECTED_ARTIFACTS["review"]["bug"],
            ["scope", "implementation"],
        )
        self.assertEqual(
            TWEED.EXPECTED_ARTIFACTS["publish"]["bug"],
            ["implementation", "review"],
        )

    def test_loader_asks_for_only_the_phase_contract(self):
        for phase, kind in (
            ("rca", "bug"),
            ("scope", "bug"),
            ("scope", "feature"),
            ("implement", "feature"),
            ("review", "bug"),
            ("publish", "feature"),
        ):
            with self.subTest(phase=phase, kind=kind):
                handoff = ready_handoff(phase, kind)
                with mock.patch.object(
                    TWEED, "run_codex_json", return_value=handoff
                ) as run_codex:
                    self.assertEqual(
                        TWEED.load_handoff(ROOT, phase, "LIN-123"), handoff
                    )
                prompt = run_codex.call_args.args[1]
                self.assertIn(TWEED.HANDOFF_SELECTIONS[phase], prompt)
                self.assertIn(
                    "do not summarize, rewrite, or add material from other issue",
                    prompt,
                )
                self.assertFalse(run_codex.call_args.kwargs["include_children"])

    def test_loader_rejects_an_unexpected_artifact(self):
        handoff = ready_handoff("scope", "bug", ["intake"])
        with mock.patch.object(TWEED, "run_codex_json", return_value=handoff):
            with self.assertRaisesRegex(RuntimeError, "wrong artifacts"):
                TWEED.load_handoff(ROOT, "scope", "LIN-123")

    def test_worker_prompt_excludes_loader_notes_and_raw_invocation(self):
        handoff = ready_handoff("scope", "bug")
        handoff["existing_result"] = "EXACT_EXISTING_SCOPE"
        prompt = TWEED.build_phase_prompt(
            ROOT, "scope", "RAW_INVOCATION_SENTINEL", handoff
        )

        self.assertIn("EXACT_RCA", prompt)
        self.assertIn("EXACT_EXISTING_SCOPE", prompt)
        self.assertNotIn("RAW_INVOCATION_SENTINEL", prompt)
        self.assertNotIn("READY_SUMMARY_SENTINEL", prompt)
        self.assertNotIn("READY_NEXT_ACTION_SENTINEL", prompt)

    def test_user_answer_is_preserved_as_relevant_supplemental_input(self):
        prompt = TWEED.build_phase_prompt(
            ROOT,
            "scope",
            "LIN-123 Question: Which API? Answer: Keep v1.",
            ready_handoff("scope", "bug"),
        )

        self.assertIn(
            '"supplemental_input": "Question: Which API? Answer: Keep v1."',
            prompt,
        )

    def test_non_create_phase_loads_handoff_before_starting_worker(self):
        handoff = ready_handoff("scope", "bug")
        receipt = completed_receipt("scope")
        with mock.patch.object(
            TWEED, "load_handoff", return_value=handoff
        ) as load_handoff, mock.patch.object(
            TWEED, "run_codex_json", return_value=receipt
        ) as run_codex:
            self.assertEqual(TWEED.run_phase(ROOT, "scope", "LIN-123"), receipt)

        load_handoff.assert_called_once_with(ROOT, "scope", "LIN-123")
        self.assertTrue(run_codex.call_args.kwargs["include_children"])
        self.assertIn("EXACT_RCA", run_codex.call_args.args[1])

    def test_blocked_handoff_does_not_start_worker(self):
        handoff = ready_handoff("scope", "bug")
        handoff.update(
            {
                "state": "blocked",
                "artifacts": [],
                "summary": "RCA missing",
                "next_action": "Run RCA.",
            }
        )
        with mock.patch.object(
            TWEED, "load_handoff", return_value=handoff
        ), mock.patch.object(TWEED, "run_codex_json") as run_codex:
            receipt = TWEED.run_phase(ROOT, "scope", "LIN-123")

        run_codex.assert_not_called()
        self.assertEqual(receipt["state"], "blocked")
        self.assertEqual(receipt["summary"], "RCA missing")


if __name__ == "__main__":
    unittest.main()
