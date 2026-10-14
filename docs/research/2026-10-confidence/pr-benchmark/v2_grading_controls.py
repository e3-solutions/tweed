"""Independent offline controls. Synthetic metadata is not a model trial."""
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('independent_hybrid_control', HERE / 'hybrid_v2_grader.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
fixture_spec = importlib.util.spec_from_file_location('v2_control_metadata', HERE / 'test_hybrid_v2_grader.py')
fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture)
healthy_stage = fixture.healthy_stage
runtime_spec = importlib.util.spec_from_file_location('v2_visible_control_runtime', HERE / 'hybrid_runtime_v2.py')
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)
runtime.install(m.frozen.hybrid.base, m.frozen.hybrid.backend)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hashes():
    return {name: file_sha(HERE / name) for name in (
        'hybrid_v2_grader.py', 'hybrid_v2.py', 'hybrid_runtime_v2.py', 'hybrid_process_v2.py', 'hybrid_grader.py', 'hybrid_runner.py', 'hybrid_process.py', 'test_hybrid_v2_grader.py',
        'cross_backend.py', 'grading_adapter.py', 'runner.py')}


def make_fixture(root, task, candidate, provider, label, package):
    source = Path(task['base_snapshot'])
    delta, submitted = m.frozen.hybrid.base.build_patch(source, candidate, root / 'submitted.patch', task['production_paths'])
    result = root / 'result_snapshot'
    m.frozen.hybrid.base.safe_copy(source, result)
    for relative in submitted:
        origin, target = candidate / relative, result / relative
        if origin.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        elif target.is_file():
            target.unlink()
    request = dict(trial_id='SYNTHETIC-CONTROL-' + task['task_id'] + '-' + label + '-' + provider,
                   task_id=task['task_id'], arm_id='SYNTHETIC-CONTROL-NOT-A-MODEL-ARM',
                   repeat=0, main_model=provider, peer_model=provider)
    request['request_sha256'] = m.frozen.hybrid.base.digest_json(request)
    tree = m.frozen.hybrid.base.tree_digest(result)
    stages = []
    for role in ('test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair'):
        terminal = dict(complete=True, summary='SYNTHETIC STRUCTURAL CONTROL ONLY; no model or independent software review', remaining=[])
        stage = dict(role=role, backend='codex_cli' if provider == 'astra' else 'claude_code',
                     model_requested='gpt-6-astra' if provider == 'astra' else 'claude-opus-5-5',
                     requested_effort='medium', assigned_model=provider, model_attribution='synthetic_control_only',
                     observed_models=[], observed_assistant_models=[], declared_complete=True,
                     total_cost_usd=None, process_exit=0, timed_out=False,
                     source_sha256_at_launch=tree, source_sha256_after=tree, wall_seconds=0,
                     status='synthetic_control_only', process_cleanup_scope='original_process_group',
                     detached_descendants_contained=False)
        if provider == 'astra':
            stage['structured_output'] = terminal
        else:
            stage['terminal'] = {'structured_output': terminal}
        stage.update(healthy_stage(provider, role))
        stage['source_sha256_at_launch'] = stage['source_sha256_after'] = tree
        stages.append(stage)
    raw = dict(request, schema_version=1, status='synthetic_control_only', synthetic_control=True,
               source_sha256=m.frozen.hybrid.base.tree_digest(source), toolkit_sha256=package,
               result_sha256=tree, patch_sha256=hashlib.sha256(delta).hexdigest(),
               scope_violations=[], stages=stages, declared_complete=True, total_cost_usd=None,
               known_cost_subtotal=0, cost_known=False, harness_invalid_reasons=[],
               wall_seconds=0, over_budget=False, human_interventions=0)
    path = root / 'receipt.json'
    path.write_text(json.dumps(raw))
    return request, raw, path


def actual_help(result, root, label):
    scratch = result / '.trial-tmp'
    scratch.mkdir(exist_ok=True)
    profile = m.frozen.hybrid.base.sandbox_profile(result, scratch, readonly=True)
    receipt = m.frozen.hybrid.base.bounded_process(
        ['/usr/bin/sandbox-exec', '-p', profile, sys.executable, '-B', str(result / 'bonaparte'), '--help'],
        cwd=result, env=m.frozen.hybrid.base.safe_env(result, scratch), timeout=15,
        output_prefix=root / ('actual-cli-' + label))
    receipt['stderr_excerpt'] = Path(receipt['stderr']).read_text(errors='replace')[-4000:]
    return receipt


start_hashes = code_hashes()
manifest_path = ROOT / '.confidence/benchmark/curation/hybrid-manifest.json'
manifest = json.loads(manifest_path.read_text())
protocol = json.loads((HERE / 'hybrid-protocol.json').read_text())
package = m.frozen.hybrid.grader.package_identity(ROOT, protocol['package'])
controls, negatives, visible = [], [], []
cases = [(task, variant, Path(task['base_snapshot'] if variant == 'base' else task['head_snapshot']), 'astra')
         for task in manifest['tasks'] for variant in ('base', 'head')]
