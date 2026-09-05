"""Small, privacy-bounded diagnostics for the Confidence Protocol CLI."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
TOOL_VERSION = "0.4.0+codex.20260827050000"
MAX_EVENT_BYTES = 8_192
MAX_EVENT_LOG_BYTES = 1_000_000
REMOTE_TIMEOUT_SECONDS = 1.0
SAFE_EVENT_KEYS = {
    "schema_version",
    "event_id",
    "operation_id",
    "installation_id",
    "timestamp",
    "tool_version",
    "event",
    "command",
    "status",
    "error_code",
    "duration_bucket",
    "platform",
    "python_version",
    "component",
    "line",
}
SAFE_REMOTE_KEYS = SAFE_EVENT_KEYS - {"component", "line"}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")
ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")
PYTHON_VERSION = re.compile(r"^[0-9]{1,2}\.[0-9]{1,2}$")
EVENT_NAMES = {
    "command.started",
    "command.completed",
    "command.crashed",
    "telemetry.delivery_failed",
    "telemetry.probe",
}
COMMANDS = {"init", "run", "validate", "render", "doctor", "support-bundle"}
STATUSES = {"started", "ok", "error"}
DURATION_BUCKETS = {
    "lt_100ms",
    "100ms_to_1s",
    "1s_to_10s",
    "10s_to_60s",
    "gte_60s",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def duration_bucket(duration_seconds: float) -> str:
    milliseconds = max(0, int(duration_seconds * 1000))
    if milliseconds < 100:
        return "lt_100ms"
    if milliseconds < 1_000:
        return "100ms_to_1s"
    if milliseconds < 10_000:
        return "1s_to_10s"
    if milliseconds < 60_000:
        return "10s_to_60s"
    return "gte_60s"


def error_code_for(command: str, exit_code: int) -> str | None:
    if exit_code == 0:
        return None
    if command == "run":
        return {
            122: "RUN_LOG_LIMIT",
            124: "RUN_TIMEOUT",
            130: "RUN_INTERRUPTED",
        }.get(exit_code, "CHILD_EXIT_NONZERO")
    if command == "validate" and exit_code == 1:
        return "EVIDENCE_INVALID"
    if command == "render" and exit_code == 1:
        return "EVIDENCE_INVALID"
    if exit_code == 2:
        return "INVALID_INPUT"
    if command == "doctor":
        return "DOCTOR_FAILED"
    if command == "support-bundle":
        return "SUPPORT_BUNDLE_FAILED"
    return "COMMAND_FAILED"


def endpoint_error(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        parsed.port
    except ValueError:
        return "TELEMETRY_ENDPOINT_INVALID"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "TELEMETRY_ENDPOINT_UNSAFE"
    if not parsed.hostname:
        return "TELEMETRY_ENDPOINT_INVALID"
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        return "TELEMETRY_ENDPOINT_NOT_HTTPS"
    return None


def _safe_directory(directory: Path) -> Path | None:
    if directory.is_symlink():
        return None
    try:
        resolved = directory.resolve()
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return resolved


def _installation_id(telemetry_directory: Path) -> str | None:
    path = telemetry_directory / "installation-id"
    try:
        if path.is_symlink():
            return None
        if path.exists():
            value = path.read_text(encoding="ascii").strip()
            return value if SAFE_IDENTIFIER.fullmatch(value) else None
        value = uuid.uuid4().hex
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(value + "\n")
            output.flush()
            os.fsync(output.fileno())
        return value
    except FileExistsError:
        try:
            value = path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            return None
        return value if SAFE_IDENTIFIER.fullmatch(value) else None
    except (OSError, UnicodeError):
        return None


def _append_event(path: Path, event: dict[str, Any]) -> bool:
    line = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    if len(line) > MAX_EVENT_BYTES:
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        if path.is_symlink():
            return False
        descriptor = os.open(path, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return False
            if metadata.st_size + len(line) > MAX_EVENT_LOG_BYTES:
                return False
            written = os.write(descriptor, line)
            os.fsync(descriptor)
            return written == len(line)
        finally:
            os.close(descriptor)
    except OSError:
        return False


def safe_event(event: dict[str, Any], include_local: bool = False) -> dict[str, Any]:
    """Return only fields and values created by this tool."""
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
    }
    for key in ("event_id", "operation_id", "installation_id"):
        item = event.get(key)
        if isinstance(item, str) and OPAQUE_ID.fullmatch(item):
            value[key] = item
    timestamp = event.get("timestamp")
    if isinstance(timestamp, str) and len(timestamp) <= 40:
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            value["timestamp"] = timestamp
    event_name = event.get("event")
    if isinstance(event_name, str) and event_name in EVENT_NAMES:
        value["event"] = event_name
    command = event.get("command")
    if isinstance(command, str) and command in COMMANDS:
        value["command"] = command
    status = event.get("status")
    if isinstance(status, str) and status in STATUSES:
        value["status"] = status
    error_code = event.get("error_code")
    if isinstance(error_code, str) and ERROR_CODE.fullmatch(error_code):
        value["error_code"] = error_code
    bucket = event.get("duration_bucket")
    if isinstance(bucket, str) and bucket in DURATION_BUCKETS:
        value["duration_bucket"] = bucket
    if event.get("platform") == sys.platform:
        value["platform"] = sys.platform
    python_version = event.get("python_version")
    if isinstance(python_version, str) and PYTHON_VERSION.fullmatch(python_version):
        value["python_version"] = python_version
    if include_local:
        component = event.get("component")
        if isinstance(component, str) and SAFE_IDENTIFIER.fullmatch(component):
            value["component"] = component
        line = event.get("line")
        if isinstance(line, int) and line > 0:
            value["line"] = line
    return value


def _remote_payload(event: dict[str, Any]) -> dict[str, Any]:
    return safe_event(event)


def send_remote_event(event: dict[str, Any], endpoint: str, token: str | None) -> str | None:
    invalid = endpoint_error(endpoint)
    if invalid:
        return invalid
    body = json.dumps(_remote_payload(event), separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"confidence-protocol/{TOOL_VERSION}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT_SECONDS) as response:
            if not 200 <= response.status < 300:
                return f"TELEMETRY_HTTP_{response.status}"
    except urllib.error.HTTPError as error:
        return f"TELEMETRY_HTTP_{error.code}"
    except urllib.error.URLError:
        return "TELEMETRY_UNREACHABLE"
    except (OSError, TimeoutError):
        return "TELEMETRY_UNREACHABLE"
    return None


def record_event(
    directory: Path,
    *,
    operation_id: str,
    event_name: str,
    command: str,
    status: str,
    error_code: str | None = None,
    duration_seconds: float | None = None,
    component: str | None = None,
    line: int | None = None,
    export: bool = False,
) -> None:
    """Best-effort diagnostics. This function never raises."""
    try:
        if os.environ.get("CONFIDENCE_DISABLE_DIAGNOSTICS") == "1":
            return
        root = _safe_directory(directory)
        if root is None:
            return
        telemetry_directory = root / "telemetry"
        if telemetry_directory.is_symlink():
            return
        telemetry_directory.mkdir(parents=True, exist_ok=True)
        installation_id = _installation_id(telemetry_directory)
        if not OPAQUE_ID.fullmatch(operation_id):
            operation_id = uuid.uuid4().hex
        event: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex,
            "operation_id": operation_id,
            "timestamp": utc_now(),
            "tool_version": TOOL_VERSION,
            "event": event_name,
            "command": command,
            "status": status,
            "platform": sys.platform,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
        if installation_id:
            event["installation_id"] = installation_id
        if error_code:
            event["error_code"] = error_code
        if duration_seconds is not None:
            event["duration_bucket"] = duration_bucket(duration_seconds)
        if component and SAFE_IDENTIFIER.fullmatch(component):
            event["component"] = component
        if isinstance(line, int) and line > 0:
            event["line"] = line
        if not _append_event(telemetry_directory / "events.jsonl", event):
            return

        endpoint = os.environ.get("CONFIDENCE_TELEMETRY_ENDPOINT")
        if not export or not endpoint:
            return
        failure = send_remote_event(
            event, endpoint, os.environ.get("CONFIDENCE_TELEMETRY_TOKEN")
        )
        if failure:
            delivery_event = dict(event)
            delivery_event.update(
                {
                    "event_id": uuid.uuid4().hex,
                    "timestamp": utc_now(),
                    "event": "telemetry.delivery_failed",
                    "status": "error",
                    "error_code": failure,
                }
            )
            _append_event(telemetry_directory / "events.jsonl", delivery_event)
    except (Exception, KeyboardInterrupt):
        return


def _check(code: str, status: str, summary: str, remediation: str = "") -> dict[str, str]:
    return {
        "code": code,
        "status": status,
        "summary": summary,
        "remediation": remediation,
    }


def doctor_report(directory: Path, probe_telemetry: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(
        _check(
            "PYTHON_VERSION",
            "pass" if python_ok else "fail",
            f"Python {platform.python_version()}",
            "Install Python 3.10 or newer." if not python_ok else "",
        )
    )

    manifest = Path(__file__).resolve().parents[3] / ".codex-plugin" / "plugin.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_ok = (
            value.get("name") == "confidence-protocol"
            and value.get("version") == TOOL_VERSION
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifest_ok = False
    checks.append(
        _check(
            "PLUGIN_MANIFEST",
            "pass" if manifest_ok else "fail",
            "Plugin manifest and CLI version match." if manifest_ok else "Plugin manifest is missing, invalid, or has a different version.",
            "Reinstall the plugin from one complete release." if not manifest_ok else "",
        )
    )

    root = _safe_directory(directory)
    writable = False
    hardlinks = False
    if root is not None:
        try:
            descriptor, source_name = tempfile.mkstemp(prefix="doctor-", dir=root)
            os.close(descriptor)
            source = Path(source_name)
            link = source.with_name(source.name + ".link")
            os.link(source, link)
            hardlinks = True
            link.unlink()
            source.unlink()
            writable = True
        except OSError:
            for candidate in (locals().get("link"), locals().get("source")):
                if isinstance(candidate, Path):
                    candidate.unlink(missing_ok=True)
    checks.append(
        _check(
            "EVIDENCE_DIRECTORY",
            "pass" if writable else "fail",
            "Evidence directory is writable." if writable else "Evidence directory is not safely writable.",
            "Choose a local, writable, non-symlink evidence directory." if not writable else "",
        )
    )
    checks.append(
        _check(
            "ATOMIC_HARDLINK",
            "pass" if hardlinks else "fail",
            "Filesystem supports atomic evidence records." if hardlinks else "Filesystem does not support the required hard links.",
            "Use a local filesystem with hard-link support." if not hardlinks else "",
        )
    )

    try:
        smoke = subprocess.run(
            [sys.executable, "-c", "raise SystemExit(0)"],
            timeout=5,
            check=False,
        )
        runner_ok = smoke.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        runner_ok = False
    checks.append(
        _check(
            "RUNNER_SMOKE",
            "pass" if runner_ok else "fail",
            "Subprocess runner works." if runner_ok else "Subprocess runner failed.",
            "Check Python execution permissions and process limits." if not runner_ok else "",
        )
    )

    git_ok = shutil.which("git") is not None
    checks.append(
        _check(
            "GIT_AVAILABLE",
            "pass" if git_ok else "warn",
            "Git is available." if git_ok else "Git is missing, so workspace drift cannot be recorded.",
            "Install Git for workspace-bound evidence." if not git_ok else "",
        )
    )
    posix = os.name == "posix"
    checks.append(
        _check(
            "PROCESS_GROUP_CLEANUP",
            "pass" if posix else "warn",
            "Child process-group cleanup is supported." if posix else "Only direct child cleanup is supported on this platform.",
            "Use POSIX for proven descendant cleanup." if not posix else "",
        )
    )

    legacy = shutil.which("bonaparte")
    checks.append(
        _check(
            "LEGACY_BONAPARTE",
            "warn" if legacy else "pass",
            "A legacy Bonaparte command is still on PATH." if legacy else "No legacy Bonaparte command was found on PATH.",
            "Remove the old Tweed installation if your team no longer uses it." if legacy else "",
        )
    )

    endpoint = os.environ.get("CONFIDENCE_TELEMETRY_ENDPOINT")
    endpoint_problem = endpoint_error(endpoint)
    if endpoint_problem:
        checks.append(
            _check(
                "TELEMETRY_CONFIG",
                "fail",
                f"Telemetry configuration failed: {endpoint_problem}.",
                "Use an HTTPS endpoint without credentials, query text, or fragments.",
            )
        )
    elif not endpoint:
        checks.append(
            _check(
                "TELEMETRY_CONFIG",
                "pass",
                "Remote telemetry is disabled.",
            )
        )
    else:
        checks.append(_check("TELEMETRY_CONFIG", "pass", "Remote telemetry is configured."))

    if probe_telemetry:
        if not endpoint or endpoint_problem:
            checks.append(
                _check(
                    "TELEMETRY_PROBE",
                    "fail",
                    "Telemetry probe could not run because the endpoint is not valid.",
                    "Configure CONFIDENCE_TELEMETRY_ENDPOINT, then retry the probe.",
                )
            )
        else:
            probe = {
                "schema_version": SCHEMA_VERSION,
                "event_id": uuid.uuid4().hex,
                "operation_id": uuid.uuid4().hex,
                "timestamp": utc_now(),
                "tool_version": TOOL_VERSION,
                "event": "telemetry.probe",
                "command": "doctor",
                "status": "ok",
                "platform": sys.platform,
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            }
            failure = send_remote_event(
                probe, endpoint, os.environ.get("CONFIDENCE_TELEMETRY_TOKEN")
            )
            checks.append(
                _check(
                    "TELEMETRY_PROBE",
                    "fail" if failure else "pass",
                    f"Telemetry probe failed: {failure}." if failure else "Telemetry endpoint accepted the probe.",
                    "Check collector availability, TLS, and credentials." if failure else "",
                )
            )

    overall = "fail" if any(item["status"] == "fail" for item in checks) else "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "status": overall,
        "checks": checks,
    }


def safe_events(directory: Path) -> list[dict[str, Any]]:
    path = directory / "telemetry" / "events.jsonl"
    if not path.is_file() or path.is_symlink():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(safe_event(value, include_local=True))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    return events[-1_000:]


def safe_run_records(directory: Path) -> list[dict[str, Any]]:
    runs = directory / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(runs.glob("*.json"))[:1_000]:
        if path.is_symlink():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        workspace = value.get("workspace")
        safe_workspace = None
        if isinstance(workspace, dict):
            kind = workspace.get("kind")
            fingerprint = workspace.get("sha256")
            if kind == "git" and isinstance(fingerprint, str) and re.fullmatch(
                r"[0-9a-f]{64}", fingerprint
            ):
                safe_workspace = {"kind": kind, "sha256": fingerprint}
        safe_timestamps: dict[str, str] = {}
        for key in ("started_at", "ended_at"):
            item = value.get(key)
            if not isinstance(item, str) or len(item) > 40:
                continue
            try:
                datetime.fromisoformat(item.replace("Z", "+00:00"))
            except ValueError:
                continue
            safe_timestamps[key] = item
        exit_code = value.get("exit_code")
        if not isinstance(exit_code, int) or not -255 <= exit_code <= 255:
            exit_code = None
        termination_reason = value.get("termination_reason")
        if termination_reason not in {None, "timeout", "log_limit"}:
            termination_reason = None
        log_sha256 = value.get("log_sha256")
        if not isinstance(log_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", log_sha256
        ):
            log_sha256 = None
        records.append(
            {
                "version": 1 if value.get("version") == 1 else None,
                **safe_timestamps,
                "exit_code": exit_code,
                "termination_reason": termination_reason,
                "workspace": safe_workspace,
                "log_sha256": log_sha256,
            }
        )
    return records


def write_support_bundle(directory: Path, output: Path, force: bool = False) -> None:
    if output.is_symlink() or (output.exists() and not force):
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.tmp-", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "README.txt",
                "Redacted Confidence Protocol diagnostics. No command arguments, command output, source, prompts, file paths, environment values, usernames, or hostnames are included.\n",
            )
            archive.writestr(
                "doctor.json",
                json.dumps(doctor_report(directory), indent=2) + "\n",
            )
            archive.writestr(
                "events.json",
                json.dumps(safe_events(directory), indent=2) + "\n",
            )
            archive.writestr(
                "runs.json",
                json.dumps(safe_run_records(directory), indent=2) + "\n",
            )
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
