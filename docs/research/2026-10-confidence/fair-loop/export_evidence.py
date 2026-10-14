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
 request=read(request_path);facts=typed_stream(stream_path,research);record=receipt.get('stage',receipt)
 if record.get('stream_sha256'):require(record['stream_sha256']==sha(stream_path),'Stream binding changed')
 if record.get('request_sha256'):require(record['request_sha256'] in (sha(request_path),digest(request)),'Request binding changed')
 observed=record.get('observed_models',record.get('observed_assistant_models'))
 if observed is not None:require(observed==facts['models'],'Raw model identity differs from receipt')
 terminal=facts['terminals'][-1] if facts['terminals'] else None
 if 'terminal' in record:require(record['terminal']==terminal,'Terminal differs from raw stream')
 initialization=record.get('initialization',record.get('harness_initialization'))
 if initialization is not None:
  actual_init=facts['inits'][0] if facts['inits'] else {}
  require(all(actual_init.get(k)==v for k,v in initialization.items()),'Raw initialization differs from receipt')
 require(request.get('model_requested')=='claude-opus-5-5' and request.get('effort')=='high','Author route assignment differs')
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
 summary={'phase':phase,'status':'settled','source_receipt_sha256':sha(receipt_path),'observed_models':facts['models'],'session_ids':facts['sessions'],'typed_terminal_observed':terminal is not None,'terminal_count':len(facts['terminals']),'actual_unique_tool_requests':len(rows) if not facts['invalid'] else None,'actual_unique_mcp_requests':sum(n for name,n in counts.items() if isinstance(name,str) and name.startswith('mcp__cp_trial__')) if not facts['invalid'] else None,'tools_by_name':dict(counts),'invalid_stream_or_ids':facts['invalid'],'provider_delivery_qualified_recorded':record.get('qualified_provider_delivery',record.get('qualified')),'timed_out':record.get('timed_out'),'wall_seconds':record.get('wall_seconds'),'reported_cost_usd':terminal.get('total_cost_usd') if terminal else None,'reported_usage':terminal.get('usage') if terminal else None,'reported_model_usage':terminal.get('modelUsage') if terminal else None,'source_authorship':clean(record.get('source_authorship')),'model_thinking_exported':False}
 write(destination/'INDEPENDENT-FACTS.json',summary);return summary
def inventory():
 entries=[{'path':str(p.relative_to(HERE)),'sha256':sha(p),'bytes':p.stat().st_size,'mode':oct(p.stat().st_mode&0o777)} for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'ARTIFACTS.json']
 write(HERE/'ARTIFACTS.json',{'self_excluded':True,'pre_inference_manifest_sha256':sha(HERE/'PRE-INFERENCE-ARTIFACTS.json'),'files':entries})
def main():
 p=argparse.ArgumentParser();p.add_argument('--authors-only',action='store_true');args=p.parse_args();rows=[]
 for relative,phase,research in [('research/opus-deep-research','research',True),('development/opus-build','initial-author',False),('development/opus-runtime-continuation','author-continuation',False),('development/opus-final-patch','author-core-correction',False)]:
  directory=PRIVATE/relative
  if (directory/'receipt.json').exists() and (directory/'released.json').exists():rows.append(export_provider(directory,HERE/'evidence'/relative,phase,research))
 write(HERE/'AUTHOR-FACTS.json',{'author_stage_facts':rows,'scope':'Author costs/requests separate from four task cells; no mock child fixtures counted as provider calls.','native_codex_model_identity':'unobserved'});inventory();print(json.dumps({'exported_closed_author_stages':len(rows),'actual_tool_requests':[r['actual_unique_tool_requests'] for r in rows]}))
if __name__=='__main__':main()
