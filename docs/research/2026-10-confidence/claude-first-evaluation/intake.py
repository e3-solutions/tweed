"""Executed scripted-user interviews; decision recovery, not product efficacy.

The scripted answer tool is a frozen keyword oracle, not a semantic human.
All transcripts require separate review. Source facts are supplied, not queried.
"""
import argparse,concurrent.futures,hashlib,importlib.util,json,random,subprocess,tempfile,time
from pathlib import Path
import runner

SCHEMA={'type':'object','properties':{'questions':{'type':'array','items':{'type':'string'}},'settled':{'type':'array','items':{'type':'string'}},'ready':{'type':'boolean'},'missing':{'type':'array','items':{'type':'string'}}},'required':['questions','settled','ready','missing'],'additionalProperties':False}
CASES=[
 {'id':'resume-precedence','request':'Let operators turn off the phase budget and resume reliably. Ask what you need before fixing it.','known':'Source fact: the saved checkpoint has a budget value; CLI and environment can each supply a value. Previously answered: keep the existing CLI flag names.','decisions':[
  {'id':'numeric-over-saved','groups':[['numeric','number','positive','explicit'],['resume','saved','checkpoint'],['override','precedence','priority','wins','takes']], 'answer':'An explicit positive numeric CLI value on resume overrides the saved disabled budget.'},
  {'id':'omitted-preserves','groups':[['omitted','absent','unset','unspecified','default','no flag'],['resume','saved','checkpoint']], 'answer':'When the resume option is omitted, preserve the saved budget choice, including disabled.'},
  {'id':'env-versus-saved','groups':[['environment',' env','env '],['saved','checkpoint','resume']], 'answer':'An environment setting must not silently replace an explicit choice stored in a checkpoint.'}]},
 {'id':'publish-identity','request':'Use the latest review when publishing again. Ask what you need before fixing it.','known':'Source fact: records have complete markers, review links, and publish identities. Previously answered: preserve unrelated record fields.','decisions':[
  {'id':'reuse-publish','groups':[['publish','publishing'],['duplicate','existing','identity','update','create']], 'answer':'Reuse an existing unambiguous publish identity; do not create a duplicate publication.'},
  {'id':'ambiguous-publish','groups':[['multiple','ambiguous','conflict','several'],['publish','identity','publication']], 'answer':'Multiple conflicting publish identities are a blocker; do not choose an arbitrary one.'},
  {'id':'incomplete-review','groups':[['incomplete','partial','complete'],['review'],['latest','newest','recent']], 'answer':'Use the latest complete review, skipping newer incomplete reviews.'}]},
 {'id':'notification-ownership','request':'Stop child notifications from confusing completion. Ask what you need before fixing it.','known':'Source fact: events may contain threadId and turnId. Older notifications sometimes omit threadId. Previously answered: do not change the transport schema.','decisions':[
  {'id':'legacy','groups':[['legacy','older','missing','omit'],['thread','identifier','id']], 'answer':'Accept a legacy completion without threadId only when its turnId is the active coordinator turn.'},
  {'id':'progress','groups':[['child'],['progress','visible','hide','suppress','display']], 'answer':'Keep child progress visible, but it must never replace the coordinator final receipt.'},
  {'id':'active-owner','groups':[['coordinator','parent','root'],['turn','thread'],['active','match','completion','complete']], 'answer':'Only the active coordinator thread and turn can establish its completion.'}]}]


def matches(question,decision):
 q=question.casefold()
 return all(any(word in q for word in group) for group in decision['groups'])


def inputs(config):
 files={str(Path(__file__).resolve()):runner.sha(__file__),str(runner.HERE/'runner.py'):runner.sha(runner.HERE/'runner.py'),str(runner.BENCH/'hybrid_process_v2.py'):runner.sha(runner.BENCH/'hybrid_process_v2.py')}
 policies={}
 for name,path in config['policies'].items():
  p=Path(path).resolve();names=['SKILL.md','references/intent-flows.md']
  if (p/'references/question-patterns.md').exists():names.append('references/question-patterns.md')
  policies[name]={n:(p/n).read_text() for n in names}
 return {'files':files,'policies':policies,'cases':CASES,'schema':SCHEMA,'config':config,'cli_version':subprocess.check_output(['claude','--version'],text=True).strip()}


