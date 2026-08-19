import importlib.machinery
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "019fd385-da76-77f3-bd3a-2f1e4e49b936"


def load_runner():
    loader = importlib.machinery.SourceFileLoader(
        "bonaparte_runner", str(ROOT / "bonaparte")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RUNNER = load_runner()


def receipt(phase="rca", state="completed"):
    completed = state == "completed"
    result = RUNNER.COMPLETED_RESULTS[phase] if completed else "needs-input"
    git_phase = phase in {"implement", "review", "publish"}
    return {
        "phase": phase,
        "state": state,
        "issue": "COR-1",
        "linear_url": "https://linear.example/COR-1",
        "result": result,
        "summary": "bounded summary",
        "question": None if completed else "Which environment?",
        "next_action": None,
        "branch": "arya/cor-1" if completed and git_phase else None,
        "commit": "a" * 40 if completed and git_phase else None,
        "pull_request_url": (
            "https://github.example/pull/1" if completed and git_phase else None
        ),
        "remote_state_changed": False,
    }


class FakeThread:
    def __init__(self, identifier, final_receipt):
        self.id = identifier
        self.final_receipt = final_receipt
        self.calls = []

    def run(self, prompt, **options):
        self.calls.append((prompt, options))
        return SimpleNamespace(
            status=SimpleNamespace(value="completed"),
            error=None,
            final_response=json.dumps(self.final_receipt),
        )


class FakeCodex:
    def __init__(self, final_receipt, identifier=SESSION_ID):
        self.thread = FakeThread(identifier, final_receipt)
        self.starts = []
        self.resumes = []
        self.closed = False

    def thread_start(self, **options):
        self.starts.append(options)
        return self.thread

    def thread_resume(self, identifier, **options):
        self.resumes.append((identifier, options))
        return self.thread

    def close(self):
        self.closed = True


class BonaparteTests(unittest.TestCase):
    def test_fresh_phase_uses_sdk_structured_output_and_issue_only_context(self):
        client = FakeCodex(receipt("scope", "needs-input"))
        with mock.patch.object(RUNNER, "open_codex", return_value=client):
            result = RUNNER.run_phase(
                ROOT,
                "scope",
                "COR-1 Expected pull-request base: staging",
                model="gpt-example",
                reasoning="high",
            )

        self.assertEqual(result["resume_session_id"], SESSION_ID)
        self.assertEqual(len(client.starts), 1)
        self.assertFalse(client.resumes)
        self.assertTrue(client.closed)
        prompt, options = client.thread.calls[0]
        self.assertIn("Linear issue: COR-1", prompt)
        self.assertIn("Expected pull-request base: staging", prompt)
        self.assertIn("only cross-phase input", prompt)
        self.assertNotIn("Untrusted Linear handoff", prompt)
        self.assertEqual(options["output_schema"], RUNNER.RECEIPT_SCHEMA)
        self.assertEqual(options["effort"], "high")
        self.assertEqual(options["model"], "gpt-example")

    def test_resume_uses_same_sdk_thread_without_reloading_workflow(self):
        client = FakeCodex(receipt("rca"))
        with mock.patch.object(RUNNER, "open_codex", return_value=client):
            result = RUNNER.run_phase(
                ROOT,
                "rca",
                "Production only",
                resume_session_id=SESSION_ID,
            )

        self.assertFalse(client.starts)
        self.assertEqual(client.resumes[0][0], SESSION_ID)
        prompt = client.thread.calls[0][0]
        self.assertIn("Clarification answer", prompt)
        self.assertIn("Production only", prompt)
        self.assertNotIn("# Bonaparte Bug RCA", prompt)
        self.assertIsNone(result["resume_session_id"])

    def test_sdk_client_is_closed_when_turn_fails(self):
        client = FakeCodex(receipt())

        def fail(*args, **kwargs):
            raise RuntimeError("transport failed")

        client.thread.run = fail
        with (
            mock.patch.object(RUNNER, "open_codex", return_value=client),
            self.assertRaisesRegex(RuntimeError, "transport failed"),
        ):
            RUNNER.run_phase(ROOT, "rca", "COR-1")
        self.assertTrue(client.closed)

    def test_completed_delivery_requires_git_and_pull_request_provenance(self):
        invalid = receipt("implement")
        invalid["pull_request_url"] = None
        client = FakeCodex(invalid)
        with (
            mock.patch.object(RUNNER, "open_codex", return_value=client),
            self.assertRaisesRegex(RuntimeError, "missing its pull request"),
        ):
            RUNNER.run_phase(ROOT, "implement", "COR-1")

    def test_invalid_receipt_is_rejected(self):
        invalid = receipt()
        invalid["private"] = "not allowed"
        client = FakeCodex(invalid)
        with (
            mock.patch.object(RUNNER, "open_codex", return_value=client),
            self.assertRaisesRegex(RuntimeError, "invalid receipt"),
        ):
            RUNNER.run_phase(ROOT, "rca", "COR-1")

    def test_receipt_is_bounded(self):
        value = receipt()
        value["summary"] = "x" * 5000
        with self.assertRaisesRegex(RuntimeError, "4 KiB"):
            RUNNER.serialize_receipt(value)

    def test_parse_create_and_resume(self):
        repository, phase, phase_input, session, model, reasoning = RUNNER.parse(
            ["--repo", str(ROOT), "create", "feature", "Add", "widgets"]
        )
        self.assertEqual(repository, ROOT)
        self.assertEqual(phase, "create")
        self.assertIn("Kind: feature", phase_input)
        self.assertIsNone(session)
        self.assertIsNone(model)
        self.assertEqual(reasoning, "medium")

        parsed = RUNNER.parse(
            ["--repo", str(ROOT), "resume", "scope", SESSION_ID, "Production"]
        )
        self.assertEqual(parsed[1:4], ("scope", "Production", SESSION_ID))

    def test_parse_rejects_old_token_only_resume(self):
        with self.assertRaisesRegex(RuntimeError, "resume <phase>"):
            RUNNER.parse(["resume", SESSION_ID, "Continue"])

    def test_open_codex_marks_runtime_as_phase_child(self):
        fake_module = SimpleNamespace()
        codex = mock.Mock(return_value="client")
        config = mock.Mock(return_value="config")
        fake_module.Codex = codex
        fake_module.CodexConfig = config
        with mock.patch.dict("sys.modules", {"openai_codex": fake_module}):
            self.assertEqual(RUNNER.open_codex(), "client")
        environment = config.call_args.kwargs["env"]
        self.assertEqual(environment[RUNNER.PHASE_CHILD_ENV], "1")

    def test_main_emits_one_receipt(self):
        output = io.StringIO()
        expected = receipt()
        parsed = (ROOT, "rca", "COR-1", None, None, "medium")
        with (
            mock.patch.object(RUNNER, "parse", return_value=parsed),
            mock.patch.object(RUNNER, "run_phase", return_value=expected),
            mock.patch.object(RUNNER.sys, "stdout", output),
        ):
            self.assertEqual(RUNNER.main(), 0)
        emitted = json.loads(output.getvalue())
        self.assertEqual(emitted, expected)


if __name__ == "__main__":
    unittest.main()
