#!/usr/bin/env python3
"""Continue only never-started original trials after coordinator interruption.

The immutable original runner and grader remain the source of execution and
grading behavior. Existing trial directories are never retried or replaced.
This coordinator records interruption accounting separately from raw receipts.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

RUNNER_SHA = "1f5e9ab2e5f0823a34c8f637ae08b4b3e7e1d1ac7bbbf5aab64ab79c95288fb8"
GRADER_SHA = "bcec860d709ddbe3c3566fb7bcdc86805b4a3e5c69131167b7743c91cbb2a007"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def load_module(path, name, expected):
    if sha(path) != expected:
        raise ValueError("Immutable source hash changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(study, specs):
    inventory = []
    for spec in specs:
        directory = study / "trials" / spec["trial_id"]
        if directory.is_symlink():
            raise ValueError("Symlink trial directory refused")
        receipt = directory / "receipt.json"
        state = ("completed_receipt" if receipt.exists() else
                 "interrupted_no_receipt" if directory.exists() else "never_started")
        files = []
        if directory.exists():
            for path in sorted(directory.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Symlink existing artifact refused")
                if path.is_file():
                    files.append({"path": str(path.relative_to(directory)), "sha256": sha(path)})
        inventory.append({"trial_id": spec["trial_id"], "state": state,
                          "request_sha256": spec["request_sha256"], "files": files,
                          "model_emission": "unknown" if state == "interrupted_no_receipt" else None})
    return inventory


def check_preservation(study, inventory):
    """Retain solver evidence; permit outputs of a newly completed first grade.

    The grading watcher can create stdout/stderr before its completed grade
    receipt exists. Those two files are mutable until that first grade closes.
    Existing completed grades and every solver artifact remain immutable.
    """
    violations, grading_outputs = [], []
    for row in inventory:
        completed_grade = any(item["path"] == "graded-receipt.json" for item in row["files"])
        for artifact in row["files"]:
            path = study / "trials" / row["trial_id"] / artifact["path"]
            if path.is_file() and not path.is_symlink() and sha(path) == artifact["sha256"]:
                continue
            detail = {"trial_id": row["trial_id"], "path": artifact["path"]}
            if (row["state"] == "completed_receipt" and not completed_grade
                    and artifact["path"] in {"grader.stdout", "grader.stderr"}
                    and path.is_file() and not path.is_symlink()):
                grading_outputs.append({**detail, "reason": "First grade was pending at inventory seal"})
            else:
                violations.append(detail)
    return violations, grading_outputs


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.study = args.study.resolve()
    args.manifest = args.manifest.resolve()
    runner = load_module(here / "runner.py", "frozen_original_runner", RUNNER_SHA)
    grader = load_module(here / "grading_adapter.py", "frozen_original_grader", GRADER_SHA)
    registered = json.loads((here / "registration.json").read_text())
    version = subprocess.check_output(["claude", "--version"], text=True).strip()
    if version.split()[0] != registered["runtime"]["claude_code"]:
        raise ValueError("Claude Code version differs from original registration")
    if sys.version.split()[0] != registered["runtime"]["python"]:
        raise ValueError("Python version differs from original registration")
    verified = SimpleNamespace(study=args.study, manifest=args.manifest,
        protocol=here / "protocol.json", registration=here / "registration.json",
        runner=here / "runner.py", repository=here.parents[3])
    frozen, tasks, arms, _, _ = grader.verify_inputs(verified)
    inventory = classify(args.study, frozen["trials"])
    selected = [spec for spec, row in zip(frozen["trials"], inventory)
                if row["state"] == "never_started"]
    summary = {state: sum(row["state"] == state for row in inventory)
               for state in ("completed_receipt", "interrupted_no_receipt", "never_started")}
    print(json.dumps({"classification": summary, "selected": [s["trial_id"] for s in selected]}), flush=True)
    if not args.execute:
        return
    record = args.study / "resumption"
    record.mkdir(exist_ok=True)
    # The seal is exclusive: a repeated launch cannot silently retry any work.
    descriptor = os.open(record / "inventory.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    seal = {"schema_version": 1, "at_utc": now(), "reason": "User-turn interruption stopped coordinator",
        "supervisor_sha256": sha(Path(__file__)), "runner_sha256": RUNNER_SHA,
        "grader_sha256": GRADER_SHA, "claude_code": version, "python": sys.version,
        "scheduled": len(inventory), "classification": summary, "inventory": inventory,
        "selected_trial_ids": [s["trial_id"] for s in selected], "concurrency": 3,
        "rule": "Never retry any preexisting trial directory; interrupted receipts remain unknown",
        "grading_feedback_to_solvers": False}
    with os.fdopen(descriptor, "w") as file:
        file.write(json.dumps(seal, indent=2) + "\n")
    runner.sandbox_check(args.study)
    protocol = json.loads(verified.protocol.read_text())
    event_lock = threading.Lock()

    def event(value):
        with event_lock:
            with (record / "events.jsonl").open("a") as file:
                file.write(json.dumps({"at_utc": now(), **value}) + "\n")

    def execute(spec):
        directory = args.study / "trials" / spec["trial_id"]
        # Preserve no-retry semantics even if another coordinator appears later.
        directory.mkdir(parents=True, exist_ok=False)
        event({"trial_id": spec["trial_id"], "state": "started", "request_sha256": spec["request_sha256"]})
        try:
            result = runner.run_trial(spec, tasks[spec["task_id"]], arms[spec["arm_id"]],
                args.study, frozen["protocol_sha256"], protocol["packages"])
        except Exception as error:
            result = {"schema_version": 1,
                **{key: spec[key] for key in ("trial_id", "task_id", "arm_id", "repeat")},
                "status": "harness_failed", "declared_complete": None, "grade": None,
                "error": f"{type(error).__name__}: {error}"}
            # Identical failure receipt semantics to the original coordinator.
            if (directory / "receipt.json").exists():
                raise ValueError("Refuse replacing an existing receipt")
            atomic_json(directory / "receipt.json", result)
        event({"trial_id": spec["trial_id"], "state": "receipt", "status": result["status"],
               "raw_receipt_sha256": sha(directory / "receipt.json")})
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(execute, spec): spec for spec in selected}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(json.dumps({"trial_id": result["trial_id"], "status": result["status"],
                              "cost": result.get("total_cost_usd")}), flush=True)
    final = classify(args.study, frozen["trials"])
    # Verify all preexisting material retained, including raw and graded files.
    violations, grading_outputs = check_preservation(args.study, inventory)
    atomic_json(record / "completion.json", {"at_utc": now(), "scheduled": len(final),
        "completed_receipts": sum(row["state"] == "completed_receipt" for row in final),
        "missing_receipt_ids": [row["trial_id"] for row in final if row["state"] != "completed_receipt"],
        "retained_prior_material": not violations, "preservation_violations": violations,
        "first_grade_output_changes": grading_outputs,
        "runner_sha256": sha(here / "runner.py"), "grader_sha256": sha(here / "grading_adapter.py")})
    if violations:
        raise ValueError("Preexisting artifacts changed; inspect preservation violations")


if __name__ == "__main__":
    main()
