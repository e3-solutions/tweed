"""Synthetic closed-analysis controls. Never read actual running-study outcomes."""
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import tempfile
import time
from types import FunctionType, SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('analysis_test_target', HERE / 'analyze.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
r = a.r


class ClosedAnalysisControls(unittest.TestCase):
    def fixture(self, root, passed=True, cost=.2):
        study = root / 'study'; study.mkdir(); r.write(study / 'registration.json', {'synthetic': True})
        controls = study / 'oracle-controls'; controls.mkdir(); r.write(controls / 'results.json', {'synthetic': True})
        source = root / 'base'; source.mkdir(); (source / 'public.py').write_text('answer = 1\n')
        toolkit = root / 'toolkit'; toolkit.mkdir(); (toolkit / 'SKILL.md').write_text('shared core')
        policy = root / 'policy'; policy.mkdir(); (policy / 'SKILL.md').write_text('selected policy')
        arm = {'id': 'enhanced-opus', 'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium', 'policy_directory': str(policy)}
        task = {'base_snapshot': str(source), 'production_paths': ['public.py']}
        payload = {'config': {'toolkit_directory': str(toolkit), 'seconds': 240, 'claude_budget_usd': 2}}
        adapter = r.route(arm)
        request = {'trial_id': 'tweed-pr40--enhanced-opus--r1', 'task_id': 'tweed-pr40', 'arm_id': 'enhanced-opus', 'repeat': 1, 'prompt': 'synthetic public requirement'}
        directory = study / 'trials' / request['trial_id']; main = directory / 'main'; main.mkdir(parents=True)
        # Golden argv comes from the frozen actual adapter, intercepted before
        # launch. The new analyzer builder is not used to make its own fixture.
        class NoInference:
            returncode = 0
            def poll(self): return 0
        old = adapter.frozen.base.claude_call.__wrapped__
        captured = FunctionType(old.__code__, {**old.__globals__, 'subprocess': SimpleNamespace(Popen=lambda *_args, **_kwargs: NoInference())}, old.__name__, old.__defaults__, old.__closure__)
        captured.__kwdefaults__ = old.__kwdefaults__
        actor = root / 'actor'; actor.mkdir()
        captured(actor, main, request['prompt'], 2, 240, time.time() + 240)
        provider_request = r.read(main / 'request.json')
        init = {'model': arm['model'], 'tools': ['mcp__cp_trial__' + name for name in adapter.EXPECTED] + ['StructuredOutput'],
                'mcp_servers': [{'name': 'cp_trial', 'status': 'connected'}], 'mcp_server_errors': [], 'claude_code_version': 'synthetic', 'permissionMode': 'dontAsk'}
        terminal = {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': {'complete': True, 'summary': 'synthetic', 'remaining': []},
                    'usage': {'input_tokens': 10, 'output_tokens': 5}, 'total_cost_usd': cost, 'modelUsage': {}, 'costBasis': 'list' if cost is not None else 'unknown'}
        events = [dict(init, type='system', subtype='init'), {'type': 'assistant', 'message': {'model': arm['model']}}, terminal]
        (main / 'stream.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events)); (main / 'stderr.log').write_text('')
        local = {'passed': True, 'synthetic': True}; r.write(directory / 'qualification' / 'local-qualification.json', local)
        stage = {'backend': 'claude', 'terminal': terminal, 'usage': terminal['usage'], 'total_cost_usd': cost, 'modelUsage': {},
                 'process_cleanup_scope': 'original_process_group', 'detached_descendants_contained': False, 'stream_changed_during_cleanup': False,
                 'guarded_new_session_processes': 1, 'timed_out': False, 'process_exit': 0, 'observed_assistant_models': [arm['model']],
                 'harness_initialization': init, 'request_sha256': r.digest(provider_request), 'stream_sha256': r.sha(main / 'stream.jsonl'),
                 'invalid_stream_lines': 0, 'wall_seconds': 1.0}
        snapshot = directory / 'result_snapshot'; adapter.frozen.base.safe_copy(source, snapshot)
        r.mount(adapter.frozen.base, toolkit, policy, snapshot)
        (snapshot / 'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
        (snapshot / '.gitignore').write_text('\n.trial-tmp/\n.confidence/\n')
        (snapshot / 'public.py').write_text('answer = 2\n')
        a.rebuild_patch(adapter, source, snapshot, directory / 'submitted.patch', task['production_paths'])
        header = {'passed': passed, 'exit_code': 0 if passed else 1}
        (directory / 'grader.stdout').write_text(json.dumps(header) + '\n'); (directory / 'grader.stderr').write_text('')
        oracle = {'oracle_passed': passed, 'exit_code': header['exit_code'], 'timed_out': False, 'header': header,
                  'stdout_sha256': r.sha(directory / 'grader.stdout'), 'stderr_sha256': r.sha(directory / 'grader.stderr'), 'output_changed_during_cleanup': False}
        raw = {key: request[key] for key in a.IDS}
        raw.update(backend='claude', model_requested=arm['model'], request_sha256=r.digest(request), stage=stage,
                   qualification=r.qualification(stage, local, arm, adapter), terminal=r.terminal(stage), eligible=True, accepted=passed,
                   scope_violations=[], result_sha256=adapter.frozen.base.tree_digest(snapshot), source_sha256_after=adapter.frozen.base.tree_digest(snapshot),
                   source_sha256_at_launch=a.launch_digest(task, arm, payload['config'], adapter), patch_sha256=r.sha(directory / 'submitted.patch'),
                   registration_sha256=r.sha(study / 'registration.json'), controls_sha256=r.sha(controls / 'results.json'),
                   tool_events_sha256=None, oracle=oracle, status='completed')
        r.write(directory / 'receipt.json', raw)
        return directory, request, task, arm, payload, study, adapter, raw

    def evaluate(self, fixture): return a.row(*fixture[:7])

    def test_positive_uses_current_bound_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.evaluate(self.fixture(Path(name)))
            self.assertTrue(value['verified_success']); self.assertTrue(value['terminal_known'])
            self.assertTrue(value['patch_bound']); self.assertFalse(value['false_completion_event'])

    def test_wrong_identity_and_request_digest_fail_closed(self):
        for field, value in [('task_id', 'other'), ('request_sha256', '0' * 64)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name)); raw = fixture[-1]; raw[field] = value
                r.write(fixture[0] / 'receipt.json', raw)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_current_source_stream_patch_and_oracle_drift_are_rejected(self):
        for relative in ('result_snapshot/public.py', 'main/stream.jsonl', 'submitted.patch', 'grader.stdout', 'grader.stderr'):
            with self.subTest(artifact=relative), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name)); path = fixture[0] / relative
                path.write_bytes(path.read_bytes() + b'changed')
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_resealed_unrelated_patch_is_not_a_source_artifact(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name)); patch = fixture[0] / 'submitted.patch'
            patch.write_text('unrelated patch bytes\n'); fixture[-1]['patch_sha256'] = r.sha(patch)
            r.write(fixture[0] / 'receipt.json', fixture[-1])
            with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_same_size_preserved_timestamp_replacement_is_force_rehashed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); base = root / 'base'; candidate = root / 'candidate'; base.mkdir(); candidate.mkdir()
            (base / 'public.py').write_text('answer = 1\n'); (candidate / 'public.py').write_text('answer = 2\n')
            stamp = (base / 'public.py').stat(); os.utime(candidate / 'public.py', ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
            for n in range(6):
                patch, paths = a.rebuild_patch(adapter, base, candidate, root / ('patch' + str(n)), ['public.py'])
                self.assertIn(b'-answer = 1\n+answer = 2\n', patch); self.assertEqual(paths, ['public.py'])

    def test_resealed_actual_argv_cannot_enable_native_tools_or_change_effort(self):
        for token in ('effort', 'duplicate-model', 'native-tools'):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name)); file = fixture[0] / 'main/request.json'; provider = r.read(file)
                if token == 'effort': provider['argv'][provider['argv'].index('--effort') + 1] = 'high'
                elif token == 'duplicate-model': provider['argv'][-1:-1] = ['--model', 'claude-haiku-5-5']
                else: provider['argv'][1:1] = ['--tools', 'Bash']
                r.write(file, provider); fixture[-1]['stage']['request_sha256'] = r.digest(provider)
                r.write(fixture[0] / 'receipt.json', fixture[-1])
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_bound_actual_assistant_native_tool_call_cannot_be_laundered(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name)); file = fixture[0] / 'main/stream.jsonl'
            with file.open('a') as stream:
                stream.write(json.dumps({'type': 'assistant', 'message': {'model': 'claude-opus-5-5', 'content': [{'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'true'}}]}}) + '\n')
            fixture[-1]['stage']['stream_sha256'] = r.sha(file); r.write(fixture[0] / 'receipt.json', fixture[-1])
            with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_historical_grade_association_is_limited_and_fresh_source_check_is_separate(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); snapshot = fixture[0] / 'result_snapshot'
            (snapshot / 'public.py').write_text('answer = 3\n')
            adapter = fixture[6]; raw = fixture[-1]
            a.rebuild_patch(adapter, Path(fixture[2]['base_snapshot']), snapshot, fixture[0] / 'submitted.patch', fixture[2]['production_paths'])
            raw.update(result_sha256=adapter.frozen.base.tree_digest(snapshot), source_sha256_after=adapter.frozen.base.tree_digest(snapshot), patch_sha256=r.sha(fixture[0] / 'submitted.patch'))
            r.write(fixture[0] / 'receipt.json', raw); value = self.evaluate(fixture)
            self.assertTrue(value['oracle_passed']); self.assertFalse(value['historical_oracle_input_digest_recorded'])
            self.assertIsNone(value['current_source_acceptance'])
            oracle = root / 'toy-oracle'; oracle.mkdir(); script = oracle / 'evaluate.py'
            script.write_text("import argparse,json,pathlib\np=argparse.ArgumentParser();p.add_argument('--workspace');a=p.parse_args()\n"
                              "good=(pathlib.Path(a.workspace)/'public.py').read_text()=='answer = 2\\n'\n"
                              "code=0 if good else 1\nprint(json.dumps({'passed':good,'exit_code':code}));raise SystemExit(code)\n")
            task = dict(fixture[2], oracle_script=str(script))
            result = a.current_rechecks(fixture[5], root / 'fresh-rechecks', [value], {'tweed-pr40': task}, {'enhanced-opus': fixture[3]}, 'synthetic-registration')
            self.assertEqual(result['known_disagreements'], 1)
            self.assertFalse(value['current_source_acceptance']); self.assertTrue(value['oracle_passed'])
            self.assertEqual(raw, r.read(fixture[0] / 'receipt.json'))

    def test_cached_current_recheck_rejects_grader_baseline_dependency_drift(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); value = self.evaluate(fixture)
            base = Path(fixture[2]['base_snapshot']); sentinel = base / 'fixture-sentinel'; sentinel.write_text('valid fixture')
            oracle = root / 'toy-oracle'; oracle.mkdir(); script = oracle / 'evaluate.py'
            script.write_text("import argparse,json,pathlib\np=argparse.ArgumentParser();p.add_argument('--workspace');a=p.parse_args()\n"
                "source=(pathlib.Path(a.workspace)/'public.py').read_text()=='answer = 2\\n'\n"
                "fixture=(pathlib.Path(__file__).parent.parent/'base'/'fixture-sentinel').read_text()=='valid fixture'\n"
                "good=source and fixture;code=0 if good else 1\nprint(json.dumps({'passed':good,'exit_code':code}));raise SystemExit(code)\n")
            task = dict(fixture[2], oracle_script=str(script)); output = root / 'fresh-rechecks'
            a.current_rechecks(fixture[5], output, [value], {'tweed-pr40': task}, {'enhanced-opus': fixture[3]}, 'synthetic-registration')
            record = r.read(output / value['trial_id'] / 'receipt.json')
            self.assertEqual(record['grader_base_before'], record['grader_base_after'])
            self.assertEqual(record['oracle_tree_before'], record['oracle_tree_after'])
            sentinel.write_text('changed fixture after grade')
            with self.assertRaisesRegex(ValueError, 'input seal changed'):
                a.current_rechecks(fixture[5], output, [value], {'tweed-pr40': task}, {'enhanced-opus': fixture[3]}, 'synthetic-registration')

    def test_current_grader_fixture_must_match_registered_task_base(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); value = self.evaluate(fixture)
            oracle = root / 'different-fixture' / 'oracle'; oracle.mkdir(parents=True)
            (oracle.parent / 'base').mkdir(); (oracle.parent / 'base' / 'public.py').write_text('different baseline')
            script = oracle / 'evaluate.py'; script.write_text('cannot execute')
            task = dict(fixture[2], oracle_script=str(script))
            with self.assertRaisesRegex(ValueError, 'differs from registered'):
                a.current_rechecks(fixture[5], root / 'rechecks', [value], {'tweed-pr40': task}, {'enhanced-opus': fixture[3]}, 'synthetic-registration')
            self.assertFalse((root / 'rechecks').exists())

    def test_missing_assignment_stays_unknown_without_inventing_a_score(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); request = {'trial_id': 'tweed-pr40--enhanced-opus--r1', 'task_id': 'tweed-pr40', 'arm_id': 'enhanced-opus', 'repeat': 1, 'prompt': 'private context'}
            arm = {'backend': 'claude', 'model': 'claude-opus-5-5'}
            value = a.missing_row(request, arm, dict(request, status='never_started', accepted=None, eligible=False), root / 'absent')
            self.assertFalse(value['verified_success']); self.assertIsNone(value['oracle_passed']); self.assertTrue(value['semantic_unknown'])
            self.assertNotIn('prompt', value)
            with self.assertRaises(ValueError): a.missing_row(request, arm, dict(request, status='never_started', accepted=True, eligible=False), root / 'absent')

    def test_codex_controlled_envelope_is_reconstructed_from_frozen_command(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); main = root / 'main'; main.mkdir(); workspace = root / 'worker'; workspace.mkdir()
            arm = {'id': 'enhanced-codex', 'backend': 'codex', 'model': 'gpt-6-astra', 'effort': 'medium'}
            adapter = r.route(arm); backend = adapter.frozen.backend; catalog = root / 'catalog.json'; r.write(catalog, {'synthetic': True})
            mcp = backend.mcp_server(workspace, main, time.time() + 240, False)
            argv = backend.command(workspace, main, catalog, 'public task', mcp=mcp, readonly=False)
            payload = {'inventories': {'enhanced-codex': {'catalog': str(catalog)}}}
            a.request_envelope(main, {'argv': argv}, arm, {}, 'public task', adapter, payload)
            argv[-1:-1] = ['--model', 'gpt-6.1-sol']
            with self.assertRaises(ValueError): a.request_envelope(main, {'argv': argv}, arm, {}, 'public task', adapter, payload)

    def test_private_temporary_path_excludes_patch_without_dropping_assignment(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); patch = fixture[0] / 'submitted.patch'
            patch.write_text('diff contains /private/var/folders/synthetic-owner-context/check.py\n')
            value = {'trial_id': fixture[1]['trial_id'], 'patch_bound': True, 'artifact_bindings': {'patch_sha256': r.sha(patch)}}
            result = {'rows': [value], 'limitations': ['synthetic privacy control']}; inventory = a.export(fixture[5], root / 'public', result)
            self.assertEqual(inventory['copied_patches'], 0); self.assertIn(value['trial_id'], inventory['privacy_excluded_patches'])
            self.assertEqual(len(r.read(root / 'public/analysis.json')['rows']), 1)

    def test_metadata_cannot_launder_different_actual_provider_facts(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name)); raw = fixture[-1]
            raw['stage']['observed_assistant_models'] = ['claude-haiku-5-5']
            r.write(fixture[0] / 'receipt.json', raw)
            with self.assertRaisesRegex(ValueError, 'actual stream'): self.evaluate(fixture)

    def test_provider_prompt_cannot_change_with_digest_resealed(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name)); path = fixture[0] / 'main/request.json'
            provider = r.read(path); provider['argv'][-1] = 'different intervention'; r.write(path, provider)
            fixture[-1]['stage']['request_sha256'] = r.digest(provider); r.write(fixture[0] / 'receipt.json', fixture[-1])
            with self.assertRaisesRegex(ValueError, 'prompt differs'): self.evaluate(fixture)

    def test_raw_truth_fields_cannot_override_recomputed_facts(self):
        for field, value in [('eligible', False), ('accepted', False), ('terminal', None)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name)); fixture[-1][field] = value
                r.write(fixture[0] / 'receipt.json', fixture[-1])
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_false_completion_is_conditioned_on_known_oracle(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.evaluate(self.fixture(Path(name), passed=False))
            self.assertTrue(value['false_completion_event']); self.assertTrue(value['false_completion_conditioned_denominator'])
            self.assertFalse(value['verified_success'])
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name)); fixture[-1].pop('oracle'); fixture[-1]['accepted'] = None
            r.write(fixture[0] / 'receipt.json', fixture[-1]); value = self.evaluate(fixture)
            self.assertFalse(value['false_completion_event']); self.assertTrue(value['semantic_unknown'])
            self.assertFalse(value['false_completion_conditioned_denominator'])

    def test_cost_unknown_remains_null_not_free(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.evaluate(self.fixture(Path(name), cost=None))
            self.assertIsNone(value['cost_estimate_usd']); self.assertEqual(value['cost_basis'], 'unknown')
            self.assertIsNone(value['observed_billed_usd'])
        self.assertIsNone(a.number(True)); self.assertIsNone(a.number(float('nan')))

    def test_duplicate_or_wrong_roster_is_rejected(self):
        tasks = ['tweed-pr' + str(n) for n in (32, 31, 40, 34, 39, 35)]
        requests = [{'trial_id': task + '--' + arm + '--r' + str(repeat), 'task_id': task, 'arm_id': arm, 'repeat': repeat} for task in tasks for arm in a.ARMS for repeat in (1, 2)]
        a.validate_roster(requests, tasks, a.ARMS)
        for mutated in (requests[:-1] + [requests[0]], requests[:-1], [dict(requests[0], task_id='wrong')] + requests[1:]):
            with self.assertRaises(ValueError): a.validate_roster(mutated, tasks, a.ARMS)

    def test_exact_cluster_bootstrap_matches_independent_enumeration(self):
        units = [-2, -1, 0, 0, 1, 2]
        samples = sorted(sum(sample) / 12 * 100 for sample in itertools.product(units, repeat=6))
        result = a.exact_bootstrap(units)
        expected = [samples[math.ceil(len(samples) * p) - 1] for p in (.025, .975)]
        self.assertEqual(result['percentile_interval_95_percentage_points'], expected)
        self.assertEqual(result['resamples'], 46656); self.assertEqual(result['task_wins'], 2); self.assertEqual(result['task_losses'], 2)
        self.assertEqual(a.exact_bootstrap([0] * 6)['percentile_interval_95_percentage_points'], [0, 0])

    def test_assigned_verified_zero_is_separate_from_unknown_semantics(self):
        rows = []
        for task in range(6):
            for arm in a.ARMS:
                for repeat in (1, 2):
                    known = arm != 'enhanced-codex'
                    success = known and (repeat == 1 or arm == 'enhanced-opus' and task < 2)
                    row = {'task_id': 'task' + str(task), 'arm_id': arm, 'repeat': repeat, 'eligible': known,
                           'verified_success': success, 'oracle_passed': success if known else None, 'semantic_unknown': not known,
                           'worker_complete_true_empty_remaining': False, 'false_completion_event': False,
                           'false_completion_conditioned_denominator': False, 'missing_or_invalid_terminal': not known,
                           'timed_out': None, 'model_attribution': 'requested_only', 'actual_model': None,
                           'cost_estimate_usd': None, 'cost_basis': 'unknown', 'usage': {key: None for key in a.USAGE_KEYS}}
                    rows.append(row)
        result = a.summarize(rows); codex = result['arms']['enhanced-codex']
        self.assertEqual(codex['assigned'], 12); self.assertEqual(codex['semantic_unknown'], 12)
        self.assertEqual(codex['verified_success'], 0); self.assertIsNone(codex['cost_estimate_usd_total'])
        self.assertIsNone(codex['known_cost_estimate_subtotal']); self.assertIsNone(codex['token_usage']['input_tokens']['total'])
        self.assertAlmostEqual(result['contrasts'][0]['mean_difference_percentage_points'], 100 / 6)
        self.assertEqual(result['contrasts'][0]['task_wins'], 2)
        for actual, expected in zip(result['contrasts'][2]['logical_semantic_difference_bounds_percentage_points'], [-100 * 8 / 12, 100 * 4 / 12]):
            self.assertAlmostEqual(actual, expected)

    def test_export_whitelist_drops_unapproved_fields_and_rejects_extra_files(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); value = self.evaluate(fixture)
            value['raw_private_prompt'] = str(root)
            result = {'rows': [value], 'private_raw_stream': str(root), 'limitations': ['synthetic safe whitelist']}
            out = root / 'public'; a.export(fixture[5], out, result)
            self.assertNotIn('private_raw_stream', (out / 'analysis.json').read_text())
            self.assertNotIn('raw_private_prompt', (out / 'analysis.json').read_text())
            (out / 'private-stream.jsonl').write_text('must never be part of public export')
            with self.assertRaisesRegex(ValueError, 'unrelated/private'): a.export(fixture[5], out, result)

    def test_overwrite_refuses_nonmatching_and_export_copies_exact_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); value = self.evaluate(fixture)
            result = {'rows': [value], 'limitations': ['synthetic export control']}; out = root / 'public'
            inventory = a.export(fixture[5], out, result)
            self.assertEqual(inventory['copied_patches'], 1)
            self.assertEqual((out / ('patches/' + value['trial_id'] + '.patch')).read_bytes(), (fixture[0] / 'submitted.patch').read_bytes())
            public = (out / 'analysis.json').read_text()
            self.assertNotIn(str(root), public); self.assertNotIn('synthetic public requirement', public)
            a.export(fixture[5], out, result)
            (out / 'analysis.json').write_text('unrelated existing output')
            with self.assertRaisesRegex(ValueError, 'overwrite'): a.export(fixture[5], out, result)


if __name__ == '__main__': unittest.main()
