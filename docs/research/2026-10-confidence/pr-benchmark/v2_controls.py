#!/usr/bin/env python3
"""Paid, non-task full-pipeline qualification; never runs historical PR tasks.

The relative CLI layout is resolved by the same V2 entry-point normalizer. Both
cross pairings exercise all four real fixed stages and the exact frozen package.
No retry, fallback, outcome tuning or cohort efficacy result is produced here.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2_pipeline_under_control', HERE / 'hybrid_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def inspect_trial(receipt, output):
    """Require mechanical behavior and evidence, not model assertions alone."""
    reasons = []
    stages = receipt.get('stages', [])
    roles = ['test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair']
    if [s.get('role') for s in stages] != roles:
        reasons.append('four_stage_order')
    for stage in stages:
        role = stage.get('role', 'unknown')
        if stage.get('adapter_qualification', {}).get('passed') is not True:
            reasons.append(role + ':inventory_or_transport_unqualified')
        final = v2.frozen.terminal_value(stage)
        if final is None or role != 'main_implementation' and (final.get('complete') is not True or final.get('remaining')):
            reasons.append(role + ':missing_or_incomplete_terminal')
        model = stage.get('assigned_model')
        expected = 'gpt-6-astra' if model == 'astra' else 'claude-opus-5-5'
        if stage.get('model_requested') != expected or stage.get('requested_effort') != 'medium':
            reasons.append(role + ':requested_model_or_effort')
        observed = stage.get('observed_assistant_models', stage.get('observed_models', []))
        if any(value != expected for value in observed) or model == 'opus' and expected not in observed:
            reasons.append(role + ':model_attribution')
        path = output / role / 'tool-events.jsonl'
        events = v2.frozen.backend.parse_events(path)[0] if path.exists() else []
        successful = {e.get('name') for e in events if e.get('ok') is True}
        if 'read_file' not in successful or 'run_tests' not in successful:
            reasons.append(role + ':missing_actual_source_read_or_test')
        if role in ('test_designer', 'adversarial_reviewer') and stage.get('source_sha256_at_launch') != stage.get('source_sha256_after'):
            reasons.append(role + ':readonly_source_drift')
    snapshot = output / 'result_snapshot'
    check = subprocess.run(['python3', '-I', '-S', '-B', '-c',
        'import runpy,sys; m=runpy.run_path(sys.argv[1]); assert m["answer"]()==2; print("V2_TOY_PASS")',
        str(snapshot / 'toy.py')], capture_output=True, text=True)
    if check.returncode != 0:
        reasons.append('final_observable_behavior')
    main_logs = [output / role / 'tool-events.jsonl' for role in ('main_implementation', 'main_repair')]
    main_events = [event for path in main_logs if path.exists() for event in v2.frozen.backend.parse_events(path)[0]]
    captures = []
    for role in ('main_implementation', 'main_repair'):
        for request_path in (output / role).glob('*.command-request.json'):
            request = json.loads(request_path.read_text())
            argv = request.get('argv', [])
            response_path = request_path.with_name(request_path.name.replace('.command-request', '.command-response'))
            if any(str(value).endswith('/.protocol/scripts/confidence.py') for value in argv) and 'run' in argv and response_path.exists():
                response = json.loads(response_path.read_text())
                captures.append(response.get('exit_code') == 0)
    if not any(captures) or not any(e.get('name') == 'confidence' and e.get('ok') is True for e in main_events):
        reasons.append('actual_confidence_capture_missing')
    if receipt.get('harness_invalid') or receipt.get('scope_violations') or receipt.get('artifact_error'):
        reasons.append('trial_integrity_or_scope')
    if receipt.get('over_budget') is True or receipt.get('wall_seconds', 601) > 600:
        reasons.append('aggregate_deadline')
    return dict(passed=not reasons, reasons=reasons, behavior_exit_code=check.returncode,
                behavior_stdout=check.stdout.strip(), behavior_stderr_sha256=hashlib.sha256(check.stderr.encode()).hexdigest(),
                trial_receipt_sha256=v2.frozen.file_sha(output / 'receipt.json'))


def run(args):
    original = {key: str(getattr(args, key)) for key in ('protocol', 'study')}
    v2.normalize_args(args)
    source_study = args.source_study.resolve()
    registration = v2.frozen.read(source_study / 'registration.json')
    for name in ('capabilities.json', 'inventory.json'):
        source = source_study / name
        if registration['files'].get(str(source)) != v2.frozen.file_sha(source):
            raise ValueError('Frozen capability/inventory identity differs: ' + name)
    if args.study.exists():
        raise ValueError('Fresh qualification directory required; do not retry a toy')
    args.study.mkdir(parents=True)
    for name in ('capabilities.json', 'inventory.json'):
        shutil.copyfile(source_study / name, args.study / name)
    base = args.study / 'non-task-base'
    base.mkdir()
    (base / 'toy.py').write_text('def answer():\n    return 1\n')
    protocol = v2.frozen.read(args.protocol)
    task = dict(task_id='v2-non-task-pipeline-toy', base_snapshot=str(base),
        production_paths=['toy.py'], test_commands=[['python3', '-B', '-c', 'from toy import answer; assert answer() in (1,2)']],
        prompt='This is a Quick reversible non-task transport qualification toy. Change toy.answer() from 1 to 2. '
        'Preserve its importability. Every stage must read toy.py with read_file and run its applicable public '
        'behavior using run_tests. Proof designer checks the base returns 1; adversarial reviewer checks the '
        'submitted code returns 2. Main implementation must use the actual confidence tool to init '
        '--title Toy --directory .confidence, then run --id toy-pass --directory .confidence --cwd . -- '
        'python3 -B -c "from toy import answer; assert answer()==2; print(2)" to capture source-bound proof. '
        'Main repair must inspect the supplied peer report, run answer()==2, and return truthful completion. '
        'Do not request additional model calls. Required externally staged peers are supplied; this toy '
        'does not require a release-gate proof packet or full historical PR behavior.')
    queue = [q for q in v2.frozen.requests(protocol, {'tasks': [task]}) if q['repeat'] == 1 and
             q['arm_id'] in ('astra_main_opus_peer', 'opus_main_astra_peer')]
    registration = dict(
        frozen_at_utc=v2.frozen.now(), purpose='Non-task full staged pipeline qualification only',
        efficacy_trials=0, raw_cli_layout=original, resolved_study=str(args.study),
                roles=['test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair'],
        files={str(p): v2.frozen.file_sha(p) for p in (args.protocol, Path(__file__).resolve(), HERE / 'hybrid_v2.py',
               HERE / 'hybrid_runner.py', HERE / 'runner.py', HERE / 'cross_backend.py', HERE / 'hybrid_process.py',
               HERE / 'hybrid_process_v2.py', HERE / 'hybrid_runtime_v2.py')},
        requests=queue, no_retries=True, preserves_registered_stage_windows=True)
    v2.frozen.write(args.study / 'toy-registration.json', registration)
    v2.frozen.invoke = v2.qualified_invoke
    checks = []
    for request in queue:
        receipt = v2.frozen.run_trial(request, task, protocol, args.study)
        check = inspect_trial(receipt, args.study / 'trials' / request['trial_id'])
        check['trial_id'] = request['trial_id']
        checks.append(check)
        v2.frozen.write(args.study / 'pipeline-checks.json', checks)
        print(json.dumps(check), flush=True)
    changed = [name for name, expected in registration['files'].items()
               if v2.frozen.file_sha(Path(name)) != expected]
    qualified = len(checks) == 2 and all(c['passed'] is True for c in checks) and not changed
    v2.frozen.write(args.study / 'qualification-summary.json', dict(
        passed=qualified, checks=checks, registered_source_files_changed=changed,
        efficacy_trials=0, checked_at_utc=v2.frozen.now()))
    if not qualified:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--source-study', type=Path, required=True)
    run(parser.parse_args())
