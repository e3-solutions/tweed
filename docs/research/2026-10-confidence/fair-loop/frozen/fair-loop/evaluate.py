"""Frozen owner product evaluator: no provider/self-claim completion grading."""
import argparse,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'.git').exists())
def load(path):
 s=importlib.util.spec_from_file_location('fair_grader_'+hashlib.sha256(str(path).encode()).hexdigest()[:8],path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load(ROOT/'docs/research/2026-10-confidence/pr-benchmark/grading_adapter.py')
O=load(ROOT/'docs/research/2026-10-confidence/pr-benchmark/tasks/oracle_runner.py')
ENTRY='''import hashlib,importlib.util,inspect,json,os,sys,unittest
from pathlib import Path
root=Path.cwd();name=os.environ['PRODUCT_MODULE'];path=root/(name+'.py');before=hashlib.sha256(path.read_bytes()).hexdigest()
s=importlib.util.spec_from_file_location('product_under_test',path);M=importlib.util.module_from_spec(s);sys.modules[s.name]=M
source_load_error=None
try:s.loader.exec_module(M)
except SyntaxError as exc:
 if not Path(exc.filename).resolve().is_relative_to(root.resolve()):raise
 source_load_error={'kind':'SyntaxError','message':exc.msg,'line':exc.lineno}
errors=[]
if Path(M.__file__).resolve()!=path.resolve() or Path(M.__spec__.origin).resolve()!=path.resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=before:errors.append('Loaded module path/hash differs from actor-local source')
forbidden={str(Path(p).resolve()) for p in json.loads(os.environ['FORBIDDEN_RUNTIME'])}
public={'csv':{'DictReader':['__init__','__next__'],'DictWriter':['__init__','writerow','writeheader']},'configparser':{'ConfigParser':['read_file','read_string','get','write']}}[name]
for api,methods in public.items():
 value=getattr(M,api,None)
 if value is None:continue
 for candidate in [value]+[getattr(value,method,None) for method in methods]:
  code=getattr(candidate,'__code__',None)
  if code and not Path(code.co_filename).resolve().is_relative_to(root.resolve()):errors.append('Tested Python API code origin is outside projected local implementation: '+api)
print(json.dumps({'local_module':str(path),'local_module_sha256':before,'binding_errors':errors,'source_load_error':source_load_error}))
if errors or source_load_error:print(json.dumps({'failed':['actor-source-load' if source_load_error else 'local-module-binding'],'run':0,'skipped':0}));raise SystemExit(1)
ids=json.loads(os.environ['OWNER_IDS']);suite=unittest.defaultTestLoader.loadTestsFromNames(ids);result=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'failed':[getattr(case,'test_case',case).id() for case,_ in result.failures+result.errors],'run':result.testsRun,'skipped':len(result.skipped)}))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped and result.testsRun==len(ids) else 1)
'''
def execute(argv,root,env,seconds=8):
 start=time.monotonic();p=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True);timeout=False
 try:out,err=p.communicate(timeout=seconds)
 except subprocess.TimeoutExpired:
  timeout=True;os.killpg(p.pid,signal.SIGTERM)
  try:out,err=p.communicate(timeout=.25)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
 return {'exit_code':124 if timeout else p.returncode,'timed_out':timeout,'stdout':out,'stderr':err,'wall_seconds':time.monotonic()-start,'process_cleanup_scope':'original_process_group','detached_descendants_contained':False}
def scoped(base,candidate,production):
 before={p.relative_to(base).as_posix():p.read_bytes() for p in A.files(base)};after={p.relative_to(candidate).as_posix():p.read_bytes() for p in A.files(candidate,A.IGNORED)};violations=[]
 for name in sorted(set(before)|set(after)):
  if before.get(name)==after.get(name):continue
  parts=Path(name).parts
  if parts[0] in ('.protocol','.confidence','.trial-tmp','.git') or 'tests' in parts or 'test' in parts or name.startswith('test_') or (Path(name).suffix=='.py' and (Path(name).name.startswith('test_') or Path(name).name.endswith('_test.py') or Path(name).name=='conftest.py')):continue
  if name in production or (len(parts)==1 and name.endswith('.py') and name not in before and name[:-3] not in sys.stdlib_module_names and name not in ('conftest.py','sitecustomize.py','usercustomize.py')):continue
  if name=='AGENTS.md':continue
  if name=='.gitignore' and after.get(name)==before.get(name,b'')+b'\n.trial-tmp/\n.confidence/\n':continue
  violations.append(name)
 return violations
