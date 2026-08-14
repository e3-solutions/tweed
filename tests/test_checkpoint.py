import json
import os
import stat
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import bonaparte_checkpoint as checkpoint

TOKEN = "01234567-89ab-4def-8123-456789abcdef"


def semantic(**overrides):
    value = {
        "stage": "waiting-input",
        "actor": "coordinator",
        "activity": "lifecycle",
        "status": "waiting",
        "count": 1,
    }
    value.update(overrides)
    return value


def record(status="waiting-input", **overrides):
    value = {
        "version": checkpoint.VERSION,
        "token": TOKEN,
        "status": status,
        "phase": "rca",
        "soft_phase_budget_seconds": 300.0,
        "worktree": "/tmp/worktree",
        "git_dir": "/tmp/repository/.git",
        "base_head": "a" * 40,
        "identity_head": "a" * 40,
        "model": None,
        "reasoning": "medium",
        "question": "Was the subscription active?",
        "pending_answer": None,
        "receipt": {"phase": "rca", "state": "needs-input"},
        "branch": "arya/example",
        "files_changed": [{"path": "README.md", "status": " M"}],
        "files_changed_total_count": 1,
        "files_changed_truncated": False,
        "checks_completed": ["git status --short"],
        "checks_completed_total_count": 1,
        "checks_completed_truncated": False,
        "activity": "waiting for incident identity",
        "blocker": "environment is user-only information",
        "remote_state_changed": None,
        "updated_at": "2026-08-13T18:00:00+00:00",
        "semantic": semantic(),
        "semantic_milestones": [semantic(status="started")],
        "semantic_milestones_total_count": 1,
        "semantic_milestones_truncated": False,
    }
    value.update(overrides)
    return value


class PathTests(unittest.TestCase):
    def test_home_resolution_supports_installed_releases_and_dev_overrides(self):
        self.assertEqual(
            checkpoint.bonaparte_home(
                "/data/bonaparte/releases/v1.2.3/bonaparte_checkpoint.py",
                {"BONAPARTE_HOME": "/ignored"},
            ),
            Path("/data/bonaparte"),
        )
        self.assertEqual(
            checkpoint.bonaparte_home(
                "/code/tweed/bonaparte_checkpoint.py",
                {"BONAPARTE_HOME": "/configured"},
            ),
            Path("/configured"),
        )
        self.assertEqual(
            checkpoint.bonaparte_home(
                "/code/tweed/bonaparte_checkpoint.py",
                {"HOME": "/users/a", "XDG_DATA_HOME": "/xdg"},
            ),
            Path("/xdg/bonaparte"),
        )

    def test_tokens_are_canonical(self):
        self.assertEqual(checkpoint.canonical_token(TOKEN), TOKEN)
        for value in (TOKEN.upper(), TOKEN.replace("-", ""), "../escape", None):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                checkpoint.canonical_token(value)


