from __future__ import annotations

import json
import unittest
from unittest import mock

import tweed_journal
import tweed_linear_adapter as adapter


class Response:
    def __init__(self, status: int, payload: object, headers: dict[str, str] | None = None):
        self.status = status
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = headers or {}

    def getheader(self, name: str):
        return self.headers.get(name)

    def read(self, amount: int) -> bytes:
        return self.raw[:amount]


class ScriptedConnections:
    def __init__(self, *steps: object):
        self.steps = list(steps)
        self.requests: list[tuple] = []
        self.hosts: list[tuple] = []

    def __call__(self, host: str, *, timeout: int):
        self.hosts.append((host, timeout))
        owner = self

        class Connection:
            def request(self, *args, **kwargs):
                owner.requests.append((args, kwargs))

            def getresponse(self):
                if not owner.steps:
                    raise AssertionError("unexpected request")
                step = owner.steps.pop(0)
                if isinstance(step, BaseException):
                    raise step
                return step

            def close(self):
                pass

        return Connection()


def graph(data: dict, status: int = 200) -> Response:
    return Response(status, {"data": data})


def issue_identity(
    issue_id: str = "issue-uuid", identifier: str = "TST-1"
) -> Response:
    return graph({"issues": {"nodes": [{"id": issue_id, "identifier": identifier}]}})


def issue_page(
    comments: list[dict] | None = None,
    *,
    has_next: bool = False,
    cursor: str | None = None,
) -> dict:
    return {
        "id": "issue-uuid",
        "identifier": "TST-1",
        "url": "https://linear.app/test/issue/TST-1/test",
        "title": "Test",
        "description": "Human request",
        "updatedAt": "2026-08-03T00:00:00.000Z",
        "team": {"id": "team-1", "key": "TST"},
        "project": {"id": "project-1", "name": "Tweed"},
        "comments": {
            "nodes": comments or [],
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        },
    }


def comment(comment_id: str, body: str) -> dict:
    return {
        "id": comment_id,
        "body": body,
        "createdAt": "2026-08-03T00:00:01.000Z",
        "updatedAt": "2026-08-03T00:00:01.000Z",
        "editedAt": None,
        "archivedAt": None,
        "parent": None,
    }


