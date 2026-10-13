"""No hosted calls: qualify isolation, frozen inputs, no retry and terminal truth."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('comparison_test_target', HERE / 'runner.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class ComparisonControls(unittest.TestCase):
    def test_private_route_models_do_not_cross_contaminate(self):
        opus = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
        haiku = r.route({'backend': 'claude', 'model': 'claude-haiku-5-5', 'effort': 'low'})
        self.assertIsNot(opus.frozen.base, haiku.frozen.base)
        self.assertEqual(opus.frozen.base.MODEL, 'claude-opus-5-5')
        self.assertEqual(haiku.frozen.base.MODEL, 'claude-haiku-5-5')
        self.assertEqual(opus.frozen.base.EFFORT, 'medium')
        self.assertEqual(haiku.frozen.base.EFFORT, 'low')

    def test_mount_has_one_selected_policy_and_shared_runtime(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); toolkit = root / 'runtime'; policy = root / 'policy'; workspace = root / 'worker'
            toolkit.mkdir(); policy.mkdir(); workspace.mkdir()
            (toolkit / 'scripts').mkdir(); (toolkit / 'scripts' / 'confidence.py').write_text('runtime bytes')
            (toolkit / 'SKILL.md').write_text('baseline')
            (toolkit / 'references').mkdir(); (toolkit / 'references' / 'old.md').write_text('stale reference')
            (policy / 'SKILL.md').write_text('enhanced')
            (policy / 'references').mkdir(); (policy / 'references' / 'questions.md').write_text('good questions')
            adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
            mounted = r.mount(adapter.frozen.base, toolkit, policy, workspace)
            self.assertEqual((mounted / 'SKILL.md').read_text(), 'enhanced')
            self.assertEqual((mounted / 'scripts' / 'confidence.py').read_text(), 'runtime bytes')
            self.assertEqual([p.name for p in (mounted / 'references').iterdir()], ['questions.md'])
            self.assertFalse((mounted / 'policy').exists())

    def stage(self, backend='claude'):
        terminal = {'complete': False, 'summary': 'honest gap', 'remaining': ['not complete']}
        return {'backend': backend, 'terminal': {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': terminal}, 'structured_output': terminal,
                'process_cleanup_scope': 'original_process_group', 'detached_descendants_contained': False,
                'stream_changed_during_cleanup': False, 'guarded_new_session_processes': 1, 'timed_out': False,
                'process_exit': 0, 'observed_assistant_models': ['claude-haiku-5-5'], 'model_requested': 'gpt-6-astra',
                'model_attribution': 'requested_only', 'actual_model': None, 'observed_models': [], 'status': 'completed', 'errors': [],
                'native_guard_violated': False, 'unexpected_native_calls': [], 'unexpected_mcp_calls': []}

    def test_honest_incomplete_is_qualified_not_fabricated_success(self):
        arm = {'backend': 'claude', 'model': 'claude-haiku-5-5'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        stage = self.stage(); q = r.qualification(stage, {'passed': True}, arm, adapter)
        self.assertTrue(q['eligible'])
        self.assertFalse(r.terminal(stage)['complete'])

    def test_unknown_metadata_and_model_substitution_fail_closed(self):
        arm = {'backend': 'claude', 'model': 'claude-haiku-5-5'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        corruptions = {'process_exit': None, 'timed_out': None, 'guarded_new_session_processes': True,
                       'observed_assistant_models': ['claude-opus-5-5'], 'stream_changed_during_cleanup': None,
                       'native_guard_violated': True, 'terminal': {'structured_output': {'complete': True}}}
        for key, value in corruptions.items():
            with self.subTest(field=key):
                stage = self.stage(); stage[key] = value
                self.assertFalse(r.qualification(stage, {'passed': True}, arm, adapter)['eligible'])
        self.assertFalse(r.qualification(self.stage(), {'passed': False}, arm, adapter)['eligible'])

    def test_codex_requested_only_attribution_remains_unknown(self):
        arm = {'backend': 'codex', 'model': 'gpt-6-astra'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        q = r.qualification(self.stage('codex'), {'passed': True}, arm, adapter)
        self.assertTrue(q['eligible'])
        self.assertEqual(q['model_attribution'], 'requested_only')
        self.assertIsNone(q['actual_model'])

    def test_claude_schema_shaped_error_or_missing_result_status_is_ineligible(self):
        arm = {'backend': 'claude', 'model': 'claude-haiku-5-5'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        mutations = [dict(is_error=True, subtype='error_max_budget_usd'), dict(is_error=True),
                     dict(subtype='error_max_turns'), dict(type='assistant'), dict(is_error=0)]
        for fields in mutations:
            with self.subTest(fields=fields):
                stage = self.stage(); stage['terminal'].update(fields)
                self.assertFalse(r.qualification(stage, {'passed': True}, arm, adapter)['eligible'])
                self.assertIsNone(r.terminal(stage))
        for missing in ('type', 'subtype', 'is_error'):
            with self.subTest(missing=missing):
                stage = self.stage(); stage['terminal'].pop(missing)
                self.assertFalse(r.qualification(stage, {'passed': True}, arm, adapter)['eligible'])
                self.assertIsNone(r.terminal(stage))

    def test_codex_schema_shaped_error_or_unknown_status_is_ineligible(self):
        arm = {'backend': 'codex', 'model': 'gpt-6-astra'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        mutations = [{'status': 'backend_error'}, {'status': None}, {'errors': [{'type': 'turn.failed'}]},
                     {'errors': None}, {'native_guard_violated': None}, {'unexpected_native_calls': None}, {'unexpected_mcp_calls': None}]
        for fields in mutations:
            with self.subTest(fields=fields):
                stage = self.stage('codex'); stage.update(fields)
                self.assertFalse(r.qualification(stage, {'passed': True}, arm, adapter)['eligible'])
                self.assertIsNone(r.terminal(stage))

    def test_codex_contradictory_observed_model_cannot_be_silent_substitution(self):
        arm = {'backend': 'codex', 'model': 'gpt-6-astra'}
        adapter = types.SimpleNamespace(effective_inventory=lambda *_: {'passed': True})
        mutations = [{'actual_model': 'gpt-6.1-sol', 'observed_models': ['gpt-6.1-sol'], 'model_attribution': 'event_observed'},
                     {'actual_model': 'gpt-6.1-sol'}, {'observed_models': ['gpt-6.1-sol']},
                     {'actual_model': 'gpt-6-astra', 'observed_models': ['gpt-6-astra'], 'model_attribution': 'requested_only'},
                     {'actual_model': None, 'observed_models': [], 'model_attribution': 'event_observed'}, {'observed_models': None}]
        for fields in mutations:
            with self.subTest(fields=fields):
                stage = self.stage('codex'); stage.update(fields)
                self.assertFalse(r.qualification(stage, {'passed': True}, arm, adapter)['eligible'])
        stage = self.stage('codex'); stage.update(actual_model='gpt-6-astra', observed_models=['gpt-6-astra'], model_attribution='event_observed')
        q = r.qualification(stage, {'passed': True}, arm, adapter)
        self.assertTrue(q['eligible'])
        self.assertEqual(q['actual_model'], 'gpt-6-astra')

    def test_strict_terminal_rejects_missing_wrong_and_extra_fields(self):
        good = self.stage()
        self.assertIsNotNone(r.terminal(good))
        for value in ({'complete': 'true', 'summary': '', 'remaining': []},
                      {'complete': True, 'summary': '', 'remaining': [1]},
                      {'complete': True, 'summary': '', 'remaining': [], 'extra': 'unbound'}, None):
            self.assertIsNone(r.terminal(dict(good, terminal=dict(good['terminal'], structured_output=value))))

    def sealed_fixture(self, root):
        source = root / 'source'; source.mkdir(); (source / 'governed.py').write_text('original')
        requests = root / 'requests.json'; r.write(requests, [{'trial_id': 't'}])
        payload = {'material': {'files': {}, 'trees': {str(source): r.inventory(source)}}, 'requests_sha256': r.sha(requests)}
        r.write(root / 'registration.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
        return source

    def test_current_source_tamper_is_detected_before_launch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); source = self.sealed_fixture(root)
            r.verify(root)
            (source / 'governed.py').write_text('modified')
            with self.assertRaisesRegex(ValueError, 'Registered tree changed'):
                r.verify(root)

    def test_source_mode_and_symlink_cannot_bypass_registration(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); source = self.sealed_fixture(root)
            file = source / 'governed.py'; file.chmod(file.stat().st_mode ^ 0o111)
            with self.assertRaises(ValueError): r.verify(root)
            file.unlink(); file.symlink_to(root / 'requests.json')
            with self.assertRaisesRegex(ValueError, 'symlink'): r.verify(root)

    def test_schedule_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); self.sealed_fixture(root)
            r.write(root / 'requests.json', [{'trial_id': 'replacement'}])
            with self.assertRaisesRegex(ValueError, 'Registered requests'): r.verify(root)

    def test_started_unknown_trial_is_never_retried(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); self.sealed_fixture(root)
            out = root / 'trials' / 't'; out.mkdir(parents=True)
            (out / 'started.json').write_text('prior attempt')
            with patch.object(r, 'route', side_effect=AssertionError('must not launch')):
                result = r.run_cell({'trial_id': 't'}, {}, {}, {}, root)
            self.assertEqual(result['status'], 'preserved_previously_started')
            self.assertEqual((out / 'started.json').read_text(), 'prior attempt')
            self.assertFalse((out / 'receipt.json').exists())

    def test_recursive_peer_request_receives_explicit_denial(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); r.write(root / 'a.review-request.json', {'role': 'critic'})
            callback = lambda *_: self.fail('No hosted reviewer may launch')
            r.deny_reviews(root, root, callback, 100)
            response = r.read(root / 'a.review-response.json')
            self.assertFalse(response['available'])
            self.assertIn('no recursive', response['reason'])

    def test_prepare_refuses_existing_outputs_before_any_probe(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with patch.object(r, 'route', side_effect=AssertionError('must not probe')):
                with self.assertRaisesRegex(ValueError, 'new output'):
                    r.prepare(root / 'missing.json', root)

    def test_oracle_cleanup_output_drift_invalidates_verdict(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'grader.stdout').write_text('initial'); (root / 'grader.stderr').write_text('')
            class Guard:
                def __enter__(self): return self
                def __exit__(self, *_): (root / 'grader.stdout').write_text('late writer')
            class Proxy:
                def __init__(self, underlying): pass
            value = {'oracle_passed': True, 'stdout_sha256': r.sha(root / 'grader.stdout'), 'stderr_sha256': r.sha(root / 'grader.stderr')}
            adapter = types.SimpleNamespace(frozen=types.SimpleNamespace(
                grader=types.SimpleNamespace(subprocess=object(), invoke_oracle=lambda *_: value),
                processes=types.SimpleNamespace(SubprocessProxy=Proxy, ProcessGuard=Guard)))
            result = r.invoke_oracle(adapter, root / 'oracle.py', root, root)
            self.assertTrue(result['output_changed_during_cleanup'])
            self.assertIsNone(result['oracle_passed'])

    def preparation_fixture(self, root):
        toolkit = root / 'runtime'; toolkit.mkdir()
        (toolkit / 'SKILL.md').write_text('shared runtime')
        policy = root / 'policy'; policy.mkdir(); (policy / 'SKILL.md').write_text('selected policy')
        overlay = root / 'overlay.md'; overlay.write_text('public question guidance')
        catalog = root / 'catalog.json'; r.write(catalog, {'models': []})
        available = root / 'availability.json'; r.write(available, {'qualified': True, 'model_requested': 'gpt-6-astra', 'cohort': False})
        tasks = []
        for number in (32, 31, 40, 34, 39, 35):
            base = root / ('base-' + str(number)); base.mkdir(); (base / 'public.py').write_text('base code')
            head = root / ('PRIVATE_ACCEPTED_HEAD-' + str(number)); head.mkdir(); (head / 'public.py').write_text('head solution')
            oracle = root / ('PRIVATE_ORACLE-' + str(number)); oracle.mkdir(); (oracle / 'evaluate.py').write_text('secret checks')
            tasks.append({'task_id': 'tweed-pr' + str(number), 'base_snapshot': str(base), 'head_snapshot': str(head), 'oracle_script': str(oracle / 'evaluate.py'),
                          'prompt': 'Fix public behavior', 'production_paths': ['public.py'], 'test_commands': [['python3', '-m', 'unittest']]})
        manifest = root / 'manifest.json'; r.write(manifest, {'tasks': tasks})
        arms = []
        for name, backend, model in [('baseline-opus', 'claude', 'claude-opus-5-5'), ('enhanced-opus', 'claude', 'claude-opus-5-5'),
                                     ('enhanced-haiku', 'claude', 'claude-haiku-5-5'), ('enhanced-codex', 'codex', 'gpt-6-astra')]:
            arms.append({'id': name, 'backend': backend, 'model': model, 'policy_directory': str(policy), 'prompt_file': str(overlay)})
        config = root / 'config.json'
        r.write(config, {'manifest': str(manifest), 'toolkit_directory': str(toolkit), 'codex_catalog': str(catalog), 'codex_qualification': str(available),
                         'repeats': 2, 'seconds': 240, 'claude_budget_usd': 2, 'arms': arms})
        def capability(source, destination): r.write(destination, {'models': ['public metadata only']})
        backend = types.SimpleNamespace(capability_catalog=capability, inventory_probe=lambda *_args, **_kwargs: {'inventory': {'passed': True}})
        adapter = types.SimpleNamespace(frozen=types.SimpleNamespace(base=types.SimpleNamespace(sandbox_check=lambda *_: {'passed': True}), backend=backend),
                                        local_mcp_probe=lambda *_args, **_kwargs: {'passed': True})
        return config, adapter

    def test_registration_has_exact_48_cells_without_oracle_or_head_exposure(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); config, adapter = self.preparation_fixture(root); study = root / 'study'
            with patch.object(r, 'route', return_value=adapter), patch.object(r, 'cli_versions', return_value={'claude': 'test Claude', 'codex': 'test Codex'}):
                payload = r.prepare(config, study)
                r.verify(study)
            requests = r.read(study / 'requests.json')
            self.assertEqual(len(requests), 48)
            self.assertEqual(len({q['trial_id'] for q in requests}), 48)
            for q in requests:
                self.assertNotIn('PRIVATE_ORACLE', q['prompt'])
                self.assertNotIn('PRIVATE_ACCEPTED_HEAD', q['prompt'])
                self.assertNotIn('secret checks', q['prompt'])
                self.assertNotIn('head solution', q['prompt'])
            self.assertEqual(payload['planned_cells'], 48)

    def test_offline_transport_failure_prevents_registration_and_calls(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); config, adapter = self.preparation_fixture(root); study = root / 'study'
            adapter.local_mcp_probe = lambda *_args, **_kwargs: {'passed': False}
            with patch.object(r, 'route', return_value=adapter), patch.object(r, 'cli_versions', return_value={'claude': 'test Claude', 'codex': 'test Codex'}):
                with self.assertRaisesRegex(ValueError, 'transport unqualified'): r.prepare(config, study)
            self.assertFalse((study / 'registration.json').exists())
            self.assertTrue((study / 'preparation-failed.json').exists())

    def test_wrong_codex_qualification_cannot_silently_change_route(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); config, adapter = self.preparation_fixture(root)
            value = r.read(config); r.write(value['codex_qualification'], {'qualified': True, 'model_requested': 'gpt-6.1-sol', 'cohort': False})
            with patch.object(r, 'route', side_effect=AssertionError('must not probe')):
                with self.assertRaisesRegex(ValueError, 'selected Codex route'): r.prepare(config, root / 'study')

    def test_import_failure_preserves_started_cell_as_explicit_unknown(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); self.sealed_fixture(root)
            request = {'trial_id': 't', 'task_id': 'tweed-pr32', 'arm_id': 'baseline-opus', 'repeat': 1}
            arm = {'backend': 'claude', 'model': 'claude-opus-5-5'}
            with patch.object(r, 'route', side_effect=RuntimeError('adapter unavailable')):
                receipt = r.run_cell(request, {}, arm, {}, root)
            self.assertIsNone(receipt['accepted'])
            self.assertFalse(receipt['eligible'])
            self.assertIn('adapter unavailable', receipt['error'])
            self.assertTrue((root / 'trials' / 't' / 'started.json').exists())
            self.assertTrue((root / 'trials' / 't' / 'receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
