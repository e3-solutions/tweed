#!/usr/bin/env python3
"""Reconstruct source/policy bytes from public Git objects, without model calls.

This is input reconstruction, not a portable one-command benchmark. Frozen
registrations retain host-specific paths and runtime versions. Choose a NEW
output directory; existing study/evidence directories are never overwritten.
"""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def load(path):
 s=importlib.util.spec_from_file_location('source_reconstruction',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
PREP=load(ROOT/'docs/research/2026-10-confidence/pr-benchmark/tasks/prepare.py')
SANDBOX=load(ROOT/'docs/research/2026-10-confidence/pr-benchmark/tasks/oracle_runner.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def subtree(commit,prefix,destination):
 rows=subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-rz','-r',commit,prefix]).split(b'\0')
 for row in rows:
  if not row:continue
  metadata,name=row.split(b'\t',1);mode,kind,oid=metadata.decode().split();name=name.decode();relative=Path(name).relative_to(prefix)
  if kind!='blob' or mode not in ('100644','100755'):raise ValueError('Nonregular input member: '+name)
  target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(subprocess.check_output(['git','-C',str(ROOT),'cat-file','blob',oid]));target.chmod(0o755 if mode=='100755' else 0o644)
def reconstruct(output):
 output=Path(output).resolve()
 if output.exists():raise ValueError('Fresh output required')
 output.mkdir(parents=True);tasks=json.loads((HERE/'TASKS.json').read_text())['tasks'];controls=[]
 for task in tasks:
  directory=output/'oracles'/('pr-'+task['task_id'].removeprefix('tweed-pr'))
  for side in ('base','head'):
   revision=task['base_sha'] if side=='base' else task['head_sha'];destination=directory/side
   PREP.export_snapshot(ROOT,revision,destination,False)
   if task['task_id']=='tweed-pr45':subtree(revision,'skills/confidence-protocol/tests',destination/'skills/confidence-protocol/tests')
   actual=PREP.tree_sha256(destination);expected=task['source_sha256'] if side=='base' else task['head_source_sha256']
   if actual!=expected:raise ValueError('Source mismatch: '+task['task_id']+'/'+side)
   controls.append({'task_id':task['task_id'],'side':side,'commit':revision,'tree_sha256':actual})
  SANDBOX.copy_candidate(directory/'base',directory/'head',directory/'reference',task['production_paths'])
 policies=output/'policies';inc=policies/'incumbent';subtree('4758787015f05a95ea38896f57a462316b3d9d80','skills/confidence-protocol',inc)
 pins=json.loads((HERE/'INCUMBENT.json').read_text())['skill_file_sha256']
 for relative,expected in pins.items():
  if sha(inc/relative)!=expected:raise ValueError('Incumbent input mismatch: '+relative)
 for arm in ('branch-a','branch-b'):
  shutil.copytree(inc,policies/arm);shutil.copy2(HERE/'designs'/f'{arm}.md',policies/arm/'SKILL.md')
  expected=next(b['skill_sha256'] for b in json.loads((HERE/'DESIGN-RESULTS.json').read_text())['branches'] if b['arm']==arm)
  if sha(policies/arm/'SKILL.md')!=expected:raise ValueError('Candidate output mismatch')
 receipt={'source_controls':controls,'common_protocol_commit':'4758787015f05a95ea38896f57a462316b3d9d80','all_expected_file_and_tree_hashes_match':True,'model_calls':0,'scope':'Reconstructed input bytes only; host-specific frozen runtime/registrations remain separate'}
 (output/'INPUT-RECONSTRUCTION.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);print(json.dumps(reconstruct(p.parse_args().output)))
