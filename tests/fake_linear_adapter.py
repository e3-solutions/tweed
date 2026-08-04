#!/usr/bin/env python3
"""Hermetic file-backed implementation of the Tweed Linear v2 protocol."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path


PROTOCOL = "dev.tweed.linear.v2"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_digest(issue: dict, excluding: str | None = None) -> str:
    stable = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description") or "",
        "comments": [
            {
                "id": item["id"],
                "body": item["body"],
                "archivedAt": item.get("archivedAt"),
            }
            for item in issue.get("comments", [])
            if item["id"] != excluding
        ],
    }
    return digest(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def snapshot_digest(issue: dict) -> str:
    stable = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description") or "",
        "updatedAt": issue.get("updatedAt"),
        "comments": [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "body",
                    "createdAt",
                    "updatedAt",
                    "editedAt",
                    "archivedAt",
                )
            }
            for item in issue.get("comments", [])
        ],
    }
    return digest(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def finalize(issue: dict) -> dict:
    issue["content_digest"] = content_digest(issue)
    issue["snapshot_digest"] = snapshot_digest(issue)
    return issue


def envelope(status: str, **values: object) -> dict:
    return {"protocol": PROTOCOL, "status": status, **values}


def main() -> int:
    request = json.load(sys.stdin)
    if request.get("protocol") != PROTOCOL:
        raise RuntimeError("unsupported protocol")
    state_path = Path(os.environ["FAKE_LINEAR_STATE"])
    with state_path.open("r+", encoding="utf-8") as state_file:
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state = json.loads(state_file.read())
        operation = request["operation"]
        trace = Path(os.environ.get("FAKE_LINEAR_TRACE", str(state_path) + ".trace"))
        with trace.open("a", encoding="utf-8") as file:
            file.write(operation + "\n")
        issue = state["issues"].get(request.get("identifier"))
        if operation == "fetch":
            response = envelope("ok", issue=issue) if issue else envelope("not-found")
        elif operation == "verify":
            unchanged = (
                issue
                and issue["snapshot_digest"] == request["expected_snapshot_digest"]
            )
            response = envelope("unchanged" if unchanged else "stale", issue=issue)
        elif operation == "create-or-recover":
            issue = next(
                (
                    item
                    for item in state["issues"].values()
                    if item["id"] == request["issue_id"]
                ),
                None,
            )
            status = "recovered"
            if issue is None:
                identifier = f"TST-{state['next']}"
                state["next"] += 1
                issue = finalize(
                    {
                        "id": request["issue_id"],
                        "identifier": identifier,
                        "url": f"https://linear.test/{identifier}",
                        "title": request["title"],
                        "description": request["description"],
                        "updatedAt": "1",
                        "comments": [],
                    }
                )
                state["issues"][identifier] = issue
                state["writes"] += 1
                status = "created"
            response = envelope(status, issue=issue)
        elif operation == "append-or-recover":
            existing = next(
                (
                    item
                    for item in issue["comments"]
                    if item["id"] == request["comment_id"]
                ),
                None,
            )
            if existing:
                status = (
                    "recovered" if existing["body"] == request["body"] else "blocked"
                )
                response = envelope(status, issue=issue, reason="conflicting comment")
            elif (
                issue["snapshot_digest"] != request["expected_snapshot_digest"]
                or issue["content_digest"] != request["expected_content_digest"]
            ):
                response = envelope("blocked", issue=issue, reason="stale snapshot")
            else:
                issue["comments"].append(
                    {
                        "id": request["comment_id"],
                        "body": request["body"],
                        "createdAt": "2",
                        "updatedAt": "2",
                        "editedAt": None,
                        "archivedAt": None,
                        "parent": None,
                    }
                )
                issue["updatedAt"] = "2"
                finalize(issue)
                state["writes"] += 1
                response = envelope("appended", issue=issue)
        else:
            response = envelope("blocked", reason="unsupported operation")
        state_file.seek(0)
        json.dump(state, state_file, sort_keys=True)
        state_file.truncate()
        state_file.flush()
        os.fsync(state_file.fileno())
    json.dump(response, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
