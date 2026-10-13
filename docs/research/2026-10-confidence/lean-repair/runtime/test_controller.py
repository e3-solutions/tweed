"""Focused CPU/simulated state controls; these are not hosted model outcomes."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import controller as c
import discovery as d


def stage(summary='done',role='main'):
    return {'backend':'claude','terminal':{'type':'result','subtype':'success','is_error':False,'structured_output':{'complete':True,'summary':summary,'remaining':[]}},'qualification':{'eligible':True,'failures':[]},'timed_out':False,'process_exit':0}

def good():
    return {'status':'completed','main':stage(),'closure':stage(),'first':{'scope_violations':[]},'final':{'scope_violations':[]},'review_qualified':True,'final_grade':{'oracle_passed':True},'final_binding_valid':True,'final_checks_passed':True,'unresolved_findings':[]}

class Controls(unittest.TestCase):
    def test_roster_no_retry_and_stage_cap(self):
        tasks=[{'task_id':f'task-{i}'} for i in range(3)]
        roster=[{'task_id':t['task_id'],'arm_id':arm,'repeat':1,'trial_id':t['task_id']+'--'+arm+'--r1'} for t in tasks for arm in ('original','revised')]
        c.validate_roster(roster,tasks)
        with self.assertRaises(ValueError):c.validate_roster(roster+[roster[0]],tasks)
        with tempfile.TemporaryDirectory() as temp:
            c.claim(Path(temp)/'stage','once')
            with self.assertRaises(FileExistsError):c.claim(Path(temp)/'stage','twice')
        self.assertEqual(c.CAPS['closure'],(300,3))
        with self.assertRaises(ValueError):c.bounded_time(300,time.time()-1)

    def test_missing_review_or_wrong_source_cannot_succeed(self):
        receipt=good();self.assertTrue(c.accepted(receipt))
        for key in ('review_qualified','final_binding_valid','final_checks_passed'):
            changed=copy.deepcopy(receipt);changed[key]=False;self.assertFalse(c.accepted(changed))
        changed=copy.deepcopy(receipt);changed['final_grade']['oracle_passed']=False;self.assertFalse(c.accepted(changed))
        changed=copy.deepcopy(receipt);changed['unresolved_findings']=['gap'];self.assertFalse(c.accepted(changed))

    def test_main_timeout_only_bounded_provenance_recovery(self):
        receipt=good();receipt['main'].update(terminal=None,timed_out=True,process_exit=-15,qualification={'eligible':False,'failures':['stage_did_not_finish','terminal_missing_or_invalid']})
        self.assertTrue(c.accepted(receipt))
        receipt['main']['qualification']['failures'].append('exact_observed_model_mismatch_or_unknown');self.assertFalse(c.accepted(receipt))
        receipt['main']={};self.assertFalse(c.accepted(receipt))
        receipt['main']=stage();receipt['main']['qualification']={'eligible':False,'failures':['effective_inventory_unqualified']};self.assertFalse(c.accepted(receipt))
        receipt['main']=stage();receipt['closure']['qualification']={'eligible':False,'failures':['stage_did_not_finish']};self.assertFalse(c.accepted(receipt))

    def test_review_disagreement_and_witness_resolution(self):
        finding={'id':'bug','blocking':True,'witness':['python3','-c','raise SystemExit(1)']}
        failing={'id':'bug','exit_code':1,'timed_out':False,'source_unchanged':True,'passed':False}
        passing={'id':'bug','exit_code':0,'timed_out':False,'source_unchanged':True,'passed':True}
        self.assertEqual(c.unresolved_findings([finding],[failing],[passing]),[])
        self.assertEqual(c.unresolved_findings([finding],[passing],[passing]),['bug'])
        self.assertEqual(c.unresolved_findings([finding],[],[passing]),['bug'])
        self.assertEqual(c.unresolved_findings([{**finding,'witness':None}],[failing],[passing]),['bug'])
        receipt=good();receipt['unresolved_findings']=['bug'];self.assertFalse(c.accepted(receipt))

    def test_missing_actual_review_terminal(self):
        with self.assertRaises(ValueError):c.review_payload({'qualification':{'eligible':True},'backend':'codex','status':'completed'})
        bad=stage(json.dumps({'findings':[],'scope_limits':[]}));bad['terminal']['structured_output']['remaining']=['gap']
        with self.assertRaises(ValueError):c.review_payload(bad)

    def test_frozen_tests_scratch_and_missing_raw_command_artifacts(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();baseline=root/'base';baseline.mkdir();(baseline/'toy.py').write_text('VALUE = 1\n');(baseline/'test_fixed.py').write_text('from toy import VALUE; assert VALUE == 2\n')
            candidate=root/'candidate';c.runtime(c.DEV).frozen.base.safe_copy(baseline,candidate)
            (candidate/'test_fixed.py').write_text('pass\n');(candidate/'.trial-tmp').mkdir();(candidate/'.trial-tmp'/'witness.py').write_text('pass\n')
            task={'base_snapshot':str(baseline),'production_paths':['toy.py']};adapter=c.runtime(c.DEV)
            check={'id':'fixed','argv':['python3','-B','test_fixed.py'],'timeout_seconds':5}
            rows,source_sha=c.witnesses_execute(adapter,task,candidate,root/'checks',[check],time.time()+10)
            self.assertFalse(rows[0]['passed']);self.assertFalse((root/'checks'/'source'/'.trial-tmp'/'witness.py').exists())
            self.assertFalse(c.validate_checks(rows,root/'checks',[check],source_sha))
            self.assertFalse(c.witness_safe(['python3','.trial-tmp/witness.py']))
            fake={key:rows[0][key] for key in ('id','requested_argv','source_sha256','source_unchanged')};fake.update(exit_code=0,timed_out=False,passed=True)
            c.write(root/'checks'/'receipt.json',[fake]);c.write(root/'checks'/'check-0.command-response.json',{'exit_code':0,'timed_out':False})
            with self.assertRaisesRegex(ValueError,'process/output artifacts missing'):c.validate_checks([fake],root/'checks',[check],source_sha)

    def test_forced_cpu_failure_feedback_repair_final_grade(self):
        with tempfile.TemporaryDirectory() as name:
            temp=Path(name);base_source=temp/'base';base_source.mkdir();(base_source/'toy.py').write_text('VALUE = 1\n')
            task={'task_id':'new-toy','prompt':'Make VALUE=2','base_snapshot':str(base_source),'production_paths':['toy.py'],'test_commands':[['python3','-B','-c','from toy import VALUE; assert VALUE == 2']]}
            receipt_path=temp/'discovery.json';c.write(receipt_path,{'validated_facts':[]})
            config={'aggregate_seconds':1100,'toolkit_directory':str(base_source),'discovery_receipts':{'new-toy':str(receipt_path)}}
            study=temp/'study';study.mkdir();c.write(study/'registration.json',{})
            events=[];real_adapter=c.runtime(c.DEV)
            def invoke(adapter,workspace,directory,prompt,role,deadline,payload):
                c.claim(directory,role);events.append((role,prompt))
                before=real_adapter.frozen.base.tree_digest(workspace)
                if role=='closure':(workspace/'toy.py').write_text('VALUE = 2\n')
                if role=='review':
                    summary=json.dumps({'findings':[{'id':'value','blocking':True,'path':'toy.py','line':1,'claim':'wrong value','witness':task['test_commands'][0]}],'scope_limits':[]})
                else:summary='done'
                return {**stage(summary),'source_sha256_at_launch':before,'source_sha256_after':real_adapter.frozen.base.tree_digest(workspace)}
            def check(adapter,workspace,directory,commands,deadline):
                c.claim(directory,'checks');rows=[]
                for index,item in enumerate(commands):
                    item={'id':'visible-'+str(index),'argv':item} if isinstance(item,list) else item
                    proc=subprocess.run(item['argv'],cwd=workspace,capture_output=True,text=True,timeout=5)
                    rows.append({'id':item['id'],'exit_code':proc.returncode,'timed_out':False,'source_unchanged':True,'passed':proc.returncode==0,'output':proc.stdout,'error_output':proc.stderr})
                return rows
            def grade(adapter,task,source,directory,deadline):
                c.claim(directory,'grade');proc=subprocess.run(task['test_commands'][0],cwd=source,capture_output=True,text=True,timeout=5)
                (directory/'grader.stdout').write_text(proc.stdout);(directory/'grader.stderr').write_text(proc.stderr)
                return {'oracle_passed':proc.returncode==0,'source_sha256':real_adapter.frozen.base.tree_digest(source)}
            request={'trial_id':'new-toy--original--r1','task_id':'new-toy','arm_id':'original','repeat':1}
            with patch.object(c,'verify',return_value={}),patch.object(c.r,'mount',return_value=None),patch.object(c,'invoke',side_effect=invoke),patch.object(c,'execute',side_effect=check),patch.object(c,'grade',side_effect=grade):
                result=c.run_cell(request,task,{'policy_directory':str(base_source)},{'config':config},study)
            self.assertEqual([role for role,_ in events],['main','review','closure'])
            self.assertFalse(result['first_pass']);self.assertTrue(result['accepted']);self.assertTrue(result['actual_repair'])
            self.assertIn('AssertionError',events[-1][1]);self.assertEqual(result['unresolved_findings'],[])
            self.assertNotEqual(result['first']['patch_sha256'],result['final']['patch_sha256'])

if __name__=='__main__':unittest.main()
