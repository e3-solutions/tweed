"""Actual capture metadata binding and privacy-preserving support exports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import load_confidence, run_cli

confidence = load_confidence("capture_metadata_tests")


class CaptureMetadataTest(unittest.TestCase):
    def test_record_only_metadata_drift_is_rejected_without_changing_log(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            evidence = root / ".confidence"
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "source.txt").write_text("stable\n")
            result = run_cli("run", "--json", "--directory", str(evidence), "--cwd", str(root),
                             "--id", "proof", "--", sys.executable, "-B", "-c", "print('observed')")
            self.assertEqual(result.returncode, 0, result.stderr)
            record_path = evidence / "runs/proof.json"
            original = json.loads(record_path.read_text())
            log = (evidence / "runs/proof.log").read_bytes()
            self.assertEqual(confidence.validate_run_record(evidence, "proof")[1], [])
            for field, value in (("evidence_directory", str(root / "fixtures")),
                                 ("exit_code", 1), ("cwd", str(root.parent)),
                                 ("argv", ["invented-command"]),
                                 ("capture_sha256", None)):
                with self.subTest(field=field):
                    changed = dict(original, **{field: value})
                    record_path.write_text(json.dumps(changed))
                    errors = confidence.validate_run_record(evidence, "proof")[1]
                    self.assertTrue(any("capture metadata hash" in error for error in errors), errors)
                    self.assertEqual((evidence / "runs/proof.log").read_bytes(), log)

    def test_impossible_stopping_status_is_rejected_even_with_recomputed_hash(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence = Path(scratch)
            result = run_cli("run", "--json", "--directory", str(evidence), "--id", "proof",
                             "--", sys.executable, "-B", "-c", "pass")
            self.assertEqual(result.returncode, 0, result.stderr)
            path = evidence / "runs/proof.json"
            original = json.loads(path.read_text())
            for reason in ("timeout", "log_limit", "invented"):
                with self.subTest(reason=reason):
                    record = dict(original, termination_reason=reason)
                    record["capture_sha256"] = confidence.capture_digest(record)
                    path.write_text(json.dumps(record))
                    errors = confidence.validate_run_record(evidence, "proof")[1]
                    self.assertTrue(any("termination" in error for error in errors), errors)

    def test_deleting_only_anchor_cannot_disable_retained_capture_binding(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence = Path(scratch)
            result = run_cli("run", "--json", "--directory", str(evidence), "--id", "proof",
                             "--", sys.executable, "-B", "-c", "pass")
            self.assertEqual(result.returncode, 0, result.stderr)
            path = evidence / "runs/proof.json"
            record = json.loads(path.read_text())
            del record["evidence_directory"]
            path.write_text(json.dumps(record))
            errors = confidence.validate_run_record(evidence, "proof")[1]
            self.assertTrue(any("capture metadata hash" in error for error in errors), errors)
            # An actual legacy capture has neither extension, not a half-deleted pair.
            del record["capture_sha256"]
            path.write_text(json.dumps(record))
            self.assertEqual(confidence.validate_run_record(evidence, "proof")[1], [])

    def test_support_export_retains_v2_kind_and_version_without_work_content(self):
        from diagnostics import safe_run_records
        with tempfile.TemporaryDirectory() as scratch:
            evidence = Path(scratch)
            result = run_cli("run", "--json", "--directory", str(evidence), "--id", "proof",
                             "--", sys.executable, "-B", "-c", "print('private-work-content')")
            self.assertEqual(result.returncode, 0, result.stderr)
            record_path = evidence / "runs/proof.json"
            record = json.loads(record_path.read_text())
            record["workspace"] = {"kind": "git-content-v1", "sha256": "a" * 64,
                                   "root": "/private/source-path"}
            record_path.write_text(json.dumps(record))
            exported = safe_run_records(evidence)
            self.assertEqual(exported[0]["version"], 2)
            self.assertEqual(exported[0]["workspace"], {"kind": "git-content-v1", "sha256": "a" * 64})
            serialized = json.dumps(exported)
            for private in ("/private/source-path", "private-work-content", scratch, "evidence_directory", "argv"):
                self.assertNotIn(private, serialized)


if __name__ == "__main__":
    unittest.main()
