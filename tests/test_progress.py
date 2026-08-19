import errno
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bonaparte_native as NATIVE
import bonaparte_progress as PROGRESS
from tests.test_bonaparte import (
    NATIVE_COLLAB_SPAWN_COMPLETED,
    NATIVE_COLLAB_WAIT_COMPLETED,
    ROOT,
    RUNNER,
    SESSION_ID,
    SUBAGENT_ID,
    app_server_script,
    delivery_receipt,
)

NATIVE_FIXTURE = ROOT / "tests/fixtures/codex_app_server_v2.jsonl"


def captured_native_messages():
    return [json.loads(line) for line in NATIVE_FIXTURE.read_text().splitlines()]


class ProgressAndEventTests(unittest.TestCase):
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
                {
                    "version",
                    "progress_abi",
                    "sequence",
                    "phase",
                    "state",
                    "runtime_version",
                    "update_state",
                    "elapsed_seconds",
                    "semantic",
                },
            )
            self.assertEqual(event["version"], 3)
            self.assertEqual(event["progress_abi"], 3)
            self.assertIsNone(event["runtime_version"])
            self.assertEqual(event["update_state"], "unknown")
            self.assertEqual(event["phase"], "review")
            self.assertLessEqual(len(json.dumps(event).encode()), 4096)

    def test_progress_fd_is_scrubbed_and_never_sent_to_children(self):
        for value in ("", "2", "+3", "not-a-descriptor"):
            with (
                self.subTest(value=value),
                mock.patch.dict(
                    os.environ, {RUNNER.PROGRESS_FD_ENV: value}, clear=False
                ),
            ):
                progress = RUNNER.acquire_progress_reporter(True)
                self.assertNotIn(RUNNER.PROGRESS_FD_ENV, os.environ)

                self.assertNotIn(RUNNER.PROGRESS_FD_ENV, NATIVE.child_environment())
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

    def test_runtime_and_stable_update_notice_are_fixed_and_nonblocking(self):
        read_descriptor, write_descriptor = os.pipe()
        os.set_blocking(write_descriptor, False)
        with mock.patch.dict(
            os.environ,
            {
                RUNNER.PROGRESS_FD_ENV: str(write_descriptor),
                "BONAPARTE_RUNTIME_VERSION": "v0.4.0",
                "BONAPARTE_STABLE_UPDATE": "available",
            },
            clear=False,
        ):
            progress = RUNNER.acquire_progress_reporter(True, "scope")
            progress.start()
            progress.stop_heartbeat()
            progress.report("finalizing")
            progress.report("completed")
            progress.close()
        events = [
            json.loads(line)
            for line in os.read(read_descriptor, 16384).splitlines()
        ]
        os.close(read_descriptor)
        self.assertEqual(
            [event["state"] for event in events],
            ["started", "update-available", "finalizing", "completed"],
        )
        self.assertTrue(
            all(
                event["runtime_version"] == "v0.4.0"
                and event["update_state"] == "available"
                and event["progress_abi"] == 3
                for event in events
            )
        )

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
            mock.patch.object(
                progress._stop, "wait", side_effect=[False, True]
            ) as wait,
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
        observer.feed(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "web_search", "query": canary},
                }
            )
        )
        for _ in range(40):
            observer.feed(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "file_change",
                            "path": canary,
                            "patch": canary,
                        },
                    }
                )
            )
        observer.feed(
            json.dumps(
                {"type": "agent_message", "message": canary, "reasoning": canary}
            )
        )
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
        self.assertTrue(
            all(event["version"] == 3 and event["phase"] == "scope" for event in events)
        )
        self.assertLessEqual(len(events[1]["semantic"].get("milestones", [])), 32)
        self.assertTrue(
            all(
                len(line) + 1 <= RUNNER.PROGRESS_MAX_BYTES
                for line in payload.splitlines()
            )
        )

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
        self.assertNotIn("private assignment", json.dumps(progress.snapshot()))

    def test_app_server_notifications_translate_without_leaking_payloads(self):
        progress = RUNNER.ProgressReporter(None, "review")
        observer = RUNNER.EventObserver(progress)
        driver = object.__new__(RUNNER.AppServerPhaseDriver)
        driver.observer = observer
        driver._last_agent_message = None
        driver._receipt_thread_id = SESSION_ID
        driver._receipt_turn_id = "turn-1"
        canary = "private-app-server-payload"

        driver.observe_notification(
            {
                "method": "thread/started",
                "params": {"thread": {"id": SESSION_ID}},
            }
        )
        driver.observe_notification(
            {
                "method": "item/completed",
                "params": {
                    "threadId": SESSION_ID,
                    "turnId": "turn-1",
                    "item": {
                        "type": "collabAgentToolCall",
                        "tool": "spawnAgent",
                        "receiverThreadIds": [SUBAGENT_ID],
                        "agentsStates": {SUBAGENT_ID: {"status": "completed"}},
                        "prompt": canary,
                        "status": "completed",
                    },
                },
            }
        )
        assignment = progress.snapshot()["semantic"]
        driver.observe_notification(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "command": "python -m unittest",
                        "exitCode": 0,
                        "status": "completed",
                    }
                },
            }
        )
        driver.observe_notification(
            {
                "method": "item/completed",
                "params": {
                    "threadId": SESSION_ID,
                    "turnId": "turn-1",
                    "item": {
                        "type": "agentMessage",
                        "text": json.dumps(delivery_receipt("review")),
                    },
                },
            }
        )
        observation = observer.finish()

        self.assertEqual(observation["session_id"], SESSION_ID)
        self.assertEqual(observation["checks_completed_total_count"], 1)
        self.assertEqual(observation["checks_completed"][0]["status"], "passed")
        self.assertEqual(assignment["stage"], "subagent-assignment")
        self.assertEqual(assignment["actor"], "subagent-1")
        self.assertEqual(json.loads(driver.last_agent_message)["state"], "completed")
        self.assertNotIn(canary, json.dumps(progress.snapshot()))

    def test_native_subagent_activity_reports_assignment(self):
        progress = RUNNER.ProgressReporter(None, "review")
        observer = RUNNER.EventObserver(progress)
        driver = object.__new__(RUNNER.AppServerPhaseDriver)
        driver.observer = observer
        driver._last_agent_message = None
        driver._receipt_thread_id = SESSION_ID
        driver._receipt_turn_id = "turn-root"

        subagent_started, failed_command, _child_message = captured_native_messages()
        driver.observe_notification(subagent_started)

        semantic = progress.snapshot()["semantic"]
        self.assertEqual(semantic["stage"], "subagent-assignment")
        self.assertEqual(semantic["actor"], "subagent-1")
        self.assertEqual(semantic["status"], "started")

        driver.observe_notification(failed_command)
        observation = observer.finish()
        self.assertEqual(observation["checks_completed"][0]["status"], "failed")

    def test_app_server_receipt_is_bound_to_the_root_thread_and_turn(self):
        driver = object.__new__(RUNNER.AppServerPhaseDriver)
        driver.observer = RUNNER.EventObserver()
        driver._last_agent_message = None
        driver._receipt_thread_id = SESSION_ID
        driver._receipt_turn_id = "turn-root"
        root_receipt = delivery_receipt("review")

        def completed_message(thread_id, turn_id, text):
            return {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {"type": "agentMessage", "text": text},
                },
            }

        driver.observe_notification(
            completed_message(SESSION_ID, "turn-root", json.dumps(root_receipt))
        )
        driver.observe_notification(captured_native_messages()[2])

        self.assertEqual(json.loads(driver.last_agent_message), root_receipt)

    def test_native_collab_agent_fields_and_enums_translate_to_legacy_taxonomy(self):
        for native_tool, legacy_tool in {
            "spawnAgent": "spawn_agent",
            "sendInput": "send_input",
            "resumeAgent": "resume_agent",
            "wait": "wait",
            "closeAgent": "close_agent",
        }.items():
            with self.subTest(tool=native_tool):
                translated = RUNNER.AppServerPhaseDriver._legacy_item(
                    {
                        "type": "collabAgentToolCall",
                        "tool": native_tool,
                        "receiverThreadIds": [SUBAGENT_ID],
                        "agentsStates": {
                            SUBAGENT_ID: {"status": "pendingInit"},
                            "missing-agent": {"status": "notFound"},
                        },
                    }
                )
                self.assertEqual(translated["type"], "collab_tool_call")
                self.assertEqual(translated["tool"], legacy_tool)
                self.assertEqual(translated["receiver_thread_ids"], [SUBAGENT_ID])
                self.assertEqual(
                    translated["agents_states"],
                    {
                        SUBAGENT_ID: {"status": "pending_init"},
                        "missing-agent": {"status": "not_found"},
                    },
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
        for index in range(PROGRESS.PROGRESS_MAX_ACTORS + 5):
            event = {
                **NATIVE_COLLAB_SPAWN_COMPLETED,
                "item": {
                    **NATIVE_COLLAB_SPAWN_COMPLETED["item"],
                    "receiver_thread_ids": [f"agent-{index}"],
                    "agents_states": {f"agent-{index}": {"status": "running"}},
                },
            }
            observer.feed(json.dumps(event))

        self.assertEqual(len(observer._actors), PROGRESS.PROGRESS_MAX_ACTORS)
        self.assertEqual(
            progress.snapshot()["semantic"]["actor"],
            f"subagent-{PROGRESS.PROGRESS_MAX_ACTORS + 1}",
        )

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
                events = [
                    json.loads(line) for line in os.read(reader, 16384).splitlines()
                ]
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
                    PROGRESS.threading, "Thread", factory
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
                    PROGRESS.threading, "Thread", return_value=heartbeat
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
                app_server_script(fake_receipt).replace(
                    "import json, sys\n",
                    "import json, os, pathlib, sys\n"
                    "if '--version' not in sys.argv:\n"
                    " with pathlib.Path(os.environ['COORDINATOR_CALLS']).open('a') as calls:\n"
                    "  calls.write('called\\n')\n",
                )
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
            emitted = json.loads(completed.stdout)
            self.assertEqual(emitted["state"], fake_receipt["state"])
            self.assertEqual(emitted["receipt_protocol"], 2)
            self.assertEqual(emitted["progress_abi"], 3)
            self.assertIsNone(emitted["resume_session_id"])
            self.assertEqual(
                coordinator_calls.read_text().splitlines(), ["called", "called"]
            )
            self.assertEqual(heartbeat_joins.read_text().splitlines(), ["joined"])
            self.assertEqual(
                [json.loads(line)["state"] for line in progress_output.splitlines()],
                ["started"],
            )
