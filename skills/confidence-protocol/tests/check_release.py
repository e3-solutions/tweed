#!/usr/bin/env python3
"""Fail when the shipped archive contains old Tweed or repository-only files."""

import io
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
archive = subprocess.run(
    ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"],
    capture_output=True,
    check=True,
).stdout
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    names = set(bundle.getnames())

forbidden_prefixes = (
    "bonaparte",
    "autoresearch",
    "workflows/",
    "skills/use-bonaparte/",
    "skills/confidence-protocol/tests/",
    ".confidence/",
)
unexpected = sorted(
    name for name in names if any(name.startswith(prefix) for prefix in forbidden_prefixes)
)
if unexpected:
    raise SystemExit("legacy or repository-only files entered release: " + ", ".join(unexpected))

required = {
    ".codex-plugin/plugin.json",
    "CHANGELOG.md",
    "README.md",
    "skills/confidence-protocol/SKILL.md",
    "skills/confidence-protocol/scripts/confidence.py",
    "skills/confidence-protocol/scripts/diagnostics.py",
}
missing = sorted(required - names)
if missing:
    raise SystemExit("release is missing: " + ", ".join(missing))

manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
if manifest.get("name") != "confidence-protocol":
    raise SystemExit("manifest does not identify Confidence Protocol")

print(f"release archive is clean ({len(names)} entries)")
