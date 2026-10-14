"""Attributable review gates exercise real files, git source, and the public CLI."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import support

confidence = support.load_confidence("confidence_review_provenance")


class ReviewProvenanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="confidence-review-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "evidence"
        self.directory.mkdir()
        self.workspace = support.fixture_workspace(self.directory, {}, self.addCleanup)
        self.contract, self.report = support.valid_documents(confidence)
        self.contract["review_policy"] = {"records_required": True, "implementer": "root"}
        self.report["review"].update(required=True, reason="Independent source review is required.",
                                      roles=["critic"], records=[])
        support.write_run(confidence, self.directory, self.workspace)
        support.write_run(confidence, self.directory, self.workspace, run_id="review")
        self.add_review()

    def add_review(self, role="critic", reviewer="independent-reviewer", scope=None, run_id="review"):
        ident = f"review-{len(self.report['review']['records']) + 1}"
        path = self.directory / "reviews" / f"{ident}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"findings": "No counterexample in assigned scope.", "role": role}) + "\n")
        record = {
            "id": ident, "role": role, "reviewer": reviewer, "model": "fixture-model",
            "harness": "fixture-harness", "scope": scope or ["P1"],
            "question": "Can unauthorized callers pass the invitation gate?",
            "findings": "No counterexample in assigned scope.", "independent": True,
            "status": "pass", "reference": f"reviews/{ident}.json",
            "reference_sha256": confidence.sha256_file(path),
            "contract_sha256": confidence.contract_digest(self.contract), "run_id": run_id,
        }
        self.report["review"]["records"].append(record)
        return record

    def save(self):
        confidence.write_json(self.directory / "contract.json", self.contract)
        confidence.write_json(self.directory / "report.json", self.report)

    def call(self, action="validate", complete=True):
        self.save()
        args = [action, "--directory", str(self.directory)]
        if action == "validate" and complete:
            args.append("--require-complete")
        return support.run_cli(*args)

    def assert_rejected(self, fragment):
        result = self.call()
        self.assertNotEqual(result.returncode, 0, "incomplete or invalid review must not release")
        self.assertIn(fragment, result.stderr)
        self.assertNotIn("Traceback", result.stderr, "malformed review must produce a validation error")

    def bind_records(self):
        for record in self.report["review"]["records"]:
            record["contract_sha256"] = confidence.contract_digest(self.contract)

    def critical(self):
        self.contract["task"]["mode"] = "critical"
        self.report["mode"] = "critical"
        self.report["review"]["roles"] = ["test_designer", "adversarial_reviewer"]
        self.report["review"]["records"] = []
        self.add_review("test_designer", "designer")
        self.add_review("adversarial_reviewer", "adversary")

    def test_attributable_pass_completes_and_renders(self):
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.call("render")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.directory / "REPORT.md").read_text()
        self.assertIn("independent-reviewer", text)
        self.assertIn("fixture-model", text)
        self.assertIn("fixture-harness", text)

    def test_opted_in_report_cannot_delete_records(self):
        self.report["review"].pop("records")
        self.assert_rejected("independent pass records")

    def test_opted_in_report_cannot_delete_roles(self):
        self.report["review"]["roles"] = []
        self.assert_rejected("named review roles")

    def test_role_labels_do_not_substitute_for_review_records(self):
        self.report["review"]["roles"].append("integration_reviewer")
        self.assert_rejected("integration_reviewer")

    def test_pinned_required_roles_reject_malformed_values(self):
        original = copy.deepcopy(self.contract)
        for roles in (None, True, "critic", [], ["unknown"], ["critic", "critic"], [None]):
            with self.subTest(roles=roles):
                self.contract = copy.deepcopy(original)
                self.contract["review_policy"]["required_roles"] = roles
                self.bind_records()
                self.assert_rejected("required_roles")

    def test_deleting_report_role_cannot_drop_contract_pinned_review(self):
        self.contract["review_policy"]["required_roles"] = ["critic", "integration_reviewer"]
        self.report["review"]["roles"].append("integration_reviewer")
        self.bind_records()
        self.add_review(role="integration_reviewer", reviewer="integration-reviewer")
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.report["review"]["roles"].remove("integration_reviewer")
        self.report["review"]["records"].pop()
        self.assert_rejected("integration_reviewer")

    def test_required_record_fields_reject_wrong_types_without_crashing(self):
        original = copy.deepcopy(self.report)
        cases = [(field, value) for field in ("id", "reviewer", "model", "harness", "question", "findings")
                 for value in (None, 7, "  ", [], {})]
        cases += [("role", []), ("role", "unknown"), ("status", {}), ("status", "complete"),
                  ("independent", 1), ("independent", "true"), ("scope", "P1"), ("scope", []),
                  ("scope", ["P1", "P1"]), ("scope", ["unknown"]), ("run_id", None),
                  ("reference", None), ("reference_sha256", "invalid"), ("contract_sha256", "invalid")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.report = copy.deepcopy(original)
                self.report["review"]["records"][0][field] = value
                self.assert_rejected("review")

    def test_records_and_entries_have_explicit_container_types(self):
        for records in ({}, "done", ["done"], [None]):
            with self.subTest(records=records):
                self.report["review"]["records"] = records
                self.assert_rejected("report.review.records")

    def test_duplicate_review_ids_are_rejected(self):
        second = self.add_review()
        second["id"] = self.report["review"]["records"][0]["id"]
        self.assert_rejected("id must be unique")

    def test_self_review_identity_is_normalized(self):
        for reviewer in ("root", " ROOT ", "Root"):
            with self.subTest(reviewer=reviewer):
                self.report["review"]["records"][0]["reviewer"] = reviewer
                self.assert_rejected("independent pass records")

    def test_declared_dependence_cannot_complete(self):
        self.report["review"]["records"][0]["independent"] = False
        self.assert_rejected("independent pass records")

    def test_unresolved_review_cannot_hide_behind_another_pass(self):
        record = self.add_review()
        for status in ("partial", "fail", "not_run"):
            with self.subTest(status=status):
                record["status"] = status
                record.pop("reference", None)
                record.pop("reference_sha256", None)
                record.pop("run_id", None)
                record.pop("contract_sha256", None)
                self.assert_rejected("unresolved review records")
                result = self.call(complete=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_role_scopes_must_cover_all_obligations_and_can_union(self):
        self.contract["proof_obligations"].append({"id": "P2", "claim": "Valid owners can invite.",
                                                    "verification": "Run owner success check."})
        evidence = copy.deepcopy(self.report["evidence"][0])
        evidence["obligation_id"] = "P2"
        self.report["evidence"].append(evidence)
        self.bind_records()
        self.assert_rejected("covering every obligation")
        self.add_review(scope=["P2"])
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_contract_digest_rejects_semantic_drift(self):
        original = copy.deepcopy(self.contract)
        mutations = [("intent", "goal", "A different objective."),
                     ("review_policy", "implementer", "another-implementer")]
        for section, field, value in mutations:
            with self.subTest(section=section):
                self.contract = copy.deepcopy(original)
                self.contract[section][field] = value
                self.assert_rejected("contract digest changed")
        self.contract = copy.deepcopy(original)
        self.contract["proof_obligations"][0]["claim"] = "A different trust contract."
        self.assert_rejected("contract digest changed")

    def test_canonical_digest_survives_key_order_and_whitespace(self):
        self.save()
        path = self.directory / "contract.json"
        reordered = dict(reversed(list(self.contract.items())))
        path.write_text(json.dumps(reordered, indent=4) + "\n\n")
        result = support.run_cli("validate", "--directory", str(self.directory), "--require-complete")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_review_artifact_modification_is_detected(self):
        path = self.directory / self.report["review"]["records"][0]["reference"]
        path.write_text("Changed findings after the recorded review.\n")
        self.assert_rejected("reference hash does not match")

    def test_missing_review_artifact_is_detected(self):
        (self.directory / self.report["review"]["records"][0]["reference"]).unlink()
        self.assert_rejected("missing file")

    def test_outside_references_reject_traversal_and_absolute_paths(self):
        outside = self.root / "outside.json"
        outside.write_text("outside evidence\n")
        for reference in ("../outside.json", str(outside)):
            with self.subTest(reference=reference):
                record = self.report["review"]["records"][0]
                record["reference"] = reference
                record["reference_sha256"] = confidence.sha256_file(outside)
                self.assert_rejected("stay inside evidence directory")

    def test_review_artifact_symlink_is_rejected(self):
        record = self.report["review"]["records"][0]
        original = self.directory / record["reference"]
        target = self.directory / "target.json"
        original.rename(target)
        original.symlink_to(target)
        self.assert_rejected("could not read log")

    def test_intermediate_symlink_cannot_escape_evidence_directory(self):
        outside = self.root / "external"
        outside.mkdir()
        target = outside / "review.json"
        target.write_text("external review\n")
        (self.directory / "linked").symlink_to(outside, target_is_directory=True)
        record = self.report["review"]["records"][0]
        record.update(reference="linked/review.json", reference_sha256=confidence.sha256_file(target))
        self.assert_rejected("stay inside evidence directory")

    def test_review_capture_failure_and_log_drift_are_rejected(self):
        support.write_run(confidence, self.directory, self.workspace, run_id="review", exit_code=1)
        self.assert_rejected("captured review run must succeed")
        support.write_run(confidence, self.directory, self.workspace, run_id="review")
        (self.directory / "runs/review.log").write_text("replaced review output\n")
        self.assert_rejected("log hash does not match")

    def test_stale_reviewer_source_rejects_even_when_behavior_proof_is_current(self):
        (self.workspace / "source.txt").write_text("changed source after review\n")
        support.write_run(confidence, self.directory, self.workspace, run_id="current-tests")
        self.report["evidence"][0]["run_ids"] = ["current-tests"]
        self.assert_rejected("workspace")

    def test_unrelated_repository_cannot_review_a_scoped_software_obligation(self):
        foreign = support.fixture_workspace(self.root / "foreign-evidence", {}, self.addCleanup)
        support.write_run(confidence, self.directory, foreign, run_id="foreign-review")
        self.report["review"]["records"][0]["run_id"] = "foreign-review"
        self.assert_rejected("source")

    def test_different_working_directory_within_reviewed_repository_is_supported(self):
        nested = self.workspace / "nested"
        nested.mkdir()
        support.write_run(confidence, self.directory, nested, run_id="nested-review")
        self.report["review"]["records"][0]["run_id"] = "nested-review"
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_repository_obligations_use_reviews_scoped_to_each_root(self):
        foreign = support.fixture_workspace(self.root / "foreign-evidence", {}, self.addCleanup)
        self.contract["proof_obligations"].append({"id": "P2", "claim": "The linked service preserves authorization.",
                                                    "verification": "Run the linked service integration check."})
        evidence = copy.deepcopy(self.report["evidence"][0])
        evidence.update(obligation_id="P2", run_ids=["foreign-tests"])
        self.report["evidence"].append(evidence)
        support.write_run(confidence, self.directory, foreign, run_id="foreign-tests")
        support.write_run(confidence, self.directory, foreign, run_id="foreign-review")
        self.bind_records()
        self.add_review(scope=["P2"], reviewer="foreign-reviewer", run_id="foreign-review")
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_review_for_one_root_cannot_claim_an_obligation_with_unreviewed_source(self):
        foreign = support.fixture_workspace(self.root / "foreign-evidence", {}, self.addCleanup)
        support.write_run(confidence, self.directory, foreign, run_id="foreign-tests")
        self.report["evidence"][0]["run_ids"].append("foreign-tests")
        self.assert_rejected("review source root does not match")

    def test_historical_test_design_source_is_allowed_but_contract_stays_current(self):
        self.critical()
        (self.workspace / "source.txt").write_text("implementation after proof design\n")
        support.write_run(confidence, self.directory, self.workspace, run_id="current-tests")
        support.write_run(confidence, self.directory, self.workspace, run_id="current-review")
        self.report["evidence"][0]["run_ids"] = ["current-tests"]
        self.report["review"]["records"][1]["run_id"] = "current-review"
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.contract["intent"]["goal"] = "Different goal after proof design."
        self.assert_rejected("contract digest changed")

    def test_critical_roles_require_different_normalized_identities(self):
        self.critical()
        self.report["review"]["records"][1]["reviewer"] = " DESIGNER "
        self.assert_rejected("different test designer")

    def test_critical_complete_review_has_both_attributable_roles(self):
        self.critical()
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_without_policy_keeps_existing_completion_behavior(self):
        self.contract.pop("review_policy")
        self.report["review"].pop("records")
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_adding_policy_does_not_invent_legacy_review_provenance(self):
        self.report["review"].pop("records")
        result = self.call(complete=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_rejected("independent pass records")


if __name__ == "__main__":
    unittest.main()