class ValidationTests(unittest.TestCase):
    def test_active_and_terminal_status_envelopes_are_accepted(self):
        for status in checkpoint.STATUSES:
            value = record(status)
            if status != "waiting-input":
                value["question"] = None
            with self.subTest(status=status):
                self.assertIs(checkpoint.validate(value), value)

    def test_envelope_is_exact_and_safety_relevant_types_are_strict(self):
        invalid = []
        missing = record()
        del missing["worktree"]
        invalid.append(missing)
        invalid.append({**record(), "extra": True})
        invalid.append(record(version=True))
        invalid.append(record(status="running"))
        invalid.append(record(status=[]))
        invalid.append(record(phase="unknown"))
        invalid.append(record(phase=[]))
        invalid.append(record(receipt=[]))
        invalid.append(record(git_dir=None))
        invalid.append(record(remote_state_changed="unknown"))
        invalid.append(record(files_changed_total_count=True))
        invalid.append(record(files_changed_total_count=2))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                checkpoint.validate(value)

    def test_waiting_input_requires_question(self):
        with self.assertRaisesRegex(RuntimeError, "question"):
            checkpoint.validate(record(question=None))

    def test_soft_phase_budget_accepts_only_positive_finite_numbers(self):
        for budget in (1, 0.25, 300.0):
            with self.subTest(budget=budget):
                value = record(soft_phase_budget_seconds=budget)
                self.assertIs(checkpoint.validate(value), value)

        invalid = (
            True,
            False,
            0,
            -1,
            float("inf"),
            float("-inf"),
            float("nan"),
            "300",
            None,
        )
        for budget in invalid:
            with self.subTest(budget=budget), self.assertRaisesRegex(
                RuntimeError, "positive finite"
            ):
                checkpoint.validate(record(soft_phase_budget_seconds=budget))

    def test_semantic_state_accepts_only_fixed_typed_values(self):
        accepted = (
            semantic(actor=None, activity=None, status=None, count=None),
            semantic(actor="subagent-27", stage="checking", activity="check"),
        )
        for item in accepted:
            with self.subTest(item=item):
                checkpoint.validate(record(semantic=item))

        invalid = (
            semantic(stage="reading /private/secret"),
            semantic(stage=[]),
            semantic(actor="subagent-secret"),
            semantic(actor=f"subagent-{checkpoint.MAX_SEMANTIC_COUNT + 1}"),
            semantic(activity="query=user@example.com"),
            semantic(activity=[]),
            semantic(status="ran command"),
            semantic(status=[]),
            semantic(count=True),
            semantic(count=-1),
            semantic(count=checkpoint.MAX_SEMANTIC_COUNT + 1),
            {**semantic(), "message": "secret"},
        )
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(RuntimeError):
                checkpoint.validate(record(semantic=item))

    def test_semantic_milestones_are_bounded_and_have_consistent_metadata(self):
        milestone = semantic(stage="checking", activity="check")
        invalid = (
            record(
                semantic_milestones=[milestone]
                * (checkpoint.MAX_SEMANTIC_MILESTONES + 1),
                semantic_milestones_total_count=(
                    checkpoint.MAX_SEMANTIC_MILESTONES + 1
                ),
            ),
            record(semantic_milestones_total_count=0),
            record(semantic_milestones_total_count=True),
            record(semantic_milestones_total_count=2),
            record(semantic_milestones_truncated="yes"),
            record(
                semantic_milestones=[semantic(activity="contains secret")]
            ),
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                checkpoint.validate(value)

        truncated = record(
            semantic_milestones_total_count=50,
            semantic_milestones_truncated=True,
        )
        self.assertIs(checkpoint.validate(truncated), truncated)

    def test_serialized_envelope_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, "1 MiB"):
            checkpoint.validate(record(pending_answer="x" * checkpoint.MAX_BYTES))


