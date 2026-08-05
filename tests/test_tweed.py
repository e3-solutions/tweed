import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "019fd385-da76-77f3-bd3a-2f1e4e49b936"


def load_runner():
    loader = importlib.machinery.SourceFileLoader("tweed_runner", str(ROOT / "tweed"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RUNNER = load_runner()


def receipt(state="completed", result="established"):
    return {
        "phase": "rca",
        "state": state,
        "issue": "COR-1",
        "linear_url": "https://linear.example/COR-1",
        "result": result,
        "summary": "summary",
        "question": "Which environment?" if state == "needs-input" else None,
        "next_action": None,
        "branch": None,
        "commit": None,
        "pull_request_url": None,
        "resume_session_id": None,
    }


class TweedRunnerTests(unittest.TestCase):
    def test_phase_templates_define_complete_durable_linear_handoffs(self):
        required_sections = {
            "rca": (
                "### Root cause",
                "### Problem definition",
                "### Causal chain",
                "#### Reproduction and runtime",
                "#### Repository, configuration, and history",
                "### Affected boundaries and files",
                "### Alternatives checked",
                "### Remaining uncertainty",
                "### Investigation map",
            ),
            "scope": (
                "### Handoff basis",
                "### Outcome",
                "### Repository evidence",
                "### Reuse decision",
                "### Change surface",
                "### Implementation steps",
                "### Acceptance criteria",
                "### Validation",
                "### Risks and safeguards",
                "### Non-goals",
                "### Alternatives considered",
                "### Decisions and assumptions",
                "### Debate map",
            ),
            "implement": (
                "### Delivered behavior",
                "### Changed files and responsibilities",
                "### Verification",
                "### Review findings",
                "### Deviations",
                "### Remaining work",
                "### Git handoff",
                "### Complete review handoff",
                "### Implementation map",
            ),
            "review": (
                "### Review basis",
                "### Final axis results",
                "### Findings",
                "### Changes made",
                "### Verification",
                "### Remaining concerns",
                "### Git handoff",
                "### Readiness",
                "### Review map",
            ),
            "publish": (
                "### Delivery",
                "### Final delivery state",
                "Pull request state:",
                "Reviewed commit:",
                "Remaining conditions:",
            ),
        }

        for phase, sections in required_sections.items():
            workflow_name, _ = RUNNER.WORKFLOWS[phase]
            template = (ROOT / "workflows" / workflow_name).read_text()
            with self.subTest(phase=phase):
                self.assertIn("## Durable phase boundary", template)
                self.assertIn("only request-specific input", template)
                self.assertIn("Linear issue identifier", template)
                self.assertIn("control-plane data only", template)
                self.assertIn("re-read", template)
                for section in sections:
                    self.assertIn(section, template)

    def test_later_phase_prompts_start_fresh_and_read_linear(self):
        for phase in ("rca", "scope", "implement", "review", "publish"):
            _, assignment = RUNNER.WORKFLOWS[phase]
            with self.subTest(phase=phase):
                self.assertIn("Start fresh with only the issue identifier", assignment)
                self.assertIn("Linear", assignment)

        self.assertNotIn("report_markdown", RUNNER.RECEIPT_FIELDS)
        self.assertNotIn("handoff", RUNNER.RECEIPT_FIELDS)

    def test_coordinator_uses_medium_reasoning(self):
        self.assertEqual(RUNNER.COORDINATOR_EFFORT, "medium")
        with mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"):
            command = RUNNER.codex_command(
                ROOT, Path("schema.json"), Path("receipt.json"), None
            )
        self.assertIn('model_reasoning_effort="medium"', command)

    def test_initial_and_resume_commands_are_distinct(self):
        with mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"):
            initial = RUNNER.codex_command(
                ROOT, Path("schema.json"), Path("receipt.json"), None
            )
            resumed = RUNNER.codex_command(
                ROOT, Path("schema.json"), Path("receipt.json"), SESSION_ID
            )
        self.assertEqual(initial[:2], ["/bin/codex", "exec"])
        self.assertIn("-C", initial)
        self.assertNotIn("resume", initial)
        self.assertEqual(resumed[:3], ["/bin/codex", "exec", "resume"])
        self.assertNotIn("-C", resumed)
        self.assertEqual(resumed[-2:], [SESSION_ID, "-"])

    def test_phase_child_environment_is_explicit(self):
        environment = RUNNER.child_environment()
        self.assertEqual(environment[RUNNER.PHASE_CHILD_ENV], "1")

    def test_nested_cli_invocation_is_rejected_before_starting_codex(self):
        environment = {**os.environ, RUNNER.PHASE_CHILD_ENV: "1"}
        completed = subprocess.run(
            [str(ROOT / "tweed"), "RCA", "COR-1"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(completed.stdout)
        self.assertEqual(failure["state"], "failed")
        self.assertIn("nested Tweed invocation blocked", failure["summary"])

    def test_extracts_resumable_session_from_json_events(self):
        events = io.StringIO(
            "not-json\n"
            + json.dumps({"type": "thread.started", "thread_id": SESSION_ID})
            + "\n"
        )
        self.assertEqual(RUNNER.extract_session_id(events), SESSION_ID)

    def test_needs_input_receipt_gets_session_id(self):
        observed = {}

        def fake_run(command, **kwargs):
            observed["command"] = command
            observed["env"] = kwargs["env"]
            observed["prompt"] = kwargs["input"]
            kwargs["stdout"].write(
                json.dumps({"type": "thread.started", "thread_id": SESSION_ID}) + "\n"
            )
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(receipt("needs-input", "needs-input")))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(ROOT, "rca", "COR-1")

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertEqual(observed["env"][RUNNER.PHASE_CHILD_ENV], "1")
        self.assertIn("already the Tweed phase coordinator", observed["prompt"])
        self.assertIn(
            "the Input below is only a Linear issue identifier", observed["prompt"]
        )
        self.assertIn(
            "verified Linear comment is the sole cross-phase handoff",
            observed["prompt"],
        )
        self.assertNotIn("report_markdown", observed["prompt"])

    def test_resume_continues_session_with_only_the_answer(self):
        observed = {}

        def fake_run(command, **kwargs):
            observed["command"] = command
            observed["prompt"] = kwargs["input"]
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(receipt()))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(
                ROOT, "rca", "Use production.", resume_session_id=SESSION_ID
            )

        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["resume_session_id"], None)
        self.assertEqual(observed["command"][-2:], [SESSION_ID, "-"])
        self.assertIn("Use production.", observed["prompt"])
        self.assertNotIn("# Tweed Bug RCA", observed["prompt"])

    def test_resume_cli_parsing_requires_phase_session_and_answer(self):
        argv = [
            "tweed",
            "--repo",
            str(ROOT),
            "resume",
            "RCA",
            SESSION_ID,
            "Use",
            "production.",
        ]
        with mock.patch.object(sys, "argv", argv):
            repository, phase, answer, session_id = RUNNER.parse()
        self.assertEqual(repository, ROOT)
        self.assertEqual(phase, "rca")
        self.assertEqual(answer, "Use production.")
        self.assertEqual(session_id, SESSION_ID)


if __name__ == "__main__":
    unittest.main()
