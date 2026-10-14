#!/usr/bin/env python3
"""Read retained receipts and export typed public evidence; never rerun models/tests.

Provider thinking and ordinary assistant narrative are not exported. Private
stream digests bind source receipts; typed events keep init, tool requests/results,
and terminal/model/usage facts required to inspect the registered decision.
"""
import argparse
import difflib
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRIVATE=ROOT/'.confidence/fork-flush'
MODEL={'backend':'claude','model':'claude-opus-5-5','effort':'high'}
def load(path):
 spec=importlib.util.spec_from_file_location('public_evidence_'+hashlib.sha256(str(path).encode()).hexdigest()[:8],path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
R=load(ROOT/'docs/research/2026-10-confidence/claude-first-evaluation/runner.py')
ADAPTER=R.route(MODEL)
BASE=ADAPTER.frozen.base
ANALYZE=load(ROOT/'docs/research/2026-10-confidence/claude-first-evaluation/analyze.py')
GRADE=load(ROOT/'docs/research/2026-10-confidence/pr-benchmark/grading_adapter.py')
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(condition,reason):
 if not condition:raise ValueError(reason)
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def clean(value):
 if isinstance(value,list):return [clean(x) for x in value if not(isinstance(x,dict) and x.get('type') in ('thinking','redacted_thinking'))]
 if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('thinking','signature')}
 return value

def typed_stream(path):
 events=[];models=set();uses={};invalid=0;inits=[];terminals=[]
 for line in path.read_text().splitlines():
  try:event=json.loads(line)
  except ValueError:invalid+=1;continue
  kind=event.get('type')
  if kind=='system' and event.get('subtype')=='init':
   inits.append(event);events.append({'type':'system','subtype':'init',**{k:event[k] for k in ('session_id','model','tools','mcp_servers','permissionMode','claude_code_version','uuid') if k in event}})
  elif kind=='assistant':
   message=event.get('message',{});model=message.get('model')
   if isinstance(model,str):models.add(model)
   content=[clean(x) for x in message.get('content',[]) if isinstance(x,dict) and x.get('type')=='tool_use']
   if content:events.append({'type':'assistant','message':{k:message[k] for k in ('id','model','role','usage') if k in message}|{'content':content},**{k:event[k] for k in ('session_id','uuid') if k in event}})
   for tool in content:
    if not isinstance(tool.get('name'),str) or not tool['name'].startswith('mcp__cp_trial__'):continue
    ident=tool.get('id')
    if not isinstance(ident,str) or not ident:invalid+=1;continue
    if ident in uses and uses[ident]!=tool:invalid+=1
    uses[ident]=tool
  elif kind=='user':
   message=event.get('message',{});content=[clean(x) for x in message.get('content',[]) if isinstance(x,dict) and x.get('type')=='tool_result']
   if content:events.append({'type':'user','message':{'role':'user','content':content},**{k:event[k] for k in ('session_id','uuid','tool_use_result') if k in event}})
  elif kind=='result':
   terminals.append(event);events.append(clean(event))
 return {'events':events,'models':sorted(models),'requests':list(uses.values()),'mcp_request_count':len(uses) if not invalid else None,'invalid_stream_or_tool_ids':invalid,'inits':inits,'terminal':terminals[-1] if terminals else None}

def export_setup():
 target=HERE/'setup-handling';target.mkdir(exist_ok=True)
 archive=PRIVATE/'runtime-amendment-no-global-write'
 for path in archive.iterdir():
  if path.is_file():shutil.copy2(path,target/path.name)
 for name in ('AMENDMENT.json','UNUSED-PROPOSED-AMENDMENT.diff','UNUSED-PROPOSED-run_tasks.py'):
  shutil.copy2(PRIVATE/name,target/name)
 authoritative=read(PRIVATE/'AMENDMENT.json')
 require(sha(PRIVATE/'run_tasks.py')==authoritative['active_driver_sha256'],'Active driver not restored')
 require(sha(PRIVATE/'RUNTIME-PREFLIGHT.json')==authoritative['old_global_sha256'],'Global preflight not restored')
 require(sha(PRIVATE/'REGISTRATION.json')==authoritative['retained_artifacts']['root.REGISTRATION.before.json'],'Root registration changed')
 require(sha(PRIVATE/'selection/registration.json')==authoritative['retained_artifacts']['study.REGISTRATION.before.json'],'Study registration changed')
 write(target/'RESTORATION-VERIFIED.json',{'active_driver_sha256':sha(PRIVATE/'run_tasks.py'),'active_global_preflight_sha256':sha(PRIVATE/'RUNTIME-PREFLIGHT.json'),'root_registration_sha256':sha(PRIVATE/'REGISTRATION.json'),'study_registration_sha256':sha(PRIVATE/'selection/registration.json'),'proposed_change_unused':True,'source_preserved_before_task_inference':True})

