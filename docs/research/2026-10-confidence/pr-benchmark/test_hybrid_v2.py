"""V2 pipeline regressions; actual local MCP processes, no hosted inference."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2_adapter_tests', HERE / 'hybrid_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


class PathPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.v2-test-')
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / 'actor'
        self.workspace.mkdir()
    def tearDown(self):
        self.temp.cleanup()

    @unittest.skipUnless(Path('/usr/bin/sandbox-exec').exists(), 'Requires macOS sandbox')
    def test_relative_real_claude_adapter_fails_exact_startup_seam(self):
        relative = (self.root / 'controller' / 'test_designer').relative_to(Path.cwd())
        result = v2.local_mcp_probe('opus', self.workspace, relative, readonly=True)
        self.assertFalse(result['passed'])
        self.assertFalse(result['config_argument_is_absolute'])
        self.assertNotEqual(result['exit_code'], 0)
        stderr = (relative / 'qualification.stderr').read_text()
        self.assertIn('server-config.json', stderr)
        self.assertEqual(result['effective_mcp_tools'], [])

    @unittest.skipUnless(Path('/usr/bin/sandbox-exec').exists(), 'Requires macOS sandbox')
    def test_normalized_relative_study_starts_all_seven_tools_both_providers(self):
        relative = (self.root / 'controller').relative_to(Path.cwd())
        args = v2.normalize_args(argparse.Namespace(study=relative, protocol=relative/'protocol.json',
            manifest=relative/'manifest.json', model_catalog=relative/'catalog.json'))
        for model in ('astra', 'opus'):
            for readonly in (False, True):
                with self.subTest(model=model, readonly=readonly):
                    result = v2.local_mcp_probe(model, self.workspace,
                        args.study / (model + str(readonly)), readonly=readonly)
                    self.assertTrue(result['passed'], result)
                    self.assertTrue(result['config_argument_is_absolute'])
                    self.assertEqual(set(result['effective_mcp_tools']), set(v2.EXPECTED))
                    self.assertEqual(result['hosted_inference_calls'], 0)
                    if readonly:
                        self.assertTrue(result['readonly_write_denied'])
        self.assertFalse((self.workspace/'qualification-must-not-create.py').exists())

    def test_normalizer_keeps_optional_catalog_none(self):
        args = v2.normalize_args(argparse.Namespace(protocol=Path('a'),manifest=Path('b'),study=Path('c'),model_catalog=None))
        self.assertTrue(args.study.is_absolute())
        self.assertIsNone(args.model_catalog)


class InventoryQualificationTests(unittest.TestCase):
    local = {'passed': True}
    def opus(self, tools=None, servers=None):
        return {'assigned_model': 'opus', 'harness_initialization': {
            'tools': tools if tools is not None else ['StructuredOutput'] + ['mcp__cp_trial__'+n for n in v2.EXPECTED],
            'mcp_servers': servers if servers is not None else [{'name':'cp_trial','status':'connected'}]}}
    def test_opus_all_tools_and_server_connected_pass(self):
        result = v2.effective_inventory(self.opus(), self.local)
        self.assertTrue(result['passed'])
        self.assertFalse(result['strict_seven_tool_parity'])
    def test_observed_failed_server_and_only_structured_output_rejected(self):
        stage = self.opus(['StructuredOutput'], [{'name':'cp_trial','status':'failed'}])
        result = v2.effective_inventory(stage,self.local)
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['missing_tools']), 7)
    def test_missing_init_remains_unknown(self):
        self.assertIsNone(v2.effective_inventory({'assigned_model':'opus'},self.local)['passed'])
    def test_unknown_fields_remain_unknown(self):
        stage = self.opus();stage['harness_initialization']['tools'] = None
        self.assertIsNone(v2.effective_inventory(stage,self.local)['passed'])
    def test_unexpected_native_tool_rejected(self):
        stage = self.opus();stage['harness_initialization']['tools'].append('Bash')
        self.assertFalse(v2.effective_inventory(stage,self.local)['passed'])
    def test_duplicate_declared_tool_rejected(self):
        stage=self.opus();stage['harness_initialization']['tools'].append('StructuredOutput')
        self.assertFalse(v2.effective_inventory(stage,self.local)['passed'])
    def test_codex_resource_handlers_are_disclosed_not_seven_tool_parity(self):
        stage={'assigned_model':'astra','inventory_guard':{'passed':True,
            'expected_tools':['mcp__cp_trial__'+n for n in v2.EXPECTED]+v2.RESOURCE_HANDLERS}}
        result=v2.effective_inventory(stage,self.local)
        self.assertTrue(result['passed'])
        self.assertFalse(result['live_wire_inventory_observed'])
        self.assertFalse(result['strict_seven_tool_parity'])
        self.assertEqual(len(result['additional_resource_handlers']),3)
    def test_failed_local_transport_overrides_nominal_provider_inventory(self):
        result=v2.effective_inventory(self.opus(),{'passed':False})
        self.assertFalse(result['passed'])


class QualifiedInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.workspace=self.root/'actor';self.workspace.mkdir()
        self.control=self.root/'stage';self.study=self.root/'study'
    def tearDown(self):self.temp.cleanup()
    def test_failed_local_probe_never_starts_inference(self):
        with patch.object(v2,'local_mcp_probe',return_value={'passed':False}),patch.object(v2,'_ORIGINAL_INVOKE') as launch:
            stage=v2.qualified_invoke('opus',self.workspace,self.control,'task',30,1000,True,self.study,budget=.2)
        launch.assert_not_called();self.assertTrue(stage['native_guard_violated'])
        self.assertIsNone(stage['total_cost_usd']);self.assertIsNone(stage['declared_complete'])
    def test_missing_live_initialization_is_unknown_and_ineligible(self):
        with patch.object(v2,'local_mcp_probe',return_value={'passed':True}),patch.object(v2,'_ORIGINAL_INVOKE',return_value={'assigned_model':'opus','declared_complete':True}):
            stage=v2.qualified_invoke('opus',self.workspace,self.control,'task',30,1000,True,self.study,budget=.2)
        self.assertIsNone(stage['adapter_qualification']['passed'])
        self.assertTrue(stage['native_guard_violated']);self.assertIsNone(stage['declared_complete'])

if __name__=='__main__':unittest.main()
