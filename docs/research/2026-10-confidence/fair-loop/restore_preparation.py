"""Restore exact frozen host-specific inputs, without executing model calls/tests.

Use only in a checkout at the original registered absolute repository path.
Other locations require explicit new registration, not rewriting original seals.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--repository',required=True);args=p.parse_args();root=Path(args.repository).resolve();mapping=json.loads((HERE/'FROZEN-SOURCE-MAP.json').read_text());private=root/'.confidence/fair-loop'
for row in mapping['frozen_files']:
 source=Path(row['source'])
 if not source.is_relative_to(root):raise SystemExit('Exact registered repository path is required: '+str(source))
 if row['published'].startswith('repository:'):
  current=root/row['published'].split(':',1)[1];assert current.exists() and sha(current)==row['sha256'];continue
 published=HERE/row['published'];assert sha(published)==row['sha256'];source.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(published,source)
for p in (HERE/'frozen/fair-loop').rglob('*'):
 if p.is_file():target=private/p.relative_to(HERE/'frozen/fair-loop');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
shutil.copy2(HERE/'prepared/registration.json',private/'study-v2/registration.json')
shutil.copytree(HERE/'setup-handling/scope-amendment',private/'scope-amendment',dirs_exist_ok=True)
for cell in (HERE/'prepared/cells').iterdir():
 target=private/'study-v2/cells'/cell.name;shutil.copytree(cell,target,dirs_exist_ok=True)
 # Clean actor input is the saved baseline source plus its pinned doc-only policy.
 workspace=target/'workspace'
 if workspace.exists():raise SystemExit('Refusing to overwrite retained actor workspace: '+str(workspace))
 shutil.copytree(target/'baseline/source',workspace)
print(json.dumps({'restored':str(private),'executed_provider_calls':0,'executed_grader_calls':0}))
