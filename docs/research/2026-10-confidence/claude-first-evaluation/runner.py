#!/usr/bin/env python3
"""A new sealed, single-attempt comparison; never rewrites previous studies.

Shared operational tools/runtime, selected full policy trees, explicit models.
Native subscription clients authenticate normally; confined tool children do not.
The historical oracle measures selected behavior, not whole-task maintainability.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / 'pr-benchmark'
EQUIVALENCE = (
    ('tweed-pr40', ('bonaparte',), 'DISABLE_SOFT_PHASE_BUDGET', 'UNBOUNDED_CHOICE'),
    ('tweed-pr39', ('bonaparte', 'bonaparte_native.py'), '_started_thread_ids', '_observed_children'),
)


def load(path):
    spec = importlib.util.spec_from_file_location('new_comparison_' + uuid.uuid4().hex, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def cli_versions(backends=('claude', 'codex')):
    return {name: subprocess.run([name, '--version'], capture_output=True, text=True, check=True, timeout=10).stdout.strip() for name in backends}


def inventory(root):
    """Regular-file identity including mode; empty directories are not inputs."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Input tree missing: ' + str(root))
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Input symlink refused: ' + str(path))
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {'sha256': sha(path), 'mode': path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise ValueError('Input special file refused: ' + str(path))
    return files


def route(arm):
    """Fresh private imported namespaces per invocation; no shared model globals."""
    adapter = load(BENCH / 'hybrid_v2.py')
    if arm['backend'] == 'claude':
        adapter.frozen.base.MODEL = arm['model']
        adapter.frozen.base.EFFORT = arm['effort']
    else:
        adapter.frozen.backend.MODEL = arm['model']
        adapter.frozen.backend.EFFORT = arm['effort']
    return adapter


def mount(base, toolkit, policy, workspace):
    """One instruction tree, shared executable/assets bytes across all arms."""
    target = workspace / '.protocol'
    base.safe_copy(Path(toolkit), target)
    for name in ('SKILL.md', 'references'):
        old = target / name
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
        source = Path(policy) / name
        if source.is_dir():
            base.safe_copy(source, old)
        elif source.is_file():
            shutil.copy2(source, old)
        elif name == 'SKILL.md':
            raise ValueError('Selected policy SKILL.md absent')
    return target


def terminal(stage):
    if stage.get('backend') == 'claude':
        raw = stage.get('terminal')
        if not isinstance(raw, dict) or raw.get('type') != 'result' or raw.get('subtype') != 'success' or raw.get('is_error') is not False:
            return None
        value = raw.get('structured_output')
    elif stage.get('backend') == 'codex':
        if (stage.get('status') != 'completed' or stage.get('errors') != [] or
            stage.get('native_guard_violated') is not False or stage.get('unexpected_native_calls') != [] or stage.get('unexpected_mcp_calls') != []):
            return None
        value = stage.get('structured_output')
    else:
        return None
    if not isinstance(value, dict) or set(value) != {'complete', 'summary', 'remaining'}:
        return None
    if type(value['complete']) is not bool or not isinstance(value['summary'], str) or not isinstance(value['remaining'], list) or not all(isinstance(x, str) for x in value['remaining']):
        return None
    return value


def qualification(stage, local, arm, adapter):
    """Derive eligibility from facts, never from a recorded PASS alone."""
    failures = []
    if stage.get('backend') != arm['backend']:
        failures.append('assigned_backend_mismatch')
    if local.get('passed') is not True:
        failures.append('local_transport_unqualified')
    for field, expected in [('process_cleanup_scope', 'original_process_group'), ('detached_descendants_contained', False), ('stream_changed_during_cleanup', False)]:
        if stage.get(field) != expected or type(stage.get(field)) is not type(expected):
            failures.append(field + '_unqualified')
    if type(stage.get('guarded_new_session_processes')) is not int or stage.get('guarded_new_session_processes', 0) < 1:
        failures.append('process_ownership_unqualified')
    if type(stage.get('timed_out')) is not bool or type(stage.get('process_exit')) is not int:
        failures.append('lifecycle_unknown')
    if stage.get('timed_out') is True or stage.get('process_exit') != 0:
        failures.append('stage_did_not_finish')
    if stage.get('native_guard_violated') or stage.get('unexpected_native_calls') or stage.get('unexpected_mcp_calls'):
        failures.append('native_tool_guard_violated')
    transport_alias = 'opus' if arm['backend'] == 'claude' else 'astra'
    facts = adapter.effective_inventory(dict(stage, assigned_model=transport_alias), local)
    if facts.get('passed') is not True:
        failures.append('effective_inventory_unqualified')
    if arm['backend'] == 'claude':
        models = stage.get('observed_assistant_models')
        if models != [arm['model']]:
            failures.append('exact_observed_model_mismatch_or_unknown')
    else:
        if stage.get('model_requested') != arm['model']:
            failures.append('requested_codex_model_mismatch')
        observed = stage.get('observed_models'); actual = stage.get('actual_model'); attribution = stage.get('model_attribution')
        if not isinstance(observed, list) or not all(isinstance(model, str) for model in observed):
            failures.append('codex_observed_model_metadata_unknown')
        elif any(model != arm['model'] for model in observed) or actual is not None and actual != arm['model']:
            failures.append('observed_codex_model_mismatch')
        elif attribution == 'event_observed' and (actual != arm['model'] or observed != [arm['model']]):
            failures.append('observed_codex_model_attribution_inconsistent')
        elif attribution == 'requested_only' and (actual is not None or observed):
            failures.append('requested_only_codex_model_attribution_inconsistent')
        elif attribution not in ('event_observed', 'requested_only'):
            failures.append('codex_model_attribution_unknown')
    if terminal(stage) is None:
        failures.append('terminal_missing_or_invalid')
    return {'eligible': not failures, 'failures': failures, 'inventory': facts,
            'model_attribution': 'assistant_event_observed' if arm['backend'] == 'claude' else stage.get('model_attribution', 'requested_only'),
            'actual_model': arm['model'] if arm['backend'] == 'claude' and stage.get('observed_assistant_models') == [arm['model']] else stage.get('actual_model')}


def material(config):
    files = {str(Path(config['manifest']).resolve()): sha(config['manifest']), str(Path(__file__).resolve()): sha(__file__),
             str(HERE / 'test_runner.py'): sha(HERE / 'test_runner.py')}
    files.update({str(p): sha(p) for p in sorted(BENCH.glob('*.py'))})
    trees = {str(Path(config['toolkit_directory']).resolve()): inventory(config['toolkit_directory'])}
    tasks = read(config['manifest'])['tasks']
    for task in tasks:
        for path in (task['base_snapshot'], task['head_snapshot'], str(Path(task['oracle_script']).parent)):
            trees[str(Path(path).resolve())] = inventory(path)
    for arm in config['arms']:
        trees[str(Path(arm['policy_directory']).resolve())] = inventory(arm['policy_directory'])
        files[str(Path(arm['prompt_file']).resolve())] = sha(arm['prompt_file'])
    for key in ('codex_catalog', 'codex_qualification'):
        files[str(Path(config[key]).resolve())] = sha(config[key])
    return {'files': files, 'trees': trees}


def verify(study):
    seal = read(study / 'registration.json')
    if digest(seal['payload']) != seal['payload_sha256']:
        raise ValueError('Registration content changed')
    payload = seal['payload']
    for path, expected in payload['material']['files'].items():
        if sha(path) != expected:
            raise ValueError('Registered file changed: ' + path)
    for path, expected in payload['material']['trees'].items():
        if inventory(path) != expected:
            raise ValueError('Registered tree changed: ' + path)
    if sha(study / 'requests.json') != payload['requests_sha256']:
        raise ValueError('Registered requests changed')
    if 'cli_versions' in payload and cli_versions() != payload['cli_versions']:
        raise ValueError('Registered CLI versions changed')
    return payload


def prepare(config_path, study):
    config_path, study = Path(config_path).resolve(), Path(study).resolve()
    if study.exists():
        raise ValueError('Preparation requires a new output directory')
    config = read(config_path)
    for key in ('manifest', 'toolkit_directory', 'codex_catalog', 'codex_qualification'):
        config[key] = str(Path(config[key]).resolve())
    if config.get('repeats') != 2 or config.get('seconds') != 240 or config.get('claude_budget_usd') != 2:
        raise ValueError('This comparison requires 2 repeats, 240 seconds and Claude USD guard 2')
    if config.get('effort', 'medium') != 'medium':
        raise ValueError('All cohort routes request medium effort')
    arms = config['arms']
    if len(arms) != 4 or len({a['id'] for a in arms}) != 4:
        raise ValueError('Four unique arms required')
    for arm in arms:
        if not isinstance(arm.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9-]*', arm['id']):
            raise ValueError('Arm identities must be safe lowercase hyphenated names')
        arm['effort'] = config.get('effort', 'medium')
        for key in ('policy_directory', 'prompt_file'):
            arm[key] = str(Path(arm[key]).resolve())
        permitted = {'claude': {'claude-opus-5-5', 'claude-haiku-5-5'}, 'codex': {'gpt-6.1-sol', 'gpt-6-astra'}}
        if arm.get('backend') not in permitted or arm.get('model') not in permitted[arm['backend']]:
            raise ValueError('Unregistered backend/model')
        if not (Path(arm['policy_directory']) / 'SKILL.md').is_file():
            raise ValueError('Each full policy tree needs SKILL.md')
    tasks = read(config['manifest'])['tasks']
    if len(tasks) != 6 or {t['task_id'] for t in tasks} != {'tweed-pr' + str(n) for n in (32, 31, 40, 34, 39, 35)}:
        raise ValueError('Six distinct historical tasks required')
    if [a['model'] for a in arms].count('claude-opus-5-5') != 2 or [a['model'] for a in arms].count('claude-haiku-5-5') != 1 or sum(a['backend'] == 'codex' for a in arms) != 1:
        raise ValueError('Requires two Opus arms, one Haiku and one Codex')
    codex_arm = next(a for a in arms if a['backend'] == 'codex')
    availability = read(config['codex_qualification'])
    if availability.get('qualified') is not True or availability.get('model_requested') != codex_arm['model'] or availability.get('cohort') is not False:
        raise ValueError('A fresh positive noncohort receipt for the selected Codex route is required')
    versions = cli_versions()
    if availability.get('cli_versions', {}).get('codex') not in (None, versions['codex']):
        raise ValueError('Selected Codex qualification used a different CLI version')
    study.mkdir(parents=True)
    try:
        adapter = route(arms[0])
        confinement = adapter.frozen.base.sandbox_check(study / 'confinement')
        requests = []
        for repeat in (1, 2):
            for task in tasks:
                for arm in arms:
                    prompt = ('Read .protocol/SKILL.md and its relevant references. '
                              'This is one bounded implementation attempt. Peer delegation is unavailable in this comparison. '
                              'Your final complete flag means the requested implementation is complete within this snapshot, not that all Confidence Protocol release gates passed. '
                              'Only facts in this snapshot and executed controlled checks may support claims.\nTask:\n' + task['prompt'] +
                              '\nVisible baseline commands:\n' + json.dumps(task['test_commands']) +
                              '\nSelected prompt policy:\n' + Path(arm['prompt_file']).read_text())
                    requests.append({'trial_id': task['task_id'] + '--' + arm['id'] + '--r' + str(repeat), 'task_id': task['task_id'], 'arm_id': arm['id'], 'repeat': repeat, 'prompt': prompt})
        random.Random(6102030).shuffle(requests)
        write(study / 'requests.json', requests)
        inventories = {}
        for arm in arms:
            runtime = route(arm)
            workspace = study / ('offline-workspace-' + arm['id']); workspace.mkdir()
            local = runtime.local_mcp_probe('opus' if arm['backend'] == 'claude' else 'astra', workspace, study / ('offline-' + arm['id']), readonly=False)
            if local.get('passed') is not True:
                raise ValueError('Route local tool transport unqualified: ' + arm['id'])
            if arm['backend'] == 'codex':
                backend = runtime.frozen.backend
                catalog = study / ('catalog-' + arm['id'] + '.json')
                backend.capability_catalog(config['codex_catalog'], catalog)
                workspace = study / 'inventory-workspace'; workspace.mkdir(exist_ok=True)
                probe = backend.inventory_probe(workspace, study / ('inventory-' + arm['id']), catalog, with_mcp=True)
                if probe.get('inventory', {}).get('passed') is not True:
                    raise ValueError('Codex declared inventory unqualified')
                inventories[arm['id']] = {'catalog': str(catalog), 'receipt': probe}
        materials = material(config)
        materials['files'][str(config_path)] = sha(config_path)
        for value in inventories.values():
            materials['files'][value['catalog']] = sha(value['catalog'])
        payload = {'config': config, 'material': materials, 'requests_sha256': sha(study / 'requests.json'), 'inventories': inventories,
                   'confinement': confinement, 'cli_versions': versions, 'prepared_at_unix': time.time(), 'planned_cells': 48,
                   'limitations': ['Historical known task set; no representative generalization', 'One bounded attempt; no whole-CP autonomy claim',
                                  'Codex actual model may be requested-only; offline inventory is not live wire parity',
                                  'Claude USD guard has no matched Codex dollar guard; CLI costs are not bills',
                                  'Original-process-group cleanup does not contain setsid escapees']}
        write(study / 'registration.json', {'payload': payload, 'payload_sha256': digest(payload)})
    except Exception:
        write(study / 'preparation-failed.json', {'failed': True, 'time': time.time()})
        raise
    return payload


def deny_reviews(control, workspace, callback, deadline):
    for path in control.glob('*.review-request.json'):
        response = path.with_name(path.name.replace('.review-request', '.review-response'))
        if not response.exists():
            write(response, {'available': False, 'reason': 'Single-attempt comparison; no recursive peer extension'})
    return []


def run_cell(request, task, arm, payload, study):
    verify(study)
    out = study / 'trials' / request['trial_id']
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.mkdir()
    except FileExistsError:
        return {'trial_id': request['trial_id'], 'status': 'preserved_previously_started'}
    write(out / 'started.json', {'request_sha256': digest(request), 'started_at_unix': time.time()})
    receipt = {'trial_id': request['trial_id'], 'task_id': request['task_id'], 'arm_id': request['arm_id'], 'repeat': request['repeat'],
               'request_sha256': digest(request), 'model_requested': arm['model'], 'backend': arm['backend'], 'eligible': False, 'accepted': None}
    try:
        adapter = route(arm); base = adapter.frozen.base
        # Service request_review immediately with an explicit unavailable result.
        adapter.frozen.backend.service_reviews = deny_reviews
        original_service = base.service_commands
        def service(control, workspace, temporary, readonly, deadline):
            deny_reviews(control, workspace, None, deadline)
            return original_service(control, workspace, temporary, readonly, deadline)
        base.service_commands = service
        with tempfile.TemporaryDirectory(prefix='cp-prompt-model-') as temporary:
            job = Path(temporary).resolve(); workspace = job / 'workspace'
            base.safe_copy(Path(task['base_snapshot']), workspace)
            for pattern in ('AGENTS.md', 'CLAUDE.md', '.claude', '.codex', '.agents', '.git'):
                for path in list(workspace.rglob(pattern)):
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
            mount(base, payload['config']['toolkit_directory'], arm['policy_directory'], workspace)
            (workspace / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
            ignore = workspace / '.gitignore'
            ignore.write_text((ignore.read_text() if ignore.exists() else '') + '\n.trial-tmp/\n.confidence/\n')
            scratch = workspace / '.trial-tmp'; scratch.mkdir(exist_ok=True)
            for args in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Comparison', '-c', 'user.email=comparison@example.invalid', 'commit', '-qm', 'Frozen base']):
                subprocess.run([base.GIT, '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *args], cwd=workspace, env=base.safe_env(workspace, scratch), capture_output=True, check=True)
            before = base.tree_digest(workspace)
            alias = 'opus' if arm['backend'] == 'claude' else 'astra'
            local = adapter.local_mcp_probe(alias, workspace, out / 'qualification', readonly=False)
            if local.get('passed') is not True:
                raise ValueError('Local MCP transport failed before inference')
            deadline = time.time() + payload['config']['seconds']
            if arm['backend'] == 'claude':
                stage = base.claude_call(workspace, out / 'main', request['prompt'], payload['config']['claude_budget_usd'], payload['config']['seconds'], deadline)
            else:
                info = payload['inventories'][arm['id']]
                stage = adapter.frozen.backend.codex_call(workspace, out / 'main', request['prompt'], catalog=Path(info['catalog']), timeout=payload['config']['seconds'], deadline=deadline,
                                                         inventory_receipt=info['receipt'], review_callback=lambda *_: {'available': False})
            stage['backend'] = arm['backend']
            q = qualification(stage, local, arm, adapter)
            snapshot = out / 'result_snapshot'; base.safe_copy(workspace, snapshot)
            violations = base.scope_diff(Path(task['base_snapshot']), snapshot, task['production_paths'])
            patch, submitted = base.build_patch(Path(task['base_snapshot']), snapshot, out / 'submitted.patch', task['production_paths'])
            receipt.update(stage=stage, qualification=q, source_sha256_at_launch=before, source_sha256_after=base.tree_digest(snapshot),
                           result_sha256=base.tree_digest(snapshot), patch_sha256=hashlib.sha256(patch).hexdigest(), submitted_paths=submitted,
                           scope_violations=violations, eligible=q['eligible'] and not violations, status='completed', terminal=terminal(stage),
                           registration_sha256=sha(study / 'registration.json'), controls_sha256=sha(study / 'oracle-controls' / 'results.json'))
            events = out / 'main' / 'tool-events.jsonl'
            receipt['tool_events_sha256'] = sha(events) if events.exists() else None
            # Existing held-out evaluator independently reconstructs production
            # and trusted tests; its files are outside actor/tool access.
            if receipt['eligible']:
                verify(study)
                oracle = invoke_oracle(adapter, Path(task['oracle_script']), snapshot, out)
                receipt.update(oracle=oracle, accepted=oracle['oracle_passed'])
    except Exception as error:
        receipt.update(status='infrastructure_or_artifact_error', error=type(error).__name__ + ': ' + str(error))
    write(out / 'receipt.json', receipt)
    return receipt


def run(study, workers=2):
    study = Path(study).resolve(); payload = verify(study)
    require_controls(study, payload)
    tasks = {t['task_id']: t for t in read(payload['config']['manifest'])['tasks']}
    arms = {a['id']: a for a in payload['config']['arms']}
    requests = read(study / 'requests.json')
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_cell, r, tasks[r['task_id']], arms[r['arm_id']], payload, study) for r in requests]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(json.dumps({k: result.get(k) for k in ('trial_id', 'status', 'eligible', 'accepted')}), flush=True)
    rows = []
    for r in requests:
        path = study / 'trials' / r['trial_id'] / 'receipt.json'
        rows.append(read(path) if path.exists() else dict(r, status='started_unknown' if path.parent.exists() else 'never_started', accepted=None, eligible=False))
    write(study / 'results.json', rows)
    return rows


def require_controls(study, payload):
    """Require actual pre-run grader controls, bound to current output bytes."""
    value = read(study / 'oracle-controls' / 'results.json')
    expected = {(t['task_id'], side) for t in read(payload['config']['manifest'])['tasks'] for side in ('base', 'head')}
    rows = value.get('results', [])
    identities = [(row.get('task_id'), row.get('side')) for row in rows]
    if value.get('passed') is not True or len(identities) != len(expected) or set(identities) != expected:
        raise ValueError('Missing, duplicated or failed current grader controls')
    for row in rows:
        if row.get('oracle_passed') is not (row['side'] == 'head'):
            raise ValueError('Current grader control verdict differs')
        directory = study / 'oracle-controls' / (row['task_id'] + '-' + row['side'])
        if sha(directory / 'grader.stdout') != row['stdout_sha256'] or sha(directory / 'grader.stderr') != row['stderr_sha256']:
            raise ValueError('Current grader control output changed')
    equivalents = value.get('equivalent_controls', [])
    if len(equivalents) != len(EQUIVALENCE) or {row.get('task_id') for row in equivalents} != {case[0] for case in EQUIVALENCE}:
        raise ValueError('Missing or duplicated current equivalence controls')
    for row in equivalents:
        directory = study / 'oracle-controls' / (row['task_id'] + '-equivalent')
        if row.get('oracle_passed') is not True or digest(inventory(directory / 'snapshot')) != row.get('snapshot_inventory_sha256'):
            raise ValueError('Current equivalence control failed or source changed')
        if sha(directory / 'grader.stdout') != row['stdout_sha256'] or sha(directory / 'grader.stderr') != row['stderr_sha256']:
            raise ValueError('Current equivalence control output changed')


def controls(study):
    """Fresh baseline/head and representation-independent rename controls."""
    study = Path(study).resolve(); payload = verify(study); adapter = route(payload['config']['arms'][0])
    root = study / 'oracle-controls'
    root.mkdir(exist_ok=False)
    results = []
    for task in read(payload['config']['manifest'])['tasks']:
        for side in ('base', 'head'):
            directory = root / (task['task_id'] + '-' + side); directory.mkdir()
            value = invoke_oracle(adapter, Path(task['oracle_script']), Path(task[side + '_snapshot']), directory)
            results.append(dict(task_id=task['task_id'], side=side, **value))
    equivalents = []
    tasks = {t['task_id']: t for t in read(payload['config']['manifest'])['tasks']}
    for task_id, paths, old, new in EQUIVALENCE:
        task = tasks[task_id]; directory = root / (task_id + '-equivalent'); directory.mkdir()
        snapshot = directory / 'snapshot'; adapter.frozen.base.safe_copy(Path(task['head_snapshot']), snapshot)
        counts = {}
        for path in paths:
            source = snapshot / path; text = source.read_text(); counts[path] = text.count(old)
            source.write_text(text.replace(old, new))
        if sum(counts.values()) == 0:
            raise ValueError('Equivalence intervention did not change any source')
        value = invoke_oracle(adapter, Path(task['oracle_script']), snapshot, directory)
        equivalents.append(dict(task_id=task_id, rename={'from': old, 'to': new, 'occurrences': counts},
                                snapshot_inventory_sha256=digest(inventory(snapshot)), **value))
    passed = all(row['oracle_passed'] is (row['side'] == 'head') for row in results) and all(row['oracle_passed'] is True for row in equivalents)
    write(root / 'results.json', {'passed': passed, 'results': results, 'equivalent_controls': equivalents,
                                'cli_versions': cli_versions(), 'registered_tool_schemas': adapter.frozen.base.digest_json(adapter.frozen.base.TOOL_SCHEMAS),
                                'oracle_scope': 'Fresh base/head/rename execution outside worker source scope; no hosted model calls'})
    if not passed:
        raise ValueError('Oracle baseline/head controls failed')
    return results


def invoke_oracle(adapter, script, snapshot, directory):
    """Independent oracle plus owned-child cleanup and final output hash binding."""
    grader = adapter.frozen.grader; processes = adapter.frozen.processes
    if not isinstance(grader.subprocess, processes.SubprocessProxy):
        grader.subprocess = processes.SubprocessProxy(grader.subprocess)
    with processes.ProcessGuard():
        result = grader.invoke_oracle(script, snapshot, directory)
    old = (result['stdout_sha256'], result['stderr_sha256'])
    result.update(stdout_sha256=sha(directory / 'grader.stdout'), stderr_sha256=sha(directory / 'grader.stderr'),
                  process_cleanup_scope='original_process_group', detached_descendants_contained=False)
    result['output_changed_during_cleanup'] = old != (result['stdout_sha256'], result['stderr_sha256'])
    if result['output_changed_during_cleanup']:
        result['oracle_passed'] = None
    return result


def qualify_route(arm, toolkit, output, catalog_source=None, seconds=90, budget=2):
    """Explicit noncohort live availability/toy call. No implicit fallback.

    Caller chooses one exact model. The result cannot select a different model
    or resume/retry itself. All source is a one-line toy, no real-PR exposure.
    """
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    arm = dict(arm, effort=arm.get('effort', 'medium'))
    adapter = route(arm); base = adapter.frozen.base
    receipt = {'backend': arm['backend'], 'model_requested': arm['model'], 'qualified': False, 'cohort': False,
               'cli_versions': cli_versions((arm['backend'] if arm['backend'] == 'claude' else 'codex',)), 'controller_sha256': sha(__file__)}
    try:
        with tempfile.TemporaryDirectory(prefix='cp-route-availability-') as name:
            workspace = Path(name).resolve() / 'workspace'; workspace.mkdir()
            (workspace / 'toy.py').write_text('def answer():\n    return 1\n')
            mount(base, toolkit, arm['policy_directory'], workspace)
            local = adapter.local_mcp_probe('opus' if arm['backend'] == 'claude' else 'astra', workspace, output / 'offline', readonly=False)
            if local.get('passed') is not True:
                raise ValueError('Offline route transport unqualified')
            prompt = ('Read .protocol/SKILL.md. This is a noncohort route qualification toy, not a full CP delivery. '
                      'Use the controlled tools to change toy.answer() to return 2. Run python3 -B -c "from toy import answer; assert answer()==2". '
                      'Do not request peer review. Return the required JSON with complete describing only this toy.')
            deadline = time.time() + seconds
            if arm['backend'] == 'claude':
                stage = base.claude_call(workspace, output / 'main', prompt, budget, seconds, deadline)
            else:
                if catalog_source is None:
                    raise ValueError('Codex qualification requires a metadata catalog')
                backend = adapter.frozen.backend; catalog = output / 'capabilities.json'
                backend.capability_catalog(catalog_source, catalog)
                probe = backend.inventory_probe(workspace, output / 'inventory', catalog, with_mcp=True)
                if probe.get('inventory', {}).get('passed') is not True:
                    raise ValueError('Codex inventory unqualified')
                stage = backend.codex_call(workspace, output / 'main', prompt, catalog=catalog, timeout=seconds, deadline=deadline,
                                           inventory_receipt=probe, review_callback=lambda *_: {'available': False})
            stage['backend'] = arm['backend']; q = qualification(stage, local, arm, adapter)
            # Owner-held actual assertion, never trusting model's declared success.
            control = output / 'owner-assertion'; control.mkdir()
            scratch = output / 'owner-scratch'; scratch.mkdir()
            profile = base.sandbox_profile(workspace, scratch, readonly=True)
            check = base.bounded_process(['/usr/bin/sandbox-exec', '-p', profile, os.sys.executable, '-B', '-c', 'from toy import answer; assert answer()==2'],
                                         cwd=workspace, env=base.safe_env(workspace, scratch), timeout=10, output_prefix=control / 'check')
            receipt.update(stage=stage, qualification=q, owner_assertion=check, qualified=q['eligible'] and check['exit_code'] == 0 and not check['timed_out'])
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
    write(output / 'receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'controls', 'run', 'qualify'])
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--workers', type=int, default=2, choices=[1, 2])
    parser.add_argument('--backend', choices=['claude', 'codex'])
    parser.add_argument('--model')
    parser.add_argument('--toolkit', type=Path)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--catalog', type=Path)
    args = parser.parse_args()
    if args.action == 'qualify':
        if None in (args.backend, args.model, args.toolkit, args.policy):
            parser.error('qualify requires --backend --model --toolkit --policy; Codex also --catalog')
        value = qualify_route({'backend': args.backend, 'model': args.model, 'policy_directory': str(args.policy)}, args.toolkit, args.study, args.catalog)
        print(json.dumps({k: value.get(k) for k in ('model_requested', 'qualified', 'error')}))
        raise SystemExit(0 if value['qualified'] else 1)
    elif args.action == 'prepare':
        if args.config is None:
            parser.error('--config is required for prepare')
        prepare(args.config, args.study)
    elif args.action == 'controls':
        controls(args.study)
    else:
        run(args.study, args.workers)
