"""Independent qualification negatives; metadata fixtures are not model calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2_grader_tests', HERE / 'hybrid_v2_grader.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


def healthy_stage(provider, role):
    expected = list(grader.frozen.hybrid.base.NATIVE_TOOLS)
    local = dict(passed=True, offline=True, hosted_inference_calls=0, provider=provider,
        readonly=role in ('test_designer', 'adversarial_reviewer'), connected=True,
        effective_mcp_tools=expected, list_files_succeeded=True, exit_code=0,
        config_argument_is_absolute=True, readonly_write_denied=True)
    stage = dict(assigned_model=provider, role=role, synthetic_control_only=True,
        timed_out=False, process_exit=0, process_cleanup_scope='original_process_group',
        detached_descendants_contained=False, guarded_new_session_processes=1,
        stream_changed_during_cleanup=False, process_cleanup_seconds=.001,
        source_sha256_at_launch='a'*64, source_sha256_after='a'*64)
    if provider == 'opus':
        tools = ['StructuredOutput'] + ['mcp__cp_trial__' + name for name in expected]
        stage.update(backend='claude_code', harness_initialization={
            'tools': tools, 'mcp_servers': [{'name': 'cp_trial', 'status': 'connected'}]},
            adapter_qualification=dict(passed=True, basis='live_claude_init', local=local,
                connected=True, effective_tools=tools, missing_tools=[], unexpected_tools=[]))
    else:
        handlers = list(grader.frozen.hybrid.backend.RESOURCE_HANDLERS)
        guard = dict(passed=True, expected_tools=['mcp__cp_trial__'+name for name in expected]+handlers,
                     declared_tools=['mcp__cp_trial.'+name for name in expected]+handlers)
        stage.update(backend='codex_cli', inventory_guard=guard,
            adapter_qualification=dict(passed=True, basis='offline_declared_codex_inventory_and_local_pipeline',
                local=local, declared_inventory=guard, live_wire_inventory_observed=False,
                strict_seven_tool_parity=False, additional_resource_handlers=handlers))
    return stage


class QualificationTests(unittest.TestCase):
    def test_both_backend_formats_and_both_roles_qualify(self):
        for provider in ('astra', 'opus'):
            for role in ('test_designer', 'main_implementation', 'adversarial_reviewer', 'main_repair'):
                self.assertTrue(grader.qualification(healthy_stage(provider, role), provider)['passed'])

    def test_missing_unknown_false_and_wrong_basis_rejected(self):
        for provider in ('astra', 'opus'):
            for mutation in ('missing', 'unknown', 'false', 'basis'):
                stage = healthy_stage(provider, 'main_repair')
                if mutation == 'missing': stage.pop('adapter_qualification')
                elif mutation == 'basis': stage['adapter_qualification']['basis'] = 'model_assertion'
                else: stage['adapter_qualification']['passed'] = None if mutation == 'unknown' else False
                self.assertFalse(grader.qualification(stage, provider)['passed'], (provider, mutation))

    def test_wrong_provider_role_and_missing_local_facts_rejected(self):
        for key, value in [('provider', 'other'), ('readonly', False), ('effective_mcp_tools', []),
                           ('connected', False), ('readonly_write_denied', None), ('hosted_inference_calls', 1),
                           ('config_argument_is_absolute', False)]:
            stage = healthy_stage('opus', 'test_designer')
            stage['adapter_qualification']['local'][key] = value
            self.assertFalse(grader.qualification(stage, 'opus')['passed'], key)

    def test_nominal_pass_boolean_cannot_hide_opus_missing_or_extra_tools(self):
        for replacement in (['StructuredOutput'], ['Bash'], [{'malformed': True}]):
            stage = healthy_stage('opus', 'main_repair')
            stage['harness_initialization']['tools'] = replacement
            self.assertFalse(grader.qualification(stage, 'opus')['passed'])

    def test_codex_inventory_mismatch_and_live_wire_overclaim_rejected(self):
        stage = healthy_stage('astra', 'main_repair')
        stage['inventory_guard']['declared_tools'] = []
        self.assertFalse(grader.qualification(stage, 'astra')['passed'])
        stage = healthy_stage('astra', 'main_repair')
        stage['adapter_qualification']['live_wire_inventory_observed'] = True
        self.assertFalse(grader.qualification(stage, 'astra')['passed'])

    def test_skipped_stage_remains_unknown_and_sanitization_drops_paths(self):
        self.assertIsNone(grader.qualification({'status': 'skipped_deadline'}, 'astra')['passed'])
        stage = healthy_stage('opus', 'main_repair')
        stage['adapter_qualification']['local']['actor_cwd'] = '/PRIVATE_PATH'
        self.assertNotIn('PRIVATE_PATH', json.dumps(grader.qualification(stage, 'opus')))

    def test_missing_unknown_malformed_and_overclaimed_lifecycle_fail_closed(self):
        fields = ['timed_out', 'process_exit', 'process_cleanup_scope', 'detached_descendants_contained',
                  'guarded_new_session_processes', 'stream_changed_during_cleanup', 'process_cleanup_seconds']
        for field in fields:
            for value in ('MISSING', None):
                stage = healthy_stage('astra', 'main_repair')
                if value == 'MISSING': stage.pop(field)
                else: stage[field] = value
                self.assertFalse(grader.qualification(stage, 'astra')['passed'], field)
        for field, value in [('process_exit', True), ('guarded_new_session_processes', False),
                             ('detached_descendants_contained', True), ('stream_changed_during_cleanup', True),
                             ('process_cleanup_seconds', float('nan')), ('process_cleanup_seconds', -1)]:
            stage = healthy_stage('astra', 'main_repair'); stage[field] = value
            self.assertFalse(grader.qualification(stage, 'astra')['passed'], (field, value))
        stage = healthy_stage('astra', 'main_repair'); stage['timed_out'] = True
        self.assertTrue(grader.qualification(stage, 'astra')['passed'], 'A known timeout is an observed attempt, not missing metadata')

    def test_missing_unknown_invalid_and_changed_peer_source_hashes_rejected(self):
        for value in (None, '', 'scope', 'a'*63):
            stage = healthy_stage('opus', 'test_designer')
            stage['source_sha256_at_launch'] = stage['source_sha256_after'] = value
            self.assertFalse(grader.qualification(stage, 'opus')['passed'])
        stage = healthy_stage('opus', 'test_designer'); stage['source_sha256_after'] = 'b'*64
        self.assertFalse(grader.qualification(stage, 'opus')['passed'])

    def test_unqualified_stages_suppress_oracle_and_keep_unknown_cost(self):
        stage = healthy_stage('opus', 'main_repair')
        stage.pop('adapter_qualification')
        raw = {'stages': [stage]}
        frozen_result = dict(adapter_sha256='old', normalized=dict(harness_invalid_reasons=[],
            truthful_success=True, stage_usage=[{}], total_cost_usd=None))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'receipt.json'; path.write_text(json.dumps(raw))
            def fake_grade(*args):
                oracle = grader.frozen.hybrid.grader.invoke_oracle(None, None, None)
                result = copy.deepcopy(frozen_result)
                result['normalized']['oracle_passed'] = oracle['oracle_passed']
                return result
            with patch.object(grader.frozen, 'grade', side_effect=fake_grade):
                result = grader.grade(path, {'main_model': 'opus', 'peer_model': 'opus'}, {}, 'package')
        self.assertIsNone(result['normalized']['oracle_passed'])
        self.assertIsNone(result['normalized']['total_cost_usd'])
        self.assertTrue(result['normalized']['harness_invalid'])
        self.assertFalse(result['normalized']['truthful_success'])
        self.assertEqual(result['frozen_adapter_sha256'], 'old')


if __name__ == '__main__': unittest.main()
