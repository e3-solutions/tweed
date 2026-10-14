#!/usr/bin/env python3
"""Export settled evidence only. No provider call, grader execution or source mutation.

Raw streams remain private. Research result bodies and StructuredOutput are
hash-bound, avoiding republication of unnecessary third-party page extracts.
Task/author MCP operations, typed identities, lifecycle and completion claims
are retained; thinking/signatures/credential fields are never exported.
"""
import argparse,collections,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'.git').exists())
PRIVATE=ROOT/'.confidence/fair-loop'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def require(value,message):
 if not value:raise ValueError(message)
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def clean(value):
 if isinstance(value,list):return [clean(x) for x in value if not(isinstance(x,dict) and x.get('type') in ('thinking','redacted_thinking'))]
 if isinstance(value,dict):
  return {k:clean(v) for k,v in value.items() if k.lower() not in ('thinking','signature','authorization','cookie','password','api_key','access_token','refresh_token','secret') and not k.upper().endswith(('_API_KEY','_ACCESS_TOKEN','_REFRESH_TOKEN'))}
 return value
def typed_stream(path,research=False):
 events=[];uses={};results={};models=set();sessions=set();inits=[];terminals=[];invalid=[]
 for number,line in enumerate(path.read_text().splitlines(),1):
  try:e=json.loads(line)
  except ValueError:invalid.append('invalid-json-line:'+str(number));continue
  if not isinstance(e,dict):invalid.append('invalid-event:'+str(number));continue
  kind=e.get('type');session=e.get('session_id')
  if isinstance(session,str):sessions.add(session)
  if kind=='system' and e.get('subtype')=='init':
   inits.append(e);events.append({'type':'system','subtype':'init',**{k:clean(e[k]) for k in ('session_id','model','tools','mcp_servers','permissionMode','claude_code_version','uuid') if k in e}})
  elif kind=='assistant':
   m=e.get('message',{});model=m.get('model')
   if isinstance(model,str):models.add(model)
   tools=[]
   for b in m.get('content',[]):
    if not isinstance(b,dict) or b.get('type')!='tool_use':continue
    ident=b.get('id')
    if not isinstance(ident,str) or not ident:invalid.append('missing-tool-id');continue
    if ident in uses and uses[ident]!=b:invalid.append('conflicting-tool-id:'+ident)
    uses[ident]=b
    if research and b.get('name')=='StructuredOutput':tools.append({'type':'tool_use','id':ident,'name':b['name'],'input_sha256':digest(b.get('input')),'input_keys':sorted(b.get('input',{}))})
    else:tools.append(clean(b))
   # Metadata is preserved even when the message contained only hidden thinking.
   events.append({'type':'assistant','message':{k:clean(m[k]) for k in ('id','model','role','usage') if k in m}|{'content':tools},**{k:e[k] for k in ('session_id','uuid') if k in e}})
  elif kind=='user':
   selected=[]
   for b in e.get('message',{}).get('content',[]):
    if not isinstance(b,dict) or b.get('type')!='tool_result':continue
    ident=b.get('tool_use_id');results[ident]=b
    if research:selected.append({'type':'tool_result','tool_use_id':ident,'is_error':b.get('is_error',False),'content_sha256':digest(b.get('content')),'serialized_content_characters':len(json.dumps(b.get('content'))),'body_withheld':'Research extracts remain private; request URL and outcome digest retained.'})
    else:selected.append(clean(b))
   if selected:events.append({'type':'user','message':{'role':'user','content':selected},**{k:e[k] for k in ('session_id','uuid') if k in e}})
  elif kind=='result':
   terminals.append(e);terminal={k:clean(v) for k,v in e.items() if k not in ('result','structured_output')}
   terminal['result_sha256']=digest(e.get('result'));terminal['structured_output_sha256']=digest(e.get('structured_output'))
   if not research:terminal['structured_output']=clean(e.get('structured_output'))
   events.append(terminal)
 return {'events':events,'models':sorted(models),'sessions':sorted(sessions),'requests':list(uses.values()),'results':results,'inits':inits,'terminals':terminals,'invalid':invalid}
