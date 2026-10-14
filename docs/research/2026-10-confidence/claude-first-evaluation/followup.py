#!/usr/bin/env python3
"""Predeclared eight-artifact PR40 change probe, distinct from the main study.

One new public CLI behavior; no claim of general maintainability. Preparation
reads registered task material only. Candidate scores are not inspected until
the initial study is frozen and this probe's second input seal is created.
"""
from __future__ import annotations

import argparse
import ast
import copy
import concurrent.futures
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
spec = __import__('importlib.util', fromlist=['']).spec_from_file_location('followup_main_helpers', HERE / 'runner.py')
r = __import__('importlib.util', fromlist=['']).module_from_spec(spec); spec.loader.exec_module(r)
METHOD = 'test_environment_disabled_default_runs_real_phase_and_persists_disabled'
TOKENS = ('unbounded', '  UnBoUnDeD  ')
NAMES = ('test_unbounded_environment_runs_real_phase', 'test_trimmed_mixed_case_environment_runs_real_phase')
REQUIREMENTS = (
    "Extend the public BONAPARTE_SOFT_PHASE_BUDGET environment input to accept "
    "'unbounded' as another spelling of 'off', including surrounding whitespace "
    "and mixed case such as '  UnBoUnDeD  '. It must deliver the same disabled "
    "real phase execution and persisted None budget as 'off'. Preserve the "
    "original selected behavior, numeric budgets, CLI overrides, resume "
    "semantics and rejection of invalid values. Make a bounded change with "
    "executed evidence. This is one isolated change attempt, not a whole CP "
    "release certification. No peer extension is available."
)


def build_oracle(original, destination):
    """Clone a trusted evaluator; only public environment-token fixture varies."""
    original, destination = Path(original), Path(destination)
    if destination.exists():
        raise ValueError('Novel oracle requires a fresh destination')
    shutil.copytree(original.parent / 'base', destination.parent / 'base')
    shutil.copytree(original, destination)
    fixture = original / 'modules' / 'test_budget_resume_audit.py'
    text = fixture.read_text(); tree = ast.parse(text)
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'BudgetResumeAudit')
    method = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == METHOD)
    prefix = text[:text.index('class BudgetResumeAudit')]
    methods = []
    for name, token in zip(NAMES, TOKENS):
        changed = copy.deepcopy(method); changed.name = name
        inputs = [node for node in ast.walk(changed) if isinstance(node, ast.Constant) and node.value == 'off']
        if len(inputs) != 1:
            raise ValueError('Trusted environment fixture no longer has one off input')
        inputs[0].value = token; methods.append(changed)
    newclass = ast.ClassDef(name='BudgetUnboundedProbe', bases=[ast.Name(id='unittest.TestCase', ctx=ast.Load())], keywords=[], body=methods, decorator_list=[])
    # Attribute AST rather than dotted Name keeps generated source valid.
    newclass.bases = [ast.Attribute(value=ast.Name(id='unittest', ctx=ast.Load()), attr='TestCase', ctx=ast.Load())]
    ast.fix_missing_locations(newclass)
    module = destination / 'modules' / 'test_budget_unbounded_probe.py'
    module.write_text(prefix + ast.unparse(newclass) + '\n')
    config = r.read(destination / 'oracle.json')
    config['test_ids'] = ['tests.test_budget_unbounded_probe.BudgetUnboundedProbe.' + name for name in NAMES]
    r.write(destination / 'oracle.json', config)
    return {'fixture_sha256': r.sha(fixture), 'selected_method': METHOD, 'tokens': list(TOKENS),
            'test_ids': config['test_ids'], 'novel_module_sha256': r.sha(module),
            'intervention': 'Only method name and one public environment input token change in each copied method body'}


