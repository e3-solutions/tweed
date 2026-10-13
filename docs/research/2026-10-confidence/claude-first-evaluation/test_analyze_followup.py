"""Synthetic qualification before follow-up inference; no real outcomes read."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analyze_followup as m
r = m.r


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def recorded_grade(directory, passed):
    directory.mkdir(parents=True, exist_ok=True)
    header = {'passed': passed, 'exit_code': 0 if passed else 1} if passed is not None else {'infrastructure_error': 'synthetic unknown'}
    (directory / 'grader.stdout').write_text(json.dumps(header) + '\nPRIVATE_NEVER_EXPORT /Users/private/log\n')
    (directory / 'grader.stderr').write_text('PRIVATE_NEVER_EXPORT /Users/private/stderr')
    return {'oracle_passed': passed, 'header': header, 'exit_code': header.get('exit_code', 1), 'timed_out': False,
            'output_changed_during_cleanup': False, 'stdout_sha256': r.sha(directory / 'grader.stdout'), 'stderr_sha256': r.sha(directory / 'grader.stderr')}


class FollowupClosureTests(unittest.TestCase):
    def fixture(self, root):
        root = root.resolve()
        study, initial = root / 'followup', root / 'initial'
        study.mkdir(); initial.mkdir()
        neutral_registration = {'synthetic_registration': True}
        write(initial / 'registration.json', neutral_registration)
        write(initial / 'results.json', {'synthetic_closed_initial': True})
        base = root / 'trusted/base'; base.mkdir(parents=True)
        (base / 'bonaparte').write_text('answer = 1\n')
        (base / 'bonaparte_checkpoint.py').write_text('saved = None\n')
        (base / 'tests').mkdir(); (base / 'tests/test_visible.py').write_text('visible = True\n')
        original = root / 'trusted/oracle'; (original / 'modules').mkdir(parents=True)
        evaluator = ('from pathlib import Path\nimport shutil\n'
            'def copy_candidate(base, candidate, destination, production_paths):\n'
            '    shutil.copytree(base, destination)\n'
            '    for name in production_paths:\n'
            '        if (candidate / name).is_file(): shutil.copyfile(candidate / name, destination / name)\n'
            '    return sorted(production_paths)\n')
        (original / 'evaluate.py').write_text(evaluator)
        (original / 'modules/test_budget_resume_audit.py').write_text('import unittest\nclass BudgetResumeAudit(unittest.TestCase):\n    def ' + m.f.METHOD + '(self):\n        token = "off"\n        self.assertTrue(token)\n')
        write(original / 'oracle.json', {'task_id': 'tweed-pr40', 'production_paths': ['bonaparte', 'bonaparte_checkpoint.py'], 'test_ids': ['synthetic.original']})
        novel = study / 'novel/oracle'; novel.parent.mkdir()
        derivation = m.f.build_oracle(original, novel)
        controls = study / 'controls'; controls.mkdir()
        observations = [dict(label=label, **recorded_grade(controls / label, passed)) for label, passed in [('head-novel', False), ('alternative-novel', True), ('alternative-original', True)]]
        shutil.copytree(base, controls / 'bounded-alternative')
        write(controls / 'results.json', {'passed': True, 'observations': observations, 'alternative_inventory_sha256': r.digest(r.inventory(controls / 'bounded-alternative'))})
        toolkit, policy = root / 'toolkit', root / 'policy'
        toolkit.mkdir(); policy.mkdir()
        (toolkit / 'SKILL.md').write_text('public shared core')
        (policy / 'SKILL.md').write_text('PRIVATE_NEVER_EXPORT selected policy')
        roster = [{'trial_id': 'tweed-pr40--' + arm + '--r' + str(repeat), 'task_id': 'tweed-pr40', 'arm_id': arm, 'repeat': repeat} for arm in m.ARMS for repeat in (1, 2)]
        arm = {'id': 'enhanced-opus', 'backend': 'claude', 'model': m.MODEL, 'effort': 'medium', 'policy_directory': str(policy)}
        declaration = {'initial_study': str(initial), 'initial_registration_sha256': r.sha(initial / 'registration.json'), 'initial_payload_sha256': r.digest(neutral_registration),
            'roster': roster, 'task': {'task_id': 'tweed-pr40', 'base_snapshot': str(base), 'oracle_script': str(original / 'evaluate.py'),
                'prompt': 'PRIVATE_NEVER_EXPORT original required behavior', 'production_paths': ['bonaparte', 'bonaparte_checkpoint.py'], 'test_commands': [['python3', '-B', '-m', 'unittest', 'tests.test_visible']]},
            'arm': arm, 'toolkit_directory': str(toolkit), 'requirements': m.f.REQUIREMENTS, 'model': m.MODEL, 'effort': 'medium',
            'seconds': 120, 'claude_budget_usd': 1, 'concurrency_ceiling': 2, 'oracle_script': str(novel / 'evaluate.py'), 'derivation': derivation,
            'prepared_at_unix': 0, 'files': {str(controls / 'results.json'): r.sha(controls / 'results.json')},
            'trees': {str(novel.parent): r.inventory(novel.parent), str(controls): r.inventory(controls)}}
        write(study / 'declaration.json', {'payload': declaration, 'payload_sha256': r.digest(declaration)})
        adapter = r.route(arm); base_helper = adapter.frozen.base
        inputs = []
        for index, assigned in enumerate(roster):
            source = initial / 'trials' / assigned['trial_id'] / 'result_snapshot'; source.mkdir(parents=True)
            accepted = True if index < 3 else False if index < 7 else None
            (source / 'bonaparte').write_text('answer = 1\n' if accepted is True else 'broken_initial = True\n')
            (source / 'bonaparte_checkpoint.py').write_text('saved = None\n')
            first_receipt = dict(assigned, eligible=accepted is not None, accepted=accepted, result_sha256=base_helper.tree_digest(source))
            write(source.parent / 'receipt.json', first_receipt)
            row = dict(assigned, source=str(source), available=True, initial_eligible=accepted is not None, initial_accepted=accepted,
                initial_receipt_sha256=r.sha(source.parent / 'receipt.json'), source_inventory=r.inventory(source), source_inventory_sha256=r.digest(r.inventory(source)),
                first_stage_artifact_inventory=r.inventory(source.parent), first_stage_artifact_inventory_sha256=r.digest(r.inventory(source.parent)))
            inputs.append(row)
        seal = {'declaration_sha256': r.sha(study / 'declaration.json'), 'initial_results_sha256': r.sha(initial / 'results.json'), 'inputs': inputs, 'sealed_at_unix': 1, 'planned': 8}
        write(study / 'input-seal.json', {'payload': seal, 'payload_sha256': r.digest(seal)})
        results = []
        for row in inputs:
            directory = study / 'trials' / row['trial_id']; directory.mkdir(parents=True)
            write(directory / 'started.json', {'input_seal_sha256': r.sha(study / 'input-seal.json'), 'started_at_unix': 2})
            clean = directory / 'clean_initial'
            _, projected = m.projected_initial(declaration, row, clean, adapter)
            snapshot = directory / 'result_snapshot'; base_helper.safe_copy(clean, snapshot)
            (snapshot / 'bonaparte').write_text('answer = 222\n')
            r.mount(base_helper, toolkit, policy, snapshot)
            (snapshot / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
            (snapshot / '.gitignore').write_text('\n.trial-tmp/\n.confidence/\n')
            (snapshot / 'tests/worker_test.py').write_text('PRIVATE_NEVER_EXPORT model-authored test\n')
            patch_bytes, submitted = m.a.rebuild_patch(adapter, clean, snapshot, directory / 'submitted.patch', declaration['task']['production_paths'])
            main = directory / 'main'; main.mkdir()
            workspace = root / 'transient' / row['trial_id'] / 'workspace'
            server = {'workspace': str(workspace), 'temporary': str(workspace / '.trial-tmp'), 'control': str(main), 'readonly': False, 'python_executable': sys.executable, 'deadline': 120}
            write(main / 'server-config.json', server)
            prompt = 'Read .protocol/SKILL.md and relevant references.\n' + declaration['requirements'] + '\nOriginal required behavior:\n' + declaration['task']['prompt'] + '\nVisible baseline commands:\n' + json.dumps(declaration['task']['test_commands'])
            request = {'argv': m.a.expected_claude_argv(main, server, arm, declaration, prompt, adapter), 'prompt': prompt, 'model_requested': m.MODEL, 'effort': 'medium', 'budget_usd': 1, 'timeout_seconds': 120, 'readonly': False}
            write(main / 'request.json', request)
            init = {'model': m.MODEL, 'tools': ['mcp__cp_trial__' + name for name in adapter.EXPECTED] + ['StructuredOutput'], 'mcp_servers': [{'name': 'cp_trial', 'status': 'connected'}], 'mcp_server_errors': [], 'claude_code_version': 'synthetic', 'permissionMode': 'dontAsk'}
            terminal = {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': {'complete': True, 'summary': 'PRIVATE_NEVER_EXPORT summary', 'remaining': []}, 'usage': {'input_tokens': 10, 'output_tokens': 5}, 'total_cost_usd': 0.1, 'modelUsage': {}, 'costBasis': 'list'}
            args = {'argv': ['python3', '-B', '-m', 'unittest', 'tests.test_visible']}
            stream = [dict(init, type='system', subtype='init'), {'type': 'assistant', 'message': {'model': m.MODEL, 'content': [{'type': 'tool_use', 'name': 'mcp__cp_trial__run_tests', 'input': args}]}}, terminal]
            (main / 'stream.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in stream))
            (main / 'stderr.log').write_text('PRIVATE_NEVER_EXPORT /Users/private/log')
            event = {'name': 'run_tests', 'arguments_sha256': r.digest(args), 'ok': True, 'command_exit_code': 0, 'command_timed_out': False}
            (main / 'tool-events.jsonl').write_text(json.dumps(event) + '\n')
            ident = '0' * 32
            write(main / (ident + '.command-request.json'), {'id': ident, 'argv': [sys.executable, '-B', '-m', 'unittest', 'tests.test_visible'], 'timeout': 90})
            (main / ('command-' + ident + '.stdout')).write_text('PRIVATE_NEVER_EXPORT stdout')
            (main / ('command-' + ident + '.stderr')).write_text('')
            write(main / (ident + '.command-response.json'), {'exit_code': 0, 'timed_out': False, 'stdout': str(main / ('command-' + ident + '.stdout')), 'stderr': str(main / ('command-' + ident + '.stderr'))})
            stage = {'backend': 'claude', 'terminal': terminal, 'usage': terminal['usage'], 'total_cost_usd': .1, 'modelUsage': {},
                'process_cleanup_scope': 'original_process_group', 'detached_descendants_contained': False, 'stream_changed_during_cleanup': False,
                'guarded_new_session_processes': 1, 'timed_out': False, 'process_exit': 0, 'observed_assistant_models': [m.MODEL], 'harness_initialization': init,
                'request_sha256': r.digest(request), 'stream_sha256': r.sha(main / 'stream.jsonl'), 'invalid_stream_lines': 0, 'wall_seconds': 1.0}
            local = {'passed': True, 'synthetic': True}; write(directory / 'qualification/local-qualification.json', local)
            raw = {k: row[k] for k in m.IDS + ('initial_eligible', 'initial_accepted')}
            raw.update(status='completed', eligible=True, stage=stage, qualification=r.qualification(stage, local, arm, adapter),
                initial_projected_sha256=base_helper.tree_digest(clean), result_sha256=base_helper.tree_digest(snapshot), projected_production_paths=projected, submitted_paths=submitted,
                scope_violations=[], patch_sha256=r.sha(directory / 'submitted.patch'), input_seal_sha256=r.sha(study / 'input-seal.json'),
                patch_stats={'bytes': len(patch_bytes), 'added_lines': sum(line.startswith(b'+') and not line.startswith(b'+++') for line in patch_bytes.splitlines()), 'removed_lines': sum(line.startswith(b'-') and not line.startswith(b'---') for line in patch_bytes.splitlines())},
                cost_estimate_usd=.1, cost_basis='list', observed_billed_usd=None, cpu_time_seconds=None,
                executed_check_counts={'requested': 1, 'exit_zero': 1, 'timed_out': 0, 'run_tests_commands': 1, 'confidence_commands': 0, 'basis': 'Actual confined command/tool events; command counts, not assertion/test counts'}, tool_events_sha256=r.sha(main / 'tool-events.jsonl'))
            for label, passed in [('initial-original', row['initial_accepted']), ('initial-novel', False), ('original', True), ('novel', True)]:
                raw[label + '_grade'] = recorded_grade(directory / label, passed)
                if label in ('original', 'novel'): raw[label + '_passed'] = passed
            write(directory / 'receipt.json', raw); results.append(raw)
        write(study / 'results.json', {'assigned': 8, 'results': results, 'originally_accepted_subset': [row['trial_id'] for row in inputs if row['initial_accepted'] is True]})
        return study, neutral_registration

    def evaluate(self, fixture, rechecks=None):
        with patch.object(r, 'verify', return_value=fixture[1]):
            return m.analyze(fixture[0], rechecks)

    def first(self, fixture):
        return fixture[0] / 'trials' / r.read(fixture[0] / 'input-seal.json')['payload']['inputs'][0]['trial_id']

    def raw_mutation(self, fixture, change):
        directory = self.first(fixture); raw = r.read(directory / 'receipt.json'); change(raw, directory); write(directory / 'receipt.json', raw)
        normalized = r.read(fixture[0] / 'results.json'); normalized['results'][0] = raw; write(fixture[0] / 'results.json', normalized)

    def test_positive_all_eight_sources_patches_grades_commands_and_strata_close(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            self.assertEqual(len(report['rows']), 8)
            self.assertEqual([report['strata'][s]['assigned'] for s in m.STRATA], [3, 4, 1])
            self.assertTrue(all(row['both_requirements_preserved'] for row in report['rows']))
            self.assertEqual(report['rows'][0]['command_evidence']['counts']['exit_zero'], 1)
            self.assertEqual(len(report['rows'][0]['changed_paths']), 1)
            self.assertEqual(report['rows'][0]['worker_test_files_changed'], 1)
            self.assertEqual(report['rows'][3]['probe_role'], 'extension_plus_repair')
            self.assertFalse(report['rows'][0]['historical_oracle_candidate_input_digest_recorded'])
            self.assertIsNone(report['winner'])

    def test_v2_custody_marker_and_exact_exclusion_preserve_measurement_guards(self):
        # Wrapper custody semantics have their own independent controller tests.
        # This synthetic compatibility check changes no source or outcome bytes.
        for exclusion in ('main/execution-scratch', 'main'):
            with self.subTest(exclusion=exclusion), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); study = fixture[0]
                declaration = r.read(study / 'declaration.json'); declaration['payload']['custody_schema'] = 'followup-input-custody-v2'
                declaration['payload']['custody_exclusion'] = {'path': exclusion, 'reason': 'Synthetic unused-fixture witness'}
                declaration['payload_sha256'] = r.digest(declaration['payload']); write(study / 'declaration.json', declaration)
                seal = r.read(study / 'input-seal.json'); seal['payload']['declaration_sha256'] = r.sha(study / 'declaration.json')
                seal['payload']['custody_schema'] = 'followup-input-custody-v2'
                seal['payload']['custody_exclusion'] = {'path': exclusion, 'reason': 'Synthetic unused-fixture witness'}
                seal['payload_sha256'] = r.digest(seal['payload']); write(study / 'input-seal.json', seal)
                normalized = r.read(study / 'results.json')
                for raw in normalized['results']:
                    directory = study / 'trials' / raw['trial_id']; raw['input_seal_sha256'] = r.sha(study / 'input-seal.json')
                    write(directory / 'receipt.json', raw)
                    write(directory / 'started.json', {'input_seal_sha256': r.sha(study / 'input-seal.json'), 'started_at_unix': 2})
                write(study / 'results.json', normalized)
                wrapper = SimpleNamespace(r=r, __file__=m.f.__file__, verify_declaration=m.f.verify_declaration, verify=m.f.verify)
                with patch.object(m, 'controller', return_value=wrapper):
                    if exclusion == 'main':
                        with self.assertRaisesRegex(ValueError, 'exact unused subtree'): self.evaluate(fixture)
                    else:
                        report = self.evaluate(fixture)
                        public = m.public_projection(report)
                        self.assertEqual(public['controller_schema'], 'followup-input-custody-v2')
                        self.assertEqual(public['input_custody_exclusion'], 'main/execution-scratch')
                        self.assertTrue(all(row['both_requirements_preserved'] for row in public['rows']))

    def test_real_v2_wrapper_api_closes_synthetic_artifacts_with_unused_scratch_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); study = fixture[0]
            wrapper = m.module('synthetic_followup_v2_compatibility', m.HERE / 'followup_v2.py')
            declaration = r.read(study / 'declaration.json')
            payload = declaration['payload']; payload.update(custody_schema=wrapper.SCHEMA, custody_exclusion=wrapper.EXCLUSION)
            initial = Path(payload['initial_study'])
            requests = [{'trial_id': task + '--' + arm + '--r' + str(repeat), 'task_id': task, 'arm_id': arm, 'repeat': repeat}
                for task in ('tweed-pr32', 'tweed-pr31', 'tweed-pr34', 'tweed-pr35', 'tweed-pr39', 'tweed-pr40') for arm in m.ARMS for repeat in (1, 2)]
            closure = []
            for request in requests:
                path = initial / 'trials' / request['trial_id'] / 'receipt.json'
                if path.exists():
                    raw = r.read(path); patchfile = path.parent / 'submitted.patch'; patchfile.write_text('Synthetic first-stage patch artifact')
                    raw['patch_sha256'] = r.sha(patchfile)
                else: raw = dict(request, eligible=False, accepted=None)
                write(path, raw); closure.append(raw)
            write(initial / 'requests.json', requests); write(initial / 'results.json', closure)
            seal = r.read(study / 'input-seal.json')
            scratch = initial / 'trials' / seal['payload']['inputs'][0]['trial_id'] / 'main/execution-scratch'; scratch.mkdir(parents=True)
            (scratch / 'unused-test-fixture-link').symlink_to('/bin/sh')
            for row in seal['payload']['inputs']:
                parent = Path(row['source']).parent
                row.update(initial_receipt_sha256=r.sha(parent / 'receipt.json'), initial_patch_sha256=r.sha(parent / 'submitted.patch'),
                    first_stage_artifact_inventory=wrapper.trial_inventory(parent))
                row['first_stage_artifact_inventory_sha256'] = r.digest(row['first_stage_artifact_inventory'])
            declaration['payload_sha256'] = r.digest(payload); write(study / 'declaration.json', declaration)
            seal['payload'].update(custody_schema=wrapper.SCHEMA, custody_exclusion=wrapper.EXCLUSION,
                declaration_sha256=r.sha(study / 'declaration.json'), initial_results_sha256=r.sha(initial / 'results.json'))
            seal['payload_sha256'] = r.digest(seal['payload']); write(study / 'input-seal.json', seal)
            normalized = r.read(study / 'results.json')
            for raw in normalized['results']:
                directory = study / 'trials' / raw['trial_id']; raw['input_seal_sha256'] = r.sha(study / 'input-seal.json'); write(directory / 'receipt.json', raw)
                write(directory / 'started.json', {'input_seal_sha256': r.sha(study / 'input-seal.json'), 'started_at_unix': 2})
            write(study / 'results.json', normalized)
            with patch.object(wrapper.r, 'verify', return_value=fixture[1]), patch.object(m, 'controller', return_value=wrapper):
                report = m.analyze(study)
            self.assertEqual(len(report['rows']), 8)
            self.assertEqual(report['controller_sha256'], r.sha(m.HERE / 'followup_v2.py'))
            self.assertEqual(m.public_projection(report)['input_custody_exclusion'], 'main/execution-scratch')

    def test_assigned_normalized_missing_duplicate_and_raw_identity_fail_closed(self):
        for kind in ('missing', 'duplicate', 'raw'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                if kind == 'raw': self.raw_mutation(fixture, lambda raw, _: raw.__setitem__('repeat', 2))
                else:
                    path = fixture[0] / 'results.json'; normalized = r.read(path)
                    if kind == 'missing': normalized['results'].pop()
                    else: normalized['results'][-1] = normalized['results'][0]
                    write(path, normalized)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_initial_artifact_log_source_and_declaration_drift_fail_closed(self):
        for kind in ('initial', 'clean', 'declaration', 'fixture'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); directory = self.first(fixture)
                if kind == 'initial': path = Path(r.read(fixture[0] / 'input-seal.json')['payload']['inputs'][0]['source']) / 'bonaparte'
                elif kind == 'clean': path = directory / 'clean_initial/bonaparte'
                elif kind == 'declaration': path = fixture[0] / 'declaration.json'
                else: path = fixture[0] / 'novel/oracle/modules/test_budget_unbounded_probe.py'
                path.write_bytes(path.read_bytes() + b'drift')
                with self.assertRaises((ValueError, SyntaxError)): self.evaluate(fixture)

    def test_request_budget_effort_scope_prompt_and_full_mcp_envelope_rejected(self):
        for field, value in [('budget_usd', 2), ('timeout_seconds', 240), ('effort', 'high'), ('readonly', True), ('prompt', 'changed intervention')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                def change(raw, directory):
                    request = r.read(directory / 'main/request.json'); request[field] = value; write(directory / 'main/request.json', request); raw['stage']['request_sha256'] = r.digest(request)
                self.raw_mutation(fixture, change)
                with self.assertRaises(ValueError): self.evaluate(fixture)
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            def change(raw, directory):
                request = r.read(directory / 'main/request.json'); request['argv'][request['argv'].index('--tools') + 1] = 'Read'; write(directory / 'main/request.json', request); raw['stage']['request_sha256'] = r.digest(request)
            self.raw_mutation(fixture, change)
            with self.assertRaisesRegex(ValueError, 'envelope'): self.evaluate(fixture)

    def test_terminal_error_cannot_preserve_positive_qualification(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            def change(raw, directory):
                path = directory / 'main/stream.jsonl'; stream = [json.loads(line) for line in path.read_text().splitlines()]
                stream[-1]['is_error'] = True
                path.write_text(''.join(json.dumps(event) + '\n' for event in stream))
                raw['stage']['terminal'] = stream[-1]; raw['stage']['stream_sha256'] = r.sha(path)
            self.raw_mutation(fixture, change)
            with self.assertRaisesRegex(ValueError, 'qualification'): self.evaluate(fixture)

    def denied_proposal(self, fixture):
        """Actual frozen server guard, without a callback/child or model call."""
        directory = self.first(fixture); main = directory / 'main'
        raw = r.read(directory / 'receipt.json')
        adapter = r.route(r.read(fixture[0] / 'declaration.json')['payload']['arm'])
        arguments = {'argv': ['grep', 'needle', 'bonaparte']}
        worker = adapter.frozen.base.WorkspaceTools({'workspace': str(directory / 'result_snapshot'), 'control': str(main / 'synthetic-denial-control'),
            'temporary': str(directory / 'result_snapshot/.trial-tmp'), 'readonly': False, 'deadline': 0, 'python_executable': sys.executable})
        response, denial = worker.call('run_tests', arguments)
        self.assertFalse(denial['ok'])
        self.assertFalse(list(worker.control.glob('*.command-request.json')))
        proposal = {'type': 'tool_use', 'id': 'synthetic-denied-1', 'name': 'mcp__cp_trial__run_tests', 'input': arguments}
        result = {'type': 'tool_result', 'tool_use_id': proposal['id'], 'is_error': True, 'content': json.dumps(response)}
        stream = [json.loads(line) for line in (main / 'stream.jsonl').read_text().splitlines()]
        stream.insert(2, {'type': 'assistant', 'message': {'model': m.MODEL, 'content': [proposal]}})
        stream.insert(3, {'type': 'user', 'message': {'content': [result]}})
        events = [json.loads(line) for line in (main / 'tool-events.jsonl').read_text().splitlines()] + [denial]
        self.reseal_proposal(fixture, raw, stream, events)
        return raw, stream, events, proposal, result

    def reseal_proposal(self, fixture, raw, stream, events):
        directory = self.first(fixture); main = directory / 'main'
        (main / 'stream.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in stream))
        (main / 'tool-events.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in events))
        raw['stage']['stream_sha256'] = r.sha(main / 'stream.jsonl')
        raw['tool_events_sha256'] = r.sha(main / 'tool-events.jsonl')
        raw['executed_check_counts']['requested'] = len(events)
        raw['executed_check_counts']['run_tests_commands'] = len(events)
        write(directory / 'receipt.json', raw)
        normalized = r.read(fixture[0] / 'results.json'); normalized['results'][0] = raw; write(fixture[0] / 'results.json', normalized)

    def test_exact_bound_preexecution_denial_allows_recovered_followup(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); self.denied_proposal(fixture)
            report = self.evaluate(fixture)
            self.assertTrue(report['rows'][0]['eligible'])
            self.assertTrue(report['rows'][0]['both_requirements_preserved'])
            self.assertEqual(report['rows'][0]['command_evidence']['server_rejected_checks'], 1)
            self.assertEqual(len(report['rows'][0]['command_evidence']['callbacks']), 1)

    def test_unsupported_proposal_needs_exact_hash_bound_rejection_not_success(self):
        for fault in ('unbound', 'digest', 'error', 'kind', 'ok-true', 'ok-true-and-denial', 'provider-result', 'missing-server'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); raw, stream, events, proposal, result = self.denied_proposal(fixture)
                if fault == 'digest': events[-1]['arguments_sha256'] = '0' * 64
                elif fault == 'error': events[-1]['error'] = 'ValueError: unrelated denial'
                elif fault == 'kind': events[-1]['error_kind'] = 'policy'
                elif fault == 'ok-true': events[-1]['ok'] = True
                elif fault == 'ok-true-and-denial': events.append(dict(events[-1], ok=True))
                elif fault == 'provider-result': result['is_error'] = False
                elif fault == 'missing-server': events.pop()
                self.reseal_proposal(fixture, raw, stream, events)
                if fault == 'unbound':
                    raw['tool_events_sha256'] = None
                    write(self.first(fixture) / 'receipt.json', raw)
                    normalized = r.read(fixture[0] / 'results.json'); normalized['results'][0] = raw; write(fixture[0] / 'results.json', normalized)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_command_callback_arguments_exit_and_paths_rebind_actual_tool_events(self):
        for kind in ('argv', 'exit', 'path'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); directory = self.first(fixture) / 'main'; ident = '0' * 32
                if kind == 'argv':
                    path = directory / (ident + '.command-request.json'); value = r.read(path); value['argv'][-1] = 'unrequested.check'; write(path, value)
                else:
                    path = directory / (ident + '.command-response.json'); value = r.read(path)
                    if kind == 'exit': value['exit_code'] = 1
                    else: value['stdout'] = '/Users/private/not-owned'
                    write(path, value)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_bound_patch_must_describe_source_even_if_digest_and_stats_resealed(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            def change(raw, directory):
                (directory / 'submitted.patch').write_text('unrelated private patch')
                raw['patch_sha256'] = r.sha(directory / 'submitted.patch')
            self.raw_mutation(fixture, change)
            with self.assertRaisesRegex(ValueError, 'describe actual'): self.evaluate(fixture)

    def test_final_source_stream_oracle_log_and_tool_event_drift_are_rejected(self):
        for relative in ('result_snapshot/bonaparte', 'main/stream.jsonl', 'original/grader.stdout', 'novel/grader.stderr', 'main/tool-events.jsonl'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); path = self.first(fixture) / relative; path.write_bytes(path.read_bytes() + b'drift')
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_false_completion_is_separate_from_unknown_grades(self):
        for passed in (False, None):
            with self.subTest(passed=passed), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                def change(raw, directory): raw.update(novel_grade=recorded_grade(directory / 'novel', passed), novel_passed=passed)
                self.raw_mutation(fixture, change); row = self.evaluate(fixture)['rows'][0]
                self.assertFalse(row['both_requirements_preserved'])
                self.assertTrue(row['completion_not_fully_verified'])
                self.assertEqual(row['false_completion_known'], passed is False)
                self.assertEqual(row['primary_final_unknown'], passed is None)

    def test_separate_rechecks_bind_sources_and_do_not_replace_primary(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); output = Path(td) / 'new-rechecks'
            def checked(adapter, script, candidate, directory): return recorded_grade(directory, True)
            with patch.object(r, 'invoke_oracle', side_effect=checked) as cpu:
                report = self.evaluate(fixture, output)
                self.assertEqual(cpu.call_count, 32)
                again = self.evaluate(fixture, output)
                self.assertEqual(cpu.call_count, 32)
            self.assertEqual(report['rows'][0]['primary_grades']['initial-novel'], False)
            self.assertEqual(report['rows'][0]['current_rechecks']['initial-novel']['passed'], True)
            self.assertFalse(report['rows'][0]['current_rechecks']['initial-novel']['agrees_with_primary'])
            self.assertFalse(again['current_recheck_summary']['primary_grades_replaced'])

    def test_started_recheck_is_not_retried_and_dependency_drift_is_rejected(self):
        for kind in ('started', 'source', 'dependency'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); output = Path(td) / 'new-rechecks'
                if kind == 'started':
                    report = self.evaluate(fixture)
                    declaration = r.read(fixture[0] / 'declaration.json')['payload']
                    seal = {'declaration_sha256': r.sha(fixture[0] / 'declaration.json'), 'input_seal_sha256': r.sha(fixture[0] / 'input-seal.json'),
                        'sources': {row['trial_id'] + '/' + side: row['artifact_bindings'][field] for row in report['rows'] for side, field in [('initial', 'initial_projected_sha256'), ('final', 'result_sha256')]}, 'dependencies': m.dependencies(declaration)}
                    write(output / 'input-seal.json', seal)
                    (output / report['rows'][0]['trial_id'] / 'initial-original').mkdir(parents=True)
                def checked(adapter, script, candidate, directory):
                    value = recorded_grade(directory, True)
                    if kind == 'source': (candidate / 'bonaparte').write_text('candidate changed')
                    if kind == 'dependency': (script.parent / 'oracle.json').write_text('fixture changed')
                    return value
                with patch.object(r, 'invoke_oracle', side_effect=checked) as cpu:
                    with self.assertRaises(ValueError): self.evaluate(fixture, output)
                    if kind == 'started': self.assertEqual(cpu.call_count, 0)

    def test_public_projection_excludes_raw_paths_prose_commands_and_patch_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            report['qualified_helpers']['private_path'] = '/Users/PRIVATE_NEVER_EXPORT'
            report['grader_dependencies']['original']['private_note'] = 'PRIVATE_NEVER_EXPORT'
            report['rows'][0]['artifact_bindings']['/Users/private/unapproved-name'] = '0' * 64
            report['rows'][0]['command_evidence']['callbacks'][0]['bindings']['private_prose'] = 'PRIVATE_NEVER_EXPORT'
            public = m.public_projection(report); text = json.dumps(public)
            for secret in ('PRIVATE_NEVER_EXPORT', '/Users/', td, '"arguments"', '"summary"', 'answer = 222', 'tests.test_visible'):
                self.assertNotIn(secret, text)
            self.assertEqual(len(public['rows']), 8)
            self.assertEqual(public['rows'][0]['changed_files'], 1)
            self.assertFalse(public['rows'][0]['patch_publication']['published'])

    def test_public_defined_fields_cannot_smuggle_raw_private_prose(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            report['rows'][0]['patch_stats']['bytes'] = 'PRIVATE_NEVER_EXPORT'
            with self.assertRaisesRegex(ValueError, 'public patch'): m.public_projection(report)

    def test_output_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'new.json'
            m.save_matching(path, {'same': True}); m.save_matching(path, {'same': True})
            with self.assertRaisesRegex(ValueError, 'overwrite'): m.save_matching(path, {'same': False})
            self.assertEqual(r.read(path), {'same': True})


if __name__ == '__main__': unittest.main()
