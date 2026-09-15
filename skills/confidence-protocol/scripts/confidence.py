#!/usr/bin/env python3
"""Create, validate, and render Confidence Protocol evidence files."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import html
import json
import math
import os
import re
import signal
import stat
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from diagnostics import (  # noqa: E402
    TOOL_VERSION,
    doctor_report,
    error_code_for,
    record_event,
    write_support_bundle,
)


MODES = ("quick", "standard", "critical")
TASK_TYPES = ("research", "bug", "feature", "refactor", "product", "security")
STATUSES = ("pass", "partial", "fail", "not_run")
REVIEW_ROLES = (
    "test_designer",
    "critic",
    "integration_reviewer",
    "adversarial_reviewer",
    "domain_reviewer",
    "security_reviewer",
)
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_TIMEOUT_SECONDS = 1800.0
DEFAULT_MAX_LOG_BYTES = 10_000_000


class DuplicateKeyError(ValueError):
    pass


def object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate key: {key}")
        value[key] = item
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError(f"expected a regular file: {path}")
            raw = source.read()
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except (OSError, UnicodeError) as error:
        raise ValueError(f"could not read {path}: {error}") from None
    try:
        value = json.loads(raw, object_pairs_hook=object_without_duplicate_keys)
    except (json.JSONDecodeError, DuplicateKeyError) as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_json_exclusive_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(json.dumps(value, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_text_atomic(path: Path, value: str, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def valid_run_id(value: Any) -> bool:
    return isinstance(value, str) and bool(RUN_ID_PATTERN.fullmatch(value))


def new_run_id(runs_directory: Path) -> str:
    base = datetime.now(timezone.utc).strftime("r-%Y%m%d-%H%M%S-%f")
    candidate = base
    suffix = 2
    while (runs_directory / f"{candidate}.json").exists() or (
        runs_directory / f"{candidate}.log"
    ).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError(f"expected a regular log file: {path}")
            for chunk in iter(lambda: source.read(65536), b""):
                digest.update(chunk)
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except OSError as error:
        raise ValueError(f"could not read log {path}: {error}") from None
    return digest.hexdigest()


def git_workspace_fingerprint(cwd: Path, evidence_directory: Path, *, _retry_missing: bool = True) -> dict[str, str] | None:
    """Bind enumerated working-tree bytes; ignored/external inputs are outside scope."""
    generated_names = {"contract.json", "report.json", "REPORT.md", "telemetry/events.jsonl", "telemetry/installation-id"}
    # Do not silently bind a different index/repository than the executed command.
    routing_variables = {"GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR",
                         "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"}
    if any(name in os.environ for name in routing_variables):
        return None
    original_cwd = Path(cwd).resolve()
    def git(*args, allow_missing=False):
        result = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, timeout=5)
        if result.returncode and not (allow_missing and result.returncode == 1):
            raise OSError('Git enumeration failed')
        return result.stdout
    try:
        root = Path(os.fsdecode(git('rev-parse', '--show-toplevel')[:-1]))
        if not root.is_absolute() or not original_cwd.is_relative_to(root.resolve()):
            return None
        # Explicit worktree routing may point at a different source tree even when
        # the reported root contains cwd. Conventional .git worktrees remain supported.
        if git('config', '--get', 'core.worktree', allow_missing=True):
            return None
        cwd = root  # ls-files paths and scope must be repository-root relative.
        tracked = {}
        for entry in git('ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            meta, separator, name = entry.partition(b'\t')
            fields = meta.split()
            if not separator or not name or len(fields) != 3:
                return None
            mode, oid, stage = fields
            if stage != b'0' or mode not in (b'100644', b'100755', b'120000'):
                return None  # conflicts, gitlinks, unsupported index state
            tracked[name] = mode
        names = set(tracked)
        names.update(filter(None, git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')))
        digest = hashlib.sha256(b'content-inventory-v1\0')
        evidence = Path(evidence_directory)
        # An evidence symlink is not an owned-output exclusion namespace.
        exclude_generated = not evidence.is_symlink()
        for name in sorted(names):
            path = root / os.fsdecode(name)
            try:
                info = path.lstat()
            except FileNotFoundError:
                if name not in tracked:
                    # A publisher can remove staging after Git enumerates it.
                    # Re-observe once; never assume an unseen entry was regular.
                    if _retry_missing:
                        return git_workspace_fingerprint(original_cwd, evidence_directory, _retry_missing=False)
                    return None
                payload = b'missing'
            else:
                # Compare parent identities to support casing aliases without lowercasing source names.
                generated = False
                if exclude_generated and name not in tracked and stat.S_ISREG(info.st_mode) and evidence.exists():
                    for ancestor in path.parents:
                        if ancestor == root.parent:
                            break
                        if ancestor.samefile(evidence):
                            relative = path.relative_to(ancestor)
                            generated = relative.as_posix() in generated_names or (len(relative.parts) == 2 and relative.parts[0] == 'runs' and relative.suffix in ('.json', '.log'))
                            # Atomic publishers own only these temporary output names.
                            # This branch applies only to untracked regular files.
                            if len(relative.parts) == 1:
                                generated = generated or bool(re.fullmatch(r"\.(?:contract\.json|report\.json|REPORT\.md)\.tmp-[a-z0-9_]{8}", relative.name))
                            elif len(relative.parts) == 2 and relative.parts[0] == 'runs':
                                temporary = re.fullmatch(r"\.([A-Za-z0-9][A-Za-z0-9._-]*)\.json\.tmp-[a-z0-9_]{8}", relative.name)
                                generated = generated or temporary is not None
                            break
                if generated:
                    continue
                if stat.S_ISLNK(info.st_mode):
                    payload = b'link\0' + os.fsencode(os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    # Avoid following a replacement symlink between lstat/open.
                    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
                    with os.fdopen(fd, 'rb') as source:
                        opened = os.fstat(source.fileno())
                        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                            return None
                        content = hashlib.sha256()
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            content.update(block)
                        after = os.fstat(source.fileno())
                        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                            return None
                    payload = b'file\0' + str(stat.S_IMODE(opened.st_mode)).encode() + b'\0' + content.digest()
                else:
                    return None
            digest.update(len(name).to_bytes(8, 'big') + name)
            digest.update(len(payload).to_bytes(8, 'big') + payload)
        return {'kind': 'git-content-v1', 'root': str(root), 'sha256': digest.hexdigest()}
    except (OSError, subprocess.TimeoutExpired):
        return None


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if os.name != "posix":
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return

    # The command starts in its own POSIX process group. The group can outlive
    # its leader, so checking only process.poll() can leave background children
    # writing to the evidence log after it has been hashed.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    if process.poll() is None:
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass

    # Give cooperative descendants a brief shutdown window, then guarantee
    # that none can outlive log capture.
    time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    if process.poll() is None:
        process.wait()


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def text_list_has_content(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(nonempty_text(item) for item in value)
    )


def valid_text_list(value: Any) -> bool:
    return isinstance(value, list) and all(nonempty_text(item) for item in value)


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    task = contract.get("task")
    intent = contract.get("intent")
    obligations = contract.get("proof_obligations")

    if contract.get("version") != 1:
        errors.append("contract.version must be 1")
    if not isinstance(task, dict):
        return errors + ["contract.task must be an object"]
    if not nonempty_text(task.get("title")):
        errors.append("contract.task.title is required")
    if task.get("mode") not in MODES:
        errors.append(f"contract.task.mode must be one of: {', '.join(MODES)}")
    if task.get("type") not in TASK_TYPES:
        errors.append(f"contract.task.type must be one of: {', '.join(TASK_TYPES)}")

    if not isinstance(intent, dict):
        errors.append("contract.intent must be an object")
    else:
        if not nonempty_text(intent.get("goal")):
            errors.append("contract.intent.goal is required")
        if not text_list_has_content(intent.get("must_happen")):
            errors.append("contract.intent.must_happen needs at least one non-empty item")
        if not text_list_has_content(intent.get("must_not_happen")):
            errors.append("contract.intent.must_not_happen needs at least one non-empty item")
        for key in ("constraints", "non_goals", "open_questions", "assumptions"):
            if not valid_text_list(intent.get(key)):
                errors.append(f"contract.intent.{key} must be a list of non-empty strings")

    if not isinstance(obligations, list) or not obligations:
        errors.append("contract.proof_obligations needs at least one item")
    else:
        seen: set[str] = set()
        for index, item in enumerate(obligations):
            label = f"contract.proof_obligations[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            obligation_id = item.get("id")
            if not nonempty_text(obligation_id):
                errors.append(f"{label}.id is required")
            elif obligation_id in seen:
                errors.append(f"duplicate proof obligation id: {obligation_id}")
            else:
                seen.add(obligation_id)
            if not nonempty_text(item.get("claim")):
                errors.append(f"{label}.claim is required")
            if not nonempty_text(item.get("verification")):
                errors.append(f"{label}.verification is required")
    return errors


def validate_run_record(
    directory: Path, run_id: str
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not valid_run_id(run_id):
        return None, [f"invalid run id: {run_id!r}"]

    record_path = directory / "runs" / f"{run_id}.json"
    try:
        record = read_json(record_path)
    except ValueError as error:
        return None, [str(error)]

    label = f"run {run_id}"
    if type(record.get("version")) is not int or record.get("version") not in (1, 2):
        errors.append(f"{label}.version must be 1 or 2")
    if record.get("id") != run_id:
        errors.append(f"{label}.id must match its filename")
    argv = record.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(item, str) for item in argv
    ):
        errors.append(f"{label}.argv must be a non-empty list of strings")
    cwd = record.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        errors.append(f"{label}.cwd must be an absolute path")

    started_at = parse_utc(record.get("started_at"))
    ended_at = parse_utc(record.get("ended_at"))
    if started_at is None:
        errors.append(f"{label}.started_at must be a UTC ISO 8601 timestamp")
    if ended_at is None:
        errors.append(f"{label}.ended_at must be a UTC ISO 8601 timestamp")
    if started_at is not None and ended_at is not None and ended_at < started_at:
        errors.append(f"{label}.ended_at must not be before started_at")

    exit_code = record.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        errors.append(f"{label}.exit_code must be an integer")

    expected_log = f"runs/{run_id}.log"
    if record.get("log") != expected_log:
        errors.append(f"{label}.log must be {expected_log}")
    log_sha256 = record.get("log_sha256")
    if not isinstance(log_sha256, str) or not SHA256_PATTERN.fullmatch(log_sha256):
        errors.append(f"{label}.log_sha256 must be a lowercase SHA-256 digest")
    else:
        log_path = directory / expected_log
        try:
            actual_sha256 = sha256_file(log_path)
        except ValueError as error:
            errors.append(str(error))
        else:
            if actual_sha256 != log_sha256:
                errors.append(f"{label} log hash does not match")
    workspace_fields = ("workspace", "workspace_start") if record.get("version") == 2 else ("workspace",)
    for field in workspace_fields:
        if record.get("version") == 2 and field not in record:
            errors.append(f"{label}.{field} is required for version 2")
        workspace = record.get(field)
        if workspace is not None:
            if not isinstance(workspace, dict):
                errors.append(f"{label}.{field} must be an object or null")
            else:
                if workspace.get("kind") not in ("git", "git-content-v1"):
                    errors.append(f"{label}.{field}.kind must be git or git-content-v1")
                if not isinstance(workspace.get("root"), str) or not Path(
                    workspace.get("root", "")
                ).is_absolute():
                    errors.append(f"{label}.{field}.root must be an absolute path")
                fingerprint = workspace.get("sha256")
                if not isinstance(fingerprint, str) or not SHA256_PATTERN.fullmatch(
                    fingerprint
                ):
                    errors.append(f"{label}.{field}.sha256 must be a SHA-256 digest")
    return record, errors


def validate_supporting_workspace(
    record: dict[str, Any], evidence_directory: Path, *, require_binding: bool = True,
    fingerprints: dict[Path, dict[str, str] | None] | None = None,
) -> list[str]:
    workspace = record.get("workspace")
    start = record.get("workspace_start")
    if workspace is not None and evidence_directory.resolve() == Path(workspace["root"]).resolve():
        return [f"run {record['id']} evidence directory is the Git root and excludes all source; recapture with --directory .confidence"]
    if record.get("version") != 2:
        if require_binding:
            return [f"run {record['id']} lacks start-state provenance; rerun to support current-code proof"]
    elif start is not None and workspace is not None and start != workspace:
        return [f"run {record['id']} workspace changed during execution; rerun verification on the final state"]
    if workspace is None or (record.get("version") == 2 and start is None):
        if require_binding:
            return [f"run {record['id']} workspace binding is unknown; capture in a supported Git working tree or use partial evidence"]
        return []
    if workspace.get("kind") != "git-content-v1" or (start is not None and start.get("kind") != "git-content-v1"):
        if require_binding:
            return [f"run {record['id']} uses legacy Git binding; rerun to support current content proof"]
        return []
    cwd = Path(record["cwd"]).resolve()
    if fingerprints is None:
        current = git_workspace_fingerprint(cwd, evidence_directory)
    else:
        if cwd not in fingerprints:
            fingerprints[cwd] = git_workspace_fingerprint(cwd, evidence_directory)
        current = fingerprints[cwd]
    if current is None:
        return [f"run {record['id']} workspace can no longer be fingerprinted"]
    if current["root"] != workspace["root"] or current["sha256"] != workspace["sha256"]:
        return [f"run {record['id']} is stale because the Git workspace changed; rerun the original verification on the current tree with a new run ID, then record that ID"]
    return []

def validate_report(
    report: dict[str, Any], contract: dict[str, Any], directory: Path
) -> list[str]:
    errors: list[str] = []
    evidence = report.get("evidence")
    # Share repeated workspace reads within this call, then recheck before return.
    # One supporting reference uses the original single-read path.
    reference_count = sum(
        len(item["run_ids"])
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("run_ids"), list)
    ) if isinstance(evidence, list) else 0
    fingerprints: dict[Path, dict[str, str] | None] | None = (
        {} if reference_count > 1 else None
    )
    task = contract.get("task") if isinstance(contract.get("task"), dict) else {}
    obligations = contract.get("proof_obligations")
    if not isinstance(obligations, list):
        obligations = []
    obligation_ids = {
        item.get("id")
        for item in obligations
        if isinstance(item, dict) and nonempty_text(item.get("id"))
    }

    if report.get("version") != 3:
        errors.append("report.version must be 3")
    if report.get("task_title") != task.get("title"):
        errors.append("report.task_title must match contract.task.title")
    if report.get("mode") != task.get("mode"):
        errors.append("report.mode must match contract.task.mode")
    if not nonempty_text(report.get("outcome")):
        errors.append("report.outcome is required")
    if not valid_text_list(report.get("changes")):
        errors.append("report.changes must be a list of non-empty strings")
    if not isinstance(evidence, list) or not evidence:
        errors.append("report.evidence needs one result per proof obligation")
    else:
        reported_ids: set[str] = set()
        for index, item in enumerate(evidence):
            label = f"report.evidence[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            obligation_id = item.get("obligation_id")
            if obligation_id not in obligation_ids:
                errors.append(f"{label}.obligation_id does not match the contract")
            elif obligation_id in reported_ids:
                errors.append(f"duplicate evidence for obligation: {obligation_id}")
            else:
                reported_ids.add(obligation_id)
            if item.get("status") not in STATUSES:
                errors.append(f"{label}.status must be one of: {', '.join(STATUSES)}")
            if not nonempty_text(item.get("details")):
                errors.append(f"{label}.details is required")
            if not valid_text_list(item.get("artifacts")):
                errors.append(f"{label}.artifacts must be a list of non-empty strings")
            run_ids = item.get("run_ids")
            if not isinstance(run_ids, list) or not all(
                valid_run_id(run_id) for run_id in run_ids
            ):
                errors.append(f"{label}.run_ids must be a list of valid run ids")
                run_ids = []
            elif len(run_ids) != len(set(run_ids)):
                errors.append(f"{label}.run_ids must not contain duplicates")

            diagnostic_run_ids = item.get("diagnostic_run_ids", [])
            if not isinstance(diagnostic_run_ids, list) or not all(
                valid_run_id(run_id) for run_id in diagnostic_run_ids
            ):
                errors.append(
                    f"{label}.diagnostic_run_ids must be a list of valid run ids"
                )
                diagnostic_run_ids = []
            elif len(diagnostic_run_ids) != len(set(diagnostic_run_ids)):
                errors.append(
                    f"{label}.diagnostic_run_ids must not contain duplicates"
                )
            if set(run_ids) & set(diagnostic_run_ids):
                errors.append(
                    f"{label} cannot use the same run as supporting and diagnostic evidence"
                )

            run_records: list[dict[str, Any]] = []
            for run_id in run_ids:
                record, run_errors = validate_run_record(directory, run_id)
                errors.extend(f"{label}: {error}" for error in run_errors)
                if record is not None and not run_errors:
                    run_records.append(record)
                    # Partial observations remain readable; only a pass promotes
                    # them to proof. Research may establish a command result
                    # without claiming that the current source was verified.
                    if item.get("status") == "pass":
                        errors.extend(
                            f"{label}: {error}"
                            for error in validate_supporting_workspace(
                                record, directory,
                                require_binding=task.get("type") != "research",
                                fingerprints=fingerprints,
                            )
                        )
            for run_id in diagnostic_run_ids:
                _, run_errors = validate_run_record(directory, run_id)
                errors.extend(f"{label}: {error}" for error in run_errors)
            if item.get("status") == "pass":
                if not run_ids:
                    errors.append(f"{label}.run_ids needs a captured run for pass status")
                elif any(record.get("exit_code") != 0 for record in run_records):
                    errors.append(f"{label} requires every supporting run to succeed")
        missing = obligation_ids - reported_ids
        if missing:
            errors.append(f"missing evidence for: {', '.join(sorted(missing))}")

    tests = report.get("tests")
    if not isinstance(tests, dict):
        errors.append("report.tests must be an object")
    else:
        for key in ("passed", "failed", "not_run"):
            if not valid_text_list(tests.get(key)):
                errors.append(
                    f"report.tests.{key} must be a list of non-empty strings"
                )

    simplicity = report.get("simplicity")
    if not isinstance(simplicity, dict):
        errors.append("report.simplicity must be an object")
    else:
        if simplicity.get("code_gate") not in ("pass", "fail"):
            errors.append("report.simplicity.code_gate must be pass or fail")
        if simplicity.get("test_gate") not in ("pass", "fail"):
            errors.append("report.simplicity.test_gate must be pass or fail")
        if not nonempty_text(simplicity.get("notes")):
            errors.append("report.simplicity.notes is required")

    review = report.get("review")
    if not isinstance(review, dict):
        errors.append("report.review must be an object")
    else:
        if not isinstance(review.get("required"), bool):
            errors.append("report.review.required must be a boolean")
        if not nonempty_text(review.get("reason")):
            errors.append("report.review.reason is required")
        roles = review.get("roles")
        if not isinstance(roles, list) or not all(role in REVIEW_ROLES for role in roles):
            errors.append(
                "report.review.roles must use known review roles: "
                + ", ".join(REVIEW_ROLES)
            )
        elif len(roles) != len(set(roles)):
            errors.append("report.review.roles must not contain duplicates")
        if not valid_text_list(review.get("findings")):
            errors.append("report.review.findings must be a list of non-empty strings")

    for key in ("risks", "user_decisions"):
        if not valid_text_list(report.get(key)):
            errors.append(f"report.{key} must be a list of non-empty strings")
    if not nonempty_text(report.get("rollback")):
        errors.append("report.rollback is required; use 'Not applicable' when true")
    if fingerprints is not None:
        for cwd, before in fingerprints.items():
            if git_workspace_fingerprint(cwd, directory) != before:
                errors.append("workspace changed during validation; rerun on a stable tree")
    return errors


def completion_errors(report: dict[str, Any]) -> list[str]:
    """Return reasons a structurally valid report is not ready for release."""
    errors: list[str] = []
    evidence = report["evidence"]
    incomplete = [
        item["obligation_id"] for item in evidence if item["status"] != "pass"
    ]
    if incomplete:
        errors.append(
            "release requires pass status for every proof obligation: "
            + ", ".join(incomplete)
        )

    simplicity = report["simplicity"]
    if simplicity["code_gate"] != "pass":
        errors.append("release requires the code simplicity gate to pass")
    if simplicity["test_gate"] != "pass":
        errors.append("release requires the test quality gate to pass")

    tests = report["tests"]
    if tests["failed"]:
        errors.append("release cannot contain failed tests")
    if tests["not_run"]:
        errors.append("release cannot contain required tests that were not run")

    review = report["review"]
    roles = set(review["roles"])
    if review["required"] and not roles:
        errors.append("release requires the named independent review")
    if report["mode"] == "critical":
        required_roles = {"test_designer", "adversarial_reviewer"}
        missing_roles = required_roles - roles
        if not review["required"] or missing_roles:
            errors.append(
                "critical release requires separate test_designer and "
                "adversarial_reviewer roles"
            )
    return errors


def initial_contract(title: str, mode: str, task_type: str) -> dict[str, Any]:
    return {
        "version": 1,
        "task": {"title": title, "mode": mode, "type": task_type},
        "intent": {
            "goal": "",
            "must_happen": [""],
            "must_not_happen": [""],
            "constraints": [],
            "non_goals": [],
            "open_questions": [],
            "assumptions": [],
        },
        "proof_obligations": [
            {"id": "P1", "claim": "", "verification": ""}
        ],
    }


def initial_report(title: str, mode: str) -> dict[str, Any]:
    return {
        "version": 3,
        "task_title": title,
        "mode": mode,
        "outcome": "",
        "changes": [],
        "evidence": [
            {
                "obligation_id": "P1",
                "status": "not_run",
                "details": "",
                "artifacts": [],
                "run_ids": [],
                "diagnostic_run_ids": [],
            }
        ],
        "tests": {"passed": [], "failed": [], "not_run": []},
        "simplicity": {"code_gate": "fail", "test_gate": "fail", "notes": ""},
        "review": {
            "required": mode == "critical",
            "reason": "",
            "roles": [],
            "findings": [],
        },
        "risks": [],
        "rollback": "",
        "user_decisions": [],
    }


def command_init(args: argparse.Namespace) -> int:
    if not args.resume and not args.title:
        print("init requires --title unless --resume is used", file=sys.stderr)
        return 2
    try:
        with evidence_writer_lock(Path(args.directory), create=True) as directory:
            contract_path, report_path = directory / 'contract.json', directory / 'report.json'
            for path in (contract_path, report_path):
                if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
                    raise RecordError('EVIDENCE_UNSAFE', f'Refusing non-regular evidence file: {path.name}')
            existing = [path for path in (contract_path, report_path) if os.path.lexists(path)]
            if args.resume:
                if not contract_path.exists():
                    raise RecordError('RESUME_AMBIGUOUS', 'Resume requires an existing contract; report-only or empty state cannot establish task identity')
                contract = read_json(contract_path)
                task = contract.get('task')
                if contract.get('version') != 1 or not isinstance(task, dict) or not nonempty_text(task.get('title')) or task.get('mode') not in MODES or task.get('type') not in TASK_TYPES:
                    raise RecordError('RESUME_AMBIGUOUS', 'Existing contract has no supported task identity')
                for requested, key in ((args.title, 'title'), (args.mode, 'mode'), (args.task_type, 'type')):
                    if requested is not None and requested != task[key]:
                        raise RecordError('RESUME_CONFLICT', f'Requested {key} conflicts with the existing contract')
                obligations = contract.get('proof_obligations')
                if not isinstance(obligations, list) or not obligations or any(not isinstance(item, dict) or not nonempty_text(item.get('id')) for item in obligations):
                    raise RecordError('RESUME_AMBIGUOUS', 'Existing contract needs named proof obligations')
                ids = [item['id'] for item in obligations]
                if len(ids) != len(set(ids)):
                    raise RecordError('RESUME_AMBIGUOUS', 'Existing contract has duplicate obligation IDs')
                if report_path.exists():
                    report = read_json(report_path)
                    evidence = report.get('evidence')
                    reported = [item.get('obligation_id') for item in evidence if isinstance(item, dict)] if isinstance(evidence, list) else []
                    if report.get('version') != 3 or report.get('task_title') != task['title'] or report.get('mode') != task['mode'] or not isinstance(evidence, list) or len(evidence) != len(reported) or len(reported) != len(ids) or any(not isinstance(item, str) for item in reported) or set(reported) != set(ids):
                        raise RecordError('RESUME_CONFLICT', 'Existing contract/report identities or obligations conflict; no files changed')
                    print('existing evidence pair preserved; fill fields, then validate')
                    return 0
                report = initial_report(task['title'], task['mode'])
                template = report['evidence'][0]
                report['evidence'] = [dict(template, obligation_id=ident) for ident in ids]
                write_text_atomic(report_path, json.dumps(report, indent=2) + '\n')
                print(f'created missing {report_path}; existing contract preserved')
                return 0
            if existing and not args.force:
                raise RecordError('EVIDENCE_EXISTS', 'refusing to overwrite: ' + ', '.join(str(path) for path in existing) + '; for a contract-only interrupted init, use --resume')
            # Force explicitly discards the old report first. An interruption can
            # leave contract-only state, never a new contract with an old report.
            if args.force:
                report_path.unlink(missing_ok=True)
            contract = initial_contract(args.title, args.mode or 'standard', args.task_type or 'feature')
            report = initial_report(args.title, args.mode or 'standard')
            write_text_atomic(contract_path, json.dumps(contract, indent=2) + '\n', replace=args.force)
            write_text_atomic(report_path, json.dumps(report, indent=2) + '\n')
            print(f'created {contract_path} and {report_path}')
            print('fill the empty fields, then run validate')
            return 0
    except (RecordError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2


class RecordError(Exception):
    def __init__(self, code, details):
        self.code = code
        self.details = details if isinstance(details, list) else [str(details)]
        super().__init__('; '.join(self.details))


def selected_result_documents(contract, result):
    """Use the existing validator unchanged, with one selected obligation.

