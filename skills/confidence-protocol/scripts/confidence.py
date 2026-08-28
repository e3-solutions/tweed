#!/usr/bin/env python3
"""Create, validate, and render Confidence Protocol evidence files."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import signal
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
        raw = path.read_text(encoding="utf-8")
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
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_workspace_fingerprint(cwd: Path, evidence_directory: Path) -> dict[str, str] | None:
    root_result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if root_result.returncode != 0:
        return None
    root = Path(root_result.stdout.decode("utf-8", "surrogateescape").strip()).resolve()
    head_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
    )
    if head_result.returncode != 0:
        return None

    pathspec = ["."]
    try:
        evidence_relative = evidence_directory.resolve().relative_to(root)
    except ValueError:
        evidence_relative = None
    if evidence_relative is not None:
        pathspec.append(f":(exclude){evidence_relative.as_posix()}/**")

    diff_result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--binary",
            "--no-ext-diff",
            "HEAD",
            "--",
            *pathspec,
        ],
        capture_output=True,
        check=False,
    )
    status_result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            *pathspec,
        ],
        capture_output=True,
        check=False,
    )
    if diff_result.returncode != 0 or status_result.returncode != 0:
        return None

    digest = hashlib.sha256()
    digest.update(b"head\0")
    digest.update(head_result.stdout.strip())
    digest.update(b"\0diff\0")
    digest.update(diff_result.stdout)

    untracked: list[str] = []
    for entry in status_result.stdout.split(b"\0"):
        if entry.startswith(b"?? "):
            untracked.append(entry[3:].decode("utf-8", "surrogateescape"))
    for relative_name in sorted(untracked):
        path = root / relative_name
        digest.update(b"\0untracked\0")
        digest.update(relative_name.encode("utf-8", "surrogateescape"))
        try:
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(65536), b""):
                        digest.update(chunk)
            else:
                digest.update(b"other\0")
        except OSError:
            return None
    return {"kind": "git", "root": str(root), "sha256": digest.hexdigest()}


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
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
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
    if record.get("version") != 1:
        errors.append(f"{label}.version must be 1")
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
        except FileNotFoundError:
            errors.append(f"missing file: {log_path}")
        else:
            if actual_sha256 != log_sha256:
                errors.append(f"{label} log hash does not match")
    workspace = record.get("workspace")
    if workspace is not None:
        if not isinstance(workspace, dict):
            errors.append(f"{label}.workspace must be an object or null")
        else:
            if workspace.get("kind") != "git":
                errors.append(f"{label}.workspace.kind must be git")
            if not isinstance(workspace.get("root"), str) or not Path(
                workspace.get("root", "")
            ).is_absolute():
                errors.append(f"{label}.workspace.root must be an absolute path")
            fingerprint = workspace.get("sha256")
            if not isinstance(fingerprint, str) or not SHA256_PATTERN.fullmatch(
                fingerprint
            ):
                errors.append(f"{label}.workspace.sha256 must be a SHA-256 digest")
    return record, errors


def validate_supporting_workspace(
    record: dict[str, Any], evidence_directory: Path
) -> list[str]:
    workspace = record.get("workspace")
    if workspace is None:
        return []
    current = git_workspace_fingerprint(Path(record["cwd"]), evidence_directory)
    if current is None:
        return [f"run {record['id']} workspace can no longer be fingerprinted"]
    if current["root"] != workspace["root"] or current["sha256"] != workspace["sha256"]:
        return [f"run {record['id']} is stale because the Git workspace changed"]
    return []


def validate_report(
    report: dict[str, Any], contract: dict[str, Any], directory: Path
) -> list[str]:
    errors: list[str] = []
    evidence = report.get("evidence")
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
                    errors.extend(
                        f"{label}: {error}"
                        for error in validate_supporting_workspace(record, directory)
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
    directory = Path(args.directory)
    if directory.is_symlink():
        print(f"refusing symlink evidence directory: {directory}", file=sys.stderr)
        return 2
    contract_path = directory / "contract.json"
    report_path = directory / "report.json"
    symlinks = [str(path) for path in (contract_path, report_path) if path.is_symlink()]
    if symlinks:
        print("refusing symlink evidence file: " + ", ".join(symlinks), file=sys.stderr)
        return 2
    existing = [
        str(path) for path in (contract_path, report_path) if os.path.lexists(path)
    ]
    if existing and not args.force:
        print("refusing to overwrite: " + ", ".join(existing), file=sys.stderr)
        return 2
    write_json(contract_path, initial_contract(args.title, args.mode, args.task_type))
    write_json(report_path, initial_report(args.title, args.mode))
    print(f"created {contract_path} and {report_path}")
    print("fill the empty fields, then run validate")
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
        print(f"refusing to overwrite run: {run_id}", file=sys.stderr)
        return 125

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        args.diagnostic_error_code = "RUN_CWD_INVALID"
        print(f"run cwd is not a directory: {cwd}", file=sys.stderr)
        return 125

    started_at = utc_now()
    try:
        log = log_path.open("xb")
    except FileExistsError:
        args.diagnostic_error_code = "RUN_ID_EXISTS"
        print(f"refusing to overwrite run: {run_id}", file=sys.stderr)
        return 125
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
        args.diagnostic_error_code = "RUN_LAUNCH_FAILED"
        log.close()
        log_path.unlink(missing_ok=True)
        print(f"could not start command: {error}", file=sys.stderr)
        return 125

    deadline = time.monotonic() + args.timeout_seconds
    termination_reason: str | None = None
    try:
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
        stop_process(process)
        log.close()
        log_path.unlink(missing_ok=True)
        print(f"run {run_id}: interrupted; no evidence record written", file=sys.stderr)
        return 130
    except OSError as error:
        args.diagnostic_error_code = "RUN_CAPTURE_FAILED"
        stop_process(process)
        log.close()
        log_path.unlink(missing_ok=True)
        print(
            f"run {run_id}: capture failed ({error}); no evidence record written",
            file=sys.stderr,
        )
        return 125
    finally:
        if not log.closed:
            log.flush()
            os.fsync(log.fileno())
            log.close()

    if termination_reason:
        with log_path.open("ab") as output:
            output.write(f"\n[confidence runner stopped: {termination_reason}]\n".encode())

    digest = hashlib.sha256()
    stream_to_terminal = True
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
        "version": 1,
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


def command_validate(args: argparse.Namespace) -> int:
    try:
        _, report, errors = load_and_validate(Path(args.directory))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if not errors and args.require_complete:
        errors.extend(completion_errors(report))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.require_complete:
        print("confidence evidence is complete and release-ready")
    else:
        print("confidence evidence is structurally valid")
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
    return f"""# Confidence Report: {markdown_text(task['title'])}

Mode: {task['mode']}  
Task type: {task['type']}

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


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create evidence file templates")
    init.add_argument("--title", required=True)
    init.add_argument("--mode", choices=MODES, default="standard")
    init.add_argument("--task-type", choices=TASK_TYPES, default="feature")
    init.add_argument("--directory", default=".confidence")
    init.add_argument("--force", action="store_true")
    init.set_defaults(handler=command_init)

    run = subparsers.add_parser("run", help="run a command and capture evidence")
    run.add_argument("--id")
    run.add_argument("--cwd", default=".")
    run.add_argument("--directory", default=".confidence")
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
        command=args.command,
        status="started",
    )
    try:
        exit_code = args.handler(args)
    except KeyboardInterrupt:
        exit_code = 130
    except Exception:
        frames = traceback.extract_tb(sys.exc_info()[2])
        last_frame = frames[-1] if frames else None
        record_event(
            directory,
            operation_id=operation_id,
            event_name="command.crashed",
            command=args.command,
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
    error_code = getattr(args, "diagnostic_error_code", None) or error_code_for(
        args.command, exit_code
    )
    record_event(
        directory,
        operation_id=operation_id,
        event_name="command.completed",
        command=args.command,
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
