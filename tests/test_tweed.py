from __future__ import annotations

import importlib.machinery
import importlib.util
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai_codex.types import TurnStatus
import tweed_journal


ROOT = Path(__file__).resolve().parents[1]
FAKE_ADAPTER = ROOT / "tests/fake_linear_adapter.py"
LOADER = importlib.machinery.SourceFileLoader("tweed_module", str(ROOT / "tweed"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
TWEED = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = TWEED
LOADER.exec_module(TWEED)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(directory: str) -> Path:
    root = Path(directory) / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Tweed Tests")
    git(root, "config", "user.email", "tweed@example.test")
    (root / "README.md").write_text("baseline\n")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "baseline")
    return root.resolve()


def make_issue(identifier: str, description: str) -> dict:
    raw = {
        "id": "12345678-1234-4123-8123-123456789abc",
        "identifier": identifier,
        "url": f"https://linear.test/{identifier}",
        "title": "Fixture issue",
        "description": description,
        "updatedAt": "1",
        "comments": [],
    }
    raw["content_digest"] = TWEED.transport_content_digest(raw)
    raw["snapshot_digest"] = TWEED.transport_snapshot_digest(raw)
    genesis = TWEED.journal.parse_genesis(description)
    return {
        "issue_id": raw["id"],
        "identifier": identifier,
        "url": raw["url"],
        "title": raw["title"],
        "description": description,
        "revision": genesis.digest,
        "digest": TWEED.digest(description),
        "snapshot_digest": raw["snapshot_digest"],
        "content_digest": raw["content_digest"],
        "genesis_digest": genesis.digest,
        "transport_snapshot": raw,
    }


def write_fake_linear(path: Path, issue: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "issues": {issue["identifier"]: issue.get("transport_snapshot", issue)},
                "next": 2,
                "writes": 0,
            }
        )
    )


class FakeThread:
    def __init__(self, response: dict):
        self.response = response
        self.prompts: list[str] = []
        self.options: list[dict] = []

    def run(self, prompt: str, **options):
        self.prompts.append(prompt)
        self.options.append(options)
        return SimpleNamespace(
            status=TurnStatus.completed,
            final_response=json.dumps(self.response),
            error=None,
        )


class SlowHandle:
    id = "turn-1"

    def __init__(self):
        self.interrupted = False

    def run(self):
        time.sleep(2)

    def interrupt(self):
        self.interrupted = True


class SlowThread:
    def __init__(self):
        self.handle = SlowHandle()

    def turn(self, _prompt: str, **_options):
        return self.handle


class ReadThread:
    def __init__(self, turns: list[SimpleNamespace]):
        self.turns = turns

    def read(self, *, include_turns: bool = False):
        assert include_turns
        return SimpleNamespace(thread=SimpleNamespace(turns=self.turns))