Other report fields are valid scratch values solely for validation. They are never
written to disk, so incomplete unrelated report sections do not block recording.
"""
    selected = dict(contract)
    selected['proof_obligations'] = [
        item for item in contract['proof_obligations'] if item['id'] == result['obligation_id']
    ]
    task = contract['task']
    probe = initial_report(task['title'], task['mode'])
    probe.update(outcome='Selected-result validation', rollback='Not applicable')
    probe['simplicity']['notes'] = 'Not evaluated by record'
    probe['review']['reason'] = 'Not evaluated by record'
    probe['evidence'] = [result]
    return selected, probe


@contextmanager
def evidence_writer_lock(directory: Path, *, create: bool = False):
    if os.name != "posix" or not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise RecordError('PLATFORM_UNSUPPORTED', 'Evidence writers require Unix directory locking; no evidence files changed')
    try:
        import fcntl
    except ImportError:
        raise RecordError('PLATFORM_UNSUPPORTED', 'Evidence writers require Unix file locking; no evidence files changed')
    if directory.is_symlink():
        raise RecordError('DIRECTORY_UNSAFE', 'Evidence directory must be a non-symlink directory')
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise RecordError('DIRECTORY_UNSAFE', 'Evidence directory must be an existing non-symlink directory')
    directory = directory.resolve()
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecordError('LOCK_BUSY', 'Another evidence writer is active; retry after it finishes')
        yield directory
    finally:
        os.close(descriptor)


def record_result(args):
    with evidence_writer_lock(Path(args.directory)) as directory:
        for filename in ('contract.json', 'report.json'):
            if (directory / filename).is_symlink():
                raise RecordError('EVIDENCE_UNSAFE', f'Refusing symlink {filename}')
        try:
            contract = read_json(directory / 'contract.json')
            report = read_json(directory / 'report.json')
        except ValueError as error:
            raise RecordError('DOCUMENT_INVALID', str(error))
        contract_errors = validate_contract(contract)
        if contract_errors:
            raise RecordError('CONTRACT_INVALID', contract_errors)
        if report.get('version') != 3 or report.get('task_title') != contract['task']['title'] or report.get('mode') != contract['task']['mode']:
            raise RecordError('REPORT_INVALID', 'Report version, title and mode must match the contract')
        obligations = {item['id'] for item in contract['proof_obligations']}
        if args.obligation not in obligations:
            raise RecordError('OBLIGATION_UNKNOWN', f'Unknown obligation: {args.obligation}')
        evidence = report.get('evidence')
        if not isinstance(evidence, list) or any(not isinstance(item, dict) or not isinstance(item.get('obligation_id'), str) for item in evidence):
            raise RecordError('REPORT_INVALID', 'Report evidence must be a list of named obligation results')
        ids = [item['obligation_id'] for item in evidence]
        if len(ids) != len(set(ids)):
            raise RecordError('REPORT_INVALID', 'Duplicate obligation results are ambiguous')
        previous = next((item for item in evidence if item['obligation_id'] == args.obligation), {})
        result = dict(previous)
        result.update(obligation_id=args.obligation, status=args.status, details=args.details,
                      run_ids=args.run, diagnostic_run_ids=args.diagnostic_run, artifacts=args.artifact)
        selected, probe = selected_result_documents(contract, result)
        errors = validate_report(probe, selected, directory)
        if errors:
            raise RecordError('RESULT_INVALID', errors)
        updated = dict(report)
        updated['evidence'] = list(evidence)
        if args.obligation in ids:
            updated['evidence'][ids.index(args.obligation)] = result
        else:
            updated['evidence'].append(result)
        if updated != report:
            write_text_atomic(directory / 'report.json', json.dumps(updated, indent=2) + '\n', replace=True)
        return {'ok': True, 'obligation_id': args.obligation, 'status': args.status,
                'run_ids': args.run, 'diagnostic_run_ids': args.diagnostic_run,
                'report': 'report.json', 'changed': updated != report,
                'completion_checked': False}



def command_record(args: argparse.Namespace) -> int:
    try:
        result = record_result(args)
    except RecordError as error:
        print(json.dumps({'ok': False, 'code': error.code, 'errors': error.details}))
        return 2
    except OSError as error:
        print(json.dumps({'ok': False, 'code': 'IO_ERROR', 'errors': [f'{type(error).__name__}: {error.strerror}']}))
        return 2
    print(json.dumps(result, separators=(',', ':')))
    return 0


def command_run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        args.diagnostic_error_code = "RUN_COMMAND_MISSING"
        print("run requires COMMAND ARG...; place -- before the command", file=sys.stderr)
        return 125
    argv = command

    raw_directory = Path(args.directory)
    if raw_directory.is_symlink():
        args.diagnostic_error_code = "RUN_EVIDENCE_UNSAFE"
        print(f"refusing symlink evidence directory: {raw_directory}", file=sys.stderr)
        return 125
    directory = raw_directory.resolve()
    runs_directory = directory / "runs"
    if runs_directory.is_symlink():
        args.diagnostic_error_code = "RUN_EVIDENCE_UNSAFE"
        print(f"refusing symlink runs directory: {runs_directory}", file=sys.stderr)
        return 125
    runs_directory.mkdir(parents=True, exist_ok=True)
    run_id = args.id if args.id is not None else new_run_id(runs_directory)
    if not valid_run_id(run_id):
        args.diagnostic_error_code = "RUN_ID_INVALID"
        print(
            "run id may contain only letters, digits, dot, underscore, and hyphen",
            file=sys.stderr,
        )
        return 125

    record_path = runs_directory / f"{run_id}.json"
    log_path = runs_directory / f"{run_id}.log"
    if record_path.exists() or log_path.exists():
        args.diagnostic_error_code = "RUN_ID_EXISTS"
        print(f"refusing to overwrite run: {run_id}; reuse the existing record if it is the intended observation, or omit --id to capture a new run", file=sys.stderr)
        return 125

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        args.diagnostic_error_code = "RUN_CWD_INVALID"
        print(f"run cwd is not a directory: {cwd}", file=sys.stderr)
        return 125

    workspace_start = git_workspace_fingerprint(cwd, directory)
    if workspace_start is not None and directory.resolve() == Path(workspace_start["root"]).resolve():
        args.diagnostic_error_code = "RUN_EVIDENCE_DIRECTORY_INVALID"
        print("evidence directory must not be the Git root; use --directory .confidence", file=sys.stderr)
        return 125
    started_at = utc_now()
    log = None
    process = None
    termination_reason: str | None = None
    # A signal must not discard an acquired descriptor or child handle before
    # this block can clean it up. Children inherit no blocked signal mask.
    args.defer_run_interrupt = True
    try:
        try:
            log = log_path.open("xb")
        except FileExistsError:
            if getattr(args, "interrupted_signal", None) is not None:
                raise KeyboardInterrupt
            args.diagnostic_error_code = "RUN_ID_EXISTS"
            print(f"refusing to overwrite run: {run_id}; reuse the existing record if it is the intended observation, or omit --id to capture a new run", file=sys.stderr)
            return 125
        if getattr(args, "interrupted_signal", None) is not None:
            raise KeyboardInterrupt
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            if getattr(args, "interrupted_signal", None) is not None:
                raise KeyboardInterrupt
            args.diagnostic_error_code = "RUN_LAUNCH_FAILED"
            log.close()
            log_path.unlink(missing_ok=True)
            print(f"could not start command: {error}", file=sys.stderr)
            return 125
        args.defer_run_interrupt = False
        if getattr(args, "interrupted_signal", None) is not None:
            raise KeyboardInterrupt
        deadline = time.monotonic() + args.timeout_seconds
        while process.poll() is None:
            if time.monotonic() >= deadline:
                termination_reason = "timeout"
                stop_process(process)
                break
            try:
                if log_path.stat().st_size > args.max_log_bytes:
                    termination_reason = "log_limit"
                    stop_process(process)
                    break
            except OSError as error:
                args.diagnostic_error_code = "RUN_CAPTURE_FAILED"
                stop_process(process)
                log.close()
                log_path.unlink(missing_ok=True)
                print(
                    f"run {run_id}: could not inspect log ({error}); "
                    "no evidence record written",
                    file=sys.stderr,
                )
                return 125
            time.sleep(0.05)
        exit_code = process.wait()
        if os.name == "posix":
            stop_process(process)
        if termination_reason == "timeout":
            exit_code = 124
        elif termination_reason == "log_limit" or log_path.stat().st_size > args.max_log_bytes:
            termination_reason = "log_limit"
            exit_code = 122
    except KeyboardInterrupt:
        if process is not None:
            stop_process(process)
        if log is not None:
            log.close()
            log_path.unlink(missing_ok=True)
        print(f"run {run_id}: interrupted; no evidence record written", file=sys.stderr)
        return 128 + getattr(args, "interrupted_signal", signal.SIGINT)
    except OSError as error:
        args.diagnostic_error_code = "RUN_CAPTURE_FAILED"
        if process is not None:
            stop_process(process)
        if log is not None:
            log.close()
            log_path.unlink(missing_ok=True)
        if getattr(args, "interrupted_signal", None) is not None:
            args.diagnostic_error_code = "RUN_INTERRUPTED"
            print(f"run {run_id}: interrupted; no evidence record written", file=sys.stderr)
            return 128 + args.interrupted_signal
        print(
            f"run {run_id}: capture failed ({error}); no evidence record written",
            file=sys.stderr,
        )
        return 125
    finally:
        args.defer_run_interrupt = False
        if log is not None and not log.closed:
            log.flush()
            os.fsync(log.fileno())
            log.close()

    if termination_reason:
        with log_path.open("ab") as output:
            output.write(f"\n[confidence runner stopped: {termination_reason}]\n".encode())

    digest = hashlib.sha256()
    stream_to_terminal = not args.json
    try:
        with log_path.open("rb") as captured:
            for chunk in iter(lambda: captured.read(65536), b""):
                digest.update(chunk)
                if stream_to_terminal:
                    try:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                    except BrokenPipeError:
                        stream_to_terminal = False
    except OSError as error:
        args.diagnostic_error_code = "RUN_CAPTURE_FAILED"
        log_path.unlink(missing_ok=True)
        print(
            f"run {run_id}: could not read captured log ({error}); "
            "no evidence record written",
            file=sys.stderr,
        )
        return 125

    ended_at = utc_now()
    workspace = git_workspace_fingerprint(cwd, directory)
    record = {
        "version": 2,
        "id": run_id,
        "argv": argv,
        "cwd": str(cwd),
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": exit_code,
        "termination_reason": termination_reason,
        "resolved_executable": shutil.which(argv[0])
        or str((cwd / argv[0]).resolve()),
        "workspace": workspace,
        "workspace_start": workspace_start,
        "log": f"runs/{run_id}.log",
        "log_sha256": digest.hexdigest(),
    }
    try:
        write_json_exclusive_atomic(record_path, record)
    except FileExistsError:
        args.diagnostic_error_code = "RUN_RECORD_COLLISION"
        print(
            f"run {run_id}: record appeared during capture; refusing to overwrite",
            file=sys.stderr,
        )
        return 125
    if args.json:
        binding = "unknown" if workspace_start is None or workspace is None else (
            "unchanged" if workspace_start == workspace else "changed"
        )
        print(json.dumps({
            "version": 1,
            "id": run_id,
            "exit_code": exit_code,
            "termination_reason": termination_reason,
            "log": record["log"],
            "record": f"runs/{run_id}.json",
            "workspace_binding": binding,
        }, separators=(",", ":")))
    if workspace_start is None or workspace is None:
        print(f"run {run_id}: workspace binding unknown; current-code proof requires a supported Git working tree", file=sys.stderr)
    elif workspace_start != workspace:
        print(f"run {run_id}: workspace changed during execution; rerun verification on the final state", file=sys.stderr)
    print(
        f"run {run_id}: exit {exit_code}, log {record['log']}",
        file=sys.stderr,
    )
    return exit_code if exit_code >= 0 else 128 + (-exit_code)


def load_and_validate(directory: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    contract = read_json(directory / "contract.json")
    report = read_json(directory / "report.json")
    errors = validate_contract(contract)
    errors.extend(validate_report(report, contract, directory))
    return contract, report, errors


def recorded_source_scopes(report: dict[str, Any], directory: Path) -> list[dict[str, Any]]:
    """Describe recorded locations, not the caller's tree or a new validation claim."""
    references: dict[tuple[str, str], set[str]] = {}
    for result in report['evidence']:
        for role, field in (('support', 'run_ids'), ('diagnostic', 'diagnostic_run_ids')):
            for run_id in result.get(field, []):
                references.setdefault((role, run_id), set()).add(result['status'])
    scopes = []
    for (role, run_id), statuses in sorted(references.items()):
        record = read_json(directory / 'runs' / f'{run_id}.json')
        workspace = record.get('workspace')
        start = record.get('workspace_start')
        known = isinstance(workspace, dict)
        start_known = isinstance(start, dict)
        if record.get('version') != 2:
            observation = 'legacy record'
        elif not known or not start_known:
            observation = 'unknown endpoint'
        elif start != workspace:
            observation = 'changed endpoints'
        else:
            observation = 'unchanged endpoints'
        kind = workspace.get('kind', 'legacy') if known else 'unknown'
        if kind == 'git':
            kind = 'git (legacy)'
        scopes.append({'role': role, 'run_id': run_id, 'claim_statuses': sorted(statuses),
                       'recorded_cwd': record.get('cwd', 'unknown'),
                       'recorded_root': workspace.get('root', 'unknown') if known else 'unknown',
                       'binding_kind': kind, 'record_version': record.get('version', 'unknown'),
                       'observation_status': observation,
                       'start_fingerprint': start.get('sha256', 'unknown') if start_known else 'unknown',
                       'fingerprint': workspace.get('sha256', 'unknown') if known else 'unknown'})
    return scopes


