"""Fixed-stage provider routing tests. No hosted inference calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('hybrid_runner_under_test',HERE/'hybrid_runner.py')
hybrid=importlib.util.module_from_spec(spec);spec.loader.exec_module(hybrid)


class HybridStageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.workspace=self.root/'source';self.workspace.mkdir()
        (self.workspace/'product.py').write_text('answer=2\n')
        self.control=self.root/'control';self.control.mkdir()
        self.study=self.root/'study';self.study.mkdir()
        (self.study/'inventory.json').write_text('{}')
    def tearDown(self):self.temp.cleanup()

    def test_astra_invocation_passes_stage_deadline_readonly_and_exact_catalog(self):
        deadline=time.time()+90
        fake={'declared_complete':False,'structured_output':{'complete':False,'summary':'review','remaining':['gap']},
              'usage':{'input_tokens':10,'output_tokens':2},'total_cost_usd':None}
        with patch.object(hybrid.backend,'codex_call',return_value=fake) as call:
            result=hybrid.invoke('astra',self.workspace,self.control,'requirements',90,deadline,True,self.study)
        kwargs=call.call_args.kwargs
        self.assertEqual(kwargs['timeout'],90);self.assertEqual(kwargs['deadline'],deadline)
        self.assertTrue(kwargs['readonly']);self.assertEqual(kwargs['catalog'],self.study/'capabilities.json')
        self.assertIs(kwargs['review_callback'],hybrid.scheduled_review)
        self.assertIsNone(result['total_cost_usd']);self.assertIn('source_sha256_after',result)
        self.assertEqual(json.loads((self.control/'receipt.json').read_text())['assigned_model'],'astra')

    def test_opus_wait_services_refusal_and_never_launches_unscheduled_peer(self):
        def fake_call(workspace,control,prompt,budget,seconds,deadline,readonly=False):
            request=control/'unexpected.review-request.json'
            request.write_text('{"role":"critic","question":"extra peer"}')
            response=control/'unexpected.review-response.json'
            until=time.monotonic()+2
            while not response.exists() and time.monotonic()<until:time.sleep(.01)
            self.assertTrue(response.exists(),'Main wait deadlocked instead of refusing the extra peer')
            self.assertFalse(json.loads(response.read_text())['available'])
            return {'declared_complete':False,'total_cost_usd':.01,'observed_assistant_models':['claude-opus-5-5']}
        with patch.object(hybrid.base,'claude_call',side_effect=fake_call) as launch:
            result=hybrid.invoke('opus',self.workspace,self.control,'task',2,time.time()+2,False,self.study,budget=.2)
        self.assertEqual(launch.call_count,1);self.assertEqual(result['provider'],'anthropic')
        self.assertEqual(result['model_attribution'],'event_observed')

    def test_provider_exception_preserves_assigned_stage_receipt_unknown_terminal(self):
        with patch.object(hybrid.backend,'codex_call',side_effect=RuntimeError('backend rejected model')):
            result=hybrid.invoke('astra',self.workspace,self.control,'task',30,time.time()+30,False,self.study)
        self.assertIsNone(result['declared_complete']);self.assertIsNone(result['total_cost_usd'])
        self.assertIn('backend rejected model',result['error'])
        self.assertTrue((self.control/'receipt.json').is_file())

    def test_unknown_provider_never_selects_fallback(self):
        with patch.object(hybrid.backend,'codex_call') as astra,patch.object(hybrid.base,'claude_call') as opus:
            result=hybrid.invoke('unregistered',self.workspace,self.control,'task',30,time.time()+30,False,self.study)
        astra.assert_not_called();opus.assert_not_called();self.assertIn('Unregistered provider',result['error'])

    def test_readonly_peer_evidence_keeps_source_binding_and_incomplete_findings(self):
        source=hybrid.base.tree_digest(self.workspace)
        result={'source_sha256_after':source,'declared_complete':False,'structured_output':{
            'complete':False,'summary':'counterexample','remaining':['test fails']},'total_cost_usd':None}
        value=hybrid.review_artifact('test_designer',result,source,self.workspace)
        self.assertEqual(value['source_sha256_at_launch'],value['source_sha256_after'])
        stored=json.loads((self.workspace/'.confidence/test_designer.json').read_text())
        self.assertFalse(stored['provider_receipt']['declared_complete'])
        self.assertIn('counterexample',hybrid.peer_text(result));self.assertIn('test fails',hybrid.peer_text(result))

    def test_visible_evidence_excludes_private_reasoning_keeps_failed_tools(self):
        events=[{'type':'item.completed','item':{'type':'reasoning','text':'PRIVATE_REASONING'}},
                {'type':'item.completed','item':{'type':'mcp_tool_call','server':'cp_trial','tool':'run_tests',
                    'status':'failed','error':{'message':'fixture error'}}},
                {'type':'item.completed','item':{'type':'agent_message','text':'VISIBLE_FINDING'}}]
        (self.control/'stream.jsonl').write_text('\n'.join(json.dumps(x) for x in events)+'\n')
        value=hybrid.visible_evidence(self.control,'astra')
        self.assertNotIn('PRIVATE_REASONING',value)
        self.assertIn('fixture error',value);self.assertIn('VISIBLE_FINDING',value)

    def test_invalid_source_after_provider_reply_keeps_stage_receipt(self):
        outside=self.root/'private';outside.write_text('PRIVATE')
        def fake_call(*args,**kwargs):
            (self.workspace/'escape.py').symlink_to(outside)
            return {'declared_complete':False,'usage':{},'total_cost_usd':None}
        with patch.object(hybrid.backend,'codex_call',side_effect=fake_call):
            result=hybrid.invoke('astra',self.workspace,self.control,'task',30,time.time()+30,False,self.study)
        self.assertIsNone(result['source_sha256_after'])
        self.assertIn('Symlink',result['source_integrity_error'])
        self.assertTrue((self.control/'receipt.json').is_file());self.assertEqual(outside.read_text(),'PRIVATE')

    def test_peer_packet_refuses_actor_symlink_destination(self):
        outside=self.root/'private';outside.mkdir()
        (self.workspace/'.confidence').symlink_to(outside,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):
            hybrid.review_artifact('test_designer',{'source_sha256_after':'sha','declared_complete':False},'sha',self.workspace)
        self.assertFalse((outside/'test_designer.json').exists())

    def test_expired_aggregate_window_skips_later_provider_stages(self):
        protocol=json.loads((HERE/'hybrid-protocol.json').read_text())
        task={'task_id':'toy-fixed-deadline','base_snapshot':str(self.workspace),'prompt':'answer stays2',
              'production_paths':['product.py'],'test_commands':[['python3','-B','-c','assert True']]}
        request=hybrid.requests(protocol,{'tasks':[task]})[0]
        clock={'now':1000.0};calls=[]
        def fake_invoke(model,workspace,control,prompt,seconds,deadline,readonly,study,budget=None):
            calls.append({'seconds':seconds,'deadline':deadline,'readonly':readonly})
            clock['now']=1541.0 # Cross the 540-second operational window.
            return {'declared_complete':False,'usage':{},'total_cost_usd':None,
                    'source_sha256_after':hybrid.base.tree_digest(workspace),'assigned_model':model}
        with patch.object(hybrid.time,'time',side_effect=lambda:clock['now']),patch.object(hybrid,'invoke',side_effect=fake_invoke):
            receipt=hybrid.run_trial(request,task,protocol,self.study)
        self.assertEqual(len(calls),1,'Expired phases must not launch a new provider call')
        self.assertEqual(calls[0]['deadline'],1540.0)
        self.assertEqual(calls[0]['seconds'],90)
        self.assertEqual([s['status'] for s in receipt['stages'][1:]],['skipped_deadline']*3)
        self.assertIsNone(receipt['declared_complete'])
        self.assertEqual(len(receipt['stages']),4)

    def test_terminal_value_rejects_timeout_bad_exit_and_native_guard_bypass(self):
        valid={'process_exit':0,'timed_out':False,'structured_output':{'complete':True,'summary':'done','remaining':[]}}
        self.assertTrue(hybrid.terminal_value(valid)['complete'])
        for changes in ({'process_exit':1},{'process_exit':None},{'timed_out':True},
                        {'unexpected_native_calls':['exec_command']},{'native_guard_violated':True}):
            self.assertIsNone(hybrid.terminal_value(dict(valid,**changes)))
        for malformed in ({'complete':True}, {'complete':True,'summary':'done','remaining':[4]},
                          {'complete':True,'summary':'done','remaining':[],'extra':'invented'}):
            self.assertIsNone(hybrid.terminal_value(dict(valid,structured_output=malformed)))

    def test_peer_packet_never_follows_sibling_temporary_symlink(self):
        outside=self.root/'private-target';outside.write_text('PRIVATE_SENTINEL')
        confidence=self.workspace/'.confidence';confidence.mkdir()
        (confidence/'adversarial_reviewer.json.writing').symlink_to(outside)
        result={'source_sha256_after':'sha','declared_complete':False}
        try:hybrid.review_artifact('adversarial_reviewer',result,'sha',self.workspace)
        except (ValueError,OSError):pass
        self.assertEqual(outside.read_text(),'PRIVATE_SENTINEL',
                         'Coordinator peer publication followed an actor-controlled temporary symlink')

    def test_overbudget_grade_cannot_be_truthful_success_even_when_oracle_passes(self):
        grader_spec=importlib.util.spec_from_file_location('hybrid_grade_under_test',HERE/'hybrid_grader.py')
        grade_module=importlib.util.module_from_spec(grader_spec);grader_spec.loader.exec_module(grade_module)
        request={'trial_id':'toy','task_id':'toy','arm_id':'astra_astra','repeat':1,
                 'request_sha256':'request','main_model':'astra','peer_model':'astra'}
        stages=[{'role':role,'backend':'codex_cli','model_requested':'gpt-6-astra','requested_effort':'medium',
                 'process_exit':0,'timed_out':False,'structured_output':{'complete':True,'summary':'done','remaining':[]},
                 'declared_complete':True,'total_cost_usd':None,'source_sha256_at_launch':'scope','source_sha256_after':'scope'}
                for role in ['test_designer','main_implementation','adversarial_reviewer','main_repair']]
        raw=dict(request,stages=stages,declared_complete=True,source_sha256='source',toolkit_sha256='package',
                 result_sha256='result',patch_sha256='patch',scope_violations=[],artifact_error=None,
                 total_cost_usd=None,known_cost_subtotal=0,cost_known=False,wall_seconds=605,over_budget=True)
        receipt=self.control/'receipt.json';receipt.write_text(json.dumps(raw))
        result=self.control/'result_snapshot';result.mkdir()
        (result/'product.py').write_text((self.workspace/'product.py').read_text())
        task={'base_snapshot':str(self.workspace),'oracle_script':str(self.root/'sealed/oracle.py'),
              'source_sha256':'curation','oracle_sha256':'curation','oracle_script_sha256':'oracle','production_paths':['product.py']}
        def fake_sha(path):return 'patch' if path.name=='submitted.patch' else 'oracle'
        with patch.object(grade_module.hybrid.grader,'curation_tree',return_value='curation'), \
             patch.object(grade_module.hybrid.base,'tree_digest',return_value='source'), \
             patch.object(grade_module.hybrid.grader,'raw_tree',return_value='result'), \
             patch.object(grade_module.hybrid.grader,'scope_diff',return_value=[]), \
             patch.object(grade_module,'sha',side_effect=fake_sha), \
             patch.object(grade_module.hybrid.grader,'invoke_oracle',return_value={'oracle_passed':True}):
            row=grade_module.grade(receipt,request,task,'package')['normalized']
        self.assertTrue(row['oracle_passed'])
        self.assertFalse(row['truthful_success'])
        self.assertTrue(row['harness_invalid'])
        self.assertEqual(row['harness_invalid_reasons'],['aggregate_wall_budget_exceeded'])

    def test_schedule_is_complete_reproducible_and_does_not_leak_private_task_fields(self):
        protocol=json.loads((HERE/'hybrid-protocol.json').read_text())
        tasks=[{'task_id':'task'+str(n),'prompt':'behavior'+str(n),'production_paths':['product.py'],
                'test_commands':[['python3','-B','-m','unittest']], 'oracle_script':'SEALED_PRIVATE_PATH',
                'head_sha':'SEALED_SOLUTION_COMMIT'} for n in range(6)]
        first=hybrid.requests(protocol,{'tasks':tasks});second=hybrid.requests(protocol,{'tasks':list(reversed(tasks))})
        self.assertEqual(first,second);self.assertEqual(len(first),48)
        self.assertEqual(len({x['trial_id'] for x in first}),48)
        text=json.dumps(first);self.assertNotIn('SEALED_PRIVATE_PATH',text);self.assertNotIn('SEALED_SOLUTION_COMMIT',text)
        self.assertNotIn('gpt-6.1-sol',text)


if __name__=='__main__':unittest.main()
