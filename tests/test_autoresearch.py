import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_autoresearch():
    loader = importlib.machinery.SourceFileLoader("autoresearch_module", str(ROOT / "autoresearch"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


AR = load_autoresearch()
OID = "a" * 40
TREE = "b" * 40


def valid_spec(repository="/tmp/source"):
    return {
        "schema_version": 1,
        "goal": "make it faster",
        "repository": {"path": repository, "source_oid": OID, "baseline_oid": OID},
        "paths": {"allowed": ["src"], "protected": ["fixtures"]},
        "evaluator": {"argv": ["python3", "evaluate.py"], "direction": "min", "timeout_seconds": 10, "max_output_bytes": 4096},
        "sandbox": {"wrapper_argv": ["sandbox"], "capabilities": ["filesystem", "process", "network-denied"]},
        "budgets": {"attempts": 4, "concurrency": 2, "wall_seconds": 60, "process_seconds": 20, "artifact_bytes": 100000},
        "search": {"directions": ["algorithm", "allocation"], "adversarial_direction": "regression hunt", "target": None, "patience": 2, "min_improvement": 0.1},
        "provenance": {"created_by": "codex", "created_at": "2026-08-08T00:00:00Z"},
    }


class SchemaTests(unittest.TestCase):
    def test_valid_spec_and_closed_objects(self):
        value = valid_spec()
        self.assertIs(AR.validate_spec(value), value)
        for mutate in (
            lambda value: value.update(extra=True),
            lambda value: value["budgets"].update(attempts=0),
            lambda value: value["evaluator"].update(direction="sideways"),
            lambda value: value["sandbox"].update(capabilities=["filesystem"]),
            lambda value: value["search"].update(adversarial_direction="algorithm"),
        ):
            value = valid_spec(); mutate(value)
            with self.subTest(value=value), self.assertRaises(AR.ValidationError): AR.validate_spec(value)

    def test_path_boundaries_reject_absolute_traversal_and_overlap(self):
        for allowed, protected in ((["/src"], []), (["../src"], []), (["src", "src/lib"], []), (["src"], ["src/generated"]), (["src"], ["src"])):
            with self.subTest(allowed=allowed, protected=protected), self.assertRaises(AR.ValidationError): AR.validate_prefixes(allowed, protected)

    def test_argv_is_an_array_not_shell_text(self):
        for value in ("make test", [], ["make", ""]):
            with self.assertRaises(AR.ValidationError): AR.validate_argv(value)

    def test_state_inside_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"; source.mkdir()
            spec = valid_spec(str(source)); state = source / "state"; state.mkdir()
            with self.assertRaisesRegex(AR.ValidationError, "must not be inside"): AR.validate_spec(spec, spec_path=state / "spec.json")


class EvaluatorTests(unittest.TestCase):
    def test_exact_protocol(self):
        self.assertEqual(AR.parse_evaluator_output('{"metric":1.25,"constraints":{"tests":true}}')["metric"], 1.25)
        invalid = (
            '{"metric":1,"constraints":{"tests":true},"extra":1}',
            '{"metric":NaN,"constraints":{"tests":true}}',
            '{"metric":1,"constraints":{}}',
            '{"metric":1,"constraints":{"tests":1}}',
            '{} trailing',
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(AR.ValidationError): AR.parse_evaluator_output(value)

    def test_improvement_and_stable_rank(self):
        self.assertTrue(AR.is_better(8, 10, "min", 1))
        self.assertFalse(AR.is_better(9.5, 10, "min", 1))
        attempts = [{"attempt_id": 2, "metric": 3}, {"attempt_id": 1, "metric": 3}, {"attempt_id": 3, "metric": 2}]
        self.assertEqual([x["attempt_id"] for x in AR.stable_rank(attempts, "min")], [3, 1, 2])
        self.assertEqual([x["attempt_id"] for x in AR.stable_rank(attempts, "max")], [1, 2, 3])

    def test_deterministic_scheduler_reserves_adversarial_attempt(self):
        self.assertEqual(AR.schedule_directions(valid_spec()), ["algorithm", "allocation", "algorithm", "regression hunt"])


class ReceiptAndReplayTests(unittest.TestCase):
    def binding(self):
        return {"run_id": "run", "attempt_id": 1, "direction": "a", "generation": 1, "baseline_oid": OID, "parent_tree": TREE, "lease": "lease", "deadline": 100.0}

    def receipt(self):
        return {"schema_version": 1, **self.binding(), "status": "completed", "summary": "done"}

    def test_stale_or_duplicate_binding_is_rejected(self):
        AR.validate_binding(self.receipt(), self.binding())
        for key, replacement in (("run_id", "old"), ("lease", "old"), ("generation", 2), ("parent_tree", OID)):
            value = self.receipt(); value[key] = replacement
            with self.subTest(key=key), self.assertRaisesRegex(AR.ValidationError, "binding"): AR.validate_binding(value, self.binding())
        value = self.receipt(); value["extra"] = True
        with self.assertRaises(AR.ValidationError): AR.validate_binding(value, self.binding())

    def test_event_replay_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); log = AR.EventLog(root, "run")
            log.append("first", {"n": 1}); log.append("second", {"n": 2})
            self.assertEqual(len(log.replay()), 2)
            path = root / "events/00000001.json"; value = json.loads(path.read_text()); value["payload"]["n"] = 9; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(AR.ValidationError, "tamper"): log.replay()

    def test_double_lock_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with AR.RunLock(root):
                with self.assertRaisesRegex(RuntimeError, "already locked"):
                    with AR.RunLock(root): pass


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.repo = self.root / "repo"; self.repo.mkdir()
        self.git("init", "-q"); self.git("config", "user.name", "Test"); self.git("config", "user.email", "test@example.com")
        (self.repo / "src").mkdir(); (self.repo / "fixtures").mkdir()
        (self.repo / "src/value.txt").write_text("one\n"); (self.repo / "fixtures/input.txt").write_text("fixed\n")
        self.git("add", "."); self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def test_clone_and_candidate_capture_leave_source_unchanged(self):
        oid, _ = AR.repository_facts(self.repo); before = AR.tree_digest(self.repo)
        candidate = self.root / "candidate"; AR.materialize(self.repo, candidate, oid)
        (candidate / "src/value.txt").write_bytes(b"two\x00binary")
        self.assertEqual(AR.inspect_candidate(candidate, oid, ["src"], ["fixtures"]), ["src/value.txt"])
        self.assertEqual(before, AR.tree_digest(self.repo)); self.assertEqual(AR.repository_facts(self.repo)[0], oid)

    def test_protected_and_special_changes_are_rejected(self):
        oid, _ = AR.repository_facts(self.repo); candidate = self.root / "candidate"; AR.materialize(self.repo, candidate, oid)
        (candidate / "fixtures/input.txt").write_text("changed")
        with self.assertRaisesRegex(AR.ValidationError, "protected"): AR.inspect_candidate(candidate, oid, ["src"], ["fixtures"])
        self.git("status", "--porcelain")


class SetupTests(unittest.TestCase):
    def test_setup_command_has_fresh_read_only_flags(self):
        command = AR.setup_command(Path("/repo"), Path("/state"), "goal", "/bin/codex")
        self.assertEqual(command[:2], ["/bin/codex", "exec"])
        for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertNotIn("resume", command)

    def test_bounded_process_output_and_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(RuntimeError): AR.run_bounded(["python3", "-c", "print('x'*100)"], cwd=root, timeout=2, max_output=10)
            with self.assertRaises(TimeoutError): AR.run_bounded(["python3", "-c", "import time; time.sleep(2)"], cwd=root, timeout=.05, max_output=10)


if __name__ == "__main__":
    unittest.main()