def export_provider(source,destination,phase,research=False,receipt_name='receipt.json',request_name='request.json',stream_name='stream.jsonl'):
 source=Path(source);destination=Path(destination)
 receipt_path=source/receipt_name
 if not receipt_path.exists():return {'phase':phase,'status':'not-settled','source':str(source)}
 receipt=read(receipt_path);request_path=source/request_name;stream_path=source/stream_name
 require(request_path.exists() and stream_path.exists(),'Missing retained provider inputs')
 request=read(request_path);facts=typed_stream(stream_path,research);record=receipt['stage'] if isinstance(receipt.get('stage'),dict) else receipt
 if record.get('stream_sha256'):require(record['stream_sha256']==sha(stream_path),'Stream binding changed')
 if record.get('stdout_sha256'):require(record['stdout_sha256']==sha(stream_path),'Captured stream binding changed')
 if record.get('request_sha256'):require(record['request_sha256'] in (sha(request_path),digest(request)),'Request binding changed')
 observed=record.get('observed_models',record.get('observed_assistant_models'))
 if observed is not None:require(observed==facts['models'],'Raw model identity differs from receipt')
 terminal=facts['terminals'][-1] if facts['terminals'] else None
 if 'terminal' in record:require(record['terminal']==terminal,'Terminal differs from raw stream')
 initialization=record.get('initialization',record.get('harness_initialization'))
 if initialization is not None:
  actual_init=facts['inits'][0] if facts['inits'] else {}
  require(all(actual_init.get(k)==v for k,v in initialization.items()),'Raw initialization differs from receipt')
 identity=request.get('identity',{});argv=request.get('argv',[]);effort=request.get('effort') or (argv[argv.index('--effort')+1] if '--effort' in argv else None)
 require((request.get('model_requested') or identity.get('model'))=='claude-opus-5-5' and effort=='high','Route assignment differs')
 for directory,entries in record.get('source_authorship',{}).items():
  for name,pin in entries.items():
   authored=source/'authored'/directory/name
   require(authored.is_file() and not authored.is_symlink() and sha(authored)==pin['sha256'] and authored.stat().st_mode&0o777==pin['mode'],'Captured author source changed: '+directory+'/'+name)
 destination.mkdir(parents=True,exist_ok=True)
 write(destination/'request.json',clean(request));write(destination/'provider-events.json',{'private_stream_sha256':sha(stream_path),'filter':'Typed init/assistant metadata/tool operations/results/terminal facts; no thinking/signatures/narrative. Research result bodies hash-bound only.','events':facts['events']})
 lifecycle={k:clean(v) for k,v in record.items() if k not in ('terminal','initialization','tool_calls','source_authorship','artifacts')}
 if terminal:lifecycle['terminal']={k:clean(terminal[k]) for k in ('type','subtype','is_error','stop_reason','terminal_reason','session_id','usage','modelUsage','total_cost_usd','duration_ms','duration_api_ms','permission_denials') if k in terminal}
 lifecycle['receipt_sha256']=sha(receipt_path);lifecycle['request_file_sha256']=sha(request_path);lifecycle['stream_file_sha256']=sha(stream_path)
 write(destination/'provider-lifecycle.json',lifecycle)
 for name in ('admission.json','process.json','released.json','transport-preflight.json','AUTHOR-STATUS.json','HANDOFF-BINDING.json'):
  if (source/name).exists():write(destination/name,clean(read(source/name)))
 if (source/'authored').exists():shutil.copytree(source/'authored',destination/'authored',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
 for p in (source/'call').glob('*') if (source/'call').exists() else []:
  if p.is_file() and (p.name.endswith(('.command-request.json','.command-response.json')) or p.name.startswith('command-') and p.suffix in ('.stdout','.stderr') or p.name=='tool-events.jsonl'):shutil.copyfile(p,destination/p.name)
 # These are actual top-level retained requests; mock child fixtures are not scanned.
 counts=collections.Counter(b.get('name') for b in facts['requests']);rows=[]
 for b in facts['requests']:
  r=facts['results'].get(b['id']);rows.append({'id':b['id'],'name':b.get('name'),'request_sha256':digest(b),'input':clean(b.get('input')) if b.get('name') in ('WebFetch','WebSearch') else None,'result_observed':r is not None,'is_error':r.get('is_error',False) if r else None,'result_sha256':digest(r) if r else None})
 write(destination/'TOOL-REQUESTS.json',{'unique_request_count':len(rows) if not facts['invalid'] else None,'by_name':dict(counts),'invalid_stream_or_ids':facts['invalid'],'requests':rows})
 summary={'phase':phase,'status':'settled','source_receipt_sha256':sha(receipt_path),'observed_models':facts['models'],'session_ids':facts['sessions'],'typed_terminal_observed':terminal is not None,'terminal_count':len(facts['terminals']),'actual_unique_tool_requests':len(rows) if not facts['invalid'] else None,'actual_unique_mcp_requests':sum(n for name,n in counts.items() if isinstance(name,str) and name.startswith('mcp__cp_trial__')) if not facts['invalid'] else None,'tools_by_name':dict(counts),'invalid_stream_or_ids':facts['invalid'],'provider_delivery_qualified_recorded':record.get('qualified_provider_delivery',record.get('qualified')),'timed_out':record.get('timed_out'),'wall_seconds':record.get('wall_seconds',record.get('elapsed')),'reported_cost_usd':terminal.get('total_cost_usd') if terminal else None,'reported_usage':terminal.get('usage') if terminal else None,'reported_model_usage':terminal.get('modelUsage') if terminal else None,'source_authorship':clean(record.get('source_authorship')),'model_thinking_exported':False}
 write(destination/'INDEPENDENT-FACTS.json',summary);return summary
def inventory():
 entries=[{'path':str(p.relative_to(HERE)),'sha256':sha(p),'bytes':p.stat().st_size,'mode':oct(p.stat().st_mode&0o777)} for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'ARTIFACTS.json']
 write(HERE/'ARTIFACTS.json',{'self_excluded':True,'pre_inference_manifest_sha256':sha(HERE/'PRE-INFERENCE-ARTIFACTS.json'),'files':entries})
def export_tasks():
 import importlib.util,sys,tempfile
 sys.dont_write_bytecode=True
 def load(path,name):
  spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 D=load(PRIVATE/'run_tasks.py','fair_export_driver');E=load(PRIVATE/'evaluate.py','fair_export_owner');study=PRIVATE/'study-v2';reg=read(study/'registration.json');rows=[]
 for cell in reg['payload']['cells']:
  directory=study/'cells'/cell['cell_id'];task=cell['task'];stages=[]
  for role in ('main','continuation'):
   stage=directory/role
   if not (stage/'result.json').exists():continue
   result=read(stage/'result.json');raw=read(stage/(role+'.receipt.json'));require(raw==result['stage'],'Stage receipt/result mismatch')
   public=HERE/'evidence/tasks'/cell['cell_id']/role
   facts=export_provider(stage,public,role,False,role+'.receipt.json',role+'.request.json',role+'.stdout')
   write(public/'raw-provider-receipt.json',clean(raw));shutil.copy2(stage/(role+'.process.json'),public/'process.json')
   if (stage/'bridge.json').exists():shutil.copy2(stage/'bridge.json',public/'bridge.json')
   grade_dir=Path(result.get('evaluation_directory',str(stage/'evaluation')))
   if not grade_dir.is_absolute():grade_dir=ROOT/grade_dir
   receipt=read(grade_dir/'receipt.json');header=json.loads((grade_dir/'grader.stdout').read_text().splitlines()[0])
   require(header==receipt['header']==result['grade'],'Owner header mapping differs')
   require(sha(grade_dir/'grader.stdout')==receipt['stdout_sha256'] and sha(grade_dir/'grader.stderr')==receipt['stderr_sha256'],'Owner output binding differs')
   source=stage/'after/source';before=stage/'before/source';require(E.A.raw_tree(source)==header['source_before_sha256']==header['source_after_sha256'],'Current captured owner source differs')
   require(sha(source/(task['module']+'.py'))==header['local_module_binding']['local_module_sha256'],'Actor-local module differs from checked module')
   require(E.scoped(Path(task['base_snapshot']),source,task['production_paths'])==header['scope_violations'],'Scope derivation differs')
   for side in ('before','after'):
    pin=read(stage/side/'receipt.json');require(pin==result[side],'Captured source receipt differs')
    require(D.R.route({'backend':'claude','model':D.C.MODEL,'effort':'high'}).frozen.base.tree_digest(stage/side/'source')==pin['source_sha256'],'Captured tree differs')
    require(sha(stage/side/'production.patch')==pin['production_patch_sha256'],'Retained patch differs')
    shutil.copy2(stage/side/'production.patch',public/(side+'-production.patch'));write(public/(side+'-source-identity.json'),pin)
    # Complete scoped actor source, including tests and identical policy, licenses.
    shutil.copytree(stage/side/'source',public/side/'source',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.git'))
   artifacts=all(header.get(k) is True for k in ('product_passed','positive_passed','negative_passed','regression_passed','scope_valid','source_current')) and header.get('evaluation_status')=='observed'
   require(artifacts==bool(header['product_passed']),'Artifact gates disagree')
   custody=D.C.qualification(header,{**raw,'stage':'main'});delivery=D.delivery_gate(header,raw)
   terminal=raw.get('terminal');final_delivery=bool(delivery and terminal is not None and not raw.get('timed_out') and raw.get('terminal_before_deadline') is True)
   row={'role':role,'artifact_complete':artifacts,'artifact_evaluation_status':header['evaluation_status'],'delivery_valid':final_delivery,'known_deadline':bool(raw.get('timed_out') and raw.get('deadline_known')),'custody_qualified':not custody,'custody_failures':custody,'controller_settled':raw.get('settled') is True,'after_source_sha256':result['after']['source_sha256'],'before_source_sha256':result['before']['source_sha256'],'primary_runtime_changed':(before/(task['module']+'.py')).read_bytes()!=(source/(task['module']+'.py')).read_bytes(),'required_gaps':header['failed_requirements'],'safe_declared_completion':terminal.get('structured_output') if terminal else None,'original_evaluation_corrected':grade_dir!=stage/'evaluation','facts':facts,'evaluation_receipt_sha256':sha(grade_dir/'receipt.json')}
   write(public/'evaluation-receipt.json',receipt);shutil.copy2(grade_dir/'grader.stdout',public/'grader.stdout');shutil.copy2(grade_dir/'grader.stderr',public/'grader.stderr');write(public/'result.json',clean(result))
   if row['original_evaluation_corrected']:
    shutil.copytree(stage/'evaluation',public/'original-unbound-evaluation',dirs_exist_ok=True)
   for p in stage.glob('*RECOVERY*'):
    if p.is_file():shutil.copy2(p,public/p.name)
   write(public/'INDEPENDENT-DERIVATION.json',row);stages.append(row)
  if len(stages)==2:
   require(stages[1]['before_source_sha256']==stages[0]['after_source_sha256'],'Continuation source lineage differs')
   feedback=read(directory/'continuation-feedback.json');require(feedback['grade_receipt_sha256']==stages[0]['evaluation_receipt_sha256'],'Continuation critic lineage differs');write(HERE/'evidence/tasks'/cell['cell_id']/'continuation-feedback.json',clean(feedback))
  final=stages[-1] if stages else None
  rows.append({'cell_id':cell['cell_id'],'task_id':cell['task_id'],'arm':cell['arm_id'],'status':'observed' if final else 'pending','stages':stages,'first_artifact_complete':stages[0]['artifact_complete'] if stages else None,'final_artifact_complete':final['artifact_complete'] if final else None,'final_delivery_valid':final['delivery_valid'] if final else None,'final_custody_qualified':final['custody_qualified'] if final else None})
 write(HERE/'TASK-FACTS.json',{'registration_sha256':sha(study/'registration.json'),'pre_inference_sha256':sha(HERE/'PRE-INFERENCE-ARTIFACTS.json'),'prospective_commit':'32960cc9c6e230c73c018af3b1902d5d1e62d89f','cells':rows,'native_codex_model_identity':'unobserved'})
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--authors-only',action='store_true');p.add_argument('--tasks',action='store_true');args=p.parse_args();rows=[]
 for relative,phase,research in [('research/opus-deep-research','research',True),('development/opus-build','initial-author',False),('development/opus-runtime-continuation','author-continuation',False),('development/opus-final-patch','author-core-correction',False)]:
  directory=PRIVATE/relative
  if (directory/'receipt.json').exists() and (directory/'released.json').exists():rows.append(export_provider(directory,HERE/'evidence'/relative,phase,research))
 write(HERE/'AUTHOR-FACTS.json',{'author_stage_facts':rows,'scope':'Author costs/requests separate from four task cells; no mock child fixtures counted as provider calls.','native_codex_model_identity':'unobserved'});
 if args.tasks:export_tasks()
 inventory();print(json.dumps({'exported_closed_author_stages':len(rows),'actual_tool_requests':[r['actual_unique_tool_requests'] for r in rows]}))
if __name__=='__main__':main()
