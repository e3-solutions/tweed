#!/usr/bin/env python3
"""Bounded, model-free Linear transport for Tweed's append-only journal."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import tweed_linear_oauth as oauth

PROTOCOL = "dev.tweed.linear.v2"
API_HOST = "api.linear.app"
API_PATH = "/graphql"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 524_288
MAX_COMMENT_BODY_BYTES = 262_144
MAX_COMMENTS = 2_000
MAX_PAGES = 40
PAGE_SIZE = 50
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class AdapterError(RuntimeError):
    """A deliberately redacted adapter failure."""


class AmbiguousMutation(AdapterError):
    """The connection failed after a mutation may have reached Linear."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _uuid4(value: object, label: str) -> str:
    if not isinstance(value, str) or not UUID4_RE.fullmatch(value):
        raise AdapterError(f"{label} must be a caller-supplied UUID-v4-shaped ID")
    return value.lower()


def _text(value: object, label: str, maximum: int = MAX_COMMENT_BODY_BYTES) -> str:
    if not isinstance(value, str) or not value:
        raise AdapterError(f"{label} must be non-empty text")
    if len(value.encode("utf-8")) > maximum:
        raise AdapterError(f"{label} exceeds the byte limit")
    return value


@dataclass
class LinearClient:
    api_key: str
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection
    unauthorized_callback: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise AdapterError("LINEAR_API_KEY is not configured")
        if "\r" in self.api_key or "\n" in self.api_key:
            raise AdapterError("LINEAR_API_KEY is invalid")

    def graphql(
        self, query: str, variables: dict[str, Any], *, mutation: bool = False
    ) -> dict[str, Any]:
        encoded = json.dumps(
            {"query": query, "variables": variables},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise AdapterError("Linear request exceeds the byte limit")
        connection = None
        try:
            connection = self.connection_factory(API_HOST, timeout=TIMEOUT_SECONDS)
            connection.request(
                "POST",
                API_PATH,
                body=encoded,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                    "User-Agent": "tweed-linear-adapter/2",
                },
            )
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length) > MAX_RESPONSE_BYTES:
                        raise AdapterError("Linear response exceeds the byte limit")
                except ValueError as error:
                    raise AdapterError("Linear returned an invalid response") from error
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        except AdapterError:
            raise
        except (TimeoutError, OSError, http.client.HTTPException) as error:
            failure = AmbiguousMutation if mutation else AdapterError
            raise failure("Linear transport failed") from error
        finally:
            if connection is not None:
                try:
                    connection.close()
                except (OSError, http.client.HTTPException):
                    pass
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AdapterError("Linear response exceeds the byte limit")
        if response.status == 401 and self.unauthorized_callback is not None:
            try:
                self.unauthorized_callback()
            except oauth.OAuthError as error:
                raise AdapterError("Linear OAuth credential invalidation failed") from error
        if response.status == 429:
            raise AdapterError("Linear rate limit reached; retry later")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            if response.status != 200:
                raise AdapterError(
                    f"Linear HTTP request failed with status {response.status}"
                ) from error
            raise AdapterError("Linear returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise AdapterError("Linear returned an invalid response")
        errors = payload.get("errors")
        if isinstance(errors, list) and any(
                isinstance(item, dict)
                and isinstance(item.get("extensions"), dict)
                and item["extensions"].get("code") == "RATELIMITED"
                for item in errors
            ):
            raise AdapterError("Linear rate limit reached; retry later")
        if response.status != 200:
            raise AdapterError(f"Linear HTTP request failed with status {response.status}")
        if errors:
            raise AdapterError("Linear GraphQL request failed")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AdapterError("Linear returned no GraphQL data")
        return data


ISSUE_QUERY = """
query TweedIssue($id: String!, $first: Int!, $after: String) {
  issue(id: $id) {
    id identifier url title description updatedAt
    team { id key }
    project { id name }
    comments(first: $first, after: $after, includeArchived: true) {
      nodes { id body createdAt updatedAt editedAt archivedAt parent { id } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

ISSUE_BY_ID_QUERY = """
query TweedIssueById($id: ID!) {
  issues(first: 2, filter: { id: { eq: $id } }, includeArchived: true) {
    nodes { id identifier url title description team { id key } project { id name } }
  }
}
"""

COMMENT_BY_ID_QUERY = """
query TweedCommentById($id: ID!) {
  comments(first: 2, filter: { id: { eq: $id } }, includeArchived: true) {
    nodes { id body createdAt updatedAt editedAt archivedAt parent { id } issue { id } }
  }
}
"""

CREATE_CONTEXT_QUERY = """
query TweedCreateContext($project: String!) {
  projects(first: 2, filter: { name: { eq: $project } }, includeArchived: false) {
    nodes {
      id name
      teams(first: 2, includeArchived: false) { nodes { id key } }
    }
  }
}
"""

ISSUE_CREATE = """
mutation TweedIssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) { success issue { id } }
}
"""

COMMENT_CREATE = """
mutation TweedCommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) { success comment { id body } }
}
"""


def _fetch_issue_full(client: LinearClient, reference: str) -> dict[str, Any]:
    after: str | None = None
    issue: dict[str, Any] | None = None
    comments: list[dict[str, Any]] = []
    comment_bytes = 0
    for _page in range(MAX_PAGES):
        data = client.graphql(
            ISSUE_QUERY, {"id": reference, "first": PAGE_SIZE, "after": after}
        )
        current = data.get("issue")
        if not isinstance(current, dict):
            raise AdapterError("Linear returned an invalid issue")
        if issue is None:
            issue = current
        elif any(
            current.get(key) != issue.get(key)
            for key in (
                "id",
                "identifier",
                "url",
                "title",
                "description",
                "updatedAt",
                "team",
                "project",
            )
        ):
            raise AdapterError("Linear issue changed during pagination")
        connection = current.get("comments")
        if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list):
            raise AdapterError("Linear returned invalid comments")
        for comment in connection["nodes"]:
            if not isinstance(comment, dict) or not isinstance(comment.get("body"), str):
                raise AdapterError("Linear returned an invalid comment")
            if len(comment["body"].encode("utf-8")) > MAX_COMMENT_BODY_BYTES:
                raise AdapterError("Linear comment exceeds the byte limit")
            # Replies are human conversation, not top-level journal records.
            if comment.get("parent") is not None:
                continue
            comment_bytes += len(comment["body"].encode("utf-8"))
            if comment_bytes > MAX_RESPONSE_BYTES // 2:
                raise AdapterError("Linear issue comment content exceeds the byte limit")
            comments.append(comment)
            if len(comments) > MAX_COMMENTS:
                raise AdapterError("Linear issue exceeds the comment limit")
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise AdapterError("Linear returned invalid pagination")
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor or cursor == after:
            raise AdapterError("Linear returned invalid pagination")
        after = cursor
    else:
        raise AdapterError("Linear issue exceeds the page limit")
    assert issue is not None
    normalized = {key: value for key, value in issue.items() if key != "comments"}
    normalized["description"] = normalized.get("description") or ""
    comments.sort(key=lambda value: (str(value.get("createdAt") or ""), value.get("id") or ""))
    normalized["comments"] = comments
    normalized["content_digest"] = _content_digest(normalized)
    normalized["snapshot_digest"] = _snapshot_digest(normalized)
    if len(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_RESPONSE_BYTES - 1024:
        raise AdapterError("Linear issue snapshot exceeds the byte limit")
    return normalized


def fetch_issue(client: LinearClient, identifier: str) -> dict[str, Any] | None:
    """Resolve through a nullable collection before using Linear's non-null issue field."""
    identifier = _text(identifier, "identifier", 256)
    identity = _fetch_issue_by_id(client, identifier)
    return _fetch_issue_full(client, identity["id"]) if identity is not None else None


