import errno
import importlib.machinery
import importlib.util
import io
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


def run_review_cli(fake_receipt):
    with tempfile.TemporaryDirectory() as temporary:
        fake_codex = Path(temporary) / "codex"
        fake_codex.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "if '--version' in sys.argv:\n"
            "    raise SystemExit(0)\n"
            f"receipt = {fake_receipt!r}\n"
            "if 'BONAPARTE_PROGRESS_FD' in os.environ:\n"
            "    raise SystemExit(91)\n"
            "target = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
            "pathlib.Path(target).write_text(json.dumps(receipt))\n"
        )
        fake_codex.chmod(0o755)
        read_descriptor, write_descriptor = os.pipe()
        os.set_blocking(write_descriptor, False)
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
    return completed, [json.loads(line) for line in progress_output.splitlines()]


class BonaparteRunnerTests(unittest.TestCase):
    def test_reasoning_defaults_to_medium_and_accepts_a_phase_override(self):
        self.assertEqual(RUNNER.resolve_reasoning(), "medium")
        self.assertEqual(RUNNER.resolve_reasoning("xhigh"), "xhigh")

    def test_model_precedence_is_command_then_global_then_codex(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(RUNNER.resolve_model())

        with mock.patch.dict(
            os.environ, {"BONAPARTE_MODEL": "global-model"}, clear=True
        ):
            self.assertEqual(RUNNER.resolve_model(), "global-model")
            self.assertEqual(
                RUNNER.resolve_model("command-model"), "command-model"
            )

    def test_empty_model_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "non-empty model"):
            RUNNER.resolve_model("  ")

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

    def test_delivery_workflows_accept_a_supplemental_expected_base(self):
        for filename in ("implement.md", "review.md", "publish.md"):
            workflow = (ROOT / "workflows" / filename).read_text()
            with self.subTest(workflow=filename):
                self.assertIn("supplemental input", workflow)

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
        self.assertNotIn("-m", observed["command"])
        self.assertNotIn("resume", observed["command"][:3])

    def test_phase_model_and_reasoning_configure_coordinator_and_children(self):
        observed = {}

        def fake_run(command, **kwargs):
            observed.update(command=command, prompt=kwargs["input"])
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(receipt()))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear", return_value=(linear_issue(), [])),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            RUNNER.run_phase(
                ROOT,
                "rca",
                "COR-1",
                model="gpt-5.6-terra",
                reasoning="high",
            )

        model_index = observed["command"].index("-m")
        self.assertEqual(observed["command"][model_index + 1], "gpt-5.6-terra")
        self.assertIn('model_reasoning_effort="high"', observed["command"])
        agent_overrides = [
            value
            for value in observed["command"]
            if value.startswith("agents.")
        ]
        self.assertEqual(len(agent_overrides), 3)
        for override in agent_overrides:
            self.assertIn('model="gpt-5.6-terra"', override)
            self.assertIn('model_reasoning_effort="high"', override)

    def test_resume_uses_the_same_session_and_can_switch_models(self):
        argv = [
            "bonaparte",
            "--model",
            "gpt-5.6-luna",
            "--reasoning",
            "high",
            "resume",
            "RCA",
            SESSION_ID,
            "Use",
            "production.",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            repository, phase, answer, session_id, model, reasoning = RUNNER.parse()
        self.assertEqual(model, "gpt-5.6-luna")
        self.assertEqual(reasoning, "high")
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
            result = RUNNER.run_phase(
                repository, phase, answer, session_id, model, reasoning
            )

        self.assertEqual(result["state"], "completed")
        self.assertEqual(observed["command"][:3], ["/bin/codex", "exec", "resume"])
        model_index = observed["command"].index("-m")
        self.assertEqual(observed["command"][model_index + 1], "gpt-5.6-luna")
        self.assertIn('model_reasoning_effort="high"', observed["command"])
        self.assertEqual(observed["command"][-2:], [SESSION_ID, "-"])
        self.assertIn("Use production.", observed["prompt"])
        self.assertNotIn("# Bonaparte Bug RCA", observed["prompt"])
        call_linear.assert_not_called()

    def test_non_review_run_phase_retains_baseline_key_only_validation(self):
        schema_invalid = receipt()
        schema_invalid.update(
            phase="scope",
            state="blocked",
            result=None,
            summary=None,
        )

        def fake_run(command, **kwargs):
            receipt_path = Path(command[command.index("--output-last-message") + 1])
            receipt_path.write_text(json.dumps(schema_invalid))
            return subprocess.CompletedProcess(command, 0, stderr="")

        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "run", side_effect=fake_run) as run,
        ):
            result = RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        run.assert_called_once()
        self.assertIsNone(result["summary"])
        self.assertEqual(result["state"], "blocked")

    def test_review_progress_lifecycle_is_bounded_and_terminal(self):
        read_descriptor, write_descriptor = os.pipe()
        os.set_blocking(write_descriptor, False)
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
        os.fstat(2)

        invalid_reader, invalid_writer = os.pipe()
        with mock.patch.dict(
            os.environ,
            {RUNNER.PROGRESS_FD_ENV: f"+{invalid_writer}"},
            clear=False,
        ):
            progress = RUNNER.acquire_progress_reporter(False)
            os.fstat(invalid_writer)
            progress.close()
        os.close(invalid_writer)
        os.close(invalid_reader)

        read_descriptor, write_descriptor = os.pipe()
        with mock.patch.dict(
            os.environ,
            {RUNNER.PROGRESS_FD_ENV: str(write_descriptor)},
            clear=False,
        ):
            progress = RUNNER.acquire_progress_reporter(False)
            self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)
            self.assertIsNone(progress._descriptor)
            with self.assertRaises(OSError):
                os.fstat(write_descriptor)
            progress.close()
        os.close(read_descriptor)

    def test_progress_fd_requires_nonblocking_without_perturbing_host_duplicate(self):
        for blocking in (True, False):
            with self.subTest(blocking=blocking):
                read_descriptor, write_descriptor = os.pipe()
                os.set_blocking(write_descriptor, blocking)
                host_descriptor = os.dup(write_descriptor)
                with mock.patch.dict(
                    os.environ,
                    {RUNNER.PROGRESS_FD_ENV: str(write_descriptor)},
                    clear=False,
                ):
                    progress = RUNNER.acquire_progress_reporter(True)

                self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)
                with self.assertRaises(OSError):
                    os.fstat(write_descriptor)
                self.assertEqual(os.get_blocking(host_descriptor), blocking)
                self.assertEqual(progress._descriptor is not None, not blocking)

                progress.close()
                os.close(host_descriptor)
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

    def test_heartbeat_loop_emits_active_until_stopped(self):
        progress = RUNNER.ProgressReporter(None)
        with (
            mock.patch.object(progress._stop, "wait", side_effect=[False, True]) as wait,
            mock.patch.object(progress, "report") as report,
        ):
            progress._heartbeat_loop()

        self.assertEqual(wait.call_count, 2)
        report.assert_called_once_with("active")

    def test_thread_setup_failures_disable_progress_without_masking_review(self):
        class StartFailure:
            ident = None
            join_called = False

            def start(self):
                raise RuntimeError("thread start unavailable")

            def join(self):
                self.join_called = True

        class InterruptedStart(StartFailure):
            started = None

            def __init__(self, error):
                self.error = error
                self.join_called = False

            def start(self):
                self.started.set()
                raise self.error

        factories = (
            mock.Mock(side_effect=RuntimeError("construction failed")),
            mock.Mock(return_value=StartFailure()),
        )
        for factory in factories:
            with self.subTest(factory=factory):
                read_descriptor, write_descriptor = os.pipe()
                progress = RUNNER.ProgressReporter(write_descriptor)
                with mock.patch.object(
                    RUNNER.threading, "Thread", factory
                ) as thread_factory:
                    progress.start()
                    progress.start()
                thread_factory.assert_called_once()
                self.assertIsNone(progress._descriptor)
                self.assertIsNone(progress._heartbeat)
                progress.stop_heartbeat()
                progress.stop_heartbeat()
                progress.close()
                output = os.read(read_descriptor, 16384)
                os.close(read_descriptor)

                self.assertEqual(
                    [json.loads(line)["state"] for line in output.splitlines()],
                    ["started"],
                )

        for error in (KeyboardInterrupt(), SystemExit(12)):
            with self.subTest(error=type(error).__name__):
                heartbeat = InterruptedStart(error)
                read_descriptor, write_descriptor = os.pipe()
                progress = RUNNER.ProgressReporter(write_descriptor)
                heartbeat.started = progress._heartbeat_running
                with mock.patch.object(
                    RUNNER.threading, "Thread", return_value=heartbeat
                ):
                    with self.assertRaises(type(error)):
                        progress.start()
                progress.close()
                os.close(read_descriptor)
                self.assertTrue(heartbeat.join_called)

    def test_review_process_continues_when_started_heartbeat_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_codex = temporary_path / "codex"
            coordinator_calls = temporary_path / "coordinator-calls"
            heartbeat_joins = temporary_path / "heartbeat-joins"
            fake_receipt = delivery_receipt("review")
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                "    raise SystemExit(0)\n"
                "with pathlib.Path(os.environ['COORDINATOR_CALLS']).open('a') as calls:\n"
                "    calls.write('called\\n')\n"
                f"receipt = {fake_receipt!r}\n"
                "target = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
                "pathlib.Path(target).write_text(json.dumps(receipt))\n"
            )
            fake_codex.chmod(0o755)
            (temporary_path / "sitecustomize.py").write_text(
                "import os, pathlib, threading\n"
                "OriginalThread = threading.Thread\n"
                "class StartRaisesAfterStarting(OriginalThread):\n"
                "    def start(self):\n"
                "        super().start()\n"
                "        if self.name == 'bonaparte-review-progress':\n"
                "            raise RuntimeError('thread start unavailable')\n"
                "    def join(self, *args, **kwargs):\n"
                "        result = super().join(*args, **kwargs)\n"
                "        if self.name == 'bonaparte-review-progress':\n"
                "            with pathlib.Path(os.environ['HEARTBEAT_JOINS']).open('a') as joins:\n"
                "                joins.write('joined\\n')\n"
                "        return result\n"
                "threading.Thread = StartRaisesAfterStarting\n"
            )
            read_descriptor, write_descriptor = os.pipe()
            os.set_blocking(write_descriptor, False)
            environment = {
                **os.environ,
                "CODEX_BIN": str(fake_codex),
                "COORDINATOR_CALLS": str(coordinator_calls),
                "HEARTBEAT_JOINS": str(heartbeat_joins),
                "PYTHONPATH": str(temporary_path),
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

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            expected_receipt = {**fake_receipt, "resume_session_id": None}
            self.assertEqual(
                completed.stdout.splitlines(),
                [json.dumps(expected_receipt, separators=(",", ":"))],
            )
            self.assertEqual(coordinator_calls.read_text().splitlines(), ["called"])
            self.assertEqual(heartbeat_joins.read_text().splitlines(), ["joined"])
            self.assertEqual(
                [json.loads(line)["state"] for line in progress_output.splitlines()],
                ["started"],
            )

    def test_receipt_size_boundary_is_review_only(self):
        baseline_accepted = {"x": "a" * 4088}
        serialized = RUNNER.serialize_receipt(baseline_accepted)
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdout", stdout):
            RUNNER.emit_serialized(serialized)

        raw_output = stdout.getvalue().encode("utf-8")
        self.assertEqual(len(serialized.encode("utf-8")), RUNNER.RECEIPT_MAX_BYTES)
        self.assertEqual(len(raw_output), RUNNER.RECEIPT_MAX_BYTES + 1)
        self.assertTrue(raw_output.endswith(b"\n"))
        self.assertEqual(json.loads(raw_output), baseline_accepted)

        review_accepted = {"x": "a" * 4087}
        review_serialized = RUNNER.serialize_review_receipt(review_accepted)
        self.assertEqual(
            len((review_serialized + "\n").encode("utf-8")),
            RUNNER.RECEIPT_MAX_BYTES,
        )
        with self.assertRaisesRegex(RuntimeError, "receipt exceeded 4 KiB"):
            RUNNER.serialize_review_receipt(baseline_accepted)

    def test_main_uses_review_serializer_only_after_review_is_selected(self):
        cases = (
            (RuntimeError("parse failed"), 1),
            (KeyboardInterrupt(), 130),
        )
        for parse_error, expected_exit in cases:
            with self.subTest(error=type(parse_error).__name__):
                stdout = io.StringIO()
                with (
                    mock.patch.dict(
                        os.environ, {RUNNER.PHASE_CHILD_ENV: ""}, clear=False
                    ),
                    mock.patch.object(RUNNER, "parse", side_effect=parse_error),
                    mock.patch.object(
                        RUNNER,
                        "serialize_receipt",
                        wraps=RUNNER.serialize_receipt,
                    ) as baseline_serializer,
                    mock.patch.object(
                        RUNNER,
                        "serialize_review_receipt",
                        wraps=RUNNER.serialize_review_receipt,
                    ) as review_serializer,
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    exit_code = RUNNER.main()

                self.assertEqual(exit_code, expected_exit)
                baseline_serializer.assert_called_once()
                review_serializer.assert_not_called()
                self.assertEqual(json.loads(stdout.getvalue())["state"], "failed")

        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {RUNNER.PHASE_CHILD_ENV: ""}, clear=False),
            mock.patch.object(
                RUNNER,
                "parse",
                return_value=(ROOT, "review", "Continue.", SESSION_ID, None, "medium"),
            ),
            mock.patch.object(
                RUNNER,
                "acquire_progress_reporter",
                return_value=RUNNER.ProgressReporter(None),
            ),
            mock.patch.object(RUNNER, "run_phase", side_effect=RuntimeError("failed")),
            mock.patch.object(
                RUNNER,
                "serialize_receipt",
                wraps=RUNNER.serialize_receipt,
            ) as baseline_serializer,
            mock.patch.object(
                RUNNER,
                "serialize_review_receipt",
                wraps=RUNNER.serialize_review_receipt,
            ) as review_serializer,
            mock.patch.object(sys, "stdout", stdout),
        ):
            exit_code = RUNNER.main()

        self.assertEqual(exit_code, 1)
        review_serializer.assert_called_once()
        baseline_serializer.assert_not_called()

    def test_review_coordinator_failure_receipt_never_exposes_stderr(self):
        canary = "private-child-detail-canary"
        final_line = "actionable final diagnostic"

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 23, stderr=f"{canary}\n\n{final_line}"
            )

        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {RUNNER.PHASE_CHILD_ENV: ""}, clear=False),
            mock.patch.object(
                RUNNER,
                "parse",
                return_value=(ROOT, "review", "Continue.", SESSION_ID, None, "medium"),
            ),
            mock.patch.object(
                RUNNER,
                "acquire_progress_reporter",
                return_value=RUNNER.ProgressReporter(None),
            ),
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(
                RUNNER.subprocess, "run", side_effect=fake_run
            ) as coordinator,
            mock.patch.object(sys, "stdout", stdout),
        ):
            exit_code = RUNNER.main()

        coordinator.assert_called_once()
        self.assertIs(coordinator.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(exit_code, 1)
        final_receipt = json.loads(stdout.getvalue())
        self.assertEqual(final_receipt["state"], "failed")
        self.assertEqual(
            final_receipt["summary"],
            "review coordinator failed (exit status 23)",
        )
        self.assertNotIn(canary, stdout.getvalue())
        self.assertNotIn(final_line, stdout.getvalue())

    def test_non_review_coordinator_retains_bounded_last_stderr_line(self):
        diagnostic = "x" * 801
        result = subprocess.CompletedProcess(
            [], 1, stderr=f"earlier detail\n\n{diagnostic}"
        )
        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "run", return_value=result) as run,
        ):
            with self.assertRaises(RuntimeError) as raised:
                RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        run.assert_called_once()
        self.assertIs(run.call_args.kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(str(raised.exception), diagnostic[:800])

    def test_review_cli_keeps_stdout_as_one_receipt(self):
        completed, events = run_review_cli(delivery_receipt("review"))
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        stdout_lines = completed.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        self.assertEqual(json.loads(stdout_lines[0])["state"], "completed")
        self.assertLessEqual(len(completed.stdout.encode()), RUNNER.RECEIPT_MAX_BYTES)
        self.assertEqual(
            [event["state"] for event in events],
            ["started", "finalizing", "completed"],
        )

    def test_review_cli_reports_noncompleted_and_rejected_receipts(self):
        needs_input = delivery_receipt("review")
        needs_input.update(
            state="needs-input",
            result="needs-input",
            question="Which environment?",
            branch=None,
            commit=None,
            pull_request_url=None,
        )
        invalid = delivery_receipt("review")
        invalid.update(state="not-a-state", summary="private-invalid-canary")
        oversized = delivery_receipt("review")
        oversized["summary"] = "x" * 5000

        cases = (
            (needs_input, 0, "needs-input", "needs-input"),
            (invalid, 1, "failed", "failed"),
            (oversized, 1, "failed", "failed"),
        )
        for child_receipt, returncode, receipt_state, progress_state in cases:
            with self.subTest(child_state=child_receipt["state"]):
                completed, events = run_review_cli(child_receipt)
                self.assertEqual(completed.returncode, returncode)
                self.assertEqual(json.loads(completed.stdout)["state"], receipt_state)
                self.assertLessEqual(
                    len(completed.stdout.encode()), RUNNER.RECEIPT_MAX_BYTES
                )
                self.assertEqual(
                    [event["state"] for event in events],
                    ["started", "finalizing", progress_state],
                )
                self.assertNotIn("private-invalid-canary", completed.stdout)

    def test_review_cli_rejects_progress_only_terminal_receipt_states(self):
        for state in ("failed", "interrupted"):
            private_canary = f"private-{state}-coordinator-payload"
            invalid = delivery_receipt("review")
            invalid.update(state=state, summary=private_canary)

            with self.subTest(state=state):
                completed, events = run_review_cli(invalid)
                final_receipt = json.loads(completed.stdout)

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(final_receipt["state"], "failed")
                self.assertEqual(
                    [event["state"] for event in events],
                    ["started", "finalizing", "failed"],
                )
                self.assertNotIn(private_canary, completed.stdout)

    def test_review_cli_rejects_receipts_violating_declared_schema(self):
        cases = (
            (
                "summary maxLength",
                "summary",
                lambda canary: canary + "x" * (801 - len(canary)),
            ),
            ("wrong field type", "issue", lambda canary: 42),
            ("invalid null", "summary", lambda canary: None),
            (
                "identifier maxLength",
                "issue",
                lambda canary: canary + "x" * (101 - len(canary)),
            ),
            ("invalid enum", "state", lambda canary: "invalid"),
        )
        for name, field, malformed_value_for in cases:
            private_canary = f"private-{name.replace(' ', '-')}-canary"
            invalid = delivery_receipt("review")
            malformed_value = malformed_value_for(private_canary)
            invalid[field] = malformed_value
            if private_canary not in str(malformed_value):
                invalid["next_action"] = private_canary

            with self.subTest(case=name):
                completed, events = run_review_cli(invalid)
                final_receipt = json.loads(completed.stdout)

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(completed.stdout.count("\n"), 1)
                self.assertEqual(final_receipt["state"], "failed")
                self.assertLessEqual(
                    len(completed.stdout.encode()), RUNNER.RECEIPT_MAX_BYTES
                )
                self.assertEqual(
                    [event["state"] for event in events],
                    ["started", "finalizing", "failed"],
                )
                self.assertNotIn(private_canary, completed.stdout)

    def test_stdout_receipt_is_pipe_readable_before_terminal_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_codex = temporary_path / "codex"
            observed_receipt = temporary_path / "observed-receipt"
            fake_receipt = delivery_receipt("review")
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                "    raise SystemExit(0)\n"
                f"receipt = {fake_receipt!r}\n"
                "target = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
                "pathlib.Path(target).write_text(json.dumps(receipt))\n"
            )
            fake_codex.chmod(0o755)
            (temporary_path / "sitecustomize.py").write_text(
                "import os, pathlib\n"
                "original_write = os.write\n"
                "def observe_order(descriptor, payload):\n"
                "    if b'\"state\":\"completed\"' in payload:\n"
                "        try:\n"
                "            receipt = os.read(int(os.environ['STDOUT_READER']), 4096)\n"
                "        except BlockingIOError:\n"
                "            receipt = b''\n"
                "        pathlib.Path(os.environ['OBSERVED_RECEIPT']).write_bytes(receipt)\n"
                "    return original_write(descriptor, payload)\n"
                "os.write = observe_order\n"
            )
            stdout_reader, stdout_writer = os.pipe()
            progress_reader, progress_writer = os.pipe()
            os.set_blocking(stdout_reader, False)
            os.set_blocking(progress_writer, False)
            environment = {
                **os.environ,
                "CODEX_BIN": str(fake_codex),
                "PYTHONPATH": str(temporary_path),
                "STDOUT_READER": str(stdout_reader),
                "OBSERVED_RECEIPT": str(observed_receipt),
                RUNNER.PROGRESS_FD_ENV: str(progress_writer),
            }
            environment.pop(RUNNER.PHASE_CHILD_ENV, None)
            process = subprocess.Popen(
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
                stdout=stdout_writer,
                stderr=subprocess.PIPE,
                pass_fds=(stdout_reader, progress_writer),
            )
            os.close(stdout_writer)
            os.close(progress_writer)
            _, stderr = process.communicate(timeout=10)
            remaining_stdout = os.read(stdout_reader, 4096)
            os.close(stdout_reader)
            progress_output = os.read(progress_reader, 16384)
            os.close(progress_reader)
            receipt_output = observed_receipt.read_bytes()

        self.assertEqual(process.returncode, 0, stderr.decode())
        self.assertEqual(remaining_stdout, b"")
        self.assertTrue(receipt_output.endswith(b"\n"))
        self.assertEqual(
            json.loads(receipt_output),
            {**fake_receipt, "resume_session_id": None},
        )
        self.assertEqual(
            [json.loads(line)["state"] for line in progress_output.splitlines()],
            ["started", "finalizing", "completed"],
        )

    def test_closed_stdout_reader_suppresses_terminal_progress_on_flush_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake_codex = Path(temporary) / "codex"
            fake_receipt = delivery_receipt("review")
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                "    raise SystemExit(0)\n"
                f"receipt = {fake_receipt!r}\n"
                "target = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
                "pathlib.Path(target).write_text(json.dumps(receipt))\n"
            )
            fake_codex.chmod(0o755)
            stdout_reader, stdout_writer = os.pipe()
            progress_reader, progress_writer = os.pipe()
            os.set_blocking(progress_writer, False)
            os.close(stdout_reader)
            environment = {
                **os.environ,
                "CODEX_BIN": str(fake_codex),
                RUNNER.PROGRESS_FD_ENV: str(progress_writer),
            }
            environment.pop(RUNNER.PHASE_CHILD_ENV, None)
            process = subprocess.Popen(
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
                stdout=stdout_writer,
                stderr=subprocess.PIPE,
                pass_fds=(progress_writer,),
            )
            os.close(stdout_writer)
            os.close(progress_writer)
            _, stderr = process.communicate(timeout=10)
            progress_output = os.read(progress_reader, 16384)
            os.close(progress_reader)

        self.assertNotEqual(process.returncode, 0, stderr.decode())
        self.assertEqual(
            [json.loads(line)["state"] for line in progress_output.splitlines()],
            ["started", "finalizing"],
        )

    def test_sigint_terminal_matches_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake_codex = Path(temporary) / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import os, signal, sys\n"
                "if '--version' in sys.argv:\n"
                "    raise SystemExit(0)\n"
                "os.kill(os.getppid(), signal.SIGINT)\n"
            )
            fake_codex.chmod(0o755)
            read_descriptor, write_descriptor = os.pipe()
            os.set_blocking(write_descriptor, False)
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

        final_receipt = json.loads(completed.stdout)
        progress_states = [
            json.loads(line)["state"] for line in progress_output.splitlines()
        ]
        self.assertEqual(completed.returncode, 130, completed.stderr)
        self.assertEqual(final_receipt["state"], "failed")
        self.assertEqual(final_receipt["summary"], "Bonaparte was interrupted.")
        self.assertEqual(progress_states, ["started", "finalizing", "failed"])
        self.assertEqual(progress_states[-1], final_receipt["state"])

    def test_partial_stdout_failure_is_not_retried_or_reported_terminal(self):
        class TrackingProgress:
            def __init__(self):
                self.states = []
                self.closed = False

            def start(self):
                self.states.append("started")

            def stop_heartbeat(self):
                pass

            def report(self, state):
                self.states.append(state)

            def close(self):
                self.closed = True

        class PartialWriteFailure:
            def __init__(self):
                self.attempts = 0
                self.partial = ""

            def write(self, output):
                self.attempts += 1
                self.partial += output[: max(1, len(output) // 2)]
                raise OSError("stdout failed after partial write")

            def flush(self):
                pass

        progress = TrackingProgress()
        stdout = PartialWriteFailure()
        final_receipt = delivery_receipt("review")
        with (
            mock.patch.dict(
                os.environ, {RUNNER.PHASE_CHILD_ENV: ""}, clear=False
            ),
            mock.patch.object(
                RUNNER,
                "parse",
                return_value=(ROOT, "review", "x", None, None, "medium"),
            ),
            mock.patch.object(
                RUNNER, "acquire_progress_reporter", return_value=progress
            ),
            mock.patch.object(RUNNER, "run_phase", return_value=final_receipt),
            mock.patch.object(sys, "stdout", stdout),
        ):
            with self.assertRaisesRegex(OSError, "stdout failed after partial write"):
                RUNNER.main()

        self.assertEqual(stdout.attempts, 1)
        self.assertTrue(stdout.partial)
        self.assertEqual(progress.states, ["started", "finalizing"])
        self.assertNotIn(final_receipt["state"], progress.states)
        self.assertTrue(progress.closed)
