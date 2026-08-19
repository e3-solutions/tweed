"""Bounded Codex app-server transport owned by one Bonaparte phase."""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from bonaparte_progress import EventObserver, PROGRESS_FD_ENV, PROGRESS_MAX_LINE_BYTES

PHASE_CHILD_ENV = "BONAPARTE_PHASE_CHILD"
COORDINATOR_TERMINATE_GRACE_SECONDS = 1.0
COORDINATOR_KILL_GRACE_SECONDS = 5.0
APP_SERVER_REQUEST_TIMEOUT_SECONDS = 45.0


def find_codex() -> str:
    requested = os.environ.get("CODEX_BIN")
    candidates = (
        [shutil.which(requested)]
        if requested
        else [
            str(Path(part or ".") / "codex")
            for part in os.environ.get("PATH", "").split(os.pathsep)
        ]
    )
    for candidate in filter(None, candidates):
        try:
            subprocess.run(
                [candidate, "--version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return candidate
        except (OSError, subprocess.SubprocessError):
            pass
    raise RuntimeError("no working local Codex CLI found")


def child_environment() -> dict[str, str]:
    environment = {**os.environ, PHASE_CHILD_ENV: "1"}
    environment.pop(PROGRESS_FD_ENV, None)
    return environment


def terminate_and_reap(process: subprocess.Popen) -> None:
    """Boundedly stop the coordinator's private process group and reap it."""
    pid = getattr(process, "pid", None)

    def signal_group(sig: int) -> None:
        try:
            if isinstance(pid, int) and pid > 0:
                os.killpg(pid, sig)
            elif sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except OSError:
            pass

    def group_alive() -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return process.poll() is None
        try:
            os.killpg(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    try:
        signal_group(signal.SIGTERM)
        deadline = time.monotonic() + COORDINATOR_TERMINATE_GRACE_SECONDS
        while time.monotonic() < deadline:
            process.poll()
            if not group_alive():
                break
            time.sleep(0.01)
        if group_alive():
            signal_group(signal.SIGKILL)
        process.wait(timeout=COORDINATOR_KILL_GRACE_SECONDS)
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass


class AppServerPhaseDriver:
    """Drive one native app-server turn without retaining its raw event stream."""

    _EOF = object()

    def __init__(self, repository: Path, observer: EventObserver):
        self.observer = observer
        self.process = subprocess.Popen(
            [find_codex(), "app-server"],
            cwd=repository,
            env=child_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Codex app-server pipes are unavailable")
        self._messages: queue.Queue = queue.Queue(maxsize=64)
        self._request_id = 0
        self._last_agent_message: str | None = None
        self._receipt_thread_id: str | None = None
        self._receipt_turn_id: str | None = None
        self._issue_branch: str | None = None
        self._disposition: str | None = None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        chunks: list[str] = []
        line_bytes = 0
        discarding = False

        def emit_line(line: str) -> bool:
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeError):
                self._messages.put(
                    RuntimeError("Codex app-server returned malformed JSON")
                )
                return False
            if not isinstance(message, dict):
                self._messages.put(
                    RuntimeError("Codex app-server returned a malformed message")
                )
                return False
            self._messages.put(message)
            return True

        try:
            while True:
                chunk = self.process.stdout.readline(64 * 1024)
                if not chunk:
                    break
                ends_line = chunk.endswith("\n")
                if not discarding:
                    line_bytes += len(chunk.encode("utf-8"))
                    if line_bytes > PROGRESS_MAX_LINE_BYTES:
                        chunks.clear()
                        discarding = True
                    else:
                        chunks.append(chunk)
                if ends_line:
                    if not discarding and not emit_line("".join(chunks)):
                        return
                    chunks.clear()
                    line_bytes = 0
                    discarding = False
            if chunks and not emit_line("".join(chunks)):
                return
        except BaseException as error:
            self._messages.put(error)
        finally:
            self._messages.put(self._EOF)

    def send(self, method: str, params: dict) -> int:
        self._request_id += 1
        try:
            self.process.stdin.write(
                json.dumps(
                    {"id": self._request_id, "method": method, "params": params},
                    ensure_ascii=False,
                )
                + "\n"
            )
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            raise RuntimeError("Codex app-server stopped") from error
        return self._request_id

    def next_message(self, timeout: float | None = None) -> dict:
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as error:
            raise TimeoutError from error
        if message is self._EOF:
            raise RuntimeError("Codex app-server stopped")
        if isinstance(message, BaseException):
            if isinstance(message, RuntimeError):
                raise message
            raise RuntimeError("Codex app-server reader failed") from message
        return message

    @staticmethod
    def _legacy_item(item: dict) -> dict:
        item_type = item.get("type")
        mapping = {
            "collabAgentToolCall": "collab_tool_call",
            "collabToolCall": "collab_tool_call",
            "subAgentActivity": "subagent_activity",
            "webSearch": "web_search",
            "mcpToolCall": "mcp_tool_call",
            "fileChange": "file_change",
            "commandExecution": "command_execution",
        }
        legacy = dict(item)
        legacy["type"] = mapping.get(item_type, item_type)
        legacy["exit_code"] = item.get("exitCode")
        native_receivers = item.get("receiverThreadIds")
        if isinstance(native_receivers, list):
            legacy["receiver_thread_ids"] = [
                identifier
                for identifier in native_receivers
                if isinstance(identifier, str) and identifier
            ]
        else:
            legacy["receiver_thread_ids"] = [
                identifier
                for identifier in (
                    item.get("receiverThreadId"),
                    item.get("newThreadId"),
                    item.get("agentThreadId"),
                )
                if isinstance(identifier, str) and identifier
            ]
        native_status = item.get("status")
        legacy["status"] = {"inProgress": "in_progress"}.get(
            native_status, native_status
        )
        legacy["tool"] = {
            "spawnAgent": "spawn_agent",
            "sendInput": "send_input",
            "resumeAgent": "resume_agent",
            "closeAgent": "close_agent",
        }.get(item.get("tool"), item.get("tool"))
        native_states = item.get("agentsStates")
        if isinstance(native_states, dict):
            legacy["agents_states"] = {
                identifier: {
                    **state,
                    "status": {
                        "pendingInit": "pending_init",
                        "notFound": "not_found",
                    }.get(state.get("status"), state.get("status")),
                }
                for identifier, state in native_states.items()
                if isinstance(identifier, str) and isinstance(state, dict)
            }
        elif isinstance(item.get("agentStatus"), str) and legacy["receiver_thread_ids"]:
            legacy["agents_states"] = {
                legacy["receiver_thread_ids"][0]: {
                    "status": {"inProgress": "running"}.get(
                        item["agentStatus"], item["agentStatus"]
                    )
                }
            }
        return legacy

    def observe_notification(self, message: dict) -> tuple[str | None, dict | None]:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise RuntimeError("Codex app-server returned a malformed notification")
        if "id" in message:
            raise RuntimeError(f"unsupported app-server request: {method}")
        if method == "thread/started":
            thread = params.get("thread")
            if isinstance(thread, dict) and isinstance(thread.get("id"), str):
                self.observer.feed(
                    json.dumps({"type": "thread.started", "thread_id": thread["id"]})
                )
        if method in {"item/started", "item/completed"}:
            item = params.get("item")
            if not isinstance(item, dict):
                raise RuntimeError("Codex app-server item notification is malformed")
            if (
                method == "item/completed"
                and item.get("type") == "agentMessage"
                and params.get("threadId") == self._receipt_thread_id
                and params.get("turnId") == self._receipt_turn_id
            ):
                text = item.get("text")
                if isinstance(text, str):
                    self._last_agent_message = text
            self.observer.feed(
                json.dumps(
                    {
                        "type": (
                            "item.started"
                            if method == "item/started"
                            else "item.completed"
                        ),
                        "item": self._legacy_item(item),
                    }
                )
            )
        if method == "turn/completed":
            turn = params.get("turn")
            if not isinstance(turn, dict):
                raise RuntimeError("Codex app-server turn completion is malformed")
            thread_id = params.get("threadId")
            if (
                turn.get("id") == self._receipt_turn_id
                and (
                    thread_id is None
                    or thread_id == self._receipt_thread_id
                )
            ):
                return method, turn
        return method, None

    def request(self, method: str, params: dict) -> dict:
        request_id = self.send(method, params)
        deadline = time.monotonic() + APP_SERVER_REQUEST_TIMEOUT_SECONDS
        while True:
            try:
                message = self.next_message(max(0.0, deadline - time.monotonic()))
            except TimeoutError as error:
                raise RuntimeError(
                    f"Codex app-server timed out during {method}"
                ) from error
            if "method" in message:
                self.observe_notification(message)
                continue
            if message.get("id") != request_id:
                raise RuntimeError("Codex app-server response correlation failed")
            if "error" in message:
                raise RuntimeError(
                    f"Codex app-server rejected {method}: {message['error']}"
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"Codex app-server returned no result for {method}")
            return result

    @property
    def last_agent_message(self) -> str | None:
        return self._last_agent_message

    def _patch_branch(self, thread_id: str) -> None:
        self.request(
            "thread/metadata/update",
            {"threadId": thread_id, "gitInfo": {"branch": self._issue_branch}},
        )

    def _patch_descendants(self, thread_id: str) -> None:
        cursor = None
        seen_cursors: set[str] = set()
        while True:
            params = {"ancestorThreadId": thread_id, "limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            page = self.request("thread/list", params)
            threads = page.get("data")
            if not isinstance(threads, list):
                raise RuntimeError("Codex thread/list omitted descendant data")
            for thread in threads:
                descendant_id = thread.get("id") if isinstance(thread, dict) else None
                if not isinstance(descendant_id, str) or not descendant_id:
                    raise RuntimeError("Codex thread/list returned an invalid descendant")
                self._patch_branch(descendant_id)
            cursor = page.get("nextCursor")
            if cursor is None:
                return
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                raise RuntimeError("Codex thread/list returned an invalid cursor")
            seen_cursors.add(cursor)

    def close(
        self,
        *,
        disposition: str | None = None,
        failed: bool | None = None,
    ) -> None:
        """Finalize native persistence, then boundedly reap the private server."""
        disposition = disposition or getattr(self, "_disposition", None)
        if disposition is None and failed is not None:  # legacy test/caller bridge
            disposition = "failed" if failed else "ephemeral"
        if disposition not in {"terminal", "resumable", "ephemeral", "failed"}:
            raise RuntimeError("app-server close requires an explicit disposition")
        thread_id = getattr(self, "_receipt_thread_id", None)
        turn_id = getattr(self, "_receipt_turn_id", None)
        error = None
        try:
            if thread_id:
                if getattr(self, "_issue_branch", None):
                    self._patch_descendants(thread_id)
                if disposition == "terminal":
                    self.request("thread/archive", {"threadId": thread_id})
                else:
                    if disposition == "failed" and turn_id:
                        self.request(
                            "turn/interrupt",
                            {"threadId": thread_id, "turnId": turn_id},
                        )
                    self.request("thread/unsubscribe", {"threadId": thread_id})
        except BaseException as caught:
            error = caught
        finally:
            terminate_and_reap(self.process)
        if error is not None:
            raise error
