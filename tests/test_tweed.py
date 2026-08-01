from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai_codex.types import TurnStatus


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("tweed_module", str(ROOT / "tweed"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
TWEED = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(TWEED)


class FakeThread:
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)
        self.prompts: list[str] = []
        self.options: list[dict] = []

    def run(self, prompt: str, **options):
        self.prompts.append(prompt)
        self.options.append(options)
        return SimpleNamespace(
            status=TurnStatus.completed,
            final_response=next(self.responses),
            error=None,
        )


class InteractiveInput:
    def isatty(self) -> bool:
        return True


class NonInteractiveInput:
    def isatty(self) -> bool:
        return False


class TweedTests(unittest.TestCase):
    def test_report_status_uses_first_nonblank_line(self):
        self.assertEqual(TWEED.report_status("\nStatus: scoped\n# Scope"), "scoped")
        self.assertIsNone(TWEED.report_status("# Scope\nStatus: scoped"))

    def test_folder_project_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            config = Path(directory) / "config.json"
            with patch.dict(os.environ, {"TWEED_CONFIG": str(config)}):
                TWEED.set_linear_project("Customer Experience", root)
                self.assertEqual(
                    TWEED.linear_project(root),
                    "Customer Experience",
                )
                stored = json.loads(config.read_text())
                self.assertEqual(
                    stored["folders"][str(root.resolve())]["linear_project"],
                    "Customer Experience",
                )
                TWEED.set_linear_project(None, root)
                self.assertIsNone(TWEED.linear_project(root))

    def test_clarification_continues_in_same_thread(self):
        thread = FakeThread(
            [
                "Status: needs-input\n\n# Clarification needed\n\nWhich behavior?",
                "Status: established\n\n# Root cause\n\nComplete.",
            ]
        )
        with (
            patch.object(TWEED.sys, "stdin", InteractiveInput()),
            patch("builtins.input", return_value="Use the existing export behavior"),
        ):
            report = TWEED.run_with_clarifications(thread, "Investigate")

        self.assertEqual(TWEED.report_status(report), "established")
        self.assertEqual(len(thread.prompts), 2)
        self.assertIn("Use the existing export behavior", thread.prompts[1])

    def test_noninteractive_clarification_stops_without_follow_up(self):
        thread = FakeThread(["Status: needs-input\n\n# Clarification needed"])
        with patch.object(TWEED.sys, "stdin", NonInteractiveInput()):
            report = TWEED.run_with_clarifications(thread, "Investigate")

        self.assertEqual(TWEED.report_status(report), "needs-input")
        self.assertEqual(thread.prompts, ["Investigate"])

    def test_linear_create_sync_is_gate_only_and_project_scoped(self):
        prompt = TWEED.linear_sync_prompt(
            "root-cause",
            "Status: established\n\n# Root cause",
            project="Customer Experience",
        )
        self.assertTrue(prompt.startswith("TWEED_LINEAR_SYNC"))
        self.assertIn("Create exactly one Linear issue", prompt)
        self.assertIn("Customer Experience", prompt)
        self.assertIn("Do not add a comment", prompt)

    def test_linear_sync_runs_only_for_completed_phase_status(self):
        self.assertTrue(TWEED.should_sync_linear("root-cause", "established"))
        self.assertTrue(TWEED.should_sync_linear("scope", "scoped"))
        self.assertFalse(TWEED.should_sync_linear("root-cause", "needs-input"))
        self.assertFalse(TWEED.should_sync_linear("scope", "blocked"))
        self.assertFalse(TWEED.should_sync_linear("implement", "partial"))

    def test_linear_update_sync_preserves_completed_handoffs(self):
        prompt = TWEED.linear_sync_prompt(
            "scope",
            "Status: scoped\n\n# Solution scope",
            issue="ENG-123",
        )
        self.assertIn("Update exactly the existing Linear issue ENG-123", prompt)
        self.assertIn("Preserve all previously completed Tweed phase content", prompt)
        self.assertIn("Do not create a new issue", prompt)

    def test_linear_sync_turn_is_filesystem_read_only(self):
        thread = FakeThread(["Status: synced\nLinear issue: ENG-123"])
        receipt = TWEED.sync_linear(
            thread,
            "scope",
            "Status: scoped\n\n# Solution scope",
            issue="ENG-123",
        )
        self.assertEqual(TWEED.report_status(receipt), "synced")
        self.assertEqual(thread.options, [{"sandbox": TWEED.Sandbox.read_only}])

    def test_issue_phase_prompt_allows_reads_but_forbids_writes(self):
        prompt = TWEED.issue_phase_prompt("ENG-123", "solution-scoping")
        self.assertIn("Linear MCP read tools", prompt)
        self.assertIn("Do not create, update, or comment", prompt)


if __name__ == "__main__":
    unittest.main()