cases += [(task, 'equivalent_rename', ROOT / '.confidence/benchmark/curation' / ('equivalent-pr' + task['task_id'].split('pr')[1]), provider)
          for task in manifest['tasks'] if task['task_id'] in ('tweed-pr39', 'tweed-pr40')
          for provider in ('astra', 'opus')]
for task, variant, candidate, provider in cases:
    with tempfile.TemporaryDirectory(prefix='hybrid-independent-synthetic-control-') as temporary:
        root = Path(temporary).resolve()
        request, raw, path = make_fixture(root, task, candidate, provider, variant, package)
        if variant == 'base':
            result = root / 'result_snapshot'
            scratch = result / '.trial-tmp'; scratch.mkdir(exist_ok=True)
            env = m.frozen.hybrid.base.safe_env(result, scratch)
            for gitargs in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Control', '-c', 'user.email=control@example.invalid', 'commit', '-qm', 'Synthetic base']):
                subprocess.run([m.frozen.hybrid.base.GIT, *gitargs], cwd=result, env=env, capture_output=True, check=True)
            for index, command in enumerate(task['test_commands']):
                control = root / ('visible-control-' + str(index))
                deadline = time.time() + 100
                worker = m.frozen.hybrid.base.WorkspaceTools(dict(workspace=str(result), control=str(control),
                    temporary=str(scratch), readonly=False, deadline=deadline, python_executable=sys.executable))
                box = {}
                thread = threading.Thread(target=lambda: box.update(value=worker.call('run_tests', {'argv': command})))
                thread.start()
                while thread.is_alive() and time.time() < deadline:
                    m.frozen.hybrid.base.service_commands(control, result, scratch, False, deadline)
                    time.sleep(.01)
                thread.join(timeout=1)
                if thread.is_alive():
                    raise RuntimeError('Visible control failed to return its actual tool response')
                observed, tool_event = box['value']
                visible.append(dict(task_id=task['task_id'], argv=command, readonly=False, exit_code=observed['exit_code'],
                    passed=observed['exit_code']==0 and tool_event['ok'], callback='actual WorkspaceTools→installed service_commands',
                    stdout_sha256=observed['stdout_sha256'], stderr_sha256=observed['stderr_sha256']))
        graded = m.grade(path, request, task, package)
        row = graded['normalized']
        expected = variant != 'base'
        record = dict(task_id=task['task_id'], variant=variant, synthetic_backend_terminal_format=provider,
                      expected_oracle_passed=expected, oracle_passed=row['oracle_passed'],
                      harness_invalid=row['harness_invalid'], harness_invalid_reasons=row['harness_invalid_reasons'],
                      control_passed=row['oracle_passed'] is expected and not row['harness_invalid'],
                      source_sha256=raw['source_sha256'], projected_result_sha256=raw['result_sha256'],
                      oracle_script_sha256=task['oracle_script_sha256'], oracle_material_sha256=task['oracle_sha256'],
                      grader_receipt=graded['grader'], raw_synthetic_control_sha256=graded['raw_receipt_sha256'])
        controls.append(record)
        print(json.dumps({key: record[key] for key in ('task_id', 'variant', 'synthetic_backend_terminal_format', 'oracle_passed', 'control_passed')}), flush=True)
        if task['task_id'] == 'tweed-pr32' and variant == 'head':
            mutations = {
                'terminal_field_mismatch': lambda x: x['stages'][-1]['structured_output'].update(complete=False),
                'unfinished_peer_proof': lambda x: x['stages'][0]['structured_output'].update(remaining=['required proof not executed']),
                'readonly_source_drift': lambda x: x['stages'][0].update(source_sha256_at_launch='DIFFERENT'),
                'timedout_main_with_terminal': lambda x: x['stages'][-1].update(timed_out=True, process_exit=-15),
                'stream_changed_during_cleanup': lambda x: x['stages'][-1].update(stream_changed_during_cleanup=True),
                'qualification_missing': lambda x: x['stages'][0].pop('adapter_qualification'),
                'qualification_unknown': lambda x: x['stages'][0]['adapter_qualification'].update(passed=None),
                'qualification_false': lambda x: x['stages'][0]['adapter_qualification'].update(passed=False),
                'qualification_wrong_provider': lambda x: x['stages'][0]['adapter_qualification']['local'].update(provider='opus'),
                'qualification_wrong_basis': lambda x: x['stages'][0]['adapter_qualification'].update(basis='model_assertion'),
                'qualification_missing_tools': lambda x: x['stages'][0]['adapter_qualification']['local'].update(effective_mcp_tools=[]),
                'lifecycle_missing_timeout': lambda x: x['stages'][-1].pop('timed_out'),
                'lifecycle_unknown_timeout': lambda x: x['stages'][-1].update(timed_out=None),
                'lifecycle_missing_cleanup_scope': lambda x: x['stages'][-1].pop('process_cleanup_scope'),
                'lifecycle_unknown_stream_cleanup': lambda x: x['stages'][-1].update(stream_changed_during_cleanup=None),
                'lifecycle_overclaimed_containment': lambda x: x['stages'][-1].update(detached_descendants_contained=True),
                'lifecycle_boolean_process_exit': lambda x: x['stages'][-1].update(process_exit=True),
                'source_missing_peer_digest': lambda x: x['stages'][0].pop('source_sha256_at_launch'),
                'source_both_peer_digests_unknown': lambda x: x['stages'][0].update(source_sha256_at_launch=None, source_sha256_after=None),
            }
            with patch.object(m.frozen.hybrid.grader, 'invoke_oracle', return_value={'oracle_passed': True, 'synthetic_isolated_oracle': True}):
                for label, mutate in mutations.items():
                    changed = copy.deepcopy(raw)
                    mutate(changed)
                    path.write_text(json.dumps(changed))
                    observed = m.grade(path, request, task, package)['normalized']
                    passed = observed['truthful_success'] is False and (label == 'unfinished_peer_proof' or observed['harness_invalid'] is True)
                    if label.startswith(('qualification_', 'lifecycle_', 'source_')):
                        passed = passed and observed['oracle_passed'] is None
                    if label == 'timedout_main_with_terminal':
                        passed = passed and observed['declared_complete'] is None
                    negatives.append(dict(name=label, passed=passed, observed_truthful_success=observed['truthful_success'],
                                          observed_harness_invalid=observed['harness_invalid'], observed_declared_complete=observed['declared_complete'],
                                          reasons=observed['harness_invalid_reasons'], isolated_oracle_synthetic=True))
        if task['task_id'] == 'tweed-pr39' and variant == 'head':
            result = root / 'result_snapshot'
            intact = actual_help(result, root, 'intact')
            (result / 'bonaparte_linear.py').unlink()
            deleted = actual_help(result, root, 'deleted')
            delta, _ = m.frozen.hybrid.base.build_patch(Path(task['base_snapshot']), result, root / 'submitted.patch', task['production_paths'])
            raw['result_sha256'] = m.frozen.hybrid.base.tree_digest(result)
            raw['patch_sha256'] = hashlib.sha256(delta).hexdigest()
            for stage in raw['stages']:
                stage['source_sha256_at_launch'] = stage['source_sha256_after'] = raw['result_sha256']
            path.write_text(json.dumps(raw))
            with patch.object(m.frozen.hybrid.grader, 'invoke_oracle', wraps=m.frozen.hybrid.grader.invoke_oracle) as oracle:
                observed = m.grade(path, request, task, package)['normalized']
                calls = oracle.call_count
            passed = (intact['exit_code'] == 0 and deleted['exit_code'] == 1 and 'ModuleNotFoundError' in deleted['stderr_excerpt']
                      and observed['harness_invalid'] is True and observed['oracle_passed'] is None
                      and 'unsupported_production_deletion:bonaparte_linear.py' in observed['harness_invalid_reasons']
                      and calls == 0)
            negatives.append(dict(name='actual_pr39_production_deletion', passed=passed,
                                  actual_intact_cli=intact, actual_deleted_cli=deleted,
                                  observed_oracle_passed=observed['oracle_passed'],
                                  observed_harness_invalid=observed['harness_invalid'], reasons=observed['harness_invalid_reasons'],
                                  sealed_oracle_invocations=calls, isolated_oracle_synthetic=False))
            print(json.dumps({'negative': 'actual_pr39_production_deletion', 'passed': passed, 'oracle_invocations': calls}), flush=True)
