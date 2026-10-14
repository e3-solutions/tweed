"""Boundary tests for the unfrozen cross-provider adapter; no paid calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cross_backend',HERE/'cross_backend.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)


def namespace(name,names):
    return {'type':'namespace','name':name,'tools':[{'type':'function','name':n} for n in names]}


class AdapterBoundaryTests(unittest.TestCase):
    def test_message_local_tools_cannot_be_mistaken_for_no_tools(self):
        payload={'input':[{'role':'developer','tools':[namespace('collaboration',['spawn_agent'])]}]}
        result=backend.inventory_guard(backend.declared_tools(payload),[])
        self.assertFalse(result['passed'])
        self.assertEqual(result['unexpected_tools'],['collaboration.spawn_agent'])

    def test_extra_native_shell_or_patch_rejected(self):
        safe=namespace('mcp__cp_trial',backend.runner.NATIVE_TOOLS)
        resources=namespace('functions',['list_mcp_resources','list_mcp_resource_templates','read_mcp_resource'])
        result=backend.inventory_guard([safe,resources],backend.runner.NATIVE_TOOLS,allow_resource_handlers=True)
        self.assertTrue(result['passed']);self.assertFalse(result['strict_seven_tool_parity'])
        for unsafe in ('apply_patch','exec_command','write_stdin'):
            self.assertFalse(backend.inventory_guard([safe,resources,namespace('functions',[unsafe])],backend.runner.NATIVE_TOOLS,allow_resource_handlers=True)['passed'])

    def test_duplicate_or_missing_controlled_tool_rejected(self):
        names=list(backend.runner.NATIVE_TOOLS)
        for bad in (names[:-1],names+[names[0]]):
            self.assertFalse(backend.inventory_guard([namespace('mcp__cp_trial',bad)],names)['passed'])

    def test_catalog_copies_model_metadata_without_identity_or_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.json';out=Path(tmp)/'catalog.json'
            source.write_text(json.dumps({'identity':'PRIVATE','auth':'PRIVATE','models':[{
                'slug':backend.MODEL,'apply_patch_tool_type':'freeform','shell_type':'unified_exec',
                'multi_agent_version':'v2','context_window':1000}]}))
            receipt=backend.capability_catalog(source,out)
            value=json.loads(out.read_text())
            self.assertEqual(set(value),{'models'});self.assertNotIn('PRIVATE',out.read_text())
            self.assertIsNone(value['models'][0]['apply_patch_tool_type'])
            self.assertEqual(value['models'][0]['multi_agent_version'],'disabled')
            self.assertEqual(value['models'][0]['context_window'],1000)
            self.assertIn('source_model_metadata_sha256',receipt)

    def test_catalog_refuses_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.json';source.write_text('{"models":[{"slug":"gpt-other"}]}')
            with self.assertRaises(ValueError):backend.capability_catalog(source,Path(tmp)/'out.json')

    def test_cli_request_has_actual_supported_controls_and_no_provider_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);argv=backend.command(root,root,root/'catalog.json','task')
            for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--json','--strict-config','--output-schema'):
                self.assertIn(flag,argv)
            self.assertEqual(argv[argv.index('--model')+1],backend.MODEL)
            self.assertIn('model_reasoning_effort="medium"',argv)
            self.assertIn('mcp_servers={}',argv)
            self.assertNotIn('model_provider=', '\n'.join(argv))
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',argv)

    def test_provider_failure_preserves_unknown_completion_usage_price_and_model(self):
        events=[{'type':'thread.started','thread_id':'session'},
                {'type':'error','message':'Model is unsupported'}, {'type':'turn.failed','error':{'message':'unsupported'}}]
        result=backend.event_receipt(events,'{"complete":true,"summary":"fabricated","remaining":[]}',error=True)
        for key in ('declared_complete','usage','total_cost_usd','actual_model'):self.assertIsNone(result[key])
        self.assertEqual(result['session_id'],'session')
        self.assertEqual(result['model_attribution'],'requested_only')

    def test_model_attribution_requires_observed_model_and_does_not_infer_from_request(self):
        result=backend.event_receipt([{'type':'turn.completed','usage':{'input_tokens':5,'output_tokens':2}}],'{"complete":true,"summary":"done","remaining":[]}')
        self.assertTrue(result['declared_complete']);self.assertIsNone(result['actual_model'])
        self.assertIsNone(result['total_cost_usd']);self.assertEqual(result['usage']['output_tokens'],2)
        result=backend.event_receipt([{'type':'turn.completed','model':'observed','usage':{}}],'{"complete":false,"summary":"partial","remaining":["work"]}')
        self.assertEqual(result['actual_model'],'observed');self.assertFalse(result['declared_complete'])

    def test_completion_requires_successful_terminal_exact_schema(self):
        events=[{'type':'turn.completed','usage':{}}]
        for bad in ('{"complete":true}','{"complete":true,"summary":4,"remaining":[]}',
                    '{"complete":true,"summary":"done","remaining":[],"extra":0}'):
            self.assertIsNone(backend.event_receipt(events,bad)['declared_complete'])
        self.assertIsNone(backend.event_receipt([], '{"complete":true,"summary":"done","remaining":[]}')['declared_complete'])

    def test_peer_callback_retains_provider_origin_source_and_resolvable_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'workspace';source.mkdir();(source/'source.py').write_text('answer=2')
            control=root/'control';control.mkdir();req={'id':'abc','role':'adversarial_reviewer','question':'verify answer2'}
            (control/'abc.review-request.json').write_text(json.dumps(req));seen=[]
            def callback(request,workspace,deadline):
                seen.append((request,workspace,deadline))
                return {'provider':'anthropic','session_id':'actual-session','model_usage':{'claude-opus-5-5':{'outputTokens':8}},'total_cost_usd':.01}
            deadline=time.time()+60
            backend.service_reviews(control,source,callback,deadline)
            response=json.loads((control/'abc.review-response.json').read_text())
            evidence=source/response['evidence_path'];self.assertTrue(evidence.is_file())
            value=json.loads(evidence.read_text());self.assertEqual(value['provider_receipt']['session_id'],'actual-session')
            self.assertEqual(value['source_sha256_at_launch'],value['source_sha256_after'])
            self.assertEqual(seen[0][2],deadline)
            backend.service_reviews(control,source,callback,deadline);self.assertEqual(len(seen),1)

    def test_live_call_refuses_unverified_or_different_catalog_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'version',return_value=backend.CLI_VERSION),patch.object(backend.subprocess,'Popen') as spawn:
            root=Path(tmp);workspace=root/'workspace';workspace.mkdir();control=root/'control';catalog=root/'catalog';catalog.write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'exact declared inventory'):
                backend.codex_call(workspace,control,'task',catalog=catalog)
            receipt={'inventory':{'passed':True,'expected_tools':[]},'capability_catalog_sha256':'WRONG'}
            with self.assertRaisesRegex(RuntimeError,'catalog differs'):
                backend.codex_call(workspace,control,'task',catalog=catalog,with_mcp=False,inventory_receipt=receipt)
            spawn.assert_not_called()

    def test_native_execution_invalidates_an_otherwise_valid_final(self):
        events=[{'type':'item.started','item':{'type':'command_execution','command':'outside'}},
                {'type':'turn.completed','usage':{}}]
        result=backend.event_receipt(events,'{"complete":true,"summary":"done","remaining":[]}')
        self.assertTrue(result['native_guard_violated']);self.assertIsNone(result['declared_complete'])

    def test_refused_scheduled_review_remains_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'workspace';source.mkdir();control=root/'control';control.mkdir()
            request={'id':'refused','role':'critic','question':'extra peer'}
            (control/'refused.review-request.json').write_text(json.dumps(request))
            backend.service_reviews(control,source,lambda *args:{'available':False,'reason':'unscheduled'},time.time()+10)
            self.assertFalse(json.loads((control/'refused.review-response.json').read_text())['available'])

    def test_symlink_source_refuses_review_without_launching_peer_or_losing_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'workspace';source.mkdir();control=root/'control';control.mkdir()
            secret=root/'private';secret.write_text('PRIVATE');(source/'production.py').symlink_to(secret)
            (control/'bad.review-request.json').write_text('{"id":"bad","role":"critic","question":"review"}')
            with patch('builtins.print'),patch.object(backend,'workspace_evidence') as evidence:
                callback=unittest.mock.Mock()
                backend.service_reviews(control,source,callback,time.time()+10)
                callback.assert_not_called();evidence.assert_not_called()
            value=json.loads((control/'bad.review-response.json').read_text())
            self.assertFalse(value['available']);self.assertIn('Symlink',value['error'])
            self.assertEqual(secret.read_text(),'PRIVATE')

    def test_evidence_directory_symlink_never_redirects_coordinator_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'workspace';source.mkdir();outside=root/'outside';outside.mkdir()
            (source/'.confidence').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(OSError):backend.workspace_evidence(source,'peer.json',{'proof':True})
            self.assertFalse((outside/'peer.json').exists())

    def test_live_inventory_probe_exposes_no_native_shell_and_only_one_mcp_server(self):
        # Local dummy-auth endpoint: real CLI serialization + real confined MCP
        # startup, no hosted inference and no user authorization headers captured.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);workspace=root/'workspace';workspace.mkdir()
            catalog=root/'catalog.json'
            source=backend.runner.ROOT/'.confidence/benchmark/cross-backend-research/actual-model-catalog.json'
            if not source.exists():self.skipTest('Pinned local public model metadata absent')
            backend.capability_catalog(source,catalog)
            result=backend.inventory_probe(workspace,root/'control',catalog,with_mcp=True)
            self.assertTrue(result['request_captured'])
            self.assertTrue(result['inventory']['passed'],result['inventory'])
            payload=json.loads((root/'control/declared-request.json').read_text())
            self.assertEqual(payload['model'],backend.MODEL)
            self.assertEqual(payload['reasoning']['effort'],'medium')
            self.assertNotIn('authorization',payload)


if __name__=='__main__':unittest.main()
