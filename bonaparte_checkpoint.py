"""Private atomic storage for durable per-phase Bonaparte run ledgers."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from bonaparte_progress import (
    PROGRESS_ACTIVITIES as SEMANTIC_ACTIVITIES,
    PROGRESS_MAX_MILESTONES as MAX_SEMANTIC_MILESTONES,
    PROGRESS_STAGES as SEMANTIC_STAGES,
    PROGRESS_STATUSES as SEMANTIC_STATUSES,
)

VERSION = 4
DEFAULT_SOFT_PHASE_BUDGET_SECONDS = 300.0
MAX_BYTES = 1 << 20
MAX_SEMANTIC_COUNT = 2**31 - 1
STATUSES = {
    "starting",
    "running",
    "finalizing",
    "waiting-input",
    "failed-resumable",
    "completed",
    "blocked",
    "failed-terminal",
}
RESUMABLE_STATUSES = {"waiting-input", "failed-resumable"}
TERMINAL_STATUSES = {"completed", "blocked", "failed-terminal"}
PENDING_ANSWER_STATES = {"none", "pending", "delivering", "delivered"}
PHASES = {"create", "rca", "scope", "implement", "review", "publish"}
SEMANTIC_FIELDS = {"stage", "actor", "activity", "status", "count"}
_SUBAGENT_ACTOR = re.compile(r"subagent-([1-9][0-9]{0,9})\Z")
_DIRECT_CONTACT = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
_SECRET_TEXT = re.compile(
    r"(?i)(?:authorization\s*:\s*(?:bearer|basic)\s+\S+|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:sk|ghp|github_pat|xox[baprs])-[_A-Za-z0-9-]{8,}|"
    r"aws_secret_access_key\s*[=:]\s*\S+|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*[=:]\s*[^\s,;]+)"
)
_PRIVATE_URL = re.compile(
    r"(?i)https?://(?:[^\s/@]+@)?(?:localhost|127(?:\.\d{1,3}){3}|"
    r"10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|[^\s/]+\.(?:internal|local))"
)

V1_FIELDS = {
    "version",
    "token",
    "status",
    "phase",
    "worktree",
    "git_dir",
    "base_head",
    "identity_head",
    "model",
    "reasoning",
    "question",
    "pending_answer",
    "receipt",
    "branch",
    "files_changed",
    "files_changed_total_count",
    "files_changed_truncated",
    "checks_completed",
    "checks_completed_total_count",
    "checks_completed_truncated",
    "activity",
    "blocker",
    "remote_state_changed",
    "updated_at",
}
V2_FIELDS = V1_FIELDS | {
    "semantic",
    "semantic_milestones",
    "semantic_milestones_total_count",
    "semantic_milestones_truncated",
}
V3_FIELDS = V2_FIELDS | {"soft_phase_budget_seconds"}
FIELDS = V3_FIELDS | {
    "phase_token",
    "native_thread_id",
    "native_turn_id",
    "protocol",
    "runtime",
    "capabilities",
    "pending_answer_state",
    "final_receipt",
}


def canonical_token(value: object, label: str = "checkpoint token") -> str:
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (AttributeError, ValueError) as error:
        raise RuntimeError(f"{label} must be a canonical UUID") from error
    return value


def bonaparte_home(runtime_file=None, environ=None) -> Path:
    runtime = Path(runtime_file or __file__).resolve().parent
    if runtime.parent.name == "releases":
        return runtime.parent.parent
    environment = os.environ if environ is None else environ
    if environment.get("BONAPARTE_HOME"):
        return Path(environment["BONAPARTE_HOME"]).expanduser()
    data = environment.get("XDG_DATA_HOME")
    if not data:
        data = Path(environment.get("HOME") or Path.home()) / ".local/share"
    return Path(data).expanduser() / "bonaparte"


def checkpoint_directory(home=None) -> Path:
    directory = Path(home or bonaparte_home()).expanduser() / "checkpoints"
    try:
        if directory.is_symlink():
            raise RuntimeError("checkpoint directory must not be a symlink")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        descriptor = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise RuntimeError("checkpoint path is not a directory")
        finally:
            os.close(descriptor)
    except RuntimeError:
        raise
    except OSError as error:
        raise RuntimeError("checkpoint directory is unavailable") from error
    return directory


def checkpoint_path(token, home=None, *, ensure_directory=True) -> Path:
    directory = (
        checkpoint_directory(home)
        if ensure_directory
        else Path(home or bonaparte_home()).expanduser() / "checkpoints"
    )
    return directory / f"{canonical_token(token)}.json"


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError, UnicodeError) as error:
        raise RuntimeError("checkpoint is not valid JSON") from error


def validate_serialization_privacy(value: object, label: str = "serialized value") -> None:
    """Reject secret-like, direct-contact, and private-endpoint free text."""
    pending = [value]
    while pending:
        candidate = pending.pop()
        if isinstance(candidate, dict):
            pending.extend(candidate.values())
        elif isinstance(candidate, (list, tuple)):
            pending.extend(candidate)
        elif isinstance(candidate, str):
            if any(ord(character) < 32 and character not in "\n\t" for character in candidate):
                raise RuntimeError(f"{label} failed privacy validation")
            if (
                _DIRECT_CONTACT.search(candidate)
                or _SECRET_TEXT.search(candidate)
                or _PRIVATE_URL.search(candidate)
            ):
                raise RuntimeError(f"{label} failed privacy validation")


def _validate_semantic(value: object, label: str) -> None:
    if not isinstance(value, dict) or set(value) != SEMANTIC_FIELDS:
        raise RuntimeError(f"checkpoint {label} is invalid")
    if not isinstance(value["stage"], str) or value["stage"] not in SEMANTIC_STAGES:
        raise RuntimeError(f"checkpoint {label} stage is invalid")
    actor = value["actor"]
    if actor is not None and actor != "coordinator":
        match = _SUBAGENT_ACTOR.fullmatch(actor) if isinstance(actor, str) else None
        if match is None or int(match.group(1)) > MAX_SEMANTIC_COUNT:
            raise RuntimeError(f"checkpoint {label} actor is invalid")
    activity = value["activity"]
    if activity is not None and (
        not isinstance(activity, str) or activity not in SEMANTIC_ACTIVITIES
    ):
        raise RuntimeError(f"checkpoint {label} activity is invalid")
    status = value["status"]
    if status is not None and (
        not isinstance(status, str) or status not in SEMANTIC_STATUSES
    ):
        raise RuntimeError(f"checkpoint {label} status is invalid")
    if value["count"] is not None and (
        type(value["count"]) is not int
        or not 0 <= value["count"] <= MAX_SEMANTIC_COUNT
    ):
        raise RuntimeError(f"checkpoint {label} count is invalid")


def _validate_common(value: dict, token=None) -> None:
    if token is not None and canonical_token(value["token"]) != canonical_token(token):
        raise RuntimeError("checkpoint token does not match its path")
    canonical_token(value["token"])
    if (
        not isinstance(value["status"], str)
        or value["status"] not in STATUSES
        or not isinstance(value["phase"], str)
        or value["phase"] not in PHASES
    ):
        raise RuntimeError("checkpoint state is invalid")
    for field in ("worktree", "git_dir", "reasoning", "updated_at"):
        if (
            not isinstance(value[field], str)
            or not value[field]
            or "\0" in value[field]
        ):
            raise RuntimeError(f"checkpoint {field} must be non-empty text")
    for field in (
        "base_head",
        "identity_head",
        "model",
        "question",
        "pending_answer",
        "branch",
        "activity",
        "blocker",
    ):
        if value[field] is not None and not isinstance(value[field], str):
            raise RuntimeError(f"checkpoint {field} must be text or null")
    if value["status"] == "waiting-input" and not value["question"]:
        raise RuntimeError("waiting-input checkpoint is missing its question")
    if not isinstance(value["receipt"], dict):
        raise RuntimeError("checkpoint receipt must be an object")  # noqa: TRY004
    remote = value["remote_state_changed"]
    if remote is not None and type(remote) is not bool:
        raise RuntimeError("checkpoint remote state must be boolean or null")
    for field in ("files_changed", "checks_completed"):
        items, total, truncated = (
            value[field],
            value[f"{field}_total_count"],
            value[f"{field}_truncated"],
        )
        if (
            not isinstance(items, list)
            or type(total) is not int
            or total < len(items)
            or type(truncated) is not bool
            or (not truncated and total != len(items))
        ):
            raise RuntimeError(f"checkpoint {field} inventory is invalid")
    if value.get("version") == VERSION:
        for check in value["checks_completed"]:
            if (
                not isinstance(check, dict)
                or set(check) != {"kind", "status", "exit"}
                or check["kind"] not in {"test", "lint", "build", "check"}
                or check["status"] not in {"passed", "failed"}
                or (
                    check["exit"] is not None
                    and (type(check["exit"]) is not int or not -255 <= check["exit"] <= 255)
                )
            ):
                raise RuntimeError("checkpoint check evidence is invalid")


def _validate_metadata(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"checkpoint {label} metadata must be an object")
    try:
        _json_bytes(value)
    except RuntimeError as error:
        raise RuntimeError(f"checkpoint {label} metadata is invalid") from error


def is_resume_eligible(value: dict) -> bool:
    """Return whether a validated ledger may enter the native resume path."""

    validate(value)
    return value["status"] in RESUMABLE_STATUSES


def authoritative_receipt(value: dict) -> dict | None:
    """Return only a terminal receipt committed by the durable ledger."""

    validate(value)
    if value["status"] not in TERMINAL_STATUSES:
        return None
    return dict(value["final_receipt"])


def _validate_soft_phase_budget(value: object) -> None:
    if type(value) not in (int, float):
        raise RuntimeError(
            "checkpoint soft phase budget must be a positive finite number"
        )
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise RuntimeError(
            "checkpoint soft phase budget must be a positive finite number"
        )


def validate(value: object, token=None) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise RuntimeError("checkpoint envelope is invalid")
    if type(value["version"]) is not int or value["version"] != VERSION:
        raise RuntimeError("checkpoint version is invalid")
    _validate_common(value, token)
    _validate_soft_phase_budget(value["soft_phase_budget_seconds"])
    canonical_token(value["phase_token"], "phase token")
    for field in ("native_thread_id", "native_turn_id"):
        identity = value[field]
        if identity is not None and (
            not isinstance(identity, str) or not identity or "\0" in identity
        ):
            raise RuntimeError(f"checkpoint {field} must be non-empty text or null")
    for field in ("protocol", "runtime", "capabilities"):
        _validate_metadata(value[field], field)
    answer_state = value["pending_answer_state"]
    if answer_state not in PENDING_ANSWER_STATES:
        raise RuntimeError("checkpoint pending answer state is invalid")
    if answer_state in {"pending", "delivering"} and not value["pending_answer"]:
        raise RuntimeError("checkpoint pending answer state is missing its answer")
    if answer_state in {"none", "delivered"} and value["pending_answer"] is not None:
        raise RuntimeError("checkpoint pending answer state conflicts with its answer")
    final_receipt = value["final_receipt"]
    if value["status"] in TERMINAL_STATUSES:
        if not isinstance(final_receipt, dict):
            raise RuntimeError("terminal checkpoint is missing its final receipt")
    elif final_receipt is not None:
        raise RuntimeError("non-terminal checkpoint has a final receipt")
    if value["semantic"] is not None:
        _validate_semantic(value["semantic"], "semantic snapshot")
    milestones = value["semantic_milestones"]
    total = value["semantic_milestones_total_count"]
    truncated = value["semantic_milestones_truncated"]
    if (
        not isinstance(milestones, list)
        or len(milestones) > MAX_SEMANTIC_MILESTONES
        or type(total) is not int
        or not len(milestones) <= total <= MAX_SEMANTIC_COUNT
        or type(truncated) is not bool
        or (not truncated and total != len(milestones))
    ):
        raise RuntimeError("checkpoint semantic milestone inventory is invalid")
    for milestone in milestones:
        _validate_semantic(milestone, "semantic milestone")
    validate_serialization_privacy(value, "checkpoint")
    if len(_json_bytes(value)) > MAX_BYTES:
        raise RuntimeError("checkpoint exceeds 1 MiB")
    return value


def _normalize_read(value: object, token: str) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError("checkpoint envelope is invalid")
    version = value.get("version")
    if type(version) is int and version == 1 and set(value) == V1_FIELDS:
        _validate_common(value, token)
        normalized = dict(value)
        normalized.update(
            soft_phase_budget_seconds=DEFAULT_SOFT_PHASE_BUDGET_SECONDS,
            semantic=None,
            semantic_milestones=[],
            semantic_milestones_total_count=0,
            semantic_milestones_truncated=False,
        )
        return validate(_upgrade_legacy(normalized), token)
    if type(version) is int and version == 2 and set(value) == V2_FIELDS:
        _validate_common(value, token)
        normalized = dict(value)
        normalized.update(soft_phase_budget_seconds=DEFAULT_SOFT_PHASE_BUDGET_SECONDS)
        return validate(_upgrade_legacy(normalized), token)
    if type(version) is int and version == 3 and set(value) == V3_FIELDS:
        _validate_common(value, token)
        _validate_soft_phase_budget(value["soft_phase_budget_seconds"])
        return validate(_upgrade_legacy(value), token)
    return validate(value, token)


def _upgrade_legacy(value: dict) -> dict:
    normalized = dict(value)
    terminal = normalized["status"] in {"completed", "blocked"}
    legacy_check_total = normalized.get("checks_completed_total_count", 0)
    normalized.update(
        version=VERSION,
        phase_token=normalized["token"],
        native_thread_id=normalized["token"],
        native_turn_id=None,
        protocol={
            "legacy_checkpoint_version": value["version"],
            "initial_remote": {"status": "legacy-unavailable"},
        },
        runtime={},
        capabilities={},
        pending_answer_state=("pending" if normalized["pending_answer"] else "none"),
        final_receipt=(dict(normalized["receipt"]) if terminal else None),
        checks_completed=[],
        checks_completed_total_count=legacy_check_total,
        checks_completed_truncated=bool(legacy_check_total),
    )
    return normalized


def _open_regular(path: Path, flags: int, mode=0o600) -> int:
    try:
        descriptor = os.open(
            path,
            flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            mode,
        )
    except OSError as error:
        raise RuntimeError("checkpoint file is unavailable") from error
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RuntimeError("checkpoint path is not a regular file")
    return descriptor


def read_checkpoint(token, home=None, *, active_only=False) -> dict:
    canonical = canonical_token(token)
    with os.fdopen(
        _open_regular(checkpoint_path(canonical, home), os.O_RDONLY), "rb"
    ) as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise RuntimeError("checkpoint exceeds 1 MiB")
    try:
        checkpoint = _normalize_read(json.loads(payload.decode("utf-8")), canonical)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("checkpoint JSON is invalid") from error
    if active_only and checkpoint["status"] not in RESUMABLE_STATUSES:
        raise RuntimeError("checkpoint is not resumable")
    return checkpoint


def write_checkpoint(checkpoint: dict, home=None) -> Path:
    payload = _json_bytes(validate(checkpoint))
    directory = checkpoint_directory(home)
    destination = directory / f"{checkpoint['token']}.json"
    descriptor, name = tempfile.mkstemp(prefix=".checkpoint-", dir=directory)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return destination


@contextmanager
def checkpoint_lease(token, home=None):
    canonical = canonical_token(token)
    path = checkpoint_directory(home) / f"{canonical}.lock"
    descriptor = _open_regular(path, os.O_RDWR | os.O_CREAT)
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("checkpoint is already active") from error
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