class LinearAdapterTests(unittest.TestCase):
    def client(self, script: ScriptedConnections, key: str = "secret-key"):
        return adapter.LinearClient(key, connection_factory=script)

    def test_https_endpoint_timeout_and_secret_only_in_header(self):
        script = ScriptedConnections(graph({"issue": None}))
        self.assertIsNone(adapter.fetch_issue(self.client(script), "TST-1"))
        self.assertEqual(script.hosts, [("api.linear.app", adapter.TIMEOUT_SECONDS)])
        args, kwargs = script.requests[0]
        self.assertEqual(args[:2], ("POST", "/graphql"))
        self.assertEqual(kwargs["headers"]["Authorization"], "secret-key")
        self.assertNotIn(b"secret-key", kwargs["body"])
        query = json.loads(kwargs["body"])["query"]
        self.assertIn("issues(first: 2", query)
        self.assertNotIn("issue(id:", query)

    def test_http_and_graphql_errors_are_redacted(self):
        secret = "super-secret-value"
        for response in (
            Response(401, {"error": secret}),
            Response(200, {"errors": [{"message": secret}]}),
        ):
            with self.subTest(status=response.status):
                script = ScriptedConnections(response)
                with self.assertRaises(adapter.AdapterError) as caught:
                    adapter.fetch_issue(self.client(script, secret), "TST-1")
                self.assertNotIn(secret, str(caught.exception))

    def test_oauth_401_marks_access_token_stale_without_retrying(self):
        script = ScriptedConnections(Response(401, {"error": "expired"}))
        invalidated: list[bool] = []
        client = adapter.LinearClient(
            "Bearer secret", script, unauthorized_callback=lambda: invalidated.append(True)
        )
        with self.assertRaisesRegex(adapter.AdapterError, "status 401"):
            adapter.fetch_issue(client, "TST-1")
        self.assertEqual(invalidated, [True])
        self.assertEqual(len(script.requests), 1)

    def test_http_200_graphql_errors_fail_and_rate_limit_is_safe(self):
        for response in (
            Response(429, b"credential and server details"),
            Response(
                400,
                {"errors": [{"message": "secret-key", "extensions": {"code": "RATELIMITED"}}]},
            ),
        ):
            with self.subTest(status=response.status):
                script = ScriptedConnections(response)
                with self.assertRaisesRegex(adapter.AdapterError, "rate limit") as caught:
                    adapter.fetch_issue(self.client(script), "TST-1")
                self.assertNotIn("credential", str(caught.exception))
                self.assertNotIn("secret-key", str(caught.exception))

    def test_fetch_paginates_all_comments_with_archived_enabled(self):
        one = comment("c1", "one")
        two = comment("c2", "two")
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": issue_page([one], has_next=True, cursor="next")}),
            graph({"issue": issue_page([two])}),
        )
        found = adapter.fetch_issue(self.client(script), "TST-1")
        self.assertEqual([entry["id"] for entry in found["comments"]], ["c1", "c2"])
        first = json.loads(script.requests[1][1]["body"])
        second = json.loads(script.requests[2][1]["body"])
        self.assertIn("includeArchived: true", first["query"])
        self.assertIsNone(first["variables"]["after"])
        self.assertEqual(second["variables"]["after"], "next")

    def test_response_comment_and_pagination_bounds_fail_closed(self):
        oversized = Response(200, b"x" * (adapter.MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(adapter.AdapterError, "byte limit"):
            adapter.fetch_issue(self.client(ScriptedConnections(oversized)), "TST-1")
        large_comment = comment("c", "x" * (adapter.MAX_COMMENT_BODY_BYTES + 1))
        with self.assertRaisesRegex(adapter.AdapterError, "comment exceeds"):
            adapter.fetch_issue(
                self.client(
                    ScriptedConnections(
                        issue_identity(), graph({"issue": issue_page([large_comment])})
                    )
                ),
                "TST-1",
            )
        repeated = ScriptedConnections(
            issue_identity(),
            graph({"issue": issue_page([], has_next=True, cursor="same")}),
            graph({"issue": issue_page([], has_next=True, cursor="same")}),
        )
        with self.assertRaisesRegex(adapter.AdapterError, "pagination"):
            adapter.fetch_issue(self.client(repeated), "TST-1")

    def test_total_comment_body_bytes_are_bounded_across_pages(self):
        large = "x" * 200_000
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": issue_page([comment("c1", large)], has_next=True, cursor="2")}),
            graph({"issue": issue_page([comment("c2", large)], has_next=True, cursor="3")}),
            graph({"issue": issue_page([comment("c3", large)])}),
        )
        with self.assertRaisesRegex(adapter.AdapterError, "comment content exceeds"):
            adapter.fetch_issue(self.client(script), "TST-1")

    def test_create_recovers_ambiguous_outcome_by_exact_id_and_content(self):
        issue_id = "12345678-1234-4123-8123-123456789abc"
        description = tweed_journal.build_genesis_description(
            {"schema_version": 1, "kind": "feature", "repository": "/repo", "planning_base": "a" * 40},
            "Human request",
        )
        created = issue_page()
        created["id"] = issue_id
        created["description"] = description
        script = ScriptedConnections(
            graph({"issues": {"nodes": []}}),
            graph(
                {
                    "projects": {
                        "nodes": [
                            {
                                "id": "project-1",
                                "name": "Tweed",
                                "teams": {"nodes": [{"id": "team-1", "key": "TST"}]},
                            }
                        ]
                    },
                }
            ),
            OSError("network failed with secret-key"),
            graph({"issues": {"nodes": [{"id": issue_id, "identifier": "TST-1"}]}}),
            graph({"issue": created}),
        )
        status, found = adapter.create_or_recover(
            self.client(script),
            {
                "issue_id": issue_id,
                "project": "Tweed",
                "title": "Test",
                "description": description,
            },
        )
        self.assertEqual(status, "recovered")
        self.assertEqual(found["id"], issue_id)
        self.assertEqual(len(script.requests), 5)

    def test_create_requires_unique_project_and_one_team(self):
        issue_id = "12345678-1234-4123-8123-123456789abc"
        script = ScriptedConnections(
            graph({"issues": {"nodes": []}}),
            graph({"projects": {"nodes": []}}),
        )
        with self.assertRaisesRegex(adapter.AdapterError, "project"):
            adapter.create_or_recover(
                self.client(script),
                {
                    "issue_id": issue_id,
                    "project": "Tweed",
                    "title": "Test",
                    "description": "Human request",
                },
            )

    def test_create_uses_unique_matched_projects_team(self):
        issue_id = "12345678-1234-4123-8123-123456789abc"
        description = tweed_journal.build_genesis_description(
            {"schema_version": 1, "kind": "feature", "repository": "/repo", "planning_base": "a" * 40},
            "Human request",
        )
        created = issue_page()
        created["id"] = issue_id
        created["team"] = {"id": "project-team", "key": "TST"}
        created["description"] = description
        script = ScriptedConnections(
            graph({"issues": {"nodes": []}}),
            graph(
                {
                    "projects": {
                        "nodes": [
                            {
                                "id": "project-1",
                                "name": "Tweed",
                                "teams": {"nodes": [{"id": "project-team"}]},
                            }
                        ]
                    }
                }
            ),
            graph({"issueCreate": {"success": True, "issue": {"id": issue_id}}}),
            graph({"issues": {"nodes": [{"id": issue_id, "identifier": "TST-1"}]}}),
            graph({"issue": created}),
        )
        adapter.create_or_recover(
            self.client(script),
            {
                "issue_id": issue_id,
                "project": "Tweed",
                "title": "Test",
                "description": description,
            },
        )
        mutation = json.loads(script.requests[2][1]["body"])
        self.assertEqual(mutation["variables"]["input"]["teamId"], "project-team")

    def test_append_rejects_stale_snapshot_without_mutation(self):
        page = issue_page()
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": page}),
            graph({"comments": {"nodes": []}}),
        )
        with self.assertRaisesRegex(adapter.AdapterError, "stale"):
            adapter.append_or_recover(
                self.client(script),
                {
                    "identifier": "TST-1",
                    "comment_id": "12345678-1234-4123-8123-123456789abc",
                    "body": "record",
                    "expected_snapshot_digest": "0" * 64,
                },
            )
        self.assertEqual(len(script.requests), 3)

    def test_append_recovers_ambiguous_mutation_and_post_fetches(self):
        comment_id = "12345678-1234-4123-8123-123456789abc"
        body = "normalized journal body"
        before = issue_page()
        normalized = {key: value for key, value in before.items() if key != "comments"}
        normalized["comments"] = []
        expected = adapter._snapshot_digest(normalized)
        made = comment(comment_id, body)
        direct = {**made, "issue": {"id": "issue-uuid"}}
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": before}),
            graph({"comments": {"nodes": []}}),
            OSError("ambiguous secret-key"),
            graph({"comments": {"nodes": [direct]}}),
            issue_identity(),
            graph({"issue": issue_page([made])}),
        )
        with (
            mock.patch.object(adapter, "_journal_head", side_effect=["predecessor", "desired"]),
            mock.patch.object(adapter, "_journal_record_digest", return_value="desired"),
        ):
            status, found = adapter.append_or_recover(
                self.client(script),
                {
                    "identifier": "TST-1",
                    "comment_id": comment_id,
                    "body": body,
                    "expected_snapshot_digest": expected,
                    "expected_content_digest": adapter._content_digest(normalized),
                    "expected_head_digest": "predecessor",
                    "desired_head_digest": "desired",
                },
            )
        self.assertEqual(status, "recovered")
        self.assertEqual(found["comments"][0]["id"], comment_id)
        self.assertEqual(len(script.requests), 7)

    def test_oauth_mutation_401_then_fresh_process_recovers_without_second_mutation(self):
        comment_id = "12345678-1234-4123-8123-123456789abc"
        body = "normalized journal body"
        before = issue_page()
        normalized = {key: value for key, value in before.items() if key != "comments"}
        normalized["comments"] = []
        request = {
            "identifier": "TST-1",
            "comment_id": comment_id,
            "body": body,
            "expected_snapshot_digest": adapter._snapshot_digest(normalized),
            "expected_content_digest": adapter._content_digest(normalized),
            "expected_head_digest": "predecessor",
            "desired_head_digest": "desired",
        }
        invalidated: list[str] = []
        first = ScriptedConnections(
            issue_identity(),
            graph({"issue": before}),
            graph({"comments": {"nodes": []}}),
            Response(401, {"error": "expired"}),
            graph({"comments": {"nodes": []}}),
        )
        first_client = adapter.LinearClient(
            "Bearer expired",
            first,
            unauthorized_callback=lambda: invalidated.append("expired"),
        )
        made = comment(comment_id, body)
        direct = {**made, "issue": {"id": "issue-uuid"}}
        recovered_page = issue_page([made])
        second = ScriptedConnections(
            issue_identity(),
            graph({"issue": recovered_page}),
            graph({"comments": {"nodes": [direct]}}),
        )
        with (
            mock.patch.object(
                adapter, "_journal_head", side_effect=["predecessor", "desired"]
            ),
            mock.patch.object(adapter, "_journal_record_digest", return_value="desired"),
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "status 401"):
                adapter.append_or_recover(first_client, request)
            status, _issue = adapter.append_or_recover(
                adapter.LinearClient("Bearer refreshed", second), request
            )
        mutation_count = sum(
            "mutation TweedCommentCreate" in json.loads(kwargs["body"])["query"]
            for script in (first, second)
            for _args, kwargs in script.requests
        )
        self.assertEqual(invalidated, ["expired"])
        self.assertEqual(status, "recovered")
        self.assertEqual(mutation_count, 1)

    def test_conflicting_deterministic_comment_fails_without_mutation(self):
        comment_id = "12345678-1234-4123-8123-123456789abc"
        before = issue_page()
        normalized = {key: value for key, value in before.items() if key != "comments"}
        normalized["comments"] = []
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": before}),
            graph({"comments": {"nodes": [{**comment(comment_id, "other"), "issue": {"id": "issue-uuid"}}]}}),
        )
        with (
            mock.patch.object(adapter, "_journal_head", return_value="head"),
            self.assertRaisesRegex(adapter.AdapterError, "conflicting"),
        ):
            adapter.append_or_recover(
                self.client(script),
                {
                    "identifier": "TST-1",
                    "comment_id": comment_id,
                    "body": "desired",
                    "expected_snapshot_digest": adapter._snapshot_digest(normalized),
                    "expected_content_digest": adapter._content_digest(normalized),
                    "desired_head_digest": "desired",
                },
            )
        self.assertEqual(len(script.requests), 3)

    def test_recovery_validates_real_canonical_journal_head(self):
        repository = "https://github.com/e3-solutions/tweed.git"
        base = "a" * 40
        description = tweed_journal.build_genesis_description(
            {
                "schema_version": 1,
                "kind": "problem",
                "repository": repository,
                "planning_base": base,
            },
            "Investigate the problem.",
        )
        genesis = tweed_journal.parse_genesis(description)
        record = tweed_journal.build_record(
            issue_identifier="TST-1",
            run_id="tw_1234567890abcdef",
            phase="root-cause",
            status="established",
            artifact_digest=tweed_journal.sha256_text("RCA report"),
            predecessor_digest=genesis.digest,
            genesis_digest=genesis.digest,
            repository=repository,
            base_commit=base,
            branch=None,
            commit=None,
            report="RCA report",
        )
        made = comment(record.metadata["comment_id"], record.comment)
        page = issue_page([made])
        page["description"] = description
        normalized = {key: value for key, value in page.items() if key != "comments"}
        normalized["comments"] = [made]
        direct = {**made, "issue": {"id": "issue-uuid"}}
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": page}),
            graph({"comments": {"nodes": [direct]}}),
        )
        status, _ = adapter.append_or_recover(
            self.client(script),
            {
                "identifier": "TST-1",
                "comment_id": record.metadata["comment_id"],
                "body": record.comment,
                "expected_snapshot_digest": "not used for exact recovery",
                "expected_content_digest": adapter._content_digest(
                    normalized, excluding_comment=record.metadata["comment_id"]
                ),
                "expected_head_digest": genesis.digest,
                "desired_head_digest": record.digest,
                "repository": repository,
                "base_commit": base,
            },
        )
        self.assertEqual(status, "recovered")

    def test_recovery_rejects_concurrent_human_description_edit(self):
        comment_id = "12345678-1234-4123-8123-123456789abc"
        made = comment(comment_id, "desired")
        page = issue_page([made])
        page["description"] = "Human request changed concurrently"
        direct = {**made, "issue": {"id": "issue-uuid"}}
        script = ScriptedConnections(
            issue_identity(),
            graph({"issue": page}),
            graph({"comments": {"nodes": [direct]}}),
        )
        with (
            mock.patch.object(adapter, "_journal_record_digest", return_value="1" * 64),
            self.assertRaisesRegex(adapter.AdapterError, "diverged"),
        ):
            adapter.append_or_recover(
                self.client(script),
                {
                    "identifier": "TST-1",
                    "comment_id": comment_id,
                    "body": "desired",
                    "expected_snapshot_digest": "old snapshot",
                    "expected_content_digest": "0" * 64,
                    "desired_head_digest": "1" * 64,
                },
            )

    def test_journal_comments_must_be_unedited_and_unarchived(self):
        repository = "https://github.com/e3-solutions/tweed.git"
        description = tweed_journal.build_genesis_description(
            {
                "schema_version": 1,
                "kind": "problem",
                "repository": repository,
                "planning_base": "a" * 40,
            },
            "Request",
        )
        genesis = tweed_journal.parse_genesis(description)
        request = {"repository": repository, "base_commit": "a" * 40}
        human = comment("human", "ordinary human conversation")
        human["updatedAt"] = "2026-08-03T00:01:00.000Z"
        self.assertEqual(
            adapter._journal_head(
                {"identifier": "TST-1", "description": description, "comments": [human]},
                request,
            ),
            genesis.digest,
        )
        for field, value in (
            ("editedAt", "2026-08-03T00:01:00.000Z"),
            ("archivedAt", "2026-08-03T00:01:00.000Z"),
        ):
            built = tweed_journal.build_record(
                issue_identifier="TST-1", run_id="tw_1234567890abcdef",
                phase="scope", status="scoped", artifact_digest=tweed_journal.sha256_text("report"),
                predecessor_digest=genesis.digest, genesis_digest=genesis.digest,
                repository=repository, base_commit="a" * 40, branch=None, commit=None,
                report="report",
            )
            record = comment("journal", built.comment)
            record[field] = value
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(adapter.AdapterError, "unedited and unarchived"),
            ):
                adapter._journal_head(
                    {
                        "identifier": "TST-1",
                        "description": description,
                        "comments": [record],
                    },
                    request,
                )


if __name__ == "__main__":
    unittest.main()
