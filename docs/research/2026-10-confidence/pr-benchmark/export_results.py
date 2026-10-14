#!/usr/bin/env python3
"""Publish outcome receipts and production patches without model transcripts.

Run after all scheduled receipts are independently graded. This is a projection
of existing evidence, not a scoring rule; the frozen analyzer remains authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project(row):
    # Explicit allowlist: summaries, free-text errors, argv, source paths,
    # provider payloads and assistant transcripts are deliberately not exported.
    fields = (
        'schema_version', 'trial_id', 'task_id', 'arm_id', 'repeat', 'status',
        'passed', 'oracle_passed', 'harness_invalid', 'model_requested',
        'observed_assistant_models', 'usage_models', 'requested_effort',
        'observed_effort', 'declared_complete', 'human_interventions',
        'total_cost_usd', 'known_cost_subtotal', 'cost_known', 'tokens',
        'wall_seconds', 'main_calls', 'review_calls', 'denials',
        'artifact_invalid', 'over_budget', 'source_sha256', 'patch_sha256',
        'result_sha256', 'request_sha256', 'proof_packet_grade',
        'semantic_correctness_beyond_oracle',
        'main_model', 'peer_model', 'stage_usage', 'missing_required_reviews',
        'truthful_success',
    )
    result = {key: row[key] for key in fields if key in row}
    result['oracle_false_completion'] = row.get('false_completion')
    result['harness_invalid_reasons'] = [value.split(':', 1)[0]
                                        for value in row.get('harness_invalid_reasons', [])]
    result['tool_input_error_count'] = sum(
        item.get('error_kind') == 'tool_input' for item in row.get('tool_errors', []))
    result['policy_denial_count'] = len(row.get('policy_denials', []))
    result['scope_violation_count'] = len(row.get('scope_violations', []))
    return result


def export(study, schedule_path, destination):
    schedule = read(schedule_path)
    rows = read(study / 'results-normalized.json')
    expected = {(r['task_id'], r['arm_id'], r['repeat']) for r in schedule}
    actual = [(r['task_id'], r['arm_id'], r['repeat']) for r in rows]
    if len(expected) != len(schedule) or len(set(actual)) != len(actual):
        raise ValueError('Duplicate scheduled or observed identity')
    if set(actual) != expected or any(r.get('status') == 'missing_receipt' for r in rows):
        raise ValueError('The complete scheduled cohort must be graded before publication')
    destination.mkdir(parents=True, exist_ok=True)
    public, artifacts = [], []
    for row in sorted(rows, key=lambda r: (r['task_id'], r['repeat'], r['arm_id'])):
        identity = row['trial_id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', identity):
            raise ValueError('Unsafe trial identity')
        directory = study / 'trials' / identity
        receipt = directory / 'graded-receipt.json'
        if receipt.is_symlink() or not receipt.is_file():
            raise ValueError('Missing independent grading receipt: ' + identity)
        recorded = read(receipt)['normalized']
        # A stale aggregate must not silently publish a newer per-trial receipt.
        if recorded != row:
            raise ValueError('Aggregate differs from graded receipt: ' + identity)
        projected = project(row)
        patch = directory / 'submitted.patch'
        if not patch.exists() and row.get('artifact_invalid') is True:
            projected['production_patch'] = None
            projected['production_patch_unavailable'] = True
            public.append(projected)
            artifacts.append({
                'trial_id': identity,
                'raw_receipt_sha256': digest((directory / 'receipt.json').read_bytes()),
                'graded_receipt_sha256': digest(receipt.read_bytes()),
                'production_patch_sha256': None,
                'production_patch_unavailable': True,
            })
            continue
        if patch.is_symlink() or not patch.is_file():
            raise ValueError('Missing regular submitted patch: ' + identity)
        data = patch.read_bytes()
        if digest(data) != row['patch_sha256']:
            raise ValueError('Patch digest mismatch: ' + identity)
        # The trusted runner produces production-only patches. Refuse accidental
        # credential, transcript, proof-directory or absolute-host-path exports.
        text = data.decode('utf-8')
        if re.search(r'(?m)^(?:diff --git|--- |\+\+\+ ).*(?:\.confidence/|\.protocol/|/Users/|/tmp/)', text):
            raise ValueError('Nonproduction path in patch: ' + identity)
        patch_name = 'patches/' + identity + '.patch'
        target = destination / patch_name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        projected['production_patch'] = patch_name
        public.append(projected)
        grade = read(directory / 'receipt.json')
        artifacts.append({
            'trial_id': identity,
            'raw_receipt_sha256': digest((directory / 'receipt.json').read_bytes()),
            'graded_receipt_sha256': digest(receipt.read_bytes()),
            'production_patch_sha256': digest(data),
            'grader_stdout_sha256': digest((directory / 'grader.stdout').read_bytes()),
            'grader_stderr_sha256': digest((directory / 'grader.stderr').read_bytes()),
            'raw_status': grade.get('status'),
        })
    (destination / 'results.json').write_text(json.dumps(public, indent=2) + '\n')
    (destination / 'artifact-hashes.json').write_text(json.dumps(artifacts, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.study, args.schedule, args.output)


if __name__ == '__main__':
    main()
