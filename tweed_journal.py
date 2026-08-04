"""Deterministic, append-only Linear journal primitives for Tweed.

This module deliberately has no Linear transport code.  It constructs and validates
the exact descriptions and comment bodies that a transport may read or append.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


PROTOCOL = "dev.tweed.linear-journal.v2"
META_START = "<!-- tweed:metadata:start -->"
META_END = "<!-- tweed:metadata:end -->"
RECORD_START = "<!-- tweed:journal:v2:start -->"
RECORD_END = "<!-- tweed:journal:v2:end -->"
GENESIS_TOKEN = "tweed-genesis-v2:"
RECORD_TOKEN = "tweed-journal-v2:"
RUN_RE = re.compile(r"tw_[a-f0-9]{16}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
COMMIT_RE = re.compile(r"[a-f0-9]{40,64}\Z")
UUID4_RE = re.compile(
    r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}\Z"
)

TRANSITIONS = {
    "root-cause": ("rca", "needs-rca", "needs-scope", "established"),
    "scope": ("scope", "needs-scope", "ready-to-implement", "scoped"),
    "implement": (
        "implementation",
        "ready-to-implement",
        "ready-to-review",
        "implemented",
    ),
    "review": ("review", "ready-to-review", "ready-to-merge", "reviewed"),
}
PHASE_ORDER = tuple(TRANSITIONS)
SECTION_TO_PHASE = {value[0]: phase for phase, value in TRANSITIONS.items()}


class JournalError(RuntimeError):
    """The Linear journal is malformed, divergent, or incompatible."""


@dataclass(frozen=True)
class Genesis:
    description: str
    metadata: dict[str, Any]
    request: str
    request_block: str
    digest: str
    initial_stage: str


@dataclass(frozen=True)
class Record:
    metadata: dict[str, Any]
    report: str
    digest: str
    comment: str
    synthetic: bool = False


@dataclass(frozen=True)
class Snapshot:
    genesis: Genesis
    records: tuple[Record, ...]
    stage: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _token_encode(value: Mapping[str, Any]) -> str:
    raw = canonical_json(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _token_decode(value: str, label: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
        decoded = raw.decode("utf-8")
        result = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JournalError(f"invalid {label} token") from error
    if not isinstance(result, dict) or canonical_json(result) != decoded:
        raise JournalError(f"noncanonical {label} token")
    return result


def _find_token(text: str, prefix: str, label: str) -> dict[str, Any] | None:
    occurrences = text.count(prefix)
    if occurrences == 0:
        return None
    if occurrences != 1:
        raise JournalError(f"{label} must contain exactly one protocol token")
    matches = re.findall(re.escape(prefix) + r"([A-Za-z0-9_-]+)", text)
    if len(matches) != 1:
        raise JournalError(f"invalid {label} token")
    return _token_decode(matches[0], label)


def deterministic_comment_id(seed: str | bytes) -> str:
    """Return a deterministic UUID-v4-shaped identifier without randomness."""
    raw = hashlib.sha256(seed.encode("utf-8") if isinstance(seed, str) else seed).digest()
    octets = bytearray(raw[:16])
    octets[6] = (octets[6] & 0x0F) | 0x40
    octets[8] = (octets[8] & 0x3F) | 0x80
    value = octets.hex()
    return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"


def _marker_count(text: str, marker: str) -> int:
    return sum(line == marker for line in text.splitlines())


def _strict_block(text: str, start: str, end: str, label: str) -> tuple[str, str]:
    # Marker-like text that is indented or embedded is malformed, not human prose.
    if start in text and _marker_count(text, start) != text.count(start):
        raise JournalError(f"malformed {label} start marker")
    if end in text and _marker_count(text, end) != text.count(end):
        raise JournalError(f"malformed {label} end marker")
    if _marker_count(text, start) != 1 or _marker_count(text, end) != 1:
        raise JournalError(f"{label} must contain exactly one marker pair")
    start_at = text.find(start)
    end_at = text.find(end, start_at + len(start))
    if end_at < 0 or end_at < start_at:
        raise JournalError(f"malformed {label} marker order")
    content_at = start_at + len(start)
    if text[content_at : content_at + 1] != "\n" or text[end_at - 1 : end_at] != "\n":
        raise JournalError(f"{label} markers require LF boundaries")
    return text[content_at + 1 : end_at - 1], text[start_at : end_at + len(end)]


def _metadata_from_block(block: str) -> dict[str, Any]:
    match = re.fullmatch(r"## Tweed\n\n```json\n(?P<json>\{.*\})\n```", block, re.DOTALL)
    if not match:
        raise JournalError("invalid Tweed metadata envelope")
    try:
        value = json.loads(match.group("json"))
    except json.JSONDecodeError as error:
        raise JournalError("invalid Tweed metadata JSON") from error
    if not isinstance(value, dict):
        raise JournalError("Tweed metadata must be an object")
    return value


def _section(description: str, name: str, *, required: bool = False) -> tuple[str, str] | None:
    start = f"<!-- tweed:{name}:start -->"
    end = f"<!-- tweed:{name}:end -->"
    present = start in description or end in description
    if not present and not required:
        return None
    return _strict_block(description, start, end, f"Tweed {name} section")


def _root_digest(metadata_block: str, request_block: str) -> str:
    return sha256_bytes(
        b"dev.tweed.genesis.v2\0"
        + metadata_block.encode("utf-8")
        + b"\0"
        + request_block.encode("utf-8")
    )


def parse_genesis(description: str) -> Genesis:
    token = _find_token(description, GENESIS_TOKEN, "Tweed genesis")
    if token is not None:
        if set(token) != {"metadata", "request"}:
            raise JournalError("Tweed genesis token has invalid fields")
        metadata = token["metadata"]
        request = token["request"]
        if not isinstance(metadata, dict) or not isinstance(request, str) or not request:
            raise JournalError("Tweed genesis token has invalid values")
        if metadata.get("schema_version") != 1:
            raise JournalError("unsupported Tweed metadata schema")
        if metadata.get("kind") not in {"problem", "feature"}:
            raise JournalError("invalid Tweed issue kind")
        if metadata.get("request_digest") != sha256_text(request):
            raise JournalError("protected request digest does not match")
        request_block = (
            "<!-- tweed:request:start -->\n"
            + request
            + "\n<!-- tweed:request:end -->"
        )
        digest_value = sha256_bytes(
            b"dev.tweed.genesis.v2\0" + canonical_json(token).encode("utf-8")
        )
        initial_stage = "needs-rca" if metadata["kind"] == "problem" else "needs-scope"
        return Genesis(
            description=description,
            metadata=dict(metadata),
            request=request,
            request_block=request_block,
            digest=digest_value,
            initial_stage=initial_stage,
        )
    metadata_body, metadata_block = _strict_block(
        description, META_START, META_END, "Tweed metadata"
    )
    metadata = _metadata_from_block(metadata_body)
    if metadata.get("schema_version") != 1:
        raise JournalError("unsupported Tweed metadata schema")
    if metadata.get("kind") not in {"problem", "feature"}:
        raise JournalError("invalid Tweed issue kind")
    request_section = _section(description, "request", required=True)
    assert request_section is not None
    request, request_block = request_section
    request_hash = sha256_text(request_block)
    declared = metadata.get("request_digest")
    if declared is not None and declared != request_hash:
        raise JournalError("protected request digest does not match")
    initial_stage = "needs-rca" if metadata["kind"] == "problem" else "needs-scope"
    return Genesis(
        description=description,
        metadata=metadata,
        request=request,
        request_block=request_block,
        digest=_root_digest(metadata_block, request_block),
        initial_stage=initial_stage,
    )


def build_genesis_description(metadata: Mapping[str, Any], request: str) -> str:
    """Build a normalization-independent token plus a visible original request."""
    if "request_digest" in metadata:
        raise JournalError("request_digest is derived and must not be supplied")
    request = request.strip()
    value = dict(metadata)
    value["request_digest"] = sha256_text(request)
    token = _token_encode({"metadata": value, "request": request})
    return (
        f"{request}\n\n---\n\n"
        "Tweed phase handoffs are appended as human-readable comments. The "
        "workflow state is derived from their validated journal.\n\n"
        f"`{GENESIS_TOKEN}{token}`\n"
    )


def _record_digest(metadata: Mapping[str, Any], report: str) -> str:
    unsigned = {key: value for key, value in metadata.items() if key != "record_digest"}
    return sha256_bytes(
        PROTOCOL.encode("ascii")
        + b"\0"
        + canonical_json(unsigned).encode("utf-8")
        + b"\0"
        + report.encode("utf-8")
    )


def build_record(
    *,
    issue_identifier: str,
    run_id: str,
    phase: str,
    status: str,
    artifact_digest: str,
    predecessor_digest: str,
    genesis_digest: str,
    repository: str,
    base_commit: str,
    branch: str | None,
    commit: str | None,
    report: str,
) -> Record:
    if phase not in TRANSITIONS:
        raise JournalError(f"unknown phase: {phase}")
    _section_name, from_stage, to_stage, legal_status = TRANSITIONS[phase]
    if status != legal_status:
        raise JournalError(f"illegal completed status for {phase}: {status}")
    base = {
        "protocol": PROTOCOL,
        "issue_identifier": issue_identifier,
        "run_id": run_id,
        "phase": phase,
        "status": status,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "artifact_digest": artifact_digest,
        "predecessor_digest": predecessor_digest,
        "genesis_digest": genesis_digest,
        "repository": repository,
        "base_commit": base_commit,
        "branch": branch,
        "commit": commit,
    }
    identity = "\0".join((PROTOCOL, issue_identifier, run_id, phase))
    base["comment_id"] = deterministic_comment_id(identity)
    base["record_digest"] = _record_digest(base, report)
    _validate_record_fields(base, report)
    comment = build_comment(base, report)
    return Record(dict(base), report, base["record_digest"], comment)


def build_comment(metadata: Mapping[str, Any], report: str) -> str:
    token = _token_encode(
        {
            "metadata": dict(metadata),
            "report_b64": base64.urlsafe_b64encode(report.encode("utf-8"))
            .decode("ascii")
            .rstrip("="),
        }
    )
    return f"{report}\n\n`{RECORD_TOKEN}{token}`"


def _validate_record_fields(metadata: Mapping[str, Any], report: str) -> None:
    required = {
        "protocol", "comment_id", "issue_identifier", "run_id", "phase", "status",
        "from_stage", "to_stage", "artifact_digest", "predecessor_digest",
        "genesis_digest", "repository", "base_commit", "branch", "commit",
        "record_digest",
    }
    if set(metadata) != required:
        raise JournalError("journal record has missing or unknown fields")
    phase = metadata.get("phase")
    if phase not in TRANSITIONS:
        raise JournalError("journal record has unknown phase")
    _section_name, from_stage, to_stage, status = TRANSITIONS[phase]
    if (metadata.get("from_stage"), metadata.get("to_stage"), metadata.get("status")) != (
        from_stage, to_stage, status
    ):
        raise JournalError("journal record has an illegal transition")
    if metadata.get("protocol") != PROTOCOL:
        raise JournalError("unsupported journal protocol")
    if not isinstance(metadata.get("issue_identifier"), str) or not metadata["issue_identifier"]:
        raise JournalError("journal record has invalid issue identifier")
    if not isinstance(metadata.get("run_id"), str) or not RUN_RE.fullmatch(metadata["run_id"]):
        raise JournalError("journal record has invalid run id")
    if not isinstance(metadata.get("comment_id"), str) or not UUID4_RE.fullmatch(metadata["comment_id"]):
        raise JournalError("journal record has invalid comment id")
    for key in ("artifact_digest", "predecessor_digest", "genesis_digest", "record_digest"):
        if not isinstance(metadata.get(key), str) or not SHA_RE.fullmatch(metadata[key]):
            raise JournalError(f"journal record has invalid {key}")
    if not isinstance(metadata.get("repository"), str) or not metadata["repository"]:
        raise JournalError("journal record has invalid repository")
    if not isinstance(metadata.get("base_commit"), str) or not COMMIT_RE.fullmatch(metadata["base_commit"]):
        raise JournalError("journal record has invalid base commit")
    branch, commit = metadata.get("branch"), metadata.get("commit")
    if phase in {"implement", "review"}:
        if not isinstance(branch, str) or not branch or not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise JournalError("repository-writing phase requires branch and commit")
    elif branch is not None or commit is not None:
        raise JournalError("planning phase must not claim branch or commit")
    if not isinstance(report, str) or not report:
        raise JournalError("journal report must be non-empty")
    if metadata["artifact_digest"] != sha256_text(report):
        raise JournalError("artifact digest does not match exact report bytes")
    if metadata["record_digest"] != _record_digest(metadata, report):
        raise JournalError("record digest does not match exact envelope and report bytes")


def parse_comment(comment: str) -> Record | None:
    token = _find_token(comment, RECORD_TOKEN, "Tweed journal record")
    if token is None:
        if RECORD_START in comment or RECORD_END in comment:
            raise JournalError("unsupported legacy journal marker")
        return None
    if set(token) != {"metadata", "report_b64"} or not isinstance(
        token.get("metadata"), dict
    ) or not isinstance(token.get("report_b64"), str):
        raise JournalError("invalid journal record token fields")
    try:
        report = base64.urlsafe_b64decode(
            token["report_b64"] + ("=" * (-len(token["report_b64"]) % 4))
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise JournalError("invalid journal report encoding") from error
    metadata = token["metadata"]
    _validate_record_fields(metadata, report)
    return Record(metadata, report, metadata["record_digest"], comment)


def _legacy_records(genesis: Genesis, issue_identifier: str) -> list[Record]:
    metadata = genesis.metadata
    if "request_digest" in metadata:
        return []
    stage = metadata.get("stage")
    if stage not in {genesis.initial_stage, "needs-scope", "ready-to-implement", "ready-to-review", "ready-to-merge"}:
        raise JournalError("legacy metadata has an invalid stage")
    start = 0 if genesis.initial_stage == "needs-rca" else 1
    stage_order = [TRANSITIONS[name][1] for name in PHASE_ORDER[start:]] + ["ready-to-merge"]
    if stage not in stage_order:
        raise JournalError("legacy stage is impossible for issue kind")
    completed = stage_order.index(stage)
    if metadata.get("contract_revision") != completed:
        raise JournalError("legacy contract revision does not match stage")
    repository = metadata.get("repository")
    base = metadata.get("planning_base")
    if not isinstance(repository, str) or not repository or not isinstance(base, str) or not COMMIT_RE.fullmatch(base):
        raise JournalError("legacy metadata lacks repository/base provenance")
    records: list[Record] = []
    predecessor = genesis.digest
    for offset, phase in enumerate(PHASE_ORDER[start:]):
        section_name = TRANSITIONS[phase][0]
        section = _section(genesis.description, section_name)
        if offset >= completed:
            if section is not None:
                raise JournalError("legacy description contains a future phase section")
            continue
        if section is None:
            raise JournalError("legacy description is missing a completed phase section")
        report, _block = section
        run_id = "tw_" + sha256_text(f"legacy\0{genesis.digest}\0{phase}")[:16]
        branch = metadata.get("integration_branch") if phase in {"implement", "review"} else None
        commit = metadata.get("integration_commit") if phase in {"implement", "review"} else None
        record = build_record(
            issue_identifier=issue_identifier,
            run_id=run_id,
            phase=phase,
            status=TRANSITIONS[phase][3],
            artifact_digest=sha256_text(report),
            predecessor_digest=predecessor,
            genesis_digest=genesis.digest,
            repository=repository,
            base_commit=base,
            branch=branch,
            commit=commit,
            report=report,
        )
        records.append(Record(record.metadata, report, record.digest, record.comment, True))
        predecessor = record.digest
    return records


def _ordered_chain(records: Iterable[Record], root: str) -> list[Record]:
    by_digest = {record.digest: record for record in records}
    successors: dict[str, list[Record]] = {}
    for record in by_digest.values():
        successors.setdefault(record.metadata["predecessor_digest"], []).append(record)
    if any(len(values) > 1 for values in successors.values()):
        raise JournalError("journal contains a fork")
    # Detect cycles independently, including disconnected cycles.
    for record in by_digest.values():
        seen: set[str] = set()
        current = record
        while current.metadata["predecessor_digest"] in by_digest:
            if current.digest in seen:
                raise JournalError("journal contains a cycle")
            seen.add(current.digest)
            current = by_digest[current.metadata["predecessor_digest"]]
    ordered: list[Record] = []
    predecessor = root
    while predecessor in successors:
        record = successors[predecessor][0]
        ordered.append(record)
        predecessor = record.digest
    if len(ordered) != len(by_digest):
        raise JournalError("journal contains a dangling or missing predecessor")
    return ordered


def validate_snapshot(
    *,
    description: str,
    comments: Iterable[str],
    issue_identifier: str,
    expected_repository: str,
    expected_base_commit: str | None = None,
    expected_branch: str | None = None,
    expected_commits: Mapping[str, str] | None = None,
    expected_head_digest: str | None = None,
    expected_stage: str | None = None,
) -> Snapshot:
    genesis = parse_genesis(description)
    parsed: list[Record] = []
    by_id: dict[str, Record] = {}
    by_operation: dict[tuple[str, str], Record] = {}
    for comment in comments:
        record = parse_comment(comment)
        if record is None:
            continue
        comment_id = record.metadata["comment_id"]
        prior = by_id.get(comment_id)
        if prior is not None:
            if prior.comment != record.comment:
                raise JournalError("conflicting duplicate journal marker")
            continue
        operation = (record.metadata["run_id"], record.metadata["phase"])
        prior_operation = by_operation.get(operation)
        if prior_operation is not None:
            if prior_operation.comment != record.comment:
                raise JournalError("conflicting duplicate run/phase journal record")
            continue
        by_id[comment_id] = record
        by_operation[operation] = record
        parsed.append(record)
    if parsed and "request_digest" not in genesis.metadata:
        # A legacy description may be journalized only from its validated current prefix.
        adopted = _legacy_records(genesis, issue_identifier)
    else:
        adopted = _legacy_records(genesis, issue_identifier) if not parsed else []
    all_records = adopted + parsed
    for record in all_records:
        value = record.metadata
        if value["issue_identifier"] != issue_identifier:
            raise JournalError("journal record belongs to another issue")
        if value["genesis_digest"] != genesis.digest:
            raise JournalError("journal record has the wrong genesis")
        if value["repository"] != expected_repository:
            raise JournalError("journal record has the wrong repository")
        if expected_base_commit is not None and value["base_commit"] != expected_base_commit:
            raise JournalError("journal record has the wrong base commit")
        if expected_branch is not None and value["phase"] in {"implement", "review"} and value["branch"] != expected_branch:
            raise JournalError("journal record has the wrong branch")
        if expected_commits and value["phase"] in expected_commits and value["commit"] != expected_commits[value["phase"]]:
            raise JournalError("journal record has the wrong commit")
    ordered = _ordered_chain(all_records, genesis.digest)
    stage = genesis.initial_stage
    phases_seen: set[str] = set()
    effective_base = genesis.metadata.get("planning_base")
    if not isinstance(effective_base, str) or not COMMIT_RE.fullmatch(effective_base):
        raise JournalError("genesis has invalid planning base provenance")
    integration_branch: str | None = None
    for record in ordered:
        phase = record.metadata["phase"]
        if phase in phases_seen or record.metadata["from_stage"] != stage:
            raise JournalError("journal chain has an illegal phase transition")
        if phase == "scope":
            effective_base = record.metadata["base_commit"]
        elif record.metadata["base_commit"] != effective_base:
            raise JournalError("journal chain has divergent base provenance")
        if phase in {"implement", "review"}:
            branch = record.metadata["branch"]
            if integration_branch is None:
                integration_branch = branch
            elif branch != integration_branch:
                raise JournalError("journal chain has divergent branch provenance")
        phases_seen.add(phase)
        stage = record.metadata["to_stage"]
    head = ordered[-1].digest if ordered else genesis.digest
    if expected_head_digest is not None and head != expected_head_digest:
        raise JournalError("journal head does not match the frozen predecessor")
    if expected_stage is not None and stage != expected_stage:
        raise JournalError("journal stage does not match the frozen stage")
    return Snapshot(genesis, tuple(ordered), stage)


def materialize_snapshot(snapshot: Snapshot) -> dict[str, Any]:
    """Return a classic v1 human-readable description derived from the chain."""
    metadata = dict(snapshot.genesis.metadata)
    metadata["stage"] = snapshot.stage
    metadata["contract_revision"] = len(snapshot.records)
    for record in snapshot.records:
        if record.synthetic:
            continue
        value = record.metadata
        metadata["last_run"] = value["run_id"]
        if value["phase"] == "scope":
            metadata["planning_base"] = value["base_commit"]
        if value["branch"] is not None:
            metadata["integration_branch"] = value["branch"]
        if value["commit"] is not None:
            metadata["integration_commit"] = value["commit"]
    body = json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False)
    description = (
        f"{META_START}\n## Tweed\n\n```json\n{body}\n```\n{META_END}\n\n"
        f"{snapshot.genesis.request_block}\n"
    )
    reports: dict[str, str] = {}
    for record in snapshot.records:
        section = TRANSITIONS[record.metadata["phase"]][0]
        reports[section] = record.report
        description += f"\n<!-- tweed:{section}:start -->\n{record.report}\n<!-- tweed:{section}:end -->\n"
    return {"metadata": metadata, "description": description, "reports": reports}
