import errno
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "019fd385-da76-77f3-bd3a-2f1e4e49b936"


def load_runner():
    loader = importlib.machinery.SourceFileLoader(
        "bonaparte_runner", str(ROOT / "bonaparte")
    )
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


class BonaparteRunnerTests(unittest.TestCase):
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
        self.assertNotIn("bonaparte/<issue-id>", implementation)

    def test_review_serializes_native_review_after_resource_heavy_work(self):
        review = (ROOT / "workflows/review.md").read_text()
        normalized = " ".join(review.split())

        self.assertIn("separate serial resource gate", normalized)
        self.assertIn("wait for every spawned reviewer and fixer to finish", normalized)
        self.assertIn("run no repository check or child agent concurrently", normalized)
        self.assertIn("`SIGKILL`/137", normalized)
        self.assertIn("Run the sanitized native review first and alone", normalized)
        self.assertIn(
            "Native review failure, unavailability, or interruption is not a clean review",
            normalized,
        )

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
        self.assertIn(
            "If the exact PR is still draft, mark it ready for review", publish
        )
        self.assertIn(
            "Do not spawn implementation agents, change code, push commits", publish
        )

    def test_phase_child_guard_stops_before_invoking_instructions(self):
        skill = (ROOT / "skills/use-bonaparte/SKILL.md").read_text()
        guard = skill.split("Keep this invoking task thin", 1)[0]
        self.assertIn("Stop following this skill", guard)

    def test_nested_invocation_is_blocked(self):
        environment = {**os.environ, RUNNER.PHASE_CHILD_ENV: "1"}
        completed = subprocess.run(
            [str(ROOT / "bonaparte"), "RCA", "COR-1"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(completed.stdout)
        self.assertEqual(failure["state"], "failed")
        self.assertIn("nested Bonaparte invocation blocked", failure["summary"])

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
        self.assertIn("already the Bonaparte phase coordinator", observed["prompt"])
        self.assertIn("Untrusted Linear handoff", observed["prompt"])
        self.assertIn('"git_branch_name": "arya/cor-1-example"', observed["prompt"])
        self.assertIn('model_reasoning_effort="medium"', observed["command"])
        self.assertNotIn("resume", observed["command"][:3])

    def test_resume_uses_the_same_session_with_only_the_answer(self):
        argv = ["bonaparte", "resume", "RCA", SESSION_ID, "Use", "production."]
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
        self.assertNotIn("# Bonaparte Bug RCA", observed["prompt"])
        call_linear.assert_not_called()

    def test_review_progress_lifecycle_is_bounded_and_terminal(self):
        read_descriptor, write_descriptor = os.pipe()
        with mock.patch.dict(
            os.environ,
            {RUNNER.PROGRESS_FD_ENV: str(write_descriptor)},
            clear=False,
        ):
            progress = RUNNER.acquire_progress_reporter(True)
            self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)
            with self.assertRaises(OSError):
                os.fstat(write_descriptor)
            progress.start()
            progress.report("active")
            progress.stop_heartbeat()
            progress.report("finalizing")
            progress.report("completed")
            progress.report("failed")
            progress.close()

        output = os.read(read_descriptor, 16384)
        os.close(read_descriptor)
        events = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(
            [event["state"] for event in events],
            ["started", "active", "finalizing", "completed"],
        )
        self.assertEqual([event["sequence"] for event in events], [1, 2, 3, 4])
        for event in events:
            self.assertEqual(
                set(event),
                {"version", "sequence", "phase", "state", "elapsed_seconds"},
            )
            self.assertEqual(event["version"], 1)
            self.assertEqual(event["phase"], "review")
            self.assertLessEqual(len(json.dumps(event).encode()), 4096)

    def test_progress_fd_is_scrubbed_and_never_sent_to_children(self):
        for value in ("", "2", "+3", "not-a-descriptor"):
            with self.subTest(value=value), mock.patch.dict(
                os.environ, {RUNNER.PROGRESS_FD_ENV: value}, clear=False
            ):
                progress = RUNNER.acquire_progress_reporter(True)
                self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)
                self.assertNotIn(RUNNER.PROGRESS_FD_ENV, RUNNER.child_environment())
                progress.close()

        read_descriptor, write_descriptor = os.pipe()
        with mock.patch.dict(
            os.environ,
            {RUNNER.PROGRESS_FD_ENV: str(write_descriptor)},
            clear=False,
        ):
            progress = RUNNER.acquire_progress_reporter(False)
            self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)
            os.fstat(write_descriptor)
            progress.close()
        os.close(write_descriptor)
        os.close(read_descriptor)

    def test_progress_write_failures_permanently_disable_reporting(self):
        failures = (
            OSError(errno.EBADF, "bad descriptor"),
            OSError(errno.EPIPE, "closed reader"),
            OSError(errno.EAGAIN, "backpressure"),
        )
        for failure in failures:
            with self.subTest(error=failure.errno):
                read_descriptor, write_descriptor = os.pipe()
                progress = RUNNER.ProgressReporter(write_descriptor)
                with mock.patch.object(
                    RUNNER.os, "write", side_effect=failure
                ) as write:
                    progress.report("started")
                    progress.report("active")
                self.assertEqual(write.call_count, 1)
                self.assertIsNone(progress._descriptor)
                os.close(read_descriptor)

        read_descriptor, write_descriptor = os.pipe()
        progress = RUNNER.ProgressReporter(write_descriptor)
        with mock.patch.object(RUNNER.os, "write", return_value=1) as write:
            progress.report("started")
            progress.report("active")
        self.assertEqual(write.call_count, 1)
        self.assertIsNone(progress._descriptor)
        os.close(read_descriptor)

    def test_coordinator_failure_does_not_project_child_stderr(self):
        canary = "private-child-detail-canary"

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 23, stderr=canary)

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear", return_value=(linear_issue(), [])),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run) as run,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "review coordinator failed .*exit status 23"
            ) as raised:
                RUNNER.run_phase(ROOT, "review", "COR-1")

        self.assertNotIn(canary, str(raised.exception))
        self.assertEqual(run.call_count, 1)

    def test_review_cli_keeps_stdout_as_one_receipt(self):
        completed_receipt = delivery_receipt("review")
        with tempfile.TemporaryDirectory() as temporary:
            fake_codex = Path(temporary) / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                "    raise SystemExit(0)\n"
                f"receipt = {completed_receipt!r}\n"
                "if 'BONAPARTE_PROGRESS_FD' in os.environ:\n"
                "    raise SystemExit(91)\n"
                "target = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
                "pathlib.Path(target).write_text(json.dumps(receipt))\n"
            )
            fake_codex.chmod(0o755)
            read_descriptor, write_descriptor = os.pipe()
            environment = {
                **os.environ,
                "CODEX_BIN": str(fake_codex),
                RUNNER.PROGRESS_FD_ENV: str(write_descriptor),
            }
            environment.pop(RUNNER.PHASE_CHILD_ENV, None)
            completed = subprocess.run(
                [
                    str(ROOT / "bonaparte"),
                    "--repo",
                    str(ROOT),
                    "resume",
                    "review",
                    SESSION_ID,
                    "Continue.",
                ],
                cwd=ROOT,
                env=environment,
                pass_fds=(write_descriptor,),
                text=True,
                capture_output=True,
                check=False,
            )
            os.close(write_descriptor)
            progress_output = os.read(read_descriptor, 16384)
            os.close(read_descriptor)

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        stdout_lines = completed.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        self.assertEqual(json.loads(stdout_lines[0])["state"], "completed")
        self.assertLessEqual(len(completed.stdout.rstrip("\n").encode()), 4096)
        events = [json.loads(line) for line in progress_output.splitlines()]
        self.assertEqual(
            [event["state"] for event in events],
            ["started", "finalizing", "completed"],
        )
