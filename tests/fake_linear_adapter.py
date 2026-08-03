#!/usr/bin/env python3
"""Hermetic atomic implementation of the dev.tweed.linear.v1 test protocol."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path


PROTOCOL = "dev.tweed.linear.v1"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    request = json.load(sys.stdin)
    if request.get("protocol") != PROTOCOL:
        raise RuntimeError("unsupported protocol")
    state_path = Path(os.environ["FAKE_LINEAR_STATE"])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.touch(exist_ok=True)
    with state_path.open("r+", encoding="utf-8") as state_file:
        fcntl.flock(state_file, fcntl.LOCK_EX)
        raw = state_file.read()
        state = json.loads(raw) if raw else {"issues": {}, "next": 1, "writes": 0}
        operation = request["operation"]
        trace = Path(os.environ.get("FAKE_LINEAR_TRACE", str(state_path) + ".trace"))
        with trace.open("a", encoding="utf-8") as file:
            file.write(operation + "\n")

        if operation == "fetch":
            issue = state["issues"].get(request["identifier"])
            response = ok(issue) if issue else blocked("not found")
        elif operation == "verify":
            issue = state["issues"].get(request["identifier"])
            unchanged = issue and matches(issue, request)
            response = envelope("unchanged" if unchanged else "stale")
        elif operation == "create-or-recover":
            marker = request["run_id"]
            issue = next(
                (item for item in state["issues"].values() if marker in item["description"]),
                None,
            )
            status = "recovered"
            if issue is None:
                identifier = f"TST-{state['next']}"
                state["next"] += 1
                issue = make_issue(identifier, request["title"], request["description"], "1")
                state["issues"][identifier] = issue
                state["writes"] += 1
                status = "created"
            response = envelope(status, issue=issue)
        elif operation == "compare-and-swap":
            issue = state["issues"].get(request["identifier"])
            if issue and issue["digest"] == request["desired_digest"]:
                response = envelope("already-applied", issue=issue)
            elif not issue or not matches(issue, request):
                response = envelope("stale", reason="precondition mismatch", issue=issue)
            else:
                revision = str(int(issue["revision"]) + 1)
                updated = make_issue(
                    issue["identifier"],
                    issue["title"],
                    request["desired_description"],
                    revision,
                )
                state["issues"][issue["identifier"]] = updated
                state["writes"] += 1
                response = envelope("applied", issue=updated)
        else:
            response = blocked("unsupported operation")

        state_file.seek(0)
        json.dump(state, state_file, sort_keys=True)
        state_file.truncate()
        state_file.flush()
        os.fsync(state_file.fileno())
    json.dump(response, sys.stdout, ensure_ascii=False)
    return 0


def matches(issue: dict, request: dict) -> bool:
    return (
        issue["revision"] == request["expected_revision"]
        and issue["digest"] == request["expected_digest"]
        and (
            "expected_description" not in request
            or issue["description"] == request["expected_description"]
        )
    )


def make_issue(identifier: str, title: str, description: str, revision: str) -> dict:
    return {
        "identifier": identifier,
        "url": f"https://linear.test/{identifier}",
        "title": title,
        "description": description,
        "revision": revision,
        "digest": digest(description),
    }


def envelope(status: str, **values: object) -> dict:
    return {"protocol": PROTOCOL, "status": status, **values}


def ok(issue: dict | None) -> dict:
    return envelope("ok", issue=issue)


def blocked(reason: str) -> dict:
    return envelope("blocked", reason=reason)


if __name__ == "__main__":
    raise SystemExit(main())
