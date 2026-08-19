import importlib.machinery
import importlib.util
import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import bonaparte_native as NATIVE

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "019fd385-da76-77f3-bd3a-2f1e4e49b936"
SUBAGENT_ID = "019ff6ce-cb6d-7fb3-a844-2b022bf2b0af"

# Legacy shapes consumed by EventObserver after app-server notification translation.
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


class AppServerFixture:
    """Deterministic, line-oriented fake for the Codex app-server process."""

    def __init__(self, final_receipt=None, *, session_id=SESSION_ID, handler=None):
        self.final_receipt = final_receipt or receipt()
        self.session_id = session_id
        self.handler = handler
        self.requests = []
        self.process = None

    def __call__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        fixture = self
        output = queue.Queue()

        class Output:
            def __init__(self):
                self.pending = ""

            def __iter__(self):
                return self

            def __next__(self):
                value = output.get(timeout=3)
                if value is None:
                    raise StopIteration
                return value

            def readline(self, size=-1):
                while not self.pending:
                    value = output.get(timeout=3)
                    if value is None:
                        return ""
                    self.pending = value
                if size >= 0 and len(self.pending) > size:
                    value, self.pending = self.pending[:size], self.pending[size:]
                    return value
                value, self.pending = self.pending, ""
                return value

            def close(self):
                return None

        class Input:
            def __init__(self):
                self.buffer = ""
                self.closed = False

            def write(self, value):
                if self.closed:
                    raise ValueError("closed")
                self.buffer += value
                while "\n" in self.buffer:
                    line, self.buffer = self.buffer.split("\n", 1)
                    if line:
                        fixture._handle(json.loads(line), output)
                return len(value)

            def flush(self):
                return None

            def close(self):
                self.closed = True

        process = mock.Mock()
        process.stdin = Input()
        process.stdout = Output()
        process.returncode = None

        def stop():
            if process.returncode is None:
                process.returncode = 0
                output.put(None)

        process.terminate.side_effect = stop
        process.kill.side_effect = stop
        process.wait.side_effect = lambda timeout=None: process.returncode or 0
        process.poll.side_effect = lambda: process.returncode
        self.process = process
        return process

    @staticmethod
    def _emit(output, value):
        output.put(json.dumps(value) + "\n")

    def _handle(self, message, output):
        self.requests.append(message)
        if self.handler and self.handler(self, message, output):
            return
        request_id = message.get("id")
        method = message.get("method")
        if request_id is None:
            return
        if method == "initialize":
            self._emit(output, {"id": request_id, "result": {}})
        elif method in {"thread/start", "thread/resume"}:
            self._emit(
                output,
                {"id": request_id, "result": {"thread": {"id": self.session_id}}},
            )
        elif method == "turn/start":
            self._emit(output, {"id": request_id, "result": {"turn": {"id": "turn-1"}}})
            self._emit(
                output,
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": self.session_id,
                        "turnId": "turn-1",
                        "item": {
                            "id": "item-final",
                            "type": "agentMessage",
                            "text": json.dumps(self.final_receipt),
                            "status": "completed",
                        },
                    },
                },
            )
            self._emit(
                output,
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": self.session_id,
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                },
            )
        elif method == "turn/steer":
            self._emit(output, {"id": request_id, "result": {"turnId": "turn-1"}})


