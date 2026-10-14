#!/usr/bin/env python3
"""Independent, outcome-blind PR replay grading adapter.

Preserves raw receipts. Never invokes models, changes frozen inputs, retries a
trial/grade, or supplies feedback. `passed` is scope-valid selected-oracle
acceptance; `oracle_passed` reports the actual selected tests separately.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time


MODEL = 'claude-opus-5-5'
EFFORT = 'medium'
SCHEMA = 1
IGNORED = {'.git', '.trial-tmp'}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text())


def files(root, ignored=frozenset()):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Material root must be a real directory')
    result = []
    for path in sorted(root.rglob('*')):
        if any(part in ignored for part in path.relative_to(root).parts):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError('Symlink in material: ' + path.relative_to(root).as_posix())
        if stat.S_ISREG(mode):
            result.append(path)
        elif not stat.S_ISDIR(mode):
            raise ValueError('Nonregular material: ' + path.relative_to(root).as_posix())
    return result


def raw_tree(root):
    digest = hashlib.sha256()
    for path in files(root, IGNORED):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0' +
                      str(path.stat().st_mode & 0o777).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def curation_tree(root):
    digest = hashlib.sha256()
    for path in files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(str(path.stat().st_mode & 0o777).encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def scope_diff(base, result, production_paths):
    def inventory(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in files(root, IGNORED)}
    before, after = inventory(base), inventory(result)
    allowed = set(production_paths)
    violations = []
    injected = b'Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n'
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        parts = Path(name).parts
        if parts[0] in ('.protocol', '.confidence', '.trial-tmp', 'tests'):
            continue
        if name == 'AGENTS.md' and after.get(name) == injected:
            continue
        if name == '.gitignore' and after.get(name) == before.get(name, b'') + b'\n.trial-tmp/\n.confidence/\n':
            continue
        if name in allowed or any(name.startswith(p.rstrip('/') + '/') for p in allowed):
            continue
        if name not in before and len(parts) == 1 and name.endswith('.py'):
            continue
        violations.append(name)
    return violations


def package_identity(repository, package):
    """Trusted historical package archive only; no candidate programs run."""
    environment = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'LANG': 'C.UTF-8',
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                   'GIT_TERMINAL_PROMPT': '0'}
    data = subprocess.check_output(['/usr/bin/git', '-C', str(repository), 'archive', '--format=tar',
                                    package['revision']], env=environment, timeout=30)
    if sha(data) != package['git_archive_sha256']:
        raise ValueError('Frozen package archive mismatch')
    with tempfile.TemporaryDirectory(prefix='cp-grade-package-') as name:
        root = Path(name)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk() or not (root / member.name).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Unsafe frozen package member')
            archive.extractall(root, filter='data')
        toolkit = root / 'skills/confidence-protocol'
        for relative, key in [('SKILL.md', 'skill_sha256'), ('scripts/confidence.py', 'confidence_script_sha256')]:
            if sha((toolkit / relative).read_bytes()) != package[key]:
                raise ValueError('Frozen package file mismatch: ' + key)
        return raw_tree(toolkit)


def completion_value(call):
    terminal = call.get('terminal')
    if not isinstance(terminal, dict) or terminal.get('is_error') is True:
        return None
    value = terminal.get('structured_output')
    if not isinstance(value, dict):
        try:
            value = json.loads(terminal.get('result', ''))
        except (ValueError, TypeError):
            return None
    if not isinstance(value, dict) or set(value) != {'complete', 'summary', 'remaining'}:
        return None
    if type(value['complete']) is not bool or not isinstance(value['summary'], str):
        return None
    if not isinstance(value['remaining'], list) or not all(isinstance(x, str) for x in value['remaining']):
        return None
    return value


def finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def clean_env():
    return {'PATH': '/Library/Developer/CommandLineTools/usr/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONNOUSERSITE': '1', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_TERMINAL_PROMPT': '0'}


def invoke_oracle(script, result, directory):
    stdout_path = directory / 'grader.stdout'
    stderr_path = directory / 'grader.stderr'
    began = time.monotonic()
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        process = subprocess.Popen([sys.executable, '-B', str(script), '--workspace', str(result)],
                                   env=clean_env(), stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
    output = stdout_path.read_text(errors='replace')
    header = None
    if output.splitlines():
        try:
            header = json.loads(output.splitlines()[0])
        except ValueError:
            pass
    # An infrastructure error or absent verdict is unknown, never a solver failure.
    verdict = None
    if not timed_out and isinstance(header, dict) and 'infrastructure_error' not in header:
        reported = header.get('exit_code')
        if type(reported) is int and reported == code and type(header.get('passed')) is bool:
            if code == 0 and header['passed'] is True:
                verdict = True
            elif code != 0 and header['passed'] is False:
                verdict = False
    return {'oracle_passed': verdict, 'exit_code': code, 'timed_out': timed_out,
            'wall_seconds': time.monotonic() - began, 'header': header,
            'stdout_sha256': sha(stdout_path.read_bytes()), 'stderr_sha256': sha(stderr_path.read_bytes())}


def verify_inputs(args):
    frozen = read_json(args.study / 'frozen-requests.json')
    protocol = read_json(args.protocol)
    manifest = read_json(args.manifest)
    registration = read_json(args.registration)
    if canonical(protocol) != frozen['protocol_sha256'] or canonical(manifest) != frozen['manifest_sha256']:
        raise ValueError('Canonical frozen protocol/manifest mismatch')
    for path, key in [(args.protocol, 'protocol_file_sha256'), (args.manifest, 'private_manifest_file_sha256'),
                      (args.runner, 'runner_file_sha256'), (args.study / 'frozen-requests.json', 'frozen_requests_file_sha256')]:
        if sha(path.read_bytes()) != registration[key]:
            raise ValueError('Registered frozen file mismatch: ' + key)
    if sha(args.runner.read_bytes()) != frozen['runner_sha256']:
        raise ValueError('Frozen runner mismatch')
    tasks = {task['task_id']: task for task in manifest['tasks']}
    arms = {arm['id']: arm for arm in protocol['arms']}
    specs = {spec['trial_id']: spec for spec in frozen['trials']}
    if len(specs) != len(frozen['trials']):
        raise ValueError('Duplicate frozen trial identity')
    packages = {name: package_identity(args.repository, package) for name, package in protocol['packages'].items()
                if name != 'materialization'}
    for task in tasks.values():
        base = Path(task.get('base_snapshot', task['source_directory']))
        oracle = Path(task['oracle_script'])
        if curation_tree(base) != task['source_sha256']:
            raise ValueError('Frozen source identity mismatch: ' + task['task_id'])
        if curation_tree(oracle.parent) != task['oracle_sha256'] or sha(oracle.read_bytes()) != task['oracle_script_sha256']:
            raise ValueError('Frozen oracle identity mismatch: ' + task['task_id'])
    for spec in specs.values():
        unsigned = {k: v for k, v in spec.items() if k != 'request_sha256'}
        if canonical(unsigned) != spec['request_sha256']:
            raise ValueError('Frozen request self digest mismatch')
        if raw_tree(Path(tasks[spec['task_id']]['base_snapshot'])) != spec['source_sha256']:
            raise ValueError('Runner frozen source identity mismatch')
    return frozen, tasks, arms, specs, packages


def normalize(receipt, spec, task, grade, failures):
    main_calls = receipt.get('calls', [])
    review_calls = receipt.get('review_calls', [])
    calls = [*main_calls, *review_calls]
    model_errors = []
    if receipt.get('model_requested') != spec['model'] or spec['model'] != MODEL:
        model_errors.append('requested_model_mismatch_or_absent')
    if receipt.get('effort') != spec['effort'] or spec['effort'] != EFFORT:
        model_errors.append('requested_effort_mismatch_or_absent')
    if not calls:
        model_errors.append('observed_model_absent')
    observed, usage_models = [], []
    for index, call in enumerate(calls):
        models = call.get('observed_assistant_models', [])
        if not models:
            model_errors.append('observed_model_absent_call_' + str(index))
        if any(model != MODEL for model in models):
            model_errors.append('observed_model_mismatch_call_' + str(index))
        if call.get('requested_effort') != EFFORT:
            model_errors.append('requested_effort_mismatch_or_absent_call_' + str(index))
        for model in models:
            if model not in observed:
                observed.append(model)
        model_usage = call.get('modelUsage') or {}
        usage_models.append(list(model_usage))
        if any(model != MODEL for model in model_usage):
            model_errors.append('usage_model_mismatch_call_' + str(index))
    final = completion_value(main_calls[-1]) if main_calls else None
    declared = final['complete'] if final is not None else None
    if receipt.get('declared_complete') is not declared:
        failures.append('completion_receipt_disagrees_with_actual_terminal')
    values = [call.get('total_cost_usd') for call in calls]
    known = bool(calls) and all(finite_nonnegative(value) for value in values)
    subtotal = sum(value for value in values if finite_nonnegative(value))
    total = subtotal if known else None
    if receipt.get('total_cost_usd') != total or receipt.get('known_cost_subtotal', subtotal) != subtotal:
        failures.append('cost_receipt_disagrees_with_observed_call_costs')
    usages = [call.get('usage') for call in calls]
    token_keys = sorted({key for usage in usages if isinstance(usage, dict) for key in usage
                         if key.endswith('_tokens') and finite_nonnegative(usage[key])})
    tokens = {key: sum(usage[key] for usage in usages if isinstance(usage, dict) and finite_nonnegative(usage.get(key)))
              if all(isinstance(usage, dict) and finite_nonnegative(usage.get(key)) for usage in usages) else None
              for key in token_keys}
    oracle_passed = grade.get('oracle_passed')
    scope = grade.get('scope_violations', [])
    artifact_invalid = receipt.get('status') == 'artifact_invalid' or bool(receipt.get('artifact_error'))
    passed = False if scope or artifact_invalid else oracle_passed
    errors = [*failures, *model_errors]
    return {'schema_version': SCHEMA, 'trial_id': spec['trial_id'], 'task_id': spec['task_id'],
            'arm_id': spec['arm_id'], 'repeat': spec['repeat'], 'status': receipt.get('status'),
            'passed': passed, 'oracle_passed': oracle_passed, 'false_completion': declared is True and oracle_passed is False,
            'harness_invalid': bool(errors), 'harness_invalid_reasons': errors,
            'model_requested': receipt.get('model_requested'), 'observed_assistant_models': observed,
            'usage_models': usage_models, 'requested_effort': receipt.get('effort'), 'observed_effort': None,
            'effort_observation_note': 'Claude receipts expose requested effort; no independently observed internal effort.',
            'declared_complete': declared, 'remaining': final['remaining'] if final is not None else None,
            'completion_summary': final['summary'] if final is not None else None,
            'human_interventions': 0, 'total_cost_usd': total, 'known_cost_subtotal': subtotal, 'cost_known': known,
            'usage': usages, 'tokens': tokens, 'wall_seconds': receipt.get('wall_seconds'),
            'main_calls': len(main_calls), 'review_calls': len(review_calls),
            'tool_errors': receipt.get('tool_errors', []), 'policy_denials': receipt.get('policy_denials', []),
            'permission_denials': receipt.get('permission_denials', []),
            'denials': len(receipt.get('policy_denials', [])) + len(receipt.get('permission_denials', [])),
            'scope_violations': scope, 'artifact_invalid': artifact_invalid, 'over_budget': receipt.get('over_budget'),
            'source_sha256': receipt.get('source_sha256'), 'patch_sha256': receipt.get('patch_sha256'),
            'result_sha256': receipt.get('result_sha256'), 'request_sha256': receipt.get('request_sha256'),
            'replay_scope': task.get('replay_scope', 'Selected historical PR behavioral checks'),
            'grade_tests': task['oracle_tests'], 'grade_scope': 'Frozen selected acceptance/preservation cases only; not whole baseline regression suite.',
            'proof_packet_grade': None, 'semantic_correctness_beyond_oracle': None}


def grade_receipt(path, spec, task, frozen, package_sha):
    raw = path.read_bytes()
    receipt = json.loads(raw)
    failures = []
    for key in ('trial_id', 'task_id', 'arm_id', 'repeat'):
        if receipt.get(key) != spec[key]:
            failures.append('identity_mismatch_' + key)
    expected = {'protocol_sha256': frozen['protocol_sha256'], 'task_sha256': canonical(task),
                'request_sha256': spec['request_sha256'], 'source_sha256': spec['source_sha256'],
                'toolkit_sha256': package_sha}
    for key, value in expected.items():
        if receipt.get(key) != value:
            failures.append('frozen_binding_mismatch_' + key)
    oracle = Path(task['oracle_script'])
    base = Path(task['base_snapshot'])
    result = path.parent / 'result_snapshot'
    grade = {'oracle_passed': None, 'scope_violations': [], 'verified_at_utc': timestamp()}
    try:
        if curation_tree(base) != task['source_sha256'] or raw_tree(base) != spec['source_sha256']:
            failures.append('source_material_changed')
        if curation_tree(oracle.parent) != task['oracle_sha256'] or sha(oracle.read_bytes()) != task['oracle_script_sha256']:
            failures.append('oracle_material_changed')
        patch = path.parent / 'submitted.patch'
        if not patch.is_file() or patch.is_symlink() or sha(patch.read_bytes()) != receipt.get('patch_sha256'):
            failures.append('patch_digest_mismatch_or_absent')
        if result.exists():
            if not isinstance(receipt.get('result_snapshot'), str) or Path(receipt['result_snapshot']).resolve() != result.resolve():
                failures.append('result_location_mismatch')
            if raw_tree(result) != receipt.get('result_sha256'):
                failures.append('result_digest_mismatch')
            scope = scope_diff(base, result, task['production_paths'])
            grade['scope_violations'] = scope
            if scope != receipt.get('scope_violations', []):
                failures.append('scope_receipt_disagrees_with_artifact')
        elif receipt.get('status') != 'artifact_invalid' and not receipt.get('artifact_error'):
            failures.append('result_snapshot_absent')
        if not failures and result.exists() and receipt.get('status') != 'artifact_invalid' and not receipt.get('artifact_error'):
            grade.update(invoke_oracle(oracle, result, path.parent))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        failures.append('verification_error_' + type(error).__name__ + ': ' + str(error))
    row = normalize(receipt, spec, task, grade, failures)
    return {'schema_version': SCHEMA, 'raw_receipt_sha256': sha(raw), 'adapter_sha256': sha(Path(__file__).read_bytes()),
            'graded_at_utc': timestamp(), 'integrity_failures': failures, 'grader': grade, 'normalized': row}


def missing_row(spec):
    return {'trial_id': spec['trial_id'], 'task_id': spec['task_id'], 'arm_id': spec['arm_id'],
            'repeat': spec['repeat'], 'status': 'missing_receipt', 'passed': None, 'oracle_passed': None,
            'declared_complete': None, 'total_cost_usd': None, 'known_cost_subtotal': None,
            'wall_seconds': None, 'human_interventions': None, 'harness_invalid': None,
            'grade_scope': 'Frozen selected acceptance/preservation cases only; not whole baseline regression suite.',
            'proof_packet_grade': None, 'semantic_correctness_beyond_oracle': None}


def run(args):
    frozen, tasks, arms, specs, packages = verify_inputs(args)
    rows = []
    observed = 0
    for trial_id, spec in specs.items():
        path = args.study / 'trials' / trial_id / 'receipt.json'
        target = path.with_name('graded-receipt.json')
        if not path.exists():
            rows.append(missing_row(spec))
            continue
        try:
            if target.exists():
                graded = read_json(target)
                if sha(path.read_bytes()) != graded['raw_receipt_sha256']:
                    raise ValueError('Raw receipt changed after one-time grade')
            else:
                graded = grade_receipt(path, spec, tasks[spec['task_id']], frozen, packages[arms[spec['arm_id']]['package']])
                atomic_json(target, graded)
                print(json.dumps({'trial_id': trial_id, 'graded': True, 'oracle_passed': graded['normalized']['oracle_passed'],
                                  'harness_invalid': graded['normalized']['harness_invalid']}), flush=True)
            rows.append(graded['normalized'])
            observed += 1
        except (OSError, ValueError, KeyError) as error:
            row = missing_row(spec)
            row.update(status='receipt_unreadable', harness_invalid=True, harness_invalid_reasons=[str(error)])
            rows.append(row)
    atomic_json(args.study / 'results-normalized.json', rows)
    atomic_json(args.study / 'grading-progress.json', {'at_utc': timestamp(), 'scheduled': len(specs),
                'receipts_graded': observed, 'receipts_pending': len(specs) - observed,
                'adapter_sha256': sha(Path(__file__).read_bytes()), 'no_solver_feedback': True})
    return observed == len(specs)


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=here / 'protocol.json')
    parser.add_argument('--registration', type=Path, default=here / 'registration.json')
    parser.add_argument('--runner', type=Path, default=here / 'runner.py')
    parser.add_argument('--repository', type=Path, default=here.parents[3])
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=20)
    parser.add_argument('--max-watch-seconds', type=float, default=21600)
    args = parser.parse_args()
    for key in ('study', 'manifest', 'protocol', 'registration', 'runner', 'repository'):
        setattr(args, key, getattr(args, key).resolve())
    # Written before reading any trial receipt, including on an empty cohort.
    registration = args.study / 'grading-adapter-registration.json'
    current_sha = sha(Path(__file__).read_bytes())
    if registration.exists():
        if read_json(registration)['adapter_sha256'] != current_sha:
            raise ValueError('Grading adapter changed after registration; do not silently regrade')
    else:
        atomic_json(registration, {'schema_version': SCHEMA, 'registered_at_utc': timestamp(),
                    'adapter_sha256': current_sha, 'before_adapter_receipt_observation': True,
                    'model_calls': 0, 'solver_feedback': False, 'runtime_python': sys.version})
    deadline = time.monotonic() + args.max_watch_seconds
    while True:
        complete = run(args)
        if complete or not args.watch or time.monotonic() >= deadline:
            return
        time.sleep(min(60, max(1, args.poll_seconds)))


if __name__ == '__main__':
    main()
