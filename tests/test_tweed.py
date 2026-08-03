from __future__ import annotations

import importlib.machinery
import importlib.util
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai_codex.types import TurnStatus


ROOT = Path(__file__).resolve().parents[1]
FAKE_ADAPTER = ROOT / "tests/fake_linear_adapter.py"
LOADER = importlib.machinery.SourceFileLoader("tweed_module", str(ROOT / "tweed"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
TWEED = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = TWEED
LOADER.exec_module(TWEED)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(directory: str) -> Path:
    root = Path(directory) / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Tweed Tests")
    git(root, "config", "user.email", "tweed@example.test")
    (root / "README.md").write_text("baseline\n")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "baseline")
    return root


def make_issue(identifier: str, description: str, *, revision: str = "1") -> dict:
    return {
        "identifier": identifier,
        "url": f"https://linear.test/{identifier}",
        "title": "Fixture issue",
        "description": description,
        "revision": revision,
        "digest": TWEED.digest(description),
    }


def write_fake_linear(path: Path, issue: dict) -> None:
    path.write_text(
        json.dumps({"issues": {issue["identifier"]: issue}, "next": 2, "writes": 0})
    )


class FakeThread:
    def __init__(self, response: dict):
        self.response = response
        self.prompts: list[str] = []
        self.options: list[dict] = []

    def run(self, prompt: str, **options):
        self.prompts.append(prompt)
        self.options.append(options)
        return SimpleNamespace(
            status=TurnStatus.completed,
            final_response=json.dumps(self.response),
            error=None,
        )


class SlowHandle:
    id = "turn-1"

    def __init__(self):
        self.interrupted = False

    def run(self):
        time.sleep(2)

    def interrupt(self):
        self.interrupted = True


class SlowThread:
    def __init__(self):
        self.handle = SlowHandle()

    def turn(self, _prompt: str, **_options):
        return self.handle


class ReadThread:
    def __init__(self, turns: list[SimpleNamespace]):
        self.turns = turns

    def read(self, *, include_turns: bool = False):
        assert include_turns
        return SimpleNamespace(thread=SimpleNamespace(turns=self.turns))


class TweedTests(unittest.TestCase):
    def test_problem_and_feature_start_at_their_only_legal_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            problem = TWEED.intake_description(
                "problem", "Duplicate export", root, "CX", "tw_0123456789abcdef"
            )
            feature = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )

        self.assertEqual(TWEED.parse_metadata(problem)["stage"], "needs-rca")
        self.assertEqual(TWEED.parse_metadata(feature)["stage"], "needs-scope")

    def test_completed_phase_replaces_one_section_and_advances_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "problem", "Duplicate export", root, "CX", "tw_0123456789abcdef"
            )
            issue = {
                "identifier": "ENG-1",
                "url": "https://linear.example/ENG-1",
                "title": "Duplicate export",
                "description": description,
            }
            metadata = TWEED.parse_metadata(description)
            result = {
                "status": "established",
                "summary": "Found the cause",
                "question": None,
                "report_markdown": "Status: established\n\n# Root cause\n\nCause.",
            }
            updated = TWEED.advanced_description(
                issue,
                metadata,
                TWEED.PHASES["root-cause"],
                result,
                "tw_1111111111111111",
                root,
                None,
                None,
            )

        parsed = TWEED.parse_metadata(updated)
        self.assertEqual(parsed["stage"], "needs-scope")
        self.assertEqual(parsed["contract_revision"], 1)
        self.assertEqual(updated.count("<!-- tweed:rca:start -->"), 1)

    def test_replacing_a_phase_is_deterministic(self):
        value = TWEED.section_block("scope", "old")
        once = TWEED.replace_section(value, "scope", "new")
        twice = TWEED.replace_section(once, "scope", "newer")
        self.assertNotIn("old", twice)
        self.assertNotIn("\nnew\n", twice)
        self.assertEqual(twice.count("tweed:scope:start"), 1)

    def test_section_parser_accepts_linear_indented_end_marker(self):
        value = "<!-- tweed:scope:start -->\nStatus: scoped\n  <!-- tweed:scope:end -->"
        self.assertEqual(TWEED.section_body(value, "scope"), "Status: scoped")
        replaced = TWEED.replace_section(value, "scope", "Status: updated")
        self.assertEqual(TWEED.section_body(replaced, "scope"), "Status: updated")

    def test_sync_reconciliation_requires_complete_exact_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )
            issue = {
                "identifier": "ENG-1",
                "url": "https://linear.example/ENG-1",
                "title": "CSV export",
                "description": description,
            }
            result = {
                "status": "scoped",
                "summary": "Scoped",
                "question": None,
                "report_markdown": (
                    "Status: scoped\n\n# Solution scope\n\n"
                    "- [Docs](https://example.com/docs)\n\n1. One\n\n2. Two"
                ),
            }
            run_id = "tw_1111111111111111"
            desired = TWEED.advanced_description(
                issue,
                TWEED.parse_metadata(description),
                TWEED.PHASES["scope"],
                result,
                run_id,
                root,
                None,
                None,
            )
            state = {
                "run_id": run_id,
                "phase": "scope",
                "new_description": desired,
            }

            self.assertTrue(
                TWEED.phase_sync_already_landed(
                    state,
                    {
                        **issue,
                        "description": desired,
                        "digest": TWEED.digest(desired),
                    },
                )
            )
            changed = TWEED.replace_section(
                desired, "request", "# Request\n\nConcurrent user edit"
            )
            self.assertFalse(
                TWEED.phase_sync_already_landed(
                    state,
                    {
                        **issue,
                        "description": changed,
                        "digest": TWEED.digest(changed),
                    },
                )
            )

    def test_wrong_stage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "problem", "Duplicate export", root, "CX", "tw_0123456789abcdef"
            )
            issue = {
                "identifier": "ENG-1",
                "url": "https://linear.example/ENG-1",
                "title": "Duplicate export",
                "description": description,
            }
            with self.assertRaisesRegex(RuntimeError, "scope requires 'needs-scope'"):
                TWEED.validate_issue_for_phase(issue, TWEED.PHASES["scope"], root)

    def test_feature_cannot_run_root_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )
            metadata = TWEED.parse_metadata(description)
            metadata["stage"] = "needs-rca"
            description = TWEED.replace_metadata(description, metadata)
            issue = {
                "identifier": "ENG-2",
                "url": "https://linear.example/ENG-2",
                "title": "CSV export",
                "description": description,
            }
            with self.assertRaisesRegex(RuntimeError, "only valid for problem"):
                TWEED.validate_issue_for_phase(issue, TWEED.PHASES["root-cause"], root)

    def test_structured_turn_uses_output_schema(self):
        response = {
            "status": "scoped",
            "summary": "Scoped",
            "question": None,
            "report_markdown": "Status: scoped",
        }
        thread = FakeThread(response)
        result = TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])
        self.assertEqual(result, response)
        self.assertIn("output_schema", thread.options[0])
        self.assertEqual(thread.options[0]["sandbox"], TWEED.Sandbox.read_only)

    def test_needs_input_requires_a_structured_question(self):
        thread = FakeThread(
            {
                "status": "needs-input",
                "summary": "Need a decision",
                "question": None,
                "report_markdown": "Status: needs-input",
            }
        )
        with self.assertRaisesRegex(RuntimeError, "without a structured question"):
            TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])

    def test_report_status_must_match_structured_status(self):
        thread = FakeThread(
            {
                "status": "scoped",
                "summary": "Scoped",
                "question": None,
                "report_markdown": "Status: blocked",
            }
        )
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])

    def test_scope_evidence_is_verified_from_repository_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            readme_hash = TWEED.hashlib.sha256(
                (root / "README.md").read_bytes()
            ).hexdigest()
            report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{readme_hash}`\n"
                "- `new-file.ts` → `ABSENT`\n\n## Implementation steps\n"
            )
            TWEED.validate_scope_evidence(root, report)

            malformed = report.replace(readme_hash, readme_hash[:-1])
            with self.assertRaisesRegex(RuntimeError, "invalid SHA-256"):
                TWEED.validate_scope_evidence(root, malformed)

            wrong = report.replace(readme_hash, "0" * 64)
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                TWEED.validate_scope_evidence(root, wrong)

            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )
            snapshot = {
                "description": description + "\n" + TWEED.section_block("scope", report)
            }
            TWEED.validate_linear_snapshot(root, snapshot)
            snapshot["description"] = snapshot["description"].replace(
                readme_hash, readme_hash[:-1]
            )
            with self.assertRaisesRegex(RuntimeError, "invalid SHA-256"):
                TWEED.validate_linear_snapshot(root, snapshot)

    def test_turn_timeout_interrupts_the_active_turn(self):
        thread = SlowThread()
        with self.assertRaisesRegex(TimeoutError, "exceeded 1 seconds"):
            TWEED.completed_json_turn(thread, "work", {}, timeout_seconds=1)
        self.assertTrue(thread.handle.interrupted)

    def test_linear_turn_timeout_is_bounded_and_configurable(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWEED_LINEAR_TIMEOUT", None)
            self.assertEqual(TWEED.linear_turn_timeout(), 300)
        with patch.dict(os.environ, {"TWEED_LINEAR_TIMEOUT": "45"}):
            self.assertEqual(TWEED.linear_turn_timeout(), 45)
        with patch.dict(os.environ, {"TWEED_LINEAR_TIMEOUT": "0"}):
            with self.assertRaisesRegex(RuntimeError, "positive integer"):
                TWEED.linear_turn_timeout()

    def test_resume_prompt_distinguishes_clarification_from_interruption(self):
        clarification = TWEED.resume_prompt("awaiting-input", "Use option A")
        interrupted = TWEED.resume_prompt("running", "")

        self.assertIn("Clarification answer", clarification)
        self.assertIn("runner process was interrupted", interrupted)
        with self.assertRaisesRegex(RuntimeError, "requires an answer"):
            TWEED.resume_prompt("awaiting-input", "")
        with self.assertRaisesRegex(RuntimeError, "without a clarification answer"):
            TWEED.resume_prompt("failed", "unexpected answer")

    def test_run_execution_lock_rejects_a_duplicate_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                with TWEED.run_execution_lock("tw_0123456789abcdef"):
                    with self.assertRaisesRegex(RuntimeError, "already active"):
                        with TWEED.run_execution_lock("tw_0123456789abcdef"):
                            pass

    def test_duplicate_resume_does_not_fail_the_live_run_or_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            state = {
                "run_id": run_id,
                "state": "running",
                "phase": "scope",
                "repository": directory,
                "worktree": directory,
                "branch": None,
            }
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.save_run(state)
                TWEED.LAST_RUN_ID = None
                with TWEED.run_execution_lock(run_id):
                    with patch.object(
                        TWEED,
                        "read_request",
                        side_effect=AssertionError("must not prompt"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "already active"):
                            TWEED.resume_command(
                                SimpleNamespace(run_id=run_id, answer=[], agent=True)
                            )
                self.assertEqual(TWEED.load_run(run_id)["state"], "running")
                self.assertIsNone(TWEED.LAST_RUN_ID)

    def test_completed_recorded_turn_is_recovered_without_a_new_turn(self):
        response = json.dumps(
            {
                "status": "scoped",
                "summary": "Scoped",
                "question": None,
                "report_markdown": "Status: scoped",
            }
        )
        turn = SimpleNamespace(
            id="turn-1",
            status=TurnStatus.completed,
            items=[
                SimpleNamespace(
                    type="agentMessage",
                    phase=SimpleNamespace(value="final_answer"),
                    text=response,
                )
            ],
        )

        result = TWEED.recover_recorded_result(
            ReadThread([turn]), {"turn_id": "turn-1"}, TWEED.PHASES["scope"]
        )

        self.assertEqual(result["status"], "scoped")

    def test_active_or_missing_recorded_turn_cannot_be_duplicated(self):
        active = SimpleNamespace(id="turn-1", status=TurnStatus.in_progress, items=[])
        with self.assertRaisesRegex(RuntimeError, "still active"):
            TWEED.recover_recorded_result(
                ReadThread([active]),
                {"turn_id": "turn-1"},
                TWEED.PHASES["scope"],
            )
        with self.assertRaisesRegex(RuntimeError, "no recorded"):
            TWEED.recover_recorded_result(ReadThread([]), {}, TWEED.PHASES["scope"])

    def test_resume_rejects_a_moved_or_changed_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            metadata = {"planning_base": git(root, "rev-parse", "HEAD")}
            TWEED.validate_resume_worktree(
                root, root, None, TWEED.PHASES["scope"], metadata
            )
            (root / "README.md").write_text("changed\n")
            git(root, "add", "README.md")
            git(root, "commit", "-m", "move head")
            with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
                TWEED.validate_resume_worktree(
                    root, root, None, TWEED.PHASES["scope"], metadata
                )

    def test_run_state_round_trip_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                state = {
                    "run_id": "tw_0123456789abcdef",
                    "state": "awaiting-input",
                    "report_markdown": "Status: needs-input",
                    "workflow_text": "workflow",
                }
                TWEED.save_run(state)
                loaded = TWEED.load_run(state["run_id"])
                path = TWEED.state_path(state["run_id"])
                self.assertEqual(loaded["state"], "awaiting-input")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse((path.parent / "report.md").exists())
                self.assertEqual(loaded["run_schema_version"], 2)

    def test_project_configuration_is_keyed_by_canonical_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            config = Path(directory) / "config.json"
            with patch.dict(os.environ, {"TWEED_CONFIG": str(config)}):
                TWEED.set_linear_project(root, "Customer Experience")
                self.assertEqual(TWEED.linear_project(root), "Customer Experience")
                TWEED.set_linear_project(root, None)
                self.assertIsNone(TWEED.linear_project(root))

    def test_child_sessions_disable_the_competing_linear_orchestrator(self):
        with patch.object(TWEED, "find_codex", return_value="/bin/true"):
            config = TWEED.codex_config(Path("/tmp").resolve())
        self.assertIn("features.hooks=false", config.config_overrides)
        self.assertIn(
            'plugins."linear-progress-sync@coreedge-local".enabled=false',
            config.config_overrides,
        )

    def test_all_child_sessions_use_sol_medium(self):
        with patch.object(TWEED, "find_codex", return_value="/bin/true"):
            config = TWEED.codex_config(Path("/tmp").resolve())
        self.assertIn('model="gpt-5.6-sol"', config.config_overrides)
        self.assertIn('model_reasoning_effort="medium"', config.config_overrides)

    def test_runner_owns_integration_worktree_and_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            base = git(root, "rev-parse", "HEAD")
            worktree, branch = TWEED.prepare_implementation_worktree(
                root, "ENG-9", base
            )
            (worktree / "feature.txt").write_text("implemented\n")
            commit = TWEED.commit_phase(worktree, "ENG-9", TWEED.PHASES["implement"])

            self.assertEqual(branch, "tweed/eng-9")
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), commit)
            self.assertFalse(git(worktree, "status", "--porcelain"))

    def test_review_without_repairs_keeps_implementation_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            commit = TWEED.commit_phase(root, "ENG-9", TWEED.PHASES["review"])
            self.assertEqual(commit, git(root, "rev-parse", "HEAD"))

    def test_model_free_linear_adapter_uses_exact_utf8_cas_and_fails_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "feature", "Café 🚚\nsecond line", root, "CX", "tw_0123456789abcdef"
            )
            issue = make_issue("TST-1", description)
            store = Path(directory) / "linear.json"
            write_fake_linear(store, issue)
            env = {
                "TWEED_LINEAR_ADAPTER": str(FAKE_ADAPTER),
                "FAKE_LINEAR_STATE": str(store),
            }
            with patch.dict(os.environ, env):
                frozen = TWEED.read_linear_issue(root, "TST-1")
                desired = description + "\nUnicode: naïve\n"
                synced = TWEED.update_linear_issue(
                    root,
                    "TST-1",
                    frozen["revision"],
                    frozen["digest"],
                    frozen["description"],
                    desired,
                )
                stale = TWEED.update_linear_issue(
                    root,
                    "TST-1",
                    frozen["revision"],
                    frozen["digest"],
                    frozen["description"],
                    desired + "stale",
                )
            state = json.loads(store.read_text())
            self.assertEqual(synced["status"], "synced")
            self.assertEqual(stale["status"], "blocked")
            self.assertEqual(state["writes"], 1)
            self.assertEqual(state["issues"]["TST-1"]["description"], desired)

    def test_missing_linear_adapter_fails_with_narrow_configuration_requirement(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWEED_LINEAR_ADAPTER", None)
            with self.assertRaisesRegex(RuntimeError, "officially authenticated adapter"):
                TWEED.linear_adapter_command()

    def test_create_transport_failure_emits_retryable_sync_blocked_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            with (
                patch.dict(os.environ, {"TWEED_STATE_HOME": directory}),
                patch.object(TWEED, "repository_root", return_value=root),
                patch.object(TWEED, "linear_project", return_value="CX"),
                patch.object(
                    TWEED, "create_linear_issue", side_effect=RuntimeError("offline")
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                result = TWEED.create_command(
                    SimpleNamespace(
                        repo=str(root),
                        request=["Create", "CSV"],
                        kind="feature",
                        agent=True,
                    )
                )
                receipt = json.loads(output.getvalue())
                saved = TWEED.load_run(receipt["run_id"])
            self.assertEqual(result, 8)
            self.assertEqual(receipt["state"], "sync-blocked")
            self.assertEqual(saved["state"], "sync-blocked")

    def test_completed_phase_transport_failure_preserves_reasoning_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description("feature", "CSV", root, "CX", run_id)
            issue = make_issue("TST-1", description)
            report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{TWEED.sha256_file(root / 'README.md')}`"
            )
            result = {
                "status": "scoped",
                "summary": "done",
                "question": None,
                "report_markdown": report,
            }
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                with (
                    patch.object(
                        TWEED,
                        "verify_linear_issue",
                        side_effect=AssertionError(
                            "finish must use the atomic CAS instead of a separate verify"
                        ),
                    ),
                    patch.object(
                        TWEED,
                        "update_linear_issue",
                        side_effect=RuntimeError("adapter offline"),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    code = TWEED.finish_phase(
                        root,
                        root,
                        None,
                        issue,
                        TWEED.parse_metadata(description),
                        TWEED.PHASES["scope"],
                        run_id,
                        "thread-1",
                        result,
                        True,
                    )
                saved = TWEED.load_run(run_id)
                persisted_report = TWEED.read_artifact(run_id, "scope")
                with (
                    patch.object(
                        TWEED,
                        "update_linear_issue",
                        return_value={
                            "status": "synced",
                            "identifier": issue["identifier"],
                            "url": issue["url"],
                        },
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as retry_output,
                ):
                    retry_code = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
            self.assertEqual(code, 8)
            self.assertEqual(json.loads(output.getvalue())["state"], "sync-blocked")
            self.assertEqual(saved["state"], "sync-blocked")
            self.assertEqual(persisted_report, report.encode())
            self.assertEqual(retry_code, 0)
            self.assertEqual(json.loads(retry_output.getvalue())["state"], "completed")

    def test_snapshot_is_frozen_once_into_separate_integrity_checked_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description(
                "problem", "Broken export", root, "CX", run_id
            )
            description += "\n" + TWEED.section_block("rca", "Status: established\n\nCause")
            issue = make_issue("TST-1", description)
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                manifest = TWEED.load_artifact_manifest(run_id)
                self.assertIn("request", manifest["artifacts"])
                self.assertIn("rca", manifest["artifacts"])
                self.assertIn("evidence", manifest["artifacts"])
                self.assertNotEqual(
                    manifest["artifacts"]["request"]["sha256"],
                    manifest["artifacts"]["rca"]["sha256"],
                )
                rca_path = (
                    TWEED.artifact_root(run_id)
                    / manifest["artifacts"]["rca"]["path"]
                )
                rca_path.write_text("tampered")
                with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
                    TWEED.read_artifact(run_id, "rca")

    def test_run_state_restores_last_committed_manifest_after_partial_write(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.put_artifact(run_id, "request", "original")
                TWEED.save_run({"run_id": run_id, "state": "running"})
                committed = TWEED.load_run(run_id)["artifact_manifest_digest"]
                TWEED.put_artifact(run_id, "scope", "uncommitted")
                self.assertNotEqual(TWEED.manifest_digest(run_id), committed)
                TWEED.load_run(run_id)
                self.assertEqual(TWEED.manifest_digest(run_id), committed)
                with self.assertRaisesRegex(RuntimeError, "artifact is missing"):
                    TWEED.read_artifact(run_id, "scope")

    def test_phase_prompt_is_bounded_and_never_repeats_complete_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            large = "SENSITIVE-COMPLETE-PAYLOAD-" + ("x" * 50000)
            description = TWEED.intake_description("feature", large, root, "CX", run_id)
            scope = "Status: scoped\n\n## Repository state\n\n- `README.md` → `" + TWEED.sha256_file(root / "README.md") + "`"
            description += "\n" + TWEED.section_block("scope", scope)
            issue = make_issue("TST-1", description)
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                packet = TWEED.build_phase_packet(
                    run_id, issue, TWEED.PHASES["implement"]
                )
                prompt = TWEED.phase_prompt(issue, TWEED.PHASES["implement"], packet)
                manifest_ref = packet["artifact_manifest"]
                manifest_bytes = Path(manifest_ref["path"]).read_bytes()
            self.assertLess(len(prompt.encode()), 8192)
            self.assertNotIn("SENSITIVE-COMPLETE-PAYLOAD", prompt)
            self.assertIn("sha256", prompt)
            self.assertIn("artifacts/sha256", prompt)
            self.assertEqual(
                TWEED.hashlib.sha256(manifest_bytes).hexdigest(),
                manifest_ref["sha256"],
            )

    def test_retry_sync_reuses_artifacts_without_reasoning_or_refetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            state_home = Path(directory) / "runs"
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description("feature", "CSV", root, "CX", run_id)
            issue = make_issue("TST-1", description)
            scope_report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{TWEED.sha256_file(root / 'README.md')}`"
            )
            desired = TWEED.replace_metadata(
                description,
                {**TWEED.parse_metadata(description), "stage": "ready-to-implement", "contract_revision": 1},
            ) + "\n" + TWEED.section_block("scope", scope_report)
            store = Path(directory) / "linear.json"
            trace = Path(directory) / "trace"
            write_fake_linear(store, issue)
            env = {
                "TWEED_STATE_HOME": str(state_home),
                "TWEED_LINEAR_ADAPTER": str(FAKE_ADAPTER),
                "FAKE_LINEAR_STATE": str(store),
                "FAKE_LINEAR_TRACE": str(trace),
            }
            with patch.dict(os.environ, env):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                TWEED.put_artifact(run_id, "linear-desired-description", desired)
                TWEED.save_run(
                    {
                        "run_id": run_id,
                        "state": "sync-pending",
                        "operation": "phase",
                        "phase": "scope",
                        "issue": TWEED.compact_issue(issue),
                        "metadata": TWEED.parse_metadata(description),
                        "repository": str(root),
                        "status": "scoped",
                        "summary": "done",
                        "expected_revision": issue["revision"],
                        "expected_digest": issue["digest"],
                    }
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    result = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
                completed_state = TWEED.load_run(run_id)["state"]
                retry_state = TWEED.load_run(run_id)
                retry_state["state"] = "sync-blocked"
                TWEED.save_run(retry_state)
                with (
                    patch.object(
                        TWEED,
                        "update_linear_issue",
                        side_effect=RuntimeError("offline again"),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as retry_output,
                ):
                    retry_result = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
                retry_saved = TWEED.load_run(run_id)["state"]
            self.assertEqual(result, 0)
            self.assertEqual(trace.read_text().splitlines(), ["compare-and-swap"])
            self.assertEqual(completed_state, "completed")
            self.assertEqual(retry_result, 8)
            self.assertEqual(json.loads(retry_output.getvalue())["state"], "sync-blocked")
            self.assertEqual(retry_saved, "sync-blocked")

    def test_complete_evidence_cache_key_invalidates_each_declared_axis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            dependency = Path(directory) / "lockfile"
            configuration = Path(directory) / "config"
            dependency.write_text("one")
            configuration.write_text("one")
            with patch.dict(os.environ, {"DECLARED_TEST_INPUT": "one"}):
                key, document = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                )
                same, _ = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                )
                self.assertEqual(key, same)
                with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                    TWEED.save_cached_evidence(key, document, {"passed": True})
                    self.assertEqual(
                        TWEED.load_cached_evidence(key, document), {"passed": True}
                    )
                variants = [
                    (["python", "-m", "pytest"], dependency, configuration, "one", {"python": "3.14", "tool": "1"}, ["a" * 64]),
                    (["python", "-m", "unittest"], dependency, configuration, "two", {"python": "3.14", "tool": "1"}, ["a" * 64]),
                    (["python", "-m", "unittest"], dependency, configuration, "one", {"python": "3.14", "tool": "2"}, ["a" * 64]),
                    (["python", "-m", "unittest"], dependency, configuration, "one", {"python": "3.14", "tool": "1"}, ["b" * 64]),
                ]
                for argv, dep, config, env_value, versions, hashes in variants:
                    with patch.dict(os.environ, {"DECLARED_TEST_INPUT": env_value}):
                        changed, _ = TWEED.evidence_cache_key(
                            root, argv, dependency_paths=[dep], configuration_paths=[config],
                            declared_environment=["DECLARED_TEST_INPUT"], tool_versions=versions,
                            artifact_hashes=hashes,
                        )
                    self.assertNotEqual(key, changed)
                dependency.write_text("two")
                changed, _ = TWEED.evidence_cache_key(
                    root, ["python", "-m", "unittest"], dependency_paths=[dependency],
                    configuration_paths=[configuration], declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"}, artifact_hashes=["a" * 64],
                )
                self.assertNotEqual(key, changed)

    def test_evidence_runner_reuses_only_a_complete_matching_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            dependency = Path(directory) / "lock"
            configuration = Path(directory) / "config"
            counter = Path(directory) / "counter"
            dependency.write_text("one")
            configuration.write_text("one")
            script = (
                "from pathlib import Path; p=Path(" + repr(str(counter)) + "); "
                "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
            )
            args = SimpleNamespace(
                repo=str(root),
                evidence_command=[sys.executable, "-c", script],
                tool_version=["python-command=3.14"],
                run_id=None,
                dependency=[str(dependency)],
                configuration=[str(configuration)],
                declared_env=[],
                no_dependencies=False,
                no_configuration=False,
                no_declared_env=True,
                no_artifacts=True,
                timeout=10,
            )
            with patch.dict(os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}):
                with contextlib.redirect_stdout(io.StringIO()) as first:
                    self.assertEqual(TWEED.evidence_command(args), 0)
                with contextlib.redirect_stdout(io.StringIO()) as second:
                    self.assertEqual(TWEED.evidence_command(args), 0)
                dependency.write_text("two")
                with contextlib.redirect_stdout(io.StringIO()) as third:
                    self.assertEqual(TWEED.evidence_command(args), 0)
            self.assertFalse(json.loads(first.getvalue())["cache_hit"])
            self.assertTrue(json.loads(second.getvalue())["cache_hit"])
            self.assertFalse(json.loads(third.getvalue())["cache_hit"])
            self.assertEqual(counter.read_text(), "2")

    def test_evidence_runner_rejects_omitted_or_contradictory_input_axes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            base = {
                "repo": str(root),
                "evidence_command": [sys.executable, "-c", "pass"],
                "tool_version": ["python-command=3.14"],
                "run_id": None,
                "dependency": [],
                "configuration": [],
                "declared_env": [],
                "no_dependencies": False,
                "no_configuration": True,
                "no_declared_env": True,
                "no_artifacts": True,
                "timeout": 10,
            }
            with self.assertRaisesRegex(RuntimeError, "dependency/lockfile"):
                TWEED.evidence_command(SimpleNamespace(**base))
            lock = Path(directory) / "lock"
            lock.write_text("one")
            contradictory = {
                **base,
                "dependency": [str(lock)],
                "no_dependencies": True,
            }
            with self.assertRaisesRegex(RuntimeError, "cannot combine"):
                TWEED.evidence_command(SimpleNamespace(**contradictory))

    def test_evidence_runner_never_caches_timeouts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            counter = Path(directory) / "counter"
            script = (
                "from pathlib import Path; import time; p=Path("
                + repr(str(counter))
                + "); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
                "time.sleep(2)"
            )
            args = SimpleNamespace(
                repo=str(root),
                evidence_command=[sys.executable, "-c", script],
                tool_version=["python-command=3.14"],
                run_id=None,
                dependency=[],
                configuration=[],
                declared_env=[],
                no_dependencies=True,
                no_configuration=True,
                no_declared_env=True,
                no_artifacts=True,
                timeout=0.2,
            )
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                for _ in range(2):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(TWEED.evidence_command(args), 124)
                    self.assertFalse(json.loads(output.getvalue())["cacheable"])
            self.assertEqual(counter.read_text(), "2")

    def test_tracked_unchanged_inputs_reuse_content_hash_by_git_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            lock = root / "lockfile"
            lock.write_text("locked")
            git(root, "add", "lockfile")
            git(root, "commit", "-m", "lock")
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                first = TWEED.cached_input_digest(root, lock)
                with patch.object(
                    TWEED,
                    "sha256_file",
                    side_effect=AssertionError("unchanged file must not be reread"),
                ):
                    second = TWEED.cached_input_digest(root, lock)
            self.assertEqual(first, second)

    def test_legacy_run_migration_preserves_backup_and_imports_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                path = TWEED.state_path(run_id)
                path.parent.mkdir(parents=True)
                old = {"run_id": run_id, "state": "sync-pending", "phase": "scope", "report_markdown": "Status: scoped", "workflow_text": "workflow"}
                path.write_text(json.dumps(old))
                loaded = TWEED.load_run(run_id)
                self.assertEqual(loaded["run_schema_version"], 2)
                self.assertTrue((path.parent / "run.v1.json").exists())
                self.assertEqual(TWEED.read_artifact(run_id, "scope"), b"Status: scoped")

    def test_skill_is_single_invocation_receipt_only_and_handles_all_states(self):
        skill = (ROOT / "skills/use-tweed/SKILL.md").read_text()
        self.assertIn("Run exactly one command", skill)
        self.assertIn("at most 4 KiB", skill)
        for state in ("created", "completed", "awaiting-input", "sync-pending", "sync-blocked", "failed", "resume", "retry-sync"):
            self.assertIn(state, skill)
        self.assertIn("Do not ingest child output", skill)

    def test_efficiency_changes_preserve_review_and_ready_gates(self):
        review = (ROOT / "workflows/review.md").read_text()
        implementation = (ROOT / "workflows/implementation.md").read_text()
        requirements = (ROOT / "REQUIREMENTS.md").read_text()
        for axis in (
            "Simplicity, clarity, reuse, and scope fidelity",
            "Correctness and robustness",
            "Compatibility and integration",
            "Performance and resource use",
            "Verification quality",
        ):
            self.assertIn(axis, review)
        self.assertIn("three baseline axes", implementation)
        self.assertIn("non-authoring reviewer re-reviews", review)
        self.assertIn("zero unresolved material findings", review)
        self.assertIn("Ready-to-merge boundary", requirements)

    def test_no_model_powered_linear_transport_tasks_remain(self):
        source = (ROOT / "tweed").read_text()
        self.assertNotIn("Tweed read ", source)
        self.assertNotIn("Tweed update ", source)
        self.assertNotIn("Exact description snapshot", source)

    def test_cor3270_benchmark_is_immutable_and_fails_on_stable_drift(self):
        script = ROOT / "benchmarks/cor3270_stage1.py"
        fixture_path = ROOT / "benchmarks/fixtures/cor3270.json"
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["stable_replay_matches_fixture"])
        self.assertEqual(result["baseline"]["model_transport_task_count"], 15)
        with tempfile.TemporaryDirectory() as directory:
            fixture = json.loads(fixture_path.read_text())
            fixture["expected_replay"]["totals"]["new_prompt_bytes"] += 1
            drifted = Path(directory) / "fixture.json"
            drifted.write_text(json.dumps(fixture))
            mismatch = subprocess.run(
                [sys.executable, str(script), "--fixture", str(drifted)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn("drifted", mismatch.stderr)

    def test_agent_receipt_is_bounded(self):
        value = TWEED.receipt(
            run_id="tw_0123456789abcdef",
            state="completed",
            issue="ENG-1",
            phase="scope",
            status="scoped",
            summary="x" * 1000,
        )
        output = json.dumps(value, separators=(",", ":")).encode()
        self.assertLessEqual(len(value["summary"]), 400)
        self.assertLess(len(output), 4096)


if __name__ == "__main__":
    unittest.main()
