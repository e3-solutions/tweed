import json
import unittest
from pathlib import Path
from unittest import mock

import bonaparte_linear as linear


class FakeDriver:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.requests = []
        self.closed = False
        self.process = mock.Mock()
        self.process.stdin = mock.Mock()

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "initialize":
            return {}
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        tool = params["tool"]
        if tool == "get_issue":
            content = {"title": "Example"}
        else:
            content = next(self.pages)
        return {"isError": False, "structuredContent": content, "content": []}

    def close(self, *, failed):
        self.closed = True


class LinearIntakeTests(unittest.TestCase):
    def test_reads_every_comment_page_through_the_shared_driver(self):
        driver = FakeDriver(
            [
                {"comments": [{"body": "one"}], "hasNextPage": True, "cursor": "c2"},
                {"comments": [{"body": "two"}], "hasNextPage": False},
            ]
        )
        with mock.patch.object(linear, "AppServerPhaseDriver", return_value=driver):
            issue, comments = linear.call_linear(Path("/repo"), "COR-1")

        self.assertEqual(issue, {"title": "Example", "identifier": "COR-1"})
        self.assertEqual(comments, [{"body": "one"}, {"body": "two"}])
        comment_calls = [
            params
            for method, params in driver.requests
            if method == "mcpServer/tool/call" and params["tool"] == "list_comments"
        ]
        self.assertNotIn("cursor", comment_calls[0]["arguments"])
        self.assertEqual(comment_calls[1]["arguments"]["cursor"], "c2")
        driver.process.stdin.write.assert_called_once_with(
            '{"method":"initialized","params":{}}\n'
        )
        self.assertTrue(driver.closed)

    def test_reads_latest_exact_bounded_phase_artifact_without_writes(self):
        comments = [
            {"id": "a", "body": "## Phase\n\nold", "createdAt": "1", "parentId": None},
            {"id": "z", "body": "## Phase\n\nnew", "createdAt": "2", "parentId": None},
            {"id": "reply", "body": "## Phase\n\nreply", "createdAt": "3", "parentId": "a"},
            {"id": "quote", "body": "## Phase\n\nquote", "createdAt": "4", "parentId": None, "quotedText": "anchor"},
            {"id": "near", "body": "## Phase \n\nnear", "createdAt": "5", "parentId": None},
        ]
        with mock.patch.object(linear, "call_linear", return_value=({}, comments)):
            latest = linear.read_linear_phase_artifact(Path("/repo"), "COR-1", "## Phase")
            exact = linear.read_linear_phase_artifact(
                Path("/repo"), "COR-1", "## Phase", comment_id="a"
            )

        self.assertEqual(latest, {"id": "z", "body": "## Phase\n\nnew", "createdAt": "2"})
        self.assertEqual(exact, {"id": "a", "body": "## Phase\n\nold", "createdAt": "1"})

    def test_phase_artifact_rejects_invalid_selectors_and_oversized_body(self):
        for header in ("", "one\ntwo", "nul\0value"):
            with self.subTest(header=header), self.assertRaises(ValueError):
                linear.read_linear_phase_artifact(Path("/repo"), "COR-1", header)
        oversized = [{
            "id": "a",
            "body": "## Phase\n" + "x" * linear.LINEAR_ARTIFACT_MAX_BYTES,
            "createdAt": "1",
            "parentId": None,
        }]
        with (
            mock.patch.object(linear, "call_linear", return_value=({}, oversized)),
            self.assertRaisesRegex(RuntimeError, "exceeds"),
        ):
            linear.read_linear_phase_artifact(Path("/repo"), "COR-1", "## Phase")

    def test_text_tool_results_are_decoded_and_driver_closes_on_failure(self):
        driver = FakeDriver([])
        driver.request = mock.Mock(
            side_effect=[
                {},
                {"thread": {"id": "thread-1"}},
                {
                    "isError": False,
                    "structuredContent": None,
                    "content": [
                        {"type": "text", "text": json.dumps({"identifier": "COR-1"})}
                    ],
                },
                {
                    "isError": False,
                    "structuredContent": {"comments": [], "hasNextPage": True},
                    "content": [],
                },
            ]
        )

        with (
            mock.patch.object(linear, "AppServerPhaseDriver", return_value=driver),
            self.assertRaisesRegex(RuntimeError, "invalid cursor"),
        ):
            linear.call_linear(Path("/repo"), "COR-1")

        self.assertTrue(driver.closed)
