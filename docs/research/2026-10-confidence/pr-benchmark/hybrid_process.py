"""Process-group cleanup for the new hybrid cohort only.

Install into explicitly supplied imported adapter namespaces; never mutate the
shared subprocess module or the frozen original runner file. Thread-local guards
own only new-session children launched in their own provider invocation thread.

This stops cooperative and SIGTERM-ignoring members of the original process
group. A descendant that calls setsid() can escape that group. OS filesystem and
network confinement still apply, but this is not full descendant containment.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


_REAL_SUBPROCESS = subprocess
_LOCAL = threading.local()
GRACE_SECONDS = 0.05


def cleanup_group(process):
    """Kill the owned original group even after its leader has exited."""
    if getattr(process, "_hybrid_group_cleanup_complete", False):
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    else:
        time.sleep(GRACE_SECONDS)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    # Reap our direct child, not a host process inventory or unrelated children.
    if process.poll() is None:
        process.wait(timeout=2)
    process._hybrid_group_cleanup_complete = True


class ProcessGuard:
    def __init__(self):
        self.processes = []

    def __enter__(self):
        stack = getattr(_LOCAL, "guards", None)
        if stack is None:
            stack = _LOCAL.guards = []
        stack.append(self)
        return self

    def __exit__(self, kind, value, traceback):
        stack = _LOCAL.guards
        if not stack or stack[-1] is not self:
            raise RuntimeError("Hybrid process guard nesting changed")
        stack.pop()
        failure = None
        for process in reversed(self.processes):
            try:
                cleanup_group(process)
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure


class SubprocessProxy:
    """Module-local Popen interception, with no cross-thread ownership transfer."""
    def __init__(self, underlying):
        self.underlying = underlying

    def __getattr__(self, name):
        return getattr(self.underlying, name)

    def Popen(self, *args, **kwargs):
        process = self.underlying.Popen(*args, **kwargs)
        stack = getattr(_LOCAL, "guards", [])
        if stack and kwargs.get("start_new_session") is True:
            stack[-1].processes.append(process)
        return process


def terminate(process):
    cleanup_group(process)


def bounded_process(argv, *, cwd, env, timeout, output_prefix):
    started = time.monotonic()
    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    out = output_prefix.with_suffix(".stdout")
    err = output_prefix.with_suffix(".stderr")
    with out.open("wb") as stdout, err.open("wb") as stderr:
        process = _REAL_SUBPROCESS.Popen(argv, cwd=cwd, env=env, stdout=stdout,
            stderr=stderr, start_new_session=True)
        timeout_hit = False
        code = None
        try:
            try:
                code = process.wait(timeout=max(0.1, timeout))
            except _REAL_SUBPROCESS.TimeoutExpired:
                timeout_hit = True
        finally:
            cleanup_group(process)
        if timeout_hit:
            code = process.returncode
    # Hash only after original-group writers have been stopped.
    return {"argv": argv, "exit_code": code, "timed_out": timeout_hit,
        "wall_seconds": time.monotonic() - started, "stdout": str(out), "stderr": str(err),
        "stdout_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "stderr_sha256": hashlib.sha256(err.read_bytes()).hexdigest(),
        "process_cleanup_scope": "original_process_group",
        "detached_descendants_contained": False}


def guarded_call(function):
    if getattr(function, "_hybrid_process_guarded", False):
        return function

    @wraps(function)
    def invoke(*args, **kwargs):
        began = time.monotonic()
        with ProcessGuard() as guard:
            result = function(*args, **kwargs)
            cleanup_started = time.monotonic()
        if isinstance(result, dict):
            result["process_cleanup_scope"] = "original_process_group"
            result["detached_descendants_contained"] = False
            result["guarded_new_session_processes"] = len(guard.processes)
            result["process_cleanup_seconds"] = time.monotonic() - cleanup_started
            result["wall_seconds"] = time.monotonic() - began
            control = kwargs.get("control", args[1] if len(args) > 1 else None)
            stream = Path(control) / "stream.jsonl" if control is not None else None
            if stream is not None and stream.is_file():
                digest = hashlib.sha256(stream.read_bytes()).hexdigest()
                previous = result.get("stream_sha256")
                result["stream_changed_during_cleanup"] = previous is not None and previous != digest
                result["stream_sha256"] = digest
        return result

    invoke._hybrid_process_guarded = True
    return invoke


def install(base, backend):
    """Install once in both separately imported hybrid runner namespaces."""
    modules = {id(module): module for module in (base, backend, backend.runner)}
    for module in modules.values():
        if not isinstance(module.subprocess, SubprocessProxy):
            module.subprocess = SubprocessProxy(module.subprocess)
    for module in (base, backend.runner):
        module.bounded_process = bounded_process
        module.terminate = terminate
    base.claude_call = guarded_call(base.claude_call)
    backend.codex_call = guarded_call(backend.codex_call)
