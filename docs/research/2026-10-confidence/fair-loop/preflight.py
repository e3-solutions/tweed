"""No model calls. Authentic base/reference and deliberately labeled evaluator controls."""
import hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
manifest=json.loads((HERE/'TASKS.json').read_text());receipts=[]
def run(task,path,label,expect):
 argv=[sys.executable,str(HERE/'evaluate.py'),'--workspace',str(path),'--task-id',task['task_id']]
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=15);data=json.loads(p.stdout);record={'control':label,'task_id':task['task_id'],'expected_product_passed':expect,'argv':argv,'exit_code':p.returncode,'grade':data};receipts.append(record)
 assert data['product_passed']==expect,(label,data)
 if label in ('authentic-base','accepted-reference'):assert data['evaluation_status']=='observed';assert all(b['exit_code']==0 for b in data['execution_receipts']['baseline'])
 return data
for task in manifest['tasks']:
 run(task,task['base_snapshot'],'authentic-base',False);run(task,task['reference_snapshot'],'accepted-reference',True)
 with tempfile.TemporaryDirectory(prefix='fair-controls-') as tmp:
  base=Path(tmp);path=base/'wrong-fix';shutil.copytree(task['reference_snapshot'],path)
  source=path/(task['module']+'.py');text=source.read_text()
  if task['module']=='csv':
   # Only reader fixed: genuine writer iterator requirement is still broken.
   original=(Path(task['base_snapshot'])/'csv.py').read_text();text=text[:text.index('class DictWriter:')]+original[original.index('class DictWriter:'):]
  else:
   # Overbroad default: treat spaces as delimiters even for unconfigured callers.
   text=text.replace("delimiters=('=', ':'),", "delimiters=(' ', '=', ':'),")
  source.write_text(text);run(task,path,'deliberate-wrong-fix',False)
  equivalent=base/'equivalent';shutil.copytree(task['reference_snapshot'],equivalent);s=equivalent/(task['module']+'.py');text=s.read_text();text=text.replace('_dict_to_list','_field_mapping_values') if task['module']=='csv' else text.replace('_OPT_NV_TMPL','_OPTION_WITHOUT_VALUE_TEMPLATE').replace('_OPT_TMPL','_OPTION_TEMPLATE');s.write_text(text);nested=equivalent/'package/tests';nested.mkdir(parents=True);(nested/'test_added.py').write_text('# Conventional actor test addition is permitted.\n');(equivalent/'tests/test_visible.py').write_text('# Actor may update product tests; independent baseline is projected.\n');run(task,equivalent,'equivalent-source-and-conventional-test-edits',True)
  origin=base/'forged-origin';shutil.copytree(task['reference_snapshot'],origin);target=next(p for p in task['forbidden_runtime_read_paths'] if p.endswith('.py'));api='DictReader.__init__' if task['module']=='csv' else 'ConfigParser.read_file';source=origin/(task['module']+'.py');source.write_text(source.read_text()+'\n'+api+'.__code__ = '+api+'.__code__.replace(co_filename='+repr(target)+')\n');d=run(task,origin,'deliberate-installed-origin-forgery',False);assert d['local_module_binding']['binding_errors']
  syntax=base/'source-syntax-error';shutil.copytree(task['reference_snapshot'],syntax);(syntax/(task['module']+'.py')).write_text('def broken(:\n');d=run(task,syntax,'deliberate-actor-local-syntax-error',False);assert d['evaluation_status']=='observed' and any(row['id']=='source-load' for row in d['failed_requirements'])
  forged=base/'installed-substitution';shutil.copytree(task['reference_snapshot'],forged);target=next(p for p in task['forbidden_runtime_read_paths'] if p.endswith('.py'))
  (forged/(task['module']+'.py')).write_text('import importlib.util\n_s=importlib.util.spec_from_file_location("installed_target",'+repr(target)+')\n_m=importlib.util.module_from_spec(_s)\n_s.loader.exec_module(_m)\nglobals().update({k:v for k,v in vars(_m).items() if not k.startswith("__")})\n')
  d=run(task,forged,'deliberate-installed-substitution',False);assert d['evaluation_status']=='unknown' and not d['failed_requirements']
result={'status':'pass','model_calls':0,'task_manifest_sha256':hashlib.sha256((HERE/'TASKS.json').read_bytes()).hexdigest(),'evaluator_sha256':hashlib.sha256((HERE/'evaluate.py').read_bytes()).hexdigest(),'controls':receipts,'meaning':'Design/calibration, not measured solving efficacy. Unknown installed-substitution result is deliberate sandbox refusal, not behavioral failure.'}
(HERE/'PREFLIGHT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'controls':len(receipts),'seconds':sum(c['grade']['execution_receipts']['owner']['wall_seconds'] for c in receipts)}))
