#!/usr/bin/env python3
"""Separate one-time V2 grading; preserve raw trials and frozen V1 semantics."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2_frozen_grader', HERE / 'hybrid_grader.py')
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
process_spec = importlib.util.spec_from_file_location('v2_grading_process_guard', HERE / 'hybrid_process_v2.py')
process_guard = importlib.util.module_from_spec(process_spec)
process_spec.loader.exec_module(process_guard)
process_guard.install(frozen.hybrid.processes)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualification(stage, assigned):
    """Independently derive qualification from provider and transport facts.

    Unknown metadata does not become false software behavior. The attempted
    harness remains unqualified and cannot contribute a verified success.
    """
    if stage.get('status', '').startswith('skipped_'):
        return dict(passed=None, skipped=True, reasons=[], provider=assigned)
    reasons = []
    cleanup_seconds = stage.get('process_cleanup_seconds')
    guarded = stage.get('guarded_new_session_processes')
    if (type(stage.get('timed_out')) is not bool or type(stage.get('process_exit')) is not int or
        stage.get('process_cleanup_scope') != 'original_process_group' or
        stage.get('detached_descendants_contained') is not False or
        type(guarded) is not int or guarded < 1 or
        stage.get('stream_changed_during_cleanup') is not False or
        type(cleanup_seconds) not in (int, float) or not math.isfinite(cleanup_seconds) or cleanup_seconds < 0):
        reasons.append('lifecycle_metadata_unqualified')
    source_launch, source_after = stage.get('source_sha256_at_launch'), stage.get('source_sha256_after')
    valid_source = all(isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value)
                       for value in (source_launch, source_after))
    if not valid_source:
        reasons.append('source_digest_unqualified')
    elif stage.get('role') in ('test_designer', 'adversarial_reviewer') and source_launch != source_after:
        reasons.append('readonly_source_drift')
    q = stage.get('adapter_qualification')
    if not isinstance(q, dict):
        q = {}
        reasons.append('qualification_missing')
    local = q.get('local')
    if not isinstance(local, dict):
        local = {}
        reasons.append('local_transport_missing')
    readonly = stage.get('role') in ('test_designer', 'adversarial_reviewer')
    expected = list(frozen.hybrid.base.NATIVE_TOOLS)
    actual = local.get('effective_mcp_tools', [])
    if not isinstance(actual, list) or not all(isinstance(value, str) for value in actual):
        actual = []
    if (local.get('passed') is not True or local.get('offline') is not True or
        local.get('hosted_inference_calls') != 0 or local.get('provider') != assigned or
        local.get('readonly') is not readonly or local.get('connected') is not True or
        local.get('list_files_succeeded') is not True or local.get('exit_code') != 0 or
        local.get('config_argument_is_absolute') is not True or
        len(actual) != len(expected) or set(actual) != set(expected) or
        readonly and local.get('readonly_write_denied') is not True):
        reasons.append('local_transport_unqualified')
    if q.get('passed') is not True:
        reasons.append('provider_inventory_unqualified')
    if stage.get('assigned_model') != assigned:
        reasons.append('assigned_provider_mismatch')
    if assigned == 'opus':
        init = stage.get('harness_initialization') or {}
        if not isinstance(init, dict):
            init = {}
        tools = init.get('tools', [])
        servers = init.get('mcp_servers', [])
        if not isinstance(tools, list) or not all(isinstance(value, str) for value in tools):
            tools = []
        if not isinstance(servers, list):
            servers = []
        wanted = {'mcp__cp_trial__' + name for name in expected}
        connected = any(isinstance(server, dict) and server.get('name') == 'cp_trial' and
                        server.get('status') == 'connected' for server in servers)
        if (stage.get('backend') != 'claude_code' or q.get('basis') != 'live_claude_init' or
            not connected or not wanted.issubset(tools) or set(tools) - wanted - {'StructuredOutput'} or
            len(tools) != len(set(tools)) or q.get('connected') is not True or
            q.get('effective_tools') != tools or q.get('missing_tools') != [] or q.get('unexpected_tools') != []):
            reasons.append('opus_live_inventory_mismatch')
    elif assigned == 'astra':
        guard = stage.get('inventory_guard') or {}
        if not isinstance(guard, dict):
            guard = {}
        handlers = list(frozen.hybrid.backend.RESOURCE_HANDLERS)
        wanted = ['mcp__cp_trial__' + name for name in expected] + handlers
        declared = guard.get('expected_tools', [])
        actual_declared = guard.get('declared_tools', [])
        if not isinstance(declared, list) or not all(isinstance(value, str) for value in declared):
            declared = []
        if not isinstance(actual_declared, list):
            actual_declared = []
        normalized = [name.replace('.', '__') if name.startswith('mcp__') else name for name in actual_declared if isinstance(name, str)]
        if (stage.get('backend') != 'codex_cli' or q.get('basis') != 'offline_declared_codex_inventory_and_local_pipeline' or
            guard.get('passed') is not True or len(declared) != len(wanted) or set(declared) != set(wanted) or
            len(normalized) != len(wanted) or set(normalized) != set(wanted) or
            q.get('declared_inventory') != guard or q.get('live_wire_inventory_observed') is not False or
            q.get('strict_seven_tool_parity') is not False or q.get('additional_resource_handlers') != handlers):
            reasons.append('astra_declared_inventory_mismatch')
    else:
        reasons.append('unregistered_provider')
    safe_local = {key: local.get(key) for key in ('passed', 'offline', 'hosted_inference_calls', 'provider',
        'readonly', 'connected', 'effective_mcp_tools', 'list_files_succeeded', 'readonly_write_denied',
        'exit_code', 'config_argument_is_absolute', 'stderr_sha256', 'stdout_sha256')}
    safe = {key: q.get(key) for key in ('passed', 'basis', 'connected', 'missing_tools', 'unexpected_tools',
        'effective_tools', 'strict_seven_tool_parity', 'live_wire_inventory_observed', 'additional_resource_handlers',
        'observed_tool_call_names')}
    return dict(passed=not reasons, skipped=False, provider=assigned, reasons=reasons,
                recorded_qualification=safe, local_transport=safe_local,
                source_binding={'at_launch': source_launch, 'after': source_after},
                lifecycle={key: stage.get(key) for key in ('timed_out', 'process_exit', 'process_cleanup_scope',
                    'detached_descendants_contained', 'guarded_new_session_processes',
                    'stream_changed_during_cleanup', 'process_cleanup_seconds')})


def grade(path, request, task, package_sha):
    raw = frozen.hybrid.read(path)
    checks = []
    for stage in raw.get('stages', []):
        assigned = request['peer_model'] if stage.get('role') in ('test_designer', 'adversarial_reviewer') else request['main_model']
        check = qualification(stage, assigned)
        check['role'] = stage.get('role')
        checks.append(check)
    reasons = [str(check.get('role') or 'unknown') + ':' + reason for check in checks for reason in check['reasons']]
    if reasons:
        with patch.object(frozen.hybrid.grader, 'invoke_oracle', return_value={
            'oracle_passed': None, 'not_invoked': True, 'reason': 'unqualified_v2_provider_transport'}):
            result = frozen.grade(path, request, task, package_sha)
    else:
        result = frozen.grade(path, request, task, package_sha)
    row = result['normalized']
    row['harness_invalid_reasons'] += reasons
    row['harness_invalid'] = bool(row['harness_invalid_reasons'])
    row['truthful_success'] = row['truthful_success'] and not reasons
    row['stage_qualification'] = checks
    for stage, check in zip(row['stage_usage'], checks):
        stage['adapter_qualification'] = check
    result.update(schema_version=2, frozen_adapter_sha256=result['adapter_sha256'],
                  adapter_sha256=sha(Path(__file__)), qualification_rule='Provider-specific inventory and local transport required for every non-skipped stage')
    return result


def run(args):
    registration = frozen.hybrid.read(args.study / 'registration.json')
    if registration.get('adapter_version') != 2 or registration['files'].get(str(Path(__file__).resolve())) != sha(Path(__file__)):
        raise ValueError('Fresh V2 registration pinning this grader is required')
    for name, expected in registration['files'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Registered file changed: ' + name)
    protocol, manifest = frozen.hybrid.read(args.protocol), frozen.hybrid.read(args.manifest)
    frozen.hybrid.verify_material(protocol, manifest, args.manifest)
    tasks = {task['task_id']: task for task in manifest['tasks']}
    queue = frozen.hybrid.read(args.study / 'requests.json')
    package_sha = frozen.hybrid.grader.package_identity(HERE.parents[3], protocol['package'])
    rows = []
    for request in queue:
        path = args.study / 'trials' / request['trial_id'] / 'receipt.json'
        if not path.exists():
            row = frozen.hybrid.grader.missing_row(request)
            row['stage_qualification'] = None
            rows.append(row)
            continue
        destination = path.with_name('v2-graded-receipt.json')
        if destination.exists():
            result = frozen.hybrid.read(destination)
            if result['raw_receipt_sha256'] != sha(path) or result['adapter_sha256'] != sha(Path(__file__)):
                raise ValueError('Raw receipt or V2 grader changed after one-time grading')
        else:
            result = grade(path, request, tasks[request['task_id']], package_sha)
            frozen.hybrid.write(destination, result)
            print(json.dumps({'trial_id': request['trial_id'], 'passed': result['normalized']['passed'],
                              'harness_invalid': result['normalized']['harness_invalid']}), flush=True)
        rows.append(result['normalized'])
    frozen.hybrid.write(args.study / 'results-normalized.json', rows)
    return all(row.get('status') != 'missing_receipt' for row in rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    for key in ('study', 'protocol', 'manifest'):
        setattr(args, key, getattr(args, key).resolve())
    while True:
        if run(args) or not args.watch:
            break
        time.sleep(30)
