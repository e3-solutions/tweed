"""Dependency/frontier behavior through the public CLI and real Git captures."""
import copy
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import sys
import tempfile
import threading
import unittest

from support import SCRIPT, load_confidence

confidence = load_confidence("dependency_frontier_fixtures")


class DependencyFrontierTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="confidence-frontier-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.directory = self.root / ".confidence"
        self.directory.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("GIT_", "CONFIDENCE_"))}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, env=self.env)
        (self.root / "source.txt").write_text("stable source\n")
        subprocess.run(["git", "-C", str(self.root), "add", "source.txt"], check=True, env=self.env)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                       check=True, env=self.env)
        self.contract = confidence.initial_contract("Proof frontier", "standard", "feature")
        self.contract["intent"].update(goal="Respect validated prerequisites.",
            must_happen=["Current upstream proof enables dependent proof."],
            must_not_happen=["Invalid upstream proof enables dependent proof."])
        self.contract["proof_obligations"] = [
            {"id": "P1", "claim": "Upstream behavior", "verification": "Verify upstream"},
            {"id": "P2", "claim": "Dependent behavior", "verification": "Verify dependent",
             "depends_on": ["P1"]},
            {"id": "P3", "claim": "Transitive behavior", "verification": "Verify transitive",
             "depends_on": ["P2"]},
            {"id": "P4", "claim": "Independent behavior", "verification": "Verify independent"},
        ]
        self.report = confidence.initial_report("Proof frontier", "standard")
        self.report.update(outcome="Proof remains in progress.", rollback="Not applicable")
        self.report["simplicity"]["notes"] = "Both gates remain pending."
        self.report["review"]["reason"] = "Reversible fixture behavior."
        self.report["evidence"] = [self.result(item["id"]) for item in self.contract["proof_obligations"]]
        self.save()

    def result(self, ident, status="not_run", runs=None):
        return {"obligation_id": ident, "status": status, "details": "Explicit fixture judgment",
                "run_ids": runs or [], "diagnostic_run_ids": [], "artifacts": []}

    def save(self):
        confidence.write_json(self.directory / "contract.json", self.contract)
        confidence.write_json(self.directory / "report.json", self.report)

    def cli(self, action, *arguments, directory=None, env=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), action,
            "--directory", str(directory or self.directory), *arguments],
            capture_output=True, text=True, timeout=20, env=env or self.env)

    def frontier(self):
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        return json.loads(response.stdout)

    def capture(self, ident="support"):
        response = self.cli("run", "--json", "--id", ident, "--cwd", str(self.root),
            "--", sys.executable, "-B", "-c", "print('independent fixture command')")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertEqual(json.loads(response.stdout)["exit_code"], 0)
        return ident

    def record(self, ident, status="pass", run="support", details="Explicit proof"):
        arguments = ["--obligation", ident, "--status", status, "--details", details]
        if run:
            arguments += ["--run", run]
        return self.cli("record", *arguments)

    def current(self):
        return confidence.read_json(self.directory / "report.json")

    def test_frontier_roots_and_blockers_follow_contract_order(self):
        observed = self.frontier()
        self.assertEqual(observed["ready"], ["P1", "P4"])
        self.assertEqual(observed["blocked"], [
            {"obligation_id": "P2", "depends_on": ["P1"]},
            {"obligation_id": "P3", "depends_on": ["P2"]}])
        self.assertFalse(observed["complete"])
        self.assertTrue(observed["completion_errors"])

    def test_frontier_repeated_json_is_identical_and_writes_no_files(self):
        def inventory():
            return {str(path.relative_to(self.root)): path.read_bytes()
                    for path in self.root.rglob("*") if path.is_file()}
        before = inventory()
        first = self.cli("next", "--json")
        second = self.cli("next", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(inventory(), before)
        self.assertFalse((self.directory / "telemetry").exists())

    def test_missing_directory_error_does_not_create_directory_or_telemetry(self):
        missing = self.root / "missing"
        response = self.cli("next", "--json", directory=missing)
        self.assertEqual(response.returncode, 1, response.stderr)
        self.assertFalse(json.loads(response.stdout)["ok"])
        self.assertFalse(missing.exists())

    def test_read_only_frontier_sends_no_enabled_remote_telemetry(self):
        requests = []
        class Observer(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
            def log_message(self, *arguments):
                pass
        server = HTTPServer(("127.0.0.1", 0), Observer)
        observer = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        observer.start()
        try:
            env = dict(self.env, CONFIDENCE_TELEMETRY_ENDPOINT=
                       f"http://127.0.0.1:{server.server_port}/observe")
            for directory in (self.directory, self.root / "missing"):
                response = self.cli("next", "--json", directory=directory, env=env)
                self.assertIn(response.returncode, (0, 1), response.stderr)
            self.assertEqual(requests, [])
            self.assertFalse((self.directory / "telemetry").exists())
            self.assertFalse((self.root / "missing").exists())
        finally:
            server.shutdown()
            observer.join(timeout=2)
            server.server_close()

    def test_frontier_never_executes_verification_text(self):
        sentinel = self.root / "executed"
        self.contract["proof_obligations"][0]["verification"] = f"touch {sentinel}; $(touch {sentinel})\n"
        self.save()
        self.assertIn("P1", self.frontier()["ready"])
        self.assertFalse(sentinel.exists())

    def test_malformed_dependency_contract_refuses_without_partial_readiness(self):
        for malformed in (None, "P1", {}, [None], [""], ["P1", "P1"], ["missing"], ["P2"]):
            with self.subTest(depends_on=malformed):
                self.contract["proof_obligations"][1]["depends_on"] = malformed
                self.save()
                response = self.cli("next", "--json")
                self.assertEqual(response.returncode, 1, response.stdout + response.stderr)
                observed = json.loads(response.stdout)
                self.assertFalse(observed["ok"])
                self.assertEqual(observed["ready"], [])
                self.assertTrue(observed["errors"])

    def test_cycle_refuses_with_explanation(self):
        self.contract["proof_obligations"][0]["depends_on"] = ["P3"]
        self.save()
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1)
        self.assertIn("cycle", response.stdout)

    def test_deep_chain_is_supported_without_recursive_crash(self):
        obligations = [{"id": f"P{index}", "claim": "Chain behavior", "verification": "Verify chain",
                        "depends_on": [f"P{index - 1}"] if index else []}
                       for index in range(1500)]
        self.contract["proof_obligations"] = obligations
        self.report["evidence"] = [self.result(item["id"]) for item in obligations]
        self.save()
        observed = self.frontier()
        self.assertEqual(observed["ready"], ["P0"])
        self.assertEqual(len(observed["blocked"]), 1499)

    def test_legacy_contract_without_dependencies_has_all_roots_ready(self):
        for obligation in self.contract["proof_obligations"]:
            obligation.pop("depends_on", None)
        self.save()
        self.assertEqual(self.frontier()["ready"], ["P1", "P2", "P3", "P4"])

    def test_dependent_pass_requires_actual_upstream_proof_and_preserves_report(self):
        self.capture()
        before = (self.directory / "report.json").read_bytes()
        response = self.record("P2")
        self.assertEqual(response.returncode, 2, response.stdout)
        self.assertIn("prerequisite", response.stdout)
        self.assertEqual((self.directory / "report.json").read_bytes(), before)
        self.assertEqual(self.record("P1").returncode, 0)
        self.assertEqual(self.record("P2").returncode, 0)
        self.assertEqual(self.frontier()["ready"], ["P3", "P4"])

    def test_incremental_pass_ignores_unrelated_unfinished_narrative(self):
        self.capture()
        self.assertEqual(self.record("P1").returncode, 0)
        self.report = self.current()
        self.report["outcome"] = ""
        self.report["extension"] = {"retained": True}
        self.save()
        response = self.record("P2")
        self.assertEqual(response.returncode, 0, response.stdout)
        after = self.current()
        self.assertEqual(after["outcome"], "")
        self.assertEqual(after["extension"], {"retained": True})
        self.assertEqual(after["evidence"][3]["status"], "not_run")

    def test_blocked_partial_can_be_recorded_without_prerequisite_pass(self):
        response = self.record("P3", status="partial", run=None, details="Missing upstream boundary")
        self.assertEqual(response.returncode, 0, response.stdout)
        self.assertEqual(self.current()["evidence"][2]["status"], "partial")

    def test_stale_upstream_cannot_enable_fresh_dependent_pass_or_frontier(self):
        self.capture()
        self.assertEqual(self.record("P1").returncode, 0)
        (self.root / "source.txt").write_text("changed source\n")
        self.capture("fresh")
        before = (self.directory / "report.json").read_bytes()
        response = self.record("P2", run="fresh")
        self.assertEqual(response.returncode, 2, response.stdout)
        self.assertIn("stale", response.stdout)
        self.assertEqual((self.directory / "report.json").read_bytes(), before)
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1)
        observed = json.loads(response.stdout)
        self.assertEqual(observed["ready"], [])
        self.assertFalse(observed["complete"])

    def test_tampered_upstream_log_refuses_frontier(self):
        self.capture()
        self.assertEqual(self.record("P1").returncode, 0)
        (self.directory / "runs/support.log").write_text("altered output\n")
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1)
        self.assertIn("hash does not match", response.stdout)
        self.assertEqual(json.loads(response.stdout)["ready"], [])

    def test_changed_upstream_status_demotes_transitive_passes_retaining_references(self):
        self.capture()
        for ident in ("P1", "P2", "P3"):
            response = self.record(ident)
            self.assertEqual(response.returncode, 0, response.stdout)
        original = copy.deepcopy(self.current()["evidence"])
        response = self.record("P1", status="partial", details="Boundary needs repair")
        self.assertEqual(response.returncode, 0, response.stdout)
        self.assertEqual(json.loads(response.stdout)["invalidated"], ["P2", "P3"])
        after = self.current()["evidence"]
        for index in (1, 2):
            self.assertEqual(after[index]["status"], "partial")
            self.assertEqual(after[index]["run_ids"], original[index]["run_ids"])
            self.assertIn("Prerequisite P1", after[index]["details"])
        self.assertEqual(after[3], original[3])

    def test_changed_support_run_demotes_but_details_only_update_does_not(self):
        self.capture()
        for ident in ("P1", "P2", "P3"):
            self.assertEqual(self.record(ident).returncode, 0)
        response = self.record("P1", details="Clarified coverage only")
        self.assertEqual(response.returncode, 0, response.stdout)
        self.assertEqual(json.loads(response.stdout)["invalidated"], [])
        self.assertEqual(self.current()["evidence"][2]["status"], "pass")
        self.capture("replacement")
        response = self.record("P1", run="replacement")
        self.assertEqual(response.returncode, 0, response.stdout)
        self.assertEqual(json.loads(response.stdout)["invalidated"], ["P2", "P3"])

    def test_diamond_invalidates_each_passed_descendant_once_in_contract_order(self):
        self.contract["proof_obligations"][2]["depends_on"] = ["P1"]
        self.contract["proof_obligations"][3]["depends_on"] = ["P2", "P3"]
        self.save()
        self.capture()
        for ident in ("P1", "P2", "P3", "P4"):
            self.assertEqual(self.record(ident).returncode, 0)
        response = self.record("P1", status="partial")
        self.assertEqual(response.returncode, 0, response.stdout)
        self.assertEqual(json.loads(response.stdout)["invalidated"], ["P2", "P3", "P4"])
        self.assertEqual([item["status"] for item in self.current()["evidence"]], ["partial"] * 4)

    def test_empty_frontier_is_not_completion_until_other_gates_pass(self):
        self.capture()
        for ident in ("P1", "P2", "P3", "P4"):
            self.assertEqual(self.record(ident).returncode, 0)
        observed = self.frontier()
        self.assertEqual(observed["ready"], [])
        self.assertEqual(observed["blocked"], [])
        self.assertFalse(observed["complete"])
        self.report = self.current()
        self.report["simplicity"].update(code_gate="pass", test_gate="pass")
        self.save()
        self.assertTrue(self.frontier()["complete"])

    def test_malformed_passed_descendant_refuses_upstream_change_without_mutation(self):
        self.capture()
        for ident in ("P1", "P2"):
            self.assertEqual(self.record(ident).returncode, 0)
        self.report = self.current()
        self.report["evidence"][1].pop("details")
        self.save()
        before = (self.directory / "report.json").read_bytes()
        response = self.record("P1", status="partial")
        self.assertEqual(response.returncode, 2, response.stdout + response.stderr)
        self.assertFalse(json.loads(response.stdout)["ok"])
        self.assertEqual((self.directory / "report.json").read_bytes(), before)

    def test_deeply_nested_json_refuses_cleanly_and_does_not_write_telemetry(self):
        # Python 3.14's JSON decoder can accept 1,500 levels; this 2 MB input
        # exercises its actual stack refusal rather than only invalid fields.
        (self.directory / "report.json").write_text('{"nested":' + '[' * 1_000_000 + '0' + ']' * 1_000_000 + '}')
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1, response.stdout + response.stderr)
        self.assertFalse(json.loads(response.stdout)["ok"])
        self.assertFalse((self.directory / "telemetry").exists())
        response = self.cli("validate")
        self.assertEqual(response.returncode, 2, response.stdout + response.stderr)
        self.assertIn("invalid JSON", response.stderr)
        response = self.record("P1", status="partial", run=None)
        self.assertEqual(response.returncode, 2, response.stdout + response.stderr)
        self.assertEqual(json.loads(response.stdout)["code"], "DOCUMENT_INVALID")

    def test_legacy_research_run_ignores_unknown_start_extension_without_crashing(self):
        self.capture()
        self.assertEqual(self.record("P1").returncode, 0)
        self.contract["task"]["type"] = "research"
        self.report = self.current()
        self.save()
        path = self.directory / "runs/support.json"
        captured = confidence.read_json(path)
        # A real historical v1 capture has no new exclusion/metadata binding.
        captured.pop("evidence_directory")
        captured.pop("capture_sha256")
        for malformed in ("wrong", [], 1, True):
            with self.subTest(workspace_start=malformed):
                path.write_text(json.dumps(dict(captured, version=1, workspace_start=malformed)))
                response = self.cli("next", "--json")
                self.assertEqual(response.returncode, 0, response.stderr)
                self.assertTrue(json.loads(response.stdout)["ok"])
                self.assertNotIn("Traceback", response.stderr)

    @unittest.skipUnless(os.name == "posix", "Executable Git fsmonitor probe requires Unix")
    def test_frontier_does_not_execute_repository_fsmonitor_hook(self):
        hooks = self.root / "hooks"
        hooks.mkdir()
        hook = hooks / "fsmonitor.py"
        sentinel = hooks / "executions"
        (self.root / ".gitignore").write_text("hooks/executions\n")
        hook.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nimport sys\n"
            "p=Path(__file__).with_name('executions')\n"
            "p.write_text('executed')\n"
            "sys.stdout.buffer.write(b'token\\x00/\\x00')\n")
        hook.chmod(0o755)
        self.capture()
        self.assertEqual(self.record("P1").returncode, 0)
        subprocess.run(["git", "-C", str(self.root), "config", "core.fsmonitor", str(hook)],
                       check=True, env=self.env)
        self.assertFalse(sentinel.exists())
        self.frontier()
        self.assertFalse(sentinel.exists(), "Read-only planning invoked configured Git code")

    def test_unhashable_evidence_id_returns_json_validation_error(self):
        for malformed in ([], {}):
            with self.subTest(obligation_id=malformed):
                self.report["evidence"][0]["obligation_id"] = malformed
                self.save()
                response = self.cli("next", "--json")
                self.assertEqual(response.returncode, 1, response.stderr)
                self.assertFalse(json.loads(response.stdout)["ok"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO reader boundary requires Unix")
    def test_fifo_and_symlink_documents_refuse_without_writes(self):
        path = self.directory / "report.json"
        original = path.read_bytes()
        path.unlink()
        os.mkfifo(path)
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1, response.stderr)
        self.assertIn("regular file", response.stdout)
        path.unlink()
        target = self.root / "external-report.json"
        target.write_bytes(original)
        path.symlink_to(target)
        response = self.cli("next", "--json")
        self.assertEqual(response.returncode, 1, response.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.directory / "telemetry").exists())


if __name__ == "__main__":
    unittest.main()