class TweedTests(unittest.TestCase):
    def test_incident_policy_requires_closed_utc_window_and_explicit_impact(self):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "Select the highest confirmed user impact",
        )
        self.assertEqual(policy["environment"], "production")
        for start, end, impact in (
            ("2026-08-03", "2026-08-04T00:00:00Z", "impact"),
            ("2026-08-04T00:00:00Z", "2026-08-03T00:00:00Z", "impact"),
            ("2026-08-03T00:00:00Z", "2026-08-04T00:00:00Z", " "),
        ):
            with (
                self.subTest(start=start, end=end, impact=impact),
                self.assertRaises(RuntimeError),
            ):
                TWEED.incident_policy(start, end, impact)
        with self.assertRaisesRegex(RuntimeError, "seven days"):
            TWEED.incident_policy(
                "2026-07-01T00:00:00Z",
                "2026-08-04T00:00:00Z",
                "impact",
            )

    def test_incident_mcp_receipts_are_from_actual_allowlisted_turn_items(self):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )
        item = SimpleNamespace(
            root=SimpleNamespace(
                type="mcpToolCall",
                id="call-1",
                server="railway",
                tool="get_logs",
                arguments={"start": policy["window_start"]},
                result={"content": [{"type": "text", "text": "bounded result"}]},
                error=None,
                duration_ms=12,
                status=SimpleNamespace(value="completed"),
            )
        )
        first = TWEED.canonical_mcp_evidence([item], policy, ("railway/get_logs",))
        second = TWEED.canonical_mcp_evidence([item], policy, ("railway/get_logs",))
        self.assertEqual(first, second)
        envelope = json.loads(first)
        self.assertEqual(envelope["calls"][0]["tool"], "get_logs")
        self.assertEqual(
            envelope["calls"][0]["arguments"]["start"], policy["window_start"]
        )
        with self.assertRaisesRegex(RuntimeError, "non-allowlisted"):
            TWEED.canonical_mcp_evidence(
                [item], policy, ("railway/environment_status",)
            )
        with self.assertRaisesRegex(RuntimeError, "no successful"):
            TWEED.canonical_mcp_evidence([], policy, ("railway/get_logs",))

        item.root.server = "codex_apps"
        item.root.tool = "railway.get_logs"
        app_evidence = json.loads(
            TWEED.canonical_mcp_evidence([item], policy, ("railway/get_logs",))
        )
        self.assertEqual(app_evidence["calls"][0]["qualified_tool"], "railway/get_logs")

    def test_incident_mcp_receipts_preserve_failed_attempts_without_losing_coverage(
        self,
    ):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )

        def item(call_id: str, status: str, result: object, error: object = None):
            return SimpleNamespace(
                root=SimpleNamespace(
                    type="mcpToolCall",
                    id=call_id,
                    server="codex_apps",
                    tool="github.search_prs",
                    arguments={"query": "production"},
                    result=result,
                    error=error,
                    duration_ms=1,
                    status=SimpleNamespace(value=status),
                )
            )

        encoded = TWEED.canonical_mcp_evidence(
            [
                item("bad-query", "failed", None, "remote payload must be redacted"),
                item("good-query", "completed", {"issues": []}),
            ],
            policy,
            ("github/search_prs",),
            coverage="GitHub existing-work search.",
        )
        calls = json.loads(encoded)["calls"]
        self.assertEqual(calls[0]["status"], "failed")
        self.assertEqual(calls[0]["error"], "model-facing MCP call failed")
        self.assertNotIn("remote payload", encoded.decode())
        self.assertEqual(calls[1]["status"], "completed")
        self.assertIsNone(calls[1]["error"])

        with self.assertRaisesRegex(RuntimeError, "no successful"):
            TWEED.canonical_mcp_evidence(
                [item("only-bad-query", "failed", None, "remote")],
                policy,
                ("github/search_prs",),
                coverage="Failed GitHub attempt only.",
            )

    def test_incident_mcp_config_hard_filters_tools_and_disables_other_servers(self):
        servers = [
            {"name": "railway", "transport": {"type": "stdio"}},
            {
                "name": "linear",
                "transport": {
                    "type": "streamable_http",
                    "url": "https://mcp.linear.app/mcp",
                },
            },
        ]
        with patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers):
            overrides = TWEED.incident_mcp_overrides(
                "/codex", Path("/repo"), ("railway/get_logs",)
            )
        self.assertIn('mcp_servers.railway.enabled_tools=["get_logs"]', overrides)
        self.assertIn(
            'mcp_servers.linear={url="https://tweed-mcp-disabled.invalid",enabled=false}',
            overrides,
        )
        app_overrides = TWEED.incident_app_overrides(
            ("github/search_prs", "linear/search")
        )
        self.assertIn("apps.default.enabled=false", app_overrides)
        self.assertIn('apps.github.enabled_tools=["search_prs"]', app_overrides)
        self.assertIn('apps.linear.enabled_tools=["search"]', app_overrides)
        self.assertNotIn("apps.slack.enabled=true", app_overrides)
        with (
            patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers),
            self.assertRaisesRegex(RuntimeError, "read-only Linear"),
        ):
            TWEED.incident_mcp_overrides(
                "/codex", Path("/repo"), ("linear/save_issue",)
            )
        app_only_servers = [
            {
                "name": "Railway",
                "transport": {"type": "stdio", "command": "railway", "args": ["mcp"]},
            }
        ]
        with (
            patch.object(TWEED, "find_codex", return_value="/codex"),
            patch.object(
                TWEED,
                "_resolved_codex_mcp_servers",
                return_value=app_only_servers,
            ),
        ):
            app_only = TWEED.incident_collector_codex_config(
                Path("/repo"), ("github/search_prs", "linear/search")
            )
        self.assertIn("apps.github.enabled=true", app_only.config_overrides)
        self.assertIn("apps.linear.enabled=true", app_only.config_overrides)
        self.assertTrue(
            any(
                value.startswith("mcp_servers.Railway=")
                for value in app_only.config_overrides
            )
        )

    def test_incident_direct_mcp_discovery_and_closed_window_validation(self):
        servers = [
            {
                "name": "Railway",
                "transport": {
                    "type": "stdio",
                    "command": "railway",
                    "args": ["mcp"],
                },
            },
            {
                "name": "github",
                "transport": {"type": "streamable_http", "url": "https://example"},
            },
        ]
        tools = [
            {
                "name": "get_logs",
                "description": "Read logs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "since": {"type": "string"},
                        "until": {"type": "string"},
                        "lines": {"type": "integer"},
                    },
                },
            }
        ]
        with (
            patch.object(TWEED, "find_codex", return_value="/codex"),
            patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers),
            patch.object(
                TWEED,
                "_stdio_mcp_session",
                return_value=(tools, [], "2025-03-26"),
            ),
        ):
            model_tools, catalog, direct_servers = TWEED.discover_direct_mcp_tools(
                Path("/repo"), ("Railway/get_logs", "github/search")
            )
        self.assertEqual(model_tools, ("github/search",))
        self.assertIn("Railway/get_logs", catalog)
        self.assertIn("Railway", direct_servers)

        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )
        valid = {
            "qualified_tool": "Railway/get_logs",
            "arguments_json": json.dumps(
                {
                    "since": policy["window_start"],
                    "until": policy["window_end"],
                    "lines": 100,
                }
            ),
        }
        normalized = TWEED.validate_direct_mcp_call(valid, catalog, policy)
        self.assertEqual(normalized["tool"], "get_logs")
        corrected = TWEED.validate_direct_mcp_call(
            {
                **valid,
                "arguments_json": json.dumps(
                    {"since": "30m", "until": "now", "lines": 100}
                ),
            },
            catalog,
            policy,
        )
        self.assertEqual(corrected["arguments"]["since"], policy["window_start"])
        self.assertEqual(corrected["arguments"]["until"], policy["window_end"])

    def test_incident_direct_mcp_strips_unrelated_environment(self):
        server = {
            "transport": {
                "type": "stdio",
                "command": "railway",
                "args": ["mcp"],
                "env": {"EXPLICIT_VALUE": "allowed"},
                "env_vars": ["EXPLICIT_SECRET"],
            }
        }
        with patch.dict(
            os.environ,
            {
                "PATH": "/bin",
                "HOME": "/home/test",
                "LINEAR_API_KEY": "must-not-leak",
                "UNRELATED_SECRET": "must-not-leak",
                "EXPLICIT_SECRET": "forwarded",
            },
            clear=True,
        ):
            transport = TWEED._stdio_mcp_transport(server, Path("/repo"))
        self.assertEqual(transport["env"]["EXPLICIT_SECRET"], "forwarded")
        self.assertEqual(transport["env"]["EXPLICIT_VALUE"], "allowed")
        self.assertNotIn("LINEAR_API_KEY", transport["env"])
        self.assertNotIn("UNRELATED_SECRET", transport["env"])
        for transport_config in (
            {**server["transport"], "env": {"LINEAR_API_KEY": "secret"}},
            {**server["transport"], "env_vars": ["LINEAR_API_KEY"]},
        ):
            with self.assertRaisesRegex(RuntimeError, "protected environment"):
                TWEED._stdio_mcp_transport(
                    {"transport": transport_config}, Path("/repo")
                )

    def test_incident_collector_schema_has_valid_empty_direct_call_contract(self):
        direct_calls = TWEED.incident_collector_schema()["properties"]["direct_calls"]
        self.assertEqual(direct_calls["maxItems"], 0)
        self.assertNotIn("enum", direct_calls["items"])

    def test_incident_direct_mcp_rejects_non_audited_mutation_tool(self):
        servers = [
            {
                "name": "Railway",
                "transport": {
                    "type": "stdio",
                    "command": "railway",
                    "args": ["mcp"],
                },
            }
        ]
        with (
            patch.object(TWEED, "find_codex", return_value="/codex"),
            patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers),
            patch.object(TWEED, "_stdio_mcp_session") as session,
            self.assertRaisesRegex(RuntimeError, "audited read allowlist"),
        ):
            TWEED.discover_direct_mcp_tools(Path("/repo"), ("Railway/delete_project",))
        session.assert_not_called()

    def test_incident_stdio_mcp_paginates_and_binds_complete_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_mcp.py"
            script.write_text(
                """import json, sys
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        cursor = message.get("params", {}).get("cursor")
        if cursor is None:
            result = {"tools": [{"name": "first", "inputSchema": {"type": "object"}}], "nextCursor": "page-2"}
        else:
            result = {"tools": [{"name": "second", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "ok"}], "isError": False}
    else:
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
            )
            server = {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(script)],
                }
            }
            tools, results, protocol = TWEED._stdio_mcp_session(
                server,
                Path(directory),
                [
                    {
                        "server": "Fake",
                        "tool": "second",
                        "qualified_tool": "Fake/second",
                        "arguments": {},
                    }
                ],
            )
        self.assertEqual([tool["name"] for tool in tools], ["first", "second"])
        self.assertEqual(protocol, "2025-03-26")
        self.assertEqual(results[0]["status"], "completed")

    def test_incident_stdio_mcp_answers_ping_and_redacts_protocol_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_mcp.py"
            script.write_text(
                """import json, sys
pending_initialize = None
for line in sys.stdin:
    message = json.loads(line)
    if pending_initialize is not None:
        assert message == {"jsonrpc": "2.0", "id": "server-ping", "result": {}}
        print(json.dumps({"jsonrpc": "2.0", "id": pending_initialize, "result": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}}), flush=True)
        pending_initialize = None
        continue
    method = message.get("method")
    if method == "initialize":
        pending_initialize = message["id"]
        print(json.dumps({"jsonrpc": "2.0", "id": "server-ping", "method": "ping", "params": {}}), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        result = {"tools": [{"name": "read", "inputSchema": {"type": "object"}}]}
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
    elif method == "tools/call":
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32001, "message": "secret-token-and-stack"}}), flush=True)
"""
            )
            server = {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(script)],
                }
            }
            _, results, _ = TWEED._stdio_mcp_session(
                server,
                Path(directory),
                [
                    {
                        "server": "Fake",
                        "tool": "read",
                        "qualified_tool": "Fake/read",
                        "arguments": {},
                    }
                ],
            )
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("-32001", results[0]["error"])
        self.assertNotIn("secret-token", results[0]["error"])

    def test_incident_stdio_mcp_rejects_missing_input_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_mcp.py"
            script.write_text(
                """import json, sys
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        result = {"tools": [{"name": "malformed"}]}
    else:
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
            )
            server = {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(script)],
                }
            }
            with self.assertRaisesRegex(RuntimeError, "invalid tool list"):
                TWEED._stdio_mcp_session(server, Path(directory), [])

    def test_incident_stdio_mcp_rejects_incomplete_initialize_result(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_mcp.py"
            script.write_text(
                """import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
            )
            server = {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(script)],
                }
            }
            with self.assertRaisesRegex(RuntimeError, "invalid initialize"):
                TWEED._stdio_mcp_session(server, Path(directory), [])

    def test_incident_direct_mcp_validates_types_and_enums(self):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )
        catalog = {
            "Railway/get_logs": {
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "log_type": {"type": "string", "enum": ["deploy", "http"]},
                        "lines": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "since": {"type": "string"},
                        "until": {"type": "string"},
                    },
                    "additionalProperties": False,
                }
            }
        }
        with self.assertRaisesRegex(RuntimeError, "enum"):
            TWEED.validate_direct_mcp_call(
                {
                    "qualified_tool": "Railway/get_logs",
                    "arguments_json": json.dumps({"log_type": "delete", "lines": 10}),
                },
                catalog,
                policy,
            )
        with self.assertRaisesRegex(RuntimeError, "wrong type"):
            TWEED.validate_direct_mcp_call(
                {
                    "qualified_tool": "Railway/get_logs",
                    "arguments_json": json.dumps(
                        {"log_type": "deploy", "lines": "many"}
                    ),
                },
                catalog,
                policy,
            )

    def test_incident_call_budget_fails_before_dispatch_65(self):
        items = [
            SimpleNamespace(root=SimpleNamespace(type="mcpToolCall"))
            for _ in range(TWEED.MAX_INCIDENT_MCP_CALLS)
        ]
        with self.assertRaisesRegex(RuntimeError, "call limit"):
            TWEED.validate_incident_dispatch_budget(
                items,
                [],
                [{"qualified_tool": "Railway/get_logs", "arguments_json": "{}"}],
            )

    def test_incident_canonical_receipt_binds_runner_stdio_calls(self):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )
        direct = {
            "server": "Railway",
            "tool": "list_projects",
            "qualified_tool": "Railway/list_projects",
            "arguments": {},
            "result": {"content": [{"type": "text", "text": "negotiation"}]},
            "protocol_version": "2025-03-26",
            "tools_sha256": "a" * 64,
            "duration_ms": 5,
        }
        envelope = json.loads(
            TWEED.canonical_mcp_evidence(
                [],
                policy,
                ("Railway/list_projects",),
                direct_calls=[direct],
            )
        )
        self.assertEqual(envelope["calls"][0]["source"], "runner-stdio")
        self.assertEqual(envelope["calls"][0]["tools_sha256"], "a" * 64)
        failed = {
            **direct,
            "result": None,
            "status": "failed",
            "error": "bounded MCP error",
        }
        with self.assertRaisesRegex(RuntimeError, "no successful"):
            TWEED.canonical_mcp_evidence(
                [],
                policy,
                ("Railway/list_projects",),
                direct_calls=[failed],
            )

    def test_incident_duplicate_must_bind_successful_linear_and_github_receipts(self):
        policy = TWEED.incident_policy(
            "2026-08-03T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "highest confirmed impact",
        )

        def item(
            call_id: str, server: str, result: object, tool: str = "search"
        ) -> SimpleNamespace:
            return SimpleNamespace(
                root=SimpleNamespace(
                    type="mcpToolCall",
                    id=call_id,
                    server=server,
                    tool=tool,
                    arguments={"query": "incident"},
                    result=result,
                    error=None,
                    duration_ms=1,
                    status=SimpleNamespace(value="completed"),
                )
            )

        encoded = TWEED.canonical_mcp_evidence(
            [
                item("linear-call", "linear", {"identifier": "COR-3293"}),
                item("github-call", "github", {"url": "https://github.test/pr/1"}),
            ],
            policy,
            ("linear/search", "github/search", "Railway/get_logs"),
            direct_calls=[
                {
                    "server": "Railway",
                    "tool": "get_logs",
                    "qualified_tool": "Railway/get_logs",
                    "arguments": {
                        "since": policy["window_start"],
                        "until": policy["window_end"],
                    },
                    "result": {"content": [{"type": "text", "text": "error"}]},
                    "protocol_version": "2025-03-26",
                    "tools_sha256": "a" * 64,
                    "duration_ms": 1,
                }
            ],
            coverage="Production logs plus Linear and GitHub existing-work searches.",
        )
        TWEED.validate_incident_collection_coverage(encoded)
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdee"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.put_artifact(run_id, "incident-evidence", encoded)
                TWEED.put_artifact(run_id, "incident-policy", json.dumps(policy))
                result = {
                    "status": "established",
                    "supporting_call_ids": ["runner-stdio:3"],
                    "existing_work_call_ids": ["linear-call", "github-call"],
                    "duplicate_reference": "COR-3293",
                }
                TWEED.validate_incident_rca_evidence(run_id, result)
                fetched_pr = item(
                    "github-fetch",
                    "github",
                    {"url": "https://github.test/pr/1"},
                    "fetch_pr",
                )
                encoded_with_fetch = TWEED.canonical_mcp_evidence(
                    [
                        item("linear-call", "linear", {"identifier": "COR-3293"}),
                        item("github-search", "github", {"issues": []}),
                        fetched_pr,
                    ],
                    policy,
                    (
                        "linear/search",
                        "github/search",
                        "github/fetch_pr",
                        "Railway/get_logs",
                    ),
                    direct_calls=[
                        {
                            "server": "Railway",
                            "tool": "get_logs",
                            "qualified_tool": "Railway/get_logs",
                            "arguments": {
                                "since": policy["window_start"],
                                "until": policy["window_end"],
                            },
                            "result": {"content": [{"type": "text", "text": "error"}]},
                            "protocol_version": "2025-03-26",
                            "tools_sha256": "a" * 64,
                            "duration_ms": 1,
                        }
                    ],
                    coverage="Production logs plus Linear and GitHub existing-work searches.",
                )
                TWEED.put_artifact(run_id, "incident-evidence", encoded_with_fetch)
                TWEED.validate_incident_collection_coverage(encoded_with_fetch)
                TWEED.validate_incident_rca_evidence(
                    run_id,
                    {
                        **result,
                        "supporting_call_ids": ["runner-stdio:4"],
                        "existing_work_call_ids": ["linear-call", "github-fetch"],
                        "duplicate_reference": "https://github.test/pr/1",
                    },
                )
                TWEED.put_artifact(run_id, "incident-evidence", encoded)
                with self.assertRaisesRegex(RuntimeError, "not present"):
                    TWEED.validate_incident_rca_evidence(
                        run_id, {**result, "duplicate_reference": "COR-9999"}
                    )
                with self.assertRaisesRegex(RuntimeError, "not present"):
                    TWEED.validate_incident_rca_evidence(
                        run_id, {**result, "duplicate_reference": "COR-329"}
                    )
                outside_window = json.loads(encoded)
                outside_window["calls"][2]["arguments"]["since"] = "30m"
                outside_encoded = json.dumps(outside_window).encode()
                with self.assertRaisesRegex(RuntimeError, "frozen window"):
                    TWEED.validate_incident_collection_coverage(outside_encoded)
                wrong_policy = {
                    **policy,
                    "window_start": "2026-08-02T00:00:00Z",
                }
                with self.assertRaisesRegex(RuntimeError, "frozen policy"):
                    TWEED.validate_incident_collection_coverage(encoded, wrong_policy)

    def test_incident_rca_requires_specific_title_and_fail_closed_dedupe(self):
        established = {
            "status": "established",
            "summary": "Room teardown self-waits",
            "question": None,
            "report_markdown": "Status: established\n\n# Root cause\n\nCycle.",
            "issue_title": " Production Room2 teardown self-deadlocks ",
            "duplicate_reference": "COR-100",
            "supporting_call_ids": ["call-production"],
            "existing_work_call_ids": ["call-linear", "call-github"],
        }
        result = TWEED.validate_incident_rca_result(established)
        self.assertEqual(
            result["issue_title"], "Production Room2 teardown self-deadlocks"
        )
        self.assertEqual(result["duplicate_reference"], "COR-100")
        with self.assertRaisesRegex(RuntimeError, "specific issue title"):
            TWEED.validate_incident_rca_result(
                {
                    **established,
                    "issue_title": None,
                    "duplicate_reference": None,
                }
            )
        duplicate = TWEED.validate_incident_rca_result(
            {**established, "issue_title": None}
        )
        self.assertIsNone(duplicate["issue_title"])
        self.assertEqual(duplicate["duplicate_reference"], "COR-100")

    def test_incident_duplicate_creates_no_linear_issue(self):
        result = {
            "status": "established",
            "summary": "Existing deployment drain incident",
            "question": None,
            "report_markdown": "Status: established\n\n# Root cause\n\nKnown.",
            "issue_title": "Deployment replacement terminates active calls",
            "duplicate_reference": "COR-3285",
            "supporting_call_ids": ["call-production"],
            "existing_work_call_ids": ["call-linear", "call-github"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            args = SimpleNamespace(
                repo=str(root),
                team="Core",
                project="Frontline",
                request=["Address recent production problems"],
                window_start="2026-08-03T00:00:00Z",
                window_end="2026-08-04T00:00:00Z",
                impact="highest confirmed user impact",
                mcp_tool=["Railway/get_logs", "linear/search", "github/search_prs"],
                agent=True,
            )
            with (
                patch.dict(
                    os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
                ),
                patch.object(
                    TWEED,
                    "collect_incident_evidence",
                    return_value=("collector-thread", "collected"),
                ),
                patch.object(
                    TWEED,
                    "run_incident_rca",
                    return_value=("rca-thread", result, "workflow"),
                ),
                patch.object(TWEED, "validate_incident_rca_evidence"),
                patch.object(TWEED, "publish_incident") as publish,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code = TWEED.incident_command(args)
        self.assertEqual(code, 9)
        publish.assert_not_called()
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["state"], "duplicate")
        self.assertIn("COR-3285", receipt["summary"])

    def test_incident_publish_retry_recovers_create_then_appends_without_codex(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdee"
            description = TWEED.intake_description(
                "problem", "Incident", root, "Frontline", run_id
            )
            issue = make_issue("TST-1", description)
            state_home = Path(directory) / "state"
            policy = TWEED.incident_policy(
                "2026-08-03T00:00:00Z",
                "2026-08-04T00:00:00Z",
                "highest confirmed impact",
            )

            def item(call_id: str, server: str, result: object) -> SimpleNamespace:
                return SimpleNamespace(
                    root=SimpleNamespace(
                        type="mcpToolCall",
                        id=call_id,
                        server=server,
                        tool="search_prs" if server == "github" else "search",
                        arguments={"query": "incident"},
                        result=result,
                        error=None,
                        duration_ms=1,
                        status=SimpleNamespace(value="completed"),
                    )
                )

            evidence = TWEED.canonical_mcp_evidence(
                [
                    item("linear-call", "linear", {"identifier": "COR-2"}),
                    item("github-call", "github", {"url": "https://github.test/2"}),
                ],
                policy,
                ("linear/search", "github/search_prs", "Railway/get_logs"),
                direct_calls=[
                    {
                        "server": "Railway",
                        "tool": "get_logs",
                        "qualified_tool": "Railway/get_logs",
                        "arguments": {
                            "since": policy["window_start"],
                            "until": policy["window_end"],
                        },
                        "result": {"content": [{"type": "text", "text": "error"}]},
                        "protocol_version": "2025-03-26",
                        "tools_sha256": "b" * 64,
                        "duration_ms": 1,
                    }
                ],
                coverage="Production logs plus existing-work searches.",
            )
            publication_evidence = {
                "status": "established",
                "supporting_call_ids": ["runner-stdio:3"],
                "existing_work_call_ids": ["linear-call", "github-call"],
                "duplicate_reference": None,
            }
            with patch.dict(os.environ, {"TWEED_STATE_HOME": str(state_home)}):
                manifest = TWEED.load_artifact_manifest(run_id)
                TWEED.put_artifact(
                    run_id,
                    "linear-intake-description",
                    description,
                    manifest=manifest,
                )
                TWEED.put_artifact(
                    run_id,
                    "rca",
                    "Status: established\n\n# Root cause\n\nConfirmed.",
                    manifest=manifest,
                )
                TWEED.put_artifact(
                    run_id, "incident-evidence", evidence, manifest=manifest
                )
                TWEED.put_artifact(
                    run_id,
                    "incident-policy",
                    json.dumps(policy),
                    manifest=manifest,
                )
                TWEED.put_artifact(
                    run_id,
                    "incident-publication-evidence",
                    json.dumps(publication_evidence),
                    manifest=manifest,
                )
                TWEED.put_artifact(
                    run_id,
                    "workflow",
                    TWEED.load_workflow("root-cause"),
                    manifest=manifest,
                )
                TWEED.save_run(
                    {
                        "run_id": run_id,
                        "state": "sync-blocked",
                        "operation": "incident-publish",
                        "phase": "root-cause",
                        "repository": str(root),
                        "project": "Frontline",
                        "team": "Core",
                        "title": "Specific incident",
                        "thread_id": "thread-1",
                        "summary": "RCA established",
                        "policy": policy,
                        "desired_digest": TWEED.digest(description),
                    }
                )
                with (
                    patch.object(
                        TWEED,
                        "create_linear_issue",
                        return_value={
                            "status": "synced",
                            "identifier": "TST-1",
                            "url": issue["url"],
                            "issue": issue,
                        },
                    ) as create,
                    patch.object(TWEED, "finish_phase", return_value=0) as finish,
                ):
                    code = TWEED._retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
            self.assertEqual(code, 0)
            create.assert_called_once()
            finish.assert_called_once()

    def test_incident_established_path_creates_then_retries_single_rca_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            state_home = Path(directory) / "state"
            store = Path(directory) / "linear.json"
            trace = Path(directory) / "linear.trace"
            store.write_text(json.dumps({"issues": {}, "next": 1, "writes": 0}))
            run_id = "tw_0123456789abcdee"
            policy = TWEED.incident_policy(
                "2026-08-03T00:00:00Z",
                "2026-08-04T00:00:00Z",
                "highest confirmed impact",
            )

            def item(call_id: str, server: str) -> SimpleNamespace:
                return SimpleNamespace(
                    root=SimpleNamespace(
                        type="mcpToolCall",
                        id=call_id,
                        server=server,
                        tool="search_prs" if server == "github" else "search",
                        arguments={"query": "incident"},
                        result={"items": []},
                        error=None,
                        duration_ms=1,
                        status=SimpleNamespace(value="completed"),
                    )
                )

            evidence = TWEED.canonical_mcp_evidence(
                [item("linear-call", "linear"), item("github-call", "github")],
                policy,
                ("linear/search", "github/search_prs", "Railway/get_logs"),
                direct_calls=[
                    {
                        "server": "Railway",
                        "tool": "get_logs",
                        "qualified_tool": "Railway/get_logs",
                        "arguments": {
                            "since": policy["window_start"],
                            "until": policy["window_end"],
                        },
                        "result": {"content": [{"type": "text", "text": "error"}]},
                        "protocol_version": "2025-03-26",
                        "tools_sha256": "d" * 64,
                        "duration_ms": 1,
                    }
                ],
                coverage="Production logs plus existing-work searches.",
            )
            result = {
                "status": "established",
                "summary": "Confirmed incident",
                "question": None,
                "report_markdown": "Status: established\n\n# Root cause\n\nConfirmed.",
                "issue_title": "Specific production incident",
                "duplicate_reference": None,
                "supporting_call_ids": ["runner-stdio:3"],
                "existing_work_call_ids": ["linear-call", "github-call"],
            }

            def collect(
                _root: Path,
                current_run: str,
                _request: str,
                _policy: dict,
                _tools: tuple,
            ) -> tuple[str, str]:
                self.assertEqual(json.loads(store.read_text())["writes"], 0)
                TWEED.put_artifact(current_run, "incident-evidence", evidence)
                return "collector-thread", "collected"

            def rca(_root: Path, current_run: str, _policy: dict):
                self.assertEqual(json.loads(store.read_text())["writes"], 0)
                TWEED.put_artifact(
                    current_run, "workflow", TWEED.load_workflow("root-cause")
                )
                return "rca-thread", result, "workflow"

            args = SimpleNamespace(
                repo=str(root),
                team="Core",
                project="Frontline",
                request=["Address production incident"],
                window_start=policy["window_start"],
                window_end=policy["window_end"],
                impact=policy["impact_policy"],
                mcp_tool=[
                    "Railway/get_logs",
                    "linear/search",
                    "github/search_prs",
                ],
                agent=True,
            )
            env = {
                "TWEED_STATE_HOME": str(state_home),
                "TWEED_LINEAR_ADAPTER": str(FAKE_ADAPTER),
                "FAKE_LINEAR_STATE": str(store),
                "FAKE_LINEAR_TRACE": str(trace),
            }
            blocked_append = {
                "status": "blocked",
                "identifier": None,
                "url": None,
                "reason": "simulated append outage",
            }
            blocked_create = {
                "status": "blocked",
                "identifier": None,
                "url": None,
                "reason": "simulated create outage",
            }
            with (
                patch.dict(os.environ, env),
                patch.object(TWEED, "new_run_id", return_value=run_id),
                patch.object(TWEED, "collect_incident_evidence", side_effect=collect),
                patch.object(TWEED, "run_incident_rca", side_effect=rca),
                patch.object(TWEED, "create_linear_issue", return_value=blocked_create),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(TWEED.incident_command(args), 8)
            self.assertEqual(json.loads(store.read_text())["writes"], 0)
            self.assertFalse(trace.exists())

            with (
                patch.dict(os.environ, env),
                patch.object(
                    TWEED, "append_linear_record", return_value=blocked_append
                ),
                contextlib.redirect_stdout(io.StringIO()) as first_retry_output,
            ):
                first_retry_code = TWEED.retry_sync_command(
                    SimpleNamespace(run_id=run_id, agent=True)
                )
                first_retry_state = TWEED.load_run(run_id)
            self.assertEqual(
                first_retry_code,
                8,
                (first_retry_state, first_retry_output.getvalue()),
            )
            self.assertEqual(
                json.loads(store.read_text())["writes"],
                1,
                (first_retry_state, first_retry_output.getvalue()),
            )
            self.assertEqual(trace.read_text().splitlines(), ["create-or-recover"])

            with (
                patch.dict(os.environ, env),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                retry_code = TWEED.retry_sync_command(
                    SimpleNamespace(run_id=run_id, agent=True)
                )
                retry_state = TWEED.load_run(run_id)
            self.assertEqual(
                retry_code,
                0,
                (retry_state, output.getvalue()),
            )
            self.assertEqual(json.loads(store.read_text())["writes"], 2)
            self.assertEqual(
                trace.read_text().splitlines(),
                ["create-or-recover", "append-or-recover"],
            )
            self.assertEqual(retry_state["state"], "completed")
            receipt = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(receipt["next_stage"], "needs-scope")

    def test_incident_workflow_recovers_only_exact_orphan_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdee"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                workflow = TWEED.load_workflow("root-cause")
                encoded = workflow.encode()
                orphan = (
                    TWEED.artifact_root(run_id)
                    / "sha256"
                    / hashlib.sha256(encoded).hexdigest()
                )
                TWEED.atomic_bytes_write(orphan, encoded)
                TWEED.atomic_json_write(
                    TWEED.artifact_manifest_path(run_id),
                    TWEED.empty_artifact_manifest(run_id),
                )
                recovered = TWEED.read_incident_workflow(run_id)
                self.assertEqual(recovered, workflow)
                entry = TWEED.load_artifact_manifest(run_id)["artifacts"]["workflow"]
                self.assertEqual(entry["sha256"], hashlib.sha256(encoded).hexdigest())

    def test_incident_collection_failure_is_terminal_and_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdee"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.save_run(
                    {
                        "run_id": run_id,
                        "state": "collecting",
                        "operation": "incident",
                    }
                )
                TWEED.mark_run_terminal(run_id, "failed", "collector failed")
                state = TWEED.load_run(run_id)
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["failed_from_state"], "collecting")

    def test_incident_rca_synthesis_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdee"
            root = make_repo(directory)
            state_home = Path(directory) / "state"
            thread = SimpleNamespace(id="thread-1", set_name=lambda _name: None)
            captured: dict[str, object] = {}

            class Client:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return None

                def thread_start(self, **kwargs):
                    captured.update(kwargs)
                    return thread

            client = Client()
            policy = TWEED.incident_policy(
                "2026-08-03T00:00:00Z",
                "2026-08-04T00:00:00Z",
                "highest confirmed impact",
            )

            def item(call_id: str, server: str) -> SimpleNamespace:
                return SimpleNamespace(
                    root=SimpleNamespace(
                        type="mcpToolCall",
                        id=call_id,
                        server=server,
                        tool="search",
                        arguments={"query": "incident"},
                        result={"items": []},
                        error=None,
                        duration_ms=1,
                        status=SimpleNamespace(value="completed"),
                    )
                )

            evidence = TWEED.canonical_mcp_evidence(
                [item("linear-call", "linear"), item("github-call", "github")],
                policy,
                ("linear/search", "github/search", "Railway/get_logs"),
                direct_calls=[
                    {
                        "server": "Railway",
                        "tool": "get_logs",
                        "qualified_tool": "Railway/get_logs",
                        "arguments": {
                            "since": policy["window_start"],
                            "until": policy["window_end"],
                        },
                        "result": {"content": [{"type": "text", "text": "error"}]},
                        "protocol_version": "2025-03-26",
                        "tools_sha256": "c" * 64,
                        "duration_ms": 1,
                    }
                ],
                coverage="Production logs plus existing-work searches.",
            )
            with patch.dict(os.environ, {"TWEED_STATE_HOME": str(state_home)}):
                for name, value in (
                    ("request", "incident"),
                    ("incident-policy", json.dumps(policy)),
                    ("incident-evidence", evidence),
                ):
                    TWEED.put_artifact(run_id, name, value)
                TWEED.save_run(
                    {
                        "run_id": run_id,
                        "state": "evidence-frozen",
                        "operation": "incident",
                        "repository": str(root),
                    }
                )
                with (
                    patch.object(TWEED, "Codex", return_value=client),
                    patch.object(TWEED, "incident_rca_codex_config"),
                    patch.object(
                        TWEED,
                        "completed_json_turn",
                        return_value={
                            "status": "established",
                            "summary": "root cause",
                            "question": None,
                            "report_markdown": "Status: established",
                            "issue_title": "Specific incident",
                            "duplicate_reference": None,
                            "supporting_call_ids": ["call-1"],
                            "existing_work_call_ids": ["call-2", "call-3"],
                        },
                    ),
                ):
                    TWEED.run_incident_rca(root, run_id, policy)
        self.assertEqual(captured["sandbox"], TWEED.Sandbox.read_only)
        self.assertEqual(captured["approval_mode"], TWEED.ApprovalMode.deny_all)

    def test_incident_resume_reuses_frozen_evidence_without_recollection(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdee"
            root = make_repo(directory)
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                TWEED.put_artifact(run_id, "incident-evidence", b"{}")
                TWEED.put_artifact(run_id, "request", "incident")
                result = {
                    "status": "established",
                    "summary": "duplicate",
                    "question": None,
                    "report_markdown": "Status: established",
                    "issue_title": None,
                    "duplicate_reference": "COR-1",
                    "supporting_call_ids": ["call-1"],
                    "existing_work_call_ids": ["call-1", "call-2"],
                }
                for terminal_state in ("failed", "canceled"):
                    state = {
                        "run_id": run_id,
                        "state": terminal_state,
                        "operation": "incident",
                        "repository": str(root),
                        "policy": {"window_start": "a", "window_end": "b"},
                        "allowed_tools": ["linear/search", "github/search"],
                    }
                    TWEED.save_run(state)
                    with (
                        patch.object(TWEED, "collect_incident_evidence") as collect,
                        patch.object(
                            TWEED,
                            "run_incident_rca",
                            return_value=("thread", result, "workflow"),
                        ) as rca,
                        patch.object(TWEED, "finalize_incident_rca", return_value=9),
                    ):
                        code = TWEED.resume_incident_run(
                            SimpleNamespace(run_id=run_id, answer=[], agent=True), state
                        )
                    self.assertEqual(code, 9)
                    collect.assert_not_called()
                    rca.assert_called_once()

    def test_problem_and_feature_start_at_their_only_legal_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            problem = TWEED.intake_description(
                "problem", "Duplicate export", root, "CX", "tw_0123456789abcdef"
            )
            feature = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )

        self.assertEqual(TWEED.parse_metadata(problem)["stage"], "needs-rca")
        self.assertEqual(TWEED.parse_metadata(feature)["stage"], "needs-scope")

    def test_section_parser_accepts_linear_indented_end_marker(self):
        value = "<!-- tweed:scope:start -->\nStatus: scoped\n  <!-- tweed:scope:end -->"
        self.assertEqual(TWEED.section_body(value, "scope"), "Status: scoped")

    def test_wrong_stage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "problem", "Duplicate export", root, "CX", "tw_0123456789abcdef"
            )
            issue = {
                "identifier": "ENG-1",
                "url": "https://linear.example/ENG-1",
                "title": "Duplicate export",
                "description": description,
            }
            with self.assertRaisesRegex(RuntimeError, "scope requires 'needs-scope'"):
                TWEED.validate_issue_for_phase(issue, TWEED.PHASES["scope"], root)

    def test_feature_cannot_run_root_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )
            metadata = TWEED.parse_metadata(description)
            metadata["stage"] = "needs-rca"
            description = tweed_journal.build_genesis_description(
                {
                    key: value
                    for key, value in metadata.items()
                    if key != "request_digest"
                },
                "CSV export",
            )
            issue = {
                "identifier": "ENG-2",
                "url": "https://linear.example/ENG-2",
                "title": "CSV export",
                "description": description,
            }
            with self.assertRaisesRegex(RuntimeError, "only valid for problem"):
                TWEED.validate_issue_for_phase(issue, TWEED.PHASES["root-cause"], root)

    def test_structured_turn_uses_output_schema(self):
        response = {
            "status": "scoped",
            "summary": "Scoped",
            "question": None,
            "report_markdown": "Status: scoped",
        }
        thread = FakeThread(response)
        result = TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])
        self.assertEqual(result, response)
        self.assertIn("output_schema", thread.options[0])
        self.assertNotIn("sandbox", thread.options[0])

    def test_phase_threads_are_unattended_and_unrestricted(self):
        scope = TWEED.phase_thread_permissions(TWEED.PHASES["scope"])
        self.assertEqual(scope["approval_mode"], TWEED.ApprovalMode.deny_all)
        self.assertEqual(scope["sandbox"], TWEED.Sandbox.full_access)
        self.assertNotIn("config", scope)

        implement = TWEED.phase_thread_permissions(TWEED.PHASES["implement"])
        self.assertEqual(implement["approval_mode"], TWEED.ApprovalMode.deny_all)
        self.assertEqual(implement["sandbox"], TWEED.Sandbox.full_access)
        self.assertNotIn("config", implement)

    def test_needs_input_requires_a_structured_question(self):
        thread = FakeThread(
            {
                "status": "needs-input",
                "summary": "Need a decision",
                "question": None,
                "report_markdown": "Status: needs-input",
            }
        )
        with self.assertRaisesRegex(RuntimeError, "without a structured question"):
            TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])

    def test_report_status_must_match_structured_status(self):
        thread = FakeThread(
            {
                "status": "scoped",
                "summary": "Scoped",
                "question": None,
                "report_markdown": "Status: blocked",
            }
        )
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            TWEED.run_phase_turn(thread, "scope it", TWEED.PHASES["scope"])

    def test_scope_evidence_is_verified_from_repository_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            readme_hash = TWEED.hashlib.sha256(
                (root / "README.md").read_bytes()
            ).hexdigest()
            report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{readme_hash}`\n"
                "- `new-file.ts` → `ABSENT`\n\n## Implementation steps\n"
            )
            TWEED.validate_scope_evidence(root, report)

            malformed = report.replace(readme_hash, readme_hash[:-1])
            with self.assertRaisesRegex(RuntimeError, "invalid SHA-256"):
                TWEED.validate_scope_evidence(root, malformed)

            wrong = report.replace(readme_hash, "0" * 64)
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                TWEED.validate_scope_evidence(root, wrong)

            observed_failure = report.replace(
                "- `new-file.ts` → `ABSENT`",
                "- `/tmp/tweed-run/artifacts/manifests/manifest.json` → `"
                + ("a" * 64)
                + "`\n"
                "- `/tmp/tweed-run/artifacts/sha256/content` → `" + ("b" * 64) + "`",
            )
            with self.assertRaisesRegex(RuntimeError, "unsafe scope evidence path"):
                TWEED.validate_scope_evidence(root, observed_failure)

            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", "tw_0123456789abcdef"
            )
            snapshot = {
                "description": description + "\n" + TWEED.section_block("scope", report)
            }
            TWEED.validate_linear_snapshot(root, snapshot)
            snapshot["description"] = snapshot["description"].replace(
                readme_hash, readme_hash[:-1]
            )
            with self.assertRaisesRegex(RuntimeError, "invalid SHA-256"):
                TWEED.validate_linear_snapshot(root, snapshot)

    def test_turn_timeout_interrupts_the_active_turn(self):
        thread = SlowThread()
        with self.assertRaisesRegex(TimeoutError, "exceeded 1 seconds"):
            TWEED.completed_json_turn(thread, "work", {}, timeout_seconds=1)
        self.assertTrue(thread.handle.interrupted)

    def test_linear_turn_timeout_is_bounded_and_configurable(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWEED_LINEAR_TIMEOUT", None)
            self.assertEqual(TWEED.linear_turn_timeout(), 300)
        with patch.dict(os.environ, {"TWEED_LINEAR_TIMEOUT": "45"}):
            self.assertEqual(TWEED.linear_turn_timeout(), 45)
        with patch.dict(os.environ, {"TWEED_LINEAR_TIMEOUT": "0"}):
            with self.assertRaisesRegex(RuntimeError, "positive integer"):
                TWEED.linear_turn_timeout()

    def test_resume_prompt_distinguishes_clarification_from_interruption(self):
        clarification = TWEED.resume_prompt("awaiting-input", "Use option A")
        interrupted = TWEED.resume_prompt("running", "")

        self.assertIn("Clarification answer", clarification)
        self.assertIn("runner process was interrupted", interrupted)
        with self.assertRaisesRegex(RuntimeError, "requires an answer"):
            TWEED.resume_prompt("awaiting-input", "")
        with self.assertRaisesRegex(RuntimeError, "without a clarification answer"):
            TWEED.resume_prompt("failed", "unexpected answer")

    def test_run_execution_lock_rejects_a_duplicate_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                with TWEED.run_execution_lock("tw_0123456789abcdef"):
                    with self.assertRaisesRegex(RuntimeError, "already active"):
                        with TWEED.run_execution_lock("tw_0123456789abcdef"):
                            pass

    def test_duplicate_resume_does_not_fail_the_live_run_or_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            state = {
                "run_id": run_id,
                "state": "running",
                "phase": "scope",
                "repository": directory,
                "worktree": directory,
                "branch": None,
            }
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.save_run(state)
                TWEED.LAST_RUN_ID = None
                with TWEED.run_execution_lock(run_id):
                    with patch.object(
                        TWEED,
                        "read_request",
                        side_effect=AssertionError("must not prompt"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "already active"):
                            TWEED.resume_command(
                                SimpleNamespace(run_id=run_id, answer=[], agent=True)
                            )
                self.assertEqual(TWEED.load_run(run_id)["state"], "running")
                self.assertIsNone(TWEED.LAST_RUN_ID)

    def test_completed_recorded_turn_is_recovered_without_a_new_turn(self):
        response = json.dumps(
            {
                "status": "scoped",
                "summary": "Scoped",
                "question": None,
                "report_markdown": "Status: scoped",
            }
        )
        turn = SimpleNamespace(
            id="turn-1",
            status=TurnStatus.completed,
            items=[
                SimpleNamespace(
                    type="agentMessage",
                    phase=SimpleNamespace(value="final_answer"),
                    text=response,
                )
            ],
        )

        result = TWEED.recover_recorded_result(
            ReadThread([turn]), {"turn_id": "turn-1"}, TWEED.PHASES["scope"]
        )

        self.assertEqual(result["status"], "scoped")

    def test_active_or_missing_recorded_turn_cannot_be_duplicated(self):
        active = SimpleNamespace(id="turn-1", status=TurnStatus.in_progress, items=[])
        with self.assertRaisesRegex(RuntimeError, "still active"):
            TWEED.recover_recorded_result(
                ReadThread([active]),
                {"turn_id": "turn-1"},
                TWEED.PHASES["scope"],
            )
        with self.assertRaisesRegex(RuntimeError, "no recorded"):
            TWEED.recover_recorded_result(ReadThread([]), {}, TWEED.PHASES["scope"])

    def test_resume_rejects_a_moved_or_changed_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            metadata = {"planning_base": git(root, "rev-parse", "HEAD")}
            TWEED.validate_resume_worktree(
                root, root, None, TWEED.PHASES["scope"], metadata
            )
            (root / "README.md").write_text("changed\n")
            git(root, "add", "README.md")
            git(root, "commit", "-m", "move head")
            with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
                TWEED.validate_resume_worktree(
                    root, root, None, TWEED.PHASES["scope"], metadata
                )

    def test_run_state_round_trip_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                state = {
                    "run_id": "tw_0123456789abcdef",
                    "state": "awaiting-input",
                    "report_markdown": "Status: needs-input",
                    "workflow_text": "workflow",
                }
                TWEED.save_run(state)
                loaded = TWEED.load_run(state["run_id"])
                path = TWEED.state_path(state["run_id"])
                self.assertEqual(loaded["state"], "awaiting-input")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse((path.parent / "report.md").exists())
            self.assertEqual(loaded["run_schema_version"], 3)

    def test_project_configuration_is_keyed_by_canonical_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            config = Path(directory) / "config.json"
            with patch.dict(os.environ, {"TWEED_CONFIG": str(config)}):
                TWEED.set_linear_project(root, "Customer Experience")
                self.assertEqual(TWEED.linear_project(root), "Customer Experience")
                TWEED.set_linear_project(root, None)
                self.assertIsNone(TWEED.linear_project(root))

    def test_linear_sync_repository_identity_matches_standard_github_remotes(self):
        expected = "e3-solutions/tweed"
        for remote in (
            "https://github.com/e3-solutions/tweed.git",
            "git@github.com:e3-solutions/tweed.git",
            "ssh://git@github.com/e3-solutions/tweed.git",
            "ssh://git@github.com:22/e3-solutions/tweed.git",
        ):
            with self.subTest(remote=remote):
                self.assertEqual(TWEED.normalize_github_origin(remote), expected)
        for remote in (
            "https://example.com/e3-solutions/tweed.git",
            "git@github.com:e3-solutions",
            "https://github.com/e3-solutions/tweed/extra",
        ):
            with self.subTest(remote=remote):
                with self.assertRaisesRegex(RuntimeError, "GitHub"):
                    TWEED.normalize_github_origin(remote)

    def test_linear_sync_repository_identity_falls_back_to_canonical_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            self.assertEqual(
                TWEED.linear_binding_repository(root),
                {"identity": str(root), "identity_source": "canonical-root"},
            )

    def test_shared_binding_honors_env_override_and_beats_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            git(
                root,
                "remote",
                "add",
                "origin",
                "git@github.com:e3-solutions/sample.git",
            )
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            (sync_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": {
                            "e3-solutions/sample": {
                                "team": "Shared Team",
                                "project": "Shared Project",
                            }
                        }
                    }
                )
            )
            legacy = Path(directory) / "legacy.json"
            with patch.dict(
                os.environ,
                {
                    "LINEAR_SYNC_CONFIG_DIR": str(sync_dir),
                    "TWEED_CONFIG": str(legacy),
                },
            ):
                TWEED.set_legacy_linear_binding(root, "Legacy Team", "Legacy Project")
                binding = TWEED.resolve_linear_binding(root)
            self.assertEqual(binding["team"], "Shared Team")
            self.assertEqual(binding["project"], "Shared Project")
            self.assertEqual(binding["source"], "linear-progress-sync")
            self.assertEqual(binding["repository"], "e3-solutions/sample")
            self.assertRegex(binding["binding_digest"], r"^[a-f0-9]{64}$")

    def test_legacy_team_project_binding_remains_compatibility_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            with patch.dict(
                os.environ,
                {
                    "LINEAR_SYNC_CONFIG_DIR": str(sync_dir),
                    "TWEED_CONFIG": str(Path(directory) / "legacy.json"),
                },
            ):
                TWEED.set_legacy_linear_binding(root, "Legacy Team", "Legacy Project")
                binding = TWEED.resolve_linear_binding(root)
            self.assertEqual(binding["source"], "legacy-tweed")
            self.assertEqual(binding["team"], "Legacy Team")
            self.assertEqual(binding["project"], "Legacy Project")

    def test_shared_opt_out_precedes_legacy_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            (sync_dir / "repos.json").write_text(
                json.dumps(
                    {"repos": {str(root): {"disabled": True, "reason": "Not tracked"}}}
                )
            )
            with patch.dict(
                os.environ,
                {
                    "LINEAR_SYNC_CONFIG_DIR": str(sync_dir),
                    "TWEED_CONFIG": str(Path(directory) / "legacy.json"),
                },
            ):
                TWEED.set_legacy_linear_binding(root, "Legacy", "Fallback")
                binding = TWEED.resolve_linear_binding(root)
            self.assertTrue(binding["disabled"])
            self.assertEqual(binding["reason"], "Not tracked")
            self.assertEqual(binding["source"], "linear-progress-sync")
            with patch.dict(os.environ, {"LINEAR_SYNC_CONFIG_DIR": str(sync_dir)}):
                explicit = TWEED.resolve_linear_binding(
                    root,
                    team_override="Explicit Team",
                    project_override="Explicit Project",
                )
            self.assertFalse(explicit["disabled"])
            self.assertEqual(explicit["source"], "command")

    def test_shared_binding_malformed_json_schema_and_duplicates_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            path = sync_dir / "repos.json"
            with patch.dict(os.environ, {"LINEAR_SYNC_CONFIG_DIR": str(sync_dir)}):
                for raw in (
                    b"{",
                    b'{"repos":[]}',
                    (
                        '{"repos":{"%s":{"team":"A","project":"P",'
                        '"disabled":true}}}' % root
                    ).encode(),
                    b'{"repos":{},"repos":{}}',
                    b'{"repos":{"Owner/Repo":{"team":"A","project":"P"},'
                    b'"owner/repo":{"team":"B","project":"Q"}}}',
                ):
                    with self.subTest(raw=raw):
                        path.write_bytes(raw)
                        with self.assertRaisesRegex(
                            RuntimeError, "malformed|repos|ambiguous"
                        ):
                            TWEED.resolve_linear_binding(root)

    def test_shared_binding_keeps_case_distinct_canonical_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            (sync_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": {
                            str(root): {"team": "A", "project": "P"},
                            str(root).swapcase(): {"team": "B", "project": "Q"},
                        }
                    }
                )
            )
            with patch.dict(os.environ, {"LINEAR_SYNC_CONFIG_DIR": str(sync_dir)}):
                binding = TWEED.resolve_linear_binding(root)
            self.assertEqual(binding["team"], "A")

    def test_project_command_reports_effective_disabled_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            (sync_dir / "repos.json").write_text(
                json.dumps(
                    {"repos": {str(root): {"disabled": True, "reason": "Local only"}}}
                )
            )
            args = SimpleNamespace(
                repo=str(root), action=None, value=[], team=None, project_name=None
            )
            with (
                patch.dict(os.environ, {"LINEAR_SYNC_CONFIG_DIR": str(sync_dir)}),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(TWEED.project_command(args), 0)
            value = json.loads(output.getvalue())
            self.assertTrue(value["disabled"])
            self.assertEqual(value["source"], "linear-progress-sync")
            self.assertEqual(value["reason"], "Local only")
            self.assertFalse(value["configured"])

    def test_auth_cli_is_interactive_bounded_and_never_prints_tokens(self):
        args = SimpleNamespace(
            agent=False,
            auth_action="status",
        )
        with (
            patch.object(
                TWEED.linear_oauth,
                "status",
                return_value={
                    "configured": True,
                    "logged_in": True,
                    "refresh_required": False,
                    "expires_at": 1234,
                    "scopes": ["read", "issues:create", "comments:create"],
                    "access_token": "must-not-print",
                },
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(TWEED.auth_command(args), 0)
        self.assertNotIn("must-not-print", output.getvalue())
        with self.assertRaisesRegex(RuntimeError, "interactive"):
            TWEED.auth_command(SimpleNamespace(agent=True, auth_action="status"))

    def test_auth_cli_defaults_to_official_app_without_requesting_client_id(self):
        parser = TWEED.build_parser()
        login = parser.parse_args(["auth", "login"])
        self.assertIsNone(login.client_id)
        help_text = parser._subparsers._group_actions[0].choices["auth"].format_help()
        login_help = (
            parser._subparsers._group_actions[0]
            .choices["auth"]
            ._subparsers._group_actions[0]
            .choices["login"]
            .format_help()
        )
        self.assertIn(TWEED.linear_oauth.DEFAULT_CLIENT_ID, login_help)
        self.assertNotIn("client ID is still required", help_text + login_help)
        args = SimpleNamespace(agent=False, auth_action="status")
        with (
            patch.object(
                TWEED.linear_oauth,
                "status",
                return_value={
                    "configured": True,
                    "logged_in": False,
                    "refresh_required": False,
                    "expires_at": None,
                    "scopes": [],
                    "viewer": None,
                },
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(TWEED.auth_command(args), 1)
        self.assertEqual(
            output.getvalue().strip(),
            "Linear OAuth is not logged in; run tweed auth login",
        )

    def test_child_sessions_disable_the_competing_linear_orchestrator(self):
        with (
            patch.object(TWEED, "find_codex", return_value="/bin/true"),
            patch.object(
                TWEED,
                "linear_mcp_disable_overrides",
                return_value=(
                    'mcp_servers.linear={url="https://tweed-linear-disabled.invalid",enabled=false}',
                ),
            ),
        ):
            config = TWEED.codex_config(Path("/tmp").resolve())
        self.assertIn("features.hooks=false", config.config_overrides)
        for override in TWEED.LINEAR_PLUGIN_DISABLE_OVERRIDES:
            self.assertIn(override, config.config_overrides)
        self.assertIn(
            'mcp_servers.linear={url="https://tweed-linear-disabled.invalid",enabled=false}',
            config.config_overrides,
        )
        for name in TWEED.LINEAR_CHILD_ENV_NAMES:
            self.assertEqual(config.env[name], "")

    def test_linear_mcp_disable_overrides_handle_clean_http_alias_and_stdio(self):
        servers = [
            {
                "name": "linear-prod",
                "transport": {
                    "type": "streamable_http",
                    "url": "HTTPS://MCP.LINEAR.APP/mcp",
                },
            },
            {
                "name": "issues",
                "transport": {
                    "type": "stdio",
                    "command": "npx",
                    "args": [
                        "-y",
                        "mcp-remote",
                        "https://mcp.linear.app",
                    ],
                },
            },
            {"name": "other", "transport": {"command": "true"}},
            {
                "name": "nonlinear-math",
                "transport": {"type": "stdio", "command": "math-server"},
            },
        ]
        with patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers):
            self.assertEqual(
                TWEED.linear_mcp_disable_overrides("/codex", Path("/repo")),
                (
                    'mcp_servers.linear-prod={url="https://tweed-linear-disabled.invalid",enabled=false}',
                    'mcp_servers.issues={command="tweed-linear-disabled",enabled=false}',
                ),
            )

    def test_linear_mcp_disable_overrides_reject_unsafe_alias(self):
        servers = [
            {
                "name": "linear.prod",
                "transport": {"url": "https://mcp.linear.app/mcp"},
            }
        ]
        with (
            patch.object(TWEED, "_resolved_codex_mcp_servers", return_value=servers),
            self.assertRaisesRegex(
                RuntimeError,
                "cannot safely disable Linear MCP alias 'linear.prod'",
            ),
        ):
            TWEED.linear_mcp_disable_overrides("/codex", Path("/repo"))

    def test_linear_mcp_disable_overrides_include_effective_project_layer(self):
        codex = TWEED.find_codex()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            (root / ".git").mkdir()
            nested = root / "packages" / "service"
            nested.mkdir(parents=True)
            project_config = root / ".codex" / "config.toml"
            project_config.parent.mkdir()
            project_config.write_text(
                '[mcp_servers.linear-project]\nurl = "https://mcp.linear.app/mcp"\n'
            )
            home = Path(directory) / "codex-home"
            home.mkdir()
            (home / "config.toml").write_text(
                f'[projects.{json.dumps(str(root))}]\ntrust_level = "trusted"\n'
            )
            env = {**os.environ, "CODEX_HOME": str(home)}
            with patch.dict(os.environ, env):
                overrides = TWEED.linear_mcp_disable_overrides(codex, nested)
            completed = subprocess.run(
                [codex, "mcp", "get", "linear-project"],
                cwd=nested,
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )
            if overrides:
                self.assertEqual(
                    overrides,
                    (
                        'mcp_servers.linear-project={url="https://tweed-linear-disabled.invalid",enabled=false}',
                    ),
                )
                completed = subprocess.run(
                    [codex, "-c", overrides[0], "mcp", "get", "linear-project"],
                    cwd=nested,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=env,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.strip(), "linear-project (disabled)")
            else:
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("No MCP server named", completed.stderr)

    def test_linear_mcp_override_parses_in_installed_codex(self):
        codex = TWEED.find_codex()
        configurations = {
            "http-with-tool-policy": (
                "[mcp_servers.linear]\n"
                'url = "https://mcp.linear.app/mcp"\n'
                "[mcp_servers.linear.tools.save_issue]\n"
                'approval_mode = "approve"\n'
            ),
            "stdio-mcp-remote": (
                "[mcp_servers.linear]\n"
                'command = "npx"\n'
                'args = ["-y", "mcp-remote", "https://mcp.linear.app/mcp"]\n'
            ),
        }
        for label, contents in configurations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                (home / "config.toml").write_text(contents)
                with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                    overrides = TWEED.linear_mcp_disable_overrides(codex, home)
                self.assertEqual(
                    overrides,
                    (
                        (
                            'mcp_servers.linear={url="https://tweed-linear-disabled.invalid",enabled=false}'
                            if label == "http-with-tool-policy"
                            else 'mcp_servers.linear={command="tweed-linear-disabled",enabled=false}'
                        ),
                    ),
                )
                completed = subprocess.run(
                    [codex, "-c", overrides[0], "mcp", "get", "linear"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env={**os.environ, "CODEX_HOME": str(home)},
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.strip(), "linear (disabled)")

    def test_linear_plugin_overrides_disable_real_keys_in_installed_codex(self):
        codex = TWEED.find_codex()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "config.toml").write_text(
                '[plugins."linear-progress-sync@coreedge-local"]\n'
                "enabled = true\n"
                '[plugins."linear@openai-curated"]\n'
                "enabled = true\n"
            )
            config = TWEED.CodexConfig(
                codex_bin=codex,
                config_overrides=TWEED.LINEAR_PLUGIN_DISABLE_OVERRIDES,
                cwd=directory,
                env={"CODEX_HOME": directory},
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                with TWEED.Codex(config) as client:
                    result = client._client._request_raw(
                        "config/read", {"cwd": directory, "includeLayers": False}
                    )
            plugins = result["config"]["plugins"]
            self.assertFalse(plugins["linear-progress-sync@coreedge-local"]["enabled"])
            self.assertFalse(plugins["linear@openai-curated"]["enabled"])
            self.assertNotIn('"linear-progress-sync@coreedge-local"', plugins)

    def test_all_child_sessions_use_sol_medium(self):
        with (
            patch.object(TWEED, "find_codex", return_value="/bin/true"),
            patch.object(TWEED, "linear_mcp_disable_overrides", return_value=()),
        ):
            config = TWEED.codex_config(Path("/tmp").resolve())
        self.assertIn('model="gpt-5.6-sol"', config.config_overrides)
        self.assertIn('model_reasoning_effort="medium"', config.config_overrides)

    def test_runner_owns_integration_worktree_and_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            base = git(root, "rev-parse", "HEAD")
            worktree, branch = TWEED.prepare_implementation_worktree(
                root, "ENG-9", base
            )
            (worktree / "feature.txt").write_text("implemented\n")
            commit = TWEED.commit_phase(worktree, "ENG-9", TWEED.PHASES["implement"])

            self.assertEqual(branch, "tweed/eng-9")
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), commit)
            self.assertFalse(git(worktree, "status", "--porcelain"))

    def test_initial_phase_config_uses_the_actual_child_worktree(self):
        caller_root = Path("/tmp/tweed-caller").resolve()
        worktree = Path("/tmp/tweed-integration").resolve()
        issue = {
            "identifier": "ENG-9",
            "url": "https://linear.test/ENG-9",
            "digest": "sha256:issue",
        }
        metadata = {
            "planning_base": "a" * 40,
            "stage": "ready-to-implement",
        }
        args = SimpleNamespace(
            command="implement",
            issue="ENG-9",
            repo=str(caller_root),
            agent=True,
        )
        with (
            patch.object(TWEED, "repository_root", return_value=caller_root),
            patch.object(TWEED, "new_run_id", return_value="tw_test"),
            patch.object(TWEED, "active_run", return_value=contextlib.nullcontext()),
            patch.object(
                TWEED, "run_execution_lock", return_value=contextlib.nullcontext()
            ),
            patch.object(
                TWEED, "issue_execution_lock", return_value=contextlib.nullcontext()
            ),
            patch.object(
                TWEED, "repository_write_lock", return_value=contextlib.nullcontext()
            ),
            patch.object(TWEED, "read_linear_issue", return_value=issue),
            patch.object(
                TWEED,
                "validate_issue_for_phase",
                return_value=(metadata, caller_root),
            ),
            patch.object(
                TWEED,
                "prepare_implementation_worktree",
                return_value=(worktree, "tweed/eng-9"),
            ),
            patch.object(TWEED, "codex_config", return_value=object()) as config,
            patch.object(
                TWEED,
                "Codex",
                return_value=contextlib.nullcontext(object()),
            ),
            patch.object(
                TWEED,
                "start_phase_thread",
                return_value=(SimpleNamespace(id="thread-1"), "workflow", "prompt"),
            ),
            patch.object(TWEED, "save_run"),
            patch.object(
                TWEED,
                "run_phase_turn",
                return_value={"status": "implemented"},
            ),
            patch.object(TWEED, "finish_phase", return_value=0),
        ):
            self.assertEqual(TWEED.phase_command(args), 0)
        config.assert_called_once_with(worktree)

    def test_review_without_repairs_keeps_implementation_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            commit = TWEED.commit_phase(root, "ENG-9", TWEED.PHASES["review"])
            self.assertEqual(commit, git(root, "rev-parse", "HEAD"))

    def test_model_free_linear_adapter_appends_exact_utf8_and_fails_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            description = TWEED.intake_description(
                "feature", "Café 🚚\nsecond line", root, "CX", "tw_0123456789abcdef"
            )
            issue = make_issue("TST-1", description)
            store = Path(directory) / "linear.json"
            write_fake_linear(store, issue)
            env = {
                "TWEED_LINEAR_ADAPTER": str(FAKE_ADAPTER),
                "FAKE_LINEAR_STATE": str(store),
            }
            with patch.dict(os.environ, env):
                frozen = TWEED.read_linear_issue(root, "TST-1")
                report = (
                    "Status: scoped\n\nUnicode: naïve 🚚\n\n"
                    "## Repository state\n\n"
                    f"- `README.md` → `{TWEED.sha256_file(root / 'README.md')}`"
                )
                record = TWEED.journal.build_record(
                    issue_identifier="TST-1",
                    run_id="tw_1123456789abcdef",
                    phase="scope",
                    status="scoped",
                    artifact_digest=TWEED.digest(report),
                    predecessor_digest=frozen["revision"],
                    genesis_digest=frozen["genesis_digest"],
                    repository=str(root),
                    base_commit=git(root, "rev-parse", "HEAD"),
                    branch=None,
                    commit=None,
                    report=report,
                )
                synced = TWEED.append_linear_record(root, frozen, record)
                stale_record = TWEED.journal.build_record(
                    issue_identifier="TST-1",
                    run_id="tw_2123456789abcdef",
                    phase="scope",
                    status="scoped",
                    artifact_digest=TWEED.digest(report + " stale"),
                    predecessor_digest=frozen["revision"],
                    genesis_digest=frozen["genesis_digest"],
                    repository=str(root),
                    base_commit=git(root, "rev-parse", "HEAD"),
                    branch=None,
                    commit=None,
                    report=report + " stale",
                )
                stale = TWEED.append_linear_record(root, frozen, stale_record)
            state = json.loads(store.read_text())
            self.assertEqual(synced["status"], "synced")
            self.assertEqual(stale["status"], "blocked")
            self.assertEqual(state["writes"], 1)
            self.assertEqual(state["issues"]["TST-1"]["description"], description)
            self.assertEqual(
                state["issues"]["TST-1"]["comments"][0]["body"], record.comment
            )

    def test_api_key_fallback_requires_explicit_key(self):
        with patch.dict(os.environ, {"TWEED_LINEAR_AUTH": "api-key"}, clear=False):
            os.environ.pop("TWEED_LINEAR_ADAPTER", None)
            os.environ.pop("LINEAR_API_KEY", None)
            with self.assertRaisesRegex(RuntimeError, "api-key mode"):
                TWEED.linear_adapter_command()

    def test_bundled_linear_adapter_defaults_to_oauth_without_api_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWEED_LINEAR_ADAPTER", None)
            os.environ.pop("TWEED_LINEAR_AUTH", None)
            os.environ.pop("LINEAR_API_KEY", None)
            command = TWEED.linear_adapter_command()
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(Path(command[1]).name, "tweed_linear_adapter.py")

    def test_external_adapter_receives_no_tweed_credentials(self):
        with patch.dict(
            os.environ,
            {
                "TWEED_LINEAR_ADAPTER": shutil.which("true") or "/usr/bin/true",
                "TWEED_LINEAR_AUTH": "api-key",
                "LINEAR_API_KEY": "secret",
                "TWEED_LINEAR_OAUTH_FILE": "/secret/token-store",
            },
        ):
            command = TWEED.linear_adapter_command()
            environment = TWEED.linear_adapter_environment(command)
        self.assertNotIn("LINEAR_API_KEY", environment)
        self.assertNotIn("TWEED_LINEAR_AUTH", environment)
        self.assertNotIn("TWEED_LINEAR_OAUTH_FILE", environment)

    def test_external_adapter_cannot_spoof_bundled_credential_trust(self):
        bundled = Path(TWEED.__file__).resolve().with_name("tweed_linear_adapter.py")
        with patch.dict(
            os.environ,
            {
                "TWEED_LINEAR_ADAPTER": f"{sys.executable} {bundled}",
                "TWEED_LINEAR_AUTH": "api-key",
                "LINEAR_API_KEY": "secret",
                "TWEED_LINEAR_OAUTH_FILE": "/secret/token-store",
            },
        ):
            command = TWEED.linear_adapter_command()
            environment = TWEED.linear_adapter_environment(command)
        self.assertNotIn("LINEAR_API_KEY", environment)
        self.assertNotIn("TWEED_LINEAR_OAUTH_FILE", environment)

    def test_create_accepts_normalized_visible_markdown_with_exact_genesis_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description(
                "feature", "CSV export", root, "CX", run_id
            )
            normalized = description.replace(
                "# Request\n\nCSV export", "Request: CSV export"
            )
            raw = {
                "id": "12345678-1234-4123-8123-123456789abc",
                "identifier": "TST-1",
                "url": "https://linear.test/TST-1",
                "title": "CSV export",
                "description": normalized,
                "updatedAt": "1",
                "comments": [],
            }
            raw["content_digest"] = TWEED.transport_content_digest(raw)
            raw["snapshot_digest"] = TWEED.transport_snapshot_digest(raw)
            with patch.object(
                TWEED,
                "call_linear_adapter",
                return_value={
                    "protocol": TWEED.LINEAR_PROTOCOL,
                    "status": "recovered",
                    "issue": raw,
                },
            ):
                result = TWEED.create_linear_issue(
                    root, "CX", "CSV export", description, run_id
                )
            self.assertEqual(result["status"], "synced")
            self.assertEqual(
                tweed_journal.parse_genesis(normalized).digest,
                tweed_journal.parse_genesis(description).digest,
            )

    def test_external_adapter_stderr_cannot_reach_errors_or_receipts(self):
        secret = "lin_api_do_not_leak_123"
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "adapter"
            adapter.write_text(
                "#!/bin/sh\necho 'lin_api_do_not_leak_123 server body' >&2\nexit 9\n"
            )
            adapter.chmod(0o700)
            with patch.dict(
                os.environ,
                {"TWEED_LINEAR_ADAPTER": str(adapter), "LINEAR_API_KEY": secret},
            ):
                with self.assertRaises(RuntimeError) as caught:
                    TWEED.call_linear_adapter({"operation": "fetch"})
                value = TWEED.receipt(
                    run_id="tw_0123456789abcdef",
                    state="failed",
                    error=secret + "\n" + ("x" * 10000),
                )
        encoded = json.dumps(value, separators=(",", ":"))
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn(secret, encoded)
        self.assertLess(len(encoded.encode()), 4096)

    def test_external_adapter_is_terminated_at_stream_byte_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "adapter.py"
            adapter.write_text(
                "import subprocess,sys\n"
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'])\n"
                "sys.stdout.buffer.write(b'x' * 1100000)\n"
            )
            with patch.dict(
                os.environ,
                {
                    "TWEED_LINEAR_ADAPTER": f"{sys.executable} {adapter}",
                    "LINEAR_API_KEY": "not-forwarded-in-argv",
                },
            ):
                started = time.monotonic()
                with self.assertRaisesRegex(RuntimeError, "byte limit"):
                    TWEED.call_linear_adapter({"operation": "fetch"})
                self.assertLess(time.monotonic() - started, 2)

    def test_create_transport_failure_emits_retryable_sync_blocked_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            with (
                patch.dict(os.environ, {"TWEED_STATE_HOME": directory}),
                patch.object(TWEED, "repository_root", return_value=root),
                patch.object(
                    TWEED,
                    "resolve_linear_binding",
                    return_value={
                        "repository": str(root),
                        "identity_source": "canonical-root",
                        "team": "Core",
                        "project": "CX",
                        "source": "linear-progress-sync",
                        "binding_digest": "b" * 64,
                        "disabled": False,
                    },
                ),
                patch.object(
                    TWEED, "create_linear_issue", side_effect=RuntimeError("offline")
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                result = TWEED.create_command(
                    SimpleNamespace(
                        repo=str(root),
                        request=["Create", "CSV"],
                        kind="feature",
                        agent=True,
                        team=None,
                        project=None,
                    )
                )
                receipt = json.loads(output.getvalue())
                saved = TWEED.load_run(receipt["run_id"])
            self.assertEqual(result, 8)
            self.assertEqual(receipt["state"], "sync-blocked")
            self.assertEqual(receipt["linear_team"], "Core")
            self.assertEqual(receipt["linear_project"], "CX")
            self.assertEqual(receipt["linear_binding_source"], "linear-progress-sync")
            self.assertEqual(receipt["linear_binding_digest"], "b" * 64)
            self.assertEqual(saved["state"], "sync-blocked")
            self.assertEqual(saved["team"], "Core")
            self.assertEqual(saved["project"], "CX")
            self.assertEqual(saved["binding_source"], "linear-progress-sync")
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                metadata = TWEED.parse_metadata(
                    TWEED.read_artifact(
                        receipt["run_id"], "linear-intake-description"
                    ).decode()
                )
            self.assertEqual(metadata["linear_team"], "Core")
            self.assertEqual(metadata["linear_binding_digest"], "b" * 64)

    def test_retry_sync_uses_frozen_binding_after_shared_config_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            git(
                root,
                "remote",
                "add",
                "origin",
                "https://github.com/e3-solutions/sample.git",
            )
            sync_dir = Path(directory) / "shared"
            sync_dir.mkdir()
            config_path = sync_dir / "repos.json"

            def write_binding(team: str, project: str) -> None:
                config_path.write_text(
                    json.dumps(
                        {
                            "repos": {
                                "e3-solutions/sample": {
                                    "team": team,
                                    "project": project,
                                }
                            }
                        }
                    )
                )

            write_binding("Frozen Team", "Frozen Project")
            environment = {
                "TWEED_STATE_HOME": str(Path(directory) / "state"),
                "LINEAR_SYNC_CONFIG_DIR": str(sync_dir),
                "TWEED_CONFIG": str(Path(directory) / "legacy.json"),
            }
            with (
                patch.dict(os.environ, environment),
                patch.object(TWEED, "repository_root", return_value=root),
                patch.object(
                    TWEED, "create_linear_issue", side_effect=RuntimeError("offline")
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(
                    TWEED.create_command(
                        SimpleNamespace(
                            repo=str(root),
                            request=["Create", "CSV"],
                            kind="feature",
                            agent=True,
                            team=None,
                            project=None,
                        )
                    ),
                    8,
                )
            run_id = json.loads(output.getvalue())["run_id"]
            with patch.dict(os.environ, environment):
                frozen = TWEED.load_run(run_id)
            write_binding("Changed Team", "Changed Project")
            captured: dict[str, object] = {}

            def recover(_root, project, _title, _description, _run_id, *, team=None):
                captured.update({"team": team, "project": project})
                return {
                    "status": "synced",
                    "identifier": "TST-1",
                    "url": "https://linear.test/TST-1",
                }

            with (
                patch.dict(os.environ, environment),
                patch.object(TWEED, "create_linear_issue", side_effect=recover),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    TWEED._retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    ),
                    0,
                )
            self.assertEqual(
                captured, {"team": "Frozen Team", "project": "Frozen Project"}
            )
            self.assertEqual(frozen["binding_source"], "linear-progress-sync")
            self.assertRegex(frozen["binding_digest"], r"^[a-f0-9]{64}$")

    def test_completed_phase_transport_failure_preserves_reasoning_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description("feature", "CSV", root, "CX", run_id)
            issue = make_issue("TST-1", description)
            report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{TWEED.sha256_file(root / 'README.md')}`"
            )
            result = {
                "status": "scoped",
                "summary": "done",
                "question": None,
                "report_markdown": report,
            }
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                with (
                    patch.object(
                        TWEED,
                        "verify_linear_issue",
                        side_effect=AssertionError(
                            "finish must publish the persisted journal record directly"
                        ),
                    ),
                    patch.object(
                        TWEED,
                        "append_linear_record",
                        side_effect=RuntimeError("adapter offline"),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    code = TWEED.finish_phase(
                        root,
                        root,
                        None,
                        issue,
                        TWEED.parse_metadata(description),
                        TWEED.PHASES["scope"],
                        run_id,
                        "thread-1",
                        result,
                        True,
                    )
                saved = TWEED.load_run(run_id)
                persisted_report = TWEED.read_artifact(run_id, "scope")
                with (
                    patch.object(
                        TWEED,
                        "append_linear_record",
                        return_value={
                            "status": "synced",
                            "identifier": issue["identifier"],
                            "url": issue["url"],
                        },
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as retry_output,
                ):
                    retry_code = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
            self.assertEqual(code, 8)
            self.assertEqual(json.loads(output.getvalue())["state"], "sync-blocked")
            self.assertEqual(saved["state"], "sync-blocked")
            self.assertEqual(persisted_report, report.encode())
            self.assertEqual(retry_code, 0)
            self.assertEqual(json.loads(retry_output.getvalue())["state"], "completed")

    def test_resume_adopts_exact_post_checkpoint_commit_without_codex(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description("feature", "CSV", root, "CX", run_id)
            issue = make_issue("TST-1", description)
            metadata = TWEED.parse_metadata(description)
            report = "Status: implemented\n\n## Verification\n\n- Passed"
            (root / "implementation.txt").write_text("done\n")
            pre_commit = git(root, "rev-parse", "HEAD")
            git(root, "add", "-A")
            expected_tree = git(root, "write-tree")
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                TWEED.record_phase_artifacts(
                    run_id,
                    TWEED.PHASES["implement"],
                    {"report_markdown": report},
                )
                TWEED.save_run(
                    {
                        "schema_version": TWEED.SCHEMA_VERSION,
                        "run_id": run_id,
                        "state": "finalizing",
                        "operation": "phase",
                        "phase": "implement",
                        "issue": TWEED.compact_issue(issue),
                        "metadata": metadata,
                        "repository": str(root),
                        "worktree": str(root),
                        "branch": "main",
                        "pre_commit_head": pre_commit,
                        "expected_commit_tree": expected_tree,
                        "thread_id": "thread-1",
                        "summary": "done",
                        "status": "implemented",
                    }
                )
                committed = TWEED.commit_phase(root, "TST-1", TWEED.PHASES["implement"])
                with (
                    patch.object(TWEED, "verify_linear_issue"),
                    patch.object(
                        TWEED,
                        "append_linear_record",
                        return_value={
                            "status": "synced",
                            "identifier": "TST-1",
                            "url": issue["url"],
                        },
                    ),
                    patch.object(
                        TWEED.Codex,
                        "__init__",
                        side_effect=AssertionError(
                            "finalization must not invoke Codex"
                        ),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    code = TWEED.resume_command(
                        SimpleNamespace(run_id=run_id, answer=[], agent=True)
                    )
                saved = TWEED.load_run(run_id)
            self.assertEqual(code, 0)
            self.assertEqual(saved["state"], "completed")
            self.assertEqual(saved["commit"], committed)
            self.assertEqual(json.loads(output.getvalue())["commit"], committed)

    def test_finalizing_commit_adoption_rejects_correct_subject_with_wrong_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            before = git(root, "rev-parse", "HEAD")
            (root / "review.txt").write_text("expected repair\n")
            git(root, "add", "review.txt")
            expected_tree = git(root, "write-tree")
            (root / "review.txt").write_text("replacement repair\n")
            git(root, "add", "review.txt")
            git(root, "commit", "-m", "Review TST-1")
            state = {
                "pre_commit_head": before,
                "expected_commit_tree": expected_tree,
                "issue": {"identifier": "TST-1"},
            }
            with self.assertRaisesRegex(RuntimeError, "unexpected repository tree"):
                TWEED.recover_finalizing_commit(state, TWEED.PHASES["review"], root)

    def test_snapshot_is_frozen_once_into_separate_integrity_checked_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description(
                "problem", "Broken export", root, "CX", run_id
            )
            genesis = tweed_journal.parse_genesis(description)
            rca = tweed_journal.build_record(
                issue_identifier="TST-1",
                run_id=run_id,
                phase="root-cause",
                status="established",
                artifact_digest=tweed_journal.sha256_text(
                    "Status: established\n\nCause"
                ),
                predecessor_digest=genesis.digest,
                genesis_digest=genesis.digest,
                repository=str(root),
                base_commit=git(root, "rev-parse", "HEAD"),
                branch=None,
                commit=None,
                report="Status: established\n\nCause",
            )
            raw = {
                "id": "12345678-1234-4123-8123-123456789abc",
                "identifier": "TST-1",
                "url": "https://linear.test/TST-1",
                "title": "Fixture issue",
                "description": description,
                "updatedAt": "1",
                "comments": [
                    {
                        "id": rca.metadata["comment_id"],
                        "body": rca.comment,
                        "createdAt": "1",
                        "updatedAt": "1",
                        "editedAt": None,
                        "archivedAt": None,
                    }
                ],
            }
            raw["content_digest"] = TWEED.transport_content_digest(raw)
            raw["snapshot_digest"] = TWEED.transport_snapshot_digest(raw)
            issue = TWEED.validate_adapter_issue(root, raw)
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                manifest = TWEED.load_artifact_manifest(run_id)
                self.assertIn("request", manifest["artifacts"])
                self.assertIn("rca", manifest["artifacts"])
                self.assertIn("evidence", manifest["artifacts"])
                self.assertIn("linear-transport-snapshot", manifest["artifacts"])
                self.assertNotEqual(
                    manifest["artifacts"]["request"]["sha256"],
                    manifest["artifacts"]["rca"]["sha256"],
                )
                rca_path = (
                    TWEED.artifact_root(run_id) / manifest["artifacts"]["rca"]["path"]
                )
                rca_path.write_text("tampered")
                with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
                    TWEED.read_artifact(run_id, "rca")

    def test_run_state_restores_last_committed_manifest_after_partial_write(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.put_artifact(run_id, "request", "original")
                TWEED.save_run({"run_id": run_id, "state": "running"})
                committed = TWEED.load_run(run_id)["artifact_manifest_digest"]
                TWEED.put_artifact(run_id, "scope", "uncommitted")
                self.assertNotEqual(TWEED.manifest_digest(run_id), committed)
                TWEED.load_run(run_id)
                self.assertEqual(TWEED.manifest_digest(run_id), committed)
                with self.assertRaisesRegex(RuntimeError, "artifact is missing"):
                    TWEED.read_artifact(run_id, "scope")

    def test_phase_prompt_is_bounded_and_never_repeats_complete_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            large = "SENSITIVE-COMPLETE-PAYLOAD-" + ("x" * 50000)
            description = TWEED.intake_description("feature", large, root, "CX", run_id)
            scope = (
                "Status: scoped\n\n## Repository state\n\n- `README.md` → `"
                + TWEED.sha256_file(root / "README.md")
                + "`"
            )
            description += "\n" + TWEED.section_block("scope", scope)
            issue = make_issue("TST-1", description)
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                packet = TWEED.build_phase_packet(
                    run_id, issue, TWEED.PHASES["implement"]
                )
                prompt = TWEED.phase_prompt(issue, TWEED.PHASES["implement"], packet)
                manifest_ref = packet["artifact_manifest"]
                manifest_bytes = Path(manifest_ref["path"]).read_bytes()
            self.assertLess(len(prompt.encode()), 8192)
            self.assertNotIn("SENSITIVE-COMPLETE-PAYLOAD", prompt)
            self.assertIn("sha256", prompt)
            self.assertIn("artifacts/sha256", prompt)
            self.assertEqual(
                TWEED.hashlib.sha256(manifest_bytes).hexdigest(),
                manifest_ref["sha256"],
            )

    def test_scope_packet_teaches_repository_evidence_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description(
                "feature", "Add an export control", root, "CX", run_id
            )
            issue = make_issue("TST-1", description)
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                TWEED.put_artifact(run_id, "request", "Add an export control")
                packet = TWEED.build_phase_packet(run_id, issue, TWEED.PHASES["scope"])
                prompt = TWEED.phase_prompt(issue, TWEED.PHASES["scope"], packet)
            contract = packet["repository_evidence_contract"]
            self.assertIn("repository-relative path", contract)
            self.assertIn("never an absolute or .. path", contract)
            self.assertIn("artifact_manifest.path", contract)
            self.assertIn("input provenance only", contract)
            self.assertIn("repository_evidence_contract", prompt)
            self.assertLess(len(json.dumps(packet).encode()), 8192)
            self.assertLess(len(prompt.encode()), 12288)

    def test_scope_workflow_documents_evidence_contract_at_output_boundary(self):
        workflow = (ROOT / "workflows/scope-solution.md").read_text()
        self.assertIn("machine-parsed repository evidence", workflow)
        self.assertIn("use only repository-relative paths", workflow)
        self.assertIn("`artifact_manifest.path`", workflow)
        self.assertIn("never include packet, manifest, run-state", workflow)

    def test_retry_sync_reuses_artifacts_without_reasoning_or_refetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            state_home = Path(directory) / "runs"
            run_id = "tw_0123456789abcdef"
            description = TWEED.intake_description("feature", "CSV", root, "CX", run_id)
            issue = make_issue("TST-1", description)
            scope_report = (
                "Status: scoped\n\n## Repository state\n\n"
                f"- `README.md` → `{TWEED.sha256_file(root / 'README.md')}`"
            )
            record = TWEED.journal.build_record(
                issue_identifier=issue["identifier"],
                run_id=run_id,
                phase="scope",
                status="scoped",
                artifact_digest=TWEED.digest(scope_report),
                predecessor_digest=issue["revision"],
                genesis_digest=issue["genesis_digest"],
                repository=str(root),
                base_commit=git(root, "rev-parse", "HEAD"),
                branch=None,
                commit=None,
                report=scope_report,
            )
            store = Path(directory) / "linear.json"
            trace = Path(directory) / "trace"
            write_fake_linear(store, issue)
            env = {
                "TWEED_STATE_HOME": str(state_home),
                "TWEED_LINEAR_ADAPTER": str(FAKE_ADAPTER),
                "FAKE_LINEAR_STATE": str(store),
                "FAKE_LINEAR_TRACE": str(trace),
            }
            with patch.dict(os.environ, env):
                TWEED.freeze_linear_snapshot(run_id, issue, "workflow")
                TWEED.put_artifact(run_id, "linear-journal-record", record.comment)
                TWEED.save_run(
                    {
                        "run_id": run_id,
                        "state": "sync-pending",
                        "operation": "phase",
                        "phase": "scope",
                        "issue": TWEED.compact_issue(issue),
                        "metadata": TWEED.parse_metadata(description),
                        "repository": str(root),
                        "status": "scoped",
                        "summary": "done",
                        "expected_head_digest": issue["revision"],
                        "expected_snapshot_digest": issue["snapshot_digest"],
                        "expected_content_digest": issue["content_digest"],
                        "desired_head_digest": record.digest,
                        "comment_id": record.metadata["comment_id"],
                    }
                )
                with contextlib.redirect_stdout(io.StringIO()) as first_output:
                    result = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
                completed_state = TWEED.load_run(run_id)["state"]
                retry_state = TWEED.load_run(run_id)
                retry_state["state"] = "sync-blocked"
                TWEED.save_run(retry_state)
                with (
                    patch.object(
                        TWEED,
                        "append_linear_record",
                        side_effect=RuntimeError("offline again"),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as retry_output,
                ):
                    retry_result = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
                retry_saved = TWEED.load_run(run_id)["state"]
            self.assertEqual(result, 0, first_output.getvalue())
            self.assertEqual(trace.read_text().splitlines(), ["append-or-recover"])
            self.assertEqual(completed_state, "completed")
            self.assertEqual(retry_result, 8)
            self.assertEqual(
                json.loads(retry_output.getvalue())["state"], "sync-blocked"
            )
            self.assertEqual(retry_saved, "sync-blocked")

    def test_complete_evidence_cache_key_invalidates_each_declared_axis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            dependency = Path(directory) / "lockfile"
            configuration = Path(directory) / "config"
            dependency.write_text("one")
            configuration.write_text("one")
            with patch.dict(os.environ, {"DECLARED_TEST_INPUT": "one"}):
                key, document = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                )
                same, _ = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                )
                self.assertEqual(key, same)
                timed_key, _ = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                    execution_controls={"timeout_seconds": 1},
                )
                other_timeout, _ = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                    execution_controls={"timeout_seconds": 2},
                )
                self.assertNotEqual(timed_key, other_timeout)
                with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                    TWEED.save_cached_evidence(key, document, {"passed": True})
                    self.assertEqual(
                        TWEED.load_cached_evidence(key, document), {"passed": True}
                    )
                variants = [
                    (
                        ["python", "-m", "pytest"],
                        dependency,
                        configuration,
                        "one",
                        {"python": "3.14", "tool": "1"},
                        ["a" * 64],
                    ),
                    (
                        ["python", "-m", "unittest"],
                        dependency,
                        configuration,
                        "two",
                        {"python": "3.14", "tool": "1"},
                        ["a" * 64],
                    ),
                    (
                        ["python", "-m", "unittest"],
                        dependency,
                        configuration,
                        "one",
                        {"python": "3.14", "tool": "2"},
                        ["a" * 64],
                    ),
                    (
                        ["python", "-m", "unittest"],
                        dependency,
                        configuration,
                        "one",
                        {"python": "3.14", "tool": "1"},
                        ["b" * 64],
                    ),
                ]
                for argv, dep, config, env_value, versions, hashes in variants:
                    with patch.dict(os.environ, {"DECLARED_TEST_INPUT": env_value}):
                        changed, _ = TWEED.evidence_cache_key(
                            root,
                            argv,
                            dependency_paths=[dep],
                            configuration_paths=[config],
                            declared_environment=["DECLARED_TEST_INPUT"],
                            tool_versions=versions,
                            artifact_hashes=hashes,
                        )
                    self.assertNotEqual(key, changed)
                dependency.write_text("two")
                changed, _ = TWEED.evidence_cache_key(
                    root,
                    ["python", "-m", "unittest"],
                    dependency_paths=[dependency],
                    configuration_paths=[configuration],
                    declared_environment=["DECLARED_TEST_INPUT"],
                    tool_versions={"python": "3.14", "tool": "1"},
                    artifact_hashes=["a" * 64],
                )
                self.assertNotEqual(key, changed)

    def test_evidence_runner_reuses_only_a_complete_matching_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            dependency = Path(directory) / "lock"
            configuration = Path(directory) / "config"
            counter = Path(directory) / "counter"
            dependency.write_text("one")
            configuration.write_text("one")
            script = (
                "from pathlib import Path; p=Path(" + repr(str(counter)) + "); "
                "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
            )
            args = SimpleNamespace(
                repo=str(root),
                evidence_command=[sys.executable, "-c", script],
                tool_version=["python-command=3.14"],
                run_id=None,
                dependency=[str(dependency)],
                configuration=[str(configuration)],
                declared_env=[],
                no_dependencies=False,
                no_configuration=False,
                no_declared_env=True,
                no_artifacts=True,
                timeout=10,
            )
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                with contextlib.redirect_stdout(io.StringIO()) as first:
                    self.assertEqual(TWEED.evidence_command(args), 0)
                with contextlib.redirect_stdout(io.StringIO()) as second:
                    self.assertEqual(TWEED.evidence_command(args), 0)
                dependency.write_text("two")
                with contextlib.redirect_stdout(io.StringIO()) as third:
                    self.assertEqual(TWEED.evidence_command(args), 0)
            self.assertFalse(json.loads(first.getvalue())["cache_hit"])
            self.assertTrue(json.loads(second.getvalue())["cache_hit"])
            self.assertFalse(json.loads(third.getvalue())["cache_hit"])
            self.assertEqual(counter.read_text(), "2")

    def test_evidence_runner_rejects_omitted_or_contradictory_input_axes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            base = {
                "repo": str(root),
                "evidence_command": [sys.executable, "-c", "pass"],
                "tool_version": ["python-command=3.14"],
                "run_id": None,
                "dependency": [],
                "configuration": [],
                "declared_env": [],
                "no_dependencies": False,
                "no_configuration": True,
                "no_declared_env": True,
                "no_artifacts": True,
                "timeout": 10,
            }
            with self.assertRaisesRegex(RuntimeError, "dependency/lockfile"):
                TWEED.evidence_command(SimpleNamespace(**base))
            lock = Path(directory) / "lock"
            lock.write_text("one")
            contradictory = {
                **base,
                "dependency": [str(lock)],
                "no_dependencies": True,
            }
            with self.assertRaisesRegex(RuntimeError, "cannot combine"):
                TWEED.evidence_command(SimpleNamespace(**contradictory))

    def test_evidence_runner_never_caches_timeouts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            counter = Path(directory) / "counter"
            script = (
                "from pathlib import Path; import subprocess,sys,time; p=Path("
                + repr(str(counter))
                + "); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)']); "
                "time.sleep(2)"
            )
            args = SimpleNamespace(
                repo=str(root),
                evidence_command=[sys.executable, "-c", script],
                tool_version=["python-command=3.14"],
                run_id=None,
                dependency=[],
                configuration=[],
                declared_env=[],
                no_dependencies=True,
                no_configuration=True,
                no_declared_env=True,
                no_artifacts=True,
                timeout=0.2,
            )
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                started = time.monotonic()
                for _ in range(2):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(TWEED.evidence_command(args), 124)
                    self.assertFalse(json.loads(output.getvalue())["cacheable"])
                elapsed = time.monotonic() - started
            self.assertEqual(counter.read_text(), "2")
            self.assertLess(elapsed, 2)

    def test_evidence_runner_terminates_oversized_output_without_caching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            args = SimpleNamespace(
                repo=str(root),
                evidence_command=[
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(b'x' * 600000)",
                ],
                tool_version=["python-command=3.14"],
                run_id=None,
                dependency=[],
                configuration=[],
                declared_env=[],
                no_dependencies=True,
                no_configuration=True,
                no_declared_env=True,
                no_artifacts=True,
                timeout=10,
            )
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(TWEED.evidence_command(args), 125)
            result = json.loads(output.getvalue())
            self.assertFalse(result["cacheable"])
            self.assertEqual(result["stdout"], "")
            self.assertIn("byte limit", result["stderr"])

    def test_tracked_unchanged_inputs_reuse_content_hash_by_git_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            lock = root / "lockfile"
            lock.write_text("locked")
            git(root, "add", "lockfile")
            git(root, "commit", "-m", "lock")
            with patch.dict(
                os.environ, {"TWEED_STATE_HOME": str(Path(directory) / "state")}
            ):
                first = TWEED.cached_input_digest(root, lock)
                with patch.object(
                    TWEED,
                    "sha256_file",
                    side_effect=AssertionError("unchanged file must not be reread"),
                ):
                    second = TWEED.cached_input_digest(root, lock)
            self.assertEqual(first, second)

    def test_repository_identity_streams_untracked_files_and_binary_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            untracked = root / "large.bin"
            untracked.write_bytes(bytes(range(256)) * 8192)
            tracked = root / "tracked.bin"
            tracked.write_bytes(b"before")
            git(root, "add", "tracked.bin")
            git(root, "commit", "-m", "binary")
            tracked.write_bytes(bytes(reversed(range(256))) * 8192)
            expected_untracked = hashlib.sha256(untracked.read_bytes()).hexdigest()
            expected_diff = hashlib.sha256(
                subprocess.run(
                    ["git", "diff", "--binary", "HEAD"],
                    cwd=root,
                    capture_output=True,
                    check=True,
                ).stdout
            ).hexdigest()
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("repository hashing must stream files"),
            ):
                identity = TWEED.repository_cache_identity(root)
            self.assertEqual(identity["untracked"]["large.bin"], expected_untracked)
            self.assertEqual(identity["worktree_diff_sha256"], expected_diff)

    def test_legacy_run_migration_preserves_backup_and_imports_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "tw_0123456789abcdef"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": directory}):
                path = TWEED.state_path(run_id)
                path.parent.mkdir(parents=True)
                old = {
                    "run_id": run_id,
                    "state": "sync-pending",
                    "phase": "scope",
                    "report_markdown": "Status: scoped",
                    "workflow_text": "workflow",
                }
                path.write_text(json.dumps(old))
                loaded = TWEED.load_run(run_id)
                self.assertEqual(loaded["run_schema_version"], 3)
                self.assertTrue((path.parent / "run.v1.json").exists())
                self.assertEqual(
                    TWEED.read_artifact(run_id, "scope"), b"Status: scoped"
                )

    def test_pending_description_sync_migrates_explicitly_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            run_id = "tw_0123456789abcdef"
            state_home = Path(directory) / "state"
            with patch.dict(os.environ, {"TWEED_STATE_HOME": str(state_home)}):
                path = TWEED.state_path(run_id)
                path.parent.mkdir(parents=True)
                path.write_text(
                    json.dumps(
                        {
                            "run_schema_version": 2,
                            "run_id": run_id,
                            "state": "sync-blocked",
                            "operation": "phase",
                            "phase": "scope",
                            "repository": str(root),
                            "issue": {"identifier": "TST-1"},
                            "status": "scoped",
                        }
                    )
                )
                loaded = TWEED.load_run(run_id)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code = TWEED.retry_sync_command(
                        SimpleNamespace(run_id=run_id, agent=True)
                    )
            self.assertTrue((path.parent / "run.v2.json").exists())
            self.assertTrue(loaded["legacy_description_sync"])
            self.assertEqual(code, 8)
            self.assertIn("cannot be translated safely", output.getvalue())

    def test_issue_lock_rejects_same_host_parallel_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            with TWEED.issue_execution_lock(root, "TST-1"):
                with self.assertRaisesRegex(RuntimeError, "active for TST-1"):
                    with TWEED.issue_execution_lock(root, "TST-1"):
                        pass

    def test_skill_is_single_invocation_receipt_only_and_handles_all_states(self):
        skill = (ROOT / "skills/use-tweed/SKILL.md").read_text()
        self.assertIn("Run exactly one command", skill)
        self.assertIn("at most 4 KiB", skill)
        for state in (
            "created",
            "completed",
            "awaiting-input",
            "sync-pending",
            "sync-blocked",
            "failed",
            "resume",
            "retry-sync",
        ):
            self.assertIn(state, skill)
        self.assertIn("Do not ingest child output", skill)

    def test_efficiency_changes_preserve_review_and_ready_gates(self):
        review = (ROOT / "workflows/review.md").read_text()
        implementation = (ROOT / "workflows/implementation.md").read_text()
        requirements = (ROOT / "REQUIREMENTS.md").read_text()
        for axis in (
            "Simplicity, clarity, reuse, and scope fidelity",
            "Correctness and robustness",
            "Compatibility and integration",
            "Performance and resource use",
            "Verification quality",
        ):
            self.assertIn(axis, review)
        self.assertIn("three baseline axes", implementation)
        self.assertIn("non-authoring reviewer re-reviews", review)
        self.assertIn("zero unresolved material findings", review)
        self.assertIn("Ready-to-merge boundary", requirements)

    def test_no_model_powered_linear_transport_tasks_remain(self):
        source = (ROOT / "tweed").read_text()
        self.assertNotIn("Tweed read ", source)
        self.assertNotIn("Tweed update ", source)
        self.assertNotIn("Exact description snapshot", source)

    def test_cor3270_benchmark_is_immutable_and_fails_on_stable_drift(self):
        script = ROOT / "benchmarks/cor3270_stage1.py"
        fixture_path = ROOT / "benchmarks/fixtures/cor3270.json"
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["stable_replay_matches_fixture"])
        self.assertEqual(result["baseline"]["model_transport_task_count"], 15)
        with tempfile.TemporaryDirectory() as directory:
            fixture = json.loads(fixture_path.read_text())
            fixture["expected_replay"]["totals"]["new_prompt_bytes"] += 1
            drifted = Path(directory) / "fixture.json"
            drifted.write_text(json.dumps(fixture))
            mismatch = subprocess.run(
                [sys.executable, str(script), "--fixture", str(drifted)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn("drifted", mismatch.stderr)

    def test_agent_receipt_is_bounded(self):
        value = TWEED.receipt(
            run_id="tw_0123456789abcdef",
            state="completed",
            issue="ENG-1",
            phase="scope",
            status="scoped",
            summary="x" * 1000,
        )
        output = json.dumps(value, separators=(",", ":")).encode()
        self.assertLessEqual(len(value["summary"]), 400)
        self.assertLess(len(output), 4096)

    def test_agent_receipt_uses_bounded_utf8_for_binding_names(self):
        name = "\U0001f680" * 128
        value = TWEED.receipt(
            run_id="tw_0123456789abcdef",
            state="completed",
            summary=f"Created {name} / {name}",
            team=name,
            project=name,
        )
        with contextlib.redirect_stdout(io.StringIO()) as output:
            TWEED.emit(value, True)
        encoded = output.getvalue().encode("utf-8")
        self.assertLessEqual(len(encoded), 4096)
        self.assertIn(name, output.getvalue())


if __name__ == "__main__":
    unittest.main()