def _snapshot_digest(issue: dict[str, Any]) -> str:
    stable = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description") or "",
        "updatedAt": issue.get("updatedAt"),
        "comments": [
            {
                key: comment.get(key)
                for key in (
                    "id",
                    "body",
                    "createdAt",
                    "updatedAt",
                    "editedAt",
                    "archivedAt",
                )
            }
            for comment in issue.get("comments", [])
        ],
    }
    return _sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _content_digest(issue: dict[str, Any], *, excluding_comment: str | None = None) -> str:
    """Digest exact human content while excluding server-controlled timestamps."""
    stable = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description") or "",
        "comments": [
            {
                "id": item.get("id"),
                "body": item.get("body"),
                "archivedAt": item.get("archivedAt"),
            }
            for item in issue.get("comments", [])
            if item.get("id") != excluding_comment
        ],
    }
    return _sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _fetch_comment(client: LinearClient, comment_id: str) -> dict[str, Any] | None:
    data = client.graphql(COMMENT_BY_ID_QUERY, {"id": comment_id})
    nodes = ((data.get("comments") or {}).get("nodes") or [])
    if not isinstance(nodes, list) or len(nodes) > 1 or any(
        not isinstance(item, dict) for item in nodes
    ):
        raise AdapterError("Linear returned invalid comment identity results")
    return nodes[0] if nodes else None