def evaluate(workspace,task_id):
 task=next(t for t in json.loads((HERE/'TASKS.json').read_text())['tasks'] if t['task_id']==task_id);candidate=Path(workspace).resolve();base=Path(task['base_snapshot']);before=A.raw_tree(candidate);scope=scoped(base,candidate,task['production_paths'])
 with tempfile.TemporaryDirectory(prefix='fair-owner-') as name:
  outer=Path(name).resolve();root=outer/'source';scratch=outer/'scratch';scratch.mkdir();O.copy_candidate(base,candidate,root,task['production_paths'])
  shutil.copyfile(HERE/task['private_module'],root/'tests/test_owner.py');entry=root/'_sealed_grading_entry.py';entry.write_text(ENTRY);projected_before=A.raw_tree(root)
  env=A.clean_env();env.update(HOME=str(scratch),TMPDIR=str(scratch),PRODUCT_MODULE=task['module'],OWNER_IDS=json.dumps(task['oracle_tests']),FORBIDDEN_RUNTIME=json.dumps(task['forbidden_runtime_read_paths']))
  profile=O.sandbox_profile(root,scratch,entry)+'\n(allow file-read* '+ ' '.join('(literal '+json.dumps(str(p))+')' for q in task['runtime_read_paths'] for p in O.ancestors(Path(q)))+')'+'\n(allow file-read* '+ ' '.join('(subpath '+json.dumps(p)+')' for p in task['runtime_read_paths'])+')'+'\n(deny file-read* '+' '.join('(literal '+json.dumps(p)+')' for p in task['forbidden_runtime_read_paths'])+')'
  prefix=['/usr/bin/sandbox-exec','-p',profile];owner=execute(prefix+[task['interpreter'],'-B',str(entry)],root,env);baseline=[]
  for command in task['visible_commands']:baseline.append({'argv':command,**execute(prefix+command,root,env)})
  projected_current=projected_before==A.raw_tree(root)
 after=A.raw_tree(candidate);current=before==after and projected_current
 try:meta=json.loads(owner['stdout'].splitlines()[0]);outcome=json.loads(owner['stdout'].splitlines()[-1])
 except (ValueError,IndexError):meta={};outcome={}
 bound=meta.get('binding_errors')==[];source_rejected=bool(meta.get('binding_errors')) or bool(meta.get('source_load_error'));ran=outcome.get('run')==len(task['oracle_tests']) and outcome.get('skipped')==0
 observed=((bound and ran) or source_rejected) and not owner['timed_out'] and all(not b['timed_out'] for b in baseline);failed=outcome.get('failed',[])
 positive=observed and ran and not any(t in failed for t in task['positive_tests']);negative=observed and ran and not any(t in failed for t in task['negative_tests']);regression=observed and ran and not any(t in failed for t in task['regression_tests']) and all(b['exit_code']==0 for b in baseline)
 gaps=[]
 for ident,passed,claim in [('positive',positive,'Configured requested behavior'),('negative',negative,'Required invalid/neighboring boundaries'),('regression',regression,'Preserved existing public behavior')]:
  if observed and ran and not passed:gaps.append({'id':ident,'claim':claim,'observed':[t for t in failed if t in task[ident+'_tests']] if ident!='regression' else [t for t in failed if t in task['regression_tests']]+['visible-command:'+str(b['argv']) for b in baseline if b['exit_code']!=0],'expected':'All registered cases pass'})
 if observed and meta.get('binding_errors'):gaps.append({'id':'local-module-binding','claim':'Check the actual actor-local implementation','observed':meta['binding_errors'],'expected':'Exact local module path/hash and local tested Python API origins'})
 if observed and meta.get('source_load_error'):gaps.append({'id':'source-load','claim':'Actor-local implementation loads','observed':meta['source_load_error'],'expected':'Local module compiles and loads before required public API checks'})
 if scope:gaps.append({'id':'scope','claim':'Declared production scope','observed':scope,'expected':[]})
 if not current:gaps.append({'id':'current-proof','claim':'Current source during independent execution','observed':'Source drift','expected':'Stable source hashes'})
 passed=observed and positive and negative and regression and not scope and current
 header={'task_id':task_id,'product_passed':passed,'positive_passed':positive,'negative_passed':negative,'regression_passed':regression,'scope_valid':not scope,'scope_violations':scope,'source_current':current,'evaluation_status':'observed' if observed else 'unknown','local_module_binding':meta,'failed_requirements':gaps,'execution_receipts':{'owner':owner,'baseline':baseline},'source_before_sha256':before,'source_after_sha256':after,'owner_stdout_sha256':hashlib.sha256(owner['stdout'].encode()).hexdigest(),'owner_stderr_sha256':hashlib.sha256(owner['stderr'].encode()).hexdigest()}
 print(json.dumps(header));return 0 if passed else 1 if observed else 2
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--task-id',required=True)
 try:raise SystemExit(evaluate(**vars(p.parse_args())))
 except (OSError,ValueError,StopIteration) as e:print(json.dumps({'product_passed':False,'evaluation_status':'unknown','infrastructure_error':str(e)}));raise SystemExit(2)