def verify_declaration(output):
    declaration = r.read(output / 'declaration.json')
    if r.digest(declaration['payload']) != declaration['payload_sha256']:
        raise ValueError('Probe declaration changed')
    payload = declaration['payload']
    initial = Path(payload['initial_study'])
    if r.sha(initial / 'registration.json') != payload['initial_registration_sha256']:
        raise ValueError('Initial registration changed')
    r.verify(initial)
    for path, expected in payload['files'].items():
        if r.sha(path) != expected:
            raise ValueError('Probe support file changed: ' + path)
    for path, expected in payload['trees'].items():
        if r.inventory(path) != expected:
            raise ValueError('Probe input tree changed: ' + path)
    return payload


def prepare(initial_study, output, policy=None):
    initial_study, output = Path(initial_study).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Probe preparation requires new output')
    initial = r.verify(initial_study)
    requests = [q for q in r.read(initial_study / 'requests.json') if q['task_id'] == 'tweed-pr40']
    if len(requests) != 8 or len({q['trial_id'] for q in requests}) != 8:
        raise ValueError('Exactly eight assigned PR40 inputs required')
    task = next(t for t in r.read(initial['config']['manifest'])['tasks'] if t['task_id'] == 'tweed-pr40')
    enhanced = next(a for a in initial['config']['arms'] if a['id'] == 'enhanced-opus')
    if policy is not None and Path(policy).resolve() != Path(enhanced['policy_directory']).resolve():
        raise ValueError('Followup must use the registered enhanced policy')
    output.mkdir(parents=True)
    original_oracle = Path(task['oracle_script']).parent
    novel = output / 'novel' / 'oracle'; novel.parent.mkdir()
    derivation = build_oracle(original_oracle, novel)
    arm = dict(enhanced, backend='claude', model='claude-opus-5-5', effort='medium')
    adapter = r.route(arm); base = adapter.frozen.base
    controlroot = output / 'controls'; controlroot.mkdir()
    observations = []
    for label, script, source in [('head-novel', novel / 'evaluate.py', Path(task['head_snapshot']))]:
        directory = controlroot / label; directory.mkdir()
        observations.append(dict(label=label, **r.invoke_oracle(adapter, script, source, directory)))
    alternative = controlroot / 'bounded-alternative'; base.safe_copy(Path(task['head_snapshot']), alternative)
    path = alternative / 'bonaparte'; text = path.read_text()
    needle = 'configured.strip().casefold() == "off"'
    if text.count(needle) != 1:
        raise ValueError('Trusted head no longer has the known bounded extension seam')
    path.write_text(text.replace(needle, 'configured.strip().casefold() in ("off", "unbounded")', 1))
    for label, script in [('alternative-novel', novel / 'evaluate.py'), ('alternative-original', Path(task['oracle_script']))]:
        directory = controlroot / label; directory.mkdir()
        observations.append(dict(label=label, **r.invoke_oracle(adapter, script, alternative, directory)))
    if [row['oracle_passed'] for row in observations] != [False, True, True]:
        raise ValueError('Novel failure sensitivity or bounded alternative controls failed')
    r.write(controlroot / 'results.json', {'passed': True, 'observations': observations,
                                         'alternative_inventory_sha256': r.digest(r.inventory(alternative))})
    files = {str(HERE / name): r.sha(HERE / name) for name in ('followup.py', 'test_followup.py', 'runner.py', 'test_runner.py')}
    files[str(controlroot / 'results.json')] = r.sha(controlroot / 'results.json')
    trees = {str(novel.parent): r.inventory(novel.parent), str(controlroot): r.inventory(controlroot)}
    payload = {'initial_study': str(initial_study), 'initial_registration_sha256': r.sha(initial_study / 'registration.json'),
               'initial_payload_sha256': r.digest(initial), 'roster': [{k: q[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')} for q in requests],
               'task': task, 'arm': arm, 'toolkit_directory': initial['config']['toolkit_directory'], 'requirements': REQUIREMENTS,
               'seconds': 120, 'claude_budget_usd': 1, 'model': 'claude-opus-5-5', 'effort': 'medium',
               'concurrency_ceiling': 2,
               'oracle_script': str(novel / 'evaluate.py'), 'derivation': derivation, 'files': files, 'trees': trees,
               'prepared_at_unix': time.time(), 'limitations': ['One small public-input change, not broad maintainability',
                    'Available regular artifacts include initially incorrect solutions; report originally accepted subset separately',
                    'Source projected onto pristine base; original tests restored; initial added tests and evidence not exposed',
                    'Opus fixed for all followups, no reciprocal model comparison', 'USD estimate is not observed subscription billing']}
    r.write(output / 'declaration.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
    return payload


def seal(output):
    output = Path(output).resolve()
    if (output / 'input-seal.json').exists():
        raise ValueError('Refusing to overwrite followup input seal')
    declaration = verify_declaration(output); initial = Path(declaration['initial_study'])
    closed = initial / 'results.json'
    all_results = r.read(closed)
    all_requests = r.read(initial / 'requests.json')
    if len(all_results) != 48 or {row['trial_id'] for row in all_results} != {row['trial_id'] for row in all_requests}:
        raise ValueError('Initial full assigned roster must be normalized before the followup input freeze')
    rows = []
    for assigned in declaration['roster']:
        directory = initial / 'trials' / assigned['trial_id']; snapshot = directory / 'result_snapshot'
        row = dict(assigned, source=str(snapshot), available=False, initial_eligible=None, initial_accepted=None)
        if directory.is_dir():
            row['first_stage_artifact_inventory'] = r.inventory(directory)
            row['first_stage_artifact_inventory_sha256'] = r.digest(row['first_stage_artifact_inventory'])
        receipt_path = directory / 'receipt.json'
        if receipt_path.is_file():
            receipt = r.read(receipt_path)
            if any(receipt.get(k) != assigned[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')):
                raise ValueError('Initial artifact identity mismatch')
            row.update(initial_receipt_sha256=r.sha(receipt_path), initial_eligible=receipt.get('eligible'), initial_accepted=receipt.get('accepted'))
        patch = directory / 'submitted.patch'
        if patch.is_file(): row['initial_patch_sha256'] = r.sha(patch)
        if snapshot.is_dir():
            try:
                source_inventory = r.inventory(snapshot)
                if not (snapshot / 'bonaparte').is_file():
                    raise ValueError('Initial production entry absent')
                row.update(available=True, source_inventory=source_inventory, source_inventory_sha256=r.digest(source_inventory))
                if receipt_path.is_file() and r.read(receipt_path).get('result_sha256') != r.route(declaration['arm']).frozen.base.tree_digest(snapshot):
                    raise ValueError('Initial receipt/source digest mismatch')
            except (OSError, ValueError) as error:
                row.update(available=False, missing_reason=type(error).__name__ + ': ' + str(error))
        else:
            row['missing_reason'] = 'No regular first-stage result source'
        rows.append(row)
    payload = {'declaration_sha256': r.sha(output / 'declaration.json'), 'initial_results_sha256': r.sha(closed),
               'inputs': rows, 'sealed_at_unix': time.time(), 'planned': 8}
    r.write(output / 'input-seal.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
    return payload


def verify(output):
    declaration = verify_declaration(output); wrapper = r.read(output / 'input-seal.json'); seal = wrapper['payload']
    if r.digest(seal) != wrapper['payload_sha256'] or seal['declaration_sha256'] != r.sha(output / 'declaration.json'):
        raise ValueError('Followup input seal changed')
    if r.sha(Path(declaration['initial_study']) / 'results.json') != seal['initial_results_sha256']:
        raise ValueError('Initial normalized outcome closure changed')
    if len(seal['inputs']) != 8 or [tuple(row[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')) for row in seal['inputs']] != [tuple(row[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')) for row in declaration['roster']]:
        raise ValueError('Followup roster changed')
    for row in seal['inputs']:
        original = Path(declaration['initial_study']) / 'trials' / row['trial_id']
        if 'first_stage_artifact_inventory' in row and r.inventory(original) != row['first_stage_artifact_inventory']:
            raise ValueError('First-stage artifact/log drift after followup seal')
        if 'first_stage_artifact_inventory' not in row and original.exists():
            raise ValueError('Previously missing initial trial appeared after followup seal')
        for name, key in [('receipt.json', 'initial_receipt_sha256'), ('submitted.patch', 'initial_patch_sha256')]:
            if key in row and r.sha(original / name) != row[key]:
                raise ValueError('Initial recorded artifact changed')
        if row['available'] and r.inventory(row['source']) != row['source_inventory']:
            raise ValueError('Initial source drift after followup seal')
    return declaration, seal


def run_cell(row, declaration, output):
    out = output / 'trials' / row['trial_id']; out.parent.mkdir(exist_ok=True)
    try: out.mkdir()
    except FileExistsError: return {'trial_id': row['trial_id'], 'status': 'preserved_previously_started'}
    receipt = {k: row[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat', 'initial_eligible', 'initial_accepted')}
    receipt.update(eligible=False, original_passed=None, novel_passed=None)
    if not row['available']:
        receipt.update(status='not_run_missing_initial_source', missing_reason=row.get('missing_reason'))
        r.write(out / 'receipt.json', receipt); return receipt
    r.write(out / 'started.json', {'input_seal_sha256': r.sha(output / 'input-seal.json'), 'started_at_unix': time.time()})
    try:
        verify(output); adapter = r.route(declaration['arm']); base = adapter.frozen.base; task = declaration['task']
        original_service = base.service_commands
        def service(control, workspace, temporary, readonly, deadline):
            r.deny_reviews(control, workspace, None, deadline)
            return original_service(control, workspace, temporary, readonly, deadline)
        base.service_commands = service
        projection = r.load(Path(task['oracle_script']))
        with tempfile.TemporaryDirectory(prefix='cp-maintainability-probe-') as name:
            workspace = Path(name).resolve() / 'workspace'
            submitted = projection.copy_candidate(Path(task['base_snapshot']), Path(row['source']), workspace, task['production_paths'])
            for pattern in ('AGENTS.md', 'CLAUDE.md', '.claude', '.codex', '.agents', '.git', '.protocol'):
                for path in list(workspace.rglob(pattern)):
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
            clean_initial = out / 'clean_initial'; base.safe_copy(workspace, clean_initial)
            # Owner baseline measures do not feed the worker or affect inclusion.
            for label, script in [('initial-original', task['oracle_script']), ('initial-novel', declaration['oracle_script'])]:
                directory = out / label; directory.mkdir()
                receipt[label + '_grade'] = r.invoke_oracle(adapter, Path(script), clean_initial, directory)
            r.mount(base, declaration['toolkit_directory'], declaration['arm']['policy_directory'], workspace)
            (workspace / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
            ignore = workspace / '.gitignore'; ignore.write_text((ignore.read_text() if ignore.exists() else '') + '\n.trial-tmp/\n.confidence/\n')
            scratch = workspace / '.trial-tmp'; scratch.mkdir(exist_ok=True)
            for args in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Probe', '-c', 'user.email=probe@example.invalid', 'commit', '-qm', 'Frozen initial artifact']):
                subprocess.run([base.GIT, '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *args], cwd=workspace, env=base.safe_env(workspace, scratch), check=True, capture_output=True)
            local = adapter.local_mcp_probe('opus', workspace, out / 'qualification', readonly=False)
            if local.get('passed') is not True: raise ValueError('Followup local transport unqualified')
            prompt = 'Read .protocol/SKILL.md and relevant references.\n' + declaration['requirements'] + '\nOriginal required behavior:\n' + task['prompt'] + '\nVisible baseline commands:\n' + json.dumps(task['test_commands'])
            deadline = time.time() + declaration['seconds']
            stage = base.claude_call(workspace, out / 'main', prompt, declaration['claude_budget_usd'], declaration['seconds'], deadline); stage['backend'] = 'claude'
            q = r.qualification(stage, local, declaration['arm'], adapter)
            snapshot = out / 'result_snapshot'; base.safe_copy(workspace, snapshot)
            patch, paths = base.build_patch(clean_initial, snapshot, out / 'submitted.patch', task['production_paths'])
            violations = base.scope_diff(clean_initial, snapshot, task['production_paths'])
            receipt.update(status='completed', stage=stage, qualification=q, eligible=q['eligible'] and not violations,
                           projected_production_paths=submitted, submitted_paths=paths, scope_violations=violations,
                           initial_projected_sha256=base.tree_digest(clean_initial), result_sha256=base.tree_digest(snapshot),
                           patch_sha256=r.sha(out / 'submitted.patch'), input_seal_sha256=r.sha(output / 'input-seal.json'),
                           patch_stats={'bytes': len(patch), 'added_lines': sum(line.startswith(b'+') and not line.startswith(b'+++') for line in patch.splitlines()),
                                        'removed_lines': sum(line.startswith(b'-') and not line.startswith(b'---') for line in patch.splitlines())})
            receipt.update(cost_estimate_usd=stage.get('total_cost_usd'), cost_basis=(stage.get('terminal') or {}).get('costBasis', 'unknown'),
                           observed_billed_usd=None, cpu_time_seconds=None,
                           cpu_time_status='No per-stage CPU accounting; actual confined command exits are recorded separately')
            events = out / 'main' / 'tool-events.jsonl'; executed = []
            if events.is_file():
                for line in events.read_text().splitlines():
                    event = json.loads(line)
                    if event.get('name') in ('run_tests', 'confidence'): executed.append(event)
            receipt['executed_check_counts'] = {'requested': len(executed), 'exit_zero': sum(e.get('command_exit_code') == 0 for e in executed),
                                                'timed_out': sum(e.get('command_timed_out') is True for e in executed),
                                                'run_tests_commands': sum(e['name'] == 'run_tests' for e in executed),
                                                'confidence_commands': sum(e['name'] == 'confidence' for e in executed),
                                                'basis': 'Actual confined command/tool events; command counts, not assertion/test counts'}
            receipt['tool_events_sha256'] = r.sha(events) if events.exists() else None
            if receipt['eligible']:
                verify(output)
                for label, script in [('original', task['oracle_script']), ('novel', declaration['oracle_script'])]:
                    directory = out / label; directory.mkdir()
                    grade = r.invoke_oracle(adapter, Path(script), snapshot, directory)
                    receipt[label + '_grade'] = grade; receipt[label + '_passed'] = grade['oracle_passed']
    except Exception as error:
        receipt.update(status='infrastructure_or_artifact_error', error=type(error).__name__ + ': ' + str(error))
    r.write(out / 'receipt.json', receipt); return receipt


def run(output, workers=2):
    output = Path(output).resolve(); declaration, inputs = verify(output)
    rows = list(inputs['inputs']); random.Random(6102031).shuffle(rows)
    if workers not in (1, 2) or workers > declaration['concurrency_ceiling']:
        raise ValueError('Followup exceeds its registered concurrency ceiling')
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_cell, row, declaration, output) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            value = future.result()
            print(json.dumps({k: value.get(k) for k in ('trial_id', 'status', 'eligible', 'original_passed', 'novel_passed')}), flush=True)
    results = []
    for row in inputs['inputs']:
        path = output / 'trials' / row['trial_id'] / 'receipt.json'
        results.append(r.read(path) if path.exists() else dict(row, status='started_unknown', original_passed=None, novel_passed=None, eligible=False))
    r.write(output / 'results.json', {'assigned': 8, 'results': results, 'originally_accepted_subset': [row['trial_id'] for row in inputs['inputs'] if row['initial_accepted'] is True]})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'seal', 'run']); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial-study', type=Path); parser.add_argument('--policy', type=Path)
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.initial_study is None: parser.error('prepare requires --initial-study')
        prepare(args.initial_study, args.output, args.policy)
    elif args.action == 'seal': seal(args.output)
    else: run(args.output, args.workers)
