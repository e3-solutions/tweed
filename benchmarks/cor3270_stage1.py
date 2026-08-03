#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["openai-codex==0.144.4"]
# ///
"""Replay the immutable sanitized COR-3270 snapshot topology."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures/cor3270.json"


def load_tweed(path: Path):
    root = str(path.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    loader = importlib.machinery.SourceFileLoader("benchmark_tweed", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def padded(prefix: str, byte_length: int) -> str:
    encoded = prefix.encode("utf-8")
    if len(encoded) > byte_length:
        raise RuntimeError("sanitized fixture prefix exceeds preserved byte length")
    return prefix + ("x" * (byte_length - len(encoded)))


def fixture_issue(tweed, spec: dict, index: int) -> dict:
    metadata = dict(spec["metadata"])
    metadata["repository"] = padded("/fixture/repository", spec["repository_bytes"])
    bodies = {
        "request": "# Request\n\nSanitized COR-3270 request fixture.\n",
        "implementation": (
            "Status: implemented\n\n## Verification\n\n- sanitized fixture\n"
        ),
    }
    if "scope" in spec["section_bytes"]:
        evidence = padded(
            "## Repository state\n\n- `fixture.txt` → `sha256:"
            + ("0" * 64)
            + "`",
            spec["evidence_bytes"],
        )
        bodies["scope"] = padded(
            "Status: scoped\n\n" + evidence + "\n\n## Scope\n\nSanitized fixture.",
            spec["section_bytes"]["scope"],
        )
    description = tweed.metadata_block(metadata)
    for name, body_bytes in spec["section_bytes"].items():
        description += "\n\n" + tweed.section_block(
            name, padded(bodies[name], body_bytes)
        )
    description += "\n"
    description = padded(description, spec["snapshot_bytes"])
    issue = {
        "issue_id": "12345678-1234-4123-8123-123456789abc",
        "identifier": "COR-3270",
        "url": padded("https://linear.example/COR-3270", spec["url_bytes"]),
        "title": padded("Sanitized COR-3270 title", spec["title_bytes"]),
        "description": description,
    }
    snapshot = tweed.journal.validate_snapshot(
        description=description,
        comments=[],
        issue_identifier=issue["identifier"],
        expected_repository=metadata["repository"],
    )
    issue["revision"] = (
        snapshot.records[-1].digest if snapshot.records else snapshot.genesis.digest
    )
    issue["genesis_digest"] = snapshot.genesis.digest
    issue["digest"] = tweed.digest(description)
    transport = {
        "id": issue["issue_id"],
        "identifier": issue["identifier"],
        "url": issue["url"],
        "title": issue["title"],
        "description": description,
        "updatedAt": f"sanitized-{index}",
        "team": {"id": "team-fixture", "key": "COR"},
        "project": {"id": "project-fixture", "name": "Negotiation"},
        "comments": [],
    }
    transport["content_digest"] = tweed.transport_content_digest(transport)
    transport["snapshot_digest"] = tweed.transport_snapshot_digest(transport)
    issue["content_digest"] = transport["content_digest"]
    issue["snapshot_digest"] = transport["snapshot_digest"]
    issue["transport_snapshot"] = transport
    return issue


def packet_metrics(tweed, fixture: dict) -> dict:
    rows = []
    started = time.perf_counter()
    for index, spec in enumerate(fixture["runs"], 1):
        name = spec["phase"]
        issue = fixture_issue(tweed, spec, index)
        phase = tweed.PHASES[name]
        replay_id = f"tw_{index:016x}"
        workflow = tweed.load_workflow(phase.workflow)
        tweed.freeze_linear_snapshot(replay_id, issue, workflow)
        packet = tweed.build_phase_packet(replay_id, issue, phase)
        prompt = tweed.phase_prompt(issue, phase, packet)
        old_prompt = (
            f"Execute only the {phase.command} phase for Linear issue "
            f"{issue['identifier']}. The runner has just read the issue from Linear "
            "and frozen the exact snapshot below. Do not use Linear write tools. "
            "Return the required structured result. If a material question is necessary, "
            "set status to needs-input, populate question, and put only a short "
            "clarification record in report_markdown. Otherwise question must be null.\n\n"
            f"Issue URL: {issue['url']}\nTitle: {issue['title']}\n\n"
            f"Exact description snapshot:\n{issue['description']}"
        )
        manifest = tweed.load_artifact_manifest(replay_id)
        rows.append(
            {
                "phase": name,
                "snapshot_bytes": len(issue["description"].encode()),
                "old_prompt_bytes": len(old_prompt.encode()),
                "new_prompt_bytes": len(prompt.encode()),
                "referenced_artifact_bytes": sum(
                    artifact["bytes"] for artifact in packet["artifacts"]
                ),
                "artifact_store_bytes": sum(
                    {
                        entry["sha256"]: entry["bytes"]
                        for entry in manifest["artifacts"].values()
                    }.values()
                ),
            }
        )
    return {
        "transform_wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "phases": rows,
        "totals": {
            key: sum(row[key] for row in rows)
            for key in (
                "snapshot_bytes",
                "old_prompt_bytes",
                "new_prompt_bytes",
                "referenced_artifact_bytes",
                "artifact_store_bytes",
            )
        },
    }


def stable_replay(replay: dict) -> dict:
    return {key: value for key, value in replay.items() if key != "transform_wall_ms"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tweed", type=Path, default=Path(__file__).parents[1] / "tweed")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument(
        "--no-verify", action="store_true", help="print drift instead of failing"
    )
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="tweed-stage1-", dir="/tmp") as directory:
        os.environ["TWEED_STATE_HOME"] = directory
        tweed = load_tweed(args.tweed.resolve())
        replay = packet_metrics(tweed, fixture)
    matches = stable_replay(replay) == fixture["expected_replay"]
    result = {
        "fixture": fixture["name"],
        "source_snapshot_digests": fixture["source_snapshot_digests"],
        "run_ids": {row["phase"]: row["run_id"] for row in fixture["runs"]},
        "baseline": fixture["baseline"],
        "replay": replay,
        "actual_hermetic_measurement": {
            "wall_ms": replay["transform_wall_ms"],
            "child_task_count": 0,
            "model_powered_linear_transport_task_count": 0,
            "prompt_bytes": replay["totals"]["new_prompt_bytes"],
            "referenced_artifact_bytes": replay["totals"][
                "referenced_artifact_bytes"
            ],
            "artifact_store_bytes": replay["totals"]["artifact_store_bytes"],
            "live_linear_requests": 0,
            "live_linear_reason": "LINEAR_API_KEY not configured",
        },
        "stable_replay_matches_fixture": matches,
        "exact_aggregate_model_tokens": None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not matches and not args.no_verify:
        print("stable replay metrics drifted from the committed fixture", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
