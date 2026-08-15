"""Privacy-bounded progress reporting and native event normalization."""

from __future__ import annotations

import json
import os
import shlex
import threading
import time
from pathlib import Path

PROGRESS_FD_ENV = "BONAPARTE_PROGRESS_FD"
PROGRESS_VERSION = 2
PROGRESS_HEARTBEAT_SECONDS = 10.0
PROGRESS_MAX_BYTES = 4096
PROGRESS_MAX_LINE_BYTES = 1024 * 1024
PROGRESS_MAX_MILESTONES = 32
PROGRESS_MAX_ACTORS = 32
MAX_COMPLETED_CHECKS = 100

PHASES = {"create", "rca", "scope", "implement", "review", "publish"}
PROGRESS_STAGES = {
    "coordinating",
    "searching",
    "tool-use",
    "checking",
    "file-changes",
    "subagent-assignment",
    "subagent-completion",
    "waiting-input",
    "finalizing",
    "terminal",
}
PROGRESS_ACTIVITIES = {
    "lifecycle",
    "search",
    "tool",
    "check",
    "file-change",
    "subagent",
}
PROGRESS_STATUSES = {
    "started",
    "in-progress",
    "completed",
    "failed",
    "waiting",
    "interrupted",
}
PROGRESS_STATES = {
    "started",
    "active",
    "finalizing",
    "completed",
    "needs-input",
    "blocked",
    "failed",
    "interrupted",
}
PROGRESS_TERMINAL_STATES = {
    "completed",
    "needs-input",
    "blocked",
    "failed",
    "interrupted",
}


def safe_semantic(value: dict | None) -> dict:
    """Return only the fixed, string-free semantic progress vocabulary."""
    if not isinstance(value, dict) or value.get("stage") not in PROGRESS_STAGES:
        return {
            "stage": "coordinating",
            "actor": "coordinator",
            "activity": "lifecycle",
            "status": "in-progress",
            "count": None,
        }
    semantic = {
        "stage": value["stage"],
        "actor": None,
        "activity": None,
        "status": None,
        "count": None,
    }
    actor = value.get("actor")
    if actor == "coordinator" or (
        isinstance(actor, str)
        and actor.startswith("subagent-")
        and actor.removeprefix("subagent-").isascii()
        and actor.removeprefix("subagent-").isdecimal()
        and int(actor.removeprefix("subagent-")) > 0
    ):
        semantic["actor"] = actor
    if value.get("activity") in PROGRESS_ACTIVITIES:
        semantic["activity"] = value["activity"]
    if value.get("status") in PROGRESS_STATUSES:
        semantic["status"] = value["status"]
    count = value.get("count")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        semantic["count"] = min(count, 2**31 - 1)
    return semantic


