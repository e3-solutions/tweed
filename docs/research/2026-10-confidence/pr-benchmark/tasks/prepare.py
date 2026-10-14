"""Recreate pinned PR replay snapshots and sealed acceptance controls.

Run outside solver trials. Source snapshots and raw logs belong in an ignored
output directory. Solver processes receive only source_directory and prompt.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent


def tree_sha256(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            data = ("symlink:" + os.readlink(path)).encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(str(path.lstat().st_mode & 0o777).encode() + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def export_snapshot(repository, commit, destination, fetch_missing):
    available = subprocess.run(["git", "-C", str(repository), "cat-file", "-e",
                                commit + "^{commit}"], capture_output=True)
    if available.returncode:
        if not fetch_missing:
            raise ValueError(f"Missing pinned commit {commit}; use --fetch-missing")
        subprocess.run(["git", "-C", str(repository), "fetch", "origin", commit], check=True)
    if destination.exists():
        raise ValueError(f"Refusing to overwrite {destination}; select a fresh output directory")
    destination.mkdir(parents=True)
    data = subprocess.check_output(["git", "-C", str(repository), "archive", commit])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            resolved = (destination / member.name).resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise ValueError("Archive member escapes snapshot")
        archive.extractall(destination, filter="data")
    for name in (".git", ".claude", ".codex", ".agents", "AGENTS.md", "CLAUDE.md"):
        path = destination / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for path in destination.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path)


def selected_test_module(path, names):
    tree = ast.parse(path.read_text())
    test_ids = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        node.body = [member for member in node.body
                     if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                     or not member.name.startswith("test_") or member.name in names]
        if not node.body:
            node.body = [ast.Pass()]
        test_ids.extend(f"tests.{path.stem}.{node.name}.{member.name}"
                        for member in node.body
                        if isinstance(member, ast.FunctionDef) and member.name in names)
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare))]
    return ast.unparse(tree) + "\n", test_ids


def control(task, side):
    started = time.monotonic()
    argv = [sys.executable, "-B", task["oracle_script"], "--workspace",
            task[side + "_snapshot"]]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    path = Path(task["oracle_script"]).parent.parent / ("control-" + side + ".txt")
    path.write_text(result.stdout + result.stderr)
    return {"side": side, "exit_code": result.returncode,
            "seconds": time.monotonic() - started, "log": str(path),
            "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare(args):
    selection = json.loads((HERE / "selection.json").read_text())
    selectors = json.loads((HERE / "selectors.json").read_text())
    output = Path(args.output).resolve()
    repository = Path(args.repository).resolve()
    tasks = []
    for public in selection["tasks"]:
        number = public["task_id"].removeprefix("tweed-pr")
        root = output / ("pr-" + number)
        base, head = root / "base", root / "head"
        export_snapshot(repository, public["base_sha"], base, args.fetch_missing)
        export_snapshot(repository, public["head_sha"], head, args.fetch_missing)
        if tree_sha256(base) != public["source_sha256"]:
            raise ValueError(f"Base snapshot hash mismatch: {public['task_id']}")
        if tree_sha256(head) != public["head_source_sha256"]:
            raise ValueError(f"Head snapshot hash mismatch: {public['task_id']}")
        oracle = root / "oracle"
        modules = oracle / "modules"
        modules.mkdir(parents=True)
        module_selection = dict(selectors[number])
        if "test_phase_runtime.py" in module_selection and "test_bonaparte.py" not in module_selection:
            module_selection["test_bonaparte.py"] = []
        test_ids = []
        for filename, names in module_selection.items():
            source, ids = selected_test_module(head / "tests" / filename, names)
            if number == "40" and filename == "test_bonaparte.py":
                source = source.replace("RUNNER.DISABLE_SOFT_PHASE_BUDGET", "_disable_budget_choice()")
                source += ("\n\ndef _disable_budget_choice():\n"
                           "    with mock.patch.object(sys, \"argv\", [\"bonaparte\", \"--repo\", str(ROOT), \"--no-soft-phase-budget\", \"scope\", \"COR-1\"]):\n"
                           "        return RUNNER.parse()[-1]\n")
            (modules / filename).write_text(source)
            test_ids.extend(ids)
        if number == "32":
            shutil.copyfile(HERE / "event_routing_oracle.py", modules / "test_independent.py")
            test_ids.extend([
                "tests.test_independent.EventRoutingEdges.test_foreign_completion_never_establishes_current_turn_terminal",
                "tests.test_independent.EventRoutingEdges.test_matching_and_legacy_completion_preserve_turn_payload",
                "tests.test_independent.EventRoutingEdges.test_foreign_messages_cannot_replace_coordinator_receipt",
            ])
        if number == "40":
            shutil.copyfile(HERE / "budget_cli_oracle.py", modules / "test_budget_cli.py")
            test_ids.extend([
                "tests.test_budget_cli.BudgetCLIEdges.test_disabled_flag_and_environment_deliver_disabled_execution",
                "tests.test_budget_cli.BudgetCLIEdges.test_explicit_numeric_budget_overrides_environment",
                "tests.test_budget_cli.BudgetCLIEdges.test_invalid_budgets_never_start_execution",
            ])
        for number_key, filename, module_name, case_names in [
            ("31", "resumability_cli_oracle.py", "test_resumability.py", [
                "tests.test_resumability.ResumabilityCLIEdges.test_soft_guard_failure_has_durable_cli_continuation",
                "tests.test_resumability.ResumabilityCLIEdges.test_interrupt_has_exit130_receipt_and_durable_continuation",
                "tests.test_resumability.ResumabilityCLIEdges.test_unrelated_transport_failure_does_not_claim_continuation"]),
            ("39", "lifecycle_oracle.py", "test_lifecycle.py", [
                "tests.test_lifecycle.NativeLifecycleEdges.test_terminal_phase_updates_owned_children_and_archives_root",
                "tests.test_lifecycle.NativeLifecycleEdges.test_child_cleanup_failure_still_attempts_root_archive_and_reaps"]),
        ]:
            if number == number_key:
                shutil.copyfile(HERE / filename, modules / module_name)
                test_ids.extend(case_names)
        if number == "34":
            path = modules / "test_handoff.py"
            source = path.read_text().replace(
                "self.assertEqual(handoff['context'], {'existing': published['body'], 'review': review['body'], 'existing_comment_id': 'STALE-PUBLISH'})",
                "self.assertEqual({key: handoff['context'].get(key) for key in ('existing', 'review', 'existing_comment_id')}, {'existing': published['body'], 'review': review['body'], 'existing_comment_id': 'STALE-PUBLISH'})")
            path.write_text(source)
        if number == "35":
            path = modules / "test_installation.py"
            source = path.read_text().replace("self.assertRaisesRegex(RuntimeError, 'tag v1.1.0 moved')", "self.assertRaises(RuntimeError)")
            source = source.replace("self.assertIn('release is missing workflows/autoresearch-critic.md', result.stderr)", "self.assertTrue(result.stderr.strip())")
            source = source.replace("self.assertIn('returned non-zero exit status', result.stderr)", "self.assertTrue(result.stderr.strip())")
            path.write_text(source)
        (oracle / "oracle.json").write_text(json.dumps({"task_id": public["task_id"],
                                                        "test_ids": test_ids,
                                                        "production_paths": public["production_paths"]}, indent=2))
        shutil.copyfile(HERE / "oracle_runner.py", oracle / "evaluate.py")
        if tree_sha256(oracle) != public["oracle_sha256"]:
            raise ValueError(f"Oracle hash mismatch; use the pinned builder runtime: {public['task_id']}")
        task = dict(public, source_directory=str(base), base_snapshot=str(base),
                    head_snapshot=str(head), base_commit=public["base_sha"],
                    oracle_script=str(oracle / "evaluate.py"),
                    oracle_script_sha256=hashlib.sha256((oracle / "evaluate.py").read_bytes()).hexdigest(),
                    test_commands=public["test_commands"])
        task["prompt"] = public["solver_prompt"]
        if args.controls:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda side: control(task, side), ("base", "head")))
            task["controls"] = {result["side"]: result for result in results}
            task["admitted"] = (task["controls"]["base"]["exit_code"] == 1
                                and task["controls"]["head"]["exit_code"] == 0)
            if not task["admitted"]:
                raise ValueError(f"RED/GREEN control failed: {public['task_id']}")
        (root / "task.json").write_text(json.dumps(task, indent=2))
        tasks.append(task)
    manifest = {"schema_version": 1, "tasks": tasks,
                "builder_python": sys.version.split()[0]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"manifest": str(output / "manifest.json"),
                      "task_ids": [task["task_id"] for task in tasks]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".", help="Local clone containing pinned public commits")
    parser.add_argument("--output", required=True, help="Fresh ignored directory, never a solver workspace")
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--controls", action="store_true")
    prepare(parser.parse_args())
