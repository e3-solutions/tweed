#!/usr/bin/env python3
"""One-time independently confined grading of the separately registered cohort."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hybrid_grade_runner', HERE / 'hybrid_runner.py')
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grade(path, request, task, package_sha):
    raw = hybrid.read(path)
    reasons = list(raw.get('harness_invalid_reasons', []))
    for key in ('trial_id', 'task_id', 'arm_id', 'repeat', 'request_sha256'):
        if raw.get(key) != request[key]:
            reasons.append('request_binding_' + key)
    source = Path(task['base_snapshot'])
    oracle = Path(task['oracle_script'])
    result = path.parent / 'result_snapshot'
    observed = None
    outcome = {}
    violations = []
    try:
        if hybrid.grader.curation_tree(source) != task['source_sha256'] or hybrid.base.tree_digest(source) != raw['source_sha256']:
            reasons.append('source_material_mismatch')
        if hybrid.grader.curation_tree(oracle.parent) != task['oracle_sha256'] or sha(oracle) != task['oracle_script_sha256']:
            reasons.append('oracle_material_mismatch')
        if raw.get('toolkit_sha256') != package_sha:
            reasons.append('toolkit_material_mismatch')
        if raw.get('artifact_error'):
            outcome['artifact_invalid'] = True
        else:
            if hybrid.grader.raw_tree(result) != raw.get('result_sha256'):
                reasons.append('result_digest_mismatch')
            if sha(path.parent / 'submitted.patch') != raw.get('patch_sha256'):
                reasons.append('patch_digest_mismatch')
            for relative in task['production_paths']:
                if (source / relative).is_file() and not (result / relative).is_file():
                    reasons.append('unsupported_production_deletion:' + relative)
            violations = hybrid.grader.scope_diff(source, result, task['production_paths'])
            if violations != raw.get('scope_violations', []):
                reasons.append('scope_receipt_mismatch')
            if not reasons:
                outcome = hybrid.grader.invoke_oracle(oracle, result, path.parent)
                observed = outcome['oracle_passed']
    except Exception as error:
        reasons.append('grade_integrity_' + type(error).__name__ + ':' + str(error))
    expected_roles = ['test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair']
    stages = raw.get('stages', [])
    if [s.get('role') for s in stages] != expected_roles:
        reasons.append('stage_roles_missing_or_reordered')
    for stage in stages:
        assigned = request['peer_model'] if stage.get('role') in ('test_designer', 'adversarial_reviewer') else request['main_model']
        expected_id = 'gpt-6-astra' if assigned == 'astra' else 'claude-opus-5-5'
        if stage.get('status', '').startswith('skipped_'):
            continue
        if stage.get('model_requested') != expected_id or stage.get('requested_effort') != 'medium':
            reasons.append(stage.get('role', 'unknown') + ':model_or_effort_request_mismatch')
        models = stage.get('observed_assistant_models', stage.get('observed_models', []))
        if any(m != expected_id for m in models):
            reasons.append(stage.get('role', 'unknown') + ':observed_model_mismatch')
        if stage.get('unexpected_native_calls') or stage.get('native_guard_violated'):
            reasons.append(stage.get('role', 'unknown') + ':unexpected_native_calls')
        if stage.get('stream_changed_during_cleanup'):
            reasons.append(stage.get('role', 'unknown') + ':stream_changed_during_cleanup')
        final = hybrid.terminal_value(stage)
        strict_declared = final['complete'] if final is not None else None
        if stage.get('declared_complete') is not strict_declared:
            reasons.append(stage.get('role', 'unknown') + ':terminal_receipt_mismatch')
        if stage.get('role') in ('test_designer', 'adversarial_reviewer'):
            if stage.get('source_sha256_at_launch') != stage.get('source_sha256_after'):
                reasons.append(stage['role'] + ':readonly_source_drift')
        if stage.get('source_integrity_error') or stage.get('review_artifact_error'):
            reasons.append(stage.get('role', 'unknown') + ':source_or_artifact_integrity')
    final = hybrid.terminal_value(stages[-1]) if len(stages) == 4 else None
    declared = final['complete'] if final is not None else None
    if raw.get('declared_complete') is not declared:
        reasons.append('terminal_declaration_mismatch')
    costs, subtotal = hybrid.base.known_cost(stages)
    if raw.get('total_cost_usd') != costs or raw.get('known_cost_subtotal') != subtotal:
        reasons.append('cost_aggregation_mismatch')
    if raw.get('cost_known') is not (costs is not None):
        reasons.append('cost_known_mismatch')
    if raw.get('over_budget') is True or raw.get('wall_seconds', 0) > 600:
        reasons.append('aggregate_wall_budget_exceeded')
    passed = False if violations or raw.get('artifact_error') else observed
    missing = [s.get('role') for s in stages if s.get('role') in ('test_designer', 'adversarial_reviewer')
               and (s.get('declared_complete') is not True or (hybrid.terminal_value(s) or {}).get('remaining'))]
    row = {k: raw.get(k) for k in ('schema_version', 'trial_id', 'task_id', 'arm_id', 'repeat',
            'status', 'wall_seconds', 'total_cost_usd', 'known_cost_subtotal', 'cost_known',
            'human_interventions', 'request_sha256', 'source_sha256', 'patch_sha256', 'result_sha256', 'over_budget')}
    row.update(passed=passed, oracle_passed=observed,
        false_completion=(declared is True and observed is False) if declared is not None and observed is not None else None,
        declared_complete=declared, main_model=request['main_model'], peer_model=request['peer_model'],
        harness_invalid=bool(reasons), harness_invalid_reasons=reasons,
        missing_required_reviews=missing,
        truthful_success=passed is True and not reasons and declared is True and not missing and not final.get('remaining'),
        stage_usage=[{k: s.get(k) for k in ('role', 'backend', 'model_requested', 'model_attribution',
            'requested_effort', 'observed_assistant_models', 'observed_models', 'declared_complete',
            'usage', 'total_cost_usd', 'wall_seconds', 'timed_out', 'process_exit', 'status',
            'process_cleanup_scope', 'detached_descendants_contained',
            'guarded_new_session_processes', 'process_cleanup_seconds',
            'stream_changed_during_cleanup')} for s in stages],
        main_calls=sum(s.get('role') in ('main_implementation', 'main_repair') and not s.get('status', '').startswith('skipped_') for s in stages),
        review_calls=sum(s.get('role') in ('test_designer', 'adversarial_reviewer') and not s.get('status', '').startswith('skipped_') for s in stages),
        planned_main_slots=2, planned_peer_slots=2, scope_violations=violations,
        artifact_invalid=bool(raw.get('artifact_error')), proof_packet_grade=None,
        semantic_correctness_beyond_oracle=None)
    return dict(schema_version=1, raw_receipt_sha256=sha(path), adapter_sha256=sha(Path(__file__)),
                graded_at_utc=hybrid.now(), grader=outcome, normalized=row)


def run(args):
    registration = hybrid.read(args.study / 'registration.json')
    for name, expected in registration['files'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Registered file changed: ' + name)
    protocol, manifest = hybrid.read(args.protocol), hybrid.read(args.manifest)
    hybrid.verify_material(protocol, manifest, args.manifest)
    tasks = {t['task_id']: t for t in manifest['tasks']}
    queue = hybrid.read(args.study / 'requests.json')
    package_sha = hybrid.grader.package_identity(HERE.parents[3], protocol['package'])
    rows = []
    for request in queue:
        path = args.study / 'trials' / request['trial_id'] / 'receipt.json'
        if not path.exists():
            rows.append(hybrid.grader.missing_row(request))
            continue
        destination = path.with_name('graded-receipt.json')
        if destination.exists():
            graded = hybrid.read(destination)
            if graded['raw_receipt_sha256'] != sha(path) or graded['adapter_sha256'] != sha(Path(__file__)):
                raise ValueError('Receipt or grader changed after one-time grading')
        else:
            graded = grade(path, request, tasks[request['task_id']], package_sha)
            hybrid.write(destination, graded)
            print(json.dumps({'trial_id': request['trial_id'], 'passed': graded['normalized']['passed']}), flush=True)
        rows.append(graded['normalized'])
    hybrid.write(args.study / 'results-normalized.json', rows)
    return all(r.get('status') != 'missing_receipt' for r in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        if run(args) or not args.watch:
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
