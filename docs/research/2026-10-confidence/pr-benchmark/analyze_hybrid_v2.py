#!/usr/bin/env python3
"""Read-only analysis of a closed, independently audited V2 replay.

The two primary comparisons change the peer at a fixed main provider. This
utility changes no grade, imputes no missing outcome, and makes no vendor ranking.
The CLI refuses live/partial arrays; analyze() also supports synthetic unknown
assignments so the missing-data definitions can be checked before closure.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
from functools import lru_cache
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent

def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

summary = module('v2_analysis_frozen_summary', 'summarize.py')
exporter = module('v2_analysis_closed_export', 'export_completed_study.py')
ARMS = {
    'astra_main_astra_peer': ('astra', 'astra'),
    'opus_main_opus_peer': ('opus', 'opus'),
    'astra_main_opus_peer': ('astra', 'opus'),
    'opus_main_astra_peer': ('opus', 'astra'),
}
CONTRASTS = [
    ('astra_main_opus_peer', 'astra_main_astra_peer'),
    ('opus_main_astra_peer', 'opus_main_opus_peer'),
]
ROLES = ['test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair']
PEERS = {'test_designer', 'adversarial_reviewer'}
BENCHMARK = 'confidence-mixed-provider-v2-2026-10-12'
REGISTRATION_ANCHOR = HERE / 'HYBRID-V2-REGISTRATION.json'


def fail(message):
    raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def sha(path):
    return exporter.sha(path)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('Duplicate JSON object key: ' + key)
        result[key] = value
    return result


def read(path):
    return json.loads(exporter.regular(path).read_text(), object_pairs_hook=no_duplicates,
                      parse_constant=lambda value: fail('Nonfinite JSON value: ' + value))


def finite_tree(value):
    if type(value) is float and not math.isfinite(value):
        fail('Nonfinite evidence')
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def nullable_bool(row, key):
    value = row.get(key)
    if value is not None and type(value) is not bool:
        fail('Expected boolean or null: ' + key)
    return value


def nonnegative(row, key):
    value = row.get(key)
    if value is not None and (type(value) not in (int, float) or
                              not math.isfinite(value) or value < 0):
        fail('Expected finite nonnegative numeric or null: ' + key)
    return value


def identity(row):
    if not isinstance(row, dict):
        fail('Expected trial object')
    task, arm, repeat = row.get('task_id'), row.get('arm_id'), row.get('repeat')
    if not isinstance(task, str) or not exporter.ID.fullmatch(task) or arm not in ARMS:
        fail('Unregistered task/arm identity')
    if type(repeat) is not int or repeat not in (1, 2):
        fail('Repeat must be integer 1 or 2')
    trial = task + '--' + arm + '--r' + str(repeat)
    if row.get('trial_id') != trial:
        fail('Trial ID differs from task/arm/repeat')
    return task, arm, repeat


def validate_schedule(schedule):
    if not isinstance(schedule, list) or len(schedule) != 48:
        fail('V2 requires the complete 48-assignment schedule')
    keys = [identity(row) for row in schedule]
    tasks = sorted({key[0] for key in keys})
    expected = {(task, arm, repeat) for task in tasks for arm in ARMS for repeat in (1, 2)}
    if len(tasks) != 6 or len(set(keys)) != 48 or set(keys) != expected:
        fail('Schedule must be exactly six tasks × four arms × two repeats')
    return tasks, set(keys)


def validate_protocol(protocol):
    if not isinstance(protocol, dict):
        fail('Expected V2 protocol object')
    if protocol.get('benchmark_id') != BENCHMARK or protocol.get('adapter_version') != 2:
        fail('Only the separate registered V2 protocol is accepted')
    arms = protocol.get('arms', [])
    if (not isinstance(arms, list) or not all(isinstance(a, dict) for a in arms) or
            len(arms) != 4 or {a.get('id'): (a.get('main_model'), a.get('peer_model'))
                         for a in arms} != ARMS):
        fail('Protocol arm assignments differ')
    primary = protocol.get('analysis', {}).get('primary_comparisons', [])
    if (not isinstance(primary, list) or not all(isinstance(x, dict) for x in primary) or
            [(x.get('intervention'), x.get('control')) for x in primary] != CONTRASTS):
        fail('Only registered fixed-main primary contrasts are accepted')


def validate_row(row):
    identity(row)
    finite_tree(row)
    if not isinstance(row.get('status'), str):
        fail('Receipt status must be explicit')
    for field in ('passed', 'oracle_passed', 'harness_invalid', 'declared_complete',
                  'truthful_success', 'false_completion', 'cost_known', 'artifact_invalid', 'over_budget'):
        nullable_bool(row, field)
    for field in ('total_cost_usd', 'known_cost_subtotal', 'wall_seconds', 'human_interventions'):
        nonnegative(row, field)
    if row.get('proof_packet_grade') is not None or row.get('semantic_correctness_beyond_oracle') is not None:
        fail('V2 did not assess proof-packet quality or correctness beyond its oracle')
    if row.get('status') == 'missing_receipt':
        for field in ('passed', 'oracle_passed', 'harness_invalid', 'declared_complete',
                      'truthful_success', 'false_completion', 'total_cost_usd', 'known_cost_subtotal',
                      'cost_known', 'wall_seconds', 'human_interventions'):
            if row.get(field) is not None:
                fail('Missing assignment must retain unknown ' + field)
        return
    if type(row.get('harness_invalid')) is not bool or type(row.get('truthful_success')) is not bool:
        fail('Observed V2 receipt requires explicit eligibility and truthful-success facts')
    if (row.get('main_model'), row.get('peer_model')) != ARMS[row['arm_id']]:
        fail('Row provider assignment differs from registered arm')
    stages = row.get('stage_usage')
    missing = row.get('missing_required_reviews')
    if not isinstance(stages, list) or not all(isinstance(stage, dict) for stage in stages):
        fail('Observed V2 receipt requires stage metadata')
    if (not isinstance(missing, list) or not all(isinstance(role, str) and role in PEERS for role in missing)
            or len(set(missing)) != len(missing)):
        fail('Malformed required-review gaps')
    roles = [stage.get('role') for stage in stages]
    if row['harness_invalid'] is False:
        q = row.get('stage_qualification')
        if roles != ROLES:
            fail('An eligible receipt requires all four registered stages in order')
        if (not isinstance(q, list) or len(q) != 4 or not all(isinstance(c, dict) for c in q) or
                [c.get('role') for c in q] != ROLES or
                any(not (c.get('passed') is True and c.get('skipped') is False or
                         c.get('passed') is None and c.get('skipped') is True) for c in q)):
            fail('Eligible receipt must have qualified or explicitly skipped V2 stages')
        for stage, check in zip(stages, q):
            if check['passed'] is True and (type(stage.get('timed_out')) is not bool or
                                           type(stage.get('process_exit')) is not int):
                fail('A qualified eligible stage requires known lifecycle facts')
    for stage in stages:
        for field in ('declared_complete', 'timed_out'):
            nullable_bool(stage, field)
        for field in ('total_cost_usd', 'wall_seconds', 'process_cleanup_seconds'):
            nonnegative(stage, field)
        if stage.get('process_exit') is not None and type(stage['process_exit']) is not int:
            fail('Process exit must be integer or null')
        if stage.get('timed_out') is True and stage.get('declared_complete') is not None:
            fail('A timed-out stage cannot have a valid terminal declaration')
        if stage.get('process_exit') not in (0, None) and stage.get('declared_complete') is not None:
            fail('A failed stage cannot have a valid terminal declaration')
    if roles == ROLES:
        if row['declared_complete'] is not stages[-1].get('declared_complete'):
            fail('Final declaration must be from the repair stage')
        for stage in stages:
            if stage['role'] in PEERS and stage.get('declared_complete') is not True and stage['role'] not in missing:
                fail('Unfinished required peer must be a recorded gap')
    if row.get('over_budget') is True and row['harness_invalid'] is False:
        fail('Over-budget receipt cannot be eligible')
    if row.get('artifact_invalid') is True and row.get('passed') is True:
        fail('Invalid artifact cannot be accepted')
    if row.get('passed') is True and row.get('oracle_passed') is not True:
        fail('Accepted task requires an observed passing oracle')
    expected_false = (row['declared_complete'] is True and row['oracle_passed'] is False
                      if row.get('declared_complete') is not None and row.get('oracle_passed') is not None else None)
    if row.get('false_completion') is not expected_false:
        fail('False-completion fact differs from declaration/observed oracle')
    costs = [stage.get('total_cost_usd') for stage in stages]
    known = [value for value in costs if value is not None]
    total = sum(known) if len(known) == len(stages) else None
    if row.get('total_cost_usd') != total or row.get('known_cost_subtotal') != sum(known):
        fail('Reported cost aggregation differs from its stage facts')
    if row.get('cost_known') is not (total is not None):
        fail('Cost-known flag differs from observed total')
    if row['truthful_success'] is True:
        q = row.get('stage_qualification')
        if (not accepted(row) or row.get('declared_complete') is not True or missing or roles != ROLES
                or any(s.get('declared_complete') is not True for s in stages if s.get('role') in PEERS)
                or not isinstance(q, list) or len(q) != 4 or
                any(not isinstance(c, dict) or c.get('passed') is not True or c.get('skipped') is True for c in q) or
                any(s.get('process_exit') != 0 or s.get('timed_out') is not False for s in stages)):
            fail('Impossible strict truthful-success facts')


def accepted(row):
    return row.get('passed') is True and row.get('harness_invalid') is False


def outcome(row):
    """Valid-only complete-case outcome; invalid and missing are excluded."""
    return row.get('passed') if row.get('harness_invalid') is False else None


def verified_acceptance_possibility(row):
    """Known ineligibility fixes verified acceptance at zero, not oracle failure."""
    if row.get('harness_invalid') is True:
        return False
    return outcome(row)


def peer_closed(row):
    if row.get('status') == 'missing_receipt':
        return None
    stages = row['stage_usage']
    if [stage.get('role') for stage in stages] != ROLES:
        return None
    return not row['missing_required_reviews'] and all(
        stage.get('declared_complete') is True for stage in stages if stage['role'] in PEERS)


def arm_summary(rows):
    observed = [row for row in rows if row.get('status') != 'missing_receipt']
    eligible = [row for row in observed if row['harness_invalid'] is False]
    known = [row for row in eligible if row.get('oracle_passed') is not None]
    declarations = [row for row in eligible if row.get('declared_complete') is True]
    false_denom = [row for row in declarations if row.get('oracle_passed') is not None]
    false_num = sum(row['oracle_passed'] is False for row in false_denom)
    totals = [row['total_cost_usd'] for row in rows if row.get('total_cost_usd') is not None]
    subtotals = [row['known_cost_subtotal'] for row in rows if row.get('known_cost_subtotal') is not None]
    count = sum(accepted(row) for row in rows)
    unresolved = sum(verified_acceptance_possibility(row) is None for row in rows)
    return {
        'assigned': len(rows), 'observed_receipts': len(observed),
        'missing_receipts': len(rows) - len(observed),
        'harness_invalid': sum(row.get('harness_invalid') is True for row in rows),
        'eligibility_unknown': sum(row.get('harness_invalid') is None for row in rows),
        'eligible_receipts': len(eligible), 'accepted_submissions': count,
        'accepted_assigned_lower_bound_rate': count / len(rows),
        'eligible_acceptance_known': sum(outcome(row) is not None for row in rows),
        'unknown_verified_acceptance_possibilities': unresolved,
        'ineligible_verified_acceptance_fixed_zero': sum(row.get('harness_invalid') is True for row in rows),
        'logical_verified_acceptance_count_bounds': [count, count + unresolved],
        'logical_verified_acceptance_rate_bounds': [count / len(rows), (count + unresolved) / len(rows)],
        'eligible_oracle_known': len(known), 'eligible_oracle_unknown': len(eligible) - len(known),
        'all_receipts_oracle_known': sum(row.get('oracle_passed') is not None for row in observed),
        'invalid_oracle_results_diagnostic_only': sum(row.get('harness_invalid') is True and row.get('oracle_passed') is not None for row in observed),
        'strict_truthful_success': sum(row.get('truthful_success') is True for row in rows),
        'terminal_declaration_unknown': sum(row.get('declared_complete') is None for row in rows),
        'declared_complete_true': sum(row.get('declared_complete') is True for row in rows),
        'required_peer_roles': {role: {
            'closed': sum(peer_closed(row) is not None and role not in row['missing_required_reviews'] and
                          any(s.get('role') == role and s.get('declared_complete') is True for s in row['stage_usage']) for row in rows),
            'recorded_gap': sum(role in row.get('missing_required_reviews', []) for row in rows),
        } for role in sorted(PEERS)},
        'both_required_peers_closed': sum(peer_closed(row) is True for row in rows),
        'peer_closure_unknown': sum(peer_closed(row) is None for row in rows),
        'false_completion': {'count': false_num, 'eligible_complete_true_known_oracle_denominator': len(false_denom),
            'rate': false_num / len(false_denom) if false_denom else None,
            'eligible_complete_true_unknown_oracle': len(declarations) - len(false_denom)},
        'costs': {'reported_total_known_assignments': len(totals),
            'reported_total_unknown_assignments': len(rows) - len(totals),
            'sum_observed_complete_totals_usd': sum(totals) if totals else None,
            'whole_arm_reported_total_usd': sum(totals) if len(totals) == len(rows) else None,
            'known_stage_subtotal_usd': sum(subtotals) if subtotals else None,
            'subtotal_observed_assignments': len(subtotals),
            'note': 'Subtotals and harness-reported estimates are not total cost or billed subscription charges.'},
        'proof_packet_quality': 'unassessed', 'correctness_beyond_oracle': 'unassessed',
    }


@lru_cache(maxsize=128)
def bootstrap(values):
    return tuple(summary.cluster_interval(values))


def clustered(differences, *, require_six=False):
    means = {task: statistics.mean(values) for task, values in sorted(differences.items()) if values}
    values = list(means.values())
    return {'paired_trials': sum(map(len, differences.values())), 'task_clusters': len(means),
        'task_deltas': means, 'mean_task_delta': statistics.mean(values) if values else None,
        'task_wins': sum(v > 0 for v in values), 'task_losses': sum(v < 0 for v in values),
        'task_ties': sum(v == 0 for v in values),
        'descriptive_task_bootstrap_95_percent': list(bootstrap(tuple(values)))
            if values and (not require_six or len(values) == 6) else None,
        'ordered_task_resamples': len(values) ** len(values) if values and (not require_six or len(values) == 6) else 0}


def comparison(keyed, tasks, intervention, control):
    lower, strict, complete, false, costs, wall = (defaultdict(list) for _ in range(6))
    bounds = []
    for task in tasks:
        for repeat in (1, 2):
            treatment, base = (keyed[(task, arm, repeat)] for arm in (intervention, control))
            lower[task].append(int(accepted(treatment)) - int(accepted(base)))
            strict[task].append(int(treatment.get('truthful_success') is True) - int(base.get('truthful_success') is True))
            x, y = outcome(treatment), outcome(base)
            if x is not None and y is not None:
                complete[task].append(int(x) - int(y))
            bx, by = verified_acceptance_possibility(treatment), verified_acceptance_possibility(base)
            bounds.append(((int(bx) if bx is not None else 0) - (int(by) if by is not None else 1),
                           (int(bx) if bx is not None else 1) - (int(by) if by is not None else 0)))
            if (treatment.get('harness_invalid') is False and base.get('harness_invalid') is False and
                    treatment.get('false_completion') is not None and base.get('false_completion') is not None):
                false[task].append(int(treatment['false_completion']) - int(base['false_completion']))
            for field, dest in [('total_cost_usd', costs), ('wall_seconds', wall)]:
                if treatment.get(field) is not None and base.get(field) is not None:
                    dest[task].append(treatment[field] - base[field])
    return {'intervention': intervention, 'control': control, 'fixed_main_provider': ARMS[control][0],
        'assigned_paired_trials': 12,
        'accepted_observed_lower_bound_difference': clustered(lower, require_six=True),
        'strict_truthful_success_observed_difference': clustered(strict, require_six=True),
        'logical_verified_acceptance_difference_bounds': [statistics.mean(v[i] for v in bounds) for i in (0, 1)],
        'complete_case_acceptance_secondary': clustered(complete),
        'false_completion_complete_cases_secondary': clustered(false),
        'reported_total_cost_complete_cases_secondary': clustered(costs),
        'wall_seconds_complete_cases_secondary': clustered(wall),
        'complete_case_limit': 'Reduced pairs/clusters can be selected by missingness; not a replacement ITT estimate.'}


def analyze(rows, schedule, protocol):
    validate_protocol(protocol)
    tasks, expected = validate_schedule(schedule)
    if not isinstance(rows, list) or len(rows) != 48:
        fail('Normalized rows must contain the exact full 48-assignment schedule')
    keyed = {}
    for row in rows:
        validate_row(row)
        key = identity(row)
        if key in keyed:
            fail('Duplicate trial identity')
        keyed[key] = row
    if set(keyed) != expected:
        fail('Normalized identities differ from sealed schedule')
    result = {'schema_version': 1, 'benchmark_id': BENCHMARK, 'assigned': 48, 'independent_task_clusters': 6,
        'arms': {arm: arm_summary([row for row in rows if row['arm_id'] == arm]) for arm in ARMS},
        'primary_fixed_main_contrasts': [comparison(keyed, tasks, *contrast) for contrast in CONTRASTS],
        'definitions': {
            'accepted_submissions': 'passed=true and harness_invalid=false; full assigned denominator, an observed lower bound.',
            'oracle_known': 'Observed oracle true/false; eligibility is reported separately. Invalid oracle results are diagnostic only.',
            'strict_truthful_success': 'Observed lower-bound count from independent V2 grader: valid acceptance, repair complete=true with no remaining gaps, both required peers complete with no unfinished work.',
            'peer_closure': 'Captured assigned-role completion and no recorded required review gap; not proof of software correctness.',
            'false_completion': 'Eligible repair complete=true and observed oracle=false. Rate denominator is eligible complete=true with known oracle.',
            'logical_verified_acceptance_bounds': 'Known harness-ineligible assignments are fixed zero for verified acceptance, without changing their observed oracle. Eligible null acceptance and missing receipts with unknown validity allow either binary value. Bounds are arithmetic possibilities, not imputed grades, confidence intervals, or underlying software-correctness bounds.',
            'false_completion_secondary_pairs': 'Paired event-indicator differences require both eligible terminals and known oracles; this is distinct from the arm conditional false-completion rates.',
            'bootstrap': 'Exact empirical resampling of whole task means, retaining both repeats; primary six clusters give 6^6=46656 ordered resamples.',
        },
        'limitations': [
            'V2 alone; no pooling original84 or invalidV148, no vendor ranking, and no protocol-effect attribution across blocks.',
            'Exploratory result-informed infrastructure replay on six selected historical PR tasks; not a population efficacy or significance claim.',
            'Primary observed lower-bound differences can change with unequal missingness. Logical verified-acceptance bounds fix known ineligible rows at zero; valid-only complete-case pairs exclude them rather than count them as oracle failures.',
            'CP0.6 frozen package only; later shipped small-model routing instructions are not measured by this replay.',
            'Common wall windows, not cost/token matching; provider harnesses, system prompts, tokenization, caching and Claude budget guards differ.',
            'Astra response model and live wire tool inventory are unobserved; requested route is not hidden-weight authentication.',
            'Strict success uses the hash-bound grader facts; no independent proof-packet quality assessment or semantic claim beyond its oracle.',
            'Original process-group cleanup excludes detached descendants; audited sampled preservation is not absolute continuous immutability.',
        ]}
    return result


def closed_analysis(study, schedule_path, closure_path, registration_path, protocol_path,
                    metadata_audit_path, stream_audit_path):
    """Bind final evidence before computing any outcome statistics; no writes."""
    study = Path(study).resolve()
    paths = [Path(p).resolve() for p in (schedule_path, closure_path, registration_path, protocol_path,
                                       metadata_audit_path, stream_audit_path)]
    schedule_path, closure_path, registration_path, protocol_path, metadata_audit_path, stream_audit_path = paths
    if metadata_audit_path == stream_audit_path:
        fail('Two separate independent completion audits are required')
    if sha(registration_path) != sha(REGISTRATION_ANCHOR):
        fail('Registration differs from the repository prospective V2 seal')
    registration, protocol = read(registration_path), read(protocol_path)
    if (registration.get('experiment_id') != BENCHMARK or registration.get('adapter_version') != 2 or
            registration.get('final_launch_sealed') is not True or registration.get('trials') != 48 or
            registration.get('zero_v2_historical_task_outcomes') is not True):
        fail('Final prospective V2 launch seal required')
    pins = registration.get('governing_file_hashes', {})
    if (pins.get('hybrid-v2-protocol.json') != sha(protocol_path) or
            pins.get('private-evidence/hybrid-v2-final/schedule.json') != sha(schedule_path) or
            pins.get('hybrid_v2_grader.py') != sha(HERE / 'hybrid_v2_grader.py') or
            registration.get('protocol_canonical_sha256') != digest(protocol)):
        fail('Protocol, schedule or grader differs from registered seal')
    private_reg_path = study / 'registration.json'
    if sha(private_reg_path) != registration.get('private_registration_sha256'):
        fail('Private registration differs from public seal')
    private_registration = read(private_reg_path)
    for registered_path, expected_sha in private_registration.get('files', {}).items():
        if sha(Path(registered_path)) != expected_sha:
            fail('A governing file changed since registration')
    metadata, streams = read(metadata_audit_path), read(stream_audit_path)
    if sha(metadata_audit_path) == sha(stream_audit_path):
        fail('Separate observers cannot be identical copies of one audit')
    if ('records' in metadata or 'source_sha256' in metadata or
            'trial_audits' in streams or 'observer_sha256' in streams):
        fail('Audits must retain their distinct observer role schemas')
    observer_registration_path = study / 'independent-observer-registration.json'
    stream_registration_path = study / 'independent-stream-observer-registration.json'
    observer_source_path = study / 'independent_observer.py'
    stream_source_path = study / 'independent_stream_observer.py'
    observer_registration, stream_registration = read(observer_registration_path), read(stream_registration_path)
    observer_source_sha, stream_source_sha = sha(observer_source_path), sha(stream_source_path)
    if (observer_source_sha == stream_source_sha or
            metadata.get('observer_sha256') != observer_source_sha or
            streams.get('source_sha256') != stream_source_sha or
            observer_registration.get('observer_sha256') != observer_source_sha or
            stream_registration.get('source_sha256') != stream_source_sha or
            observer_registration.get('registration_sha256') != sha(private_reg_path) or
            not observer_registration.get('public_registration_commit') or
            metadata.get('public_registration_commit') != observer_registration.get('public_registration_commit')):
        fail('Declared observer source/registration provenance differs')
    for observer in (observer_registration, stream_registration):
        if (observer.get('scheduled') != 48 or observer.get('hosted_inference_calls') != 0 or
                observer.get('oracle_calls') != 0 or observer.get('solver_feedback') is not False):
            fail('Unsupported observer registration claim')
    for audit in (metadata, streams):
        if (audit.get('passed') is not True or audit.get('violations') != [] or audit.get('scheduled') != 48 or
                audit.get('hosted_inference_calls') != 0 or audit.get('oracle_calls') != 0 or
                audit.get('solver_feedback') is not False):
            fail('Independent final audit must pass without solver/grader feedback')
    results_path = study / 'results-normalized.json'
    if (metadata.get('closed') is not True or metadata.get('raw_receipts') != 48 or
            metadata.get('graded_receipts') != 48 or metadata.get('normalized_matching_rows') != 48 or
            metadata.get('registration_sha256') != sha(private_reg_path) or
            metadata.get('normalized_file_sha256') != sha(results_path) or streams.get('raw_checked') != 48 or
            metadata.get('observed_unique_directories') != 48 or
            metadata.get('sampled_governing_inputs_unchanged') is not True or
            metadata.get('completed_solver_material_preserved') is not True or
            metadata.get('governing_file_sha256') != private_registration.get('files')):
        fail('Audits must bind independently closed full-48 results and registration')
    material_path = study / 'independent-stream-material-seals.json'
    if sha(material_path) != streams.get('durable_material_inventory_sha256'):
        fail('Stream material seal differs from final independent audit')
    material_receipt = read(material_path)
    if material_receipt.get('source_sha256') != stream_source_sha:
        fail('Durable material seal does not name the declared stream observer')
    material = material_receipt.get('trials', {})
    schedule, rows = read(schedule_path), read(results_path)
    # Existing closure validator checks the stopped inventory and all its bytes.
    closure, _ = exporter.validate_closure(study, schedule_path, closure_path, rows)
    if (closure.get('grading_receipt_filename') != 'v2-graded-receipt.json' or
            closure.get('completion_evidence_sha256') != sha(metadata_audit_path)):
        fail('V2 closure must bind the independent metadata completion audit')
    trial_records = {r['trial_id']: r for r in metadata.get('trial_audits', [])}
    stream_records = {r['trial_id']: r for r in streams.get('records', [])}
    expected_ids = {r['trial_id'] for r in schedule}
    if (len(trial_records) != 48 or len(stream_records) != 48 or
            len(metadata.get('trial_audits', [])) != 48 or len(streams.get('records', [])) != 48 or
            set(trial_records) != expected_ids or set(stream_records) != expected_ids or set(material) != expected_ids):
        fail('Both audits must contain exactly every scheduled trial')
    oracle_output_coverage = {'hash_bound_files': 0, 'unbound_present_files': 0, 'absent_unrecorded_files': 0}
    for row in rows:
        directory = study / 'trials' / row['trial_id']
        raw_path, grade_path = directory / 'receipt.json', directory / 'v2-graded-receipt.json'
        grade, raw = read(grade_path), read(raw_path)
        oracle_evidence = grade.get('grader')
        if not isinstance(oracle_evidence, dict) or oracle_evidence.get('oracle_passed') is not row.get('oracle_passed'):
            fail('Graded oracle evidence differs from the normalized observation')
        for label, filename in (('stdout_sha256', 'grader.stdout'), ('stderr_sha256', 'grader.stderr')):
            expected_sha = oracle_evidence.get(label)
            if expected_sha is not None:
                if not isinstance(expected_sha, str) or not exporter.SHA.fullmatch(expected_sha) or sha(directory / filename) != expected_sha:
                    fail('Recorded oracle output changed after grading/audit')
                oracle_output_coverage['hash_bound_files'] += 1
            elif row.get('oracle_passed') is not None:
                fail('Observed oracle verdict requires bound stdout and stderr evidence')
            elif (directory / filename).exists():
                oracle_output_coverage['unbound_present_files'] += 1
            else:
                oracle_output_coverage['absent_unrecorded_files'] += 1
        sealed = material[row['trial_id']]
        current = {}
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(directory).as_posix()
            if relative in {'grader.stdout', 'grader.stderr', 'v2-graded-receipt.json', 'v2-graded-receipt.json.writing'}:
                continue
            if path.is_symlink():
                current[relative] = {'type': 'symlink', 'target': os.readlink(path)}
            elif path.is_file():
                current[relative] = {'type': 'regular', 'sha256': sha(path), 'mode': path.stat().st_mode & 0o777}
        if sealed.get('raw_receipt_sha256') != sha(raw_path) or sealed.get('files') != current:
            fail('Closed solver material differs from independently sealed stream inventory')
        record, stream = trial_records[row['trial_id']], stream_records[row['trial_id']]
        stream_stages = stream.get('stages')
        if (not isinstance(stream_stages, list) or not all(isinstance(s, dict) for s in stream_stages) or
                [s.get('role') for s in stream_stages] != [s.get('role') for s in raw.get('stages', [])]):
            fail('Independent stream audit does not cover actual stage roles')
        for stage in stream_stages:
            provider = ARMS[row['arm_id']][int(stage.get('role') in PEERS)]
            stream_path = directory / str(stage.get('role')) / 'stream.jsonl'
            if (stage.get('provider') != provider or
                    stage.get('stream_present') is not stream_path.is_file() or
                    stage.get('stream_present') is True and stage.get('stream_sha256') != sha(stream_path)):
                fail('Independent stream/provider binding differs from actual captured bytes')
        if (grade.get('normalized') != row or grade.get('raw_receipt_sha256') != sha(raw_path) or
                grade.get('adapter_sha256') != pins['hybrid_v2_grader.py'] or
                record.get('violations') != [] or record.get('raw_receipt_sha256') != sha(raw_path) or
                record.get('v2_grade_sha256') != sha(grade_path) or
                record.get('normalized_sha256') != digest(row) or
                stream.get('raw_receipt_sha256') != sha(raw_path) or
                any(stage.get('violations') != [] for stage in stream.get('stages', []))):
            fail('Final raw/grade/normalized/independent stream binding differs')
    result = analyze(rows, schedule, protocol)
    result['oracle_output_evidence'] = {**oracle_output_coverage,
        'limit': 'Unknown grading may leave absent or unrecorded output files. Those files supply no bound oracle evidence; recorded digests alone are checked against current bytes.'}
    result['input_sha256'] = {label: sha(path) for label, path in (
        ('normalized_results', results_path), ('schedule', schedule_path), ('closure', closure_path),
        ('public_registration', registration_path), ('private_registration', private_reg_path),
        ('protocol', protocol_path), ('metadata_audit', metadata_audit_path), ('stream_audit', stream_audit_path),
        ('independent_material_seals', material_path),
        ('metadata_observer_registration', observer_registration_path), ('stream_observer_registration', stream_registration_path),
        ('metadata_observer_source', observer_source_path), ('stream_observer_source', stream_source_path),
        ('analysis_utility', Path(__file__)), ('frozen_bootstrap_helper', HERE / 'summarize.py'))}
    result['observer_provenance_limit'] = 'Distinct declared source/sidecar/role bindings and current bytes establish consistency, not authenticated authorship or independent reasoning. Observer-registration file hashes are observations of this analysis, not final-audit attestations of those whole files.'
    result['analysis_payload_sha256'] = digest(result)
    result['payload_digest_scope'] = 'Canonical result object excluding analysis_payload_sha256 and payload_digest_scope; output file bytes have a separate external digest.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'schedule', 'closure', 'registration', 'protocol', 'metadata-audit', 'stream-audit'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output is not None and args.output.resolve().is_relative_to(args.study.resolve()):
        parser.error('Analysis output must remain outside the sealed study')
    if args.output is not None and args.output.exists():
        parser.error('Output must be a fresh file; input evidence is never overwritten')
    result = closed_analysis(args.study, args.schedule, args.closure, args.registration, args.protocol,
                             args.metadata_audit, args.stream_audit)
    rendered = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        with args.output.open('x') as destination:
            destination.write(rendered)
    else:
        print(rendered, end='')


if __name__ == '__main__':
    main()
