import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "confidence.py"
SPEC = importlib.util.spec_from_file_location("confidence", SCRIPT)
confidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(confidence)


class ConfidenceTest(unittest.TestCase):
    def write_run(
        self, directory: Path, run_id: str = "tests", exit_code: int = 0
    ) -> None:
        log_path = directory / "runs" / f"{run_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(b"test output\n")
        confidence.write_json(
            directory / "runs" / f"{run_id}.json",
            {
                "version": 1,
                "id": run_id,
                "argv": ["python3", "-m", "unittest"],
                "cwd": str(directory.resolve()),
                "started_at": "2026-08-26T01:00:00.000000Z",
                "ended_at": "2026-08-26T01:00:01.000000Z",
                "exit_code": exit_code,
                "log": f"runs/{run_id}.log",
                "log_sha256": confidence.sha256_file(log_path),
            },
        )

    def valid_files(self, directory: Path) -> None:
        contract = confidence.initial_contract("Invite users", "standard", "feature")
        contract["intent"].update(
            {
                "goal": "A team owner can invite a user.",
                "must_happen": ["A valid invitation is sent."],
                "must_not_happen": ["A non-owner cannot invite users."],
            }
        )
        contract["proof_obligations"][0].update(
            {
                "claim": "Only owners can invite users.",
                "verification": "Run the authorization integration test.",
            }
        )
        report = confidence.initial_report("Invite users", "standard")
        report.update(
            {
                "outcome": "The invitation flow works for owners.",
                "rollback": "Revert the invitation change.",
            }
        )
        report["evidence"][0].update(
            {
                "status": "pass",
                "details": "The integration test passed.",
                "artifacts": ["tests/invitations.test.ts"],
                "run_ids": ["tests"],
                "diagnostic_run_ids": [],
            }
        )
        report["tests"]["passed"] = ["npm test -- invitations"]
        report["simplicity"].update(
            {
                "code_gate": "pass",
                "test_gate": "pass",
                "notes": "The change uses the existing authorization path.",
            }
        )
        report["review"].update(
            {
                "required": False,
                "reason": "The test fixture is local and does not cross a review boundary.",
            }
        )
        self.write_run(directory)
        confidence.write_json(directory / "contract.json", contract)
        confidence.write_json(directory / "report.json", report)

    def test_valid_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertEqual(errors, [])

    def test_completion_rejects_unfinished_release_gates(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["simplicity"]["code_gate"] = "fail"
            report["simplicity"]["test_gate"] = "fail"
            errors = confidence.completion_errors(report)
            self.assertTrue(any("code simplicity" in error for error in errors))
            self.assertTrue(any("test quality" in error for error in errors))

    def test_completion_rejects_partial_evidence_and_unrun_tests(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["status"] = "partial"
            report["simplicity"]["code_gate"] = "pass"
            report["simplicity"]["test_gate"] = "pass"
            report["tests"]["not_run"] = ["browser flow"]
            errors = confidence.completion_errors(report)
            self.assertTrue(any("proof obligation" in error for error in errors))
            self.assertTrue(any("not run" in error for error in errors))

    def test_completion_accepts_a_fully_passing_report(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["simplicity"]["code_gate"] = "pass"
            report["simplicity"]["test_gate"] = "pass"
            self.assertEqual(confidence.completion_errors(report), [])

    def test_critical_completion_requires_two_distinct_review_roles(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["mode"] = "critical"
            report["simplicity"]["code_gate"] = "pass"
            report["simplicity"]["test_gate"] = "pass"
            report["review"].update(
                {
                    "required": True,
                    "roles": ["test_designer"],
                    "findings": ["The proof plan covers the failure boundary."],
                }
            )
            errors = confidence.completion_errors(report)
            self.assertTrue(any("adversarial_reviewer" in error for error in errors))
            report["review"]["roles"].append("adversarial_reviewer")
            self.assertEqual(confidence.completion_errors(report), [])

    def test_missing_obligation_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["evidence"] = []
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("evidence" in error for error in errors))

    def test_duplicate_obligation_id_fails(self) -> None:
        contract = confidence.initial_contract("Test", "standard", "bug")
        contract["proof_obligations"].append(dict(contract["proof_obligations"][0]))
        errors = confidence.validate_contract(contract)
        self.assertTrue(any("duplicate" in error for error in errors))

    def test_blank_required_list_item_fails(self) -> None:
        contract = confidence.initial_contract("Test", "standard", "feature")
        contract["intent"]["goal"] = "Ship the feature."
        contract["intent"]["must_not_happen"] = ["Do not break existing users."]
        contract["proof_obligations"][0].update(
            {"claim": "The flow works.", "verification": "Run the flow test."}
        )
        errors = confidence.validate_contract(contract)
        self.assertTrue(any("must_happen" in error for error in errors))

    def test_report_must_match_contract(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["mode"] = "critical"
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("report.mode" in error for error in errors))

    def test_pass_requires_a_captured_run(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["run_ids"] = []
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("captured run" in error for error in errors))

    def test_pass_requires_a_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            self.write_run(directory, exit_code=7)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("supporting run" in error for error in errors))

    def test_tampered_log_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            (directory / "runs" / "tests.log").write_text("changed\n")
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("hash does not match" in error for error in errors))

    def test_supporting_run_becomes_stale_when_git_workspace_changes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "confidence@example.test"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Confidence Test"],
                cwd=root,
                check=True,
            )
            source = root / "source.txt"
            source.write_text("before\n")
            subprocess.run(["git", "add", "source.txt"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "baseline"], cwd=root, check=True
            )
            directory = root / ".confidence"
            self.valid_files(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "bound",
                    "--directory",
                    str(directory),
                    "--cwd",
                    str(root),
                    "--",
                    sys.executable,
                    "-c",
                    "print('bound')",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["run_ids"] = ["bound"]
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertEqual(errors, [])
            source.write_text("after\n")
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("workspace changed" in error for error in errors))

    def test_render_contains_claim_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            contract, report, _ = confidence.load_and_validate(directory)
            rendered = confidence.render_markdown(contract, report, directory)
            self.assertIn("Only owners can invite users.", rendered)
            self.assertIn("| pass |", rendered)
            self.assertIn("tests (exit 0)", rendered)

    def test_run_captures_success_and_returns_child_status(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "captured",
                    "--directory",
                    str(directory),
                    "--cwd",
                    str(root),
                    "--",
                    sys.executable,
                    "-c",
                    "print('proof')",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "proof\n")
            record = json.loads(
                (directory / "runs" / "captured.json").read_text()
            )
            self.assertEqual(record["exit_code"], 0)
            self.assertEqual(
                record["log_sha256"],
                confidence.sha256_file(directory / "runs" / "captured.log"),
            )

    def test_run_records_failure_and_returns_child_status(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "failed",
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
            record = json.loads((directory / "runs" / "failed.json").read_text())
            self.assertEqual(record["exit_code"], 7)

    def test_run_times_out_and_records_the_stop_reason(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "timeout",
                    "--directory",
                    str(directory),
                    "--timeout-seconds",
                    "0.05",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(2)",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 124)
            record = json.loads((directory / "runs" / "timeout.json").read_text())
            self.assertEqual(record["exit_code"], 124)
            self.assertEqual(record["termination_reason"], "timeout")

    def test_run_timeout_requires_a_positive_finite_value(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                try:
                    confidence.parser().parse_args(
                        [
                            "run",
                            f"--timeout-seconds={value}",
                            "--",
                            sys.executable,
                        ]
                    )
                except SystemExit as error:
                    self.assertEqual(error.code, 2)
                else:
                    self.fail("non-finite timeout value was accepted")
        self.assertEqual(confidence.positive_float("0.05"), 0.05)

    def test_run_stops_when_the_log_limit_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "large-log",
                    "--directory",
                    str(directory),
                    "--max-log-bytes",
                    "100",
                    "--",
                    sys.executable,
                    "-c",
                    "print('x' * 10000)",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 122)
            record = json.loads((directory / "runs" / "large-log.json").read_text())
            self.assertEqual(record["termination_reason"], "log_limit")

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_run_stops_background_children_before_hashing_the_log(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            child = "import time; time.sleep(0.3); print('late', flush=True)"
            parent = (
                "import subprocess, sys; "
                f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                "print('leader', flush=True)"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "background-child",
                    "--directory",
                    str(directory),
                    "--",
                    sys.executable,
                    "-c",
                    parent,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            log_path = directory / "runs" / "background-child.log"
            record = json.loads(
                (directory / "runs" / "background-child.json").read_text()
            )
            captured_hash = confidence.sha256_file(log_path)
            time.sleep(0.5)
            self.assertEqual(log_path.read_text(), "leader\n")
            self.assertEqual(confidence.sha256_file(log_path), captured_hash)
            self.assertEqual(record["log_sha256"], captured_hash)

    def test_run_rejects_path_traversal_id(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "../escape",
                    "--directory",
                    str(root / ".confidence"),
                    "--",
                    sys.executable,
                    "-c",
                    "print('no')",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 125)
            self.assertFalse((root / "escape.json").exists())

    def test_run_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            command = [
                sys.executable,
                str(SCRIPT),
                "run",
                "--id",
                "once",
                "--directory",
                str(directory),
                "--",
                sys.executable,
                "-c",
                "print('once')",
            ]
            self.assertEqual(
                subprocess.run(command, capture_output=True, text=True).returncode, 0
            )
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 125)
            self.assertIn("refusing to overwrite", second.stderr)

    def test_run_rejects_a_symlinked_runs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            outside = root / "outside"
            outside.mkdir()
            directory.mkdir()
            (directory / "runs").symlink_to(outside, target_is_directory=True)
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
                    "print('no')",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 125)
            self.assertFalse(any(outside.iterdir()))

    def test_atomic_record_write_never_replaces_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "record.json"
            path.write_text('{"original": true}\n')
            with self.assertRaises(FileExistsError):
                confidence.write_json_exclusive_atomic(path, {"replacement": True})
            self.assertEqual(path.read_text(), '{"original": true}\n')

    def test_fail_then_pass_runs_support_one_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            self.write_run(directory, "before-fix", exit_code=1)
            self.write_run(directory, "after-fix", exit_code=0)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["run_ids"] = ["after-fix"]
            report["evidence"][0]["diagnostic_run_ids"] = ["before-fix"]
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertEqual(errors, [])

    def test_pass_rejects_a_failed_supporting_run_even_with_a_success(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            self.write_run(directory, "real-test", exit_code=1)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["run_ids"] = ["real-test", "tests"]
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("every supporting run" in error for error in errors))

    def test_run_cannot_be_supporting_and_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["diagnostic_run_ids"] = ["tests"]
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("supporting and diagnostic" in error for error in errors))

    def test_run_id_must_match_filename(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            record_path = directory / "runs" / "tests.json"
            record = confidence.read_json(record_path)
            record["id"] = "different"
            confidence.write_json(record_path, record)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("match its filename" in error for error in errors))

    def test_run_could_not_start_creates_no_record(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "missing-command",
                    "--directory",
                    str(directory),
                    "--",
                    "definitely-not-a-real-confidence-command",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 125)
            self.assertIn("could not start command", result.stderr)
            self.assertFalse((directory / "runs" / "missing-command.json").exists())
            self.assertFalse((directory / "runs" / "missing-command.log").exists())

    def test_run_accepts_command_when_argparse_consumes_separator(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--id",
                    "portable",
                    "--directory",
                    str(directory),
                    sys.executable,
                    "-c",
                    "print('portable')",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((directory / "runs" / "portable.json").exists())

    def test_render_escapes_table_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            contract = confidence.read_json(directory / "contract.json")
            report = confidence.read_json(directory / "report.json")
            contract["proof_obligations"][0]["claim"] = "Owner | only\nrule"
            rendered = confidence.render_markdown(contract, report, directory)
            self.assertIn("Owner \\| only rule", rendered)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "duplicate.json"
            path.write_text('{"status": "fail", "status": "pass"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                confidence.read_json(path)

    def test_report_rejects_non_string_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            report = confidence.read_json(directory / "report.json")
            report["evidence"][0]["artifacts"] = [1]
            confidence.write_json(directory / "report.json", report)
            _, _, errors = confidence.load_and_validate(directory)
            self.assertTrue(any("artifacts" in error for error in errors))

    def test_render_flattens_markdown_structure_in_text_fields(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            self.valid_files(directory)
            contract = confidence.read_json(directory / "contract.json")
            report = confidence.read_json(directory / "report.json")
            report["changes"] = ["safe\n\n## Forged section"]
            report["outcome"] = "ok\n\n<script>alert(1)</script>"
            rendered = confidence.render_markdown(contract, report, directory)
            self.assertNotIn("\n## Forged section", rendered)
            self.assertNotIn("<script>", rendered)

    def test_render_stays_inside_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / ".confidence"
            self.valid_files(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "render",
                    "--directory",
                    str(directory),
                    "--output",
                    "../outside.md",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / "outside.md").exists())

    def test_render_requires_force_to_replace_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / ".confidence"
            self.valid_files(directory)
            command = [
                sys.executable,
                str(SCRIPT),
                "render",
                "--directory",
                str(directory),
            ]
            self.assertEqual(subprocess.run(command).returncode, 0)
            self.assertEqual(subprocess.run(command).returncode, 2)
            self.assertEqual(subprocess.run(command + ["--force"]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