def app_server_script(fake_receipt):
    return (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "if '--version' in sys.argv: raise SystemExit(0)\n"
        f"receipt = {fake_receipt!r}\n"
        "session = " + repr(SESSION_ID) + "\n"
        "for line in sys.stdin:\n"
        " message=json.loads(line); method=message.get('method'); request_id=message.get('id')\n"
        " if request_id is None: continue\n"
        " if method == 'initialize': result={}\n"
        " elif method in ('thread/start','thread/resume'): result={'thread':{'id':session}}\n"
        " elif method == 'turn/start':\n"
        "  result={'turn':{'id':'turn-1'}}\n"
        " else: result={'turnId':'turn-1'}\n"
        " print(json.dumps({'id':request_id,'result':result}), flush=True)\n"
        " if method == 'turn/start':\n"
        "  print(json.dumps({'method':'item/completed','params':{'threadId':session,'turnId':'turn-1','item':{'id':'final','type':'agentMessage','text':json.dumps(receipt),'status':'completed'}}}), flush=True)\n"
        "  print(json.dumps({'method':'turn/completed','params':{'threadId':session,'turn':{'id':'turn-1','status':'completed'}}}), flush=True)\n"
    )


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
        fake_codex.write_text(app_server_script(fake_receipt))
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

    def test_soft_phase_budget_default_custom_and_invalid_never_start_codex(self):
        cases = (
            (["bonaparte", "RCA", "COR-1"], RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS),
            (
                [
                    "bonaparte",
                    "--soft-phase-budget-seconds",
                    "12.5",
                    "RCA",
                    "COR-1",
                ],
                12.5,
            ),
        )
        for argv, expected in cases:
            with (
                self.subTest(argv=argv),
                mock.patch.object(sys, "argv", argv),
                mock.patch.dict(os.environ, {}, clear=True),
            ):
                self.assertEqual(RUNNER.parse()[-1], expected)

        for invalid in ("0", "-1", "nan", "inf", "not-seconds"):
            stdout = io.StringIO()
            with (
                self.subTest(invalid=invalid),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "bonaparte",
                        "--soft-phase-budget-seconds",
                        invalid,
                        "RCA",
                        "COR-1",
                    ],
                ),
                mock.patch.dict(os.environ, {RUNNER.PHASE_CHILD_ENV: ""}, clear=False),
                mock.patch.object(RUNNER.subprocess, "Popen") as popen,
                mock.patch.object(sys, "stdout", stdout),
            ):
                self.assertEqual(RUNNER.main(), 1)
            popen.assert_not_called()
            self.assertIn("positive finite", json.loads(stdout.getvalue())["summary"])

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
                "### Incident",
                "### Causal chain",
                "| Claim | Evidence | What it proves |",
                "| Alternative | Decisive check | Result |",
            ],
            "scope.md": [
                "**Status:** Scoped",
                "### Handoff basis",
                "| File or boundary | Current evidence | Exact responsibility |",
                "### Implementation slices",
                "### Acceptance and proof",
                "| Observable criterion | Boundary | Smallest decisive check | Owner |",
                "### Guardrails",
            ],
            "implement.md": [
                "**Status:** Implemented",
                "### Review contract",
                "| File or boundary | Responsibility delivered |",
                "### Evidence ledger",
                "### Deviations and remaining work",
                "### Git handoff",
            ],
            "review.md": [
                "### Review basis",
                "### Contract and quality result",
                "### Evidence ledger",
                "| ID / axis | Consequence and evidence | Disposition / fix | Re-review |",
                "| Contract fidelity | Pass |",
                "| Engineering quality | Pass |",
                "### Git handoff",
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
                self.assertIn("re-read the comment", workflow)
                for marker in markers:
                    self.assertIn(marker, workflow)

        implementation = (ROOT / "workflows/implement.md").read_text()
        self.assertIn("issue.git_branch_name", implementation)
        self.assertNotIn("bonaparte/<issue-id>", implementation)
        for filename in ("bug-rca.md", "scope.md", "implement.md", "review.md"):
            workflow = (ROOT / "workflows" / filename).read_text()
            current_schema = workflow.split("```markdown", 1)[1].split("```", 1)[0]
            with self.subTest(clean_receipt=filename):
                self.assertNotIn("### Investigation map", current_schema)
                self.assertNotIn("### Debate map", current_schema)
                self.assertNotIn("### Implementation map", current_schema)
                self.assertNotIn("### Review map", current_schema)

        scope = (ROOT / "workflows/scope.md").read_text()
        scope_schema = scope.split("```markdown", 1)[1].split("```", 1)[0]
        self.assertEqual(scope_schema.count("### Handoff basis"), 1)
        self.assertNotIn("Tweed comments", scope)

    def test_verification_ownership_depends_on_changed_boundary(self):
        scope = (ROOT / "workflows/scope.md").read_text()
        implementation = (ROOT / "workflows/implement.md").read_text()
        review = (ROOT / "workflows/review.md").read_text()

        for boundary in (
            "Simple local logic",
            "External/native protocol",
            "Process lifecycle",
            "Persistence/concurrency",
            "Producer-consumer boundary",
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

        self.assertIn("Immediately preceding schema", scope)
        self.assertIn("no current status", scope)
        self.assertIn("without redesigning it", scope)
        self.assertIn("Immediately preceding schema", implementation)
        self.assertIn("evidence candidates", implementation)
        self.assertIn("Immediately preceding schema", review)
        self.assertIn("evidence candidates", review)
        self.assertIn("Never inherit a `pass`", review)
        self.assertIn("`**Status:** Implemented`", implementation)
        self.assertIn("`### Contract and quality result`", review)
        self.assertIn("without reimplementation", implementation)
        self.assertIn("recorded head", review)

    def test_review_can_refresh_a_stale_verdict_for_descendant_corrections(self):
        review = (ROOT / "workflows/review.md").read_text()

        self.assertIn("clean\n  descendant of the recorded reviewed commit", review)
        self.assertIn("review only the added range", review)
        self.assertIn("replace the existing review comment", review)
        self.assertIn("A non-descendant head", review)

    def test_publish_can_reconcile_a_reviewed_descendant_without_duplication(self):
        publish = (ROOT / "workflows/publish.md").read_text()

        self.assertIn("newer complete review for the same open PR and branch", publish)
        self.assertRegex(publish, r"update\s+`existing_comment_id` in place")
        self.assertIn("Never add a duplicate", publish)

    def test_coordinator_owns_a_bounded_coverage_frontier(self):
        runner = (ROOT / "bonaparte").read_text()
        for marker in (
            "Maintain a working coverage map",
            "frontier contains unresolved items",
            "- Fact: investigate it",
            "- Decision: resolve it",
            "- Risk: run a falsifiable check",
            "smallest low-cost check that can change the result",
            "After each material result, update the map",
            "Finish only when the completion gate passes",
            "Publish only durable",
        ):
            self.assertIn(marker, runner)
        self.assertIn("self-contained plain-language question", runner)
        self.assertIn("impact times uncertainty", (ROOT / "workflows/scope.md").read_text())
        self.assertIn("two independent judgments", (ROOT / "workflows/review.md").read_text())

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
        self.assertIn("unattempted query is not unavailable evidence", rca)
        self.assertIn("Static evidence proves susceptibility, not the incident", rca)
        self.assertIn("smallest conclusion-changing diagnostics", rca)
        self.assertRegex(rca, r"Existing RCA: treat it as a hypothesis")
        self.assertIn("update `existing_comment_id`", rca)
        self.assertIn("All diagnostics and evidence access must be read-only", rca)
        self.assertIn("keep one durable RCA slot in Linear", rca)
        self.assertIn("first `Not established` comment", rca)

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
        self.assertIn("options and a recommendation", skill)
        self.assertRegex(skill, r"Never\s+answer for the user")
        self.assertIn("combine independent questions", skill)
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

    def test_resume_token_parse_defers_checkpoint_loading_until_the_lease(self):
        token = str(uuid.uuid4())
        with (
            mock.patch.object(sys, "argv", ["bonaparte", "resume", token, "Answer"]),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(RUNNER, "read_checkpoint") as read,
        ):
            repository, phase, answer, parsed_token, model, reasoning, budget = RUNNER.parse()

        self.assertEqual(repository, ROOT)
        self.assertIsNone(phase)
        self.assertEqual(answer, "Answer")
        self.assertEqual(parsed_token, token)
        self.assertIsNone(model)
        self.assertIsNone(reasoning)
        self.assertIsNone(budget)
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
                            "kind": "test",
                            "status": "passed",
                            "exit": 0,
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
                        RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
                    ),
                ),
                mock.patch.object(RUNNER, "run_phase", side_effect=fake_phase),
                mock.patch.object(sys, "stdout", stdout),
            ):
                self.assertEqual(RUNNER.main(), 0)
                output = json.loads(stdout.getvalue())
                stored = RUNNER.read_checkpoint(output["resume_token"])

        self.assertEqual(output["state"], "needs-input")
        self.assertEqual(output["resume_session_id"], output["phase_token"])
        self.assertEqual(output["question"], "Which environment?")
        self.assertEqual(output["worktree"], str(ROOT))
        self.assertLessEqual(len(stdout.getvalue().encode()), RUNNER.RECEIPT_MAX_BYTES)
        self.assertEqual(stored["status"], "waiting-input")
        self.assertEqual(stored["token"], output["phase_token"])
        self.assertEqual(stored["native_thread_id"], SESSION_ID)
        self.assertEqual(stored["model"], "saved-model")
        self.assertEqual(stored["reasoning"], "high")
        self.assertEqual(stored["question"], "Which environment?")
        self.assertIsNone(stored["pending_answer"])
        self.assertEqual(stored["checks_completed_total_count"], 1)

    def test_fresh_phase_failure_after_session_is_durably_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                def failed_phase(*_arguments, **keywords):
                    keywords["observation"].update(
                        session_id=SESSION_ID, soft_budget_steered=True
                    )
                    raise RuntimeError(
                        "soft-budget guard observed root work after steer acknowledgement"
                    )

                with (
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
                            RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
                        ),
                    ),
                    mock.patch.object(
                        RUNNER, "run_phase", side_effect=failed_phase
                    ),
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    exit_code = RUNNER.main()
                result = json.loads(stdout.getvalue())
                stored = RUNNER.read_checkpoint(result["resume_token"], active_only=True)
                waiting_checkpoint = dict(stored)

                observed = {}

                def completed_phase(*arguments):
                    observed["prompt"] = arguments[2]
                    observed["session_id"] = arguments[3]
                    arguments[-3].update(session_id=SESSION_ID)
                    return receipt("completed")

                with mock.patch.object(
                    RUNNER, "run_phase", side_effect=completed_phase
                ):
                    completed, completed_exit = RUNNER.resume_checkpoint(
                        stored, "Continue", None, None
                    )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["resume_token"], result["phase_token"])
        self.assertEqual(result["question"], RUNNER.SOFT_BUDGET_CONTINUE_QUESTION)
        self.assertIsNone(result["remote_state_changed"])
        self.assertEqual(waiting_checkpoint["status"], "failed-resumable")
        self.assertIsNone(waiting_checkpoint["pending_answer"])
        self.assertEqual(observed["prompt"], "Continue")
        self.assertEqual(observed["session_id"], SESSION_ID)
        self.assertEqual(completed_exit, 0)
        self.assertEqual(completed["state"], "completed")

    def test_every_failure_is_recorded_before_returning(self):
        other_session = str(uuid.uuid4())
        cases = (
            ("initialize", None, {}, "timed out during initialize"),
            (
                "turn start",
                None,
                {"session_id": SESSION_ID},
                "timed out during turn/start",
            ),
            (
                "legacy mismatch",
                SESSION_ID,
                {"session_id": other_session},
                "Codex resumed a different session",
            ),
        )
        for label, requested_session, observed, message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                def failed_phase(*_arguments, **keywords):
                    keywords["observation"].update(observed)
                    raise RuntimeError(message)

                with (
                    mock.patch.dict(
                        os.environ, {"BONAPARTE_HOME": temporary}, clear=False
                    ),
                    mock.patch.object(RUNNER, "run_phase", side_effect=failed_phase),
                ):
                    result, exit_code = RUNNER.run_and_checkpoint(
                        ROOT,
                        "rca",
                        "COR-1",
                        requested_session,
                        None,
                        "medium",
                    )

                self.assertEqual(exit_code, 1)
                self.assertEqual(result["state"], "blocked")
                records = list(Path(temporary).rglob("*.json"))
                self.assertEqual(len(records), 1)
                self.assertEqual(json.loads(records[0].read_text())["status"], "failed-resumable")

    def test_soft_budget_interruption_after_session_is_durably_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            def interrupted_phase(*_arguments, **keywords):
                keywords["observation"].update(
                    session_id=SESSION_ID, soft_budget_steered=True
                )
                raise KeyboardInterrupt

            with (
                mock.patch.dict(
                    os.environ, {"BONAPARTE_HOME": temporary}, clear=False
                ),
                mock.patch.object(
                    RUNNER, "run_phase", side_effect=interrupted_phase
                ),
            ):
                result, exit_code = RUNNER.run_and_checkpoint(
                    ROOT,
                    "rca",
                    "COR-1",
                    None,
                    None,
                    "medium",
                )
                stored = RUNNER.read_checkpoint(result["resume_token"], active_only=True)

        self.assertEqual(exit_code, 130)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["resume_token"], result["phase_token"])
        self.assertEqual(result["summary"], "Bonaparte was interrupted.")
        self.assertEqual(stored["status"], "failed-resumable")

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
                self.assertEqual(
                    checkpoint["soft_phase_budget_seconds"],
                    RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
                )

                def fake_phase(
                    repository,
                    phase,
                    prompt,
                    session_id,
                    model,
                    reasoning,
                    observation,
                    replayed_answer,
                    soft_phase_budget_seconds,
                ):
                    durable = RUNNER.read_checkpoint(token)
                    self.assertEqual(durable["pending_answer"], "Production")
                    self.assertEqual(repository, ROOT)
                    self.assertEqual(phase, "rca")
                    self.assertEqual(prompt, "Production")
                    self.assertEqual(session_id, SESSION_ID)
                    self.assertEqual(model, "saved-model")
                    self.assertEqual(reasoning, "high")
                    self.assertFalse(replayed_answer)
                    self.assertEqual(
                        soft_phase_budget_seconds,
                        17.25,
                    )
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
                            17.25,
                        ),
                    ),
                    mock.patch.object(
                        RUNNER, "inspect_checkpoint", return_value={"safe_to_resume": True}
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
        self.assertEqual(stored["soft_phase_budget_seconds"], 17.25)

    def test_legacy_resume_routes_through_an_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                self.question_checkpoint()

                def completed(*arguments):
                    durable = RUNNER.read_checkpoint(SESSION_ID)
                    self.assertEqual(durable["pending_answer"], "Production")
                    self.assertEqual(
                        arguments[-1], RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS
                    )
                    arguments[-3].update(session_id=SESSION_ID)
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
                            None,
                        ),
                    ),
                    mock.patch.object(
                        RUNNER, "inspect_checkpoint", return_value={"safe_to_resume": True}
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
                            None,
                        ),
                    ),
                    mock.patch.object(RUNNER, "run_phase") as reopened,
                    mock.patch.object(sys, "stdout", stdout),
                ):
                    self.assertEqual(RUNNER.main(), 0)

        run.assert_called_once()
        self.assertEqual(stored["status"], "completed")
        reopened.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["state"], "completed")

    def test_ambiguous_resume_failure_preserves_and_replays_the_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ, {"BONAPARTE_HOME": temporary}, clear=False
            ):
                checkpoint = self.question_checkpoint()
                token = checkpoint["token"]

                def failed_phase(*arguments):
                    observation = arguments[-3]
                    durable = RUNNER.read_checkpoint(token)
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
                    observed["replayed"] = arguments[-2]
                    arguments[-3].update(session_id=SESSION_ID)
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
                    arguments[-3].update(
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
                checkpoint["pending_answer_state"] = "pending"
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
                        arguments[-3].update(session_id=SESSION_ID)
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

            observer = RUNNER.EventObserver()
            for command, exit_code in (
                ("python -m unittest", 1),
                ("git checkout -b arya/example", 0),
                ("cargo check", 0),
                ('/bin/zsh -lc "uv run pytest tests -q"', 0),
            ):
                observer.feed(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": command,
                                "exit_code": exit_code,
                            },
                        }
                    )
                )
            observation = observer.finish()

        self.assertEqual(
            {item["path"] for item in state["files_changed"]},
            {"committed.txt", "dirty.txt"},
        )
        self.assertEqual(observation["checks_completed_total_count"], 3)
        self.assertEqual(observation["checks_completed"][0]["status"], "failed")
        self.assertEqual(observation["checks_completed"][1]["kind"], "check")
        self.assertEqual(observation["checks_completed"][2]["kind"], "test")

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

    def test_non_review_run_phase_enforces_the_declared_schema(self):
        schema_invalid = receipt()
        schema_invalid.update(
            phase="scope",
            state="blocked",
            result=None,
            summary=None,
        )

        server = AppServerFixture(schema_invalid)

        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server) as run,
            self.assertRaisesRegex(RuntimeError, "invalid receipt"),
        ):
            RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        run.assert_called_once()

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
        with self.assertRaisesRegex(RuntimeError, "receipt exceeded 4 KiB"):
            RUNNER.serialize_receipt(oversized)

    def test_review_coordinator_failure_receipt_never_exposes_stderr(self):
        canary = "private-child-detail-canary"
        process = mock.Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO()
        process.returncode = 23
        process.poll.return_value = 23

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
                return_value=(ROOT, "review", "Continue.", SESSION_ID, None, "medium", None),
            ),
            mock.patch.object(
                RUNNER,
                "acquire_progress_reporter",
                return_value=RUNNER.ProgressReporter(None),
            ),
            mock.patch.object(
                RUNNER, "inspect_checkpoint", return_value={"safe_to_resume": True}
            ),
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", return_value=process) as coordinator,
            mock.patch.object(sys, "stdout", stdout),
        ):
            exit_code = RUNNER.main()

        self.assertEqual(exit_code, 1)
        final_receipt = json.loads(stdout.getvalue())
        self.assertIn(final_receipt["state"], {"blocked", "failed"})
        self.assertTrue(final_receipt["summary"])
        self.assertNotIn(canary, stdout.getvalue())

    def test_app_server_eof_is_reported_and_process_is_cleaned_up(self):
        process = mock.Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO()
        process.returncode = 1
        process.poll.return_value = 1
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", return_value=process) as run,
            mock.patch.object(NATIVE, "terminate_and_reap") as cleanup,
        ):
            with self.assertRaisesRegex(RuntimeError, "app-server stopped"):
                RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        run.assert_called_once()
        self.assertIs(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        cleanup.assert_called_once_with(process)

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
            (invalid, 1, "blocked", "blocked"),
            (oversized, 1, "blocked", "blocked"),
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
                self.assertEqual(final_receipt["state"], "blocked")
                self.assertEqual(
                    [event["state"] for event in events],
                    ["started", "finalizing", "blocked"],
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
                self.assertEqual(final_receipt["state"], "blocked")
                self.assertLessEqual(
                    len(completed.stdout.encode()), RUNNER.RECEIPT_MAX_BYTES
                )
                self.assertEqual(
                    [event["state"] for event in events],
                    ["started", "finalizing", "blocked"],
                )
                self.assertNotIn(private_canary, completed.stdout)

    def test_stdout_receipt_is_pipe_readable_before_terminal_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_codex = temporary_path / "codex"
            observed_receipt = temporary_path / "observed-receipt"
            fake_receipt = delivery_receipt("review")
            fake_codex.write_text(app_server_script(fake_receipt))
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
        emitted = json.loads(receipt_output)
        self.assertEqual(emitted["state"], "completed")
        self.assertEqual(emitted["receipt_protocol"], 2)
        self.assertEqual(emitted["progress_abi"], 3)
        self.assertEqual(emitted["resume_session_id"], None)
        self.assertEqual(
            [json.loads(line)["state"] for line in progress_output.splitlines()],
            ["started", "finalizing", "completed"],
        )

    def test_closed_stdout_reader_suppresses_terminal_progress_on_flush_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake_codex = Path(temporary) / "codex"
            fake_receipt = delivery_receipt("review")
            fake_codex.write_text(app_server_script(fake_receipt))
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
        self.assertEqual(final_receipt["state"], "blocked")
        self.assertEqual(final_receipt["summary"], "Bonaparte was interrupted.")
        self.assertEqual(progress_states, ["started", "finalizing", "blocked"])
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
                return_value=(
                    ROOT,
                    "review",
                    "x",
                    None,
                    None,
                    "medium",
                    RUNNER.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
                ),
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
