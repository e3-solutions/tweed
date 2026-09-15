"""The release checker must inspect shipped bytes, never execute their code."""
import io
import json
import tarfile
import unittest

from check_release import REQUIRED, validate_archive


class ReleaseArchiveTest(unittest.TestCase):
    def archive(self, *, manifest=None, source=None, remove=None, extra=None):
        files = {name: b"fixture" for name in REQUIRED}
        files[".codex-plugin/plugin.json"] = json.dumps(
            manifest if manifest is not None else {"name": "confidence-protocol", "version": "candidate"}
        ).encode()
        files["skills/confidence-protocol/scripts/diagnostics.py"] = (
            source if source is not None else 'TOOL_VERSION = "candidate"\n'
        ).encode()
        if remove:
            files.pop(remove)
        if extra:
            files[extra] = b"unwanted"
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as bundle:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        return output.getvalue()

    def test_matching_archived_versions_pass_without_executing_source(self):
        archive = self.archive(source='raise RuntimeError("must not execute")\nTOOL_VERSION = "candidate"\n')
        self.assertEqual(validate_archive(archive), len(REQUIRED))

    def test_archived_manifest_mismatch_is_rejected(self):
        archive = self.archive(manifest={"name": "confidence-protocol", "version": "wrong"})
        with self.assertRaisesRegex(ValueError, "does not match archived TOOL_VERSION"):
            validate_archive(archive)

    def test_archived_manifest_identity_and_version_are_required(self):
        for manifest in ({"name": "wrong", "version": "candidate"}, {"name": "confidence-protocol"}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                validate_archive(self.archive(manifest=manifest))

    def test_version_must_be_one_static_literal(self):
        for source in ('TOOL_VERSION = str("candidate")', 'pass',
                       'TOOL_VERSION = "candidate"\nTOOL_VERSION = "candidate"'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_archive(self.archive(source=source))

    def test_missing_required_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "release is missing"):
            validate_archive(self.archive(remove="README.md"))

    def test_repository_only_files_are_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "repository-only"):
            validate_archive(self.archive(extra="skills/confidence-protocol/tests/leaked.py"))


if __name__ == "__main__":
    unittest.main()
