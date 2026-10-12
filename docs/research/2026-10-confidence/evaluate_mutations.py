#!/usr/bin/env python3
"""Run bounded refusal-oracle mutations in disposable copies of the actual CLI.

This measures whether selected regression tests reject removed guards. It does not
measure model task accuracy. The control must pass; every mutant must fail by test
assertion rather than syntax, import, or runner failure. No model calls or network.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "confidence-protocol"
CASES = [
    ("dependency_graph", "validate_dependency_graph",
     "test_dependency_frontier.DependencyFrontierTest.test_cycle_refuses_with_explanation"),
    ("review_integrity", "validate_review_records",
     "test_review_provenance.ReviewProvenanceTest.test_review_artifact_modification_is_detected"),
    ("source_freshness", "validate_supporting_workspace",
     "test_dependency_frontier.DependencyFrontierTest.test_stale_upstream_cannot_enable_fresh_dependent_pass_or_frontier"),
    ("review_policy", "completion_errors",
     "test_review_provenance.ReviewProvenanceTest.test_opted_in_report_cannot_delete_records"),
]


def run_case(label, function, test, mutate):
    with tempfile.TemporaryDirectory(prefix="confidence-mutation-") as scratch:
        package = Path(scratch) / "skills" / "confidence-protocol"
        shutil.copytree(SKILL / "scripts", package / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SKILL / "tests", package / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        script = package / "scripts" / "confidence.py"
        if mutate:
            tree = ast.parse(script.read_text())
            owner = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
            if function == "completion_errors":
                gate = next(node for node in owner.body if isinstance(node, ast.If)
                            and "records_required" in ast.unparse(node.test))
                gate.test = ast.Constant(False)
            else:
                owner.body = [ast.Return(ast.List(elts=[], ctx=ast.Load()))]
            script.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GIT_", "CONFIDENCE_"))}
        env.update(PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run([sys.executable, "-B", "-m", "unittest", test, "-v"],
                                cwd=package / "tests", env=env, capture_output=True,
                                text=True, timeout=90)
        output = result.stdout + result.stderr
        assertion_failure = "AssertionError" in output and "FAILED (failures=" in output
        accepted = result.returncode == 0 if not mutate else result.returncode != 0 and assertion_failure
        return {"case": label, "mutation": mutate, "test": test,
                "exit_code": result.returncode, "oracle_expectation_met": accepted,
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "output": output}


def main():
    results = [run_case(label, function, test, mutate)
               for label, function, test in CASES for mutate in (False, True)]
    print(json.dumps({"schema": 1, "scope": "four targeted guard-removal mutations, eight real subprocess trials",
                      "results": results, "pass": all(item["oracle_expectation_met"] for item in results)}, indent=2))
    return 0 if all(item["oracle_expectation_met"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
