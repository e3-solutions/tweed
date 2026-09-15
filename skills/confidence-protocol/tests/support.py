"""Small explicit fixtures; no TestCase lifecycle or shared mutable documents."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile


SCRIPT = Path(__file__).parents[1] / "scripts" / "confidence.py"


def load_confidence(name):
    """Give each test module a fresh runtime module for isolated patching."""
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fixture_workspace(directory, workspaces, add_cleanup):
    """Create one committed real source tree per evidence directory."""
    if directory not in workspaces:
        temporary = tempfile.TemporaryDirectory(prefix="confidence-fixture-")
        add_cleanup(temporary.cleanup)
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "source.txt").write_text("stable fixture source\n")
        subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=Confidence Test",
             "-c", "user.email=confidence@example.test", "commit", "-q", "-m", "fixture"],
            check=True,
        )
        workspaces[directory] = root
    return workspaces[directory]


def write_run(confidence, directory, workspace, run_id="tests", exit_code=0):
    """Synthetic record for validator tests, bound to a real committed tree."""
    fingerprint = confidence.git_workspace_fingerprint(workspace, directory)
    if fingerprint is None:
        raise AssertionError("fixture workspace must have known source binding")
    log_path = directory / "runs" / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(b"test output\n")
    confidence.write_json(directory / "runs" / f"{run_id}.json", {
        "version": 2, "id": run_id, "argv": ["python3", "-m", "unittest"],
        "cwd": str(workspace.resolve()), "workspace_start": fingerprint, "workspace": fingerprint,
        "started_at": "2026-08-26T01:00:00.000000Z", "ended_at": "2026-08-26T01:00:01.000000Z",
        "exit_code": exit_code, "log": f"runs/{run_id}.log", "log_sha256": confidence.sha256_file(log_path),
    })


def valid_documents(confidence):
    contract = confidence.initial_contract("Invite users", "standard", "feature")
    contract["intent"].update(
        {
            "goal": "A team owner can invite a user.",
            "must_happen": ["A valid invitation is sent."],
            "must_not_happen": ["A non-owner cannot invite users."],
        }
    )
    contract["proof_obligations"][0].update(
        {
            "claim": "Only owners can invite users.",
            "verification": "Run the authorization integration test.",
        }
    )
    report = confidence.initial_report("Invite users", "standard")
    report.update(
        {
            "outcome": "The invitation flow works for owners.",
            "rollback": "Revert the invitation change.",
        }
    )
    report["evidence"][0].update(
        {
            "status": "pass",
            "details": "The integration test passed.",
            "artifacts": ["tests/invitations.test.ts"],
            "run_ids": ["tests"],
            "diagnostic_run_ids": [],
        }
    )
    report["tests"]["passed"] = ["npm test -- invitations"]
    report["simplicity"].update(
        {
            "code_gate": "pass",
            "test_gate": "pass",
            "notes": "The change uses the existing authorization path.",
        }
    )
    report["review"].update(
        {
            "required": False,
            "reason": "The test fixture is local and does not cross a review boundary.",
        }
    )
    return contract, report


def write_documents(confidence, directory):
    contract, report = valid_documents(confidence)
    confidence.write_json(directory / "contract.json", contract)
    confidence.write_json(directory / "report.json", report)


def run_cli(*args, **options):
    """Run the real CLI; callers keep process policy and argument choices explicit."""
    settings = {"capture_output": True, "text": True}
    settings.update(options)
    return subprocess.run([sys.executable, str(SCRIPT), *args], **settings)
