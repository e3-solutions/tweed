"""Two fresh packet-only Opus proposals; same prompt/workspace/budget."""
import concurrent.futures,hashlib,importlib.util,json,pathlib
R=pathlib.Path(__file__).resolve().parents[2]; E=R/'.confidence/fork-flush'
s=importlib.util.spec_from_file_location('lead',R/'.confidence/lean-repair/lead_call.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.E=E
schema={'type':'object','properties':{'skill_md':{'type':'string'},'design_mechanism':{'type':'string'},'prediction':{'type':'string'},'tradeoffs':{'type':'array','items':{'type':'string'}},'preserved_invariants':{'type':'array','items':{'type':'string'}},'limitations':{'type':'array','items':{'type':'string'}}},'required':['skill_md','design_mechanism','prediction','tradeoffs','preserved_invariants','limitations'],'additionalProperties':False}
prompt=(E/'DESIGN-PROMPT.txt').read_text(); assert hashlib.sha256(prompt.encode()).hexdigest()==json.loads((E/'DESIGN-INPUT.json').read_text())['prompt_sha256']
def branch(name):
 r=m.call('design-'+name,E/'policies'/name,prompt,'claude-opus-5-5',180,1.5,schema=schema)
 term=r.get('terminal') or {}; valid=r['exit_code']==0 and not r['timed_out'] and r['observed_models']==['claude-opus-5-5'] and term.get('subtype')=='success' and term.get('is_error') is False and set(r['tool_names'])<= {'StructuredOutput'}
 result=term.get('structured_output')
 if valid and isinstance(result,dict) and isinstance(result.get('skill_md'),str):
  text=result['skill_md']; text=text if text.endswith('\n') else text+'\n'
  (E/'policies'/name/'SKILL.md').write_text(text)
  (E/'lead'/('design-'+name)/'PROPOSAL.json').write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps({'branch':name,'valid_provider_delivery':True,'skill_sha256':hashlib.sha256(text.encode()).hexdigest(),'bytes':len(text.encode())}),flush=True)
 else: print(json.dumps({'branch':name,'valid_provider_delivery':False}),flush=True)
 return valid
if __name__=='__main__':
 v=importlib.util.spec_from_file_location('verify',E/'verify_seal.py');vm=importlib.util.module_from_spec(v);v.loader.exec_module(vm);vm.verify()
 assert (E/'policies'/'branch-a'/'SKILL.md').read_bytes()==(E/'policies'/'incumbent'/'SKILL.md').read_bytes()
 assert (E/'policies'/'branch-b'/'SKILL.md').read_bytes()==(E/'policies'/'incumbent'/'SKILL.md').read_bytes()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(branch,['branch-a','branch-b']))
 assert all(results), 'invalid/interrupted proposals retained; no blind retry'