def _fetch_issue_by_id(client: LinearClient, issue_id: str) -> dict[str, Any] | None:
    data = client.graphql(ISSUE_BY_ID_QUERY, {"id": issue_id})
    nodes = ((data.get("issues") or {}).get("nodes") or [])
    if not isinstance(nodes, list) or len(nodes) > 1 or any(
        not isinstance(item, dict) for item in nodes
    ):
        raise AdapterError("Linear returned invalid issue identity results")
    return nodes[0] if nodes else None


def _same_issue(candidate: dict[str, Any], request: dict[str, Any]) -> bool:
    project = candidate.get("project") or {}
    team = candidate.get("team") or {}
    try:
        import tweed_journal

        candidate_genesis = tweed_journal.parse_genesis(
            candidate.get("description") or ""
        ).digest
        desired_genesis = tweed_journal.parse_genesis(request["description"]).digest
    except (ImportError, RuntimeError, TypeError):
        return False
    return (
        candidate.get("id") == request["issue_id"]
        and candidate.get("title") == request["title"]
        and candidate_genesis == desired_genesis
        and project.get("name") == request["project"]
        and team.get("id") == request["team_id"]
    )


def create_or_recover(client: LinearClient, request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    issue_id = _uuid4(request.get("issue_id"), "issue_id")
    title = _text(request.get("title"), "title", 1024)
    description = _text(request.get("description"), "description")
    project_name = _text(request.get("project"), "project", 1024)
    checked = {
        **request,
        "issue_id": issue_id,
        "title": title,
        "description": description,
        "project": project_name,
    }
    existing_identity = _fetch_issue_by_id(client, issue_id)
    existing = (
        _fetch_issue_full(client, existing_identity["id"])
        if existing_identity is not None
        else None
    )
    context = client.graphql(CREATE_CONTEXT_QUERY, {"project": project_name})
    projects = ((context.get("projects") or {}).get("nodes") or [])
    if len(projects) != 1 or projects[0].get("name") != project_name:
        raise AdapterError("configured Linear project is not uniquely resolvable")
    teams = ((projects[0].get("teams") or {}).get("nodes") or [])
    if len(teams) != 1:
        raise AdapterError("configured Linear project must belong to exactly one active team")
    checked["team_id"] = teams[0].get("id")
    if not checked["team_id"]:
        raise AdapterError("configured Linear project returned an invalid team")
    if existing is not None:
        if not _same_issue(existing, checked):
            raise AdapterError("deterministic issue ID already has conflicting content")
        return "recovered", existing
    mutation_error: AdapterError | None = None
    try:
        data = client.graphql(
            ISSUE_CREATE,
            {
                "input": {
                    "id": issue_id,
                    "teamId": teams[0]["id"],
                    "projectId": projects[0]["id"],
                    "title": title,
                    "description": description,
                }
            },
            mutation=True,
        )
        result = data.get("issueCreate") or {}
        if result.get("success") is not True or (result.get("issue") or {}).get("id") != issue_id:
            mutation_error = AdapterError("Linear did not confirm issue creation")
    except AdapterError as error:
        mutation_error = error
    recovered_identity = _fetch_issue_by_id(client, issue_id)
    recovered = (
        _fetch_issue_full(client, recovered_identity["id"])
        if recovered_identity is not None
        else None
    )
    if recovered is not None and _same_issue(recovered, checked):
        return ("recovered" if mutation_error else "created"), recovered
    if recovered is not None:
        raise AdapterError("deterministic issue ID recovered conflicting content")
    raise mutation_error or AdapterError("Linear issue creation could not be recovered")


def _journal_head(issue: dict[str, Any], request: dict[str, Any]) -> str:
    """Validate the whole canonical journal and return its exact head digest."""
    try:
        import tweed_journal  # type: ignore
    except ImportError as error:
        raise AdapterError("canonical Tweed journal validator is unavailable") from error
    try:
        for item in issue.get("comments", []):
            body = item.get("body") or ""
            if tweed_journal.RECORD_TOKEN in body and (
                item.get("archivedAt") is not None
                or item.get("editedAt") is not None
            ):
                raise AdapterError("Tweed journal comments must be unedited and unarchived")
        snapshot = tweed_journal.validate_snapshot(
            description=issue.get("description") or "",
            comments=[item["body"] for item in issue.get("comments", [])],
            issue_identifier=issue.get("identifier"),
            expected_repository=_text(
                request.get("repository"), "repository", 4096
            ),
            expected_base_commit=request.get("base_commit"),
            expected_branch=request.get("branch"),
            expected_commits=request.get("commits"),
        )
    except (RuntimeError, TypeError, ValueError) as error:
        raise AdapterError(f"invalid Linear journal: {error}") from error
    return snapshot.records[-1].digest if snapshot.records else snapshot.genesis.digest


def _journal_record_digest(body: object) -> str | None:
    if not isinstance(body, str):
        return None
    try:
        import tweed_journal

        record = tweed_journal.parse_comment(body)
    except (ImportError, RuntimeError, TypeError, ValueError):
        return None
    return record.digest if record is not None else None


def _validate_precondition(issue: dict[str, Any], request: dict[str, Any]) -> str:
    expected = _text(request.get("expected_snapshot_digest"), "expected_snapshot_digest", 128)
    if issue.get("snapshot_digest") != expected:
        raise AdapterError("stale Linear snapshot")
    expected_content = _text(
        request.get("expected_content_digest"), "expected_content_digest", 128
    )
    if issue.get("content_digest") != expected_content:
        raise AdapterError("stale Linear content")
    head = _journal_head(issue, request)
    if head != request.get("expected_head_digest"):
        raise AdapterError("stale Linear journal head")
    return head


def append_or_recover(client: LinearClient, request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    identifier = _text(request.get("identifier"), "identifier", 256)
    comment_id = _uuid4(request.get("comment_id"), "comment_id")
    body = _text(request.get("body"), "body")
    issue = fetch_issue(client, identifier)
    if issue is None:
        raise AdapterError("Linear issue was not found")
    direct = _fetch_comment(client, comment_id)
    if direct is not None:
        if (
            _journal_record_digest(direct.get("body"))
            != request.get("desired_head_digest")
            or (direct.get("issue") or {}).get("id") != issue.get("id")
        ):
            raise AdapterError("deterministic comment ID already has conflicting content")
        if not any(
            item.get("id") == comment_id
            and _journal_record_digest(item.get("body"))
            == request.get("desired_head_digest")
            for item in issue["comments"]
        ):
            raise AdapterError("deterministic comment is absent from the issue snapshot")
        if _content_digest(issue, excluding_comment=comment_id) != request.get(
            "expected_content_digest"
        ):
            raise AdapterError("Linear content diverged while recovering the append")
        if _journal_head(issue, request) != request.get("desired_head_digest"):
            raise AdapterError("recovered comment does not produce the desired journal head")
        return "recovered", issue
    _validate_precondition(issue, request)
    mutation_error: AdapterError | None = None
    try:
        data = client.graphql(
            COMMENT_CREATE,
            {"input": {"id": comment_id, "issueId": issue["id"], "body": body}},
            mutation=True,
        )
        result = data.get("commentCreate") or {}
        comment = result.get("comment") or {}
        if (
            result.get("success") is not True
            or comment.get("id") != comment_id
            or _journal_record_digest(comment.get("body"))
            != request.get("desired_head_digest")
        ):
            mutation_error = AdapterError("Linear did not confirm comment creation")
    except AdapterError as error:
        mutation_error = error
    direct = _fetch_comment(client, comment_id)
    if direct is None:
        raise mutation_error or AdapterError("Linear comment creation could not be recovered")
    if (
        _journal_record_digest(direct.get("body"))
        != request.get("desired_head_digest")
        or (direct.get("issue") or {}).get("id") != issue.get("id")
    ):
        raise AdapterError("deterministic comment ID recovered conflicting content")
    final_issue = fetch_issue(client, identifier)
    if final_issue is None or not any(
        item.get("id") == comment_id
        and _journal_record_digest(item.get("body"))
        == request.get("desired_head_digest")
        for item in final_issue["comments"]
    ):
        raise AdapterError("Linear comment is absent from the post-write snapshot")
    if _content_digest(final_issue, excluding_comment=comment_id) != request.get(
        "expected_content_digest"
    ):
        raise AdapterError("Linear content diverged while appending the journal record")
    if _journal_head(final_issue, request) != request.get("desired_head_digest"):
        raise AdapterError("appended comment does not produce the desired journal head")
    return ("recovered" if mutation_error else "appended"), final_issue


def handle(request: dict[str, Any], client: LinearClient) -> dict[str, Any]:
    if request.get("protocol") != PROTOCOL:
        raise AdapterError("unsupported adapter protocol")
    operation = request.get("operation")
    if operation == "fetch":
        issue = fetch_issue(client, request.get("identifier"))
        return {"protocol": PROTOCOL, "status": "ok" if issue else "not-found", "issue": issue}
    if operation == "verify":
        issue = fetch_issue(client, request.get("identifier"))
        unchanged = issue is not None and issue["snapshot_digest"] == request.get("expected_snapshot_digest")
        return {"protocol": PROTOCOL, "status": "unchanged" if unchanged else "stale", "issue": issue}
    if operation == "create-or-recover":
        status, issue = create_or_recover(client, request)
        return {"protocol": PROTOCOL, "status": status, "issue": issue}
    if operation == "append-or-recover":
        status, issue = append_or_recover(client, request)
        return {"protocol": PROTOCOL, "status": status, "issue": issue}
    raise AdapterError("unsupported adapter operation")


def client_from_environment() -> LinearClient:
    mode = os.environ.get("TWEED_LINEAR_AUTH", "oauth").strip().lower()
    if mode == "oauth":
        token = oauth.access_token()
        return LinearClient(
            "Bearer " + token,
            unauthorized_callback=lambda: oauth.invalidate_access_token(token),
        )
    if mode == "api-key":
        authorization = os.environ.get("LINEAR_API_KEY", "")
        if not authorization:
            raise AdapterError("explicit api-key mode requires LINEAR_API_KEY")
        return LinearClient(authorization)
    raise AdapterError("TWEED_LINEAR_AUTH must be oauth or api-key")


def authorization_from_environment() -> str:
    """Compatibility/testing accessor; production uses client_from_environment."""
    return client_from_environment().api_key


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise AdapterError("adapter request exceeds the byte limit")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict):
            raise AdapterError("adapter request must be an object")
        response = handle(request, client_from_environment())
    except (AdapterError, oauth.OAuthError, UnicodeDecodeError, json.JSONDecodeError) as error:
        response = {"protocol": PROTOCOL, "status": "blocked", "reason": str(error)}
    except Exception:  # noqa: BLE001 - trust-boundary fail-closed; never emit internals.
        response = {
            "protocol": PROTOCOL,
            "status": "blocked",
            "reason": "internal Linear adapter failure",
        }
    json.dump(response, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
