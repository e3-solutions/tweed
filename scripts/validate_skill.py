#!/usr/bin/env python3
"""Minimal repository-owned validation for the bundled Codex skill."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_skill.py SKILL_DIRECTORY")
    root = Path(sys.argv[1])
    skill = root / "SKILL.md"
    agent = root / "agents/openai.yaml"
    text = skill.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(?P<header>.*?)\n---\n(?P<body>.+)", text, re.DOTALL)
    if not match:
        raise SystemExit("SKILL.md must contain YAML frontmatter and a body")
    fields = {}
    for line in match.group("header").splitlines():
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise SystemExit("SKILL.md frontmatter must use nonempty key: value fields")
        fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"}:
        raise SystemExit("SKILL.md frontmatter must contain only name and description")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"]):
        raise SystemExit("skill name is invalid")
    if len(fields["description"]) > 1024:
        raise SystemExit("skill description is too long")
    body = match.group("body")
    for required in ("Run exactly one command", "at most 4 KiB", "retry-sync"):
        if required not in body:
            raise SystemExit(f"SKILL.md is missing required text: {required}")
    agent_text = agent.read_text(encoding="utf-8")
    for required in ("display_name:", "short_description:", "default_prompt:"):
        if required not in agent_text:
            raise SystemExit(f"openai.yaml is missing {required}")
    print("Skill is valid!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
