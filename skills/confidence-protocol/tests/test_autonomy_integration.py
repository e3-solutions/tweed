"""Public CLI acceptance checks for durable, dependency-aware proof workflows."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import support

confidence = support.load_confidence("confidence_autonomy_integration")


class AutonomyIntegrationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="confidence-integration-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = self.root / "source"
        self.workspace.mkdir()
        (self.workspace / "behavior.py").write_text("answer = 42\n")
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        subprocess.run(["git", "-C", str(self.workspace), "add", "behavior.py"], check=True)
        subprocess.run(["git", "-C", str(self.workspace), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "baseline"],
                       check=True)
        self.directory = self.workspace / ".confidence"
        self.contract, self.report = support.valid_documents(confidence)
        self.contract["proof_obligations"] = [
            {"id": "P1", "claim": "The public result is correct.", "verification": "Check answer equals 42."},
            {"id": "P2", "claim": "The dependent flow works.", "verification": "Run dependent flow.",
             "depends_on": ["P1"]},
            {"id": "P3", "claim": "The full flow works.", "verification": "Run complete flow.",
             "depends_on": ["P2"]},
        ]
        self.report["evidence"] = [
            {"obligation_id": obligation["id"], "status": "partial", "details": "Required proof pending.",
             "run_ids": [], "diagnostic_run_ids": [], "artifacts": []}
            for obligation in self.contract["proof_obligations"]
        ]
        self.report["tests"]["passed"] = []
        self.write_documents()

    def write_documents(self):
        confidence.write_json(self.directory / "contract.json", self.contract)
        confidence.write_json(self.directory / "report.json", self.report)

    def cli(self, action, *args, directory=None, cwd=None):
        return support.run_cli(action, "--directory", str(directory or self.directory), *args,
                               cwd=cwd or self.workspace)

    def frontier(self, directory=None, cwd=None, expected=0):
        result = self.cli("next", "--json", directory=directory, cwd=cwd)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def capture(self, run_id="proof", command=None):
        result = self.cli("run", "--id", run_id, "--cwd", str(self.workspace), "--json", "--",
                          sys.executable, "-B", "-c", command or "from behavior import answer; assert answer == 42")
        return result

    def record(self, obligation, status="pass", run_id="proof", details="The captured acceptance check passed."):
        arguments = ["--obligation", obligation, "--status", status, "--details", details]
        if run_id is not None:
            arguments += ["--run", run_id]
        return self.cli("record", *arguments)

    def test_cli_workflow_advances_frontier_and_completes_in_new_processes(self):
        first = self.frontier()
        self.assertEqual(first["ready"], ["P1"])
        self.assertEqual(first["blocked"], [
            {"obligation_id": "P2", "depends_on": ["P1"]},
            {"obligation_id": "P3", "depends_on": ["P2"]},
        ])
        self.assertFalse(first["complete"])
        self.assertEqual(self.capture().returncode, 0)
        out_of_order = self.record("P2")
        self.assertNotEqual(out_of_order.returncode, 0, "A dependent claim passed before its prerequisite")
        self.assertEqual(self.record("P1").returncode, 0)
        self.assertEqual(self.frontier()["ready"], ["P2"])
        self.assertEqual(self.record("P2").returncode, 0)
        self.assertEqual(self.frontier()["ready"], ["P3"])
        self.assertEqual(self.record("P3").returncode, 0)
        complete = self.frontier()
        self.assertTrue(complete["complete"], complete)
        self.assertEqual(complete["ready"], [])
        self.assertEqual(self.cli("validate", "--require-complete").returncode, 0)

    def test_replacing_upstream_support_invalidates_transitive_passes(self):
        self.assertEqual(self.capture().returncode, 0)
        for obligation in ("P1", "P2", "P3"):
            self.assertEqual(self.record(obligation).returncode, 0)
        self.assertEqual(self.capture("replacement").returncode, 0)
        updated = self.record("P1", run_id="replacement")
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertEqual(json.loads(updated.stdout)["invalidated"], ["P2", "P3"])
        durable = confidence.read_json(self.directory / "report.json")
        self.assertEqual([item["status"] for item in durable["evidence"]], ["pass", "partial", "partial"])
        self.assertEqual(self.frontier()["ready"], ["P2"])
        self.assertNotEqual(self.cli("validate", "--require-complete").returncode, 0)
        retry = self.record("P1", run_id="replacement")
        self.assertEqual(json.loads(retry.stdout)["invalidated"], [])
        self.assertFalse(json.loads(retry.stdout)["changed"])

    def test_next_is_byte_preserving_and_does_not_execute_verification_text(self):
        marker = self.root / "executed"
        self.contract["proof_obligations"][0]["verification"] = (
            f"{sys.executable} -c \"from pathlib import Path; Path('{marker}').write_text('executed')\""
        )
        self.write_documents()
        before = {path.relative_to(self.directory): (hashlib.sha256(path.read_bytes()).hexdigest(),
                                                     path.stat().st_mtime_ns)
                  for path in self.directory.rglob("*") if path.is_file()}
        self.assertEqual(self.frontier()["ready"], ["P1"])
        self.assertEqual(self.frontier()["ready"], ["P1"])
        after = {path.relative_to(self.directory): (hashlib.sha256(path.read_bytes()).hexdigest(),
                                                    path.stat().st_mtime_ns)
                 for path in self.directory.rglob("*") if path.is_file()}
        self.assertEqual(before, after, "Planning wrote evidence or telemetry")
        self.assertFalse(marker.exists(), "Planning executed the verification string")

    def test_invalid_graph_has_no_frontier_and_does_not_write_telemetry(self):
        for dependencies in (["missing"], ["P1"], ["P3"]):
            with self.subTest(dependencies=dependencies):
                self.contract["proof_obligations"][0]["depends_on"] = dependencies
                self.write_documents()
                result = self.frontier(expected=1)
                self.assertFalse(result["ok"])
                self.assertEqual(result["ready"], [])
                self.assertEqual(result["blocked"], [])
                self.assertFalse(result["complete"])
                self.assertTrue(result["errors"])
                self.assertFalse((self.directory / "telemetry").exists())

    def test_copied_report_retains_original_scope_and_checks_original_source(self):
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(self.record("P1").returncode, 0)
        caller = self.root / "different-caller"
        caller.mkdir()
        (caller / "behavior.py").write_text("answer = -1\n")
        copied = caller / ".confidence"
        shutil.copytree(self.directory, copied)
        result = self.frontier(directory=copied, cwd=caller)
        self.assertEqual(len(result["source_scopes"]), 1)
        scope = result["source_scopes"][0]
        self.assertEqual(scope["recorded_root"], str(self.workspace.resolve()))
        self.assertEqual(scope["recorded_cwd"], str(self.workspace.resolve()))
        self.assertEqual(scope["run_ids"], ["proof"])
        (self.workspace / "behavior.py").write_text("answer = 0\n")
        stale = self.frontier(directory=copied, cwd=caller, expected=1)
        self.assertTrue(any("workspace changed" in error for error in stale["errors"]), stale)

    def test_printed_success_cannot_promote_nonzero_process_to_proof(self):
        child = self.capture("false-success", "print('All obligations passed'); raise SystemExit(7)")
        self.assertEqual(child.returncode, 7)
        result = self.record("P1", run_id="false-success")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.frontier()["ready"], ["P1"])
        self.assertEqual(confidence.read_json(self.directory / "report.json")["evidence"][0]["status"], "partial")

    def test_structured_review_rejects_self_review_and_changed_reference(self):
        self.directory = self.root / "review-evidence"
        self.contract["review_policy"] = {"records_required": True, "implementer": "author"}
        self.report["review"].update(required=True, roles=["adversarial_reviewer"],
                                      reason="The independent proof review is required.")
        self.write_documents()
        reference = self.directory / "adversarial-review.txt"
        reference.write_text("Checked prerequisite ordering and stale captured evidence.\n")
        self.assertEqual(self.capture().returncode, 0)
        for obligation in ("P1", "P2", "P3"):
            self.assertEqual(self.record(obligation).returncode, 0)
        self.report = confidence.read_json(self.directory / "report.json")
        review = {"id": "review-1", "reviewer": "author", "model": "claude-opus-5-5",
                  "harness": "claude-code", "role": "adversarial_reviewer", "independent": True,
                  "question": "Can a dependent claim pass without proof?", "findings": "No bypass found.",
                  "scope": ["P1", "P2", "P3"], "status": "pass", "run_id": "proof",
                  "reference": reference.name, "reference_sha256": confidence.sha256_file(reference),
                  "contract_sha256": confidence.contract_digest(self.contract)}
        self.report["review"]["records"] = [review]
        self.write_documents()
        refused = self.cli("validate", "--require-complete")
        self.assertNotEqual(refused.returncode, 0, "Self-review satisfied an independent-review gate")
        review["reviewer"] = "independent-reviewer"
        self.write_documents()
        self.assertEqual(self.cli("validate", "--require-complete").returncode, 0)
        reference.write_text("The original review was replaced.\n")
        invalid = self.frontier(expected=1)
        self.assertTrue(any("review reference hash" in error for error in invalid["errors"]), invalid)

    def test_flat_legacy_contract_uses_same_cli_without_dependency_metadata(self):
        for obligation in self.contract["proof_obligations"]:
            obligation.pop("depends_on", None)
        self.write_documents()
        self.assertEqual(self.frontier()["ready"], ["P1", "P2", "P3"])
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(self.record("P3").returncode, 0)
        self.assertEqual(self.frontier()["ready"], ["P1", "P2"])


if __name__ == "__main__":
    unittest.main()
