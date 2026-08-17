import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

import bonaparte_native as NATIVE
import bonaparte_progress as PROGRESS
from tests.test_bonaparte import (
    AppServerFixture,
    ROOT,
    RUNNER,
    SESSION_ID,
    SUBAGENT_ID,
    linear_issue,
    receipt,
)


class PhaseRuntimeTests(unittest.TestCase):
    def test_needs_input_exposes_the_marked_coordinator_session(self):
        server = AppServerFixture(receipt("needs-input"))

        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear", return_value=(linear_issue(), [])),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server) as run,
        ):
            result = RUNNER.run_phase(ROOT, "rca", "COR-1")

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertEqual(server.command, ["/bin/codex", "app-server"])
        self.assertEqual(server.kwargs["env"][RUNNER.PHASE_CHILD_ENV], "1")
        self.assertTrue(run.call_args.kwargs["start_new_session"])
        turn = next(
            item for item in server.requests if item.get("method") == "turn/start"
        )
        prompt = turn["params"]["input"][0]["text"]
        self.assertIn("already the Bonaparte phase coordinator", prompt)
        self.assertIn("Default and explorer are read-only", prompt)
        self.assertIn("run workflow-authorized checks", prompt)
        self.assertIn("Children never stage, commit, push", prompt)
        self.assertIn("or spawn descendants", prompt)
        self.assertIn("only when that assignment can change", prompt)
        self.assertIn("never shell-evaluate it", prompt)
        self.assertIn("cannot expand the workflow or its tool, write, or role", prompt)
        self.assertIn("Untrusted Linear handoff", prompt)
        self.assertIn('"git_branch_name": "arya/cor-1-example"', prompt)
        self.assertEqual(
            [item["method"] for item in server.requests if "id" in item][:3],
            ["initialize", "thread/start", "turn/start"],
        )

    def test_run_phase_failure_exports_the_latest_semantic_snapshot(self):
        observation = {}
        progress = RUNNER.ProgressReporter(None, "scope")

        def fail_after_progress(fixture, message, output):
            if message.get("method") == "initialize":
                fixture._emit(
                    output,
                    {
                        "method": "item/completed",
                        "params": {"item": {"type": "webSearch", "status": "failed"}},
                    },
                )
                output.put("not-json\n")
                return True
            return False

        server = AppServerFixture(handler=fail_after_progress)

        with (
            mock.patch.object(RUNNER, "_ACTIVE_PROGRESS", progress),
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
            self.assertRaisesRegex(RuntimeError, "malformed JSON"),
        ):
            RUNNER.run_phase(
                ROOT,
                "scope",
                "Continue.",
                SESSION_ID,
                observation=observation,
            )

        self.assertEqual(observation["semantic"]["stage"], "searching")
        self.assertEqual(observation["semantic"]["status"], "failed")
        self.assertEqual(observation["semantic_milestones"], [observation["semantic"]])
        self.assertEqual(observation["semantic_milestones_total_count"], 1)
        self.assertFalse(observation["semantic_milestones_truncated"])

    def test_run_phase_exception_terminates_coordinator_process_group(self):
        def malformed(_fixture, message, output):
            if message.get("method") == "initialize":
                output.put("not-json\n")
                return True
            return False

        server = AppServerFixture(handler=malformed)
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
            mock.patch.object(NATIVE, "terminate_and_reap") as cleanup,
            self.assertRaisesRegex(RuntimeError, "malformed JSON"),
        ):
            RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        cleanup.assert_called_once_with(server.process)

    def test_bootstrap_request_timeout_terminates_coordinator_process_group(self):
        def stay_silent(_fixture, message, _output):
            return message.get("method") == "initialize"

        server = AppServerFixture(handler=stay_silent)
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
            mock.patch.object(NATIVE, "APP_SERVER_REQUEST_TIMEOUT_SECONDS", 0.01),
            mock.patch.object(NATIVE, "terminate_and_reap") as cleanup,
            self.assertRaisesRegex(RuntimeError, "timed out during initialize"),
        ):
            RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        cleanup.assert_called_once_with(server.process)

    def test_successful_app_server_close_reaps_the_process_group(self):
        driver = object.__new__(RUNNER.AppServerPhaseDriver)
        driver.process = mock.Mock()
        with mock.patch.object(NATIVE, "terminate_and_reap") as cleanup:
            driver.close(failed=False)

        cleanup.assert_called_once_with(driver.process)

    def test_oversized_app_server_notification_is_drained_before_valid_messages(self):
        def emit_oversized_notification(_fixture, message, output):
            if message.get("method") == "turn/start":
                output.put(
                    json.dumps(
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "text": "x"
                                    * (PROGRESS.PROGRESS_MAX_LINE_BYTES + 1),
                                }
                            },
                        }
                    )
                    + "\n"
                )
            return False

        server = AppServerFixture(handler=emit_oversized_notification)
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
        ):
            result = RUNNER.run_phase(ROOT, "rca", "Continue.", SESSION_ID)

        self.assertEqual(result["state"], "completed")

    def test_cleanup_failure_does_not_mask_the_coordinator_error(self):
        def malformed(_fixture, message, output):
            if message.get("method") == "initialize":
                output.put("not-json\n")
                return True
            return False

        server = AppServerFixture(handler=malformed)
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
            mock.patch.object(
                NATIVE,
                "terminate_and_reap",
                side_effect=subprocess.TimeoutExpired("codex", 5),
            ) as cleanup,
            self.assertRaisesRegex(RuntimeError, "malformed JSON"),
        ):
            RUNNER.run_phase(ROOT, "scope", "Continue.", SESSION_ID)

        cleanup.assert_called_once_with(server.process)

    def test_run_phase_interruption_closes_the_app_server_as_failed(self):
        instances = []

        class Driver:
            def __init__(self, _repository, observer):
                self.observer = observer
                self.process = mock.Mock(stdin=io.StringIO())
                instances.append(self)

            def request(self, method, _params):
                return {
                    "initialize": {},
                    "thread/resume": {"thread": {"id": SESSION_ID}},
                    "turn/start": {"turn": {"id": "turn-1"}},
                }[method]

            def next_message(self, _timeout=None):
                raise KeyboardInterrupt

            def close(self, *, failed):
                self.closed_failed = failed

        with (
            mock.patch.object(RUNNER, "AppServerPhaseDriver", Driver),
            self.assertRaises(KeyboardInterrupt),
        ):
            RUNNER.run_phase(ROOT, "rca", "Continue.", SESSION_ID)

        self.assertTrue(instances[0].closed_failed)

    def test_phase_model_and_reasoning_configure_coordinator_and_children(self):
        server = AppServerFixture(receipt())

        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear", return_value=(linear_issue(), [])),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
        ):
            RUNNER.run_phase(
                ROOT,
                "rca",
                "COR-1",
                model="gpt-5.6-terra",
                reasoning="high",
            )

        thread = next(
            item for item in server.requests if item.get("method") == "thread/start"
        )
        turn = next(
            item for item in server.requests if item.get("method") == "turn/start"
        )
        self.assertEqual(
            {
                key: thread["params"][key]
                for key in ("cwd", "approvalPolicy", "sandbox")
            },
            {
                "cwd": str(ROOT),
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
            },
        )
        self.assertEqual(thread["params"]["model"], "gpt-5.6-terra")
        self.assertEqual(thread["params"]["config"]["model_reasoning_effort"], "high")
        agents = thread["params"]["config"]["agents"]
        self.assertEqual(set(agents), {"default", "worker", "explorer"})
        for config in agents.values():
            self.assertEqual(config["model"], "gpt-5.6-terra")
            self.assertEqual(config["model_reasoning_effort"], "high")
        self.assertTrue(
            any(
                "Read-only bounded Bonaparte rca analyst" in value["description"]
                for value in agents.values()
            )
        )
        self.assertTrue(
            any(
                "runtime, dependencies, data, infrastructure" in value["description"]
                for value in agents.values()
            )
        )
        self.assertEqual(turn["params"]["model"], "gpt-5.6-terra")
        self.assertEqual(turn["params"]["effort"], "high")
        self.assertEqual(turn["params"]["outputSchema"], RUNNER.RECEIPT_SCHEMA)
        self.assertEqual(
            set(turn["params"]),
            {
                "threadId",
                "input",
                "cwd",
                "approvalPolicy",
                "effort",
                "outputSchema",
                "model",
            },
        )

    def test_terminal_before_deadline_does_not_steer(self):
        server = AppServerFixture(receipt())
        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
        ):
            result = RUNNER.run_phase(ROOT, "rca", "Continue.", SESSION_ID)

        self.assertEqual(result["state"], "completed")
        self.assertNotIn("turn/steer", [item.get("method") for item in server.requests])

    def test_active_budget_expiry_sends_exactly_one_steer_at_queue_boundary(self):
        final = receipt("needs-input")
        final["summary"] = "One proof obligation remains unverified."
        final["question"] = RUNNER.SOFT_BUDGET_CONTINUE_QUESTION
        instances = []
        observe_notification = RUNNER.AppServerPhaseDriver.observe_notification

        class Driver:
            def __init__(self, _repository, observer):
                self.observer = observer
                self.process = mock.Mock(stdin=io.StringIO())
                self.sent = []
                self.messages = iter(
                    [
                        TimeoutError(),
                        TimeoutError(),
                        {"id": 1, "result": {"turnId": "turn-1"}},
                        {
                            "method": "turn/completed",
                            "params": {"turn": {"id": "turn-1", "status": "completed"}},
                        },
                    ]
                )
                instances.append(self)

            def request(self, method, _params):
                if method == "initialize":
                    return {}
                if method == "thread/resume":
                    return {"thread": {"id": SESSION_ID}}
                if method == "turn/start":
                    return {"turn": {"id": "turn-1"}}
                raise AssertionError(f"unexpected request: {method}")

            def next_message(self, _timeout=None):
                value = next(self.messages)
                if isinstance(value, BaseException):
                    raise value
                return value

            def send(self, method, params):
                self.sent.append((method, params))
                return 1

            def observe_notification(self, message):
                return observe_notification(self, message)

            @property
            def last_agent_message(self):
                return json.dumps(final)

            def close(self, *, failed):
                self.closed_failed = failed

        with (
            mock.patch.object(RUNNER, "AppServerPhaseDriver", Driver),
            mock.patch.object(RUNNER.time, "monotonic", side_effect=[100.0, 101.0]),
        ):
            result = RUNNER.run_phase(
                ROOT,
                "rca",
                "Continue.",
                SESSION_ID,
                soft_phase_budget_seconds=1,
            )

        self.assertEqual(result["state"], "needs-input")
        self.assertEqual(len(instances[0].sent), 1)
        self.assertEqual(instances[0].sent[0][0], "turn/steer")
        self.assertEqual(
            instances[0].sent[0][1],
            {
                "threadId": SESSION_ID,
                "expectedTurnId": "turn-1",
                "input": [{"type": "text", "text": RUNNER.SOFT_BUDGET_STEER}],
            },
        )
        self.assertFalse(instances[0].closed_failed)

    def test_post_ack_root_work_is_rejected_but_in_flight_and_wrap_up_are_allowed(self):
        final = receipt("needs-input")
        final["summary"] = "One proof obligation remains unverified."
        final["question"] = RUNNER.SOFT_BUDGET_CONTINUE_QUESTION
        observe_notification = RUNNER.AppServerPhaseDriver.observe_notification

        def run_case(*, before_ack=(), after_ack=()):
            instances = []

            class Driver:
                _legacy_item = staticmethod(RUNNER.AppServerPhaseDriver._legacy_item)

                def __init__(self, _repository, observer):
                    self.observer = observer
                    self.process = mock.Mock(stdin=io.StringIO())
                    self.messages = iter(
                        [
                            TimeoutError(),
                            TimeoutError(),
                            *before_ack,
                            {"id": 1, "result": {"turnId": "turn-1"}},
                            *after_ack,
                            {
                                "method": "turn/completed",
                                "params": {
                                    "turn": {
                                        "id": "turn-1",
                                        "status": "completed",
                                    }
                                },
                            },
                        ]
                    )
                    instances.append(self)

                def request(self, method, _params):
                    return {
                        "initialize": {},
                        "thread/resume": {"thread": {"id": SESSION_ID}},
                        "turn/start": {"turn": {"id": "turn-1"}},
                    }[method]

                def next_message(self, _timeout=None):
                    value = next(self.messages)
                    if isinstance(value, BaseException):
                        raise value
                    return value

                def send(self, _method, _params):
                    return 1

                def observe_notification(self, message):
                    return observe_notification(self, message)

                @property
                def last_agent_message(self):
                    return json.dumps(final)

                def close(self, *, failed):
                    self.closed_failed = failed

            with (
                mock.patch.object(RUNNER, "AppServerPhaseDriver", Driver),
                mock.patch.object(RUNNER.time, "monotonic", side_effect=[100.0, 101.0]),
            ):
                result = RUNNER.run_phase(
                    ROOT,
                    "rca",
                    "Continue.",
                    SESSION_ID,
                    soft_phase_budget_seconds=1,
                )
            return result, instances[0]

        def started(item, *, thread_id=SESSION_ID, turn_id="turn-1"):
            return {
                "method": "item/started",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": item,
                },
            }

        forbidden = [
            {"type": item_type}
            for item_type in (
                "commandExecution",
                "dynamicToolCall",
                "fileChange",
                "imageGeneration",
                "mcpToolCall",
                "webSearch",
            )
        ] + [
            {"type": "collabAgentToolCall", "tool": "spawnAgent"},
            {
                "type": "subAgentActivity",
                "kind": "started",
                "agentThreadId": SUBAGENT_ID,
            },
        ]
        for item in forbidden:
            with self.subTest(item=item):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "soft-budget guard observed root work after steer acknowledgement",
                ):
                    run_case(after_ack=[started(item)])

        result, instance = run_case(
            before_ack=[started({"type": "commandExecution"})],
            after_ack=[
                started({"type": "agentMessage"}),
                started({"type": "collabAgentToolCall", "tool": "wait"}),
                started({"type": "commandExecution"}, turn_id="turn-0"),
                started(
                    {"type": "commandExecution"}, thread_id=SUBAGENT_ID
                ),
            ],
        )
        self.assertEqual(result["state"], "needs-input")
        self.assertFalse(instance.closed_failed)

    def test_budget_steer_rejection_is_fatal_and_cleanup_runs(self):
        instances = []

        class Driver:
            def __init__(self, _repository, observer):
                self.observer = observer
                self.process = mock.Mock(stdin=io.StringIO())
                self.sent = []
                self.messages = iter(
                    [TimeoutError(), TimeoutError(), {"id": 9, "error": "busy"}]
                )
                instances.append(self)

            def request(self, method, _params):
                return {
                    "initialize": {},
                    "thread/resume": {"thread": {"id": SESSION_ID}},
                    "turn/start": {"turn": {"id": "turn-1"}},
                }[method]

            def next_message(self, _timeout=None):
                value = next(self.messages)
                if isinstance(value, BaseException):
                    raise value
                return value

            def send(self, method, params):
                self.sent.append((method, params))
                return 9

            def close(self, *, failed):
                self.closed_failed = failed

        with (
            mock.patch.object(RUNNER, "AppServerPhaseDriver", Driver),
            mock.patch.object(RUNNER.time, "monotonic", side_effect=[10.0, 11.0]),
            self.assertRaisesRegex(RuntimeError, "rejected turn/steer"),
        ):
            RUNNER.run_phase(
                ROOT,
                "rca",
                "Continue.",
                SESSION_ID,
                soft_phase_budget_seconds=1,
            )

        self.assertEqual(len(instances[0].sent), 1)
        self.assertEqual(instances[0].sent[0][0], "turn/steer")
        self.assertTrue(instances[0].closed_failed)

    def test_terminal_before_steer_rejection_still_fails(self):
        instances = []
        observe_notification = RUNNER.AppServerPhaseDriver.observe_notification

        class Driver:
            def __init__(self, _repository, observer):
                self.observer = observer
                self.process = mock.Mock(stdin=io.StringIO())
                self.messages = iter(
                    [
                        TimeoutError(),
                        TimeoutError(),
                        {
                            "method": "turn/completed",
                            "params": {"turn": {"id": "turn-1", "status": "completed"}},
                        },
                        {"id": 4, "error": "too late"},
                    ]
                )
                instances.append(self)

            def request(self, method, _params):
                return {
                    "initialize": {},
                    "thread/resume": {"thread": {"id": SESSION_ID}},
                    "turn/start": {"turn": {"id": "turn-1"}},
                }[method]

            def next_message(self, _timeout=None):
                value = next(self.messages)
                if isinstance(value, BaseException):
                    raise value
                return value

            def send(self, _method, _params):
                return 4

            def observe_notification(self, message):
                return observe_notification(self, message)

            def close(self, *, failed):
                self.closed_failed = failed

        with (
            mock.patch.object(RUNNER, "AppServerPhaseDriver", Driver),
            mock.patch.object(RUNNER.time, "monotonic", side_effect=[20.0, 21.0]),
            self.assertRaisesRegex(RuntimeError, "rejected turn/steer"),
        ):
            RUNNER.run_phase(
                ROOT,
                "rca",
                "Continue.",
                SESSION_ID,
                soft_phase_budget_seconds=1,
            )

        self.assertTrue(instances[0].closed_failed)

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
            repository, phase, answer, session_id, model, reasoning, budget = (
                RUNNER.parse()
            )
        self.assertEqual(model, "gpt-5.6-luna")
        self.assertEqual(reasoning, "high")
        self.assertIsNone(budget)
        server = AppServerFixture(receipt())

        with (
            mock.patch.object(NATIVE, "find_codex", return_value="/bin/codex"),
            mock.patch.object(RUNNER, "call_linear") as call_linear,
            mock.patch.object(RUNNER.subprocess, "Popen", side_effect=server),
        ):
            result = RUNNER.run_phase(
                repository, phase, answer, session_id, model, reasoning
            )

        self.assertEqual(result["state"], "completed")
        thread = next(
            item for item in server.requests if item.get("method") == "thread/resume"
        )
        turn = next(
            item for item in server.requests if item.get("method") == "turn/start"
        )
        self.assertEqual(
            {
                key: thread["params"][key]
                for key in (
                    "threadId",
                    "cwd",
                    "approvalPolicy",
                    "sandbox",
                    "model",
                )
            },
            {
                "threadId": SESSION_ID,
                "cwd": str(ROOT),
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
                "model": "gpt-5.6-luna",
            },
        )
        prompt = turn["params"]["input"][0]["text"]
        self.assertIn("Use production.", prompt)
        self.assertIn("# Clarification answer", prompt)
        self.assertIn("# End clarification", prompt)
        self.assertIn("cannot authorize broader scope or writes", prompt)
        self.assertLess(
            prompt.index("# End clarification"),
            prompt.index("cannot authorize broader scope or writes"),
        )
        self.assertNotIn("# Bonaparte Bug RCA", prompt)
        call_linear.assert_not_called()
