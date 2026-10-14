"""Export exact qualified preparation inputs; never invoke providers or graders."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'.git').exists());PRIVATE=ROOT/'.confidence/fair-loop'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);assert sha(src)==sha(dst)
def tree(src,dst):
 for p in sorted(src.rglob('*')):
  if p.is_file() and not any(x in ('__pycache__','.git') for x in p.relative_to(src).parts):copy(p,dst/p.relative_to(src))
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
registration=json.loads((PRIVATE/'study-v2/registration.json').read_text());payload=registration['payload'];mapping=[]
for value,pin in payload['files'].items():
 src=Path(value);assert sha(src)==pin,('Frozen file drift',value)
 if src.is_relative_to(PRIVATE):target=HERE/'frozen'/'fair-loop'/src.relative_to(PRIVATE);copy(src,target);public=str(target.relative_to(HERE))
 else:public='repository:'+str(src.relative_to(ROOT));assert src.is_relative_to(ROOT)
 mapping.append({'source':value,'published':public,'sha256':pin,'mode':oct(src.stat().st_mode&0o777)})
for value,inventory in payload['trees'].items():
 src=Path(value);target=HERE/'frozen'/'fair-loop'/src.relative_to(PRIVATE)
 for name,pin in inventory.items():
  p=src/name;assert sha(p)==pin['sha256'] and p.stat().st_mode&0o777==pin['mode'];copy(p,target/name)
copy(PRIVATE/'study-v2/registration.json',HERE/'prepared/registration.json')
for cell in payload['cells']:
 source=PRIVATE/'study-v2/cells'/cell['cell_id'];target=HERE/'prepared/cells'/cell['cell_id']
 for name in ('base','baseline','inputs','preflight','runs'):tree(source/name,target/name)
 # The clean baseline already binds original actor inputs; no mutable live workspace export.
for name in ('research_call.py','development_call.py','development_continue_call.py','development_patch_call.py','development_tool_server.py'):
 copy(PRIVATE/name,HERE/'author-transports'/name)
for name in ('PROMPT.txt','CONTINUATION-PROMPT.txt','INPUT-PINS.json','OWNER-UPDATE.json','CONTINUATION-AUTHORIZATION.json'):
 p=PRIVATE/'development'/name
 if p.exists():copy(p,HERE/'author-transports/development'/name)
p=PRIVATE/'research/PROMPT.txt'
if p.exists():copy(p,HERE/'author-transports/research/PROMPT.txt')
# Preserve the aborted setup, which had no task inference, separately from qualified v2.
if (PRIVATE/'study/registration.json').exists():copy(PRIVATE/'study/registration.json',HERE/'setup-handling/failed-study/registration.json')
for cell in (PRIVATE/'study/cells').iterdir():
 if cell.is_dir():
  for name in ('preflight','inputs','runs'):tree(cell/name,HERE/'setup-handling/failed-study/cells'/cell.name/name)
tree(PRIVATE/'native-preflight/python39-launcher',HERE/'setup-handling/python39-file-capture')
for p in PRIVATE.glob('REVIEW*.md'):copy(p,HERE/p.name)
for p in (PRIVATE/'native-preflight/author-controls-v2').iterdir():
 if p.is_file():copy(p,HERE/'preparation/author-core-controls'/p.name)
write(HERE/'FROZEN-SOURCE-MAP.json',{'registration_sha256':sha(PRIVATE/'study-v2/registration.json'),'frozen_files':mapping,'composition':'Actual Opus authored controller+cleanup; native Codex mechanical adapter/driver using existing qualified helpers; independent Codex owner grader. Original/partial author stages retained separately.','host_specific_paths':True,'task_inference_run_by_exporter':False,'grader_rerun_by_exporter':False})
print(json.dumps({'frozen_files':len(mapping),'prepared_cells':len(payload['cells']),'registration_sha256':sha(PRIVATE/'study-v2/registration.json')}))
