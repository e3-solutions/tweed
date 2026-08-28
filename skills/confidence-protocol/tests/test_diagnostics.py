import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import confidence  # noqa: E402
import diagnostics  # noqa: E402


SCRIPT = SCRIPTS / "confidence.py"
CANARIES = {
    "secret": "token-super-secret-9281",
    "source": "def private_customer_algorithm():",
    "prompt": "PROMPT_DO_NOT_SHARE_7291",
    "path": "/Users/alice/private-repo/customer.py",
    "host": "alice-workstation-private",
}


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class DiagnosticsTest(unittest.TestCase):
    def test_error_codes_distinguish_common_failures(self) -> None:
        self.assertEqual(diagnostics.error_code_for("run", 124), "RUN_TIMEOUT")
        self.assertEqual(diagnostics.error_code_for("run", 122), "RUN_LOG_LIMIT")
        self.assertEqual(diagnostics.error_code_for("run", 125), "RUNNER_ERROR")
        self.assertEqual(
            diagnostics.error_code_for("run", 7), "CHILD_EXIT_NONZERO"
        )
        self.assertEqual(
            diagnostics.error_code_for("validate", 1), "EVIDENCE_INVALID"
        )

    def test_event_log_is_structured_and_contains_no_work_content(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            diagnostics.record_event(
                directory,
                operation_id="operation-1",
                event_name="command.completed",
                command="run",
                status="error",
                error_code="CHILD_EXIT_NONZERO",
                duration_seconds=1.2,
            )
            event = json.loads(
                (directory / "telemetry" / "events.jsonl").read_text().strip()
            )
            self.assertEqual(set(event), set(event) & diagnostics.SAFE_EVENT_KEYS)
            self.assertEqual(event["error_code"], "CHILD_EXIT_NONZERO")
            text = json.dumps(event)
            for canary in CANARIES.values():
                self.assertNotIn(canary, text)

    def test_concurrent_event_writes_remain_valid_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            threads = [
                threading.Thread(
                    target=diagnostics.record_event,
                    kwargs={
                        "directory": directory,
                        "operation_id": f"operation-{index}",
                        "event_name": "command.completed",
                        "command": "doctor",
                        "status": "ok",
                    },
                )
                for index in range(30)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            lines = (directory / "telemetry" / "events.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 30)
            self.assertTrue(all(isinstance(json.loads(line), dict) for line in lines))

    def test_remote_telemetry_uses_a_fixed_safe_payload(self) -> None:
        captured = []

        def open_request(request, timeout):
            captured.append((json.loads(request.data), request.headers, timeout))
            return FakeResponse()

        event = {
            "schema_version": 1,
            "event_id": "1" * 32,
            "operation_id": "2" * 32,
            "installation_id": "3" * 32,
            "timestamp": "2026-08-27T01:00:00.000000Z",
            "tool_version": diagnostics.TOOL_VERSION,
            "event": "command.completed",
            "command": "run",
            "status": "error",
            "error_code": "CHILD_EXIT_NONZERO",
            "duration_bucket": "lt_100ms",
            "platform": sys.platform,
            "python_version": "3.14",
            "argv": [CANARIES["secret"]],
            "output": CANARIES["source"],
            "cwd": CANARIES["path"],
            "prompt": CANARIES["prompt"],
            "hostname": CANARIES["host"],
        }
        with mock.patch("urllib.request.urlopen", side_effect=open_request):
            result = diagnostics.send_remote_event(
                event, "https://telemetry.example.test/events", CANARIES["secret"]
            )
        self.assertIsNone(result)
        body, headers, timeout = captured[0]
        self.assertEqual(set(body), diagnostics.SAFE_REMOTE_KEYS)
        serialized = json.dumps(body)
        for canary in CANARIES.values():
            self.assertNotIn(canary, serialized)
        self.assertIn("Authorization", headers)
        self.assertEqual(timeout, diagnostics.REMOTE_TIMEOUT_SECONDS)

    def test_remote_telemetry_is_disabled_without_an_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "urllib.request.urlopen"
            ) as sender:
                diagnostics.record_event(
                    Path(name) / ".confidence",
                    operation_id="operation-1",
                    event_name="command.completed",
                    command="run",
                    status="ok",
                    export=True,
                )
            sender.assert_not_called()

    def test_unsafe_telemetry_endpoint_is_rejected(self) -> None:
        self.assertEqual(
            diagnostics.endpoint_error("http://collector.example.test/events"),
            "TELEMETRY_ENDPOINT_NOT_HTTPS",
        )
        self.assertEqual(
            diagnostics.endpoint_error("https://user:pass@example.test/events"),
            "TELEMETRY_ENDPOINT_UNSAFE",
        )
        self.assertEqual(
            diagnostics.endpoint_error("https://example.test/events?secret=value"),
            "TELEMETRY_ENDPOINT_UNSAFE",
        )
        self.assertIsNone(diagnostics.endpoint_error("http://127.0.0.1:9999/events"))

    def test_diagnostics_failure_does_not_change_child_exit(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            directory.mkdir()
            (directory / "telemetry").symlink_to(root / "outside", target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--directory",
                    str(directory),
                    "--",
                    sys.executable,
                    "-c",
                    "raise SystemExit(7)",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 7)
            self.assertTrue(any((directory / "runs").glob("*.json")))

    def test_remote_failure_does_not_change_success(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            environment = os.environ.copy()
            environment["CONFIDENCE_TELEMETRY_ENDPOINT"] = "http://127.0.0.1:9/events"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--directory",
                    str(Path(name) / ".confidence"),
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ],
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ok\n")

    def test_launch_failure_has_a_specific_persistent_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--directory",
                    str(directory),
                    "--",
                    "definitely-not-a-real-confidence-command",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 125)
            events = [
                json.loads(line)
                for line in (directory / "telemetry" / "events.jsonl")
                .read_text()
                .splitlines()
            ]
            self.assertEqual(events[-1]["error_code"], "RUN_LAUNCH_FAILED")
            self.assertEqual(events[-1]["status"], "error")

    def test_real_run_events_and_support_bundle_never_capture_child_argv(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            child = (
                f"print({CANARIES['source']!r}); "
                f"print({CANARIES['path']!r}); "
                f"print({CANARIES['prompt']!r}); "
                f"print({CANARIES['secret']!r})"
            )
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--directory",
                    str(directory),
                    "--",
                    sys.executable,
                    "-c",
                    child,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            raw_events = (directory / "telemetry" / "events.jsonl").read_text()
            events = [json.loads(line) for line in raw_events.splitlines()]
            self.assertEqual([item["command"] for item in events], ["run", "run"])
            for canary in CANARIES.values():
                self.assertNotIn(canary, raw_events)

            output = root / "support.zip"
            bundle = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "support-bundle",
                    "--directory",
                    str(directory),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(bundle.returncode, 0, bundle.stderr)
            with zipfile.ZipFile(output) as archive:
                contents = "\n".join(
                    archive.read(item).decode("utf-8") for item in archive.namelist()
                )
            for canary in CANARIES.values():
                self.assertNotIn(canary, contents)

    def test_support_bundle_excludes_sensitive_run_fields_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            runs = directory / "runs"
            runs.mkdir(parents=True)
            log = runs / "sensitive.log"
            log.write_text("\n".join(CANARIES.values()))
            (runs / "sensitive.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "id": CANARIES["secret"],
                        "argv": [CANARIES["prompt"]],
                        "cwd": CANARIES["path"],
                        "resolved_executable": CANARIES["host"],
                        "started_at": "2026-08-27T01:00:00.000000Z",
                        "ended_at": "2026-08-27T01:00:01.000000Z",
                        "exit_code": 7,
                        "termination_reason": None,
                        "workspace": {
                            "kind": "git",
                            "root": CANARIES["path"],
                            "sha256": "a" * 64,
                        },
                        "log": "runs/sensitive.log",
                        "log_sha256": "b" * 64,
                    }
                )
            )
            telemetry = directory / "telemetry"
            telemetry.mkdir()
            (telemetry / "events.jsonl").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "tool_version": diagnostics.TOOL_VERSION,
                        "event_id": "1" * 32,
                        "operation_id": "2" * 32,
                        "timestamp": "2026-08-27T01:00:00.000000Z",
                        "event": CANARIES["prompt"],
                        "command": CANARIES["secret"],
                        "status": CANARIES["source"],
                        "error_code": CANARIES["host"],
                        "component": CANARIES["path"],
                    }
                )
                + "\n"
            )
            output = root / "support.zip"
            diagnostics.write_support_bundle(directory, output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"README.txt", "doctor.json", "events.json", "runs.json"},
                )
                contents = "\n".join(
                    archive.read(item).decode("utf-8") for item in archive.namelist()
                )
            for canary in CANARIES.values():
                self.assertNotIn(canary, contents)
            self.assertNotIn("argv", contents)
            self.assertNotIn("cwd", contents)

    def test_doctor_reports_required_health_checks(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            report = diagnostics.doctor_report(Path(name) / ".confidence")
            codes = {item["code"] for item in report["checks"]}
            self.assertEqual(report["status"], "pass")
            self.assertTrue(
                {
                    "PYTHON_VERSION",
                    "PLUGIN_MANIFEST",
                    "EVIDENCE_DIRECTORY",
                    "ATOMIC_HARDLINK",
                    "RUNNER_SMOKE",
                    "GIT_AVAILABLE",
                    "PROCESS_GROUP_CLEANUP",
                    "LEGACY_BONAPARTE",
                    "TELEMETRY_CONFIG",
                }
                <= codes
            )

    def test_internal_exception_is_logged_and_returns_125(self) -> None:
        events = []

        def explode(_args):
            raise RuntimeError(CANARIES["secret"])

        fake_parser = mock.Mock()
        fake_parser.return_value.parse_args.return_value = SimpleNamespace(
            action="doctor",
            directory=".confidence",
            handler=explode,
        )
        with mock.patch.object(confidence, "parser", return_value=fake_parser.return_value), mock.patch.object(
            confidence, "record_event", side_effect=lambda *args, **kwargs: events.append(kwargs)
        ), contextlib.redirect_stderr(io.StringIO()) as error:
            result = confidence.main()
        self.assertEqual(result, 125)
        self.assertEqual(events[-1]["error_code"], "INTERNAL_ERROR")
        self.assertNotIn(CANARIES["secret"], error.getvalue())


if __name__ == "__main__":
    unittest.main()
