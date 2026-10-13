#!/usr/bin/env python3
"""Close the eight saved PR40 follow-ups; optional separate CPU rechecks.

No hosted calls, retries, rewriting of primary grades, or model ranking. This
analyzer is research-only and uses the qualified owner harness helper APIs.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


a = module('followup_closure_helpers', HERE / 'analyze.py')
f = module('followup_frozen_controller', HERE / 'followup.py')
r = f.r
LOADED_HELPERS = {name + '_sha256': r.sha(HERE / (name.replace('_py', '.py'))) for name in ('analyze_py', 'followup_py', 'runner_py')}
require, number, bound, oracle_truth = a.require, a.number, a.bound, a.oracle_truth
IDS = a.IDS
ARMS = a.ARMS
MODEL = 'claude-opus-5-5'
STATUSES = {'completed', 'infrastructure_or_artifact_error', 'not_run_missing_initial_source', 'started_unknown', 'never_started'}
STRATA = ('initially_accepted', 'initially_broken', 'initially_unknown')
LIMITS = [
    'Eight predeclared PR40 artifacts, including available incorrect initial solutions; one small environment-token extension, not broad maintainability.',
    'Every available artifact receives the same Opus medium 120-second/USD1 route. Original arm labels describe initial artifacts, not a reciprocal follow-up model comparison.',
    'Originally accepted, broken and unknown strata remain separate. Extension on a broken artifact also requires repair; it is not pure maintenance effort.',
    'Historical grader receipts lack candidate input digests. Current saved stdout/stderr fidelity does not establish historical candidate association.',
    'Fresh CPU rechecks bind current candidate and all evaluator dependencies before/after; they are separate diagnostics and never replace registered primary grades.',
    'A started attempt or recheck is preserved and never automatically retried. Current bytes and controller refusal semantics do not prove absolute continuous custody.',
    'Worker completion is a declaration; absent or failing required original/novel checks remain unknown or unsuccessful. Selected checks do not certify all preserved behavior.',
    'Changed files/lines and command counts are descriptive. They do not measure assertion coverage or establish code quality, maintainability or model superiority.',
    'Usage and CLI cost estimates are not subscription bills; unknown cost, CPU accounting and effort observation remain unknown.',
    'Production patches, sources, raw commands, model summaries and error prose remain private pending a separate privacy review; artifacts are hashed without redaction.',
    'When prospective custody v2 is used, only the unused first-stage main/execution-scratch subtree is excluded from artifact inventory; source, receipt, patch, request and log bindings remain required. The original legacy controller and declaration are retained.',
]


def same(left, right, reason):
    require(r.digest(left) == r.digest(right), reason)


def key(row):
    require(all(k in row for k in IDS), 'Followup assignment identity incomplete')
    require(row['task_id'] == 'tweed-pr40' and row['arm_id'] in ARMS and type(row['repeat']) is int and row['repeat'] in (1, 2), 'Followup assignment identity invalid')
    require(row['trial_id'] == 'tweed-pr40--' + row['arm_id'] + '--r' + str(row['repeat']), 'Followup trial identity noncanonical')
    return row['trial_id']


def roster(rows):
    require(isinstance(rows, list) and len(rows) == 8, 'Followup roster must preserve all eight assignments')
    actual = [key(row) for row in rows]
    expected = {'tweed-pr40--' + arm + '--r' + str(repeat) for arm in ARMS for repeat in (1, 2)}
    require(len(set(actual)) == 8 and set(actual) == expected, 'Followup roster duplicated/missing/mismatched')


def dependencies(declaration):
    task = declaration['task']
    result = {}
    for label, script in (('original', task['oracle_script']), ('novel', declaration['oracle_script'])):
        oracle = Path(script).parent
        fixture = oracle.parent / 'base'
        require(r.inventory(fixture) == r.inventory(task['base_snapshot']), 'Grader baseline fixture differs from frozen task base')
        result[label] = {'script_sha256': r.sha(script), 'oracle_tree_sha256': r.digest(r.inventory(oracle)),
                         'grader_base_sha256': r.digest(r.inventory(fixture)), 'task_base_sha256': r.digest(r.inventory(task['base_snapshot']))}
    return result


def controller(study):
    marker = r.read(study / 'declaration.json')['payload'].get('custody_schema')
    require(marker in (None, 'followup-input-custody-v2'), 'Unknown input custody schema')
    return f if marker is None else module('followup_custody_v2', HERE / 'followup_v2.py')


def verify_plan(study, custody=None):
    """Read declared inputs and controls only; do not read initial scores here."""
    custody = custody or controller(study)
    declaration = custody.verify_declaration(study)
    require(declaration['initial_payload_sha256'] == r.digest(custody.r.verify(Path(declaration['initial_study']))), 'Declared initial input payload association differs')
    roster(declaration['roster'])
    require(declaration['model'] == MODEL and declaration['effort'] == 'medium' and declaration['seconds'] == 120 and declaration['claude_budget_usd'] == 1 and declaration['concurrency_ceiling'] == 2, 'Followup requested route/limits differ from preregistration')
    require(declaration['arm']['backend'] == 'claude' and declaration['arm']['model'] == MODEL and declaration['arm']['effort'] == 'medium', 'Followup worker arm differs')
    require(declaration['requirements'] == f.REQUIREMENTS, 'Followup requirement differs from frozen controller')
    original = Path(declaration['task']['oracle_script']).parent
    novel = Path(declaration['oracle_script']).parent
    derivation = declaration['derivation']
    bound(original / 'modules/test_budget_resume_audit.py', derivation['fixture_sha256'], 'Original derivation fixture')
    bound(novel / 'modules/test_budget_unbounded_probe.py', derivation['novel_module_sha256'], 'Novel derivation fixture')
    require(r.sha(novel / 'evaluate.py') == r.sha(original / 'evaluate.py'), 'Novel evaluator differs from original trusted evaluator')
    original_tree = ast.parse((original / 'modules/test_budget_resume_audit.py').read_text())
    klass = next(n for n in original_tree.body if isinstance(n, ast.ClassDef) and n.name == 'BudgetResumeAudit')
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == f.METHOD)
    changed = ast.parse((novel / 'modules/test_budget_unbounded_probe.py').read_text()).body[-1].body
    require(len(changed) == 2, 'Novel fixture method inventory differs')
    for actual, token, method_name in zip(changed, f.TOKENS, f.NAMES):
        expected = copy.deepcopy(method); expected.name = method_name
        literals = [n for n in ast.walk(expected) if isinstance(n, ast.Constant) and n.value == 'off']
        require(len(literals) == 1, 'Original fixture token derivation changed')
        literals[0].value = token
        require(ast.dump(actual) == ast.dump(expected), 'Novel oracle changed more than method name/public token')
    same(derivation['tokens'], list(f.TOKENS), 'Novel token declaration differs')
    same(derivation['test_ids'], r.read(novel / 'oracle.json')['test_ids'], 'Novel selected test IDs differ')
    controls = r.read(study / 'controls/results.json')
    observations = controls['observations']
    require(controls.get('passed') is True and [o['label'] for o in observations] == ['head-novel', 'alternative-novel', 'alternative-original'], 'Followup control roster differs')
    for observation, expected in zip(observations, (False, True, True)):
        require(oracle_truth(observation, study / 'controls' / observation['label']) is expected, 'Followup control did not reject head/accept bounded alternative')
    require(controls['alternative_inventory_sha256'] == r.digest(r.inventory(study / 'controls/bounded-alternative')), 'Bounded alternative control source drift')
    return declaration, dependencies(declaration)


def projected_initial(declaration, initial, destination, adapter):
    task = declaration['task']
    projection = r.load(Path(task['oracle_script']))
    submitted = projection.copy_candidate(Path(task['base_snapshot']), Path(initial['source']), destination, task['production_paths'])
    for pattern in ('AGENTS.md', 'CLAUDE.md', '.claude', '.codex', '.agents', '.git', '.protocol'):
        for path in list(destination.rglob(pattern)):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    return adapter.frozen.base.tree_digest(destination), submitted


def grade(raw, label, directory, bindings):
    value = raw.get(label + '_grade')
    if not isinstance(value, dict):
        require(raw.get(label + '_passed') is None, 'Primary grade is absent but PASS/FAIL asserted')
        for filename in ('grader.stdout', 'grader.stderr'):
            path = directory / filename
            if path.exists(): bindings[label + '_unbound_' + filename.replace('.', '_') + '_sha256'] = r.sha(path)
        return None
    truth = oracle_truth(value, directory)
    if label in ('original', 'novel'):
        require(raw.get(label + '_passed') is truth, 'Primary recorded verdict contradicts bound grader facts')
    for stream in ('stdout', 'stderr'):
        bindings[label + '_' + stream + '_sha256'] = value[stream + '_sha256']
    return truth


def commands(main, raw, stage, adapter):
    """Bind actual stream requests to server events; retain raw argv privately."""
    events_path = main / 'tool-events.jsonl'
    if raw.get('tool_events_sha256') is None:
        require(not events_path.exists(), 'Unbound tool-events log')
        events = []
    else:
        bound(events_path, raw['tool_events_sha256'], 'Actual tool events')
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
    stream, _ = adapter.frozen.backend.parse_events(main / 'stream.jsonl')
    requested = []
    for event in stream:
        for block in (event.get('message') or {}).get('content', []) if event.get('type') == 'assistant' else []:
            if block.get('type') == 'tool_use' and block.get('name', '').startswith('mcp__cp_trial__'):
                requested.append({'name': block['name'].split('__')[-1], 'arguments_sha256': r.digest(block.get('input')), 'arguments': block.get('input')})
    available = Counter((q['name'], q['arguments_sha256']) for q in requested)
    actual = Counter((e['name'], e['arguments_sha256']) for e in events)
    require(not (actual - available), 'Actual server event has no corresponding provider request')
    for event in events:
        require(event['name'] in adapter.EXPECTED and type(event.get('ok')) is bool, 'Unknown actual server event shape')
        if 'command_exit_code' in event: require(event['command_exit_code'] is None or type(event['command_exit_code']) is int, 'Actual command exit code malformed')
        if 'command_timed_out' in event: require(event['command_timed_out'] is None or type(event['command_timed_out']) is bool, 'Actual command timeout malformed')
    checks = [e for e in events if e['name'] in ('run_tests', 'confidence')]
    counts = {'requested': len(checks), 'exit_zero': sum(e.get('command_exit_code') == 0 for e in checks),
              'timed_out': sum(e.get('command_timed_out') is True for e in checks),
              'run_tests_commands': sum(e['name'] == 'run_tests' for e in checks),
              'confidence_commands': sum(e['name'] == 'confidence' for e in checks),
              'basis': 'Actual confined command/tool events; command counts, not assertion/test counts'}
    same(raw.get('executed_check_counts'), counts, 'Recorded executed-check counts differ from actual events')
    callbacks = []
    for request_path in sorted(main.glob('*.command-request.json')):
        request = r.read(request_path)
        ident = request['id']
        require(re.fullmatch(r'[0-9a-f]{32}', ident) and request_path.name == ident + '.command-request.json', 'Command callback identity differs')
        response_path = main / (ident + '.command-response.json')
        response = r.read(response_path) if response_path.exists() else None
        bindings = {'request_sha256': r.sha(request_path)}
        if response is not None:
            bindings['response_sha256'] = r.sha(response_path)
            for field in ('stdout', 'stderr'):
                if response.get(field) is not None:
                    path = Path(response[field])
                    require(path.resolve().parent == main.resolve() and path.name.startswith('command-' + ident + '.'), 'Command log path escapes owned callback')
                    bindings[field + '_sha256'] = r.sha(path)
        callbacks.append({'argv': request['argv'], 'argv_sha256': r.digest(request['argv']),
                          'exit_code': (response or {}).get('exit_code'), 'timed_out': (response or {}).get('timed_out'),
                          'bindings': bindings})
    # Relate a served command to its actual coordinator callback. This is a data
    # association check; the qualified provider helper remains the tool guard.
    server = r.read(main / 'server-config.json')
    translations = {'python3': server['python_executable'], 'python': server['python_executable'],
                    server['python_executable']: server['python_executable'], 'git': adapter.frozen.base.GIT,
                    'bash': '/bin/bash', 'sh': '/bin/sh'}
    command_requests = []
    for request in requested:
        if request['name'] not in ('run_tests', 'confidence') or not isinstance(request['arguments'], dict): continue
        argv = request['arguments'].get('argv')
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv): continue
        if request['name'] == 'confidence': argv = ['python3', '-B', str(Path(server['workspace']) / '.protocol/scripts/confidence.py'), *argv]
        if argv[0] in translations:
            command_requests.append(([translations[argv[0]], *argv[1:]], request))
    require(not (Counter(c['argv_sha256'] for c in callbacks) - Counter(r.digest(argv) for argv, _ in command_requests)), 'Actual command callback does not match any provider command request')
    for event in checks:
        if event.get('ok') is not True: continue
        expected = [argv for argv, request in command_requests if request['name'] == event['name'] and request['arguments_sha256'] == event['arguments_sha256']]
        require(any(callback['argv'] in expected and callback['exit_code'] == event.get('command_exit_code') and callback['timed_out'] is event.get('command_timed_out') for callback in callbacks), 'Actual command callback status differs from server event')
    return {'counts': counts, 'server_rejected_checks': sum(e.get('ok') is False for e in checks),
            'calls_without_server_event': sum((available - actual).values()), 'provider_requests': requested,
            'callbacks': callbacks, 'tool_events_sha256': r.sha(events_path) if events_path.exists() else None}


def row(study, initial, declaration, adapter):
    directory = study / 'trials' / key(initial)
    receipt_path = directory / 'receipt.json'
    if receipt_path.exists():
        raw = r.read(receipt_path)
    else:
        raw = dict(initial, status='started_unknown', original_passed=None, novel_passed=None, eligible=False)
    same({k: raw[k] for k in IDS}, {k: initial[k] for k in IDS}, 'Raw followup assignment differs from sealed input')
    require(raw.get('initial_eligible') is initial['initial_eligible'] and raw.get('initial_accepted') is initial['initial_accepted'], 'Raw initial stratum differs from input seal')
    require(type(initial['available']) is bool and all(initial[field] is None or type(initial[field]) is bool for field in ('initial_eligible', 'initial_accepted')), 'Initial source/stratum facts unknown shape')
    require(raw.get('status') in STATUSES and type(raw.get('eligible')) is bool, 'Unknown followup terminal status/eligibility')
    bindings = {'initial_artifacts_sha256': initial.get('first_stage_artifact_inventory_sha256'), 'initial_source_inventory_sha256': initial.get('source_inventory_sha256')}
    original = Path(declaration['initial_study']) / 'trials' / initial['trial_id']
    require(Path(initial['source']).resolve() == (original / 'result_snapshot').resolve(), 'Sealed initial source association differs from assigned artifact')
    if 'first_stage_artifact_inventory' in initial:
        require(r.digest(initial['first_stage_artifact_inventory']) == bindings['initial_artifacts_sha256'], 'Initial artifact inventory digest differs')
    if initial['available']:
        require(r.digest(initial['source_inventory']) == bindings['initial_source_inventory_sha256'], 'Initial source inventory digest differs')
    if 'initial_receipt_sha256' in initial:
        bindings['initial_receipt_sha256'] = bound(original / 'receipt.json', initial['initial_receipt_sha256'], 'Initial owner receipt')
        previous = r.read(original / 'receipt.json')
        same({k: previous[k] for k in IDS}, {k: initial[k] for k in IDS}, 'Initial owner receipt identity differs')
        require(previous.get('eligible') is initial['initial_eligible'] and previous.get('accepted') is initial['initial_accepted'], 'Initial owner receipt stratum differs')
    if 'initial_patch_sha256' in initial: bindings['initial_patch_sha256'] = bound(original / 'submitted.patch', initial['initial_patch_sha256'], 'Initial production patch')
    if raw['status'] == 'not_run_missing_initial_source':
        require(initial['available'] is False and not (directory / 'started.json').exists(), 'An available initial source was silently excluded from followup')
    if receipt_path.exists(): bindings['receipt_sha256'] = r.sha(receipt_path)
    started = directory / 'started.json'
    if started.exists():
        marker = r.read(started)
        bound(study / 'input-seal.json', marker['input_seal_sha256'], 'Started input seal')
        require(number(marker.get('started_at_unix')) is not None, 'Started followup time unknown')
        seal_time = r.read(study / 'input-seal.json')['payload']['sealed_at_unix']
        require(number(seal_time) is not None and number(declaration.get('prepared_at_unix')) is not None and declaration['prepared_at_unix'] <= seal_time <= marker['started_at_unix'], 'Recorded followup declaration/seal/start chronology differs')
        bindings['started_sha256'] = r.sha(started)
    elif raw['status'] == 'completed':
        raise ValueError('Completed followup has no started marker')
    clean = directory / 'clean_initial'
    initial_hash, projected_paths = None, None
    if clean.is_dir():
        require(initial['available'] is True, 'Missing initial source unexpectedly produced a projected candidate')
        with tempfile.TemporaryDirectory(prefix='cp-followup-rebuild-initial-') as name:
            expected_hash, projected_paths = projected_initial(declaration, initial, Path(name) / 'workspace', adapter)
        initial_hash = adapter.frozen.base.tree_digest(clean)
        require(initial_hash == expected_hash, 'Clean initial source does not match sealed initial production projection')
        if 'initial_projected_sha256' in raw: require(raw['initial_projected_sha256'] == initial_hash, 'Recorded initial projected source differs')
        bindings['initial_projected_sha256'] = initial_hash
    snapshot, patch = directory / 'result_snapshot', directory / 'submitted.patch'
    stats, changed_paths, test_files_changed, bound_result = None, None, None, False
    if snapshot.is_dir() and 'result_sha256' in raw:
        require(initial_hash is not None, 'Final source has no reconstructed initial projection')
        result_hash = adapter.frozen.base.tree_digest(snapshot)
        require(result_hash == raw['result_sha256'], 'Final source current-byte digest differs')
        bound(patch, raw.get('patch_sha256'), 'Followup production patch')
        with tempfile.TemporaryDirectory(prefix='cp-followup-patch-rebuild-') as name:
            rebuilt, submitted = a.rebuild_patch(adapter, clean, snapshot, Path(name) / 'rebuilt.patch', declaration['task']['production_paths'])
        require(rebuilt == patch.read_bytes(), 'Production patch does not describe actual final-vs-initial source')
        same(raw.get('submitted_paths'), submitted, 'Submitted production path inventory differs')
        same(raw.get('projected_production_paths'), projected_paths, 'Initial projected path inventory differs')
        violations = adapter.frozen.base.scope_diff(clean, snapshot, declaration['task']['production_paths'])
        same(raw.get('scope_violations'), violations, 'Recorded final source scope differs')
        stats = {'bytes': len(rebuilt), 'added_lines': sum(line.startswith(b'+') and not line.startswith(b'+++') for line in rebuilt.splitlines()),
                 'removed_lines': sum(line.startswith(b'-') and not line.startswith(b'---') for line in rebuilt.splitlines())}
        same(raw.get('patch_stats'), stats, 'Recorded patch statistics differ from actual bytes')
        before, after = r.inventory(clean), r.inventory(snapshot)
        changed_paths = [p for p in submitted if before.get(p) != after.get(p)]
        test_files_changed = sum(before.get(p) != after.get(p) for p in set(before) | set(after) if p.startswith('tests/'))
        bindings.update(result_sha256=result_hash, patch_sha256=r.sha(patch))
        bound_result = not violations
    elif raw['status'] == 'completed':
        raise ValueError('Completed followup lacks bound final source/patch')
    else:
        if snapshot.exists(): bindings['unbound_result_inventory_sha256'] = r.digest(r.inventory(snapshot))
        if patch.exists(): bindings['unbound_patch_sha256'] = r.sha(patch)
    stage = raw.get('stage')
    q, terminal, command_evidence = None, None, None
    if isinstance(stage, dict):
        main = directory / 'main'; request = r.read(main / 'request.json')
        require(r.digest(request) == stage.get('request_sha256'), 'Actual followup request digest differs')
        require(request.get('model_requested') == MODEL and request.get('effort') == 'medium' and request.get('budget_usd') == 1 and request.get('timeout_seconds') == 120 and request.get('readonly') is False, 'Actual followup route/effort/budget/scope differs')
        prompt = 'Read .protocol/SKILL.md and relevant references.\n' + declaration['requirements'] + '\nOriginal required behavior:\n' + declaration['task']['prompt'] + '\nVisible baseline commands:\n' + json.dumps(declaration['task']['test_commands'])
        a.request_envelope(main, request, declaration['arm'], declaration, prompt, adapter, {})
        require(request.get('prompt') == prompt, 'Actual followup request prompt differs')
        bindings['request_sha256'] = r.sha(main / 'request.json')
        bindings['server_config_sha256'] = r.sha(main / 'server-config.json')
        bindings['stream_sha256'] = bound(main / 'stream.jsonl', stage.get('stream_sha256'), 'Followup provider stream')
        a.provider_facts(main, stage, declaration['arm'], adapter)
        local_path = directory / 'qualification/local-qualification.json'
        q = r.qualification(stage, r.read(local_path), declaration['arm'], adapter)
        same(raw.get('qualification'), q, 'Followup qualification differs from current provider facts')
        require(raw['eligible'] is (q['eligible'] and bound_result), 'Raw followup eligibility differs from provider/source facts')
        bindings['local_qualification_sha256'] = r.sha(local_path)
        if (main / 'stderr.log').exists(): bindings['current_stderr_sha256'] = r.sha(main / 'stderr.log')
        terminal = r.terminal(stage)
        command_evidence = commands(main, raw, stage, adapter)
    else:
        require(raw['eligible'] is False, 'Missing stage cannot certify a followup')
        if (directory / 'main').exists(): bindings['unbound_main_inventory_sha256'] = r.digest(r.inventory(directory / 'main'))
    primary = {label: grade(raw, label, directory / label, bindings) for label in ('initial-original', 'initial-novel', 'original', 'novel')}
    require(raw['eligible'] or primary['original'] is None and primary['novel'] is None, 'Ineligible followup has admitted primary final grades')
    if 'input_seal_sha256' in raw: bound(study / 'input-seal.json', raw['input_seal_sha256'], 'Followup recorded input seal')
    stratum = 'initially_accepted' if initial['initial_eligible'] is True and initial['initial_accepted'] is True else 'initially_broken' if initial['initial_accepted'] is False else 'initially_unknown'
    probe_role = 'extension_plus_repair' if stratum == 'initially_broken' or primary['initial-original'] is False else 'extension_on_originally_accepted' if stratum == 'initially_accepted' and primary['initial-original'] is True else 'extension_with_unknown_initial_correctness'
    preserved = raw['eligible'] and primary['original'] is True and primary['novel'] is True
    complete = terminal['complete'] if terminal is not None else None
    usage = {k: number((stage or {}).get('usage', {}).get(k)) for k in a.USAGE_KEYS} if isinstance((stage or {}).get('usage'), dict) else {k: None for k in a.USAGE_KEYS}
    costs = number((stage or {}).get('total_cost_usd'))
    if 'cost_estimate_usd' in raw: require(raw['cost_estimate_usd'] == (stage or {}).get('total_cost_usd'), 'Raw cost estimate differs from provider receipt')
    basis = ((stage or {}).get('terminal') or {}).get('costBasis', 'unknown')
    if basis not in ('list', 'unknown'): basis = 'unknown'
    if 'cost_basis' in raw: require(raw['cost_basis'] == basis, 'Raw cost basis differs from provider receipt')
    if 'observed_billed_usd' in raw: require(raw['observed_billed_usd'] is None, 'Unobserved billing cannot be invented')
    value = {k: initial[k] for k in IDS}
    value.update(initial_available=initial['available'], initial_eligible=initial['initial_eligible'], initial_accepted=initial['initial_accepted'],
                 initial_stratum=stratum, probe_role=probe_role, status=raw['status'] if directory.exists() else 'never_started', eligible=raw['eligible'], primary_grades=primary,
                 both_requirements_preserved=preserved, primary_final_unknown=primary['original'] is None or primary['novel'] is None,
                 terminal_known=terminal is not None, worker_declares_complete=complete, worker_declares_complete_empty_remaining=None if terminal is None else complete and terminal['remaining'] == [],
                 false_completion_known=complete is True and any(primary[k] is False for k in ('original', 'novel')),
                 completion_not_fully_verified=complete is True and not preserved, model_requested=MODEL, actual_model=(q or {}).get('actual_model'),
                 requested_effort='medium', observed_effort=None, wall_seconds=number((stage or {}).get('wall_seconds')), usage=usage,
                 requested_timeout_seconds=120, requested_budget_usd=1,
                 cost_estimate_usd=costs, cost_basis=basis, observed_subscription_charge_usd=None, cpu_time_seconds=None,
                 patch_stats=stats, submitted_paths=raw.get('submitted_paths'), changed_paths=changed_paths, worker_test_files_changed=test_files_changed,
                 command_evidence=command_evidence, artifact_bindings=bindings,
                 current_rechecks={}, historical_oracle_candidate_input_digest_recorded=False)
    return value, raw


def current_rechecks(study, output, rows, declaration, deps):
    """New durable source-associated CPU checks; no favorable replacement retries."""
    adapter = r.route(declaration['arm']); base = adapter.frozen.base
    candidates = {}
    for row in rows:
        for side, field, folder in (('initial', 'initial_projected_sha256', 'clean_initial'), ('final', 'result_sha256', 'result_snapshot')):
            if row['artifact_bindings'].get(field): candidates[row['trial_id'] + '/' + side] = row['artifact_bindings'][field]
    seal = {'declaration_sha256': r.sha(study / 'declaration.json'), 'input_seal_sha256': r.sha(study / 'input-seal.json'), 'sources': candidates, 'dependencies': deps}
    output = Path(output).resolve()
    if output.exists(): same(r.read(output / 'input-seal.json'), seal, 'Fresh recheck input seal changed')
    else:
        output.mkdir(parents=True)
        save_matching(output / 'input-seal.json', seal)
    for row in rows:
        for side, field, folder in (('initial', 'initial_projected_sha256', 'clean_initial'), ('final', 'result_sha256', 'result_snapshot')):
            source_hash = row['artifact_bindings'].get(field)
            if source_hash is None: continue
            source = study / 'trials' / row['trial_id'] / folder
            for label in ('original', 'novel'):
                script = Path(declaration['task']['oracle_script'] if label == 'original' else declaration['oracle_script'])
                directory = output / row['trial_id'] / (side + '-' + label)
                if (directory / 'receipt.json').exists(): record = r.read(directory / 'receipt.json')
                else:
                    require(not directory.exists(), 'Started CPU recheck is unknown; refusing automatic retry')
                    directory.mkdir(parents=True)
                    save_matching(directory / 'started.json', {'started': True, 'source_sha256': source_hash})
                    before = dependencies(declaration)
                    require(before == deps and base.tree_digest(source) == source_hash, 'CPU recheck source/dependencies drift before execution')
                    checked = r.invoke_oracle(adapter, script, source, directory)
                    record = {'source_before': source_hash, 'source_after': base.tree_digest(source), 'dependencies_before': before,
                              'dependencies_after': dependencies(declaration), 'grade': checked}
                    save_matching(directory / 'receipt.json', record)
                require(record['source_before'] == record['source_after'] == source_hash == base.tree_digest(source), 'CPU recheck source drift')
                require(record['dependencies_before'] == record['dependencies_after'] == deps == dependencies(declaration), 'CPU recheck fixture dependencies drift')
                current = oracle_truth(record['grade'], directory)
                primary = row['primary_grades'][('initial-' if side == 'initial' else '') + label]
                row['current_rechecks'][side + '-' + label] = {'passed': current, 'agrees_with_primary': current is primary if current is not None and primary is not None else None,
                    'bindings': {'receipt_sha256': r.sha(directory / 'receipt.json'), 'source_sha256': source_hash, **deps[label],
                                 'stdout_sha256': record['grade']['stdout_sha256'], 'stderr_sha256': record['grade']['stderr_sha256']}}
    return {'input_seal_sha256': r.sha(output / 'input-seal.json'), 'primary_grades_replaced': False,
            'checks': sum(len(row['current_rechecks']) for row in rows), 'disagreements': sum(c['agrees_with_primary'] is False for row in rows for c in row['current_rechecks'].values())}


def summarize(rows):
    groups = {}
    for stratum in STRATA:
        selected = [row for row in rows if row['initial_stratum'] == stratum]
        costs = [row['cost_estimate_usd'] for row in selected]
        known = [v for v in costs if v is not None]
        groups[stratum] = {'assigned': len(selected), 'available': sum(row['initial_available'] for row in selected),
            'eligible': sum(row['eligible'] for row in selected), 'both_requirements_preserved': sum(row['both_requirements_preserved'] for row in selected),
            'primary_final_unknown': sum(row['primary_final_unknown'] for row in selected), 'false_completion_known': sum(row['false_completion_known'] for row in selected),
            'cost_estimate_usd_total': sum(known) if len(known) == len(costs) and selected else None,
            'known_cost_estimate_usd_subtotal': sum(known) if known else None, 'unknown_cost_rows': len(costs) - len(known), 'observed_subscription_charge_usd': None}
    return groups


def analyze(study, recheck_output=None):
    study = Path(study).resolve()
    require(LOADED_HELPERS == {name + '_sha256': r.sha(HERE / (name.replace('_py', '.py'))) for name in ('analyze_py', 'followup_py', 'runner_py')}, 'Qualified helper bytes changed after module load')
    custody = controller(study)
    controller_hash = r.sha(custody.__file__)
    declaration, deps = verify_plan(study, custody)
    verified_declaration, seal = custody.verify(study)
    exclusion = None
    if declaration.get('custody_schema') == 'followup-input-custody-v2':
        require(seal.get('custody_schema') == 'followup-input-custody-v2' and seal.get('custody_exclusion', {}).get('path') == 'main/execution-scratch' and declaration.get('custody_exclusion', {}).get('path') == 'main/execution-scratch', 'V2 custody exclusion differs from exact unused subtree')
        exclusion = 'main/execution-scratch'
    same(verified_declaration, declaration, 'Declaration changed between validation passes')
    roster(seal['inputs'])
    normalized = r.read(study / 'results.json')
    require(normalized.get('assigned') == 8, 'Normalized followup assigned count differs')
    roster(normalized['results'])
    accepted = [row['trial_id'] for row in seal['inputs'] if row['initial_accepted'] is True]
    same(normalized['originally_accepted_subset'], accepted, 'Normalized initial acceptance stratum differs from sealed inputs')
    same([key(row) for row in normalized['results']], [key(row) for row in seal['inputs']], 'Normalized followup order differs from assigned roster')
    adapter = r.route(declaration['arm'])
    rows = []
    for initial, aggregate in zip(seal['inputs'], normalized['results']):
        value, raw = row(study, initial, declaration, adapter)
        same(aggregate, raw, 'Normalized followup/raw receipt equality failed')
        rows.append(value)
    trials = study / 'trials'
    if trials.exists(): require({p.name for p in trials.iterdir()} <= {key(row) for row in seal['inputs']}, 'Unassigned/retry followup directory')
    rechecks = current_rechecks(study, recheck_output, rows, declaration, deps) if recheck_output is not None else {'checks': 0, 'primary_grades_replaced': False, 'not_run': True}
    require(dependencies(declaration) == deps, 'Fixture dependencies changed during closure')
    custody.verify(study)
    require(r.sha(custody.__file__) == controller_hash, 'Input custody wrapper changed during closure')
    require(LOADED_HELPERS == {name + '_sha256': r.sha(HERE / (name.replace('_py', '.py'))) for name in ('analyze_py', 'followup_py', 'runner_py')}, 'Qualified helper bytes changed during closure')
    report = {'schema_version': '1.0', 'assigned': 8, 'declaration_sha256': r.sha(study / 'declaration.json'),
              'input_seal_sha256': r.sha(study / 'input-seal.json'), 'normalized_results_sha256': r.sha(study / 'results.json'),
              'analyzer_sha256': r.sha(__file__), 'analyzer_tests_sha256': r.sha(HERE / 'test_analyze_followup.py'),
              'qualified_helpers': dict(LOADED_HELPERS),
              'controller_schema': declaration.get('custody_schema', 'legacy'), 'controller_sha256': controller_hash,
              'input_custody_exclusion': exclusion,
              'grader_dependencies': deps, 'rows': rows, 'strata': summarize(rows), 'current_recheck_summary': rechecks,
              'limitations': LIMITS, 'winner': None}
    report['closure_sha256'] = r.digest(report)
    return report


def public_projection(report):
    """Allowlist categorical results/measurement/hash fields; exclude private bytes."""
    def hashes(data, allowed):
        values = {key: data[key] for key in allowed if key in data}
        require(all(value is None or isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in values.values()), 'Unsafe public artifact binding')
        return values
    def flag(value): return value is None or type(value) is bool
    dependency_keys = ('script_sha256', 'oracle_tree_sha256', 'grader_base_sha256', 'task_base_sha256')
    recheck_labels = ('initial-original', 'initial-novel', 'final-original', 'final-novel')
    artifact_keys = {'initial_artifacts_sha256', 'initial_source_inventory_sha256', 'initial_receipt_sha256', 'initial_patch_sha256', 'receipt_sha256', 'started_sha256', 'initial_projected_sha256', 'result_sha256', 'patch_sha256', 'unbound_result_inventory_sha256', 'unbound_patch_sha256', 'unbound_main_inventory_sha256', 'request_sha256', 'server_config_sha256', 'stream_sha256', 'local_qualification_sha256', 'current_stderr_sha256'}
    artifact_keys |= {label + '_' + stream + '_sha256' for label in ('initial-original', 'initial-novel', 'original', 'novel') for stream in ('stdout', 'stderr', 'unbound_grader_stdout', 'unbound_grader_stderr')}
    public = {key: report[key] for key in ('schema_version', 'assigned', 'declaration_sha256', 'input_seal_sha256', 'normalized_results_sha256', 'analyzer_sha256', 'analyzer_tests_sha256', 'qualified_helpers', 'grader_dependencies', 'closure_sha256', 'controller_schema', 'controller_sha256', 'input_custody_exclusion')}
    require(public['schema_version'] == '1.0' and public['assigned'] == 8, 'Unsafe public closure identity')
    hashes(public, ('declaration_sha256', 'input_seal_sha256', 'normalized_results_sha256', 'analyzer_sha256', 'analyzer_tests_sha256', 'closure_sha256', 'controller_sha256'))
    require((public['controller_schema'], public['input_custody_exclusion']) in (('legacy', None), ('followup-input-custody-v2', 'main/execution-scratch')), 'Unsafe public custody schema/exclusion')
    public['qualified_helpers'] = hashes(report['qualified_helpers'], ('analyze_py_sha256', 'followup_py_sha256', 'runner_py_sha256'))
    public['grader_dependencies'] = {label: hashes(report['grader_dependencies'][label], dependency_keys) for label in ('original', 'novel')}
    rows = []
    keys = set(IDS) | {'initial_available', 'initial_eligible', 'initial_accepted', 'initial_stratum', 'probe_role', 'status', 'eligible', 'primary_grades',
        'both_requirements_preserved', 'primary_final_unknown', 'terminal_known', 'worker_declares_complete', 'worker_declares_complete_empty_remaining',
        'false_completion_known', 'completion_not_fully_verified', 'model_requested', 'actual_model', 'requested_effort', 'observed_effort',
        'wall_seconds', 'cost_estimate_usd', 'cost_basis', 'observed_subscription_charge_usd', 'cpu_time_seconds', 'patch_stats',
        'historical_oracle_candidate_input_digest_recorded', 'worker_test_files_changed', 'requested_timeout_seconds', 'requested_budget_usd'}
    for row in report['rows']:
        key(row)
        require(row['status'] in STATUSES and row['initial_stratum'] in STRATA and row['model_requested'] == MODEL and row['actual_model'] in (MODEL, None), 'Public categorical field invalid')
        clean = {key: row[key] for key in keys}
        require(clean['probe_role'] in ('extension_plus_repair', 'extension_on_originally_accepted', 'extension_with_unknown_initial_correctness') and clean['requested_effort'] == 'medium' and clean['observed_effort'] is None and clean['requested_timeout_seconds'] == 120 and clean['requested_budget_usd'] == 1, 'Unsafe public route/probe role')
        for field in ('initial_available', 'initial_eligible', 'initial_accepted', 'eligible', 'both_requirements_preserved', 'primary_final_unknown', 'terminal_known', 'worker_declares_complete', 'worker_declares_complete_empty_remaining', 'false_completion_known', 'completion_not_fully_verified'):
            require(flag(clean[field]), 'Unsafe public verdict flag')
        require(clean['historical_oracle_candidate_input_digest_recorded'] is False and clean['cost_basis'] in ('list', 'unknown') and clean['observed_subscription_charge_usd'] is None and clean['cpu_time_seconds'] is None, 'Unsafe public evidence/cost claim')
        for field in ('wall_seconds', 'cost_estimate_usd', 'worker_test_files_changed'):
            require(clean[field] is None or number(clean[field]) is not None, 'Unsafe public measurement')
        clean['primary_grades'] = {label: row['primary_grades'][label] for label in ('initial-original', 'initial-novel', 'original', 'novel')}
        require(all(flag(value) for value in clean['primary_grades'].values()), 'Unsafe public primary grade')
        if clean['patch_stats'] is not None:
            clean['patch_stats'] = {field: clean['patch_stats'][field] for field in ('bytes', 'added_lines', 'removed_lines')}
            require(all(type(value) is int and value >= 0 for value in clean['patch_stats'].values()), 'Unsafe public patch statistics')
        clean['usage'] = {key: row['usage'][key] for key in a.USAGE_KEYS}
        require(all(value is None or number(value) is not None for value in clean['usage'].values()), 'Unsafe public usage measurement')
        clean['artifact_bindings'] = hashes(row['artifact_bindings'], artifact_keys)
        clean['current_rechecks'] = {}
        for label in recheck_labels:
            if label not in row['current_rechecks']: continue
            check = row['current_rechecks'][label]
            require(flag(check['passed']) and flag(check['agrees_with_primary']), 'Unsafe public CPU verdict')
            clean['current_rechecks'][label] = {'passed': check['passed'], 'agrees_with_primary': check['agrees_with_primary'],
                'bindings': hashes(check['bindings'], ('receipt_sha256', 'source_sha256', 'stdout_sha256', 'stderr_sha256', *dependency_keys))}
        command = row['command_evidence']
        clean['commands'] = None
        if command is not None:
            counts = {field: command['counts'][field] for field in ('requested', 'exit_zero', 'timed_out', 'run_tests_commands', 'confidence_commands')}
            require(all(type(value) is int and value >= 0 for value in [*counts.values(), command['server_rejected_checks'], command['calls_without_server_event']]), 'Unsafe public command count')
            callbacks = []
            for call in command['callbacks']:
                require(call['exit_code'] is None or type(call['exit_code']) is int, 'Unsafe public command exit')
                require(flag(call['timed_out']), 'Unsafe public command timeout')
                callbacks.append({**hashes(call, ('argv_sha256',)), 'exit_code': call['exit_code'], 'timed_out': call['timed_out'],
                                  'bindings': hashes(call['bindings'], ('request_sha256', 'response_sha256', 'stdout_sha256', 'stderr_sha256'))})
            clean['commands'] = {'counts': counts, 'server_rejected_checks': command['server_rejected_checks'], 'calls_without_server_event': command['calls_without_server_event'], **hashes(command, ('tool_events_sha256',)), 'callback_records': callbacks}
        clean['changed_files'] = None if row['changed_paths'] is None else len(row['changed_paths'])
        clean['patch_publication'] = {'published': False, 'reason': 'Raw production patch requires a separate privacy review; exact private bytes remain bound without redaction', 'sha256': row['artifact_bindings'].get('patch_sha256')}
        rows.append(clean)
    roster(rows)
    summary = report['current_recheck_summary']
    require(summary['primary_grades_replaced'] is False, 'Public recheck cannot replace primary grades')
    safe_summary = {field: summary[field] for field in ('checks', 'disagreements', 'primary_grades_replaced', 'not_run') if field in summary}
    for field in ('checks', 'disagreements'):
        if field in safe_summary: require(type(safe_summary[field]) is int and safe_summary[field] >= 0, 'Unsafe public recheck count')
    if 'not_run' in safe_summary: require(type(safe_summary['not_run']) is bool, 'Unsafe public recheck flag')
    safe_summary.update(hashes(summary, ('input_seal_sha256',)))
    public.update(rows=rows, strata=summarize(rows), current_recheck_summary=safe_summary, limitations=list(LIMITS), winner=None)
    public['projection_sha256'] = r.digest(public)
    return public


def save_matching(path, value):
    path = Path(path)
    if path.exists(): same(r.read(path), value, 'Refusing to overwrite different analysis/recheck output')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as out: out.write(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-output', type=Path)
    parser.add_argument('--recheck-output', type=Path, help='New separate durable CPU rechecks; started checks are never retried')
    args = parser.parse_args()
    require(args.public_output is None or args.output.resolve() != args.public_output.resolve(), 'Private/public output paths must differ')
    report = analyze(args.study, args.recheck_output)
    public = public_projection(report)
    for path, value in ((args.output, report), (args.public_output, public)):
        if path is not None and path.exists(): same(r.read(path), value, 'Refusing to overwrite different analysis output')
    save_matching(args.output, report)
    if args.public_output is not None: save_matching(args.public_output, public)
    print(json.dumps({'assigned': report['assigned'], 'eligible': sum(row['eligible'] for row in report['rows']), 'closure_sha256': report['closure_sha256'], 'projection_sha256': public['projection_sha256']}))


if __name__ == '__main__': main()
