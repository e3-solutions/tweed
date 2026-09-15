"""Public source-scope handoff output without changing acceptance rules."""

import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
import test_confidence as fixtures

c = fixtures.confidence
SCRIPT = fixtures.SCRIPT


class SourceScopeOutputTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "evidence"
        self.directory.mkdir()
        self.fixture = fixtures.ConfidenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.valid_files(self.directory)
        self.source = self.fixture.fixture_workspace(self.directory)
        self.caller = self.root / "other"
        self.caller.mkdir()
        (self.caller / "different.txt").write_text("different source")
        # Replace fixture run with an actual public CLI capture.
        shutil.rmtree(self.directory / "runs")
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "run",
                "--id",
                "tests",
                "--directory",
                str(self.directory),
                "--cwd",
                str(self.source),
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path;assert Path('source.txt').read_text()=='stable fixture source\\n'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)

    def call(self, action, *args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                action,
                "--directory",
                str(self.directory),
                *args,
            ],
            cwd=self.caller,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CONFIDENCE_DISABLE_DIAGNOSTICS": "1"},
        )

    def test_public_handoff_names_recorded_tree_and_rejects_changed_source(self):
        result = self.call("validate", "--require-complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.source.resolve()), result.stdout)
        self.assertNotIn(str(self.caller), result.stdout)
        self.assertIn("not caller checkout", result.stdout)
        self.assertIn("unchanged endpoints", result.stdout)
        rendered = self.call("render")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        text = (self.directory / "REPORT.md").read_text()
        self.assertIn("Recorded source scope", text)
        self.assertIn("git\\-content\\-v1", text)
        self.assertIn("tests", text)
        (self.source / "source.txt").write_text("changed")
        self.assertNotEqual(self.call("validate", "--require-complete").returncode, 0)

    def test_multi_root_and_deduplicated_references(self):
        second = self.root / "second-evidence"
        second.mkdir()
        self.fixture.write_run(second, "other")
        shutil.copyfile(second / "runs/other.json", self.directory / "runs/other.json")
        shutil.copyfile(second / "runs/other.log", self.directory / "runs/other.log")
        report = c.read_json(self.directory / "report.json")
        report["evidence"][0]["run_ids"] = ["tests", "other"]
        c.write_json(self.directory / "report.json", report)
        result = self.call("validate", "--require-complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = c.recorded_source_scopes(report, self.directory)
        for item in rows:
            self.assertIn(item["role"], result.stdout)
            self.assertIn(item["observation_status"], result.stdout)
            if item["recorded_root"] != "unknown":
                self.assertIn(item["recorded_root"], result.stdout)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["recorded_root"] for r in rows}), 2)
        report["evidence"].append(dict(report["evidence"][0]))
        self.assertEqual(len(c.recorded_source_scopes(report, self.directory)), 2)

    def test_partial_unknown_and_diagnostic_are_explicit(self):
        record = c.read_json(self.directory / "runs/tests.json")
        record["workspace"] = None
        record["workspace_start"] = None
        c.write_json(self.directory / "runs/tests.json", record)
        diagnostic = dict(record, id="diagnostic", log="runs/diagnostic.log")
        c.write_json(self.directory / "runs/diagnostic.json", diagnostic)
        shutil.copyfile(
            self.directory / "runs/tests.log", self.directory / "runs/diagnostic.log"
        )
        report = c.read_json(self.directory / "report.json")
        report["evidence"][0].update(
            status="partial", diagnostic_run_ids=["diagnostic"]
        )
        c.write_json(self.directory / "report.json", report)
        result = self.call("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = c.recorded_source_scopes(report, self.directory)
        for item in rows:
            self.assertIn(item["role"], result.stdout)
            self.assertIn(item["observation_status"], result.stdout)
            if item["recorded_root"] != "unknown":
                self.assertIn(item["recorded_root"], result.stdout)
        self.assertEqual({r["role"] for r in rows}, {"support", "diagnostic"})
        self.assertTrue(
            all(
                r["binding_kind"] == "unknown" and r["claim_statuses"] == ["partial"]
                for r in rows
            )
        )
        self.assertNotEqual(self.call("validate", "--require-complete").returncode, 0)

    def test_partial_start_unknown_preserves_known_end_root(self):
        record = c.read_json(self.directory / "runs/tests.json")
        record["workspace_start"] = None
        c.write_json(self.directory / "runs/tests.json", record)
        report = c.read_json(self.directory / "report.json")
        report["evidence"][0]["status"] = "partial"
        c.write_json(self.directory / "report.json", report)
        result = self.call("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        scope = c.recorded_source_scopes(report, self.directory)[0]
        self.assertIn(scope["observation_status"], result.stdout)
        self.assertIn(scope["recorded_root"], result.stdout)
        self.assertEqual(scope["record_version"], 2)
        self.assertEqual(scope["observation_status"], "unknown endpoint")
        self.assertEqual(scope["start_fingerprint"], "unknown")
        self.assertEqual(scope["recorded_root"], str(self.source.resolve()))
        self.assertEqual(scope["binding_kind"], "git-content-v1")

    def test_legacy_record_content_kind_is_not_unchanged_observation(self):
        record = c.read_json(self.directory / "runs/tests.json")
        record["version"] = 1
        record.pop("workspace_start", None)
        c.write_json(self.directory / "runs/tests.json", record)
        report = c.read_json(self.directory / "report.json")
        report["evidence"][0]["status"] = "partial"
        c.write_json(self.directory / "report.json", report)
        result = self.call("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        scope = c.recorded_source_scopes(report, self.directory)[0]
        self.assertIn(scope["observation_status"], result.stdout)
        self.assertIn(scope["recorded_root"], result.stdout)
        self.assertEqual(scope["record_version"], 1)
        self.assertEqual(scope["binding_kind"], "git-content-v1")
        self.assertEqual(scope["observation_status"], "legacy record")
        self.assertEqual(scope["recorded_root"], str(self.source.resolve()))

    def test_changed_endpoints_are_visible_for_partial_observation(self):
        record = c.read_json(self.directory / "runs/tests.json")
        record["workspace_start"]["sha256"] = "a" * 64
        c.write_json(self.directory / "runs/tests.json", record)
        report = c.read_json(self.directory / "report.json")
        report["evidence"][0]["status"] = "partial"
        c.write_json(self.directory / "report.json", report)
        result = self.call("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        scope = c.recorded_source_scopes(report, self.directory)[0]
        self.assertIn(scope["observation_status"], result.stdout)
        self.assertIn(scope["recorded_root"], result.stdout)
        self.assertEqual(scope["observation_status"], "changed endpoints")
        self.assertEqual(scope["start_fingerprint"], "a" * 64)
        self.assertNotEqual(scope["start_fingerprint"], scope["fingerprint"])

    def test_legacy_and_malicious_scope_formatting(self):
        record = c.read_json(self.directory / "runs/tests.json")
        record["workspace"] = {
            "kind": "git",
            "root": "/tmp/[click](https://invalid)|`x`\n<script>",
            "sha256": "a" * 64,
        }
        c.write_json(self.directory / "runs/tests.json", record)
        rows = c.recorded_source_scopes(
            c.read_json(self.directory / "report.json"), self.directory
        )
        self.assertEqual(rows[0]["binding_kind"], "git (legacy)")
        text = c.source_scope_markdown(rows)
        self.assertNotIn("[click](", text)
        self.assertNotIn("<script>", text)
        self.assertIn("\\|", text)
        self.assertIn("\\`", text)
        self.assertIn("&lt;script", text)


if __name__ == "__main__":
    unittest.main()