end_hashes = code_hashes()
artifact = dict(schema_version=4, kind='independent_synthetic_harness_controls_not_model_trials',
                created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), model_calls=0, no_solver_outcomes=True,
                manifest_file_sha256=file_sha(manifest_path), code_sha256_at_start=start_hashes, code_sha256_at_end=end_hashes,
                code_stable_during_controls=start_hashes == end_hashes, audit_script_sha256=file_sha(__file__),
                all_controls_passed=start_hashes == end_hashes and all(r['control_passed'] for r in controls) and all(r['passed'] for r in negatives) and all(r['passed'] for r in visible),
                controls=controls, negative_controls=negatives, visible_baseline_controls=visible, process_cleanup_scope='original_process_group',
                detached_descendants_contained=False,
                limits='Qualification, provider, metadata/time/cleanup fields are synthetic fixtures, not native model observations. Twelve real oracles use historical base/head production-only projections; four equivalent controls cover two renames in two backend terminal formats. Nineteen negative probes isolate qualification/normalization with a synthetic verdict. PR39 deletion executes actual confined CLI help, then verifies the production-deletion guard blocks the sealed oracle. Six visible baseline commands execute through actual WorkspaceTools and the installed isolated-runtime callback. Native process-group behavior is a separate test suite; no full descendant containment.')
output = ROOT / '.confidence/benchmark/hybrid-v2-grade-independent-controls-runtime-sealed.json'
if output.exists():
    raise ValueError('Refusing to overwrite previous V2 controls')
output.write_text(json.dumps(artifact, indent=2) + '\n')
print(json.dumps(dict(artifact=str(output), controls=len(controls), negative_controls=len(negatives),
                     all_passed=artifact['all_controls_passed'], code_stable=artifact['code_stable_during_controls'],
                     sha256=file_sha(output), model_calls=0)), flush=True)
if not artifact['all_controls_passed']:
    raise SystemExit(1)
