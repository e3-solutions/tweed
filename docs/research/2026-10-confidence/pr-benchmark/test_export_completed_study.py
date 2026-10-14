"""Closed schedule publication controls; no provider calls."""
import hashlib,importlib.util,json
from pathlib import Path
import tempfile,unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('completed_export_tests',HERE/'export_completed_study.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


class ClosedExportTests(unittest.TestCase):
    def write(self,path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.study=self.root/'study';self.out=self.root/'public';self.schedule=self.root/'schedule.json'
        self.rows=[];schedule=[]
        for repeat in (1,2,3):
            row=dict(trial_id='task--arm--r'+str(repeat),task_id='task',arm_id='arm',repeat=repeat,
                status='missing_receipt',passed=None,oracle_passed=None,declared_complete=None,
                total_cost_usd=None,known_cost_subtotal=None,wall_seconds=None,human_interventions=None,
                harness_invalid=None,proof_packet_grade=None,semantic_correctness_beyond_oracle=None)
            self.rows.append(row);schedule.append({k:row[k] for k in ('trial_id','task_id','arm_id','repeat')})
        row=self.rows[0];row.update(status='terminal_missing',passed=False,oracle_passed=False,
            false_completion=None,harness_invalid=False,known_cost_subtotal=0,
            tool_errors=[{'error_kind':'tool_input','error':'PRIVATE_ERROR /Users/private'}],
            completion_summary='PRIVATE_OUTPUT',remaining=['PRIVATE_GAP'],
            stage_usage=[{'role':'test_designer','backend':'claude_code','model_requested':'claude-opus-5-5',
                'usage':{'input_tokens':10,'output_tokens':4,'message':'PRIVATE_OUTPUT'},'total_cost_usd':None,
                'error':'PRIVATE_ERROR','summary':'PRIVATE_OUTPUT'}])
        self.trial=self.study/'trials'/row['trial_id'];self.trial.mkdir(parents=True)
        self.patch=b'diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n'
        row['patch_sha256']=hashlib.sha256(self.patch).hexdigest()
        (self.trial/'submitted.patch').write_bytes(self.patch)
        raw={'status':'terminal_missing','production_paths':['main.py'],'secret':'PRIVATE_RAW',
             'stages':[{'role':'test_designer','adapter_qualification':{'passed':False,'reason':'PRIVATE_REASON',
                'effective_tools':['StructuredOutput'],'local':{'passed':True,'actor_cwd':'/Users/private',
                 'config_argument':'/Users/private/config.json','readonly':True}}}]}
        self.write(self.trial/'receipt.json',raw)
        self.write(self.trial/'graded-receipt.json',{'normalized':row,'raw_receipt_sha256':e.sha(self.trial/'receipt.json')})
        self.write(self.study/'results-normalized.json',self.rows);self.write(self.schedule,schedule)
        self.write(self.study/'trials'/self.rows[1]['trial_id']/'test_designer/request.json',{'secret':'PRIVATE_REQUEST'})
        self.inventory=self.root/'inventory.json';self.closure=self.root/'closure.json';self.reseal()
    def tearDown(self):self.temp.cleanup()
    def reseal(self,**kwargs):
        for p in (self.inventory,self.closure):
            if p.exists():p.unlink()
        return e.seal(self.study,self.schedule,self.inventory,self.closure,'Stopped fixture with interrupted/unstarted assignments',**kwargs)
    def export(self,**kwargs):return e.export(self.study,self.schedule,self.out,closure_path=self.closure,**kwargs)
    def test_exact_full_schedule_unknowns_and_redaction(self):
        closure=self.export();text=(self.out/'results.json').read_text();rows=json.loads(text)
        self.assertNotIn('PRIVATE_',text);self.assertNotIn('/Users/',text)
        self.assertEqual(len(rows),3);self.assertEqual(closure['classification'],{'completed_receipt':1,'interrupted_no_receipt':1,'never_started':1})
        for r in rows[1:]:
            for key in ('passed','oracle_passed','total_cost_usd','declared_complete','human_interventions','policy_denial_count','scope_violation_count'):
                self.assertIsNone(r[key])
        self.assertEqual(rows[0]['stage_usage'][0]['usage'],{'input_tokens':10,'output_tokens':4})
        self.assertEqual((self.out/rows[0]['production_patch']).read_bytes(),self.patch)
        self.assertIsNone(json.loads((self.out/'artifact-hashes.json').read_text())[1]['raw_receipt_sha256'])
    def test_missing_requires_exact_closure_coverage(self):
        value=e.read(self.closure);value['missing_assignments'].pop();self.write(self.closure,value)
        with self.assertRaisesRegex(ValueError,'exactly every missing'):self.export()
    def test_missing_is_not_coerced_to_failure_or_zero(self):
        self.rows[1]['passed']=False;self.write(self.study/'results-normalized.json',self.rows)
        with self.assertRaisesRegex(ValueError,'retain unknown'):self.export()
    def test_missing_cost_zero_is_rejected(self):
        self.rows[1]['total_cost_usd']=0;self.write(self.study/'results-normalized.json',self.rows)
        with self.assertRaisesRegex(ValueError,'retain unknown'):self.export()
    def test_aggregate_must_equal_graded_normalized(self):
        self.rows[0]['passed']=True;self.write(self.study/'results-normalized.json',self.rows)
        with self.assertRaisesRegex(ValueError,'Aggregate differs'):self.export()
    def test_raw_grade_binding_required(self):
        raw=e.read(self.trial/'receipt.json');raw['status']='submitted';self.write(self.trial/'receipt.json',raw);self.reseal()
        with self.assertRaisesRegex(ValueError,'Grade/raw'):self.export()
    def test_postseal_new_provider_request_rejected(self):
        self.write(self.study/'trials'/self.rows[1]['trial_id']/'main_implementation/request.json',{})
        with self.assertRaisesRegex(ValueError,'gained or lost'):self.export()
    def test_schedule_denominator_change_rejected(self):
        value=e.read(self.schedule);value.pop();self.write(self.schedule,value)
        with self.assertRaises(ValueError):self.export()
    def test_patch_nonproduction_header_rejected_even_when_hash_bound(self):
        data=self.patch.replace(b'a/main.py b/main.py',b'a/.confidence/private b/.confidence/private')
        (self.trial/'submitted.patch').write_bytes(data);self.rows[0]['patch_sha256']=hashlib.sha256(data).hexdigest()
        graded=e.read(self.trial/'graded-receipt.json');graded['normalized']=self.rows[0];self.write(self.trial/'graded-receipt.json',graded)
        self.write(self.study/'results-normalized.json',self.rows);self.reseal()
        with self.assertRaisesRegex(ValueError,'Nonproduction'):self.export()
    def test_host_path_in_patch_refuses_export(self):
        data=self.patch+b'+location="/Users/private/file"\n';(self.trial/'submitted.patch').write_bytes(data)
        self.rows[0]['patch_sha256']=hashlib.sha256(data).hexdigest()
        graded=e.read(self.trial/'graded-receipt.json');graded['normalized']=self.rows[0];self.write(self.trial/'graded-receipt.json',graded)
        self.write(self.study/'results-normalized.json',self.rows);self.reseal()
        with self.assertRaisesRegex(ValueError,'Host path'):self.export()
    def test_symlink_evidence_rejected(self):
        p=self.trial/'submitted.patch';p.unlink();outside=self.root/'external';outside.write_bytes(self.patch);p.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'regular evidence'):self.export()
    def test_supplement_is_separate_and_free_text_is_redacted(self):
        supplement={'schema_version':1,'schedule_sha256':e.sha(self.schedule),'assignments':3,'rows':[],
          'astra_errors':{'PermissionError: PRIVATE /Users/private':2}}
        for row in self.rows:
            observed=row['status']!='missing_receipt'
            item={k:row[k] for k in ('trial_id','task_id','arm_id','repeat')}
            item.update(raw_receipt_sha256=e.sha(self.trial/'receipt.json') if observed else None,
                        graded_receipt_sha256=e.sha(self.trial/'graded-receipt.json') if observed else None,
                        stage_qualifications=[{'role':'test_designer','error':'PermissionError: PRIVATE /Users/private',
                            'qualification':{'passed':False,'reason':'PRIVATE'}}])
            supplement['rows'].append(item)
        path=self.root/'supplement.json';self.write(path,supplement);self.export(supplement_path=path)
        text=(self.out/'retrospective-inventory-supplement.json').read_text();self.assertNotIn('PRIVATE',text)
        self.assertEqual(json.loads(text)['astra_error_classes'],{'PermissionError':2})
        self.assertFalse(json.loads((self.out/'results.json').read_text())[0]['harness_invalid'])

    def test_explicit_v2_grading_filename_works_and_is_pinned(self):
        old=self.trial/'graded-receipt.json';new=self.trial/'v2-graded-receipt.json';new.write_bytes(old.read_bytes())
        # Both filenames exist, but the caller and closure select V2 explicitly.
        self.reseal(graded_filename='v2-graded-receipt.json')
        value=self.export(graded_filename='v2-graded-receipt.json')
        self.assertEqual(value['grading_receipt_filename'],'v2-graded-receipt.json')
        with self.assertRaisesRegex(ValueError,'filename mismatch'):self.export()
    def test_unsupported_grading_filename_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.export(graded_filename='../private')
    def test_completion_audit_is_bound_and_revalidated(self):
        audit=self.root/'audit.json';self.write(audit,{'passed':True,'violations':[]})
        self.reseal(completion_evidence=audit)
        value=self.export();self.assertEqual(value['completion_evidence_sha256'],e.sha(audit))
        self.write(audit,{'passed':False,'violations':['changed']})
        with self.assertRaisesRegex(ValueError,'Completion audit'):self.export()

class V2QualificationProjectionTests(unittest.TestCase):
    def test_hashes_unknown_inventory_and_extra_resources_are_preserved(self):
        digest='a'*64
        raw={'passed':None,'basis':'live_claude_init','reason':'PRIVATE_REASON',
            'local':{'passed':True,'stdout_sha256':digest,'stderr_sha256':digest,
                     'actor_cwd':'/Users/private','config_argument':'/Users/private/config.json'},
            'additional_resource_handlers':['functions.list_mcp_resources','functions.read_mcp_resource'],
            'live_wire_inventory_observed':False,'strict_seven_tool_parity':False}
        value=e.qualification(raw)
        self.assertIsNone(value['passed']);self.assertEqual(value['local']['stdout_sha256'],digest)
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertNotIn('/Users',json.dumps(value))
        self.assertFalse(value['strict_seven_tool_parity']);self.assertEqual(len(value['additional_resource_handlers']),2)
    def test_full_normalized_qualification_source_lifecycle_known_and_unknown(self):
        digest='b'*64
        check={'passed':False,'skipped':False,'provider':'astra','role':'main_repair',
            'reasons':['lifecycle_metadata_unqualified'],
            'local_transport':{'passed':True,'readonly':False,'stdout_sha256':digest,'actor_cwd':'/Users/private'},
            'recorded_qualification':{'passed':None,'basis':'offline_declared_codex_inventory_and_local_pipeline',
                'live_wire_inventory_observed':False,'additional_resource_handlers':['functions.list_mcp_resources']},
            'source_binding':{'at_launch':digest,'after':None,'private_path':'/Users/private'},
            'lifecycle':{'timed_out':None,'process_exit':0,'process_cleanup_scope':'original_process_group',
                'guarded_new_session_processes':1,'stream_changed_during_cleanup':None,'process_cleanup_seconds':None,
                'error':'PRIVATE_OUTPUT'}}
        row={'stage_qualification':[check],'stage_usage':[{'adapter_qualification':check}]}
        value=e.project(row);q=value['stage_qualification'][0]
        self.assertIsNone(q['recorded_qualification']['passed']);self.assertIsNone(q['lifecycle']['timed_out'])
        self.assertIsNone(q['source_binding']['after']);self.assertEqual(q['source_binding']['at_launch'],digest)
        self.assertEqual(q['lifecycle']['process_exit'],0);self.assertFalse(q['passed'])
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertNotIn('/Users',json.dumps(value))
        self.assertEqual(value['stage_usage'][0]['adapter_qualification'],q)
    def test_missing_normalized_qualification_stays_null(self):
        value=e.project({'stage_qualification':None,'source_binding':None,'lifecycle':None})
        self.assertIsNone(value['stage_qualification']);self.assertIsNone(value['source_binding']);self.assertIsNone(value['lifecycle'])
    def test_invalid_source_digest_text_is_redacted_without_fake_validity(self):
        value=e.source_binding_projection({'at_launch':'PRIVATE /Users/person','after':None})
        self.assertIsNone(value['at_launch']);self.assertTrue(value['at_launch_invalid_redacted'])
        self.assertIsNone(value['after']);self.assertNotIn('after_invalid_redacted',value)
        self.assertNotIn('PRIVATE',json.dumps(value))
    def test_unclassified_error_text_cannot_be_exported_as_error_class(self):
        self.assertEqual(e.error_class('PRIVATE_REASON /Users/person'), 'unclassified_error')
    def test_malformed_qualification_hash_is_rejected(self):
        with self.assertRaises(ValueError):e.qualification({'stdout_sha256':'PRIVATE'})

if __name__=='__main__':unittest.main()