def scope(base,result,production):
 findings=GRADE.scope_diff(base,result,production)
 for original in GRADE.files(base):
  rel=original.relative_to(base)
  if 'tests' not in rel.parts:continue
  candidate=result/rel
  if not candidate.is_file() or candidate.is_symlink() or candidate.read_bytes()!=original.read_bytes() or (candidate.stat().st_mode&0o777)!=(original.stat().st_mode&0o777):findings.append(rel.as_posix())
 return sorted(set(findings))

def analyze_stage(cell,role,task):
 control=cell/role;receipt_path=control/'receipt.json'
 if not receipt_path.exists():return None
 raw=read(receipt_path);public=HERE/'evidence'/cell.name/role;public.mkdir(parents=True,exist_ok=True)
 if raw.get('status')!='completed':
  write(public/'receipt.json',clean(raw));return {'role':role,'status':raw.get('status'),'stage_qualified':False,'evidence_current':False,'software_complete':None,'error':raw.get('error')}
 stage=raw['stage'];require(read(control/'stage.json')==stage,'Stage receipt mismatch')
 request=read(control/'call/request.json');facts=typed_stream(control/'call/stream.jsonl')
 require(sha(control/'call/stream.jsonl')==stage['stream_sha256'],'Stream binding changed')
 require(R.digest(request)==stage['request_sha256'],'Request binding changed')
 require(facts['terminal']==stage['terminal'],'Raw terminal changed')
 require(facts['models']==stage['observed_assistant_models'],'Raw model metadata differs')
 recorded_init=stage['harness_initialization'];actual_init=facts['inits'][0] if facts['inits'] else {}
 require(isinstance(recorded_init,dict) and all(recorded_init[k]==actual_init.get(k) for k in recorded_init),'Initialization metadata differs')
 require(request.get('model_requested')==MODEL['model'] and request.get('effort')=='high' and request['argv'][request['argv'].index('--effort')+1]=='high' and request['argv'][request['argv'].index('--model')+1]==MODEL['model'],'Assigned request route changed')
 for relative,expected in stage['artifacts'].items():require(sha(control/'call'/relative)==expected,'Retained provider/command artifact changed: '+relative)
 local=read(control/'qualification/local-qualification.json');qualification=R.qualification(stage,local,MODEL,ADAPTER)
 if stage.get('requested_effort')!='high':qualification['eligible']=False;qualification['failures'].append('requested_effort_mismatch')
 if not raw['protocol_context_unchanged']:qualification['eligible']=False;qualification['failures'].append('policy_or_common_toolkit_modified')
 require(qualification==stage['qualification'],'Recorded qualification differs from rederived rule')
 for side in ('before','after'):
  source=control/side/'source';snapshot=read(control/side/'receipt.json');require(snapshot==raw[side],'Snapshot receipt differs')
  require(BASE.tree_digest(source)==snapshot['source_sha256'],'Current retained source changed')
  with tempfile.TemporaryDirectory(prefix='fork-public-patch-') as tmp:
   patch,paths=ANALYZE.rebuild_patch(ADAPTER,Path(task['base_snapshot']),source,Path(tmp)/'patch',task['production_paths'])
  require(hashlib.sha256(patch).hexdigest()==snapshot['production_patch_sha256']==sha(control/side/'production.patch'),'Production patch changed')
  require(paths==snapshot['production_paths'],'Submitted production paths changed')
  shutil.copy2(control/side/'production.patch',public/(side+'-production.patch'))
  write(public/(side+'-source-identity.json'),snapshot)
 require(stage['source_sha256_at_launch']==raw['before']['source_sha256'] and stage['source_sha256_after']==raw['after']['source_sha256'],'Provider source association changed')
 evaluation=read(control/'evaluation/receipt.json');require(evaluation==raw['evaluation'],'Evaluation receipt differs')
 process=evaluation['process'];output=control/'evaluation/grader.stdout';error=control/'evaluation/grader.stderr'
 require(sha(output)==process['stdout_sha256'] and sha(error)==process['stderr_sha256'],'Owner output changed')
 header=json.loads(output.read_text().splitlines()[0]);require(header==evaluation['header'],'Owner header changed')
 require(header['source_before_sha256']==header['source_after_sha256']==BASE.tree_digest(control/'after/source'),'Owner source pin differs')
 derived_scope=scope(Path(task['base_snapshot']),control/'after/source',task['production_paths']);require(derived_scope==header['scope_violations'],'Scope verdict changed')
 scope_text=[]
 for name in derived_scope:
  old=Path(task['base_snapshot'])/name;new=control/'after/source'/name
  old_text=old.read_text(errors='replace').splitlines(keepends=True) if old.is_file() else []
  new_text=new.read_text(errors='replace').splitlines(keepends=True) if new.is_file() else []
  scope_text.extend(difflib.unified_diff(old_text,new_text,fromfile='base/'+name,tofile='candidate/'+name))
 (public/'scope.diff').write_text(''.join(scope_text))
 baseline_passed=all(b['exit_code']==0 and not b['timed_out'] for b in header['baseline_receipts']);require(baseline_passed==header['baseline_passed'],'Baseline gate differs')
 qualified_eval=not process['timed_out'] and evaluation['source_unchanged'] and header['source_current'] is True and header['setup_status']=='verified'
 require(bool(qualified_eval)==evaluation['qualified_evaluation'],'Evaluation qualification differs')
 software=bool(qualified_eval and header['required_behavior_passed'] and header['negative_boundaries_passed'] and baseline_passed and not derived_scope and header['source_current'] and process['exit_code']==0)
 require(software==header['passed'],'Full current software gate differs')
 public_events={'private_stream_sha256':stage['stream_sha256'],'export_filter':'No thinking, redacted thinking, signatures or assistant narrative; init/tool-use/tool-result/terminal facts only','events':facts['events']}
 write(public/'provider-events.json',public_events);write(public/'request.json',request)
 write(public/'provider-lifecycle.json',{k:clean(stage[k]) for k in ('process_exit','timed_out','wall_seconds','process_cleanup_scope','detached_descendants_contained','guarded_new_session_processes','process_cleanup_seconds','stream_changed_during_cleanup','requested_effort','observed_assistant_models','usage','modelUsage','total_cost_usd','terminal') if k in stage})
 write(public/'qualification.json',qualification);write(public/'local-qualification.json',local);write(public/'evaluation-receipt.json',evaluation)
 shutil.copy2(output,public/'grader.stdout');shutil.copy2(error,public/'grader.stderr')
 for path in (control/'call').glob('*.command-*.json'):shutil.copy2(path,public/path.name)
 for path in (control/'call').glob('command-*.*'):
  if path.suffix in ('.stdout','.stderr'):shutil.copy2(path,public/path.name)
 if (control/'call/tool-events.jsonl').exists():shutil.copy2(control/'call/tool-events.jsonl',public/'tool-events.jsonl')
 write(public/'raw-stage-receipt.json',clean(raw))
 terminal=R.terminal(stage)
 primary_changed=[name for name in task['production_paths'] if (control/'before/source'/name).read_bytes()!=(control/'after/source'/name).read_bytes()]
 new_helpers=[p.name for p in (control/'after/source').glob('*.py') if not (control/'before/source'/p.name).exists()]
 result={'role':role,'status':raw['status'],'provider_request_mtime_at_export':(control/'call/request.json').stat().st_mtime,'provider_interval_end_estimate':(control/'call/request.json').stat().st_mtime+stage['wall_seconds'],'timing_basis':'Current retained request-file mtime plus recorded stage wall_seconds; metadata, not a content-hash-certified creation timestamp','observed_models':facts['models'],'session_id':facts['terminal'].get('session_id') if facts['terminal'] else facts['inits'][0].get('session_id') if facts['inits'] else None,'stage_qualified':qualification['eligible'],'qualification_failures':qualification['failures'],'software_complete':software,'evidence_current':True,'declared_completion':terminal,'required_behavior_passed':header['required_behavior_passed'],'negative_boundaries_passed':header['negative_boundaries_passed'],'baseline_passed':baseline_passed,'scope_violations':derived_scope,'scope_source_facts':[{ 'path':name,'baseline_existed':(Path(task['base_snapshot'])/name).exists(),'candidate_existed':(control/'after/source'/name).exists(),'classification':'changed-existing-baseline' if (Path(task['base_snapshot'])/name).exists() else 'new-outside-permitted-location'} for name in derived_scope],'failed_requirements':header['failed_requirements'],'evaluation_qualified':bool(qualified_eval),'timed_out':stage['timed_out'],'wall_seconds':stage['wall_seconds'],'mcp_request_count':facts['mcp_request_count'],'invalid_stream_or_tool_ids':facts['invalid_stream_or_tool_ids'],'reported_usage':stage.get('usage'),'reported_model_usage':stage.get('modelUsage'),'reported_cost_usd':stage.get('total_cost_usd'),'before_source_sha256':raw['before']['source_sha256'],'after_source_sha256':raw['after']['source_sha256'],'production_patch_sha256':raw['after']['production_patch_sha256'],'production_patch_changed':raw['production_patch_changed_in_stage'],'declared_primary_production_paths_changed':primary_changed,'new_root_helpers':new_helpers,'receipt_sha256':sha(receipt_path),'stream_sha256':stage['stream_sha256'],'request_file_sha256':sha(control/'call/request.json'),'evaluation_receipt_sha256':sha(control/'evaluation/receipt.json')}
 write(public/'INDEPENDENT-DERIVATION.json',result);return result