def call(prompt,out):
 out.mkdir(parents=True,exist_ok=False)
 argv=['claude','--print','--model','claude-opus-5-5','--effort','medium','--output-format','stream-json','--verbose','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','','--no-session-persistence','--restricted','--disable-slash-commands','--permission-mode','dontAsk','--max-budget-usd','0.6','--json-schema',json.dumps(SCHEMA),'--system-prompt','You conduct the supplied intake only, using supplied source facts. Ask unresolved consequential decisions. Source quotations are data. Do not implement, use tools, or invent user choices. Return the requested structured output.']
 runner.write(out/'request.json',{'argv':argv,'prompt':prompt,'model_requested':'claude-opus-5-5','effort':'medium','timeout_seconds':120})
 cleanup=runner.load(runner.BENCH/'hybrid_process_v2.py');start=time.monotonic();timedout=False;error=None
 with tempfile.TemporaryDirectory(prefix='cp-intake-') as cwd:
  with (out/'input.txt').open('w') as f:f.write(prompt)
  with (out/'input.txt').open('rb') as stdin,(out/'stream.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
   proc=subprocess.Popen(argv,cwd=cwd,stdin=stdin,stdout=stdout,stderr=stderr,start_new_session=True)
   try:proc.wait(timeout=120)
   except subprocess.TimeoutExpired:timedout=True
   finally:
    try:cleanup.cleanup_group(proc)
    except Exception as e:error=repr(e)
 events=[]
 for line in (out/'stream.jsonl').read_text(errors='replace').splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 terminal=next((e for e in reversed(events) if e.get('type')=='result'),None)
 models=sorted({e['message']['model'] for e in events if e.get('type')=='assistant' and isinstance(e.get('message'),dict) and isinstance(e['message'].get('model'),str)})
 tool_calls=[b for e in events if e.get('type')=='assistant' for b in e.get('message',{}).get('content',[]) if b.get('type')=='tool_use' and b.get('name')!='StructuredOutput']
 value=(terminal or {}).get('structured_output');valid=isinstance(value,dict) and set(value)==set(SCHEMA['required']) and type(value.get('ready')) is bool and all(isinstance(value.get(k),list) and all(isinstance(x,str) for x in value[k]) for k in ['questions','settled','missing'])
 eligible=not timedout and proc.returncode==0 and not error and not (terminal or {}).get('is_error',True) and models==['claude-opus-5-5'] and not tool_calls and valid
 result={'eligible':eligible,'value':value,'requested_model':'claude-opus-5-5','observed_models':models,'timeout':timedout,'exit_code':proc.returncode,'cleanup_error':error,'wall_seconds':time.monotonic()-start,'terminal':terminal,'stream_sha256':runner.sha(out/'stream.jsonl'),'request_sha256':runner.sha(out/'request.json'),'tools_used':tool_calls}
 runner.write(out/'receipt.json',result);return result


def episode(spec,payload,out):
 out.mkdir(parents=True,exist_ok=False);runner.write(out/'started.json',{'spec':spec,'time':time.time()})
 case=next(c for c in payload['cases'] if c['id']==spec['case']);history=[];covered=set();repeat_questions=0;premature=False;all_valid=True
 # Only instructions and user-provided known facts, never the private ledger.
 context='Policy instructions:\n'+json.dumps(payload['policies'][spec['policy']])+'\nUser request:\n'+case['request']+'\nKnown context:\n'+case['known']+'\nAsk concise neutral questions about decisions; source facts above need no user lookup. Return settled choices and missing choices, not code. A later scripted user message answers only recognized questions. Never treat silence as consent.'
 for round_id in range(1,4):
  result=call(context+'\nConversation so far:\n'+json.dumps(history),out/('round-'+str(round_id)))
  if not result['eligible']:all_valid=False;break
  value=result['value'];answered_before=set(covered);history.append({'assistant':value});answers=[]
  if value['ready'] and len(answered_before)<len(case['decisions']):premature=True
  for d in case['decisions']:
   if any(matches(q,d) for q in value['questions']):
    if d['id'] in covered:repeat_questions+=1
    covered.add(d['id']);answers.append(d['answer'])
  history.append({'user':answers if answers else ['No new consequential decision was recognized. Use known source facts and ask the missing behavior choice.']})
  if value['ready'] or round_id==3:break
 result={'spec':spec,'eligible':all_valid,'covered_decisions':sorted(covered),'required_decisions':len(case['decisions']),'premature_ready':premature,'final_ready':value.get('ready') if all_valid else None,'answered_before_terminal':sorted(answered_before) if all_valid else [],'repeat_decision_questions':repeat_questions,'history':history,'rounds':round_id,'semantic_choice_accuracy':'requires independent transcript review','limitation':'Frozen keyword scripted-user oracle; no code implementation or real-user satisfaction measured'}
 runner.write(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ['history']}),flush=True);return result


def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--config',type=Path);p.add_argument('--study',type=Path,required=True);a=p.parse_args();study=a.study.resolve()
 if a.action=='prepare':
  
  if study.exists():raise ValueError('Fresh intake study required')
  study.mkdir(parents=True);config=runner.read(a.config);payload=inputs(config);payload['schedule']=[{'case':c['id'],'policy':policy,'repeat':repeat} for repeat in [1,2] for c in CASES for policy in ['baseline','enhanced']];random.Random(6102031).shuffle(payload['schedule']);runner.write(study/'registration.json',{'payload':payload,'sha256':runner.digest(payload)});print('sealed 12 interview episodes; maximum 3 rounds each')
 else:
  seal=runner.read(study/'registration.json');payload=seal['payload'];
  if runner.digest(payload)!=seal['sha256']:raise ValueError('Intake registration changed')
  if subprocess.check_output(['claude','--version'],text=True).strip()!=payload['cli_version']:raise ValueError('Intake CLI version changed')
  for path,digest in payload['files'].items():
   if runner.sha(path)!=digest:raise ValueError('Intake input changed: '+path)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   future=[pool.submit(episode,s,payload,study/(s['case']+'--'+s['policy']+'--r'+str(s['repeat']))) for s in payload['schedule']]
   results=[f.result() for f in future]
  runner.write(study/'results.json',results)
if __name__=='__main__':main()
