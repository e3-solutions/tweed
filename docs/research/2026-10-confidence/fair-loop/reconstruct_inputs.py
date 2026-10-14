"""Host-specific reconstruction from public frozen inputs, no model invocation."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repository',required=True);args=p.parse_args();repo=Path(args.repository).resolve();bundle=Path(__file__).resolve().parent;dest=repo/'.confidence/fair-loop';dest.mkdir(parents=True,exist_ok=True)
for name in ('EVALUATOR.md','TASKS.json','evaluate.py','preflight.py'):
 shutil.copyfile(bundle/name,dest/name)
shutil.copytree(bundle/'oracles',dest/'oracles',dirs_exist_ok=True)
data=json.loads((dest/'TASKS.json').read_text());amendments=[]
for task in data['tasks']:
 for field,suffix in [('base_snapshot','base'),('source_directory','base'),('reference_snapshot','head')]:
  old=task[field];task[field]=str(dest/'oracles'/task['task_id']/suffix)
  if old!=task[field]:amendments.append({'task':task['task_id'],'field':field,'original':old,'reconstructed':task[field]})
 task['oracle_argv']=['python3',str(dest/'evaluate.py'),'--task-id',task['task_id'],'--workspace','{workspace}']
 for suffix,key in [('base','source_sha256'),('head','reference_source_sha256')]:
  source=dest/'oracles'/task['task_id']/suffix/(task['module']+'.py');assert hashlib.sha256(source.read_bytes()).hexdigest()==task[key]
 assert hashlib.sha256((dest/task['private_module']).read_bytes()).hexdigest()==task['owner_sha256']
 if not Path(task['interpreter']).exists():raise SystemExit('Registered host interpreter unavailable: '+task['interpreter'])
(dest/'TASKS.json').write_text(json.dumps(data,indent=2)+'\n');(dest/'RECONSTRUCTION.json').write_text(json.dumps({'path_amendments':amendments,'meaning':'Original frozen public manifest retained; reconstructed paths only. Exact host runtimes and macOS sandbox required.'},indent=2)+'\n')
print(dest)
