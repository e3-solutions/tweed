"""Frozen owner behavior evaluator; no model calls or policy-ledger requirement."""
import argparse,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('prior_adapter',REPO/'docs/research/2026-10-confidence/pr-benchmark/grading_adapter.py')
O=load('prior_sandbox',REPO/'docs/research/2026-10-confidence/pr-benchmark/tasks/oracle_runner.py')
ENTRY='''import json,unittest
ids=json.loads(__import__('os').environ['OWNER_IDS'])
suite=unittest.defaultTestLoader.loadTestsFromNames(ids)
result=unittest.TextTestRunner(verbosity=2).run(suite)
failed=[case.id() for case,_ in result.failures+result.errors]
print(json.dumps({'failed':failed,'skipped':len(result.skipped),'run':result.testsRun}))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped and result.testsRun==len(ids) else 1)
'''
def bounded(argv,cwd,env,timeout=5):
 start=time.monotonic();process=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 timed_out=False
 try:stdout,stderr=process.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  timed_out=True;os.killpg(process.pid,signal.SIGTERM)
  try:stdout,stderr=process.communicate(timeout=0.25)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate()
 return {'exit_code':124 if timed_out else process.returncode,'timed_out':timed_out,'stdout':stdout,'stderr':stderr,'wall_seconds':time.monotonic()-start,'process_cleanup_scope':'original_process_group','detached_descendants_contained':False}
def evaluate(workspace,task_id):
 tasks=json.loads((HERE/'TASKS.json').read_text())['tasks'];task=next(t for t in tasks if t['task_id']==task_id)
 candidate=Path(workspace).resolve();before=A.raw_tree(candidate)
 baseline=Path(task['base_snapshot'])
 scope=A.scope_diff(baseline,candidate,task['production_paths'])
 for original in A.files(baseline):
  relative=original.relative_to(baseline)
  if 'tests' not in relative.parts:continue
  submitted=candidate/relative
  if not submitted.is_file() or submitted.is_symlink() or submitted.read_bytes()!=original.read_bytes() or (submitted.stat().st_mode&0o777)!=(original.stat().st_mode&0o777):scope.append(relative.as_posix())
 scope=sorted(set(scope))
 with tempfile.TemporaryDirectory(prefix='fork-owner-') as tmp:
  outer=Path(tmp).resolve();root=outer/'source';scratch=outer/'scratch';scratch.mkdir()
  O.copy_candidate(Path(task['base_snapshot']),candidate,root,task['production_paths'])
  tests=root/'tests';tests.mkdir(exist_ok=True);(tests/'__init__.py').touch()
  shutil.copyfile(HERE/task['private_module'],tests/'test_fork_owner.py')
  entry=root/'_sealed_grading_entry.py';entry.write_text(ENTRY)
  projected_before=A.raw_tree(root)
  env=A.clean_env();env.update(HOME=str(scratch),TMPDIR=str(scratch),OWNER_IDS=json.dumps(task['oracle_tests']))
  argv=['/usr/bin/sandbox-exec','-p',O.sandbox_profile(root,scratch,entry),sys.executable,'-B',str(entry)]
  r=bounded(argv,root,env);code=r['exit_code'];output=r['stdout']+r['stderr']
  baselines=[]
  for command in task['visible_commands']:
   result=bounded(argv[:-3]+[sys.executable,'-B',*command[2:]],root,env)
   baselines.append({'argv':command,**result})
  output+=''.join('\nFocused baseline: '+json.dumps(b['argv'])+'\n'+b['stdout']+b['stderr'] for b in baselines)
  projected_after=A.raw_tree(root)
 after=A.raw_tree(candidate);current=before==after and projected_before==projected_after
 try:receipt=json.loads(r['stdout'].splitlines()[-1]) if code!=124 else None
 except (ValueError,IndexError):receipt=None
 setup='verified' if receipt and receipt['run']==len(task['oracle_tests']) and not receipt['skipped'] else 'unknown'
 failed=receipt['failed'] if receipt else []
 baseline_passed=all(b['exit_code']==0 and not b['timed_out'] for b in baselines)
 if any(b['timed_out'] for b in baselines):setup='unknown'
 positive=setup=='verified' and not any(x in failed for x in task['positive_tests'])
 negative=setup=='verified' and not any(x in failed for x in task['negative_tests'])
 failures=([{'requirement':'behavior','failed_tests':[x for x in failed if x in task['positive_tests']]}] if not positive else [])+([{'requirement':'negative-boundaries','failed_tests':[x for x in failed if x in task['negative_tests']]}] if not negative else [])
 if not baseline_passed:failures.append({'requirement':'baseline-regression','commands':[b['argv'] for b in baselines if b['exit_code']!=0]})
 if scope:failures.append({'requirement':'scope','paths':scope})
 if not current:failures.append({'requirement':'current-proof'})
 passed=code==0 and positive and negative and baseline_passed and not scope and current and setup=='verified'
 header={'task_id':task_id,'exit_code':code,'passed':passed,'oracle_passed':code==0,'required_behavior_passed':positive,'negative_boundaries_passed':negative,'baseline_passed':baseline_passed,'baseline_receipts':baselines,'scope_violations':scope,'source_current':current,'setup_status':setup,'failed_requirements':failures,'source_before_sha256':before,'source_after_sha256':after,'output_sha256':hashlib.sha256(output.encode()).hexdigest()}
 print(json.dumps(header));print(output);return 0 if passed else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--task-id',required=True)
 try:raise SystemExit(evaluate(**vars(p.parse_args())))
 except (OSError,ValueError,StopIteration) as e:print(json.dumps({'passed':False,'setup_status':'unknown','infrastructure_error':str(e)}));raise SystemExit(2)
