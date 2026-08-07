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


class TweedRunnerTests(unittest.TestCase):
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
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(ROOT, "rca", "COR-1")
            observed["omit_event"] = True
            fallback = RUNNER.run_phase(ROOT, "rca", "COR-1")

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertIsNone(fallback["resume_session_id"])
        self.assertEqual(observed["env"][RUNNER.PHASE_CHILD_ENV], "1")
        self.assertIn("already the Tweed phase coordinator", observed["prompt"])
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
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            result = RUNNER.run_phase(repository, phase, answer, session_id)

        self.assertEqual(result["state"], "completed")
        self.assertEqual(observed["command"][:3], ["/bin/codex", "exec", "resume"])
        self.assertEqual(observed["command"][-2:], [SESSION_ID, "-"])
        self.assertIn("Use production.", observed["prompt"])
        self.assertNotIn("# Tweed Bug RCA", observed["prompt"])
