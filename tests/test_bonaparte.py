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
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "019fd385-da76-77f3-bd3a-2f1e4e49b936"
SUBAGENT_ID = "019ff6ce-cb6d-7fb3-a844-2b022bf2b0af"

# Shapes captured from Codex's native `exec --json` collaboration events.
NATIVE_COLLAB_SPAWN_COMPLETED = {
    "type": "item.completed",
    "item": {
        "id": "item_0",
        "type": "collab_tool_call",
        "tool": "spawn_agent",
        "sender_thread_id": SESSION_ID,
        "receiver_thread_ids": [SUBAGENT_ID],
        "prompt": "private assignment",
        "agents_states": {
            SUBAGENT_ID: {"status": "pending_init", "message": None}
        },
        "status": "completed",
    },
}
NATIVE_COLLAB_WAIT_COMPLETED = {
    "type": "item.completed",
    "item": {
        "id": "item_1",
        "type": "collab_tool_call",
        "tool": "wait",
        "sender_thread_id": SESSION_ID,
        "receiver_thread_ids": [SUBAGENT_ID],
        "agents_states": {
            SUBAGENT_ID: {"status": "completed", "message": None}
        },
        "status": "completed",
    },
}


def load_runner():
    loader = importlib.machinery.SourceFileLoader(
        "bonaparte_runner", str(ROOT / "bonaparte")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RUNNER = load_runner()


def popen_adapter(fake_run):
    """Adapt legacy completed-process fixtures to the incremental Popen boundary."""
    def construct(command, **kwargs):
        process = mock.Mock()
        process.stdout = io.BytesIO()

        class Input(io.BytesIO):
            def close(self):
                events = io.StringIO()
                completed = fake_run(
                    command,
                    **{
                        **kwargs,
                        "input": self.getvalue().decode(),
                        "stdout": events,
                    },
                )
                process.stdout = io.BytesIO(events.getvalue().encode())
                process.returncode = completed.returncode
                stderr = getattr(completed, "stderr", None)
                target = kwargs.get("stderr")
                if stderr and hasattr(target, "write"):
                    target.write(stderr)
                super().close()

        process.stdin = Input()
        process.wait.side_effect = lambda: process.returncode
        return process

    return construct


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
        "remote_state_changed": False,
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
        "remote_state_changed": True,
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
            "BONAPARTE_HOME": str(Path(temporary) / "bonaparte-home"),
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
    def question_checkpoint(self, question="Which environment?"):
        value = receipt("needs-input")
        value["question"] = question
        observation = {
            "session_id": SESSION_ID,
            "activity": "waiting-external",
            "checks_completed": [],
            "checks_completed_total_count": 0,
            "checks_completed_truncated": False,
        }
        return RUNNER.new_question_checkpoint(
            ROOT,
            "rca",
            value,
            SESSION_ID,
            "saved-model",
            "high",
            observation,
            RUNNER.capture_git_state(ROOT),
        )

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
                "### Proof obligations",
                "| File or boundary | Current evidence | Exact responsibility |",
                "| Risk | Evidence and affected boundary | Safeguard |",
                "| Alternative | Evidence | Decision and reason |",
                "| Axis/role | Material conclusion | Evidence |",
            ],
            "implement.md": [
                "### Review contract",
                "### Delivered behavior",
                "| File or boundary | Responsibility delivered |",
                "### Evidence ledger",
                "| Finding | Evidence and consequence | Disposition/fix |",
                "| Role | Material conclusion | Evidence |",
            ],
            "review.md": [
                "### Review basis",
                "### Evidence ledger",
                "| Axis | Result | Evidence | Remaining concern |",
                "| ID | Axis | Material consequence/contract | Evidence |",
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

    def test_verification_ownership_depends_on_changed_boundary(self):
        scope = (ROOT / "workflows/scope.md").read_text()
        implementation = (ROOT / "workflows/implement.md").read_text()
        review = (ROOT / "workflows/review.md").read_text()

        for boundary in (
            "Simple local logic",
            "external/native protocol",
            "process lifecycle",
            "persistence/concurrency",
            "producer-consumer boundary",
        ):
            self.assertIn(boundary, scope)
        self.assertRegex(scope, r"Do not waive it as\s+safe degradation")
        self.assertIn("provisional evidence", implementation)
        self.assertIn("Designate one verification owner", implementation)
        self.assertIn(
            "run the smallest decisive authorized diagnostics", implementation
        )
        self.assertIn("Rebuild the evidence ledger", review)
        self.assertRegex(review, r"run the\s+smallest decisive checks")
        for workflow in (implementation, review):
            self.assertRegex(workflow, r"`pass`, `fail`, or\s+`unverified`")
            self.assertIn("fresh read-only verifier", workflow)
            self.assertIn("unverified", workflow)

    def test_workflows_upgrade_only_the_immediately_preceding_handoff_schema(self):
        scope = (ROOT / "workflows/scope.md").read_text()
        implementation = (ROOT / "workflows/implement.md").read_text()
        review = (ROOT / "workflows/review.md").read_text()

        self.assertIn("immediately preceding legacy schema", scope)
        self.assertRegex(scope, r"lacks\s+`### Proof obligations`")
        self.assertIn("without redesigning the accepted scope", scope)
        for workflow in (implementation, review):
            self.assertIn("immediately preceding legacy schema", workflow)
            self.assertIn("`### Verification`", workflow)
            self.assertRegex(workflow, r"lacks\s+`### Evidence ledger`")
            self.assertRegex(
                workflow, r"evidence candidates, not\s+inherited `pass`"
            )
            self.assertRegex(
                workflow, r"missing ledger\s+alone is not a blocker"
            )
        self.assertIn("without reimplementing", implementation)
        self.assertIn("exact recorded head", review)

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

        self.assertIn("push the final verified\n   head normally", implementation)
        self.assertIn("Create the one draft PR now", implementation)
        self.assertIn("- Draft PR: `[URL]`", implementation)
        self.assertIn("same draft PR", review)
        self.assertIn("- Draft PR: `[URL]`", review)
        self.assertIn(
            "If the exact PR is still draft, mark it ready for review", publish
        )
        self.assertIn("Do not spawn subagents, change code, push commits", publish)

    def test_workflows_route_evidence_and_delegate_proportionally(self):
        create = (ROOT / "workflows/create.md").read_text()
        rca = (ROOT / "workflows/bug-rca.md").read_text()
        scope = (ROOT / "workflows/scope.md").read_text()
        implementation = (ROOT / "workflows/implement.md").read_text()
        review = (ROOT / "workflows/review.md").read_text()
        publish = (ROOT / "workflows/publish.md").read_text()

        self.assertIn("Search once for an obvious duplicate", create)
        self.assertIn("active, nonterminal", create)
        self.assertIn("re-read the selected issue", create)

        self.assertIn("Trace only boundaries implicated by the reported path", rca)
        self.assertIn("subscriptions, leases, tokens, or webhooks", rca)
        self.assertIn("dependency/provider telemetry or status", rca)
        self.assertIn("do not confuse an unattempted query", rca)
        self.assertIn("Static evidence proves susceptibility, not the incident", rca)
        self.assertIn("smallest conclusion-changing diagnostics", rca)
        self.assertIn("Treat an `existing` RCA as a hypothesis", rca)
        self.assertIn("update `existing_comment_id`", rca)
        self.assertIn("All diagnostics and evidence access must be read-only", rca)

        self.assertNotIn("Spawn exactly three", scope)
        self.assertIn("Use zero to three read-only agents", scope)
        self.assertIn("Do not publish an omnibus", scope)
        self.assertIn("trigger, observable outcome, and smallest", scope)

        self.assertNotIn("--allow-empty", implementation)
        self.assertIn(
            "coordinator may implement one narrow coherent packet", implementation
        )
        self.assertIn("do not push every wave", implementation)
        self.assertIn("coordinator alone owns staging", implementation)

        self.assertIn("one canonical range", review)
        self.assertIn("Add zero to three", review)
        self.assertIn("deterministic proving check is sufficient", review)

        self.assertIn("Do not spawn subagents", publish)
        self.assertIn("unexpectedly non-draft", publish)
        self.assertIn("## Completion gate", publish)
        self.assertIn("**Status:** Ready for review", publish)
        self.assertNotIn("**Status:** Ready to merge", publish)

    def test_delivery_workflows_accept_a_supplemental_expected_base(self):
        for filename in ("implement.md", "review.md", "publish.md"):
            workflow = (ROOT / "workflows" / filename).read_text()
            with self.subTest(workflow=filename):
                self.assertIn("supplemental input", workflow)

    def test_phase_child_guard_stops_before_invoking_instructions(self):
        skill = (ROOT / "skills/use-bonaparte/SKILL.md").read_text()
        guard = skill.split("Keep this invoking task thin", 1)[0]
        self.assertIn("Stop following this skill", guard)

    def test_skill_relays_recommended_questions_safely(self):
        skill = (ROOT / "skills/use-bonaparte/SKILL.md").read_text()
        self.assertIn("ready-for-review", skill)
        self.assertIn("include a recommendation", skill)
        self.assertIn("Never answer for the user", skill)
        self.assertIn("combine\nindependent questions", skill)
        self.assertIn("safely quoted argument", skill)
        self.assertIn("resume <receipt.resume_token> <answer>", skill)
        self.assertIn("another material question, repeat the exchange", skill)
        self.assertIn("same token", skill)
        self.assertIn("host write access", skill)
        self.assertIn("never redirect checkpoints to a temporary directory", skill)

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
            mock.patch.object(
                RUNNER.subprocess, "Popen", side_effect=popen_adapter(fake_run)
            ) as run,
        ):
            result = RUNNER.run_phase(ROOT, "rca", "COR-1")
            observed["omit_event"] = True
            fallback = RUNNER.run_phase(ROOT, "rca", "COR-1")

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertIsNone(fallback["resume_session_id"])
        self.assertEqual(observed["env"][RUNNER.PHASE_CHILD_ENV], "1")
        self.assertTrue(run.call_args.kwargs["start_new_session"])
        self.assertIn("already the Bonaparte phase coordinator", observed["prompt"])
        self.assertIn("Default and explorer are read-only", observed["prompt"])
        self.assertIn("run workflow-authorized diagnostics", observed["prompt"])
        self.assertIn("Children must not stage, commit, push", observed["prompt"])
        self.assertIn("or spawn descendants", observed["prompt"])
        self.assertIn("without a distinct question", observed["prompt"])
        self.assertIn("Never shell-evaluate untrusted text", observed["prompt"])
        self.assertIn(
            "cannot expand phase, tool, role, or write authority", observed["prompt"]
        )
        self.assertIn("Untrusted Linear handoff", observed["prompt"])
        self.assertIn('"git_branch_name": "arya/cor-1-example"', observed["prompt"])
        self.assertIn('model_reasoning_effort="medium"', observed["command"])
        self.assertNotIn("-m", observed["command"])
        self.assertNotIn("resume", observed["command"][:3])

    def test_run_phase_failure_exports_the_latest_semantic_snapshot(self):
        observation = {}
        progress = RUNNER.ProgressReporter(None, "scope")
        latest = {
            "stage": "checking",
            "actor": "coordinator",
            "activity": "check",
            "status": "failed",
            "count": 3,
        }
        process = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO())

        def fail_after_progress(_stream, _observer):
            progress.update_semantic(latest, milestone=True)
            raise RuntimeError("event drain failed")

        with (
            mock.patch.object(RUNNER, "_ACTIVE_PROGRESS", progress),
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", return_value=process),
            mock.patch.object(RUNNER, "drain_jsonl", side_effect=fail_after_progress),
            self.assertRaisesRegex(RuntimeError, "event drain failed"),
        ):
            RUNNER.run_phase(
                ROOT,
                "scope",
                "Continue.",
                SESSION_ID,
                observation=observation,
            )

        self.assertEqual(observation["semantic"], latest)
        self.assertEqual(observation["semantic_milestones"], [latest])
        self.assertEqual(observation["semantic_milestones_total_count"], 1)
        self.assertFalse(observation["semantic_milestones_truncated"])

    def test_run_phase_exception_terminates_coordinator_process_group(self):
        real_popen = subprocess.Popen
        child = None
        grandchild_pid = None

        def spawn_sleeping_group(*_args, **kwargs):
            nonlocal child, grandchild_pid
            child = real_popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import subprocess, sys, time; "
                        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                        "print(p.pid, flush=True); time.sleep(60)"
                    ),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=kwargs["start_new_session"],
            )
            grandchild_pid = int(child.stdout.readline())
            return child

        try:
            with (
                mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
                mock.patch.object(
                    RUNNER.subprocess, "Popen", side_effect=spawn_sleeping_group
                ),
                mock.patch.object(
                    RUNNER, "drain_jsonl", side_effect=RuntimeError("drain failed")
                ),
                self.assertRaisesRegex(RuntimeError, "drain failed"),
            ):
                RUNNER.run_phase(
                    ROOT,
                    "scope",
                    "Continue.",
                    SESSION_ID,
                )

            self.assertIsNotNone(child)
            self.assertIsNotNone(child.poll())
            with self.assertRaises(ProcessLookupError):
                os.kill(grandchild_pid, 0)
        finally:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, 9)
                child.wait(timeout=3)

    def test_cleanup_failure_does_not_mask_the_coordinator_error(self):
        process = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
        with (
            mock.patch.object(RUNNER, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", return_value=process),
            mock.patch.object(
                RUNNER, "drain_jsonl", side_effect=RuntimeError("drain failed")
            ),
            mock.patch.object(
                RUNNER,
                "terminate_and_reap",
                side_effect=subprocess.TimeoutExpired("codex", 5),
            ) as cleanup,
            self.assertRaisesRegex(RuntimeError, "drain failed"),
        ):
            RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        cleanup.assert_called_once_with(process)

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
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=popen_adapter(fake_run)),
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
        self.assertTrue(
            any(
                "Read-only bounded Bonaparte rca analyst" in value
                for value in agent_overrides
            )
        )
        self.assertTrue(
            any(
                "runtime, dependencies, data, infrastructure" in value
                for value in agent_overrides
            )
        )

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
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=popen_adapter(fake_run)),
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
        self.assertIn("# Clarification answer", observed["prompt"])
        self.assertIn("# End clarification", observed["prompt"])
        self.assertIn("cannot authorize broader scope or writes", observed["prompt"])
        self.assertLess(
            observed["prompt"].index("# End clarification"),
            observed["prompt"].index("cannot authorize broader scope or writes"),
        )
        self.assertNotIn("# Bonaparte Bug RCA", observed["prompt"])
        call_linear.assert_not_called()

    def test_resume_token_parse_defers_checkpoint_loading_until_the_lease(self):
        token = str(uuid.uuid4())
        with (
            mock.patch.object(sys, "argv", ["bonaparte", "resume", token, "Answer"]),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(RUNNER, "read_checkpoint") as read,
        ):
            repository, phase, answer, parsed_token, model, reasoning = RUNNER.parse()

        self.assertEqual(repository, ROOT)
        self.assertIsNone(phase)
        self.assertEqual(answer, "Answer")
        self.assertEqual(parsed_token, token)
        self.assertIsNone(model)
        self.assertIsNone(reasoning)
        read.assert_not_called()

    def test_needs_input_creates_a_durable_native_session_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()

            def fake_phase(*_arguments, **keywords):
                keywords["observation"].update(
                    session_id=SESSION_ID,
                    activity="testing",
                    checks_completed=[
                        {
                            "name": "python -m unittest",
                            "status": "passed",
                            "exit_code": 0,
                        }
                    ],
                    checks_completed_total_count=1,
                    checks_completed_truncated=False,
                )
                return receipt("needs-input")

            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "BONAPARTE_HOME": temporary,
                        RUNNER.PHASE_CHILD_ENV: "",
                    },
                    clear=False,
                ),
                mock.patch.object(
                    RUNNER,
                    "parse",
                    return_value=(
                        ROOT,
                        "rca",
                        "COR-1",
                        None,
                        "saved-model",
                        "high",
                    ),
                ),
                mock.patch.object(RUNNER, "run_phase", side_effect=fake_phase),
                mock.patch.object(sys, "stdout", stdout),
            ):
                self.assertEqual(RUNNER.main(), 0)
                output = json.loads(stdout.getvalue())
                stored = RUNNER.read_checkpoint(output["resume_token"])

        self.assertEqual(output["state"], "needs-input")
        self.assertEqual(output["resume_session_id"], SESSION_ID)
        self.assertEqual(output["question"], "Which environment?")
        self.assertEqual(output["worktree"], str(ROOT))
        self.assertLessEqual(len(stdout.getvalue().encode()), RUNNER.RECEIPT_MAX_BYTES)
        self.assertEqual(stored["status"], "waiting-input")
        self.assertEqual(stored["token"], SESSION_ID)
        self.assertEqual(stored["model"], "saved-model")
        self.assertEqual(stored["reasoning"], "high")
        self.assertEqual(stored["question"], "Which environment?")
        self.assertIsNone(stored["pending_answer"])
        self.assertEqual(stored["checks_completed_total_count"], 1)

    def test_checkpoint_observation_replaces_only_complete_semantic_snapshots(self):
        stale_semantic = {
            "stage": "coordinating",
            "actor": "coordinator",
            "activity": "lifecycle",
            "status": "started",
            "count": None,
        }
        stale_milestone = {**stale_semantic, "status": "completed"}
        checkpoint = {
            "semantic": stale_semantic,
            "semantic_milestones": [stale_milestone],
            "semantic_milestones_total_count": 1,
            "semantic_milestones_truncated": False,
        }
        latest_semantic = {
            "stage": "checking",
            "actor": "coordinator",
            "activity": "check",
            "status": "failed",
            "count": 41,
        }
        latest_milestones = [
            {**latest_semantic, "status": "completed", "count": 40},
            latest_semantic,
        ]

        RUNNER._update_checkpoint_observation(
            checkpoint,
            {
                "semantic": latest_semantic,
                "semantic_milestones": latest_milestones,
                "semantic_milestones_total_count": 43,
                "semantic_milestones_truncated": True,
            },
        )

        self.assertEqual(checkpoint["semantic"], latest_semantic)
        self.assertEqual(checkpoint["semantic_milestones"], latest_milestones)
        self.assertEqual(checkpoint["semantic_milestones_total_count"], 43)
        self.assertTrue(checkpoint["semantic_milestones_truncated"])
        retained = {
            name: checkpoint[name]
            for name in (
                "semantic",
                "semantic_milestones",
                "semantic_milestones_total_count",
                "semantic_milestones_truncated",
            )
        }

        RUNNER._update_checkpoint_observation(checkpoint, {})

        self.assertEqual(
            {name: checkpoint[name] for name in retained},
            retained,
        )

    def test_token_resume_persists_answer_and_reuses_session_and_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                checkpoint = self.question_checkpoint()
                token = checkpoint["token"]

                def fake_phase(
                    repository,
                    phase,
                    prompt,
                    session_id,
                    model,
                    reasoning,
                    observation,
                    replayed_answer,
                ):
                    durable = RUNNER.read_checkpoint(token, active_only=True)
                    self.assertEqual(durable["pending_answer"], "Production")
                    self.assertEqual(repository, ROOT)
                    self.assertEqual(phase, "rca")
                    self.assertEqual(prompt, "Production")
                    self.assertEqual(session_id, SESSION_ID)
                    self.assertEqual(model, "saved-model")
                    self.assertEqual(reasoning, "high")
                    self.assertFalse(replayed_answer)
                    observation.update(session_id=SESSION_ID)
                    value = receipt("needs-input")
                    value["question"] = "Can you confirm the request ID?"
                    return value

                with (
                    mock.patch.object(
                        RUNNER,
                        "parse",
                        return_value=(
                            ROOT,
                            None,
                            "Production",
                            token,
                            None,
                            None,
                        ),
                    ),
                    mock.patch.object(RUNNER, "run_phase", side_effect=fake_phase),
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    self.assertEqual(RUNNER.main(), 0, stdout.getvalue())
                output = json.loads(stdout.getvalue())
                stored = RUNNER.read_checkpoint(token, active_only=True)

        self.assertEqual(output["resume_token"], token)
        self.assertEqual(output["question"], "Can you confirm the request ID?")
        self.assertEqual(stored["question"], output["question"])
        self.assertIsNone(stored["pending_answer"])

    def test_legacy_resume_routes_through_an_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                self.question_checkpoint()

                def completed(*arguments):
                    durable = RUNNER.read_checkpoint(SESSION_ID, active_only=True)
                    self.assertEqual(durable["pending_answer"], "Production")
                    arguments[-2].update(session_id=SESSION_ID)
                    return receipt("completed")

                with (
                    mock.patch.object(
                        RUNNER,
                        "parse",
                        return_value=(
                            ROOT,
                            "rca",
                            "Production",
                            SESSION_ID,
                            None,
                            None,
                        ),
                    ),
                    mock.patch.object(RUNNER, "run_phase", side_effect=completed) as run,
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    self.assertEqual(RUNNER.main(), 0, stdout.getvalue())
                stored = RUNNER.read_checkpoint(SESSION_ID)

                stdout = io.StringIO()
                with (
                    mock.patch.object(
                        RUNNER,
                        "parse",
                        return_value=(
                            ROOT,
                            "rca",
                            "Production",
                            SESSION_ID,
                            None,
                            None,
                        ),
                    ),
                    mock.patch.object(RUNNER, "run_phase") as reopened,
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    self.assertEqual(RUNNER.main(), 1)

        run.assert_called_once()
        self.assertEqual(stored["status"], "completed")
        reopened.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["state"], "failed")

    def test_ambiguous_resume_failure_preserves_and_replays_the_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                checkpoint = self.question_checkpoint()
                token = checkpoint["token"]

                def failed_phase(*arguments):
                    observation = arguments[-2]
                    durable = RUNNER.read_checkpoint(token, active_only=True)
                    self.assertEqual(durable["pending_answer"], "Production")
                    observation.update(session_id=SESSION_ID)
                    raise RuntimeError("native transport stopped")

                with mock.patch.object(
                    RUNNER, "run_phase", side_effect=failed_phase
                ):
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Production", None, None
                    )
                self.assertEqual(exit_code, 1)
                self.assertEqual(result["resume_token"], token)
                durable = RUNNER.read_checkpoint(token, active_only=True)
                self.assertEqual(durable["pending_answer"], "Production")

                observed = {}

                def completed_phase(*arguments):
                    observed["prompt"] = arguments[2]
                    observed["replayed"] = arguments[-1]
                    arguments[-2].update(session_id=SESSION_ID)
                    return receipt("completed")

                with mock.patch.object(
                    RUNNER, "run_phase", side_effect=completed_phase
                ):
                    final, exit_code = RUNNER.resume_checkpoint(
                        durable, "", None, None
                    )
                stored = RUNNER.read_checkpoint(token)
                with self.assertRaises(RuntimeError):
                    RUNNER.read_checkpoint(token, active_only=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual(final["state"], "completed")
        self.assertEqual(observed["prompt"], "Production")
        self.assertTrue(observed["replayed"])
        self.assertEqual(stored["status"], "completed")

    def test_resume_session_mismatch_does_not_retarget_the_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                checkpoint = self.question_checkpoint()
                token = checkpoint["token"]
                other_session = str(uuid.uuid4())

                def mismatch(*arguments):
                    arguments[-2].update(
                        session_id=other_session,
                    )
                    raise RuntimeError("Codex resumed a different session")

                with mock.patch.object(RUNNER, "run_phase", side_effect=mismatch):
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Production", None, None
                    )
                stored = RUNNER.read_checkpoint(token, active_only=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["resume_token"], token)
        self.assertEqual(stored["token"], SESSION_ID)

    def test_pending_answer_conflict_is_rejected_without_native_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                checkpoint = self.question_checkpoint()
                checkpoint["pending_answer"] = "Production"
                RUNNER.write_checkpoint(checkpoint)
                with mock.patch.object(RUNNER, "run_phase") as run_phase:
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Staging", None, None
                    )
                stored = RUNNER.read_checkpoint(SESSION_ID, active_only=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["resume_token"], SESSION_ID)
        self.assertEqual(stored["pending_answer"], "Production")
        run_phase.assert_not_called()

    def test_terminal_resume_receipt_reports_cumulative_remote_state(self):
        for previous, expected in ((True, True), (None, None)):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as temporary:
                with mock.patch.dict(
                    os.environ, {"BONAPARTE_HOME": temporary}, clear=False
                ):
                    checkpoint = self.question_checkpoint()
                    checkpoint["remote_state_changed"] = previous
                    RUNNER.write_checkpoint(checkpoint)

                    def completed(*arguments):
                        arguments[-2].update(session_id=SESSION_ID)
                        value = receipt("completed")
                        value["remote_state_changed"] = False
                        return value

                    with mock.patch.object(
                        RUNNER, "run_phase", side_effect=completed
                    ):
                        result, exit_code = RUNNER.resume_checkpoint(
                            checkpoint, "Production", None, None
                        )
                    stored = RUNNER.read_checkpoint(SESSION_ID)

                self.assertEqual(exit_code, 0)
                self.assertIs(result["remote_state_changed"], expected)
                self.assertIs(stored["remote_state_changed"], expected)

    def test_resume_rejects_a_different_branch_after_saving_the_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            home = Path(temporary) / "home"
            repository.mkdir()

            def git(*arguments):
                subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Bonaparte Test")
            git("config", "user.email", "bonaparte@example.com")
            (repository / "baseline.txt").write_text("baseline")
            git("add", ".")
            git("commit", "-qm", "baseline")
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": str(home)}, clear=False
            ):
                value = receipt("needs-input")
                checkpoint = RUNNER.new_question_checkpoint(
                    repository,
                    "rca",
                    value,
                    SESSION_ID,
                    None,
                    "medium",
                    {},
                    RUNNER.capture_git_state(repository),
                )
                checkpoint_branch = checkpoint["branch"]
                git("checkout", "-qb", "other")
                with mock.patch.object(RUNNER, "run_phase") as run_phase:
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Production", None, None
                    )
                stored = RUNNER.read_checkpoint(SESSION_ID, active_only=True)

                with mock.patch.object(RUNNER, "run_phase") as second_run:
                    second, second_exit = RUNNER.resume_checkpoint(
                        stored, "", None, None
                    )
                stored_again = RUNNER.read_checkpoint(SESSION_ID, active_only=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["resume_token"], SESSION_ID)
        self.assertEqual(stored["pending_answer"], "Production")
        self.assertFalse(stored["remote_state_changed"])
        self.assertEqual(stored["branch"], checkpoint_branch)
        run_phase.assert_not_called()
        self.assertEqual(second_exit, 1)
        self.assertEqual(second["resume_token"], SESSION_ID)
        self.assertEqual(stored_again["branch"], checkpoint_branch)
        second_run.assert_not_called()

    def test_checkpoint_uses_the_branch_current_when_the_question_is_asked(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            home = Path(temporary) / "home"
            repository.mkdir()

            def git(*arguments):
                subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Bonaparte Test")
            git("config", "user.email", "bonaparte@example.com")
            (repository / "baseline.txt").write_text("baseline")
            git("add", ".")
            git("commit", "-qm", "baseline")
            base = RUNNER.capture_git_state(repository)
            git("checkout", "-qb", "arya/feature")

            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": str(home)}, clear=False
            ):
                checkpoint = RUNNER.new_question_checkpoint(
                    repository,
                    "implement",
                    {
                        **delivery_receipt("implement"),
                        "state": "needs-input",
                        "result": None,
                        "question": "Confirm rollout?",
                    },
                    SESSION_ID,
                    None,
                    "medium",
                    {},
                    base,
                )
                with mock.patch.object(
                    RUNNER,
                    "run_phase",
                    return_value=delivery_receipt("implement"),
                ) as run:
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Production", None, None
                    )

        self.assertEqual(checkpoint["branch"], "arya/feature")
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["state"], "completed")
        run.assert_called_once()

    def test_repeated_question_updates_the_saved_branch_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            home = Path(temporary) / "home"
            repository.mkdir()

            def git(*arguments):
                subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Bonaparte Test")
            git("config", "user.email", "bonaparte@example.com")
            (repository / "baseline.txt").write_text("baseline")
            git("add", ".")
            git("commit", "-qm", "baseline")
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": str(home)}, clear=False
            ):
                checkpoint = RUNNER.new_question_checkpoint(
                    repository,
                    "implement",
                    {
                        **delivery_receipt("implement"),
                        "state": "needs-input",
                        "result": None,
                        "question": "First question?",
                    },
                    SESSION_ID,
                    None,
                    "medium",
                    {},
                    RUNNER.capture_git_state(repository),
                )

                def second_question(*_arguments):
                    git("checkout", "-qb", "arya/feature")
                    value = delivery_receipt("implement")
                    value.update(
                        state="needs-input", result=None, question="Second question?"
                    )
                    return value

                with mock.patch.object(
                    RUNNER, "run_phase", side_effect=second_question
                ):
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "First answer", None, None
                    )
                stored = RUNNER.read_checkpoint(SESSION_ID, active_only=True)

                with mock.patch.object(
                    RUNNER, "run_phase", return_value=delivery_receipt("implement")
                ) as resumed:
                    final, final_exit = RUNNER.resume_checkpoint(
                        stored, "Second answer", None, None
                    )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["question"], "Second question?")
        self.assertEqual(stored["branch"], "arya/feature")
        self.assertEqual(final_exit, 0)
        self.assertEqual(final["state"], "completed")
        resumed.assert_called_once()

    def test_resume_preserves_a_detached_checkpoint_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            home = Path(temporary) / "home"
            repository.mkdir()

            def git(*arguments):
                subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Bonaparte Test")
            git("config", "user.email", "bonaparte@example.com")
            (repository / "baseline.txt").write_text("baseline")
            git("add", ".")
            git("commit", "-qm", "baseline")
            git("checkout", "--detach", "-q")
            base = RUNNER.capture_git_state(repository)

            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": str(home)}, clear=False
            ):
                checkpoint = RUNNER.new_question_checkpoint(
                    repository,
                    "rca",
                    receipt("needs-input"),
                    SESSION_ID,
                    None,
                    "medium",
                    {},
                    base,
                )
                git("checkout", "-qb", "other")
                with mock.patch.object(RUNNER, "run_phase") as run:
                    result, exit_code = RUNNER.resume_checkpoint(
                        checkpoint, "Production", None, None
                    )
                stored = RUNNER.read_checkpoint(SESSION_ID, active_only=True)

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["resume_token"], SESSION_ID)
        self.assertIsNone(stored["branch"])
        run.assert_not_called()

    def test_checkpoint_receipt_is_bounded_without_losing_token_or_question(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                question = "\\" * 500
                checkpoint = self.question_checkpoint(question)
                checkpoint.update(
                    worktree="/" + "w" * 5000,
                    files_changed=[
                        {"path": "p" * 500, "status": "??"} for _ in range(500)
                    ],
                    files_changed_total_count=500,
                    files_changed_truncated=False,
                )
                projected = RUNNER.checkpoint_receipt(checkpoint)
                serialized = RUNNER.serialize_receipt(projected) + "\n"

        self.assertLessEqual(len(serialized.encode()), RUNNER.RECEIPT_MAX_BYTES)
        self.assertEqual(projected["resume_token"], SESSION_ID)
        self.assertEqual(projected["question"], question)

    def test_git_and_event_inventory_cover_committed_dirty_and_failed_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()

            def git(*arguments):
                subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Bonaparte Test")
            git("config", "user.email", "bonaparte@example.com")
            (repository / "baseline.txt").write_text("baseline")
            git("add", ".")
            git("commit", "-qm", "baseline")
            base = RUNNER.capture_git_state(repository)
            (repository / "committed.txt").write_text("committed")
            git("add", ".")
            git("commit", "-qm", "phase change")
            (repository / "dirty.txt").write_text("dirty")
            state = RUNNER.capture_git_state(repository, base["head"])

            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as events:
                events.write(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "python -m unittest",
                                "exit_code": 1,
                            },
                        }
                    )
                    + "\n"
                )
                events.write(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "git checkout -b arya/example",
                                "exit_code": 0,
                            },
                        }
                    )
                    + "\n"
                )
                events.write(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "cargo check",
                                "exit_code": 0,
                            },
                        }
                    )
                    + "\n"
                )
                events.write(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": '/bin/zsh -lc "uv run pytest tests -q"',
                                "exit_code": 0,
                            },
                        }
                    )
                    + "\n"
                )
                observation = RUNNER.observe_events(events)

        self.assertEqual(
            {item["path"] for item in state["files_changed"]},
            {"committed.txt", "dirty.txt"},
        )
        self.assertEqual(observation["checks_completed_total_count"], 3)
        self.assertEqual(observation["checks_completed"][0]["status"], "failed")
        self.assertEqual(observation["checks_completed"][1]["name"], "cargo check")
        self.assertIn("uv run pytest", observation["checks_completed"][2]["name"])

    def test_git_inventory_marks_failed_queries_as_incomplete(self):
        outputs = {
            ("symbolic-ref", "--quiet", "--short", "HEAD"): "main",
            ("rev-parse", "--verify", "HEAD"): "b" * 40,
            ("rev-parse", "--absolute-git-dir"): "/repo/.git",
        }

        def output(_repository, *arguments):
            return outputs.get(arguments)

        with mock.patch.object(RUNNER, "git_output", side_effect=output):
            state = RUNNER.capture_git_state(ROOT, "a" * 40)

        self.assertEqual(state["files_changed"], [])
        self.assertEqual(state["files_changed_total_count"], 0)
        self.assertTrue(state["files_changed_truncated"])

    def test_checkpoint_creation_requires_a_verified_git_identity(self):
        unavailable = {
            "worktree": str(ROOT),
            "git_dir": None,
            "head": None,
            "branch": None,
            "files_changed": [],
            "files_changed_total_count": 0,
            "files_changed_truncated": True,
        }
        with (
            mock.patch.object(RUNNER, "capture_git_state", return_value=unavailable),
            mock.patch.object(RUNNER, "write_checkpoint") as write,
            self.assertRaisesRegex(RuntimeError, "identity is unavailable"),
        ):
            RUNNER.new_question_checkpoint(
                ROOT,
                "rca",
                receipt("needs-input"),
                SESSION_ID,
                None,
                "medium",
                {},
                unavailable,
            )
        write.assert_not_called()

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
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=popen_adapter(fake_run)) as run,
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
                {"version", "sequence", "phase", "state", "elapsed_seconds", "semantic"},
            )
            self.assertEqual(event["version"], 2)
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

    def test_semantic_translation_is_bounded_deduplicated_and_private(self):
        read_descriptor, write_descriptor = os.pipe()
        os.set_blocking(write_descriptor, False)
        progress = RUNNER.ProgressReporter(write_descriptor, "scope")
        observer = RUNNER.EventObserver(progress)
        canary = "private-query-command-path-secret"
        observer.feed(json.dumps({"type": "item.completed", "item": {"type": "web_search", "query": canary}}))
        for _ in range(40):
            observer.feed(json.dumps({"type": "item.completed", "item": {"type": "file_change", "path": canary, "patch": canary}}))
        observer.feed(json.dumps({"type": "agent_message", "message": canary, "reasoning": canary}))
        observer.feed("not json " + canary)
        progress.report("started")
        progress.report("active")
        progress.stop_heartbeat()
        progress.report("finalizing")
        progress.report("completed")
        progress.close()
        payload = os.read(read_descriptor, 65536)
        os.close(read_descriptor)
        events = [json.loads(line) for line in payload.splitlines()]
        self.assertNotIn(canary, payload.decode())
        self.assertTrue(all(event["version"] == 2 and event["phase"] == "scope" for event in events))
        self.assertLessEqual(len(events[1]["semantic"].get("milestones", [])), 32)
        self.assertTrue(all(len(line) + 1 <= RUNNER.PROGRESS_MAX_BYTES for line in payload.splitlines()))

    def test_native_collab_events_emit_assignment_and_completion(self):
        progress = RUNNER.ProgressReporter(None, "implement")
        observer = RUNNER.EventObserver(progress)

        observer.feed(
            json.dumps(
                {
                    **NATIVE_COLLAB_SPAWN_COMPLETED,
                    "type": "item.started",
                    "item": {
                        **NATIVE_COLLAB_SPAWN_COMPLETED["item"],
                        "receiver_thread_ids": [],
                        "agents_states": {},
                        "status": "in_progress",
                    },
                }
            )
        )
        observer.feed(json.dumps(NATIVE_COLLAB_SPAWN_COMPLETED))
        assignment = progress.snapshot()["semantic"]
        observer.feed(
            json.dumps(
                {
                    **NATIVE_COLLAB_WAIT_COMPLETED,
                    "type": "item.started",
                    "item": {
                        **NATIVE_COLLAB_WAIT_COMPLETED["item"],
                        "agents_states": {SUBAGENT_ID: {"status": "running"}},
                        "status": "in_progress",
                    },
                }
            )
        )
        observer.feed(json.dumps(NATIVE_COLLAB_WAIT_COMPLETED))
        completion = progress.snapshot()["semantic"]

        self.assertEqual(
            assignment,
            {
                "stage": "subagent-assignment",
                "actor": "subagent-1",
                "activity": "subagent",
                "status": "completed",
                "count": 1,
            },
        )
        self.assertEqual(
            completion,
            {
                "stage": "subagent-completion",
                "actor": "subagent-1",
                "activity": "subagent",
                "status": "completed",
                "count": 2,
            },
        )
        self.assertNotIn(
            "private assignment", json.dumps(progress.snapshot())
        )

    def test_native_item_status_and_updates_drive_semantics(self):
        progress = RUNNER.ProgressReporter(None, "review")
        observer = RUNNER.EventObserver(progress)
        observer.feed(
            json.dumps(
                {
                    "type": "item.updated",
                    "item": {"type": "web_search", "status": "in_progress"},
                }
            )
        )
        self.assertEqual(progress.snapshot()["semantic"]["status"], "in-progress")

        observer.feed(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "mcp_tool_call", "status": "failed"},
                }
            )
        )
        semantic = progress.snapshot()["semantic"]
        self.assertEqual(semantic["stage"], "tool-use")
        self.assertEqual(semantic["status"], "failed")

        observer.feed(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "status": "declined"},
                }
            )
        )
        self.assertEqual(progress.snapshot()["semantic"]["status"], "failed")

        observer.feed(
            json.dumps(
                {
                    **NATIVE_COLLAB_WAIT_COMPLETED,
                    "item": {
                        **NATIVE_COLLAB_WAIT_COMPLETED["item"],
                        "agents_states": {SUBAGENT_ID: {"status": "running"}},
                        "status": "failed",
                    },
                }
            )
        )
        semantic = progress.snapshot()["semantic"]
        self.assertEqual(semantic["stage"], "subagent-completion")
        self.assertEqual(semantic["status"], "failed")

    def test_subagent_actor_retention_is_capped(self):
        progress = RUNNER.ProgressReporter(None, "rca")
        observer = RUNNER.EventObserver(progress)
        for index in range(RUNNER.PROGRESS_MAX_ACTORS + 5):
            event = {
                **NATIVE_COLLAB_SPAWN_COMPLETED,
                "item": {
                    **NATIVE_COLLAB_SPAWN_COMPLETED["item"],
                    "receiver_thread_ids": [f"agent-{index}"],
                    "agents_states": {f"agent-{index}": {"status": "running"}},
                },
            }
            observer.feed(json.dumps(event))

        self.assertEqual(len(observer._actors), RUNNER.PROGRESS_MAX_ACTORS)
        self.assertEqual(
            progress.snapshot()["semantic"]["actor"],
            f"subagent-{RUNNER.PROGRESS_MAX_ACTORS + 1}",
        )

    def test_incremental_drain_ignores_oversized_and_unterminated_lines(self):
        progress = RUNNER.ProgressReporter(None, "implement")
        observer = RUNNER.EventObserver(progress)
        stream = io.BytesIO(
            (b"x" * (RUNNER.PROGRESS_MAX_LINE_BYTES + 10))
            + b"\nmalformed\n"
            + json.dumps({"type": "thread.started", "thread_id": SESSION_ID}).encode()
        )
        RUNNER.drain_jsonl(stream, observer)
        self.assertEqual(observer.observation["session_id"], SESSION_ID)

    def test_incremental_drain_ignores_non_string_structural_types(self):
        observer = RUNNER.EventObserver(RUNNER.ProgressReporter(None, "implement"))
        records = [
            {"type": ["item.completed"], "item": {"type": "web_search"}},
            {"type": "item.completed", "item": {"type": ["web_search"]}},
            {"type": "thread.started", "thread_id": SESSION_ID},
        ]
        stream = io.BytesIO(
            b"".join(json.dumps(record).encode() + b"\n" for record in records)
        )

        RUNNER.drain_jsonl(stream, observer)

        self.assertEqual(observer.observation["session_id"], SESSION_ID)

    def test_incremental_drain_observes_a_flushed_event_while_child_is_alive(self):
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys, time; "
                    f"print(json.dumps({{'type': 'thread.started', "
                    f"'thread_id': {SESSION_ID!r}}}), flush=True); "
                    "time.sleep(1.5)"
                ),
            ],
            stdout=subprocess.PIPE,
        )
        self.assertIsNotNone(process.stdout)
        started_at = RUNNER.time.monotonic()

        class RecordingObserver(RUNNER.EventObserver):
            first_event_elapsed = None
            child_was_alive = None

            def feed(self, line):
                if self.first_event_elapsed is None:
                    self.first_event_elapsed = RUNNER.time.monotonic() - started_at
                    self.child_was_alive = process.poll() is None
                super().feed(line)

        observer = RecordingObserver(RUNNER.ProgressReporter(None, "review"))
        try:
            RUNNER.drain_jsonl(process.stdout, observer)
            process.stdout.close()
            self.assertEqual(process.wait(timeout=3), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)

        self.assertEqual(observer.observation["session_id"], SESSION_ID)
        self.assertTrue(observer.child_was_alive)
        self.assertLess(observer.first_event_elapsed, 1.5)

    def test_progress_reporter_uses_every_phase(self):
        for phase in RUNNER.WORKFLOWS:
            with self.subTest(phase=phase):
                reader, writer = os.pipe()
                os.set_blocking(writer, False)
                progress = RUNNER.ProgressReporter(writer, phase)
                progress.report("started")
                progress.stop_heartbeat()
                progress.report("finalizing")
                progress.report("completed")
                progress.close()
                events = [json.loads(line) for line in os.read(reader, 16384).splitlines()]
                os.close(reader)
                self.assertEqual([event["phase"] for event in events], [phase] * 3)

    def test_needs_input_progress_is_waiting_not_failed(self):
        reader, writer = os.pipe()
        os.set_blocking(writer, False)
        progress = RUNNER.ProgressReporter(writer, "rca")
        progress.report("started")
        progress.stop_heartbeat()
        progress.report("finalizing")
        progress.report("needs-input")
        progress.close()
        events = [json.loads(line) for line in os.read(reader, 16384).splitlines()]
        os.close(reader)

        self.assertEqual(events[-1]["state"], "needs-input")
        self.assertEqual(
            events[-1]["semantic"],
            {
                "stage": "waiting-input",
                "actor": "coordinator",
                "activity": "lifecycle",
                "status": "waiting",
                "count": None,
            },
        )

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
                "BONAPARTE_HOME": str(temporary_path / "home"),
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

    def test_receipt_size_boundary_includes_the_emitted_newline(self):
        accepted = {"x": "a" * 4087}
        serialized = RUNNER.serialize_receipt(accepted)
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdout", stdout):
            RUNNER.emit_serialized(serialized)

        raw_output = stdout.getvalue().encode("utf-8")
        self.assertEqual(len(raw_output), RUNNER.RECEIPT_MAX_BYTES)
        self.assertTrue(raw_output.endswith(b"\n"))
        self.assertEqual(json.loads(raw_output), accepted)

        oversized = {"x": "a" * 4088}
        self.assertEqual(RUNNER.serialize_review_receipt(accepted), serialized)
        with self.assertRaisesRegex(RuntimeError, "receipt exceeded 4 KiB"):
            RUNNER.serialize_receipt(oversized)
        with self.assertRaisesRegex(RuntimeError, "receipt exceeded 4 KiB"):
            RUNNER.serialize_review_receipt(oversized)

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
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.dict(
                os.environ,
                {RUNNER.PHASE_CHILD_ENV: "", "BONAPARTE_HOME": temporary},
                clear=False,
            ),
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
                RUNNER.subprocess, "Popen", side_effect=popen_adapter(fake_run)
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
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=popen_adapter(lambda command, **kwargs: result)) as run,
        ):
            with self.assertRaises(RuntimeError) as raised:
                RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        run.assert_called_once()
        self.assertTrue(hasattr(run.call_args.kwargs["stderr"], "write"))
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
                "BONAPARTE_HOME": str(temporary_path / "home"),
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
                "BONAPARTE_HOME": str(Path(temporary) / "home"),
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
                "BONAPARTE_HOME": str(Path(temporary) / "home"),
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
