#!/usr/bin/env python3
"""Read-only verification of this retained local study and installation.

Requires the owner's private evidence tree. No hosted calls or new CPU grades.
Public projections preserve hashes without exposing that private material.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('delivery_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def never_grade(*args, **kwargs):
    raise ValueError('Delivery verification requires completed cached CPU checks')


def protect_evidence(evidence):
    """Refuse Python writes to retained evidence, including cache preparation.

    Temporary reconstruction is allowed outside this root. This is a Python
    audit guard, not operating-system confinement of arbitrary subprocesses.
    Hosted calls and fresh grader invocation are separately disabled.
    """
    protected = Path(evidence).absolute()

    def contains(value):
        if not isinstance(value, (str, bytes, os.PathLike)):
            return False
        path = Path(os.fsdecode(value)).absolute()
        return path.is_relative_to(protected) or path.resolve().is_relative_to(protected.resolve())

    def guard(event, args):
        if event == 'open':
            flags = args[2] if len(args) > 2 else 0
            writing = type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and contains(args[0]):
                raise ValueError('Read-only evidence write refused')
        elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.chown', 'os.utime', 'os.truncate'):
            if contains(args[0]):
                raise ValueError('Read-only evidence mutation refused')
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            if any(contains(path) for path in args[:2]):
                raise ValueError('Read-only evidence mutation refused')

    sys.addaudithook(guard)


def complete_cache(output, followup=False):
    """Refuse incomplete recorded caches before analysis can prepare a run."""
    output = Path(output)
    require(output.is_dir() and not output.is_symlink(), 'Completed CPU cache root required')
    seal = output / 'input-seal.json'
    require(seal.is_file() and not seal.is_symlink(), 'Completed CPU cache seal required')
    sources = read(seal)['sources']
    require(isinstance(sources, dict) and sources, 'Completed CPU cache sources required')
    for name in sources:
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'Noncanonical CPU cache identity')
        if followup:
            require(len(relative.parts) == 2 and relative.name in ('initial', 'final'), 'Noncanonical followup cache identity')
            paths = [output / relative.parent / (relative.name + '-' + label) for label in ('original', 'novel')]
        else:
            require(len(relative.parts) == 1, 'Noncanonical main cache identity')
            paths = [output / relative]
        for directory in paths:
            require(directory.is_dir() and not directory.is_symlink(), 'Completed CPU trial cache required')
            receipt = directory / 'receipt.json'
            require(receipt.is_file() and not receipt.is_symlink(), 'Completed CPU receipt required')


def inventory(path):
    path = Path(path)
    require(path.is_dir() and not path.is_symlink(), 'Installed root must be a regular directory')
    result = {}
    for item in path.rglob('*'):
        require(not item.is_symlink(), 'Installed symlink refused')
        if item.is_file():
            result[item.relative_to(path).as_posix()] = {
                'sha256': sha(item), 'mode': item.stat().st_mode & 0o777}
        else:
            require(item.is_dir(), 'Nonregular installed member refused')
    return result


def check_installation(installed, repo):
    require(installed['enabled'] and installed['installed_plugin']['version'] == '0.7.0', 'Installed version/state differs')
    require(isinstance(installed['files'], dict) and installed['files'], 'Installed manifest must be nonempty')
    require(inventory(installed['source_directory']) == inventory(installed['cache_directory']) == installed['files'], 'Installed source/cache differs')
    for path, facts in installed['files'].items():
        current = Path(repo) / path
        require(sha(current) == facts['sha256'] and current.stat().st_mode & 0o777 == facts['mode'], 'Installed file differs from current repository source')


def verify(evidence):
    evidence = Path(evidence).resolve()
    protect_evidence(evidence)
    complete_cache(evidence / 'current-source-rechecks')
    complete_cache(evidence / 'followup-source-rechecks', followup=True)
    main = load('analyze')
    main.r.invoke_oracle = never_grade
    result = main.analyze(evidence / 'study', evidence / 'current-source-rechecks')
    require(result == read(evidence / 'main-analysis.json'), 'Retained main analysis differs')
    public = {key: value for key, value in result.items() if key in main.TOP_KEYS}
    public['rows'] = [{key: value for key, value in row.items() if key in main.ROW_KEYS}
                      for row in result['rows']]
    require(public == read(HERE / 'results/analysis.json'), 'Published main projection differs')
    main_counts = result['assigned'], result['current_recheck_summary']['known_agreements']
    for path, digest in read(HERE / 'results/artifact-hashes.json')['files'].items():
        require(sha(HERE / 'results' / path) == digest, 'Published main artifact hash differs')

    intake = load('analyze_intake')
    report = intake.analyze(evidence / 'intake-study', evidence / 'intake-review',
                           evidence / 'intake-review/independent-semantics-20261013T152603Z-529478ba.json',
                           HERE.parents[3])
    require(report == read(evidence / 'intake-analysis.json'), 'Retained intake analysis differs')
    require(intake.public_projection(report) == read(HERE / 'intake-results.json'), 'Published intake projection differs')
    intake_assigned = report['assigned']

    followup = load('analyze_followup')
    followup.r.invoke_oracle = never_grade
    followup.a.r.invoke_oracle = never_grade
    report = followup.analyze(evidence / 'followup-study-v2', evidence / 'followup-source-rechecks')
    require(report == read(evidence / 'followup-analysis.json'), 'Retained followup analysis differs')
    require(followup.public_projection(report) == read(HERE / 'followup-results.json'), 'Published followup projection differs')
    followup_counts = report['assigned'], report['current_recheck_summary']['checks']

    visible = evidence / 'code-review-packets/visible'
    mapping = {(row['anonymous_task'], row['anonymous_candidate']): row
               for row in read(evidence / 'code-review-packets/private-owner.json')['mapping']}
    covered = set()
    for index in read(HERE / 'quality-results/index.json')['reviewers']:
        name = index['reviewer']
        original = evidence / 'code-review-jury' / (name + '.json')
        published = HERE / 'quality-results' / ('jury-' + name + '.json')
        require(sha(original) == index['original_sha256'], 'Original jury hash differs')
        require(sha(published) == index['public_sha256'], 'Published jury hash differs')
        for candidate in read(published)['candidates']:
            key = candidate['task'], candidate['candidate']
            require(key not in covered, 'Duplicate anonymous candidate')
            covered.add(key)
            owner = mapping[key]
            require(candidate['unmasked_assignment'] == {
                field: owner[field] for field in ('trial_id', 'task_id', 'arm_id', 'repeat')}, 'Jury assignment mapping differs')
            patch = visible / key[0] / 'candidates' / key[1] / 'change.patch'
            require(sha(patch) == owner['reviewer_patch_sha256'], 'Anonymous patch hash differs')
            for path, facts in owner['reviewer_production_hashes'].items():
                require(sha(patch.parent / 'production' / path) == facts['sha256'], 'Anonymous source hash differs')
    require(covered == set(mapping) and len(covered) == 48, 'Anonymous review coverage differs')
    probe = read(HERE / 'quality-results/posthoc-routing.json')
    require(probe['script_sha256'] == sha(HERE / 'posthoc_routing_probe.py'), 'Routing probe script hash differs')
    require(len(probe['rows']) == 16, 'Routing probe observation count differs')
    for row in probe['rows']:
        require(row['exit_code'] == 0 and row['result']['steer_exercised'] and row['result']['process_closed'], 'Routing probe lifecycle differs')
        owner = mapping['T02', row['anonymous_candidate']]
        for path, digest in row['result']['source_files'].items():
            require(digest == owner['reviewer_production_hashes'][path]['sha256'], 'Routing probe source differs')

    installed = read(evidence / 'installation.json')
    repo = HERE.parents[3]
    require(installed['files'] == read(HERE / 'installation-results.json')['file_manifest'], 'Installed manifest differs from public release')
    check_installation(installed, repo)
    backup = Path(installed['backup_directory'])
    require(read(backup / 'source-0.6.0/.codex-plugin/plugin.json')['version'] == '0.6.0', 'Prior version backup differs')
    require(read(evidence / 'installed-doctor.json')['exit_code'] == 0, 'Installed doctor did not succeed')
    require(read(evidence / 'installed-doctor.json')['result']['tool_version'] == '0.7.0', 'Installed doctor version differs')
    print(json.dumps({'main_assignments': main_counts[0], 'intake_assignments': intake_assigned,
                      'followup_assignments': followup_counts[0],
                      'anonymous_candidates_reviewed': len(covered), 'supplemental_routing_observations': len(probe['rows']),
                      'current_main_cpu_checks': main_counts[1], 'current_followup_cpu_checks': followup_counts[1],
                      'installed_version': installed['installed_plugin']['version'], 'installed_files': len(installed['files']),
                      'scope': 'Current recorded bytes and executed retained checks; no claim of historical continuous custody or full preimplementation review coverage'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    verify(args.evidence)
