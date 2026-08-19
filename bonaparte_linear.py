"""Read Linear intake through the shared native app-server transport."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from bonaparte_native import AppServerPhaseDriver
from bonaparte_progress import EventObserver

LINEAR_ARTIFACT_MAX_BYTES = 64 * 1024
CREATE_CORRELATION_PREFIX = "Bonaparte phase token: "


def create_correlation_marker(token: str) -> str:
    canonical = str(uuid.UUID(token))
    if canonical != token:
        raise ValueError("create correlation token must be canonical")
    return f"{CREATE_CORRELATION_PREFIX}{canonical}"


def _tool(
    driver: AppServerPhaseDriver,
    thread_id: str,
    name: str,
    arguments: dict,
) -> dict:
    result = driver.request(
        "mcpServer/tool/call",
        {
            "threadId": thread_id,
            "server": "linear",
            "tool": name,
            "arguments": arguments,
        },
    )
    if result.get("isError"):
        detail = next(
            (
                block.get("text", "")
                for block in result.get("content", [])
                if block.get("type") == "text"
            ),
            "",
        )
        raise RuntimeError(detail or f"Linear {name} failed")
    content = result.get("structuredContent")
    for block in result.get("content", []):
        if isinstance(content, dict) or block.get("type") != "text":
            continue
        try:
            content = json.loads(block["text"])
        except (KeyError, json.JSONDecodeError):
            pass
    if not isinstance(content, dict):
        raise RuntimeError(f"Linear {name} returned no JSON object")
    return content


def call_linear(repository: Path, issue_identifier: str) -> tuple[dict, list[dict]]:
    driver = AppServerPhaseDriver(repository, EventObserver())
    try:
        driver.request(
            "initialize", {"clientInfo": {"name": "bonaparte", "version": "1"}}
        )
        driver.process.stdin.write('{"method":"initialized","params":{}}\n')
        driver.process.stdin.flush()
        started = driver.request(
            "thread/start", {"cwd": str(repository), "ephemeral": True}
        )
        thread_id = started["thread"]["id"]
        issue = _tool(driver, thread_id, "get_issue", {"id": issue_identifier})
        issue["identifier"] = issue.get("identifier") or issue_identifier
        comments = []
        cursor = None
        seen_cursors = set()
        while True:
            arguments = {
                "issueId": issue_identifier,
                "limit": 250,
                "orderBy": "createdAt",
            }
            if cursor:
                arguments["cursor"] = cursor
            page = _tool(driver, thread_id, "list_comments", arguments)
            page_comments = page.get("comments")
            if not isinstance(page_comments, list):
                raise RuntimeError("Linear comments response omitted its comments")
            comments.extend(page_comments)
            has_next_page = page.get("hasNextPage")
            if not isinstance(has_next_page, bool):
                raise RuntimeError(
                    "Linear comments response omitted its pagination state"
                )
            if not has_next_page:
                break
            cursor = page.get("cursor")
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                raise RuntimeError("Linear comments response has an invalid cursor")
            seen_cursors.add(cursor)
        return issue, comments
    finally:
        driver.close(failed=False)


def find_linear_issue_by_correlation(repository: Path, token: str) -> dict | None:
    """Read back exactly one create result carrying the durable phase marker."""
    marker = create_correlation_marker(token)
    driver = AppServerPhaseDriver(repository, EventObserver())
    try:
        driver.request(
            "initialize", {"clientInfo": {"name": "bonaparte", "version": "1"}}
        )
        driver.process.stdin.write('{"method":"initialized","params":{}}\n')
        driver.process.stdin.flush()
        started = driver.request(
            "thread/start", {"cwd": str(repository), "ephemeral": True}
        )
        thread_id = started["thread"]["id"]
        page = _tool(
            driver,
            thread_id,
            "list_issues",
            {"query": token, "limit": 250, "orderBy": "createdAt"},
        )
        issues = page.get("issues")
        if not isinstance(issues, list) or page.get("hasNextPage") is not False:
            raise RuntimeError("Linear create correlation response is incomplete")
        matches = []
        for candidate in issues:
            if not isinstance(candidate, dict):
                continue
            description = candidate.get("description")
            identifier = candidate.get("identifier") or candidate.get("id")
            if (
                isinstance(description, str)
                and marker in description.splitlines()
                and isinstance(identifier, str)
                and identifier
            ):
                matches.append(identifier)
        if len(matches) > 1:
            raise RuntimeError("Linear create correlation is ambiguous")
        if not matches:
            return None
        issue = _tool(driver, thread_id, "get_issue", {"id": matches[0]})
        description = issue.get("description")
        if not isinstance(description, str) or marker not in description.splitlines():
            raise RuntimeError("Linear create correlation readback mismatched")
        issue["identifier"] = issue.get("identifier") or matches[0]
        return issue
    finally:
        driver.close(failed=False)


def read_linear_phase_artifact(
    repository: Path,
    issue_identifier: str,
    header: str,
    comment_id: str | None = None,
) -> dict | None:
    """Read one exact, bounded, top-level Linear phase artifact without writes."""

    if not isinstance(header, str) or not header or "\n" in header or "\0" in header:
        raise ValueError("Linear artifact header must be one non-empty line")
    if comment_id is not None and (
        not isinstance(comment_id, str) or not comment_id or "\0" in comment_id
    ):
        raise ValueError("Linear artifact comment ID must be non-empty text")

    _issue, comments = call_linear(repository, issue_identifier)
    matches = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        if comment.get("parentId") is not None or comment.get("quotedText") is not None:
            continue
        identifier = comment.get("id")
        body = comment.get("body")
        created_at = comment.get("createdAt")
        if not all(isinstance(value, str) for value in (identifier, body, created_at)):
            continue
        if comment_id is not None and identifier != comment_id:
            continue
        if body.split("\n", 1)[0] != header:
            continue
        if len(body.encode("utf-8")) > LINEAR_ARTIFACT_MAX_BYTES:
            raise RuntimeError("Linear phase artifact exceeds the read limit")
        matches.append({"id": identifier, "body": body, "createdAt": created_at})

    if comment_id is not None:
        if len(matches) > 1:
            raise RuntimeError("Linear returned a duplicate exact comment ID")
        return matches[0] if matches else None
    if not matches:
        return None
    return max(matches, key=lambda value: (value["createdAt"], value["id"]))
