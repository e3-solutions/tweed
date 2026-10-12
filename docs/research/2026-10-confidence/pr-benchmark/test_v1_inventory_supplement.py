"""Supplement keeps unknowns and original frozen receipts, no inference."""
import importlib.util,json
from pathlib import Path
import tempfile,unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v1_inventory_tests',HERE/'v1_inventory_supplement.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
        self.write=write
        requests=[dict(trial_id='t'+str(i),task_id='task',arm_id='arm',repeat=i,main_model='astra',peer_model='opus') for i in (1,2,3)]
        write(self.root/'requests.json',requests);write(self.root/'schedule.json',requests)
        write(self.root/'registration.json',{'files':{str(self.root/'schedule.json'):audit.sha(self.root/'schedule.json')}})
        stage={'role':'test_designer','assigned_model':'opus','model_requested':'claude-opus-5-5',
            'observed_assistant_models':['claude-opus-5-5'],'total_cost_usd':None,'usage':None,
            'harness_initialization':{'tools':['StructuredOutput'],'mcp_servers':[{'name':'cp_trial','status':'failed'}]}}
        self.raw=self.root/'trials/t1/receipt.json';write(self.raw,{'stages':[stage]})
        self.graded=self.raw.with_name('graded-receipt.json');write(self.graded,{'raw_receipt_sha256':audit.sha(self.raw),
            'adapter_sha256':audit.sha(HERE/'hybrid_grader.py'),'normalized':{'truthful_success':True,'harness_invalid':False,'total_cost_usd':None}})
        write(self.root/'trials/t2/test_designer/request.json',{})
    def tearDown(self):self.temp.cleanup()
    def test_counts_missing_unknown_cost_and_supplement_dont_rewrite_primary(self):
        before=[audit.sha(self.raw),audit.sha(self.graded)]
        result=audit.supplement(self.root)
        self.assertEqual(result['assignment_counts'],{'completed_receipt':1,'interrupted_before_receipt':1,'never_started':1})
        self.assertEqual(result['independently_graded_observed'],1)
        self.assertEqual(result['supplemental_verified_success_count'],0)
        self.assertIsNone(result['rows'][0]['registered_primary']['total_cost_usd'])
        self.assertTrue(result['rows'][0]['registered_primary']['truthful_success'])
        self.assertTrue(result['rows'][0]['supplemental_harness_invalid'])
        self.assertIsNone(result['rows'][1]['supplemental_harness_invalid'])
        self.assertIsNone(result['rows'][2]['registered_primary'])
        self.assertEqual(before,[audit.sha(self.raw),audit.sha(self.graded)])
    def test_ungraded_observed_receipt_is_rejected(self):
        self.graded.unlink()
        with self.assertRaisesRegex(ValueError,'not independently graded'):audit.supplement(self.root)
    def test_raw_modified_after_grade_is_rejected(self):
        self.write(self.raw,{'stages':[]})
        with self.assertRaisesRegex(ValueError,'no longer binds'):audit.supplement(self.root)

if __name__=='__main__':unittest.main()