class PersistenceTests(unittest.TestCase):
    def test_v1_checkpoint_is_read_and_normalized_to_current_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = record()
            for field in set(legacy) - checkpoint.V1_FIELDS:
                del legacy[field]
            legacy["version"] = 1
            path = checkpoint.checkpoint_path(TOKEN, home)
            path.write_text(json.dumps(legacy))

            normalized = checkpoint.read_checkpoint(TOKEN, home)
            self.assertEqual(normalized["version"], checkpoint.VERSION)
            self.assertEqual(
                normalized["soft_phase_budget_seconds"],
                checkpoint.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
            )
            self.assertIsNone(normalized["semantic"])
            self.assertEqual(normalized["semantic_milestones"], [])
            self.assertEqual(normalized["semantic_milestones_total_count"], 0)
            self.assertFalse(normalized["semantic_milestones_truncated"])

            checkpoint.write_checkpoint(normalized, home)
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["version"], checkpoint.VERSION)
            self.assertEqual(
                persisted["soft_phase_budget_seconds"],
                checkpoint.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
            )

    def test_v2_checkpoint_is_read_and_normalized_to_default_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = record()
            del legacy["soft_phase_budget_seconds"]
            legacy["version"] = 2
            path = checkpoint.checkpoint_path(TOKEN, home)
            path.write_text(json.dumps(legacy))

            normalized = checkpoint.read_checkpoint(TOKEN, home)

            self.assertEqual(normalized["version"], checkpoint.VERSION)
            self.assertEqual(
                normalized["soft_phase_budget_seconds"],
                checkpoint.DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
            )

    def test_configured_budget_survives_atomic_round_trip_and_lease_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            configured = record(soft_phase_budget_seconds=42.5)

            with checkpoint.checkpoint_lease(TOKEN, home):
                path = checkpoint.write_checkpoint(configured, home)
                self.assertEqual(
                    checkpoint.read_checkpoint(TOKEN, home)[
                        "soft_phase_budget_seconds"
                    ],
                    42.5,
                )

            with checkpoint.checkpoint_lease(TOKEN, home):
                self.assertEqual(
                    json.loads(path.read_text())["soft_phase_budget_seconds"],
                    42.5,
                )

    def test_atomic_round_trip_permissions_and_fsync(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with mock.patch.object(checkpoint.os, "fsync", wraps=os.fsync) as fsync:
                path = checkpoint.write_checkpoint(record(), home)
            self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertEqual(checkpoint.read_checkpoint(TOKEN, home), record())
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])

            replacement = record(activity="answer recorded")
            path.chmod(0o666)
            checkpoint.write_checkpoint(replacement, home)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(checkpoint.read_checkpoint(TOKEN, home), replacement)

    def test_read_is_bounded_and_validates_token_and_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = checkpoint.checkpoint_path(TOKEN, home)
            path.write_bytes(b"x" * (checkpoint.MAX_BYTES + 1))
            with self.assertRaisesRegex(RuntimeError, "1 MiB"):
                checkpoint.read_checkpoint(TOKEN, home)

            path.write_text(json.dumps(record(token=str(uuid.uuid4()))))
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                checkpoint.read_checkpoint(TOKEN, home)

            path.write_text("not JSON")
            with self.assertRaisesRegex(RuntimeError, "JSON"):
                checkpoint.read_checkpoint(TOKEN, home)

    def test_active_read_accepts_only_waiting_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint.write_checkpoint(record(), temporary)
            self.assertEqual(
                checkpoint.read_checkpoint(TOKEN, temporary, active_only=True)[
                    "status"
                ],
                "waiting-input",
            )
            checkpoint.write_checkpoint(
                record("completed", question=None),
                temporary,
            )
            with self.assertRaisesRegex(RuntimeError, "no longer waiting"):
                checkpoint.read_checkpoint(TOKEN, temporary, active_only=True)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires O_NOFOLLOW")
    def test_symlinks_are_never_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            victim = home / "victim"
            victim.write_text("do not follow")

            directory = home / "checkpoints"
            directory.symlink_to(home)
            with self.assertRaises(RuntimeError):
                checkpoint.checkpoint_directory(home)
            directory.unlink()
            directory = checkpoint.checkpoint_directory(home)

            path = directory / f"{TOKEN}.json"
            path.symlink_to(victim)
            with self.assertRaises(RuntimeError):
                checkpoint.read_checkpoint(TOKEN, home)
            checkpoint.write_checkpoint(record(), home)
            self.assertEqual(victim.read_text(), "do not follow")
            self.assertEqual(checkpoint.read_checkpoint(TOKEN, home), record())

            path.unlink()
            lock = directory / f"{TOKEN}.lock"
            lock.symlink_to(victim)
            with self.assertRaises(RuntimeError):
                with checkpoint.checkpoint_lease(TOKEN, home):
                    pass

    def test_lease_is_private_nonblocking_and_reusable(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with checkpoint.checkpoint_lease(TOKEN, home):
                lock = home / "checkpoints" / f"{TOKEN}.lock"
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with checkpoint.checkpoint_lease(TOKEN, home):
                        pass
            with checkpoint.checkpoint_lease(TOKEN, home):
                pass


if __name__ == "__main__":
    unittest.main()
