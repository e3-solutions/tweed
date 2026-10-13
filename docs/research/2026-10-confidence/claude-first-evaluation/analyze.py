#!/usr/bin/env python3
"""Closed48 current-byte analysis, without model calls or oracle re-execution.

Verified assigned success is an evidence outcome, not unknown semantic failure.
Private local custody checks cannot prove absolute continuous immutability.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import sys
from types import FunctionType

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('closed48_helpers', HERE / 'runner.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
IDS = ('trial_id', 'task_id', 'arm_id', 'repeat')
ARMS = ('baseline-opus', 'enhanced-opus', 'enhanced-haiku', 'enhanced-codex')
USAGE_KEYS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
MODELS = {'claude-opus-5-5', 'claude-haiku-5-5', 'claude-haiku-4-5', 'gpt-6.1-sol', 'gpt-6-astra'}
ROW_KEYS = set(IDS) | {'backend', 'model_requested', 'actual_model', 'model_attribution', 'status', 'eligible', 'verified_success', 'oracle_passed',
    'semantic_unknown', 'worker_complete_true_empty_remaining', 'declares_complete_true', 'false_completion_event', 'false_completion_conditioned_denominator',
    'terminal_known', 'missing_or_invalid_terminal', 'timed_out', 'wall_seconds', 'usage', 'cost_estimate_usd', 'cost_basis', 'observed_billed_usd',
    'qualification_failures', 'artifact_bindings', 'patch_present', 'patch_bound', 'custody', 'historical_oracle_input_digest_recorded',
    'current_source_acceptance', 'oracle_association_status', 'current_recheck_agrees_with_recorded_grade', 'current_recheck_bindings'}
TOP_KEYS = {'schema_version', 'assigned', 'registration_sha256', 'requests_sha256', 'controls_sha256', 'closure_sha256', 'analyzer_sha256',
            'analyzer_tests_sha256', 'rows', 'arms', 'contrasts', 'limitations', 'current_recheck_summary'}


def require(condition, reason):
    if not condition: raise ValueError(reason)


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def bound(path, expected, label):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), label + ' absent/nonregular')
    actual = r.sha(path)
    require(actual == expected, label + ' current-byte digest mismatch')
    return actual


def oracle_truth(grade, directory):
    """Re-derive recorded verdict from current saved header + lifecycle, no run."""
    bound(directory / 'grader.stdout', grade.get('stdout_sha256'), 'Oracle stdout')
    bound(directory / 'grader.stderr', grade.get('stderr_sha256'), 'Oracle stderr')
    lines = (directory / 'grader.stdout').read_text(errors='replace').splitlines()
    try: header = json.loads(lines[0]) if lines else None
    except ValueError: header = None
    require(header == grade.get('header'), 'Oracle saved header differs from current output')
    result = None
    if grade.get('timed_out') is False and grade.get('output_changed_during_cleanup') is not True and isinstance(header, dict) and 'infrastructure_error' not in header:
        code = grade.get('exit_code'); reported = header.get('exit_code')
        if type(code) is int and type(reported) is int and code == reported and type(header.get('passed')) is bool:
            if code == 0 and header['passed'] is True: result = True
            elif code != 0 and header['passed'] is False: result = False
    require(grade.get('oracle_passed') is result, 'Oracle recorded verdict contradicts saved facts')
    return result


def validate_roster(requests, tasks, arms):
    expected = {(task, arm, repeat) for task in tasks for arm in arms for repeat in (1, 2)}
    actual = [(q.get('task_id'), q.get('arm_id'), q.get('repeat')) for q in requests]
    require(len(requests) == 48 and len(set(actual)) == 48 and set(actual) == expected, 'Closed48 schedule missing/duplicated/wrong identities')
    require(len({q.get('trial_id') for q in requests}) == 48, 'Duplicated trial identities')
    for q in requests:
        require(q['trial_id'] == q['task_id'] + '--' + q['arm_id'] + '--r' + str(q['repeat']), 'Noncanonical assigned trial identity')


def provider_facts(main, stage, arm, adapter):
    """Re-derive provider metadata from the bound actual output, no inference."""
    events, invalid = adapter.frozen.backend.parse_events(main / 'stream.jsonl')
    require(invalid == stage.get('invalid_stream_lines'), 'Recorded invalid stream count differs')
    if arm['backend'] == 'claude':
        terminal = next((event for event in reversed(events) if event.get('type') == 'result'), None)
        models = []
        init = None
        for event in events:
            if event.get('type') == 'assistant':
                model = (event.get('message') or {}).get('model')
                if isinstance(model, str) and model not in models: models.append(model)
                for block in (event.get('message') or {}).get('content', []):
                    if not isinstance(block, dict) or block.get('type') != 'tool_use': continue
                    name = block.get('name'); allowed = {'mcp__cp_trial__' + tool for tool in adapter.EXPECTED} | {'StructuredOutput'}
                    require(name in allowed, 'Actual assistant requested a tool outside the controlled inventory')
                    if name in ('mcp__cp_trial__run_tests', 'mcp__cp_trial__confidence'):
                        arguments = block.get('input')
                        require(isinstance(arguments, dict), 'Actual controlled command input unknown')
                        argv = arguments.get('argv')
                        require(isinstance(argv, list) and argv and all(isinstance(x, str) and '\0' not in x for x in argv), 'Actual controlled command argv malformed')
                        if name.endswith('__confidence'):
                            require(argv[0] in ('init', 'run', 'record', 'validate', 'render', 'next'), 'Actual unsupported Confidence command')
                        else:
                            require(argv[0] in ('python3', 'python', 'git', 'bash', 'sh', sys.executable), 'Actual executable outside confined command inventory')
                            if argv[0] in ('bash', 'sh'): require(argv[1:2] == ['-c'], 'Actual shell command enables login/startup behavior')
            elif event.get('type') == 'system' and event.get('subtype') == 'init':
                init = {key: event.get(key) for key in ('model', 'tools', 'mcp_servers', 'mcp_server_errors', 'claude_code_version', 'permissionMode')}
        require(terminal == stage.get('terminal') and models == stage.get('observed_assistant_models') and init == stage.get('harness_initialization'), 'Recorded Claude facts differ from actual stream')
        for key, wanted in [('usage', (terminal or {}).get('usage')), ('total_cost_usd', (terminal or {}).get('total_cost_usd')), ('modelUsage', (terminal or {}).get('modelUsage', {}))]:
            require(stage.get(key) == wanted, 'Recorded Claude ' + key + ' differs from actual stream')
    else:
        final = (main / 'final.json').read_text() if (main / 'final.json').is_file() else None
        facts = adapter.frozen.backend.event_receipt(events, final, error=stage.get('process_exit') != 0 or stage.get('timed_out') is True)
        for key, wanted in facts.items():
            require(stage.get(key) == wanted, 'Recorded Codex ' + key + ' differs from actual events')


def expected_claude_argv(main, server, arm, config, prompt, adapter):
    """Full frozen request envelope, reconstructed without launching a provider."""
    base = adapter.frozen.base; workspace = Path(server['workspace']); temporary = Path(server['temporary'])
    require(server.get('readonly') is False and server.get('python_executable') == sys.executable, 'Actual MCP scope/runtime differs')
    require(temporary == workspace / '.trial-tmp', 'Actual MCP scratch differs')
    profile = base.sandbox_profile(workspace, temporary, extra_reads=[Path(base.__file__).resolve(), main / 'server-config.json'], extra_writes=[main], readonly=False)
    mcp = {'mcpServers': {'cp_trial': {'command': '/usr/bin/sandbox-exec',
        'args': ['-p', profile, sys.executable, '-I', '-S', '-B', str(Path(base.__file__).resolve()), 'serve', '--config', str(main / 'server-config.json')],
        'env': base.safe_env(workspace, temporary)}}}
    return ['claude', '--print', '--model', arm['model'], '--effort', arm['effort'], '--output-format', 'stream-json', '--verbose',
        '--tools', '', '--strict-mcp-config', '--mcp-config', json.dumps(mcp), '--setting-sources', '', '--no-session-persistence', '--restricted',
        '--disable-slash-commands', '--permission-mode', 'dontAsk', '--allowedTools', 'mcp__cp_trial__*', '--max-budget-usd', str(config['claude_budget_usd']),
        '--json-schema', json.dumps(base.FINAL_SCHEMA), '--system-prompt',
        'You are a software engineer working only through the controlled workspace tools. No native tools, network, history, or outside files are available. Read the actual supplied .protocol/SKILL.md before work. Complete the requested behavior and return the required final JSON truthfully; remaining gaps remain explicit.', prompt]


def request_envelope(main, actual, arm, config, prompt, adapter, payload):
    server = r.read(main / 'server-config.json')
    if arm['backend'] == 'claude':
        expected = expected_claude_argv(main, server, arm, config, prompt, adapter)
    else:
        backend = adapter.frozen.backend; workspace = Path(server['workspace']); temporary = Path(server['temporary'])
        require(server.get('readonly') is False and server.get('python_executable') == sys.executable, 'Actual Codex MCP scope/runtime differs')
        require(temporary == workspace / '.trial-tmp', 'Actual Codex MCP scratch differs')
        args = actual['argv']; configurations = {}
        for index, arg in enumerate(args):
            if arg == '-c':
                key, value = args[index + 1].split('=', 1)
                require(key not in configurations, 'Duplicate Codex configuration override')
                configurations[key] = value
        tokens = re.findall(r'"tool_timeout_sec"=([0-9][0-9.eE+\-]*)', configurations.get('mcp_servers', ''))
        require(len(tokens) == 1, 'Actual Codex MCP wire timeout unavailable/duplicated')
        timeout = json.loads(tokens[0])
        require(number(timeout) is not None and timeout >= 1, 'Actual Codex MCP timeout unknown')
        profile = backend.runner.sandbox_profile(workspace, temporary, extra_reads=[backend.HERE / 'runner.py', main / 'server-config.json'], extra_writes=[main], readonly=False)
        mcp = {'cp_trial': {'command': '/usr/bin/sandbox-exec', 'args': ['-p', profile, sys.executable, '-I', '-S', '-B', str(backend.HERE / 'runner.py'), 'serve', '--config', str(main / 'server-config.json')],
            'env': backend.runner.safe_env(workspace, temporary), 'required': True, 'enabled_tools': list(backend.runner.NATIVE_TOOLS), 'default_tools_approval_mode': 'approve',
            'startup_timeout_sec': 10, 'tool_timeout_sec': timeout}}
        original = backend.command
        isolated = FunctionType(original.__code__, {**original.__globals__, 'write_json': lambda *_: None}, original.__name__, original.__defaults__, original.__closure__)
        isolated.__kwdefaults__ = original.__kwdefaults__
        info = payload['inventories'][arm['id']]
        expected = isolated(workspace, main, Path(info['catalog']), prompt, mcp=mcp, readonly=False)
    require(actual['argv'] == expected, 'Actual provider argv differs from full frozen controlled envelope')


def launch_digest(task, arm, config, adapter):
    """Reconstruct source inputs only; synthetic Git/scratch are digest-excluded."""
    base = adapter.frozen.base
    with tempfile.TemporaryDirectory(prefix='cp-analysis-source-only-') as name:
        workspace = Path(name) / 'workspace'; base.safe_copy(Path(task['base_snapshot']), workspace)
        for pattern in ('AGENTS.md', 'CLAUDE.md', '.claude', '.codex', '.agents', '.git'):
            for path in list(workspace.rglob(pattern)):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        r.mount(base, config['toolkit_directory'], arm['policy_directory'], workspace)
        (workspace / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
        ignore = workspace / '.gitignore'; ignore.write_text((ignore.read_text() if ignore.exists() else '') + '\n.trial-tmp/\n.confidence/\n')
        return base.tree_digest(workspace)


def rebuild_patch(adapter, base_source, result_source, output, production_paths):
    """Trusted source projection with forced tracked-content rehash.

    shutil.copy2 preserves timestamps. The historical helper can reuse a Git
    stat-cache entry for a same-size replacement within one clock tick. This
    private clone forces renormalization, without modifying frozen code or the
    global subprocess module. Untracked files/deletions still use final add-A.
    """
    original = adapter.frozen.base.build_patch; underlying = original.__globals__['subprocess']
    class FreshIndex:
        def __getattr__(self, name): return getattr(underlying, name)
        def run(self, argv, **kwargs):
            if argv[-2:] == ['add', '-A']:
                underlying.run([*argv[:-2], 'add', '--renormalize', '.'], **kwargs)
            return underlying.run(argv, **kwargs)
    cloned = FunctionType(original.__code__, {**original.__globals__, 'subprocess': FreshIndex()}, original.__name__, original.__defaults__, original.__closure__)
    return cloned(base_source, result_source, output, production_paths)


def row(directory, request, task, arm, payload, study, adapter):
    """Check one owner receipt and all available recorded-bound artifacts."""
    path = directory / 'receipt.json'; raw = r.read(path)
    require(raw.get('status') in ('completed', 'infrastructure_or_artifact_error'), 'Unknown raw owner receipt status')
    require(all(raw.get(key) == request[key] for key in IDS), 'Raw trial identity mismatch')
    require(raw.get('request_sha256') == r.digest(request), 'Assigned request digest mismatch')
    require(raw.get('backend') == arm['backend'] and raw.get('model_requested') == arm['model'], 'Raw requested route mismatch')
    require(type(raw.get('eligible')) is bool and (raw.get('accepted') is None or type(raw.get('accepted')) is bool), 'Unknown eligibility/acceptance shape')
    bindings = {'receipt_sha256': r.sha(path)}
    if raw.get('status') == 'completed':
        require('registration_sha256' in raw and 'controls_sha256' in raw, 'Completed registration/control binding absent')
    if 'registration_sha256' in raw:
        bindings['registration_sha256'] = bound(study / 'registration.json', raw['registration_sha256'], 'Registration')
    if 'controls_sha256' in raw:
        bindings['controls_sha256'] = bound(study / 'oracle-controls' / 'results.json', raw['controls_sha256'], 'Controls')
    snapshot = directory / 'result_snapshot'; patch = directory / 'submitted.patch'; stage = raw.get('stage')
    artifact_valid = False
    if snapshot.is_dir() and 'result_sha256' in raw:
        actual = adapter.frozen.base.tree_digest(snapshot)
        require(actual == raw['result_sha256'] == raw.get('source_sha256_after'), 'Result source digest mismatch')
        bindings['result_sha256'] = actual
        scope = adapter.frozen.base.scope_diff(Path(task['base_snapshot']), snapshot, task['production_paths'])
        require(scope == raw.get('scope_violations'), 'Raw source scope differs from current artifact')
        bindings['patch_sha256'] = bound(patch, raw.get('patch_sha256'), 'Production patch')
        with tempfile.TemporaryDirectory(prefix='cp-analysis-patch-only-') as name:
            rebuilt, submitted = rebuild_patch(adapter, Path(task['base_snapshot']), snapshot, Path(name) / 'rebuilt.patch', task['production_paths'])
        require(rebuilt == patch.read_bytes(), 'Bound production patch is unrelated to current source')
        if 'submitted_paths' in raw: require(submitted == raw['submitted_paths'], 'Submitted production path set differs from current source')
        artifact_valid = not scope
        require(raw.get('source_sha256_at_launch') == launch_digest(task, arm, payload['config'], adapter), 'Reconstructed launch source differs from raw input digest')
    elif raw.get('status') == 'completed':
        raise ValueError('Completed source/patch binding absent')
    elif snapshot.is_dir():
        bindings['unbound_current_result_inventory_sha256'] = r.digest(r.inventory(snapshot))
    if patch.exists() and 'patch_sha256' not in bindings:
        bindings['unbound_current_patch_sha256'] = r.sha(patch)
    recomputed = {'eligible': False, 'failures': ['returned_stage_or_artifact_unknown'], 'model_attribution': 'unknown', 'actual_model': None}
    terminal = None
    if isinstance(stage, dict):
        main = directory / 'main'; actual_request = r.read(main / 'request.json')
        require(r.digest(actual_request) == stage.get('request_sha256'), 'Actual provider request digest mismatch')
        require(actual_request.get('model_requested') == arm['model'], 'Actual provider model request mismatch')
        require(actual_request.get('readonly') is False, 'Main provider request is not the registered writable route')
        require(actual_request.get('timeout_seconds') == payload['config']['seconds'], 'Provider wall budget differs')
        argv = actual_request.get('argv', [])
        require(argv and argv[-1] == request['prompt'], 'Actual provider prompt differs from assigned request')
        require('--model' in argv and argv[argv.index('--model') + 1] == arm['model'], 'Actual provider argv model differs')
        if arm['backend'] == 'claude':
            require(actual_request.get('effort') == arm['effort'] and actual_request.get('budget_usd') == payload['config']['claude_budget_usd'], 'Claude effort/budget differs')
        else:
            require(actual_request.get('requested_effort') == arm['effort'], 'Codex effort differs')
        request_envelope(main, actual_request, arm, payload['config'], request['prompt'], adapter, payload)
        bindings['actual_request_sha256'] = r.sha(main / 'request.json')
        bindings['stream_sha256'] = bound(main / 'stream.jsonl', stage.get('stream_sha256'), 'Main stream')
        provider_facts(main, stage, arm, adapter)
        if (main / 'final.json').is_file(): bindings['final_output_sha256'] = r.sha(main / 'final.json')
        local = r.read(directory / 'qualification' / 'local-qualification.json')
        recomputed = r.qualification(stage, local, arm, adapter)
        require(recomputed == raw.get('qualification'), 'Raw qualification differs from current factual recomputation')
        terminal = r.terminal(stage)
        require(raw.get('terminal') == terminal, 'Raw terminal differs from provider success/schema facts')
        if isinstance(raw.get('qualification'), dict):
            require(raw.get('eligible') is (recomputed['eligible'] and artifact_valid), 'Raw eligibility contradicts current stage/source facts')
        events = main / 'tool-events.jsonl'
        if raw.get('tool_events_sha256') is not None:
            bindings['tool_events_sha256'] = bound(events, raw['tool_events_sha256'], 'Tool events')
        else:
            require(not events.exists(), 'Unbound unexpected tool events')
        if (main / 'stderr.log').exists():
            bindings['current_stderr_sha256'] = r.sha(main / 'stderr.log')
    else:
        require(raw['eligible'] is False and raw['accepted'] is None, 'Missing returned stage cannot certify success')
    oracle = raw.get('oracle'); accepted = None
    if isinstance(oracle, dict):
        require(raw['eligible'] is True, 'Ineligible artifact has an admitted oracle score')
        accepted = oracle_truth(oracle, directory)
        bindings.update(oracle_stdout_sha256=oracle['stdout_sha256'], oracle_stderr_sha256=oracle['stderr_sha256'])
    else:
        for filename, label in [('grader.stdout', 'unbound_current_oracle_stdout_sha256'), ('grader.stderr', 'unbound_current_oracle_stderr_sha256')]:
            file = directory / filename
            if file.exists():
                require(file.is_file() and not file.is_symlink(), 'Unbound oracle artifact nonregular')
                bindings[label] = r.sha(file)
    require(raw['accepted'] is accepted, 'Raw acceptance contradicts current oracle facts')
    complete = terminal is not None and terminal['complete'] is True and terminal['remaining'] == []
    declares = terminal is not None and terminal['complete'] is True
    # Unknown semantic behavior cannot produce a false-completion event.
    false_completion = declares and accepted is False
    semantic_unknown = accepted is None
    usage = (stage or {}).get('usage'); safe_usage = {key: number(usage.get(key)) if isinstance(usage, dict) else None for key in USAGE_KEYS}
    cost = number((stage or {}).get('total_cost_usd'))
    basis = ((stage or {}).get('terminal') or {}).get('costBasis') if arm['backend'] == 'claude' else None
    if basis not in ('list', 'unknown'): basis = 'unknown'
    result = {key: request[key] for key in IDS}
    actual_model = recomputed.get('actual_model')
    if actual_model not in MODELS: actual_model = None
    attribution = recomputed.get('model_attribution')
    if attribution not in ('assistant_event_observed', 'event_observed', 'requested_only', 'unknown'): attribution = 'unknown'
    result.update(backend=arm['backend'], model_requested=arm['model'], actual_model=actual_model, model_attribution=attribution,
                  status=raw.get('status') if raw.get('status') in ('completed', 'infrastructure_or_artifact_error') else 'unknown',
                  eligible=raw['eligible'], verified_success=raw['eligible'] and accepted is True, oracle_passed=accepted,
                  semantic_unknown=semantic_unknown, worker_complete_true_empty_remaining=complete, declares_complete_true=declares,
                  false_completion_event=false_completion, false_completion_conditioned_denominator=declares and accepted is not None,
                  terminal_known=terminal is not None, missing_or_invalid_terminal=terminal is None, timed_out=(stage or {}).get('timed_out') if type((stage or {}).get('timed_out')) is bool else None,
                  wall_seconds=number((stage or {}).get('wall_seconds')), usage=safe_usage, cost_estimate_usd=cost, cost_basis=basis,
                  observed_billed_usd=None, qualification_failures=recomputed.get('failures', []), artifact_bindings=bindings,
                  patch_present=patch.is_file(), patch_bound='patch_sha256' in bindings,
                  historical_oracle_input_digest_recorded=False, current_source_acceptance=None,
                  oracle_association_status='Historical grader has no candidate input digest; separate current-source recheck required',
                  custody='Current local recorded-byte bindings; no claim of continuous absolute immutability')
    return result


def exact_bootstrap(units):
    """Six task sums of two paired binary differences; all 6^6 resamples."""
    require(len(units) == 6 and all(type(x) is int and -2 <= x <= 2 for x in units), 'Six paired task clusters required')
    distribution = Counter({0: 1})
    for _ in range(6):
        following = Counter()
        for total, count in distribution.items():
            for unit in units: following[total + unit] += count
        distribution = following
    count = 6 ** 6
    def quantile(p):
        rank = math.ceil(p * count); seen = 0
        for total, weight in sorted(distribution.items()):
            seen += weight
            if seen >= rank: return total / 12 * 100
        raise AssertionError('Incomplete bootstrap distribution')
    return {'mean_difference_percentage_points': sum(units) / 12 * 100,
            'percentile_interval_95_percentage_points': [quantile(Fraction(1, 40)), quantile(Fraction(39, 40))],
            'resamples': count, 'clusters': 6, 'paired_cells': 12, 'task_wins': sum(x > 0 for x in units),
            'task_losses': sum(x < 0 for x in units), 'task_ties': sum(x == 0 for x in units),
            'quantile_definition': 'Empirical inverse CDF, ceiling probability-times-46656 rank',
            'outcome': 'Assigned verified success; unqualified/unknown software semantics count as zero verified evidence'}


def contrast(rows, positive, negative):
    lookup = {(row['task_id'], row['arm_id'], row['repeat']): row for row in rows}
    units = []; lower = upper = 0; task_differences = []
    for task in sorted({row['task_id'] for row in rows}):
        value = 0
        for repeat in (1, 2):
            a, b = lookup[task, positive, repeat], lookup[task, negative, repeat]
            value += int(a['verified_success']) - int(b['verified_success'])
            amin, amax = int(a['oracle_passed'] is True), int(a['oracle_passed'] is not False)
            bmin, bmax = int(b['oracle_passed'] is True), int(b['oracle_passed'] is not False)
            lower += amin - bmax; upper += amax - bmin
        units.append(value)
        task_differences.append({'task_id': task, 'paired_repeats': 2, 'difference_percentage_points': value / 2 * 100, 'paired_binary_difference_sum': value})
    return dict(positive=positive, negative=negative, **exact_bootstrap(units),
                logical_semantic_difference_bounds_percentage_points=[lower / 12 * 100, upper / 12 * 100],
                task_differences=task_differences,
                logical_bounds_are_not_confidence_intervals=True)


def summarize(rows):
    tables = {}
    for arm in ARMS:
        selected = [row for row in rows if row['arm_id'] == arm]
        counts = {key: sum(row[key] is True for row in selected) for key in ('eligible', 'verified_success', 'worker_complete_true_empty_remaining', 'false_completion_event', 'false_completion_conditioned_denominator', 'missing_or_invalid_terminal', 'timed_out', 'semantic_unknown')}
        costs = [row['cost_estimate_usd'] for row in selected if row['cost_estimate_usd'] is not None]
        tables[arm] = dict(assigned=len(selected), **counts, model_attribution_counts=dict(Counter(row['model_attribution'] for row in selected)),
                          actual_model_unknown=sum(row['actual_model'] is None for row in selected), known_cost_estimates=len(costs),
                          cost_estimate_usd_total=sum(costs) if len(costs) == len(selected) else None, known_cost_estimate_subtotal=sum(costs) if costs else None,
                          cost_basis_counts=dict(Counter(row['cost_basis'] for row in selected)), observed_billed_usd=None)
        tables[arm]['token_usage'] = {key: {'known_rows': sum(row['usage'][key] is not None for row in selected),
            'known_subtotal': sum(row['usage'][key] for row in selected if row['usage'][key] is not None) if any(row['usage'][key] is not None for row in selected) else None,
            'total': sum(row['usage'][key] for row in selected) if all(row['usage'][key] is not None for row in selected) else None} for key in USAGE_KEYS}
    return {'arms': tables, 'contrasts': [contrast(rows, 'enhanced-opus', 'baseline-opus'), contrast(rows, 'enhanced-haiku', 'enhanced-opus'), contrast(rows, 'enhanced-codex', 'enhanced-opus')]}


def missing_row(request, arm, closure, directory):
    status = 'started_unknown' if directory.exists() else 'never_started'
    require(closure == dict(request, status=status, accepted=None, eligible=False), 'Missing receipt closure does not match registered unknown-assignment shape')
    value = {key: request[key] for key in IDS}
    bindings = {}
    snapshot = directory / 'result_snapshot'
    if snapshot.is_dir(): bindings['unbound_current_result_inventory_sha256'] = r.digest(r.inventory(snapshot))
    value.update(backend=arm['backend'], model_requested=arm['model'], actual_model=None, model_attribution='unknown', status=status,
        eligible=False, verified_success=False, oracle_passed=None, semantic_unknown=True, worker_complete_true_empty_remaining=False,
        declares_complete_true=False, false_completion_event=False, false_completion_conditioned_denominator=False,
        terminal_known=False, missing_or_invalid_terminal=True, timed_out=None, wall_seconds=None,
        usage={key: None for key in USAGE_KEYS}, cost_estimate_usd=None, cost_basis='unknown', observed_billed_usd=None,
        qualification_failures=['returned_stage_or_artifact_unknown'], artifact_bindings=bindings,
        patch_present=(directory / 'submitted.patch').is_file(), patch_bound=False,
        historical_oracle_input_digest_recorded=False, current_source_acceptance=None,
        oracle_association_status='No historical oracle admission for this unknown assignment',
        custody='Current normalized unknown assignment; no source/outcome admission')
    return value


def current_rechecks(study, output, rows, tasks, arms, registration_sha256):
    """Separate fresh CPU checks, never overwrite historical primary evidence."""
    output = Path(output).resolve()
    dependencies = {}
    for task_id, task in tasks.items():
        oracle = Path(task['oracle_script']).parent; fixture = oracle.parent / 'base'
        fixture_inventory = r.inventory(fixture); registered_base = r.inventory(task['base_snapshot'])
        require(fixture_inventory == registered_base, 'Current grader fixture differs from registered task base')
        dependencies[task_id] = {'oracle_inventory': r.inventory(oracle), 'grader_base_inventory': fixture_inventory,
                                'registered_task_base_inventory': registered_base}
    expected_seal = {'registration_sha256': registration_sha256,
            'sources': {row['trial_id']: row['artifact_bindings'].get('result_sha256') for row in rows if row['eligible']},
            'grader_dependencies': dependencies}
    if output.exists():
        seal = r.read(output / 'input-seal.json')
        require(seal == expected_seal, 'Recheck parent/source input seal changed')
    else:
        output.mkdir(parents=True)
        save_matching(output / 'input-seal.json', json.dumps(expected_seal, indent=2).encode() + b'\n')
    checked = agreements = disagreements = unknown = 0
    for row in rows:
        if not row['eligible']: continue
        directory = output / row['trial_id']; snapshot = study / 'trials' / row['trial_id'] / 'result_snapshot'
        task = tasks[row['task_id']]; adapter = r.route(arms[row['arm_id']]); script = Path(task['oracle_script'])
        expected_source = row['artifact_bindings']['result_sha256']; expected_oracle = r.digest(r.inventory(script.parent))
        fixture = script.parent.parent / 'base'; expected_base = r.digest(dependencies[row['task_id']]['grader_base_inventory'])
        if (directory / 'receipt.json').exists():
            record = r.read(directory / 'receipt.json')
        else:
            require(not directory.exists(), 'Prior started recheck is unknown; refusing automatic rerun')
            directory.mkdir(); save_matching(directory / 'started.json', b'{"status":"started"}\n')
            require(adapter.frozen.base.tree_digest(snapshot) == expected_source, 'Source changed before fresh recheck')
            grade = r.invoke_oracle(adapter, script, snapshot, directory)
            record = {'source_before': expected_source, 'source_after': adapter.frozen.base.tree_digest(snapshot),
                      'oracle_tree_before': expected_oracle, 'oracle_tree_after': r.digest(r.inventory(script.parent)),
                      'grader_base_before': expected_base, 'grader_base_after': r.digest(r.inventory(fixture)),
                      'oracle_tree_sha256': expected_oracle, 'oracle_script_sha256': r.sha(script), 'grade': grade,
                      'scope': 'Fresh source-associated selected behavioral check; no claim about historical grader input'}
            save_matching(directory / 'receipt.json', json.dumps(record, indent=2).encode() + b'\n')
        require(record['source_before'] == record['source_after'] == expected_source == adapter.frozen.base.tree_digest(snapshot), 'Fresh recheck source binding drift')
        require(record['oracle_tree_sha256'] == r.digest(r.inventory(script.parent)) == expected_oracle and record['oracle_script_sha256'] == r.sha(script), 'Fresh recheck oracle drift')
        require(record['oracle_tree_before'] == record['oracle_tree_after'] == expected_oracle, 'Oracle script/modules changed during fresh recheck')
        require(record['grader_base_before'] == record['grader_base_after'] == expected_base == r.digest(r.inventory(fixture)), 'Grader baseline dependency drift')
        current = oracle_truth(record['grade'], directory); row['current_source_acceptance'] = current
        agreement = current is row['oracle_passed'] if current is not None and row['oracle_passed'] is not None else None
        row['current_recheck_agrees_with_recorded_grade'] = agreement
        row['current_recheck_bindings'] = {'receipt_sha256': r.sha(directory / 'receipt.json'), 'source_sha256': expected_source,
            'oracle_tree_sha256': expected_oracle, 'oracle_script_sha256': r.sha(script),
            'grader_base_sha256': expected_base, 'registered_task_base_sha256': r.digest(dependencies[row['task_id']]['registered_task_base_inventory']),
            'stdout_sha256': record['grade']['stdout_sha256'], 'stderr_sha256': record['grade']['stderr_sha256']}
        row['oracle_association_status'] = 'Historical input binding absent; fresh current-source recheck is separately bound'
        checked += 1; agreements += agreement is True; disagreements += agreement is False; unknown += agreement is None
    return {'checked': checked, 'known_agreements': agreements, 'known_disagreements': disagreements, 'agreement_unknown': unknown,
            'primary_recorded_grades_changed': False, 'recheck_outcomes_not_substituted_into_primary_contrasts': True,
            'input_seal_sha256': r.sha(output / 'input-seal.json')}


def analyze(study, recheck_output=None):
    study = Path(study).resolve(); payload = r.verify(study); r.require_controls(study, payload)
    tasks = {t['task_id']: t for t in r.read(payload['config']['manifest'])['tasks']}
    arms = {a['id']: a for a in payload['config']['arms']}
    require(set(arms) == set(ARMS), 'Registered arm identities differ from planned contrasts')
    requests = r.read(study / 'requests.json'); validate_roster(requests, tasks, arms)
    closure = r.read(study / 'results.json')
    require(len(closure) == 48 and len({q.get('trial_id') for q in closure}) == 48, 'Closed48 normalized closure missing/duplicated')
    lookup = {q['trial_id']: q for q in closure}; rows = []
    for request in requests:
        directory = study / 'trials' / request['trial_id']; arm = arms[request['arm_id']]
        if not (directory / 'receipt.json').exists():
            rows.append(missing_row(request, arm, lookup.get(request['trial_id']), directory)); continue
        raw = r.read(directory / 'receipt.json')
        require(lookup.get(request['trial_id']) == raw, 'Normalized closure differs from current raw receipt')
        rows.append(row(directory, request, tasks[request['task_id']], arm, payload, study, r.route(arm)))
    rechecks = current_rechecks(study, recheck_output, rows, tasks, arms, r.sha(study / 'registration.json')) if recheck_output is not None else None
    return {'schema_version': 1, 'assigned': 48, 'registration_sha256': r.sha(study / 'registration.json'), 'requests_sha256': r.sha(study / 'requests.json'),
            'controls_sha256': r.sha(study / 'oracle-controls' / 'results.json'), 'closure_sha256': r.sha(study / 'results.json'),
            'analyzer_sha256': r.sha(__file__), 'analyzer_tests_sha256': r.sha(HERE / 'test_analyze.py'), 'rows': rows, 'current_recheck_summary': rechecks, **summarize(rows),
            'limitations': ['Six purposively chosen familiar historical tasks in one repository, two repeats',
                'Intervals are exploratory task-cluster resampling, not population inference/significance or a vendor ranking',
                'Ineligible cases lack raw software oracle verdicts; zero verified evidence is not semantic failure',
                'Primary verified-success label means recorded eligible oracle success; historical grader did not record an input digest',
                'Separate fresh source rechecks establish current selected behavior and agreement, never rewrite primary records',
                'Historical main registration did not separately seal the grader sibling base; current rechecks bind it and require registered-task-base equivalence',
                'Costs are CLI estimates with missing telemetry; no billed-cost, quota-pooling or saving claim',
                'Maintainability jury, intake and eight followup probes are separate studies and not pooled',
                'Frozen enhanced candidate1 is evaluated; later necessary-versus-sufficient guide correction is outside this intervention',
                'Current recorded-byte custody only; original process groups are not complete descendant containment']}


def save_matching(path, data):
    path = Path(path)
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == data, 'Refusing to overwrite nonmatching output: ' + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)


def export(study, output, result):
    study, output = Path(study).resolve(), Path(output).resolve()
    public = {key: value for key, value in result.items() if key in TOP_KEYS}
    public['rows'] = [{key: value for key, value in row.items() if key in ROW_KEYS} for row in result['rows']]
    safe = json.dumps(public, indent=2, allow_nan=False).encode() + b'\n'
    for marker in (str(study).encode(), str(Path.home()).encode(), b'-----BEGIN PRIVATE KEY-----', b'-----BEGIN RSA PRIVATE KEY-----'):
        require(marker not in safe, 'Public JSON contains a private path/key marker')
    patches = {}; missing = []; excluded = {}
    for row in result['rows']:
        if not row['patch_bound']:
            missing.append(row['trial_id']); continue
        source = study / 'trials' / row['trial_id'] / 'submitted.patch'
        bound(source, row['artifact_bindings']['patch_sha256'], 'Export production patch')
        patch_bytes = source.read_bytes()
        markers = (str(study).encode(), str(Path.home()).encode(), b'/private/var/folders/', b'/var/folders/', b'/tmp/', b'/private/tmp/',
                   b'-----BEGIN PRIVATE KEY-----', b'-----BEGIN RSA PRIVATE KEY-----')
        if any(marker in patch_bytes for marker in markers):
            missing.append(row['trial_id']); excluded[row['trial_id']] = 'Private path/key marker; exact patch retained privately, not redacted'; continue
        patches['patches/' + row['trial_id'] + '.patch'] = patch_bytes
    expected = {'analysis.json', 'artifact-hashes.json'} | set(patches)
    if output.exists():
        for path in output.rglob('*'):
            require(not path.is_symlink(), 'Export contains a symlink')
            relative = path.relative_to(output).as_posix()
            require(relative == 'patches' if path.is_dir() else path.is_file() and relative in expected, 'Export contains unrelated/private files')
    save_matching(output / 'analysis.json', safe)
    artifacts = {'analysis.json': r.sha(output / 'analysis.json')}
    for relative, patch_bytes in patches.items():
        save_matching(output / relative, patch_bytes); artifacts[relative] = r.sha(output / relative)
    inventory = {'files': artifacts, 'copied_patches': len(artifacts) - 1, 'assigned': 48, 'missing_or_unbound_patches': missing,
                 'privacy_excluded_patches': excluded,
                 'excluded': ['Raw prompts/prose, user paths, streams, stderr, private source trees, authentication material'],
                 'scope': 'Patch bytes preserve original artifacts; source correctness is the selected oracle, not reconstruction or maintainability proof'}
    save_matching(output / 'artifact-hashes.json', json.dumps(inventory, indent=2).encode() + b'\n')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--recheck-output', type=Path, help='Separate new directory for source-bound CPU rechecks; never changes primary records')
    args = parser.parse_args(); result = analyze(args.study, args.recheck_output)
    save_matching(args.output, json.dumps(result, indent=2, allow_nan=False).encode() + b'\n')
    if args.export: export(args.study, args.export, result)