def grouped_source_scopes(scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in scopes:
        key = (item['recorded_root'], item['recorded_cwd'], item['role'],
               item['observation_status'], item['binding_kind'], tuple(item['claim_statuses']))
        if key not in groups:
            groups[key] = {field: item[field] for field in
                           ('recorded_root', 'recorded_cwd', 'role', 'observation_status',
                            'binding_kind', 'claim_statuses')}
            groups[key]['run_ids'] = []
        groups[key]['run_ids'].append(item['run_id'])
    return list(groups.values())


def source_scope_markdown(scopes: list[dict[str, Any]]) -> str:
    def cell(value: Any) -> str:
        text = markdown_text(value)
        return re.sub(r'([\\`*_{}\[\]()#+.!|>-])', r'\\\1', text)
    lines = ['## Recorded source scope', '',
             'Recorded locations are not the caller’s checkout. Diagnostics and partial observations do not certify current code. Exact record version and start/end fingerprints are in runs/<id>.json.', '',
             '| Runs | Role / claim status | Recorded location | Observation / binding |',
             '| --- | --- | --- | --- |']
    for item in grouped_source_scopes(scopes):
        location = item['recorded_root']
        if item['recorded_cwd'] != location:
            location += '; cwd: ' + item['recorded_cwd']
        values = [', '.join(item['run_ids']), item['role'] + ' / ' + ', '.join(item['claim_statuses']),
                  location, item['observation_status'] + ' / ' + item['binding_kind']]
        lines.append('| ' + ' | '.join(cell(value) for value in values) + ' |')
    if not scopes:
        lines.append('| None | — | unknown | unknown |')
    return '\n'.join(lines)


def command_validate(args: argparse.Namespace) -> int:
    try:
        contract, report, errors = load_and_validate(Path(args.directory))
    except ValueError as error:
        print(error, file=sys.stderr)
        if str(error).startswith("missing file:"):
            print("Check --directory. If starting a new task, use init with the intended --directory; otherwise select the existing evidence directory.", file=sys.stderr)
        return 2
    completion_failed = False
    if not errors and args.require_complete:
        errors.extend(completion_errors(report))
        completion_failed = bool(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if completion_failed:
            print("To check a partial report, use validate without --require-complete with the same --directory. Keep required gaps explicit; structural validity does not establish completion.", file=sys.stderr)
        return 1
    try:
        scopes = recorded_source_scopes(report, Path(args.directory))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if args.require_complete:
        if contract["task"]["type"] == "research":
            print("confidence research evidence is complete; this does not certify current code")
        else:
            print("confidence evidence checks are complete")
    else:
        print("confidence evidence is structurally valid")
    print("Recorded source scope (not caller checkout; diagnostics and partial observations do not certify current code):")
    for item in grouped_source_scopes(scopes):
        location = item["recorded_root"]
        if item["recorded_cwd"] != location:
            location += "; cwd: " + item["recorded_cwd"]
        print(f"{item['role']} ({', '.join(item['claim_statuses'])}): {len(item['run_ids'])} run(s) [{', '.join(item['run_ids'])}] | "
              f"{json.dumps(location, ensure_ascii=True)} | {item['observation_status']} / {item['binding_kind']}")
    if scopes:
        print("Exact versions and start/end fingerprints: runs/<id>.json")
    if not scopes:
        print("No captured source scopes recorded.")
    return 0


def bullet_list(items: list[Any]) -> str:
    clean = [markdown_text(item) for item in items if str(item).strip()]
    return "\n".join(f"- {item}" for item in clean) if clean else "- None"


def markdown_text(value: Any) -> str:
    return html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ")


def markdown_cell(value: Any) -> str:
    return markdown_text(value).replace("|", "\\|")


def render_markdown(
    contract: dict[str, Any], report: dict[str, Any], directory: Path
) -> str:
    task = contract["task"]
    intent = contract["intent"]
    rows = []
    evidence_by_id = {item["obligation_id"]: item for item in report["evidence"]}
    for obligation in contract["proof_obligations"]:
        result = evidence_by_id[obligation["id"]]
        artifacts = ", ".join(result["artifacts"]) or "None"
        runs = []
        for run_id in result["run_ids"]:
            record = read_json(directory / "runs" / f"{run_id}.json")
            runs.append(f"support: {run_id} (exit {record['exit_code']})")
        for run_id in result.get("diagnostic_run_ids", []):
            record = read_json(directory / "runs" / f"{run_id}.json")
            runs.append(f"diagnostic: {run_id} (exit {record['exit_code']})")
        rows.append(
            f"| {markdown_cell(obligation['id'])} | "
            f"{markdown_cell(obligation['claim'])} | "
            f"{markdown_cell(result['status'])} | "
            f"{markdown_cell(result['details'])} | "
            f"{markdown_cell(', '.join(runs) or 'None')} | "
            f"{markdown_cell(artifacts)} |"
        )
    tests = report["tests"]
    simplicity = report["simplicity"]
    review = report["review"]
    scope = (
        "Research command evidence does not certify current code."
        if task["type"] == "research"
        else "Passing code claims require source binding; partial observations do not establish current-code correctness."
    )
    return f"""# Confidence Report: {markdown_text(task['title'])}

Mode: {task['mode']}

Task type: {task['type']}

{scope}

## Outcome

{markdown_text(report['outcome'])}

## Goal

{markdown_text(intent['goal'])}

## Changes

{bullet_list(report['changes'])}

## Proof

| ID | Claim | Status | Evidence | Captured runs | Artifacts |
| --- | --- | --- | --- | --- | --- |
{chr(10).join(rows)}

{source_scope_markdown(recorded_source_scopes(report, directory))}

## Tests

Passed:

{bullet_list(tests['passed'])}

Failed:

{bullet_list(tests['failed'])}

Not run:

{bullet_list(tests['not_run'])}

## Simplicity

Code gate: {simplicity['code_gate']}

Test gate: {simplicity['test_gate']}

{markdown_text(simplicity['notes'])}

## Review gate

Required: {str(review['required']).lower()}
Reason: {markdown_text(review['reason'])}

Roles:

{bullet_list(review['roles'])}

Findings and dispositions:

{bullet_list(review['findings'])}

## Risks

{bullet_list(report['risks'])}

## User decisions

{bullet_list(report['user_decisions'])}

## Rollback

{markdown_text(report['rollback'])}
"""


def command_render(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if directory.is_symlink():
        print(f"refusing symlink evidence directory: {directory}", file=sys.stderr)
        return 2
    try:
        contract, report, errors = load_and_validate(directory)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("report was not rendered", file=sys.stderr)
        return 1
    output = directory / args.output if args.output else directory / "REPORT.md"
    resolved_directory = directory.resolve()
    resolved_output = output.resolve()
    if not resolved_output.is_relative_to(resolved_directory):
        print("render output must stay inside the evidence directory", file=sys.stderr)
        return 2
    if output.is_symlink():
        print(f"refusing symlink render output: {output}", file=sys.stderr)
        return 2
    if os.path.lexists(output) and not args.force:
        print(f"refusing to overwrite render output: {output}", file=sys.stderr)
        return 2
    try:
        write_text_atomic(
            output,
            render_markdown(contract, report, directory),
            replace=args.force,
        )
    except FileExistsError:
        print(f"refusing to overwrite render output: {output}", file=sys.stderr)
        return 2
    print(f"wrote {output}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(Path(args.directory), probe_telemetry=args.probe_telemetry)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Confidence Protocol {TOOL_VERSION}")
        for check in report["checks"]:
            print(f"[{check['status'].upper()}] {check['code']}: {check['summary']}")
            if check["remediation"]:
                print(f"  Fix: {check['remediation']}")
        print(f"Doctor result: {report['status']}")
    return 0 if report["status"] == "pass" else 1


def command_support_bundle(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else Path(
        "confidence-support-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + ".zip"
    )
    try:
        write_support_bundle(Path(args.directory), output, force=args.force)
    except FileExistsError:
        print(f"refusing to overwrite support bundle: {output}", file=sys.stderr)
        return 2
    except OSError as error:
        print(
            f"could not create support bundle ({type(error).__name__})",
            file=sys.stderr,
        )
        return 2
    print(f"wrote redacted support bundle {output}")
    return 0


class EvidenceArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        self.json_errors = False
        parsed, remaining = self.parse_known_args(args, namespace)
        if remaining:
            self.json_errors = getattr(parsed, "action", None) == "record"
            self.error("unrecognized arguments: " + " ".join(remaining))
        return parsed

    def error(self, message):
        if getattr(self, "json_errors", False):
            print(json.dumps({"ok": False, "code": "ARGUMENT_INVALID", "errors": [message]}))
            self.exit(2)
        super().error(message)


def parser() -> argparse.ArgumentParser:
    root = EvidenceArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="action", required=True)

    init = subparsers.add_parser("init", help="create or resume evidence templates (Unix locking required)", description="Uses cooperative Unix directory locking and atomic individual files, not a two-file transaction. --resume preserves an existing contract and creates only its missing report; --force discards the old report before replacement.")
    init.add_argument("--title")
    init.add_argument("--mode", choices=MODES)
    init.add_argument("--task-type", choices=TASK_TYPES)
    init.add_argument("--directory", default=".confidence")
    init_action = init.add_mutually_exclusive_group()
    init_action.add_argument("--force", action="store_true")
    init_action.add_argument("--resume", action="store_true", help="preserve existing contract bytes and create its missing report; no title needed")
    init.set_defaults(handler=command_init)

    record = subparsers.add_parser(
        "record", help="record an explicit obligation result (Unix only)",
        description="Update one explicit result using Unix file locking. Reference arguments replace its current sets; run files are preserved. Does not infer pass or check completion.",
    )
    record.json_errors = True
    record.add_argument("--directory", default=".confidence")
    record.add_argument("--obligation", required=True)
    record.add_argument("--status", choices=STATUSES, required=True)
    record.add_argument("--details", required=True)
    record.add_argument("--run", action="append", default=[])
    record.add_argument("--diagnostic-run", action="append", default=[])
    record.add_argument("--artifact", action="append", default=[])
    record.set_defaults(handler=command_record)

    run = subparsers.add_parser("run", help="run a command and capture evidence")
    run.add_argument("--id", help="unique run ID; generated when omitted")
    run.add_argument("--cwd", default=".", help="command execution directory (default: caller current directory)")
    run.add_argument("--directory", default=".confidence", help="evidence directory, relative to caller cwd, not --cwd (default: .confidence)")
    run.add_argument(
        "--json", action="store_true",
        help="emit a compact JSON receipt instead of replaying the captured log",
    )
    run.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    run.add_argument(
        "--max-log-bytes",
        type=positive_int,
        default=DEFAULT_MAX_LOG_BYTES,
    )
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(handler=command_run)

    validate = subparsers.add_parser("validate", help="validate evidence files")
    validate.add_argument("--directory", default=".confidence")
    validate.add_argument(
        "--require-complete",
        action="store_true",
        help="also require all proof and release gates to pass",
    )
    validate.set_defaults(handler=command_validate)

    render = subparsers.add_parser("render", help="render a Markdown report")
    render.add_argument("--directory", default=".confidence")
    render.add_argument("--output")
    render.add_argument("--force", action="store_true")
    render.set_defaults(handler=command_render)

    doctor = subparsers.add_parser("doctor", help="check the local installation")
    doctor.add_argument("--directory", default=".confidence")
    doctor.add_argument(
        "--probe-telemetry",
        action="store_true",
        help="send one safe probe to the configured telemetry endpoint",
    )
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    bundle = subparsers.add_parser(
        "support-bundle", help="create a redacted diagnostics archive"
    )
    bundle.add_argument("--directory", default=".confidence")
    bundle.add_argument("--output")
    bundle.add_argument("--force", action="store_true")
    bundle.set_defaults(handler=command_support_bundle)
    return root


def main() -> int:
    args = parser().parse_args()
    requested_operation_id = os.environ.get("CONFIDENCE_OPERATION_ID", "")
    operation_id = (
        requested_operation_id
        if re.fullmatch(r"[0-9a-f]{32}", requested_operation_id)
        else os.urandom(16).hex()
    )
    directory = Path(getattr(args, "directory", ".confidence"))
    started = time.monotonic()
    record_event(
        directory,
        operation_id=operation_id,
        event_name="command.started",
        command=args.action,
        status="started",
    )
    previous_signals = {}
    if args.action == "run":
        def interrupt_run(signum: int, _frame: Any) -> None:
            if getattr(args, "interrupted_signal", None) is None:
                args.interrupted_signal = signum
                if not getattr(args, "defer_run_interrupt", False):
                    raise KeyboardInterrupt
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_signals[signum] = signal.signal(signum, interrupt_run)
    try:
        exit_code = args.handler(args)
    except KeyboardInterrupt:
        exit_code = 128 + getattr(args, "interrupted_signal", signal.SIGINT)
    except Exception:
        frames = traceback.extract_tb(sys.exc_info()[2])
        last_frame = frames[-1] if frames else None
        record_event(
            directory,
            operation_id=operation_id,
            event_name="command.crashed",
            command=args.action,
            status="error",
            error_code="INTERNAL_ERROR",
            duration_seconds=time.monotonic() - started,
            component=(
                f"{Path(last_frame.filename).name}.{last_frame.name}"
                if last_frame
                else "confidence.internal"
            ),
            line=last_frame.lineno if last_frame else None,
            export=True,
        )
        print(
            f"confidence internal error; diagnostic operation {operation_id}",
            file=sys.stderr,
        )
        if os.environ.get("CONFIDENCE_DEBUG") == "1":
            traceback.print_exc()
        return 125
    finally:
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
    error_code = getattr(args, "diagnostic_error_code", None) or error_code_for(
        args.action, exit_code
    )
    record_event(
        directory,
        operation_id=operation_id,
        event_name="command.completed",
        command=args.action,
        status="ok" if exit_code == 0 else "error",
        error_code=error_code,
        duration_seconds=time.monotonic() - started,
        export=True,
    )
    if exit_code != 0:
        print(f"diagnostic operation {operation_id}: {error_code}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
