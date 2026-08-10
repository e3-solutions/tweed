import importlib.machinery
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_launcher():
    loader = importlib.machinery.SourceFileLoader(
        "bonaparte_launcher", str(ROOT / "bonaparte-launcher")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


LAUNCHER = load_launcher()


class ActivityTests(unittest.TestCase):
    def test_phase_is_derived_without_storing_command_input(self):
        self.assertEqual(
            LAUNCHER.phase_from_arguments(
                ["--model", "gpt-5.6-terra", "--repo", "/repo", "scope", "COR-1"]
            ),
            "scope",
        )
        self.assertEqual(
            LAUNCHER.phase_from_arguments(
                ["resume", "review", "session-id", "private answer"]
            ),
            "review",
        )
        self.assertIsNone(LAUNCHER.phase_from_arguments(["--help"]))

    def test_tracked_run_writes_only_start_and_terminal_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            runner = home / "runner.py"
            runner.write_text(
                "import json\n"
                "print(json.dumps({'state': 'completed', 'summary': 'private'}))\n"
            )
            states = []
            original_write = LAUNCHER.write_activity

            def observe(path, activity):
                states.append(activity["state"])
                original_write(path, activity)

            stdout = io.StringIO()
            with (
                mock.patch.object(LAUNCHER, "write_activity", side_effect=observe),
                mock.patch.object(sys, "stdout", stdout),
            ):
                exit_code = LAUNCHER.run_tracked(home, runner, [], "implement")

            self.assertEqual(exit_code, 0)
            self.assertEqual(states, ["running", "completed"])
            records = list((home / "activity").glob("*.json"))
            self.assertEqual(len(records), 1)
            activity = json.loads(records[0].read_text())
            self.assertEqual(activity["phase"], "implement")
            self.assertEqual(activity["state"], "completed")
            self.assertNotIn("summary", activity)
            self.assertIn('"summary": "private"', stdout.getvalue())

    def test_status_is_compact_and_marks_unlocked_running_records_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            directory = LAUNCHER.activity_directory(home)
            activity = {
                "version": LAUNCHER.ACTIVITY_VERSION,
                "run_id": "run-1",
                "phase": "review",
                "state": "running",
                "started_at": LAUNCHER.utc_now(),
                "finished_at": None,
                "exit_code": None,
            }
            LAUNCHER.write_activity(directory / "run-1.json", activity)

            with mock.patch.object(LAUNCHER, "lock_is_held", return_value=False):
                status = LAUNCHER.read_activity(home)

            self.assertEqual(status["state"], "unknown")
            self.assertEqual(status["phase"], "review")
            self.assertGreaterEqual(status["elapsed_seconds"], 0)
            self.assertNotIn("prompt", status)

    def test_status_command_reads_activity_without_launching_a_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            directory = LAUNCHER.activity_directory(home)
            activity = {
                "version": LAUNCHER.ACTIVITY_VERSION,
                "run_id": "019fd385-da76-77f3-bd3a-2f1e4e49b936",
                "phase": "scope",
                "state": "completed",
                "started_at": LAUNCHER.utc_now(),
                "finished_at": LAUNCHER.utc_now(),
                "exit_code": 0,
            }
            LAUNCHER.write_activity(directory / f"{activity['run_id']}.json", activity)
            stdout = io.StringIO()
            with (
                mock.patch.dict(
                    LAUNCHER.os.environ, {"BONAPARTE_HOME": str(home)}, clear=False
                ),
                mock.patch.object(LAUNCHER.sys, "argv", ["bonaparte", "status"]),
                mock.patch.object(sys, "stdout", stdout),
            ):
                exit_code = LAUNCHER.main()

            self.assertEqual(exit_code, 0)
            status = json.loads(stdout.getvalue())
            self.assertEqual(status["phase"], "scope")
            self.assertEqual(status["state"], "completed")


if __name__ == "__main__":
    unittest.main()