class ProgressReporter:
    """Emit privacy-bounded semantic lifecycle events to an isolated descriptor."""

    def __init__(self, descriptor: int | None, phase: str = "review"):
        self._descriptor = descriptor
        self._phase = phase if phase in PHASES else "review"
        self._started_at = time.monotonic()
        self._sequence = 0
        self._last_state: str | None = None
        self._terminal = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._heartbeat: threading.Thread | None = None
        self._start_attempted = False
        self._heartbeat_running = threading.Event()
        self._semantic = safe_semantic(
            {
                "stage": "coordinating",
                "actor": "coordinator",
                "activity": "lifecycle",
                "status": "started",
            }
        )
        self._milestones: list[dict] = []
        self._milestones_total_count = 0
        self._milestones_truncated = False

    def _disable_locked(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def update_semantic(self, semantic: dict, *, milestone: bool = False) -> None:
        safe = safe_semantic(semantic)
        with self._lock:
            self._semantic = safe
            if milestone and safe not in self._milestones:
                self._milestones_total_count += 1
                self._milestones.append(dict(safe))
                if len(self._milestones) > PROGRESS_MAX_MILESTONES:
                    del self._milestones[0]
                    self._milestones_truncated = True

    def restore_semantic(self, checkpoint: dict) -> None:
        safe = safe_semantic(checkpoint.get("semantic"))
        milestones = checkpoint.get("semantic_milestones")
        if not isinstance(milestones, list):
            milestones = []
        with self._lock:
            self._semantic = safe
            self._milestones = []
            for value in milestones[-PROGRESS_MAX_MILESTONES:]:
                item = safe_semantic(value)
                if item not in self._milestones:
                    self._milestones.append(item)
            total = checkpoint.get(
                "semantic_milestones_total_count", len(self._milestones)
            )
            self._milestones_total_count = (
                total
                if isinstance(total, int)
                and not isinstance(total, bool)
                and total >= len(self._milestones)
                else len(self._milestones)
            )
            self._milestones_truncated = bool(
                checkpoint.get("semantic_milestones_truncated")
                or self._milestones_total_count > len(self._milestones)
            )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "semantic": dict(self._semantic),
                "semantic_milestones": [dict(item) for item in self._milestones],
                "semantic_milestones_total_count": self._milestones_total_count,
                "semantic_milestones_truncated": self._milestones_truncated,
            }

    def report(self, state: str) -> None:
        if state not in PROGRESS_STATES:
            raise ValueError("invalid progress state")
        with self._lock:
            if self._descriptor is None or self._terminal:
                return
            if (
                (state == "started" and self._last_state is not None)
                or (state == "active" and self._last_state not in {"started", "active"})
                or (
                    state == "finalizing"
                    and self._last_state not in {"started", "active"}
                )
                or (
                    state in PROGRESS_TERMINAL_STATES
                    and self._last_state != "finalizing"
                )
            ):
                return
            sequence = self._sequence + 1
            event = {
                "version": PROGRESS_VERSION,
                "sequence": sequence,
                "phase": self._phase,
                "state": state,
                "elapsed_seconds": round(
                    max(0.0, time.monotonic() - self._started_at), 3
                ),
                "semantic": dict(self._semantic),
            }
            if self._milestones:
                event["semantic"]["milestones"] = [
                    dict(item) for item in self._milestones
                ]
                event["semantic"][
                    "milestones_total_count"
                ] = self._milestones_total_count
                event["semantic"]["milestones_truncated"] = self._milestones_truncated
            if state == "finalizing":
                event["semantic"].update(
                    stage="finalizing",
                    activity="lifecycle",
                    status="in-progress",
                    count=None,
                )
            elif state == "needs-input":
                event["semantic"].update(
                    stage="waiting-input",
                    actor="coordinator",
                    activity="lifecycle",
                    status="waiting",
                    count=None,
                )
            elif state in PROGRESS_TERMINAL_STATES:
                terminal_status = (
                    "completed"
                    if state == "completed"
                    else "interrupted" if state == "interrupted" else "failed"
                )
                event["semantic"].update(
                    stage="terminal",
                    activity="lifecycle",
                    status=terminal_status,
                    count=None,
                )
            try:
                payload = (
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode("utf-8")
            except (TypeError, ValueError, UnicodeError, OverflowError):
                self._disable_locked()
                return
            while len(payload) > PROGRESS_MAX_BYTES and event["semantic"].get(
                "milestones"
            ):
                del event["semantic"]["milestones"][0]
                event["semantic"]["milestones_truncated"] = True
                payload = (
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode("utf-8")
            if len(payload) > PROGRESS_MAX_BYTES:
                event["semantic"] = safe_semantic(self._semantic)
                payload = (
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode("utf-8")
            if len(payload) > PROGRESS_MAX_BYTES:
                self._disable_locked()
                return
            try:
                written = os.write(self._descriptor, payload)
            except OSError:
                self._disable_locked()
                return
            if written != len(payload):
                self._disable_locked()
                return
            self._sequence = sequence
            self._last_state = state
            if state in PROGRESS_TERMINAL_STATES:
                self._terminal = True

    def start(self) -> None:
        if self._descriptor is None or self._start_attempted:
            return
        self._start_attempted = True
        self.report("started")
        if self._descriptor is None:
            return
        heartbeat = None
        try:
            heartbeat = threading.Thread(
                target=self._heartbeat_loop,
                name="bonaparte-review-progress",
                daemon=True,
            )
            self._heartbeat = heartbeat
            heartbeat.start()
        except Exception:  # noqa: BLE001 - optional progress is best effort
            self._stop.set()
            if heartbeat is not None:
                try:
                    heartbeat.join()
                except Exception:  # noqa: BLE001 - preserve the coordinator path
                    pass
            self._heartbeat = None
            with self._lock:
                self._disable_locked()

    def _heartbeat_loop(self) -> None:
        self._heartbeat_running.set()
        while not self._stop.wait(PROGRESS_HEARTBEAT_SECONDS):
            self.report("active")

    def stop_heartbeat(self) -> None:
        self._stop.set()
        heartbeat = self._heartbeat
        if heartbeat is not None:
            try:
                heartbeat.join()
            except RuntimeError:
                pass
        self._heartbeat = None

    def close(self) -> None:
        self.stop_heartbeat()
        with self._lock:
            self._disable_locked()


def acquire_progress_reporter(
    enabled: bool = True, phase: str = "review"
) -> ProgressReporter:
    """Consume the inherited descriptor without ever exposing it to a child."""

    raw_descriptor = os.environ.pop(PROGRESS_FD_ENV, None)
    if (
        raw_descriptor is None
        or not raw_descriptor.isascii()
        or not raw_descriptor.isdecimal()
    ):
        return ProgressReporter(None, phase)
    try:
        original = int(raw_descriptor)
    except ValueError:
        return ProgressReporter(None, phase)
    if original < 3:
        return ProgressReporter(None, phase)
    if not enabled:
        try:
            os.close(original)
        except (OSError, OverflowError):
            pass
        return ProgressReporter(None, phase)
    duplicate = None
    try:
        duplicate = os.dup(original)
        os.set_inheritable(duplicate, False)
        if os.get_blocking(duplicate):
            os.close(duplicate)
            duplicate = None
    except (OSError, OverflowError, ValueError):
        if duplicate is not None:
            try:
                os.close(duplicate)
            except (OSError, OverflowError):
                pass
        return ProgressReporter(None, phase)
    finally:
        try:
            os.close(original)
        except (OSError, OverflowError):
            pass
    return ProgressReporter(duplicate, phase)


class EventObserver:
    """Normalize current Codex events without retaining native payloads."""

    def __init__(self, progress: ProgressReporter | None = None):
        self.observation = {
            "session_id": None,
            "checks_completed": [],
            "checks_completed_total_count": 0,
            "checks_completed_truncated": False,
        }
        self._progress = progress
        self._counts = {name: 0 for name in PROGRESS_ACTIVITIES if name != "lifecycle"}
        self._actors: dict[str, str] = {}

    def _actor(self, identifier: object) -> str:
        if not isinstance(identifier, str) or not identifier:
            return "coordinator"
        if identifier not in self._actors:
            if len(self._actors) >= PROGRESS_MAX_ACTORS:
                return f"subagent-{PROGRESS_MAX_ACTORS + 1}"
            self._actors[identifier] = f"subagent-{len(self._actors) + 1}"
        return self._actors[identifier]

    @staticmethod
    def _event_status(event_type: str | None, item: dict) -> str | None:
        native = item.get("status")
        status = {
            "in_progress": "in-progress",
            "completed": "completed",
            "failed": "failed",
            "declined": "failed",
            "interrupted": "interrupted",
        }.get(native if isinstance(native, str) else None)
        if event_type == "item.started" and status == "in-progress":
            return "started"
        return status or {
            "item.started": "started",
            "item.updated": "in-progress",
            "item.completed": "completed",
        }.get(event_type)

    @staticmethod
    def _collab_agents(item: dict) -> list[tuple[str, str | None]]:
        states = item.get("agents_states")
        if isinstance(states, dict) and states:
            return [
                (identifier, state.get("status"))
                for identifier, state in states.items()
                if isinstance(identifier, str)
                and identifier
                and isinstance(state, dict)
                and isinstance(state.get("status"), str)
            ]
        receivers = item.get("receiver_thread_ids")
        if not isinstance(receivers, list):
            return []
        return [
            (identifier, None)
            for identifier in receivers
            if isinstance(identifier, str) and identifier
        ]

    @staticmethod
    def _agent_status(native_status: str | None) -> str | None:
        return {
            "pending_init": "started",
            "running": "in-progress",
            "completed": "completed",
            "errored": "failed",
            "shutdown": "completed",
            "not_found": "failed",
            "interrupted": "interrupted",
        }.get(native_status)

    def _update_progress(
        self, stage: str, activity: str, status: str, actor: str = "coordinator"
    ) -> None:
        if status in {"completed", "failed", "interrupted"}:
            self._counts[activity] += 1
            count = self._counts[activity]
        else:
            count = self._counts[activity] + 1
        if self._progress is not None:
            self._progress.update_semantic(
                {
                    "stage": stage,
                    "actor": actor,
                    "activity": activity,
                    "status": status,
                    "count": count,
                },
                milestone=status in {"completed", "failed", "interrupted"},
            )

    def _observe_collab(self, event_type: str | None, item: dict) -> None:
        tool = item.get("tool")
        stage = {
            "spawn_agent": "subagent-assignment",
            "send_input": "subagent-assignment",
            "wait": "subagent-completion",
            "close_agent": "subagent-completion",
        }.get(tool if isinstance(tool, str) else None)
        status = self._event_status(event_type, item)
        if stage is None or status is None:
            return
        agents = self._collab_agents(item)
        if not agents:
            self._update_progress(stage, "subagent", status)
            return
        for identifier, native_status in agents:
            agent_status = self._agent_status(native_status)
            effective_status = status
            if (
                status != "failed"
                and stage == "subagent-completion"
                and event_type in {"item.updated", "item.completed"}
                and agent_status is not None
            ):
                effective_status = agent_status
            self._update_progress(
                stage,
                "subagent",
                effective_status,
                self._actor(identifier),
            )

    def _observe_subagent_activity(self, item: dict) -> None:
        kind = item.get("kind")
        stage_and_status = {
            "started": ("subagent-assignment", "started"),
            "interacted": ("subagent-assignment", "in-progress"),
            "interrupted": ("subagent-completion", "interrupted"),
        }.get(kind if isinstance(kind, str) else None)
        if stage_and_status is None:
            return
        receivers = item.get("receiver_thread_ids")
        identifier = receivers[0] if isinstance(receivers, list) and receivers else None
        stage, status = stage_and_status
        self._update_progress(stage, "subagent", status, self._actor(identifier))

    def feed(self, line: str) -> None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeError):
            return
        if not isinstance(event, dict):
            return
        event_type = event.get("type")
        if not isinstance(event_type, str):
            event_type = None
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            self.observation["session_id"] = event["thread_id"]
        item = event.get("item")
        if not isinstance(item, dict):
            return
        item_type = item.get("type")
        if not isinstance(item_type, str):
            item_type = None
        status = self._event_status(event_type, item)
        if item_type == "collab_tool_call":
            self._observe_collab(event_type, item)
        elif item_type == "subagent_activity":
            self._observe_subagent_activity(item)
        mapping = {
            "web_search": ("searching", "search"),
            "mcp_tool_call": ("tool-use", "tool"),
            "file_change": ("file-changes", "file-change"),
            "command_execution": ("tool-use", "tool"),
        }
        mapped = mapping.get(item_type)
        if status and mapped:
            stage, activity = mapped
            self._update_progress(stage, activity, status)
        if event_type != "item.completed" or item_type != "command_execution":
            return
        self._observe_completed_command(item)

    def _observe_completed_command(self, item: dict) -> None:
        command = str(item.get("command") or "")[:300]
        exit_code = item.get("exit_code")
        try:
            words = [word.casefold() for word in shlex.split(command)]
        except ValueError:
            words = command.casefold().split()
        if (
            len(words) >= 3
            and Path(words[0]).name in {"sh", "bash", "zsh"}
            and words[1] in {"-c", "-lc"}
        ):
            try:
                words = [word.casefold() for word in shlex.split(words[2])]
            except ValueError:
                words = words[2].split()
        if words and Path(words[0]).name == "uv" and "run" in words[1:]:
            words = words[words.index("run") + 1 :]
        executable = Path(words[0]).name if words else ""
        known_runner = executable in {"pytest", "ruff", "black", "unittest"}
        known_subcommand = executable in {
            "cargo",
            "go",
            "make",
            "npm",
            "pnpm",
            "yarn",
            "python",
            "python3",
        } and bool(
            set(words[1:]).intersection(
                {"test", "pytest", "unittest", "lint", "check", "build"}
            )
        )
        if not (known_runner or known_subcommand):
            return
        self.observation["checks_completed_total_count"] += 1
        checks = self.observation["checks_completed"]
        if len(checks) < MAX_COMPLETED_CHECKS:
            checks.append(
                {
                    "name": command,
                    "status": "passed" if exit_code == 0 else "failed",
                    "exit_code": exit_code if isinstance(exit_code, int) else None,
                }
            )
        else:
            self.observation["checks_completed_truncated"] = True
        self._counts["check"] += 1
        if self._progress is not None:
            self._progress.update_semantic(
                {
                    "stage": "checking",
                    "actor": "coordinator",
                    "activity": "check",
                    "status": "completed" if exit_code == 0 else "failed",
                    "count": self._counts["check"],
                },
                milestone=True,
            )

    def finish(self) -> dict:
        if self._progress is not None:
            self.observation.update(self._progress.snapshot())
        return self.observation