def export(final=False):
 export_setup();tasks={t['task_id']:t for t in read(PRIVATE/'TASKS.json')['tasks']};requests=read(PRIVATE/'selection/requests.json');rows=[]
 for request in requests:
  cell=PRIVATE/'selection/cells'/request['cell_id'];stages=[x for x in (analyze_stage(cell,'solve',tasks[request['task_id']]),analyze_stage(cell,'repair',tasks[request['task_id']])) if x is not None]
  first=stages[0] if stages else None;last=stages[-1] if stages else None
  if len(stages)>1:
   require(last['before_source_sha256']==first['after_source_sha256'],'Repair did not start at evaluated first source')
   feedback_path=cell/'repair-feedback.json';feedback=read(feedback_path)
   require(feedback['cell_id']==cell.name and feedback['evaluation_receipt_sha256']==sha(cell/'solve/evaluation/receipt.json'),'Repair feedback lineage changed')
   require(feedback['feedback']['failed_requirements']==read(cell/'solve/evaluation/receipt.json')['header']['failed_requirements'],'Repair omitted required failure feedback')
   require(feedback['feedback']['scope_violations']==first['scope_violations'],'Repair omitted scope feedback')
   prompt=read(cell/'repair/call/request.json')['prompt'];packet_text=prompt.split('\nActual independent requirement feedback (including scope):\n',1)[1].split('\nThis is the sole repair attempt.',1)[0]
   require(json.loads(packet_text)==feedback['feedback'],'Delivered repair packet differs')
   write(HERE/'evidence'/cell.name/'repair-feedback.json',feedback)
  counts=[s.get('mcp_request_count') for s in stages]
  rows.append({'cell_id':request['cell_id'],'task_id':request['task_id'],'arm_id':request['arm_id'],'status':'closed' if final and first else 'initial-observed' if first else 'pending','first_complete':bool(first and first['stage_qualified'] and first['software_complete']),'final_complete':bool(first and first['stage_qualified'] and last and last['stage_qualified'] and last['software_complete']),'actual_repair_attempted':len(stages)>1,'production_changed_in_repair':stages[-1].get('production_patch_changed') if len(stages)>1 else False,'mcp_request_count':sum(counts) if stages and all(type(c) is int for c in counts) else None,'stages':stages})
 designs=read(PRIVATE/'DESIGN-RESULTS.json');by_arm={}
 for arm in ('incumbent','branch-a','branch-b'):
  members=[r for r in rows if r['arm_id']==arm];counts=[r['mcp_request_count'] for r in members]
  token_values=[s.get('reported_usage',{}).get('output_tokens') if isinstance(s.get('reported_usage'),dict) else None for r in members for s in r['stages']]
  by_arm[arm]={'reported_output_tokens':sum(token_values) if token_values and all(type(v) is int for v in token_values) else None,'known_reported_output_tokens':sum(v for v in token_values if type(v) is int),'output_token_missing_stages':sum(v is None for v in token_values),'assigned':len(members),'observed':sum(bool(r['stages']) for r in members),'first_complete':sum(r['first_complete'] for r in members),'final_complete':sum(r['final_complete'] for r in members),'repair_attempts':sum(r['actual_repair_attempted'] for r in members),'mcp_request_count':sum(counts) if all(type(c) is int for c in counts) else None,'reported_wall_seconds':sum(s['wall_seconds'] for r in members for s in r['stages']),'reported_cost_usd':sum(s['reported_cost_usd'] for r in members for s in r['stages'] if type(s.get('reported_cost_usd')) in (int,float)),'cost_missing_stages':sum(s.get('reported_cost_usd') is None for r in members for s in r['stages'])}
 if (PRIVATE/'DISPATCH-PAUSE.json').exists():shutil.copy2(PRIVATE/'DISPATCH-PAUSE.json',HERE/'setup-handling/DISPATCH-PAUSE.json')
 concurrency={'registered_max_concurrent_task_calls':2,'observed_overlap':3,'overlap_seconds':44.47650804200384,'overlapped_calls':['tweed-pr26--branch-a/repair','tweed-pr45--branch-b/solve','tweed-pr45--incumbent/solve'],'timing_basis':'Retained request mtimes plus stage wall durations; independently audited controller chronology','pause_after_repair_complete':True,'pause_fixed_overlap':False,'strict_comparative_inference_qualified':False}
 write(HERE/'setup-handling/SCHEDULING-DEVIATION.json',concurrency)
 design_calls=[]
 for arm in ('branch-a','branch-b'):
  directory=PRIVATE/'lead'/('design-'+arm);raw=read(directory/'receipt.json');facts=typed_stream(directory/'stream.jsonl');public=HERE/'evidence'/'designs'/arm
  require(sha(directory/'stream.jsonl')==next(b['stream_sha256'] for b in designs['branches'] if b['arm']==arm),'Design stream changed')
  write(public/'provider-events.json',{'private_stream_sha256':sha(directory/'stream.jsonl'),'events':facts['events'],'export_filter':'No provider thinking or assistant narrative'})
  write(public/'provider-lifecycle.json',clean(raw));write(public/'request.json',read(directory/'request.json'))
  design_calls.append({'arm':arm,'observed_models':facts['models'],'reported_usage':raw.get('terminal',{}).get('usage'),'reported_cost_usd':raw.get('terminal',{}).get('total_cost_usd'),'wall_seconds':raw.get('wall_seconds'),'mcp_requests':facts['mcp_request_count'],'cost_scope':'Separate design-call overhead, excluded from selection MCP request proxy'})
 result={'schema_version':1,'phase':'final' if final else 'initial-pending-repair-closure','assigned':6,'entrypoint_control_commit':'4758787015f05a95ea38896f57a462316b3d9d80','rows':rows,'by_arm':by_arm,'design_static_results':designs,'design_call_overhead':design_calls,'controller_fidelity':concurrency,'promotion':{'promoted':False,'reason':'Both original candidates exceed the frozen105% entrypoint-size cap; neither is eligible regardless of task diagnostics. No correction or criterion amendment.','confirmation_run':False},'native_checker_model_identity':'unobserved','source_binding_scope':'Retained current-byte receipts/source/patch hashes; no absolute continuous-immutability claim','provider_thinking_exported':False,'setup_handling':'Source-preserving restoration before task inference; proposed helper change archived unused','limitations':['One small historical task panel and one fresh-context design fan-out, not periodic fork-and-flush replication.','Only SKILL.md differs; common refs/toolkit and actual requested solver route are held fixed.','The shared475 toolkit already implements/documents run --json; actual modern reference/test reads differ across arms. Authorized common exposure is not private oracle leakage, but the PR45 slice is not blind to a related current solution recipe.','Installed0.8 and original0.6 are not these comparison controls.','Timeout is a retained stage deadline/missing-delivery observation; causal attribution is not assumed environmental or protocol failure.','Author complete/remaining preserved verbatim, separate from independent current software gates.','Reported usage/cost is provider metadata, not independently billed-account cost.']}
 write(HERE/'RESULTS.json',result);return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args();result=export(args.final)
 print(json.dumps({'phase':result['phase'],'observed':sum(bool(r['stages']) for r in result['rows']),'by_arm':result['by_arm']}))
