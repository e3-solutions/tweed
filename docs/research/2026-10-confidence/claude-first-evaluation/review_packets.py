#!/usr/bin/env python3
"""Private source-only, metadata-blinded packets after closed48 validation.

Provide reviewers ONLY output/visible. Owner mapping/provenance stay outside it.
This formatter does not launch reviewers or confer filesystem confinement.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import random
import re
import shutil
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('blind_packets_analysis', HERE / 'analyze.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
r = a.r
EXCLUDED = {'.git', '.confidence', '.claude', '.codex', '.agents', 'AGENTS.md', 'CLAUDE.md', '.protocol', '.trial-tmp'}
RESERVED = {'sitecustomize.py', 'usercustomize.py', 'conftest.py', 'tests.py', 'pytest.py', 'hypothesis.py'} | {name + '.py' for name in sys.stdlib_module_names}
SELF_ATTRIBUTION = re.compile(r'\b(?:generated|implemented|written|authored|created|produced)\s+(?:by|with|using)\b[^\n]{0,120}\b(?:opus|haiku|astra|luna|terra|gpt[- ]?6|claude)\b', re.I)
RUBRIC = """Review the source against the supplied requirements. You have no executed outcome evidence.

For each candidate, report concrete findings with the relative file and line,
exact code, behavioral consequence, requirement or engineering basis, and a
minimal repair. Separate a demonstrated source property from an unexecuted
hypothesis. Propose a discriminating executable counterexample when useful;
the owner executes it later, outside this review. Do not claim tests ran.

For complexity findings, name a layer or abstraction that can be removed and
show how the simpler replacement preserves the required behavior. Explain any
tradeoff. Code size alone is not quality, and necessary complexity is not a
defect. Examine interfaces, duplicated decisions, state handling, regression
risks, and whether the next bounded change requires unnecessary edits.

