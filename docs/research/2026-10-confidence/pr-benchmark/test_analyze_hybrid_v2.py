"""Synthetic closed-analysis adversaries; no hosted calls or live outcomes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2_analysis_tests', HERE / 'analyze_hybrid_v2.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def fixtures():
    schedule, rows = [], []
    for task in range(6):
        for arm in a.ARMS:
            for repeat in (1, 2):
                identity = dict(task_id='synthetic-' + str(task), arm_id=arm, repeat=repeat,
                                trial_id='synthetic-' + str(task) + '--' + arm + '--r' + str(repeat))
                schedule.append(identity)
                rows.append({**identity, 'status': 'completed', 'passed': False, 'oracle_passed': False,
                    'harness_invalid': False, 'declared_complete': False, 'truthful_success': False,
                    'false_completion': False, 'missing_required_reviews': [],
                    'main_model': a.ARMS[arm][0], 'peer_model': a.ARMS[arm][1],
                    'total_cost_usd': None, 'known_cost_subtotal': 0, 'cost_known': False,
                    'wall_seconds': 10, 'human_interventions': 0,
                    'proof_packet_grade': None, 'semantic_correctness_beyond_oracle': None,
                    'stage_qualification': [{'role': role, 'passed': True, 'skipped': False} for role in a.ROLES],
                    'stage_usage': [dict(role=role, declared_complete=role in a.PEERS,
                        timed_out=False, process_exit=0, total_cost_usd=None, wall_seconds=1)
                        for role in a.ROLES]})
    protocol = json.loads((HERE / 'hybrid-v2-protocol.json').read_text())
    return schedule, rows, protocol


def declare(row, complete):
    row['declared_complete'] = complete
    row['stage_usage'][-1]['declared_complete'] = complete
    row['false_completion'] = (complete is True and row['oracle_passed'] is False
        if complete is not None and row['oracle_passed'] is not None else None)


def succeed(row):
    row['passed'] = row['oracle_passed'] = True
    declare(row, True)
    row['truthful_success'] = True


def missing(row):
    identity = {key: row[key] for key in ('trial_id', 'task_id', 'arm_id', 'repeat')}
    row.clear()
    row.update(identity, status='missing_receipt', passed=None, oracle_passed=None,
        declared_complete=None, total_cost_usd=None, known_cost_subtotal=None,
        wall_seconds=None, human_interventions=None, harness_invalid=None,
        proof_packet_grade=None, semantic_correctness_beyond_oracle=None)


class AnalysisControls(unittest.TestCase):
    def setUp(self):
        self.schedule, self.rows, self.protocol = fixtures()

    def analyze(self):
        return a.analyze(self.rows, self.schedule, self.protocol)

    def test_only_two_registered_fixed_main_contrasts(self):
        result = self.analyze()
        self.assertEqual([(x['intervention'], x['control']) for x in result['primary_fixed_main_contrasts']], a.CONTRASTS)
        self.assertEqual([x['assigned'] for x in result['arms'].values()], [12] * 4)
        self.assertNotIn('baseline', result)

    def test_repeated_trials_stay_in_six_clusters(self):
        for row in self.rows:
            if row['arm_id'] == 'astra_main_opus_peer' and row['task_id'] == 'synthetic-0':
                succeed(row)
        paired = self.analyze()['primary_fixed_main_contrasts'][0]['accepted_observed_lower_bound_difference']
        self.assertEqual(paired['paired_trials'], 12)
        self.assertEqual(paired['task_clusters'], 6)
        self.assertEqual(paired['ordered_task_resamples'], 46656)
        self.assertEqual(paired['task_deltas']['synthetic-0'], 1)
        self.assertAlmostEqual(paired['mean_task_delta'], 1 / 6)

    def test_mutated_previous_output_cannot_poison_later_bootstrap(self):
        first = self.analyze()
        interval = first['primary_fixed_main_contrasts'][0]['accepted_observed_lower_bound_difference']['descriptive_task_bootstrap_95_percent']
        interval[0] = 999
        second = self.analyze()
        self.assertEqual(second['primary_fixed_main_contrasts'][0]['accepted_observed_lower_bound_difference']['descriptive_task_bootstrap_95_percent'], [0, 0])

    def test_one_repeat_does_not_become_independent_task(self):
        row = next(r for r in self.rows if r['arm_id'] == 'astra_main_opus_peer')
        succeed(row)
        paired = self.analyze()['primary_fixed_main_contrasts'][0]['accepted_observed_lower_bound_difference']
        self.assertEqual(paired['task_deltas'][row['task_id']], .5)
        self.assertEqual(paired['task_clusters'], 6)
        self.assertAlmostEqual(paired['mean_task_delta'], 1 / 12)

    def test_missing_and_invalid_are_not_oracle_failures(self):
        candidates = [r for r in self.rows if r['arm_id'] == 'astra_main_opus_peer']
        missing(candidates[0])
        succeed(candidates[1])
        candidates[1].update(harness_invalid=True, truthful_success=False)
        result = self.analyze()
        arm = result['arms']['astra_main_opus_peer']
        self.assertEqual(arm['accepted_submissions'], 0)
        self.assertEqual(arm['logical_verified_acceptance_count_bounds'], [0, 1])
        self.assertEqual(arm['ineligible_verified_acceptance_fixed_zero'], 1)
        self.assertEqual(arm['unknown_verified_acceptance_possibilities'], 1)
        self.assertEqual(arm['eligible_oracle_known'], 10)
        self.assertEqual(arm['invalid_oracle_results_diagnostic_only'], 1)
        self.assertEqual(arm['harness_invalid'], 1)
        paired = result['primary_fixed_main_contrasts'][0]
        self.assertEqual(paired['complete_case_acceptance_secondary']['paired_trials'], 10)
        self.assertEqual(paired['logical_verified_acceptance_difference_bounds'], [0, 1 / 12])

    def test_known_invalid_passing_oracle_has_fixed_zero_verified_upper_bound(self):
        row = next(r for r in self.rows if r['arm_id'] == 'astra_main_opus_peer')
        succeed(row)
        row.update(harness_invalid=True, truthful_success=False)
        result = self.analyze()
        arm = result['arms'][row['arm_id']]
        self.assertTrue(row['passed'])  # original diagnostic fact is preserved
        self.assertTrue(row['oracle_passed'])
        self.assertEqual(arm['accepted_submissions'], 0)
        self.assertEqual(arm['logical_verified_acceptance_count_bounds'], [0, 0])
        self.assertEqual(arm['eligible_oracle_known'], 11)
        paired = result['primary_fixed_main_contrasts'][0]
        self.assertEqual(paired['logical_verified_acceptance_difference_bounds'], [0, 0])
        self.assertEqual(paired['complete_case_acceptance_secondary']['paired_trials'], 11)

    def test_invalid_unknown_oracle_is_still_fixed_zero_verified_acceptance(self):
        row = next(r for r in self.rows if r['arm_id'] == 'astra_main_opus_peer')
        row.update(harness_invalid=True, passed=None, oracle_passed=None, false_completion=None)
        arm = self.analyze()['arms'][row['arm_id']]
        self.assertEqual(arm['logical_verified_acceptance_count_bounds'], [0, 0])
        self.assertEqual(arm['unknown_verified_acceptance_possibilities'], 0)
        self.assertEqual(arm['ineligible_verified_acceptance_fixed_zero'], 1)
        self.assertIsNone(row['oracle_passed'])  # zero does not fabricate failure

    def test_eligible_unknown_and_missing_validity_allow_logical_upper_bound(self):
        rows = [r for r in self.rows if r['arm_id'] == 'astra_main_opus_peer']
        rows[0].update(passed=None, oracle_passed=None, false_completion=None)
        missing(rows[1])
        result = self.analyze()
        arm = result['arms']['astra_main_opus_peer']
        self.assertEqual(arm['accepted_submissions'], 0)
        self.assertEqual(arm['logical_verified_acceptance_count_bounds'], [0, 2])
        self.assertEqual(arm['unknown_verified_acceptance_possibilities'], 2)
        self.assertEqual(arm['eligible_oracle_unknown'], 1)
        self.assertEqual(arm['eligibility_unknown'], 1)
        paired = result['primary_fixed_main_contrasts'][0]
        self.assertEqual(paired['complete_case_acceptance_secondary']['paired_trials'], 10)
        self.assertEqual(paired['logical_verified_acceptance_difference_bounds'], [0, 1 / 6])

    def test_missing_control_cannot_be_an_observed_treatment_win(self):
        task = self.rows[0]['task_id']
        control = next(r for r in self.rows if r['task_id'] == task and r['arm_id'] == 'astra_main_astra_peer' and r['repeat'] == 1)
        treatment = next(r for r in self.rows if r['task_id'] == task and r['arm_id'] == 'astra_main_opus_peer' and r['repeat'] == 1)
        missing(control)
        succeed(treatment)
        paired = self.analyze()['primary_fixed_main_contrasts'][0]
        self.assertAlmostEqual(paired['accepted_observed_lower_bound_difference']['mean_task_delta'], 1 / 12)
        self.assertEqual(paired['logical_verified_acceptance_difference_bounds'], [0, 1 / 12])
        self.assertEqual(paired['complete_case_acceptance_secondary']['paired_trials'], 11)
        self.assertEqual(paired['complete_case_acceptance_secondary']['mean_task_delta'], 0)

    def test_unknown_cost_never_becomes_zero_total(self):
        arm = self.analyze()['arms']['astra_main_astra_peer']['costs']
        self.assertIsNone(arm['whole_arm_reported_total_usd'])
        self.assertIsNone(arm['sum_observed_complete_totals_usd'])
        self.assertEqual(arm['known_stage_subtotal_usd'], 0)
        self.assertEqual(arm['reported_total_unknown_assignments'], 12)

    def test_one_known_stage_is_not_known_trial_total(self):
        row = self.rows[0]
        row['stage_usage'][0]['total_cost_usd'] = .2
        row['known_cost_subtotal'] = .2
        costs = self.analyze()['arms'][row['arm_id']]['costs']
        self.assertEqual(costs['known_stage_subtotal_usd'], .2)
        self.assertIsNone(costs['whole_arm_reported_total_usd'])

    def test_all_stage_costs_known_produce_known_total(self):
        for row in self.rows:
            for stage in row['stage_usage']:
                stage['total_cost_usd'] = .1
            row.update(total_cost_usd=.4, known_cost_subtotal=.4, cost_known=True)
        costs = self.analyze()['arms']['opus_main_opus_peer']['costs']
        self.assertEqual(costs['reported_total_known_assignments'], 12)
        self.assertAlmostEqual(costs['whole_arm_reported_total_usd'], 4.8)

    def test_false_completion_rate_denominator_is_explicit(self):
        rows = [r for r in self.rows if r['arm_id'] == 'astra_main_astra_peer']
        declare(rows[0], True)  # known failure
        rows[1].update(passed=None, oracle_passed=None)
        declare(rows[1], True)  # unknown grading
        succeed(rows[2])       # known success
        declare(rows[3], None) # unknown terminal
        stats = self.analyze()['arms']['astra_main_astra_peer']
        self.assertEqual(stats['false_completion']['count'], 1)
        self.assertEqual(stats['false_completion']['eligible_complete_true_known_oracle_denominator'], 2)
        self.assertEqual(stats['false_completion']['eligible_complete_true_unknown_oracle'], 1)
        self.assertEqual(stats['false_completion']['rate'], .5)
        self.assertEqual(stats['terminal_declaration_unknown'], 1)

    def test_acceptance_and_strict_completion_are_separate(self):
        self.rows[0].update(passed=True, oracle_passed=True)
        stats = self.analyze()['arms'][self.rows[0]['arm_id']]
        self.assertEqual(stats['accepted_submissions'], 1)
        self.assertEqual(stats['strict_truthful_success'], 0)
        self.assertEqual(stats['both_required_peers_closed'], 12)

    def test_peer_complete_with_unfinished_work_is_not_closed(self):
        row = self.rows[0]
        row['missing_required_reviews'] = ['test_designer']
        stats = self.analyze()['arms'][row['arm_id']]
        self.assertEqual(stats['both_required_peers_closed'], 11)
        self.assertEqual(stats['required_peer_roles']['test_designer']['recorded_gap'], 1)
        self.assertEqual(stats['required_peer_roles']['test_designer']['closed'], 11)

    def test_reject_malformed_identities_and_pooled_rows(self):
        for mutate in (
            lambda rows: rows.pop(),
            lambda rows: rows.append(deepcopy(rows[0])),
            lambda rows: rows.__setitem__(1, deepcopy(rows[0])),
            lambda rows: rows[0].update(arm_id='original_cp_05'),
            lambda rows: rows[0].update(repeat=True),
            lambda rows: rows[0].update(trial_id='other'),
        ):
            with self.subTest(mutate=mutate):
                _, rows, _ = fixtures()
                mutate(rows)
                with self.assertRaises(ValueError):
                    a.analyze(rows, self.schedule, self.protocol)

    def test_reject_nonfinite_negative_and_boolean_costs(self):
        for value in (float('nan'), float('inf'), -.1, True):
            with self.subTest(value=value):
                self.rows[0]['known_cost_subtotal'] = value
                with self.assertRaises(ValueError):
                    self.analyze()

    def test_reject_integer_boolean_and_impossible_success(self):
        mutators = (
            lambda r: r.update(passed=1),
            lambda r: r.update(truthful_success=True),
            lambda r: r.update(passed=True, oracle_passed=False),
            lambda r: r.update(false_completion=True),
            lambda r: r.update(total_cost_usd=0, cost_known=True),
            lambda r: r.update(over_budget=True),
            lambda r: r.update(artifact_invalid=True, passed=True, oracle_passed=True),
        )
        for mutate in mutators:
            with self.subTest(mutate=mutate):
                _, rows, _ = fixtures()
                mutate(rows[0])
                with self.assertRaises(ValueError):
                    a.analyze(rows, self.schedule, self.protocol)

    def test_reject_strict_success_missing_review_or_qualification(self):
        for field, value in (('missing_required_reviews', ['test_designer']), ('harness_invalid', True),
                             ('stage_qualification', [{'passed': True}] * 3)):
            with self.subTest(field=field):
                _, rows, _ = fixtures()
                succeed(rows[0])
                rows[0][field] = value
                with self.assertRaises(ValueError):
                    a.analyze(rows, self.schedule, self.protocol)

    def test_unknown_qualification_cannot_be_an_eligible_receipt(self):
        self.rows[0]['stage_qualification'][0]['passed'] = None
        with self.assertRaises(ValueError):
            self.analyze()

    def test_reject_timeout_with_valid_declaration(self):
        self.rows[0]['stage_usage'][0]['timed_out'] = True
        with self.assertRaises(ValueError):
            self.analyze()

    def test_timeout_unknown_terminal_can_retain_known_oracle(self):
        stage = self.rows[0]['stage_usage'][-1]
        stage.update(timed_out=True, declared_complete=None)
        declare(self.rows[0], None)
        self.assertEqual(self.analyze()['arms'][self.rows[0]['arm_id']]['terminal_declaration_unknown'], 1)

    def test_reject_unknown_peer_without_recorded_gap(self):
        self.rows[0]['stage_usage'][0]['declared_complete'] = None
        with self.assertRaises(ValueError):
            self.analyze()

    def test_reject_invented_packet_quality(self):
        self.rows[0]['proof_packet_grade'] = True
        with self.assertRaises(ValueError):
            self.analyze()

    def test_reject_missing_assignment_with_observed_cost(self):
        missing(self.rows[0])
        self.rows[0]['total_cost_usd'] = 0
        with self.assertRaises(ValueError):
            self.analyze()

    def test_reject_protocol_vendor_ranking_or_v1_pooling(self):
        for mutate in (
            lambda p: p.update(adapter_version=1),
            lambda p: p['analysis']['primary_comparisons'].append({'intervention': 'opus_main_opus_peer', 'control': 'astra_main_astra_peer'}),
        ):
            with self.subTest(mutate=mutate):
                p = deepcopy(self.protocol)
                mutate(p)
                with self.assertRaises(ValueError):
                    a.analyze(self.rows, self.schedule, p)

    def test_json_duplicate_keys_and_nonfinite_literals_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'value.json'
            for text in ('{"passed":false,"passed":true}', '{"cost":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    a.read(path)


class ClosedCLIControls(unittest.TestCase):
    """Real temporary evidence files, seals and mutation controls, all synthetic."""
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.study = self.root / 'study'
        schedule, self.rows, protocol = fixtures()
        self.schedule = self.root / 'schedule.json'
        self.protocol = self.root / 'protocol.json'
        self.registration = self.root / 'public-registration.json'
        self.metadata_path = self.root / 'metadata-audit.json'
        self.stream_path = self.root / 'stream-audit.json'
        self.closure = self.root / 'closure.json'
        self.inventory = self.root / 'inventory.json'
        self.write(self.schedule, schedule)
        self.write(self.protocol, protocol)
        self.write(self.study / 'registration.json', {'files': {}})
        (self.study / 'independent_observer.py').write_text('# Synthetic metadata observer, not executed\n')
        (self.study / 'independent_stream_observer.py').write_text('# Synthetic stream observer, not executed\n')
        self.observer_source_sha = a.sha(self.study / 'independent_observer.py')
        self.stream_source_sha = a.sha(self.study / 'independent_stream_observer.py')
        common_sidecar = dict(scheduled=48, hosted_inference_calls=0, oracle_calls=0, solver_feedback=False)
        self.write(self.study / 'independent-observer-registration.json', {**common_sidecar,
            'observer_sha256': self.observer_source_sha, 'registration_sha256': a.sha(self.study / 'registration.json'),
            'public_registration_commit': 'b' * 40})
        self.write(self.study / 'independent-stream-observer-registration.json', {**common_sidecar,
            'source_sha256': self.stream_source_sha})
        self.write(self.study / 'results-normalized.json', self.rows)
        trial_audits, stream_records, material = [], [], {}
        for row in self.rows:
            directory = self.study / 'trials' / row['trial_id']
            raw_path, grade_path = directory / 'receipt.json', directory / 'v2-graded-receipt.json'
            self.write(raw_path, {'synthetic': True, 'trial_id': row['trial_id'], 'stages': row['stage_usage']})
            (directory / 'grader.stdout').write_text('{"passed":false,"exit_code":1}\n')
            (directory / 'grader.stderr').write_text('')
            self.write(grade_path, {'normalized': row, 'raw_receipt_sha256': a.sha(raw_path),
                'adapter_sha256': a.sha(HERE / 'hybrid_v2_grader.py'),
                'grader': {'oracle_passed': row['oracle_passed'],
                    'stdout_sha256': a.sha(directory / 'grader.stdout'),
                    'stderr_sha256': a.sha(directory / 'grader.stderr')}})
            trial_audits.append(dict(trial_id=row['trial_id'], raw_receipt_sha256=a.sha(raw_path),
                v2_grade_sha256=a.sha(grade_path), normalized_sha256=a.digest(row), violations=[]))
            stream_records.append(dict(trial_id=row['trial_id'], raw_receipt_sha256=a.sha(raw_path),
                stages=[dict(role=role, provider=a.ARMS[row['arm_id']][int(role in a.PEERS)],
                    stream_present=False, violations=[]) for role in a.ROLES]))
            material[row['trial_id']] = {'raw_receipt_sha256': a.sha(raw_path), 'files': {
                'receipt.json': {'type': 'regular', 'sha256': a.sha(raw_path), 'mode': raw_path.stat().st_mode & 0o777}}}
        self.write(self.study / 'independent-stream-material-seals.json', {'trials': material,
            'source_sha256': self.stream_source_sha})
        common = dict(passed=True, violations=[], scheduled=48, hosted_inference_calls=0,
                      oracle_calls=0, solver_feedback=False)
        self.metadata = {**common, 'closed': True, 'observer_sha256': self.observer_source_sha,
            'public_registration_commit': 'b' * 40, 'raw_receipts': 48, 'graded_receipts': 48,
            'normalized_matching_rows': 48, 'observed_unique_directories': 48,
            'sampled_governing_inputs_unchanged': True, 'completed_solver_material_preserved': True,
            'governing_file_sha256': {}, 'registration_sha256': a.sha(self.study / 'registration.json'),
            'normalized_file_sha256': a.sha(self.study / 'results-normalized.json'), 'trial_audits': trial_audits}
        self.stream = {**common, 'source_sha256': self.stream_source_sha, 'raw_checked': 48, 'records': stream_records,
            'durable_material_inventory_sha256': a.sha(self.study / 'independent-stream-material-seals.json')}
        self.write(self.metadata_path, self.metadata)
        self.write(self.stream_path, self.stream)
        self.public_registration = dict(experiment_id=a.BENCHMARK, adapter_version=2,
            final_launch_sealed=True, trials=48, zero_v2_historical_task_outcomes=True,
            private_registration_sha256=a.sha(self.study / 'registration.json'),
            protocol_canonical_sha256=a.digest(protocol), governing_file_hashes={
                'hybrid-v2-protocol.json': a.sha(self.protocol),
                'private-evidence/hybrid-v2-final/schedule.json': a.sha(self.schedule),
                'hybrid_v2_grader.py': a.sha(HERE / 'hybrid_v2_grader.py')})
        self.write(self.registration, self.public_registration)
        # Explicit synthetic repository anchor: real CLI uses the committed prospective seal.
        self.anchor_patch = patch.object(a, 'REGISTRATION_ANCHOR', self.registration)
        self.anchor_patch.start()
        a.exporter.seal(self.study, self.schedule, self.inventory, self.closure,
            'Synthetic completed control; not model observations', graded_filename='v2-graded-receipt.json',
            completion_evidence=self.metadata_path)

    def tearDown(self):
        self.anchor_patch.stop()
        self.temp.cleanup()

    def analyze(self):
        return a.closed_analysis(self.study, self.schedule, self.closure, self.registration,
                                 self.protocol, self.metadata_path, self.stream_path)

    def test_closed_synthetic_evidence_passes_and_binds_inputs_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.analyze()
        self.assertEqual(result['assigned'], 48)
        self.assertEqual(result['oracle_output_evidence']['hash_bound_files'], 96)
        self.assertEqual(result['oracle_output_evidence']['unbound_present_files'], 0)
        self.assertEqual(result['input_sha256']['normalized_results'], a.sha(self.study / 'results-normalized.json'))
        claimed = result.pop('analysis_payload_sha256')
        result.pop('payload_digest_scope')
        self.assertEqual(claimed, a.digest(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_or_progress_only_audit_rejected(self):
        self.metadata.update(closed=False, raw_receipts=47)
        self.write(self.metadata_path, self.metadata)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_failed_stream_audit_cannot_use_passing_metadata(self):
        self.stream['violations'] = ['material_changed']
        self.stream['passed'] = False
        self.write(self.stream_path, self.stream)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_same_audit_cannot_stand_in_for_two_independent_audits(self):
        with self.assertRaises(ValueError):
            a.closed_analysis(self.study, self.schedule, self.closure, self.registration,
                              self.protocol, self.metadata_path, self.metadata_path)

    def test_modified_aggregate_is_rejected_before_statistics(self):
        self.rows[0]['passed'] = True
        self.write(self.study / 'results-normalized.json', self.rows)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_modified_raw_or_closed_solver_material_rejected(self):
        path = self.study / 'trials' / self.rows[0]['trial_id'] / 'extra.txt'
        path.write_text('late writer')
        with self.assertRaises(ValueError):
            self.analyze()

    def test_unknown_invalid_grade_with_unbound_logs_cannot_supply_oracle_evidence(self):
        row = self.rows[0]
        row.update(harness_invalid=True, passed=None, oracle_passed=None, false_completion=None)
        self.write(self.study / 'results-normalized.json', self.rows)
        grade_path = self.study / 'trials' / row['trial_id'] / 'v2-graded-receipt.json'
        grade = a.read(grade_path)
        grade.update(normalized=row, grader={'oracle_passed': None})
        self.write(grade_path, grade)
        self.metadata['normalized_file_sha256'] = a.sha(self.study / 'results-normalized.json')
        self.metadata['trial_audits'][0].update(v2_grade_sha256=a.sha(grade_path), normalized_sha256=a.digest(row))
        self.write(self.metadata_path, self.metadata)
        self.inventory.unlink()
        self.closure.unlink()
        a.exporter.seal(self.study, self.schedule, self.inventory, self.closure,
            'Synthetic unknown grading with unbound diagnostic logs', graded_filename='v2-graded-receipt.json',
            completion_evidence=self.metadata_path)
        result = self.analyze()
        self.assertEqual(result['oracle_output_evidence']['hash_bound_files'], 94)
        self.assertEqual(result['oracle_output_evidence']['unbound_present_files'], 2)
        self.assertEqual(result['arms'][row['arm_id']]['logical_verified_acceptance_count_bounds'], [0, 0])

    def test_post_audit_oracle_stdout_and_stderr_changes_are_rejected(self):
        directory = self.study / 'trials' / self.rows[0]['trial_id']
        for filename in ('grader.stdout', 'grader.stderr'):
            with self.subTest(filename=filename):
                path = directory / filename
                before = path.read_bytes()
                path.write_bytes(before + b'post-audit alteration')
                with self.assertRaises(ValueError):
                    self.analyze()
                path.write_bytes(before)

    def test_bound_oracle_output_disappearance_is_rejected(self):
        path = self.study / 'trials' / self.rows[0]['trial_id'] / 'grader.stdout'
        path.unlink()
        with self.assertRaises(ValueError):
            self.analyze()

    def test_identical_merged_audit_copies_do_not_establish_two_observers(self):
        merged = {**self.metadata, **self.stream}
        self.write(self.metadata_path, merged)
        self.write(self.stream_path, merged)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_differently_formatted_merged_audits_still_do_not_qualify(self):
        merged = {**self.metadata, **self.stream}
        self.write(self.metadata_path, merged)
        self.stream_path.write_text(json.dumps(merged))
        self.assertNotEqual(a.sha(self.metadata_path), a.sha(self.stream_path))
        with self.assertRaises(ValueError):
            self.analyze()

    def test_missing_observer_provenance_is_blocking(self):
        self.stream.pop('source_sha256')
        self.write(self.stream_path, self.stream)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_observer_sidecar_cannot_claim_solver_feedback(self):
        path = self.study / 'independent-stream-observer-registration.json'
        receipt = a.read(path)
        receipt['solver_feedback'] = True
        self.write(path, receipt)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_changed_observer_source_or_sidecar_is_rejected(self):
        path = self.study / 'independent_observer.py'
        path.write_text('# Changed after registration\n')
        with self.assertRaises(ValueError):
            self.analyze()

    def test_modified_schedule_or_protocol_pin_rejected(self):
        schedule = a.read(self.schedule)
        schedule.reverse()
        self.write(self.schedule, schedule)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_unbound_closure_cannot_bypass_independent_completion_audit(self):
        closure = a.read(self.closure)
        closure.pop('completion_evidence_sha256')
        closure.pop('completion_evidence_path')
        self.write(self.closure, closure)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_duplicate_audit_trial_record_rejected(self):
        self.stream['records'][1] = self.stream['records'][0]
        self.write(self.stream_path, self.stream)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_output_cannot_overwrite_evidence_or_change_sealed_material(self):
        args = ['analyze_hybrid_v2.py', '--study', str(self.study), '--schedule', str(self.schedule),
            '--closure', str(self.closure), '--registration', str(self.registration),
            '--protocol', str(self.protocol), '--metadata-audit', str(self.metadata_path),
            '--stream-audit', str(self.stream_path)]
        before = self.protocol.read_bytes()
        for output in (self.protocol, self.study / 'trials' / self.rows[0]['trial_id'] / 'analysis.json'):
            with self.subTest(output=output), patch('sys.argv', args + ['--output', str(output)]):
                with self.assertRaises(SystemExit):
                    a.main()
        self.assertEqual(before, self.protocol.read_bytes())

    def test_stream_audit_with_missing_stage_is_rejected(self):
        self.stream['records'][0]['stages'].pop()
        self.write(self.stream_path, self.stream)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_unregistered_fabricated_launch_seal_is_rejected(self):
        with patch.object(a, 'REGISTRATION_ANCHOR', HERE / 'HYBRID-V2-REGISTRATION.json'):
            with self.assertRaises(ValueError):
                self.analyze()

    def test_stream_material_inventory_changed_rejected(self):
        self.write(self.study / 'independent-stream-material-seals.json', {'trials': {}})
        with self.assertRaises(ValueError):
            self.analyze()


if __name__ == '__main__':
    unittest.main()
