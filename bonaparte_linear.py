"""Read Linear intake through the shared native app-server transport."""

from __future__ import annotations

import json
from pathlib import Path

from bonaparte_native import AppServerPhaseDriver
from bonaparte_progress import EventObserver


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