Assess requirements and engineering standards separately. Use observable
consequences rather than taste or attractive formatting. Record no finding
when none is supported, with inspection limits. Do not infer authors/models,
guess executed acceptance, or rank providers. Candidate identifiers are anonymous.
"""


def relative(path):
    value = Path(path)
    a.require(not value.is_absolute() and '..' not in value.parts and value.parts, 'Unsafe production path')
    return value


def ordinary(path, root):
    for component in (path, *path.parents):
        if component == root.parent: break
        a.require(not component.is_symlink(), 'Reviewer source symlink refused')
    a.require(path.is_file(), 'Reviewer source must be a regular file')


def production_files(base, candidate, paths):
    """Declared paths plus new safe regular root helpers; deletions remain visible."""
    base, candidate = Path(base), Path(candidate)
    allowed = set()
    for name in paths:
        rel = relative(name)
        for root in (base, candidate):
            path = root / rel
            if path.is_symlink(): raise ValueError('Production symlink refused')
            if path.is_dir():
                for child in path.rglob('*'):
                    if child.is_symlink(): raise ValueError('Production subtree symlink refused')
                    if child.is_file(): allowed.add(child.relative_to(root).as_posix())
                    elif not child.is_dir(): raise ValueError('Production subtree special file refused')
            elif path.exists():
                ordinary(path, root); allowed.add(rel.as_posix())
            else: allowed.add(rel.as_posix())
    existing = {path.name for path in base.iterdir()}
    for path in candidate.glob('*.py'):
        if path.name in existing: continue
        a.require(path.name not in RESERVED, 'Unsafe/shadowing helper name refused')
        ordinary(path, candidate); allowed.add(path.name)
    before, after = {}, {}
    for name in sorted(allowed):
        for root, target in ((base, before), (candidate, after)):
            path = root / name
            if path.exists():
                ordinary(path, root); target[name] = path
    return before, after


def copy_files(files, destination):
    hashes = {}
    for name, source in sorted(files.items()):
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target); hashes[name] = {'sha256': r.sha(target), 'mode': target.stat().st_mode & 0o777}
    return hashes


def baseline_files(base):
    files = {}
    for path in sorted(base.rglob('*')):
        name = path.relative_to(base)
        if any(part in EXCLUDED for part in name.parts): continue
        a.require(not path.is_symlink(), 'Baseline source symlink refused')
        if path.is_file(): files[name.as_posix()] = path
        elif not path.is_dir(): raise ValueError('Baseline special file refused')
    return files


def verify_candidate(study, row, base_adapter, public, public_inventory):
    directory = study / 'trials' / row['trial_id']; candidate = directory / 'result_snapshot'
    patch = directory / 'submitted.patch'; bindings = row['artifact_bindings']
    if not candidate.exists():
        a.require(not row['patch_bound'], 'Bound production patch has no source')
        return None, None, 'missing-source'
    a.require(candidate.is_dir() and not candidate.is_symlink(), 'Candidate source nonregular')
    if 'result_sha256' in bindings:
        a.require(base_adapter.tree_digest(candidate) == bindings['result_sha256'], 'Candidate source drift since analysis')
        binding = 'recorded-result'
    else:
        a.require(r.digest(r.inventory(candidate)) == bindings.get('unbound_current_result_inventory_sha256'), 'Unbound candidate source drift since analysis')
        binding = 'current-inventory-only'
    if row['patch_bound']:
        a.bound(patch, bindings['patch_sha256'], 'Private candidate patch')
        exported = public / 'patches' / (row['trial_id'] + '.patch')
        if row['trial_id'] in public_inventory.get('privacy_excluded_patches', {}):
            a.require(not exported.exists(), 'Privacy-excluded patch unexpectedly public')
        else:
            a.bound(exported, bindings['patch_sha256'], 'Previously exported candidate patch')
            a.require(patch.read_bytes() == exported.read_bytes(), 'Private/exported patch differs')
        return candidate, patch, binding
    return candidate, None, binding


def potential_unblinding(before, after):
    warnings = []
    for name, source in after.items():
        old = before[name].read_text(errors='replace').splitlines() if name in before else []
        for number, line in enumerate(source.read_text(errors='replace').splitlines(), 1):
            if line not in old and SELF_ATTRIBUTION.search(line):
                warnings.append({'path': name, 'line': number, 'reason': 'Added source self-attribution could reveal author/model; bytes preserved'})
    return warnings


def build(study, public, output, seed=6102032, rechecks=None):
    study, public, output = Path(study).resolve(), Path(public).resolve(), Path(output).resolve()
    a.require(not output.exists(), 'Reviewer packet output must be new')
    # Revalidation compares recorded-byte evidence only; no grading/model calls.
    published = r.read(public / 'analysis.json')
    if published.get('current_recheck_summary') is not None:
        a.require(rechecks is not None, 'Source-rechecked analysis requires its existing recheck directory')
        for row in published['rows']:
            if row['eligible']:
                a.require((Path(rechecks) / row['trial_id'] / 'receipt.json').is_file(), 'Existing current recheck receipt absent')
    def refuse_regrade(*_args, **_kwargs): raise ValueError('Review packet export cannot execute grading or model calls')
    # This is the formatter's private imported helper namespace, not a global
    # process/module patch. Rechecks must already exist and are read-only here.
    r.invoke_oracle = refuse_regrade
    current = a.analyze(study, rechecks)
    a.require(current == published, 'Public analysis differs from current closed48 validation')
    public_inventory = r.read(public / 'artifact-hashes.json')
    for name, expected in public_inventory['files'].items():
        a.bound(public / relative(name), expected, 'Public closed48 artifact')
    payload = r.verify(study)
    tasks = {task['task_id']: task for task in r.read(payload['config']['manifest'])['tasks']}
    requests = r.read(study / 'requests.json')
    a.validate_roster(requests, tasks, a.ARMS)
    rows = {row['trial_id']: row for row in published['rows']}
    a.require(set(rows) == {q['trial_id'] for q in requests}, 'Review roster differs from assigned48')
    shuffled = sorted(rows); rng = random.Random(seed); rng.shuffle(shuffled)
    anonymous = {trial: 'C' + str(index + 1).zfill(3) for index, trial in enumerate(shuffled)}
    task_order = sorted(tasks); rng.shuffle(task_order)
    groups = {task: 'T' + str(index + 1).zfill(2) for index, task in enumerate(task_order)}
    adapter = r.route(payload['config']['arms'][0]).frozen.base
    # Validate every input before creating any packet directory.
    validated = {}; baselines = {task_id: baseline_files(Path(task['base_snapshot'])) for task_id, task in tasks.items()}
    for trial in shuffled:
        row = rows[trial]; task = tasks[row['task_id']]
        source, patch, binding = verify_candidate(study, row, adapter, public, public_inventory)
        files = production_files(Path(task['base_snapshot']), source, task['production_paths']) if source is not None else None
        validated[trial] = (source, patch, binding, files)
    output.mkdir(parents=True); visible = output / 'visible'; visible.mkdir()
    (visible / 'REVIEW.md').write_text(RUBRIC)
    private_mapping = []
    for task_id in task_order:
        task = tasks[task_id]; group = visible / groups[task_id]; group.mkdir()
        requirements = task.get('requirements') or task.get('prompt')
        a.require(isinstance(requirements, str) and requirements, 'Task requirements absent')
        (group / 'requirements.md').write_text(requirements + '\n\nAllowed production paths:\n' + '\n'.join(task['production_paths']) + '\n')
        copy_files(baselines[task_id], group / 'baseline')
        for trial in shuffled:
            row = rows[trial]
            if row['task_id'] != task_id: continue
            label = anonymous[trial]; target = group / 'candidates' / label; target.mkdir(parents=True)
            source, original_patch, binding, files = validated[trial]
            if source is None:
                (target / 'status.txt').write_text('missing-source\n')
                projection_hashes = {}; reviewer_patch = None
            else:
                before, after = files
                projection_hashes = copy_files(after, target / 'production')
                # Trusted patch builder strips paths/metadata outside production.
                # New valid helpers and deleted production files are included.
                packet_patch, _ = a.rebuild_patch(SimpleNamespace(frozen=SimpleNamespace(base=adapter)), Path(task['base_snapshot']), source, target / 'change.patch', task['production_paths'])
                if original_patch is not None:
                    a.require(packet_patch == original_patch.read_bytes(), 'Reviewer production patch differs from bound original')
                reviewer_patch = r.sha(target / 'change.patch')
                (target / 'status.txt').write_text('available\n')
            private_mapping.append({'anonymous_candidate': label, 'anonymous_task': groups[task_id], 'trial_id': trial,
                                    'task_id': task_id, 'arm_id': row['arm_id'], 'repeat': row['repeat'],
                                    'model_requested': row['model_requested'], 'source_binding': binding,
                                    'potential_unblinding': potential_unblinding(*files) if files is not None else [],
                                    'source_sha256': row['artifact_bindings'].get('result_sha256'),
                                    'reviewer_production_hashes': projection_hashes, 'reviewer_patch_sha256': reviewer_patch})
    visible_hashes = r.inventory(visible)
    owner = {'seed': seed, 'assigned': 48, 'mapping': private_mapping, 'visible_inventory': visible_hashes,
             'visible_inventory_sha256': r.digest(visible_hashes), 'parent_registration_sha256': published['registration_sha256'],
             'parent_analysis_sha256': r.sha(public / 'analysis.json'), 'parent_public_inventory_sha256': r.sha(public / 'artifact-hashes.json'),
             'exporter_sha256': r.sha(__file__), 'exporter_tests_sha256': r.sha(HERE / 'test_review_packets.py'),
             'limitations': ['Private packet creation is not publication', 'Only visible/ may be provided to reviewers; owner mapping stays outside reviewer access',
                            'Metadata is blinded, but source style/provider-specific product code may reveal clues',
                            'No executed outcome, model label or quality score supplied to reviewers',
                            'Formatter does not launch models or enforce actual reviewer tool/filesystem confinement']}
    r.write(output / 'private-owner.json', owner)
    return owner


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True); parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seed', type=int, default=6102032)
    parser.add_argument('--rechecks', type=Path, help='Existing complete source-recheck directory, read only')
    args = parser.parse_args(); owner = build(args.study, args.public, args.output, args.seed, args.rechecks)
    print(json.dumps({'assigned': owner['assigned'], 'visible_inventory_sha256': owner['visible_inventory_sha256']}))
