import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time
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
        "evaluator": {
            "argv": ["python3", "fixtures/evaluate.py"],
            "baseline_argv": ["python3", "fixtures/evaluate.py"],
            "check_argv": ["python3", "fixtures/check.py"],
            "constraint_names": ["tests"],
            "immutable_inputs": ["fixtures/evaluate.py", "fixtures/check.py"],
            "direction": "min",
            "timeout_seconds": 10,
            "max_output_bytes": 4096,
        },
        "sandbox": {"wrapper_argv": ["sandbox"], "capabilities": ["filesystem-contained", "process-contained", "network-denied"]},
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

        with self.assertRaisesRegex(AR.ValidationError, "constraint keys"):
            AR.parse_evaluator_output('{"metric":1,"constraints":{"other":true}}', ["tests"])

    def test_improvement_and_stable_rank(self):
        self.assertTrue(AR.is_better(8, 10, "min", 1))
        self.assertFalse(AR.is_better(9.5, 10, "min", 1))
        attempts = [{"attempt_id": 2, "metric": 3}, {"attempt_id": 1, "metric": 3}, {"attempt_id": 3, "metric": 2}]
        self.assertEqual([x["attempt_id"] for x in AR.stable_rank(attempts, "min")], [3, 1, 2])
        self.assertEqual([x["attempt_id"] for x in AR.stable_rank(attempts, "max")], [1, 2, 3])

    def test_deterministic_scheduler_reserves_adversarial_attempt(self):
        self.assertEqual(AR.schedule_directions(valid_spec()), ["algorithm", "allocation", "algorithm", "regression hunt"])
        self.assertEqual(
            AR.schedule_directions(valid_spec(), winner_direction="allocation", used=2, count=2),
            ["allocation", "regression hunt"],
        )
        self.assertEqual(
            AR.schedule_directions(valid_spec(), winner_direction="allocation", used=2, count=1, limit=3),
            ["regression hunt"],
        )


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

    def test_critic_boolean_and_objection_are_biconditional(self):
        base = {"schema_version": 1, "run_id": "run", "attempt_id": 1, "lease": "lease", "summary": ""}
        for supported, objection in ((False, "material"), (True, "")):
            with self.subTest(supported=supported), self.assertRaisesRegex(AR.ValidationError, "exactly when"):
                AR.validate_binding({**base, "supported": supported, "objection": objection}, self.binding(), critic=True)
        AR.validate_binding({**base, "supported": False, "objection": ""}, self.binding(), critic=True)

    def test_event_replay_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); log = AR.EventLog(root, "run")
            log.append("first", {"n": 1}); log.append("second", {"n": 2})
            self.assertEqual(len(log.replay()), 2)
            path = root / "events/00000001.json"; value = json.loads(path.read_text()); value["payload"]["n"] = 9; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(AR.ValidationError, "tamper"): log.replay()

    def test_reconstruct_rejects_patch_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); patch = root / "evidence/00000001.patch"; patch.parent.mkdir()
            digest = AR.exclusive_bytes(patch, b"patch")
            log = AR.EventLog(root, "run")
            spec = valid_spec()
            log.append("run-started", {"spec_digest": AR.digest_json(spec), "started_epoch": time.time()})
            record = {"attempt_id": 1, "patch": str(patch), "patch_digest": digest, "metric": 1, "constraints": {"tests": True}, "tree": TREE, "direction": "algorithm", "binding": self.binding()}
            log.append("attempt-verified", record, 1)
            patch.write_bytes(b"tampered")
            with self.assertRaisesRegex(AR.ValidationError, "patch artifact tamper"):
                AR.reconstruct_state(log.replay(), root, spec)

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

    def test_candidate_score_uses_baseline_owned_evaluator_assets(self):
        oid, _ = AR.repository_facts(self.repo)
        # Add a complete baseline evaluator contract.
        evaluator = "import json\nprint(json.dumps({'metric':1,'constraints':{'tests':True}}))\n"
        (self.repo / "fixtures/evaluate.py").write_text(evaluator); (self.repo / "fixtures/check.py").write_text(evaluator)
        self.git("add", "."); self.git("commit", "-qm", "evaluator"); oid = self.git("rev-parse", "HEAD").stdout.strip()
        spec = valid_spec(str(self.repo)); spec["repository"].update(source_oid=oid, baseline_oid=oid)
        spec["sandbox"] = {"wrapper_argv": ["env"], "capabilities": ["filesystem-contained", "process-contained", "network-denied"]}
        control, baseline = self.root / "control", self.root / "baseline"
        AR.materialize(self.repo, control, oid); AR.export_index(control, baseline)
        (control / "fixtures/evaluate.py").write_text("raise SystemExit('candidate self-score')")
        AR.git(control, "add", "fixtures/evaluate.py")
        budget = AR.RunBudget(time.time(), 10, 1_000_000, self.root)
        score = AR.evaluate_tree(spec, control, baseline, self.root, budget)
        self.assertEqual(score["metric"], 1.0)


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
            started = time.monotonic()
            with self.assertRaises(RuntimeError): AR.run_bounded(["python3", "-c", "import sys,time;sys.stdout.write('x'*10000);sys.stdout.flush();time.sleep(3)"], cwd=root, timeout=2, max_output=10)
            self.assertLess(time.monotonic() - started, 1)
            with self.assertRaises(TimeoutError): AR.run_bounded(["python3", "-c", "import time; time.sleep(2)"], cwd=root, timeout=.05, max_output=10)

    def test_canonical_prompts_are_loaded(self):
        self.assertIn("# Autoresearch Setup", AR.workflow_prompt("setup"))
        self.assertIn("# Autoresearch Worker", AR.workflow_prompt("worker"))
        self.assertIn("# Autoresearch Critic", AR.workflow_prompt("critic"))

    def test_persisted_wall_and_artifact_budgets_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expired = AR.RunBudget(time.time() - 2, 1, 1000, root)
            with self.assertRaises(AR.BudgetExceeded): expired.remaining()
            (root / "events").mkdir(); (root / "events/a").write_bytes(b"x" * 20)
            with self.assertRaises(AR.BudgetExceeded): AR.RunBudget(time.time(), 10, 10, root).check_artifacts()

    def test_capability_probe_rejects_claim_without_active_denial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); spec = valid_spec()
            result = subprocess.CompletedProcess([], 0, b"read\n", b"")
            with mock.patch.object(AR, "run_bounded", return_value=result):
                with self.assertRaisesRegex(AR.ValidationError, "capability probe"):
                    AR.capability_probe(spec, root, AR.RunBudget(time.time(), 10, 100000, root))


class ControllerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.repo = self.root / "source"; self.repo.mkdir()
        self.git("init", "-q"); self.git("config", "user.name", "Test"); self.git("config", "user.email", "test@example.com")
        (self.repo / "src").mkdir(); (self.repo / "fixtures").mkdir()
        (self.repo / "src/value.txt").write_text("10\n")
        evaluator = "import json,pathlib\nn=int(pathlib.Path('src/value.txt').read_text())\nprint(json.dumps({'metric':n,'constraints':{'tests':True}},separators=(',',':')))\n"
        (self.repo / "fixtures/evaluate.py").write_text(evaluator)
        (self.repo / "fixtures/check.py").write_text(evaluator)
        self.git("add", "."); self.git("commit", "-qm", "baseline")
        self.oid = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def spec(self):
        value = valid_spec(str(self.repo)); value["repository"].update(source_oid=self.oid, baseline_oid=self.oid)
        value["sandbox"] = {"wrapper_argv": ["env"], "capabilities": ["filesystem-contained", "process-contained", "network-denied"]}
        value["budgets"].update(attempts=4, concurrency=2, wall_seconds=30, process_seconds=5, artifact_bytes=5_000_000)
        value["search"].update(patience=4, min_improvement=0.1)
        return value

    @staticmethod
    def _assignment(prompt, marker):
        return json.loads(prompt.split(marker, 1)[1])

    def fake_processes(self, reverse=False, failed_attempt=None, calls=None):
        original = AR.run_bounded
        calls = calls if calls is not None else []

        def fake(command, **kwargs):
            if command[0] != "codex":
                return original(command, **kwargs)
            prompt = kwargs["input_text"]
            output = Path(command[command.index("--output-last-message") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if "# Controller assignment\n" in prompt:
                assignment = self._assignment(prompt, "# Controller assignment\n")
                binding = assignment["binding"]; attempt = binding["attempt_id"]
                calls.append(("worker", attempt, binding["direction"]))
                # Force opposite completion orders while retaining identical candidates.
                if (attempt == 1) == reverse:
                    time.sleep(0.08)
                status = "failed" if attempt == failed_attempt else "completed"
                (Path(kwargs["cwd"]) / "src/value.txt").write_text(f"{max(1, 10 - attempt)}\n")
                receipt = {"schema_version": 1, **binding, "status": status, "summary": status}
            else:
                assignment = self._assignment(prompt, "# Closed controller evidence\n")
                binding = assignment["binding"]; calls.append(("critic", binding["attempt_id"], assignment["final"]))
                receipt = {"schema_version": 1, **binding, "supported": False, "objection": "", "summary": "clear"}
            output.write_text(json.dumps(receipt))
            return subprocess.CompletedProcess(command, 0, b"", b"")

        return fake

    def run_once(self, name, reverse=False, failed_attempt=None):
        state = self.root / name; spec_path = self.root / f"{name}.json"; spec_path.write_text(json.dumps(self.spec()))
        calls = []
        with (
            mock.patch.object(AR, "capability_probe"),
            mock.patch.object(AR, "run_bounded", side_effect=self.fake_processes(reverse, failed_attempt, calls)),
        ):
            result = AR.run_controller(spec_path, state)
        return state, spec_path, result, calls

    def test_reversed_completion_order_has_same_serialized_promotions_and_final_replay(self):
        first, _, result_one, calls_one = self.run_once("one", reverse=False)
        second, _, result_two, calls_two = self.run_once("two", reverse=True)
        self.assertEqual(result_one["best_metric"], result_two["best_metric"])
        self.assertEqual(result_one["best_attempt_id"], result_two["best_attempt_id"])
        promotions = []
        for state in (first, second):
            events = AR.EventLog(state, json.loads((state / "events/00000001.json").read_text())["run_id"]).replay()
            promotions.append([event["attempt_id"] for event in events if event["kind"] == "promotion"])
            kinds = [event["kind"] for event in events]
            self.assertIn("final-critic", kinds); self.assertEqual(kinds[-1], "run-completed")
            self.assertEqual(AR.file_digest(Path(json.loads((state / "result.json").read_text())["patch"])), json.loads((state / "result.json").read_text())["patch_digest"])
        self.assertEqual(promotions[0], promotions[1])
        self.assertTrue(any(call[0] == "critic" and call[2] for call in calls_one))

    def test_failed_worker_receipt_is_rejected_before_capture(self):
        state, _, _, _ = self.run_once("failed", failed_attempt=1)
        events = AR.EventLog(state, json.loads((state / "events/00000001.json").read_text())["run_id"]).replay()
        rejection = [event for event in events if event["kind"] == "attempt-rejected" and event["attempt_id"] == 1]
        self.assertEqual(len(rejection), 1); self.assertIn("reported failed", rejection[0]["payload"]["reason"])
        self.assertFalse((state / "evidence/00000001.patch").exists())

    def test_resume_ignores_torn_mutable_files_and_detects_patch_tamper(self):
        state, _, result, _ = self.run_once("resume")
        (state / "checkpoint.json").write_text("torn")
        (state / "result.json").write_text("torn")
        with mock.patch.object(AR, "capability_probe"):
            resumed = AR.run_controller(state / "spec.json", state, resume=True)
        self.assertEqual(resumed, result)
        patch = Path(result["patch"]); patch.write_bytes(patch.read_bytes() + b"tamper")
        with self.assertRaisesRegex(AR.ValidationError, "patch artifact tamper"):
            AR.run_controller(state / "spec.json", state, resume=True)

    def test_crash_after_final_critic_reuses_immutable_receipt(self):
        state, _, result, _ = self.run_once("crash")
        events = sorted((state / "events").glob("*.json")); self.assertEqual(json.loads(events[-1].read_text())["kind"], "run-completed")
        events[-1].unlink(); (state / "result.json").unlink(); Path(result["patch"]).unlink()
        calls = []
        with (
            mock.patch.object(AR, "capability_probe"),
            mock.patch.object(AR, "run_bounded", side_effect=self.fake_processes(calls=calls)),
        ):
            resumed = AR.run_controller(state / "spec.json", state, resume=True)
        self.assertEqual(resumed["status"], "completed")
        self.assertFalse(any(call[0] == "critic" for call in calls), calls)


if __name__ == "__main__":
    unittest.main()
