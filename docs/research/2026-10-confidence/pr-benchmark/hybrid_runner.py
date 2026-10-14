#!/usr/bin/env python3
"""Separate fixed-stage Astra/Opus experiment; never resumes the old cohort.

The coordinator performs reviews outside the main subprocess's clock. This
tests provider routing. A separate toy tests a model-triggered review callback.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load('hybrid_frozen_base', 'runner.py')
backend = load('hybrid_backend', 'cross_backend.py')
grader = load('hybrid_grader_helpers', 'grading_adapter.py')
backend.MODEL = 'gpt-6-astra'
processes = load('hybrid_process_guards', 'hybrid_process.py')
processes.install(base, backend)


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requests(protocol, manifest):
    tasks = sorted(manifest['tasks'], key=lambda t: t['task_id'])
    random.Random(6102028).shuffle(tasks)
    arms = protocol['arms']
    result = []
    for index, task in enumerate(tasks):
        for repeat in (1, 2):
            offset = (index + 2 * (repeat - 1)) % 4
            order = arms[offset:] + arms[:offset]
            if repeat == 2:
                order = list(reversed(order))
            for arm in order:
                review_terminal = ('\nFor this reviewer episode, complete means the review assignment is finished, '
                                   'not that the software task is correct or complete. Put findings, proposed '
                                   'checks and scope limits in summary; put only unfinished required review '
                                   'work in remaining. You must not implement the task.')
                common = ('Task requirements:\n' + task['prompt'] +
                          '\nAllowed production paths:\n' + json.dumps(task['production_paths']) +
                          '\nThis bounded replay supports edits to those baseline files and new ordinary '
                          'root Python helpers. Preserve the configured baseline production files; '
                          'their deletion is not supported by this replay projection.' +
                          '\nVisible baseline checks:\n' + json.dumps(task['test_commands']) +
                          '\nCommon workflow:\n' + protocol['common_workflow_instruction'] +
                          '\nReturn the required complete/summary/remaining JSON truthfully. '
                          'Put substantive findings and observed evidence in summary, '
                          'and required unfinished proof in remaining.')
                request = dict(trial_id=task['task_id'] + '--' + arm['id'] + '--r' + str(repeat),
                               task_id=task['task_id'], arm_id=arm['id'], repeat=repeat,
                               main_model=arm['main_model'], peer_model=arm['peer_model'],
                               common_prompt=common,
                               proof_prompt=common + '\n' + protocol['review_roles']['test_designer']['prompt'] + review_terminal,
                               post_prompt=common + '\n' + protocol['review_roles']['adversarial_reviewer']['prompt'] + review_terminal,
                               main_prompt=common + '\nImplement the task using the supplied proof-design report. '
                               'The adversarial review follows this episode; do not wait for it or call additional peers.',
                               repair_prompt=common + '\nReconcile the supplied adversarial report and repair real defects. '
                               'Rerun affected proof and preserve required gaps; do not call additional peers.')
                request['request_sha256'] = base.digest_json(request)
                result.append(request)
    return result


def verify_material(protocol, manifest, manifest_path=None):
    if len(manifest['tasks']) != 6 or len(protocol['arms']) != 4:
        raise ValueError('This registered runner requires all six tasks and four arms')
    if {t['task_id'] for t in manifest['tasks']} != set(protocol['tasks']['task_ids']):
        raise ValueError('Registered task identities differ from loaded manifest')
    if manifest_path is not None and file_sha(manifest_path) != protocol['tasks']['private_manifest_sha256']:
        raise ValueError('Registered manifest file identity mismatch')
    selection = HERE / protocol['tasks']['selection_path']
    if file_sha(selection) != protocol['tasks']['selection_sha256']:
        raise ValueError('Registered public selection identity mismatch')
    for task in manifest['tasks']:
        if grader.curation_tree(Path(task['base_snapshot'])) != task['source_sha256']:
            raise ValueError('Base source mismatch: ' + task['task_id'])
        oracle = Path(task['oracle_script'])
        if grader.curation_tree(oracle.parent) != task['oracle_sha256'] or file_sha(oracle) != task['oracle_script_sha256']:
            raise ValueError('Oracle mismatch: ' + task['task_id'])
    expected = {'astra', 'opus'}
    if set(protocol['models']) - {'attribution'} != expected:
        raise ValueError('Only the explicitly registered Astra/Opus assignment is supported')
    if protocol['models']['astra']['requested_id'] != backend.MODEL:
        raise ValueError('Codex model mismatch')
    if protocol['models']['opus']['requested_id'] != base.MODEL:
        raise ValueError('Claude model mismatch')


def scheduled_review(request, workspace, deadline):
    return {'available': False, 'reason': 'Reviews are supplied by fixed external stages; no additional review call is permitted.'}


def terminal_value(stage):
    if stage.get('process_exit') != 0 or stage.get('timed_out') is True or stage.get('unexpected_native_calls') or stage.get('native_guard_violated'):
        return None
    terminal = stage.get('terminal') if stage.get('backend') == 'claude_code' else {'structured_output': stage.get('structured_output')}
    if base.completion(terminal) is None:
        return None
    value = terminal.get('structured_output')
    return value if isinstance(value, dict) else json.loads(terminal['result'])


def invoke(model, workspace, control, prompt, seconds, deadline, readonly, study, *, budget=None):
    began = now()
    try:
        if model == 'astra':
            value = backend.codex_call(workspace, control, prompt,
                catalog=study / 'capabilities.json', timeout=seconds, deadline=deadline,
                readonly=readonly, inventory_receipt=read(study / 'inventory.json'),
                review_callback=scheduled_review)
        elif model == 'opus':
            # The unchanged Claude adapter services execution requests itself;
            # this outer loop refuses extra peer requests immediately.
            box = {}
            def launch():
                try:
                    box['value'] = base.claude_call(workspace, control, prompt,
                        budget,
                        seconds, deadline, readonly=readonly)
                except Exception as error:
                    box['error'] = type(error).__name__ + ': ' + str(error)
            thread = threading.Thread(target=launch)
            thread.start()
            while thread.is_alive():
                for path in control.glob('*.review-request.json'):
                    response = path.with_name(path.name.replace('.review-request', '.review-response'))
                    if not response.exists():
                        write(response, scheduled_review({}, workspace, deadline))
                time.sleep(.1)
            thread.join()
            if 'error' in box:
                raise RuntimeError(box['error'])
            value = box['value']
            value.update(backend='claude_code', provider='anthropic', model_requested=base.MODEL,
                         requested_effort=base.EFFORT,
                         model_attribution='event_observed' if value.get('observed_assistant_models') else 'unknown')
        else:
            raise ValueError('Unregistered provider assignment')
    except Exception as error:
        value = dict(backend=model, model_requested=backend.MODEL if model == 'astra' else base.MODEL,
                     declared_complete=None, terminal=None, usage=None, total_cost_usd=None,
                     error=type(error).__name__ + ': ' + str(error))
    try:
        source_sha = base.tree_digest(workspace)
    except Exception as error:
        source_sha = None
        value['source_integrity_error'] = type(error).__name__ + ': ' + str(error)
    value.update(started_at_utc=began, ended_at_utc=now(), assigned_model=model,
                 source_sha256_after=source_sha)
    final = terminal_value(value)
    value['declared_complete'] = final['complete'] if final is not None else None
    write(control / 'receipt.json', value)
    return value


def review_artifact(role, result, source_sha, workspace):
    value = dict(role=role, source_sha256_at_launch=source_sha,
                 source_sha256_after=result['source_sha256_after'], provider_receipt=result,
                 status='completed' if result.get('declared_complete') is True and
                        not (terminal_value(result) or {}).get('remaining') else 'partial')
    path = workspace / '.confidence' / (role + '.json')
    backend.workspace_evidence(workspace, path.name, value)
    return value


def peer_text(receipt):
    terminal = receipt.get('terminal') or {}
    value = terminal.get('structured_output') or receipt.get('structured_output')
    if value is None:
        value = terminal.get('result')
    return json.dumps(dict(declared_complete=receipt.get('declared_complete'), result=value,
                           timed_out=receipt.get('timed_out'), error=receipt.get('error')))


def run_trial(spec, task, protocol, study):
    out = study / 'trials' / spec['trial_id']
    if out.exists():
        raise ValueError('Refusing to retry or overwrite an assigned trial')
    out.mkdir(parents=True)
    began = time.monotonic()
    deadline = time.time() + 600
    start = now()
    with tempfile.TemporaryDirectory(prefix='cp-hybrid-') as scratch:
        job = Path(scratch).resolve()
        workspace = job / 'workspace'
        source = Path(task['base_snapshot'])
        base.safe_copy(source, workspace)
        for pattern in ('AGENTS.md', 'CLAUDE.md', '.claude', '.codex', '.git'):
            for path in list(workspace.rglob(pattern)):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        toolkit, toolkit_sha = base.snapshot_toolkit(protocol['package']['revision'], job, protocol['package'])
        shutil.copytree(toolkit, workspace / '.protocol')
        shutil.copytree(job / 'extract', workspace / '.protocol' / 'package')
        temporary = workspace / '.trial-tmp'
        temporary.mkdir()
        (workspace / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
        ignore = workspace / '.gitignore'
        ignore.write_text((ignore.read_text() if ignore.exists() else '') + '\n.trial-tmp/\n.confidence/\n')
        for argv in ([base.GIT, 'init', '-q'], [base.GIT, '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', 'add', '.'],
                     [base.GIT, '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Benchmark', '-c', 'user.email=benchmark@example.invalid', 'commit', '-qm', 'Frozen base']):
            subprocess.run(argv, cwd=workspace, env=base.safe_env(workspace, temporary), check=True, capture_output=True)
        stages = []
        for role, model, seconds, prompt, readonly, budget in (
            ('test_designer', spec['peer_model'], 90, spec['proof_prompt'], True, .6),
            ('main_implementation', spec['main_model'], 240, spec['main_prompt'], False, 1.75),
            ('adversarial_reviewer', spec['peer_model'], 90, spec['post_prompt'], True, .6),
            ('main_repair', spec['main_model'], 120, spec['repair_prompt'], False, .8),
        ):
            if role == 'main_implementation':
                prompt += '\nSupplied proof-design report:\n' + peer_text(stages[0])
            if role == 'adversarial_reviewer':
                prompt += '\nRaw visible implementation evidence:\n' + visible_evidence(out / 'main_implementation', spec['main_model'])
            if role == 'main_repair':
                prompt += '\nSupplied adversarial report:\n' + peer_text(stages[2])
                prompt += '\nPrior visible implementation evidence:\n' + visible_evidence(out / 'main_implementation', spec['main_model'])
            source_error = None
            try:
                source_sha = base.tree_digest(workspace)
            except Exception as error:
                source_sha = None
                source_error = type(error).__name__ + ': ' + str(error)
            remaining = min(seconds, deadline - time.time() - 60)
            if source_error or remaining <= 0:
                result = dict(assigned_model=model, declared_complete=None, terminal=None,
                              status='skipped_source_invalid' if source_error else 'skipped_deadline',
                              source_integrity_error=source_error, source_sha256_after=source_sha,
                              total_cost_usd=None, usage=None, started_at_utc=now(), ended_at_utc=now())
            else:
                result = invoke(model, workspace, out / role, prompt, remaining, deadline - 60, readonly, study, budget=budget)
            result['role'] = role
            result['timeout_seconds_granted'] = max(0, remaining)
            result['source_sha256_at_launch'] = source_sha
            stages.append(result)
            write(out / role / 'receipt.json', result)
            if readonly:
                try:
                    review_artifact(role, result, source_sha, workspace)
                except Exception as error:
                    result['review_artifact_error'] = type(error).__name__ + ': ' + str(error)
                    write(out / role / 'receipt.json', result)
        snapshot = out / 'result_snapshot'
        artifact_error = None
        try:
            base.safe_copy(workspace, snapshot)
            violations = base.scope_diff(source, snapshot, task['production_paths'])
            patch, submitted = base.build_patch(source, snapshot, out / 'submitted.patch', task['production_paths'])
            result_sha = base.tree_digest(snapshot)
        except Exception as error:
            artifact_error = type(error).__name__ + ': ' + str(error)
            violations, patch, submitted, result_sha = [], b'', [], None
        known, subtotal = base.known_cost(stages)
        invalid_reasons = []
        for stage in stages:
            if stage.get('unexpected_native_calls') or stage.get('native_guard_violated'):
                invalid_reasons.append(stage['role'] + ':unexpected_native_calls')
            if stage.get('stream_changed_during_cleanup'):
                invalid_reasons.append(stage['role'] + ':stream_changed_during_cleanup')
            if stage.get('source_integrity_error') or stage.get('review_artifact_error'):
                invalid_reasons.append(stage['role'] + ':source_or_artifact_integrity')
            if stage['role'] in ('test_designer', 'adversarial_reviewer') and stage.get('source_sha256_at_launch') != stage.get('source_sha256_after'):
                invalid_reasons.append(stage['role'] + ':readonly_source_drift')
        missing_reviews = [s['role'] for s in stages if s['role'] in ('test_designer', 'adversarial_reviewer')
                           and (s.get('declared_complete') is not True or
                                (terminal_value(s) or {}).get('remaining'))]
        status = 'submitted' if stages[-1].get('declared_complete') is True else 'unfinished'
        if any(terminal_value(s) is None for s in stages):
            status = 'terminal_missing'
        receipt = dict(schema_version=1, **{k: spec[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')},
            status='artifact_invalid' if artifact_error else status,
            declared_complete=stages[-1].get('declared_complete'),
            wall_seconds=time.monotonic() - began, started_at_utc=start, ended_at_utc=now(),
            stages=stages, total_cost_usd=known, known_cost_subtotal=subtotal,
            cost_known=known is not None, human_interventions=0,
            missing_required_reviews=missing_reviews, harness_invalid=bool(invalid_reasons),
            harness_invalid_reasons=invalid_reasons,
            request_sha256=spec['request_sha256'], source_sha256=base.tree_digest(source),
            toolkit_sha256=toolkit_sha, patch_sha256=hashlib.sha256(patch).hexdigest(),
            result_sha256=result_sha, scope_violations=violations, production_paths=submitted,
            artifact_error=artifact_error, over_budget=time.monotonic() - began > 600,
            grade=None)
        write(out / 'receipt.json', receipt)
    return receipt


def visible_evidence(control, model):
    path = control / 'stream.jsonl'
    if not path.exists():
        return 'No visible episode transcript was captured.'
    if model == 'opus':
        return json.dumps(base.visible_transcript(path))
    # Codex JSON events expose visible agent messages, MCP requests/results and
    # errors, not private reasoning. Preserve these fields without invention.
    events, _ = backend.parse_events(path)
    return json.dumps([e for e in events if e.get('type') in ('item.completed', 'turn.failed', 'error')
                       and e.get('item', {}).get('type') != 'reasoning'])


def prepare(args):
    protocol, manifest = read(args.protocol), read(args.manifest)
    verify_material(protocol, manifest, args.manifest)
    if args.study.exists():
        raise ValueError('Fresh study directory required')
    args.study.mkdir(parents=True)
    queue = requests(protocol, manifest)
    write(args.study / 'requests.json', queue)
    write(args.study / 'schedule.json', [{k: r[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')} for r in queue])
    backend.capability_catalog(args.model_catalog, args.study / 'capabilities.json')
    probe_workspace = args.study / 'probe-workspace'
    probe_workspace.mkdir()
    inventory = backend.inventory_probe(probe_workspace, args.study / 'inventory', args.study / 'capabilities.json', with_mcp=True)
    if not inventory['inventory']['passed']:
        raise ValueError('Exact native/MCP inventory failed')
    write(args.study / 'inventory.json', inventory)
    files = [args.protocol, args.manifest, HERE / 'hybrid_runner.py', HERE / 'cross_backend.py', HERE / 'runner.py',
             HERE / 'grading_adapter.py', HERE / 'hybrid_grader.py', HERE / 'hybrid_process.py', args.study / 'requests.json', args.study / 'schedule.json',
             args.study / 'capabilities.json', args.study / 'inventory.json']
    registration = dict(frozen_at_utc=now(), zero_hybrid_solver_outcomes=True,
                        files={str(p.resolve()): file_sha(p) for p in files},
                        protocol_sha256=base.digest_json(protocol), manifest_sha256=base.digest_json(manifest),
                        dynamic_prompt_rule='Fixed queue templates plus same-trial visible stage receipts/transcripts; exact payload recorded at launch',
                        trials=len(queue))
    write(args.study / 'registration.json', registration)
    print(json.dumps(registration, indent=2))


def run(args):
    registration = read(args.study / 'registration.json')
    for name, sha in registration['files'].items():
        if file_sha(Path(name)) != sha:
            raise ValueError('Registered file changed: ' + name)
    protocol, manifest = read(args.protocol), read(args.manifest)
    verify_material(protocol, manifest, args.manifest)
    tasks = {t['task_id']: t for t in manifest['tasks']}
    queue = read(args.study / 'requests.json')
    if (args.study / 'trials').exists():
        raise ValueError('Refusing a second cohort launch')
    def execute(spec):
        result = run_trial(spec, tasks[spec['task_id']], protocol, args.study)
        print(json.dumps({k: result[k] for k in ('trial_id', 'status', 'declared_complete', 'wall_seconds')}), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=protocol['resources']['concurrency']) as pool:
        results = list(pool.map(execute, queue))
    write(args.study / 'raw-results.json', results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run'))
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--model-catalog', type=Path)
    args = parser.parse_args()
    prepare(args) if args.action == 'prepare' else run(args)


if __name__ == '__main__':
    main()
