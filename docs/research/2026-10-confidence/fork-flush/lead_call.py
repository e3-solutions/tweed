"""Bounded actual Claude calls for revision development; no provider bypass."""
import argparse,hashlib,json,pathlib,subprocess,sys,time
ROOT=pathlib.Path('/Users/aryagm/.codex/worktrees/b6ce/tweed');E=ROOT/'.confidence/lean-repair'
H=ROOT/'docs/research/2026-10-confidence/claude-first-evaluation';sys.path.insert(0,str(H));import runner as r
def call(name,cwd,prompt,model,seconds,budget,owned=(),schema=None):
 out=E/'lead'/name;out.mkdir(parents=True,exist_ok=False)
 tools='Read,Glob,Grep,Edit,Write' if owned else ''
 allowed=['Read','Glob','Grep']+['Edit(./'+x+')' for x in owned] if owned else []
 allowed+=['Write(./'+x+')' for x in owned]
 argv=['/opt/homebrew/bin/claude','--print','--model',model,'--effort','high' if owned else 'medium','--output-format','stream-json','--verbose','--tools',tools,'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','','--no-session-persistence','--restricted','--disable-slash-commands','--permission-mode','dontAsk','--max-budget-usd',str(budget)]
 if allowed:argv+=['--allowedTools',*allowed]
 if schema:argv+=['--json-schema',json.dumps(schema)]
 argv+=['--append-system-prompt','Use only authorized supplied source. You are not alone; preserve others work. Actual tools and executed checks establish observations; prose is not proof. Never request hidden reasoning.']
 request={'argv':argv,'cwd':str(cwd),'model_requested':model,'owned_files':list(owned),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'timeout_seconds':seconds,'cli_version':subprocess.check_output([argv[0],'--version'],text=True).strip()}
 r.write(out/'request.json',request);(out/'prompt.txt').write_text(prompt)
 process_guard=r.load(r.BENCH/'hybrid_process_v2.py');started=time.monotonic();timed=False
 with (out/'prompt.txt').open('rb') as inp,(out/'stream.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
  p=subprocess.Popen(argv,cwd=cwd,stdin=inp,stdout=stdout,stderr=stderr,start_new_session=True)
  try:p.wait(timeout=seconds)
  except subprocess.TimeoutExpired:timed=True
  finally:process_guard.cleanup_group(p)
 events=[];invalid=0
 for line in (out/'stream.jsonl').read_text(errors='replace').splitlines():
  try:events.append(json.loads(line))
  except ValueError:invalid+=1
 terminal=next((x for x in reversed(events) if x.get('type')=='result'),None)
 models=sorted({x['message']['model'] for x in events if x.get('type')=='assistant' and isinstance(x.get('message'),dict) and isinstance(x['message'].get('model'),str)})
 calls=[b for x in events if x.get('type')=='assistant' for b in x.get('message',{}).get('content',[]) if isinstance(b,dict) and b.get('type')=='tool_use']
 receipt={'exit_code':p.returncode,'timed_out':timed,'wall_seconds':time.monotonic()-started,'observed_models':models,'terminal':terminal,'stream_sha256':r.sha(out/'stream.jsonl'),'request_sha256':r.sha(out/'request.json'),'tool_call_count':len(calls),'tool_names':sorted({x.get('name') for x in calls}),'invalid_stream_lines':invalid,'process_cleanup_scope':'original_process_group','detached_descendants_contained':False}
 r.write(out/'receipt.json',receipt)
 if terminal:(out/'answer.txt').write_text(terminal.get('result',''))
 print(json.dumps({k:receipt[k] for k in ['exit_code','timed_out','wall_seconds','observed_models','tool_call_count']}),flush=True)
 return receipt
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['discovery','development']);args=a.parse_args();work=pathlib.Path('/Users/aryagm/.codex/worktrees/confidence-opus-lead/tweed')
 if args.mode=='discovery':
  names=['skills/confidence-protocol/SKILL.md','skills/confidence-protocol/references/intent-flows.md','skills/confidence-protocol/references/model-routing.md','docs/research/2026-10-confidence/v08-spotcheck/REPORT.md']
  source={n:(work/n).read_text().splitlines() for n in names}
  schema={'type':'object','properties':{'facts':{'type':'array','items':{'type':'object','properties':{'path':{'type':'string'},'line':{'type':'integer'},'quote':{'type':'string'},'implication':{'type':'string'}},'required':['path','line','quote','implication'],'additionalProperties':False}},'gaps':{'type':'array','items':{'type':'string'}}},'required':['facts','gaps'],'additionalProperties':False}
  prompt='Bounded source discovery ONLY. Extract up to six facts relevant to existing requirement coverage, intake stopping and repair handoff. Cite exact supplied path, 1-based line and a single verbatim line. Implications are candidates, not proof. Do not design or edit; do not rank models. Source packet:\n'+json.dumps(source)
  receipt=call('haiku-discovery',work,prompt,'claude-haiku-5-5',120,.6,schema=schema)
  assert receipt['exit_code']==0 and not receipt['timed_out'] and receipt['observed_models']==['claude-haiku-5-5']
  assert set(receipt['tool_names'])<= {'StructuredOutput'}
  term=receipt['terminal'];assert term['subtype']=='success' and term['is_error'] is False
  facts=term['structured_output'];assert len(facts['facts'])<=6
  for fact in facts['facts']:assert fact['quote']==source[fact['path']][fact['line']-1]
  r.write(E/'lead/haiku-discovery/verified-facts.json',{'facts':facts,'verification':'Each quoted line retraced in supplied current source; implications remain candidates','source_sha256':{n:r.sha(work/n) for n in names}})
 else:
  owned=['skills/confidence-protocol/SKILL.md','skills/confidence-protocol/references/intent-flows.md','skills/confidence-protocol/references/model-routing.md','skills/confidence-protocol/references/question-patterns.md','README.md','CHANGELOG.md','.codex-plugin/plugin.json','skills/confidence-protocol/scripts/diagnostics.py','docs/research/2026-10-confidence/lean-repair/DESIGN.md']
  prompt=(E/'lead/development-prompt.txt').read_text();call('opus-development',work,prompt,'claude-opus-5-5',600,5,owned)
