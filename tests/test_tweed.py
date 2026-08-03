from __future__ import annotations

import importlib.machinery
import importlib.util
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

    def test_sync_reconciliation_accepts_only_matching_transition_and_section(self):
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
                        "description": TWEED.replace_section(
                            desired,
                            "scope",
                            result["report_markdown"]
                            .replace("- [Docs]", "* [Docs]")
                            .replace(
                                "](https://example.com/docs)",
                                "](<https://example.com/docs>)",
                            )
                            .replace("\n\n2. Two", "\n2. Two"),
                        )
                        + "\n\n",
                    },
                )
            )
            changed = TWEED.replace_section(desired, "scope", "Status: scoped\n\nWrong")
            self.assertFalse(
                TWEED.phase_sync_already_landed(
                    state, {**issue, "description": changed}
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
                self.assertEqual(
                    (path.parent / "report.md").stat().st_mode & 0o777, 0o600
                )

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
