#!/usr/bin/env python3
"""Fail when the shipped archive contains old Tweed or repository-only files."""

import ast
import io
import json
import subprocess
import tarfile
from pathlib import Path


FORBIDDEN_PREFIXES = (
    "bonaparte",
    "autoresearch",
    "workflows/",
    "skills/use-bonaparte/",
    "skills/confidence-protocol/tests/",
    ".confidence/",
)
REQUIRED = {
    ".codex-plugin/plugin.json",
    "CHANGELOG.md",
    "README.md",
    "skills/confidence-protocol/SKILL.md",
    "skills/confidence-protocol/scripts/confidence.py",
    "skills/confidence-protocol/scripts/diagnostics.py",
}


def validate_archive(archive: bytes) -> int:
    """Inspect the shipped bytes without importing or executing their Python."""
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        names = set(bundle.getnames())
        unexpected = sorted(
            name for name in names
            if any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
        )
        if unexpected:
            raise ValueError("legacy or repository-only files entered release: " + ", ".join(unexpected))
        missing = sorted(REQUIRED - names)
        if missing:
            raise ValueError("release is missing: " + ", ".join(missing))

        def read(name: str) -> bytes:
            member = bundle.getmember(name)
            if not member.isfile():
                raise ValueError("release requires a regular file: " + name)
            with bundle.extractfile(member) as source:
                return source.read()

        manifest = json.loads(read(".codex-plugin/plugin.json"))
        if not isinstance(manifest, dict) or manifest.get("name") != "confidence-protocol":
            raise ValueError("archived manifest does not identify Confidence Protocol")
        version = manifest.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("archived manifest needs a non-empty version")

        tree = ast.parse(read("skills/confidence-protocol/scripts/diagnostics.py"))
        versions = []
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            if any(isinstance(target, ast.Name) and target.id == "TOOL_VERSION" for target in targets):
                if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                    raise ValueError("archived TOOL_VERSION must be a literal string")
                versions.append(node.value.value)
        if len(versions) != 1:
            raise ValueError("archive needs exactly one literal TOOL_VERSION assignment")
        if versions[0] != version:
            raise ValueError("archived manifest version does not match archived TOOL_VERSION")
        return len(names)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    archive = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout
    try:
        count = validate_archive(archive)
    except (ValueError, SyntaxError, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error
    print(f"release archive is clean ({count} entries)")


if __name__ == "__main__":
    main()
