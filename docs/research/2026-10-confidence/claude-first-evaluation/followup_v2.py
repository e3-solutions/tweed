#!/usr/bin/env python3
"""Prospective eight-input custody amendment; original followup runtime unchanged.

Only main/execution-scratch descendants are outside first-stage input custody.
The excluded directory itself and every ancestor must remain regular directories.
Preparation copies already qualified controls; it issues no inference or grading.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


original = load('prospective_followup_original', HERE / 'followup.py')
r = original.r
METHOD, TOKENS, NAMES, REQUIREMENTS = original.METHOD, original.TOKENS, original.NAMES, original.REQUIREMENTS
EXCLUSION = {'path': 'main/execution-scratch', 'reason': 'Ephemeral confined first-stage execution scratch is neither candidate source nor followup input; no other path is excluded'}
SCHEMA = 'followup-input-custody-v2'


def require(condition, reason):
    if not condition: raise ValueError(reason)


def regular_ancestors(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        require(not entry.is_symlink(), 'Symlink input/ancestor refused: ' + str(entry))
    return path


def trial_inventory(path):
    """Skip one exact subtree, without following it or any other symlink."""
    path = regular_ancestors(path)
    require(path.is_dir(), 'First-stage trial must be a regular directory')
    result = {}
    def walk(directory):
        for item in sorted(directory.iterdir()):
            relative = item.relative_to(path).as_posix()
            require(not item.is_symlink(), 'Symlink first-stage input refused: ' + relative)
            if relative == EXCLUSION['path']:
                require(item.is_dir(), 'Excluded scratch root must be a regular directory')
                continue
            if item.is_dir(): walk(item)
            else:
                require(item.is_file(), 'Nonregular first-stage input refused: ' + relative)
                result[relative] = {'sha256': r.sha(item), 'mode': item.stat().st_mode & 0o777}
    walk(path)
    return result


def private_runtime(payload):
    """Clone functions into one private namespace; no global monkeypatching."""
    initial = Path(payload['initial_study'])
    trials = {str((initial / 'trials' / row['trial_id']).absolute()) for row in payload['roster']}
    def inventory(path):
        path = regular_ancestors(path)
        return trial_inventory(path) if str(path) in trials else r.inventory(path)
    proxy = SimpleNamespace(**vars(r)); proxy.inventory = inventory
    scope = dict(vars(original)); scope['r'] = proxy
    for name, function in vars(original).items():
        if isinstance(function, FunctionType) and function.__module__ == original.__name__:
            cloned = FunctionType(function.__code__, scope, function.__name__, function.__defaults__, function.__closure__)
            cloned.__kwdefaults__ = function.__kwdefaults__; scope[name] = cloned
    scope['verify_declaration'] = verify_declaration; scope['verify'] = verify
    return SimpleNamespace(**scope)


def closed_inputs(payload):
    initial = regular_ancestors(payload['initial_study'])
    for name in ('requests.json', 'results.json'):
        path = regular_ancestors(initial / name); require(path.is_file(), 'Regular main closure/request required')
    requests = r.read(initial / 'requests.json'); closure = r.read(initial / 'results.json')
    require(len(requests) == len(closure) == 48, 'Full48 closure required')
    lookup = {row['trial_id']: row for row in closure}
    require(len(lookup) == 48 and len({row['trial_id'] for row in requests}) == 48 and set(lookup) == {row['trial_id'] for row in requests}, 'Duplicate/missing closure identity')
    for request in requests:
        directory = regular_ancestors(initial / 'trials' / request['trial_id'])
        receipt = directory / 'receipt.json'; regular_ancestors(receipt)
        require(receipt.is_file() and r.read(receipt) == lookup[request['trial_id']], 'Normalized closure differs from regular raw receipt')
        require(all(lookup[request['trial_id']].get(key) == request[key] for key in ('trial_id', 'task_id', 'arm_id', 'repeat')), 'Closure assigned identity differs')
    expected = [{key: row[key] for key in ('trial_id', 'task_id', 'arm_id', 'repeat')} for row in requests if row['task_id'] == 'tweed-pr40']
    require(expected == payload['roster'] and len(expected) == 8, 'Same eight PR40 identities required')
    adapter = r.route(payload['arm'])
    for assigned in expected:
        directory = initial / 'trials' / assigned['trial_id']; trial_inventory(directory)
        source = directory / 'result_snapshot'; regular_ancestors(source); r.inventory(source)
        require(source.is_dir() and (source / 'bonaparte').is_file(), 'All eight regular production artifacts required')
        patch = directory / 'submitted.patch'; regular_ancestors(patch)
        require(patch.is_file(), 'All eight regular production patches required')
        raw = lookup[assigned['trial_id']]
        require(r.sha(patch) == raw.get('patch_sha256') and adapter.frozen.base.tree_digest(source) == raw.get('result_sha256'), 'Candidate source/patch receipt binding differs')
    return closure


def current_witness(payload):
    """Validate completed analysis and cached CPU checks, without reruns."""
    witness = payload['analysis_witness']
    analyzer = load('prospective_followup_analysis', HERE / 'analyze.py')
    def never_regrade(*_args, **_kwargs): raise ValueError('Followup preparation may only reuse completed current rechecks')
    analyzer.r.invoke_oracle = never_regrade
    current = analyzer.analyze(Path(payload['initial_study']), Path(witness['rechecks']))
    require(current == r.read(witness['analysis']), 'Strict current primary analysis differs from supplied witness')
    summary = current['current_recheck_summary']
    require(summary is not None and summary['known_disagreements'] == 0 and summary['known_agreements'] == sum(row['eligible'] is True for row in current['rows']), 'All eligible current-source grades must agree with historical primary grades')
    return current


def prepare(prepared, output, analysis, rechecks, amendment):
    prepared, output = regular_ancestors(prepared), regular_ancestors(output)
    require(not output.exists(), 'V2 preparation requires new output; original preparation preserved')
    require(all(not (prepared / name).exists() and not (prepared / name).is_symlink() for name in ('input-seal.json', 'trials')), 'Amendment requires original preparation with no sealed inputs or calls')
    regular_ancestors(prepared / 'declaration.json')
    prior = original.verify_declaration(prepared)
    support_regular(prior)
    for path in (analysis, rechecks, amendment): regular_ancestors(path)
    require(Path(analysis).is_file() and Path(amendment).is_file() and Path(rechecks).is_dir(), 'Analysis/recheck/amendment witnesses required')
    require(prior['seconds'] == 120 and prior['claude_budget_usd'] == 1 and prior['model'] == 'claude-opus-5-5' and prior['effort'] == 'medium' and prior['requirements'] == REQUIREMENTS, 'Original prospective probe route/budget/requirements changed')
    payload = copy.deepcopy(prior)
    payload.update(custody_schema=SCHEMA, custody_exclusion=EXCLUSION, original_preparation=str(prepared), original_declaration_sha256=r.sha(prepared / 'declaration.json'),
                   analysis_witness={'analysis': str(Path(analysis).absolute()), 'rechecks': str(Path(rechecks).absolute())}, amendment=str(Path(amendment).absolute()))
    closed_inputs(payload); current_witness(payload)
    require(r.read(prepared / 'controls/results.json').get('passed') is True, 'Original qualified controls absent')
    output.mkdir(parents=True)
    # Complete byte-identical control/oracle dependencies are checked before
    # copying; historical result headers retain their original paths.
    for name in ('novel', 'controls'):
        source = prepared / name; inventory = r.inventory(source)
        shutil.copytree(source, output / name)
        require(r.inventory(output / name) == inventory, 'Copied qualified preparation differs')
        payload['trees'][str(output / name)] = inventory
    payload['oracle_script'] = str(output / 'novel/oracle/evaluate.py')
    for path in (HERE / 'followup_v2.py', HERE / 'test_followup_v2.py', HERE / 'analyze.py', HERE / 'test_analyze.py', prepared / 'declaration.json', Path(analysis), Path(amendment)):
        payload['files'][str(path.absolute())] = r.sha(path)
    payload['trees'][str(Path(rechecks).absolute())] = r.inventory(rechecks)
    payload['limitations'].append(EXCLUSION['reason'])
    r.write(output / 'declaration.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
    return payload


def verify_declaration(output):
    output = regular_ancestors(output); regular_ancestors(output / 'declaration.json')
    support_regular(r.read(output / 'declaration.json')['payload'])
    payload = original.verify_declaration(output)
    require(payload.get('custody_schema') == SCHEMA and payload.get('custody_exclusion') == EXCLUSION, 'V2 custody amendment identity differs')
    closed_inputs(payload)
    return payload


def support_regular(payload):
    for path in payload['files']:
        require(regular_ancestors(path).is_file(), 'Regular support file required')
    for path in payload['trees']:
        require(regular_ancestors(path).is_dir(), 'Regular support tree required')


def seal(output):
    output = regular_ancestors(output); declaration = verify_declaration(output)
    regular_ancestors(output / 'input-seal.json')
    current_witness(declaration)
    payload = private_runtime(declaration).seal(output)
    require(len(payload['inputs']) == 8 and all(row['available'] for row in payload['inputs']), 'All eight unchanged sources must remain included')
    # Declare the exact exclusion in the input seal, independently of prose.
    payload.update(custody_schema=SCHEMA, custody_exclusion=EXCLUSION)
    r.write(output / 'input-seal.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
    return payload


def verify(output):
    declaration = verify_declaration(output)
    require(regular_ancestors(Path(output) / 'input-seal.json').is_file(), 'Regular input seal required')
    wrapper = r.read(Path(output) / 'input-seal.json')
    require(wrapper['payload'].get('custody_schema') == SCHEMA and wrapper['payload'].get('custody_exclusion') == EXCLUSION, 'Input seal amendment identity differs')
    # Call cloned original verification without recursion through this wrapper.
    runtime = private_runtime(declaration)
    return clone_verify(runtime)(output)


def clone_verify(runtime):
    function = original.verify
    return FunctionType(function.__code__, {**runtime.run.__globals__, 'verify_declaration': verify_declaration}, function.__name__, function.__defaults__, function.__closure__)


def run_cell(row, declaration, output): return private_runtime(declaration).run_cell(row, declaration, Path(output))


def run(output, workers=2):
    declaration = verify_declaration(output)
    return private_runtime(declaration).run(Path(output), workers)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'seal', 'run']); parser.add_argument('--output', type=Path, required=True)
    for name in ('prepared', 'analysis', 'rechecks', 'amendment'): parser.add_argument('--' + name, type=Path)
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    if args.action == 'prepare':
        if any(getattr(args, key) is None for key in ('prepared', 'analysis', 'rechecks', 'amendment')): parser.error('prepare requires --prepared --analysis --rechecks --amendment')
        prepare(args.prepared, args.output, args.analysis, args.rechecks, args.amendment)
    elif args.action == 'seal': seal(args.output)
    else: run(args.output, args.workers)
