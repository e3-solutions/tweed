"""Narrow prospective path control; no models or owner behavioral reruns."""
import hashlib,importlib.util,json,shutil,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=load(HERE/'before-evaluate.py','before_scope');new=load(PARENT/'evaluate.py','current_scope');tasks=json.loads((PARENT/'TASKS.json').read_text())['tasks'];task=tasks[0];base=Path(task['reference_snapshot'])
allowed=['package/test_api.py','package/api_test.py','package/conftest.py','conftest.py'];unauthorized='package/implementation.py'
with tempfile.TemporaryDirectory(prefix='fair-scope-control-') as d:
 candidate=Path(d).resolve()/'candidate';shutil.copytree(base,candidate)
 for name in allowed:
  p=candidate/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('raise RuntimeError("Actor-only conventional test fixture; never owner code")\n')
 old_result=old.scoped(base,candidate,task['production_paths']);new_result=new.scoped(base,candidate,task['production_paths'])
 assert old_result==sorted(allowed) and new_result==[]
 projected=Path(d).resolve()/'projected';new.O.copy_candidate(base,candidate,projected,task['production_paths'])
 assert all(not (projected/name).exists() for name in allowed)
 assert (projected/(task['module']+'.py')).read_bytes()==(base/(task['module']+'.py')).read_bytes()
 p=candidate/unauthorized;p.write_text('# Unapproved nested production change\n');negative=new.scoped(base,candidate,task['production_paths']);assert negative==[unauthorized]
receipt={'passed':True,'model_calls':0,'behavioral_oracle_reruns':0,'transport_reruns':0,'before_evaluator_sha256':hashlib.sha256((HERE/'before-evaluate.py').read_bytes()).hexdigest(),'after_evaluator_sha256':hashlib.sha256((PARENT/'evaluate.py').read_bytes()).hexdigest(),'allowed_paths':allowed,'old_scope_violations':old_result,'new_scope_violations':new_result,'actor_tests_copied_into_owner_projection':False,'projected_primary_module_unchanged':True,'unauthorized_nested_production_still_rejected':negative,'task_manifest_unchanged_sha256':hashlib.sha256((PARENT/'TASKS.json').read_bytes()).hexdigest(),'phase':'Pre-inference contract correction; no task outcomes known'}
(HERE/'CONTROL.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'passed':True,'after_evaluator_sha256':receipt['after_evaluator_sha256']}))
