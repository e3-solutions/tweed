import importlib.machinery
import importlib.util
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


def receipt(state="completed"):
    return {
        "phase": "rca",
        "state": state,
        "issue": "COR-1",
        "linear_url": "https://linear.example/COR-1",
        "result": "established" if state == "completed" else "needs-input",
        "summary": "summary",
        "question": "Which environment?" if state == "needs-input" else None,
        "next_action": None,
        "branch": None,
        "commit": None,
        "pull_request_url": None,
    }


def linear_issue():
    return {
        "identifier": "COR-1",
        "title": "Example",
        "url": "https://linear.example/COR-1",
        "description": "**Kind:** Bug\n\nExample intake",
        "gitBranchName": "arya/cor-1-example",
        "labels": [],
    }


def delivery_receipt(phase, pull_request_url="https://github.example/pr/1"):
    return {
        "phase": phase,
        "state": "completed",
        "issue": "COR-1",
        "linear_url": "https://linear.example/COR-1",
        "result": RUNNER.COMPLETED_RESULTS[phase],
        "summary": "done",
        "question": None,
        "next_action": None,
        "branch": "arya/cor-1-example",
        "commit": "a" * 40,
        "pull_request_url": pull_request_url,
    }


class TweedRunnerTests(unittest.TestCase):
    def test_coordinator_reasoning_is_medium(self):
        self.assertEqual(RUNNER.COORDINATOR_EFFORT, "medium")

    def test_workflows_require_complete_evidence_bearing_handoffs(self):
        required_markers = {
            "bug-rca.md": [
                "### Causal chain",
                "#### Reproduction and runtime",
                "### Affected boundaries and files",
                "| Alternative | Evidence tested | Result |",
                "| Role | Material conclusion | Evidence |",
            ],
            "scope.md": [
                "### Handoff basis",
                "| File or boundary | Current evidence | Exact responsibility |",
                "| Risk | Evidence and affected boundary | Safeguard |",
                "| Alternative | Evidence | Decision and reason |",
                "| Axis/role | Material conclusion | Evidence |",
            ],
            "implement.md": [
                "### Review contract",
                "### Delivered behavior",
                "| File or boundary | Responsibility delivered |",
                "| Command or diagnostic | Result | Scope/criterion proved |",
                "| Finding | Evidence and consequence | Disposition/fix |",
                "| Role | Material conclusion | Evidence |",
            ],
            "review.md": [
                "### Review basis",
                "| Axis | Result | Evidence | Remaining concern |",
                "| ID | Axis | Material consequence/contract | Evidence |",
                "| Exact command or diagnostic | Result | Contract/finding proved |",
                "| Role | Material conclusion | Evidence |",
            ],
            "publish.md": [
                "### Delivery",
                "Pull request state: Open and non-draft",
                "### Final delivery state",
                "Remaining conditions:",
            ],
        }

        for filename, markers in required_markers.items():
            workflow = (ROOT / "workflows" / filename).read_text()
            with self.subTest(workflow=filename):
                self.assertIn("After writing, re-read the comment", workflow)
                for marker in markers:
                    self.assertIn(marker, workflow)

        implementation = (ROOT / "workflows/implement.md").read_text()
        self.assertIn("issue.git_branch_name", implementation)
        self.assertNotIn("tweed/<issue-id>", implementation)

    def test_delivery_phases_require_the_draft_pr_handoff(self):
        for phase in ("implement", "review", "publish"):
            with self.subTest(phase=phase):
                with self.assertRaisesRegex(RuntimeError, "missing its pull request"):
                    RUNNER.require_pull_request(delivery_receipt(phase, None), phase)
                RUNNER.require_pull_request(delivery_receipt(phase), phase)

    def test_workflows_keep_one_pr_current_until_publish(self):
        implementation = (ROOT / "workflows/implement.md").read_text()
        review = (ROOT / "workflows/review.md").read_text()
        publish = (ROOT / "workflows/publish.md").read_text()

        self.assertIn("push it normally\n   to the draft PR", implementation)
        self.assertIn("- Draft PR: `[URL]`", implementation)
        self.assertIn("same draft PR", review)
        self.assertIn("- Draft PR: `[URL]`", review)
        self.assertIn("Mark that exact draft ready for review", publish)
        self.assertIn(
            "Do not spawn implementation agents, change code, push commits", publish
        )

    def test_phase_child_guard_stops_before_invoking_instructions(self):
        skill = (ROOT / "skills/use-tweed/SKILL.md").read_text()
        guard = skill.split("Keep this invoking task thin", 1)[0]
        self.assertIn("Stop following this skill", guard)

    def test_nested_invocation_is_blocked(self):
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

    def test_needs_input_exposes_the_marked_coordinator_session(self):
        observed = {}

        def fake_run(command, **kwargs):
            observed.update(command=command, env=kwargs["env"], prompt=kwargs["input"])
            if not observed.get("omit_event"):
                kwargs["stdout"].write(
                    json.dumps({"type": "thread.started", "thread_id": SESSION_ID})
                    + "\n"
                )
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(receipt("needs-input")))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear", return_value=(linear_issue(), [])),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(ROOT, "rca", "COR-1")
            observed["omit_event"] = True
            fallback = RUNNER.run_phase(ROOT, "rca", "COR-1")

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertIsNone(fallback["resume_session_id"])
        self.assertEqual(observed["env"][RUNNER.PHASE_CHILD_ENV], "1")
        self.assertIn("already the Tweed phase coordinator", observed["prompt"])
        self.assertIn("Untrusted Linear handoff", observed["prompt"])
        self.assertIn('"git_branch_name": "arya/cor-1-example"', observed["prompt"])
        self.assertIn('model_reasoning_effort="medium"', observed["command"])
        self.assertNotIn("resume", observed["command"][:3])

    def test_resume_uses_the_same_session_with_only_the_answer(self):
        argv = ["tweed", "resume", "RCA", SESSION_ID, "Use", "production."]
        with mock.patch.object(sys, "argv", argv):
            repository, phase, answer, session_id = RUNNER.parse()
        observed = {}

        def fake_run(command, **kwargs):
            observed.update(command=command, prompt=kwargs["input"])
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(receipt()))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear") as call_linear,
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(repository, phase, answer, session_id)

        self.assertEqual(result["state"], "completed")
        self.assertEqual(observed["command"][:3], ["/bin/codex", "exec", "resume"])
        self.assertEqual(observed["command"][-2:], [SESSION_ID, "-"])
        self.assertIn("Use production.", observed["prompt"])
        self.assertNotIn("# Tweed Bug RCA", observed["prompt"])
        call_linear.assert_not_called()
