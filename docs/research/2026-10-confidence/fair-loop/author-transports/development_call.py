"""Minimal actual-author development transport; no controller implementation."""
import fcntl,hashlib,importlib.util,json,pathlib,shutil,subprocess,sys,time
E=pathlib.Path(__file__).resolve().parent;R=E.parents[1]
spec=importlib.util.spec_from_file_location('actual_author_legacy',R/'docs/research/2026-10-confidence/claude-first-evaluation/runner.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
MODEL='claude-opus-5-5';TOOLS=('list_files','read_file','write_file','replace_text','run_tests')
def main():
 out=E/'development'/'opus-build';out.mkdir(parents=True,exist_ok=False);workspace=E/'development'/'workspace';adapter=r.route({'backend':'claude','model':MODEL,'effort':'high'});base=adapter.frozen.base
 control=out/'call';control.mkdir();temporary=workspace/'.trial-tmp';temporary.mkdir(exist_ok=True)
 config={'workspace':str(workspace),'control':str(control),'temporary':str(temporary),'readonly':False,'deadline':time.time()+600,'python_executable':sys.executable,'borrowed_runner':str(workspace/'.protocol/qualified/docs/research/2026-10-confidence/pr-benchmark/runner.py')}
 config_path=control/'server-config.json';r.write(config_path,config);server=E/'development_tool_server.py'
 profile=base.sandbox_profile(workspace,temporary,extra_reads=[server,config_path],extra_writes=[control],readonly=False)
 mcp={'mcpServers':{'cp_trial':{'command':'/usr/bin/sandbox-exec','args':['-p',profile,sys.executable,'-I','-S','-B',str(server),str(config_path)],'env':base.safe_env(workspace,temporary)}}}
 prompt=(E/'development'/'PROMPT.txt').read_text();schema=base.FINAL_SCHEMA
 argv=['claude','--print','--model',MODEL,'--effort','high','--output-format','stream-json','--verbose','--tools','','--strict-mcp-config','--mcp-config',json.dumps(mcp),'--setting-sources','','--no-session-persistence','--restricted','--disable-slash-commands','--permission-mode','dontAsk','--allowedTools',*['mcp__cp_trial__'+name for name in TOOLS],'--max-budget-usd','5','--json-schema',json.dumps(schema),'--system-prompt','You are the actual developer author working only through the5 bounded coding tools. Own only NEW runtime and candidate source in this isolated authorized snapshot. .protocol is immutable supplied source. No network, outside files, tasks/oracles/headsolutions, native tools or nested hosted calls. Use real CPU subprocess controls, not model outcome claims. Return required final JSON truthfully.',prompt]
 request={'argv':argv,'model_requested':MODEL,'effort':'high','timeout_seconds':600,'budget_usd':5,'cwd':str(workspace),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'provider_lock':str(E/'provider.lock'),'authorized_output_roots':['runtime/','candidate/'],'tools':list(TOOLS),'cli_version':subprocess.check_output(['claude','--version'],text=True).strip()};r.write(out/'request.json',request)
 # Offline actual tool list and immutable write denial; no hosted request.
 calls=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'actual-author-preflight','version':'1'}}},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'write_file','arguments':{'path':'.protocol/MUST-NOT-WRITE','content':'denied'}}}]
 proc=subprocess.run([mcp['mcpServers']['cp_trial']['command'],*mcp['mcpServers']['cp_trial']['args']],cwd=workspace,env=mcp['mcpServers']['cp_trial']['env'],input=''.join(json.dumps(item)+'\n' for item in calls),text=True,capture_output=True,timeout=20)
 byid={item.get('id'):item for item in [json.loads(line) for line in proc.stdout.splitlines()]};names=[item['name'] for item in byid.get(2,{}).get('result',{}).get('tools',[])];passed=proc.returncode==0 and names==list(TOOLS) and byid.get(3,{}).get('result',{}).get('isError') is True and not (workspace/'.protocol/MUST-NOT-WRITE').exists();r.write(out/'transport-preflight.json',{'passed':passed,'hosted_calls':0,'effective_tools':names,'immutable_source_write_denied':passed,'stdout_sha256':hashlib.sha256(proc.stdout.encode()).hexdigest()})
 if not passed:raise RuntimeError('Actual5-tool development transport failed before inference')
 with (E/'provider.lock').open('a+') as permit:
  queued=time.time();fcntl.flock(permit.fileno(),fcntl.LOCK_EX);admitted=time.time();config['deadline']=admitted+600;r.write(config_path,config)
  r.write(out/'admission.json',{'queued_at_unix':queued,'admitted_at_unix':admitted,'lock':str(E/'provider.lock'),'global_serial_limit':1,'held_until':'reap/cleanup/raw settlement/receipt/authored-source capture'})
  with (out/'stream.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
   process=base.subprocess.Popen(argv,cwd=workspace,stdout=stdout,stderr=stderr,start_new_session=True);r.write(out/'process.json',{'pid':process.pid,'process_group':process.pid,'popen_at_unix':time.time(),'permit_held':True});timed=False
   try:
    while process.poll() is None:
     base.service_commands(control,workspace,temporary,False,admitted+600)
     if time.time()>=admitted+600:timed=True;base.terminate(process);break
     time.sleep(.1)
   finally:adapter.frozen.processes.cleanup_group(process)
  events=[];invalid=0
  for line in (out/'stream.jsonl').read_text(errors='replace').splitlines():
   try:events.append(json.loads(line))
   except ValueError:invalid+=1
  terminals=[x for x in events if x.get('type')=='result'];terminal=terminals[-1] if terminals else None;models=sorted({x['message']['model'] for x in events if x.get('type')=='assistant' and isinstance(x.get('message'),dict) and isinstance(x['message'].get('model'),str)})
  calls=[b for x in events if x.get('type')=='assistant' for b in x.get('message',{}).get('content',[]) if isinstance(b,dict) and b.get('type')=='tool_use'];init=next((x for x in events if x.get('type')=='system' and x.get('subtype')=='init'),None)
  allowed={'StructuredOutput',*['mcp__cp_trial__'+name for name in TOOLS]};unexpected=[x.get('name') for x in calls if x.get('name') not in allowed];live_tools=init.get('tools') if init else None
  valid=process.returncode==0 and not timed and models==[MODEL] and len(terminals)==1 and terminal.get('subtype')=='success' and terminal.get('is_error') is False and not unexpected and isinstance(live_tools,list) and set(live_tools)==allowed
  authored={}
  for name in ('runtime','candidate'):
   source=workspace/name
   if source.exists():
    destination=out/'authored'/name;destination.parent.mkdir(exist_ok=True);base.safe_copy(source,destination);authored[name]=r.inventory(destination)
  receipt={'qualified_provider_delivery':valid,'process_exit':process.returncode,'timed_out':timed,'wall_seconds':time.time()-admitted,'queued_seconds':admitted-queued,'requested_model':MODEL,'observed_models':models,'initialization':init,'terminal':terminal,'tool_calls':calls,'unexpected_tool_requests':unexpected,'invalid_stream_lines':invalid,'request_sha256':r.sha(out/'request.json'),'stream_sha256':r.sha(out/'stream.jsonl'),'source_authorship':authored,'process_cleanup_scope':'original_process_group','detached_descendants_contained':False,'admitted_at_unix':admitted,'reaped_and_source_captured_at_unix':time.time()}
  r.write(out/'receipt.json',receipt);r.write(out/'released.json',{'released_at_unix':time.time(),'receipt_sha256':r.sha(out/'receipt.json'),'authored_source_captured':True});fcntl.flock(permit.fileno(),fcntl.LOCK_UN)
 print(json.dumps({k:receipt[k] for k in ('qualified_provider_delivery','process_exit','timed_out','wall_seconds','requested_model','observed_models')}),flush=True)
 if not valid:raise SystemExit(1)
if __name__=='__main__':main()
