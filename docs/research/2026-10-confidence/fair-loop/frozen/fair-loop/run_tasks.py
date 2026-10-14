"""Native Codex mechanical bridge; Opus controller owns admission and recovery.

Reuse existing source/patch capture and independent grading. No model fallback,
post-outcome policy changes, additional task selection or parallel dispatch.
"""
import argparse, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'.git').exists() and (p/'docs').is_dir())

def load(path):
    s = importlib.util.spec_from_file_location('fair_'+hashlib.sha256(str(path).encode()).hexdigest()[:8], path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

C = load(HERE/'runtime/controller.py')
R = load(ROOT/'docs/research/2026-10-confidence/claude-first-evaluation/runner.py')
G = load(R.BENCH/'grading_adapter.py')
read, write, sha = R.read, R.write, R.sha

def adapter(): return load(HERE/'runtime_adapter.py')

def delivery_gate(grade, receipt):
    """Backup composition guard: bare authored core omits terminal validity.

    Preserve its bytes and report that gap. The unchanged prospective contract
    permits an observed delivery or a known settled deadline, never unknown
    non-deadline delivery. This guard does not reinterpret artifact correctness.
    """
    if C.qualification(grade, {**receipt,'stage':'main'}): return False
    terminal = receipt.get('terminal')
    if terminal is None:
        return receipt.get('timed_out') is True and receipt.get('deadline_known') is True
    return (receipt.get('terminal_before_deadline') is True and
            receipt.get('reap',{}).get('returncode')==0 and
            terminal.get('type')=='result' and terminal.get('subtype')=='success' and
            terminal.get('is_error') is False and R.route({'backend':'claude','model':C.MODEL,'effort':'high'}).frozen.base.completion(terminal) is not None)

def continuation_decision(grade, receipt):
    if not delivery_gate(grade,receipt): return {'admit':False,'reason':'Unknown or invalid delivery provenance'}
    return C.continuation_decision(grade,receipt)

def capture(task, workspace, directory):
    directory.mkdir(parents=True, exist_ok=False)
    base = R.route({'backend':'claude','model':C.MODEL,'effort':'high'}).frozen.base
    base.safe_copy(workspace, directory/'source')
    patch, paths = R.load(R.HERE/'analyze.py').rebuild_patch(
        R.route({'backend':'claude','model':C.MODEL,'effort':'high'}),
        Path(task['base_snapshot']), directory/'source', directory/'production.patch', task['production_paths'])
    result = {'source_sha256':base.tree_digest(directory/'source'),
              'production_patch_sha256':hashlib.sha256(patch).hexdigest(),'production_paths':paths}
    write(directory/'receipt.json', result); return result

def evaluate(task, workspace, directory):
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); before = C.inventory(workspace); expected = G.raw_tree(workspace)
    p = subprocess.run([sys.executable,'-B',str(HERE/'evaluate.py'),'--workspace',str(workspace),
                        '--task-id',task['task_id']], cwd=HERE, capture_output=True, text=True, timeout=60)
    (directory/'grader.stdout').write_text(p.stdout); (directory/'grader.stderr').write_text(p.stderr)
    header = json.loads(p.stdout.splitlines()[0])
    binding = (C.inventory(workspace)==before and header.get('source_before_sha256')==expected and
               header.get('source_after_sha256')==expected and header.get('source_current') is True)
    write(directory/'receipt.json', {'exit_code':p.returncode,'wall_seconds':time.monotonic()-started,
                                    'header':header,'evaluator_sha256':sha(HERE/'evaluate.py'),
                                    'stdout_sha256':sha(directory/'grader.stdout'),'stderr_sha256':sha(directory/'grader.stderr'),
                                    'captured_grade_source_bound':binding,'expected_captured_source_sha256':expected})
    if not binding: raise ValueError('Independent grade does not bind unchanged captured source')
    return header

def verify(study):
    reg = read(study/'registration.json'); payload = reg['payload']
    if R.digest(payload) != reg['payload_sha256']: raise ValueError('Registration digest changed')
    for p, h in payload['files'].items():
        if sha(p) != h: raise ValueError('Frozen file changed: '+p)
    for p, tree in payload['trees'].items():
        if R.inventory(p) != tree: raise ValueError('Frozen input tree changed: '+p)
    for row in payload['cells']:
        C.check_seal(str(study/'cells'/row['cell_id']), row['task'], row['policy'])
    return payload

def prepare(config_path, study):
    config_path = config_path.resolve(); study = study.resolve()
    if study.exists(): raise ValueError('Fresh output directory required')
    config = read(config_path); tasks = read(HERE/'TASKS.json')['tasks']; study.mkdir(parents=True)
    indexed = {t['task_id']:t for t in tasks}; arms = {a['id']:a for a in config['arms']}
    if len(arms)!=2 or 'incumbent' not in arms or len(config['order'])!=4: raise ValueError('Exact paired roster required')
    rows=[]; seen=set()
    for task_id, arm_id in config['order']:
        if (task_id,arm_id) in seen: raise ValueError('Duplicate cell')
        seen.add((task_id,arm_id)); original = indexed[task_id]; arm = arms[arm_id]
        cell_id = task_id+'--'+arm_id; cell = study/'cells'/cell_id; cell.mkdir(parents=True)
        shutil.copytree(original['base_snapshot'],cell/'base')
        shutil.copytree(original['base_snapshot'],cell/'workspace')
        policy = cell/'workspace/.protocol'; shutil.copytree(config['common_docs'],policy)
        shutil.copy2(arm['skill_file'],policy/'SKILL.md')
        (cell/'workspace/AGENTS.md').write_text('Use .protocol/SKILL.md and the supplied controlled tools.\n')
        task = {**original,'base_snapshot':str(cell/'base'),'source_directory':str(cell/'base')}
        # Opus mutation controls run on private clones, never original frozen inputs.
        C.prepare(str(cell),task,str(policy))
        checked = adapter().transport_preflight(task,cell/'workspace',cell/'preflight')
        if checked.get('passed') is not True: raise ValueError('Composed route failed: '+cell_id)
        baseline = capture(task,cell/'workspace',cell/'baseline')
        prompt = ('Read .protocol/SKILL.md and relevant references. Complete this bounded real task and execute the visible checks. '
                  'Only the supplied coding tools are available; protocol CLI certificates and peer model calls are excluded. '
                  'Independent Codex checks occur outside your timer. Return the final JSON truthfully.\nTask:\n'+task['prompt']+
                  '\nVisible commands:\n'+json.dumps(task['visible_commands']))
        rows.append({'cell_id':cell_id,'task_id':task_id,'arm_id':arm_id,'task':task,'policy':str(policy),
                     'prompt':prompt,'baseline':baseline,'preflight_sha256':sha(cell/'preflight/receipt.json')})
    expected={(t['task_id'],a) for t in tasks for a in arms}
    if seen!=expected: raise ValueError('Incomplete paired roster')
    files={str(p.resolve()):sha(p) for p in [config_path,HERE/'TASKS.json',HERE/'evaluate.py',Path(__file__),HERE/'runtime_adapter.py',
                                            HERE/'EVALUATOR.md',HERE/'PREFLIGHT.json',*sorted((HERE/'runtime').glob('*.py')),
                                            *sorted(R.BENCH.glob('*.py')),R.HERE/'runner.py',R.HERE/'analyze.py']}
    trees={str((HERE/'oracles').resolve()):R.inventory(HERE/'oracles'),str(Path(config['common_docs']).resolve()):R.inventory(config['common_docs'])}
    for arm in arms.values(): files[str(Path(arm['skill_file']).resolve())]=sha(arm['skill_file'])
    for row in rows:
        files[str(study/'cells'/row['cell_id']/'inputs/SEAL.json')]=sha(study/'cells'/row['cell_id']/'inputs/SEAL.json')
        files[str(study/'cells'/row['cell_id']/'preflight/receipt.json')]=row['preflight_sha256']
    payload={'cells':rows,'files':files,'trees':trees,'limits':{'main':C.MAIN,'continuation':C.CONT,'global_model_limit':1},
             'author':'Native Codex mechanical bridge using actual Opus controller, qualified existing adapters and independent Codex grader'}
    write(study/'registration.json',{'payload':payload,'payload_sha256':R.digest(payload)})
    verify(study); return {'prepared':True,'cells':[r['cell_id'] for r in rows]}

def execute(study, cell_id, role):
    payload = verify(study); auth=read(study/'CALLS-AUTHORIZED.json')
    if auth.get('registration_sha256')!=sha(study/'registration.json'): raise ValueError('Missing exact root dispatch authorization')
    row=next(r for r in payload['cells'] if r['cell_id']==cell_id); cell=study/'cells'/cell_id
    workspace=cell/'workspace'; task=row['task']; stage=cell/role
    if stage.exists(): raise ValueError('Stage already assigned')
    prompt=row['prompt']; limits=C.MAIN if role=='main' else C.CONT
    if role=='continuation':
        first=read(cell/'main/result.json'); decision=continuation_decision(first['grade'],first['stage'])
        if not C.claim_continuation(str(cell),decision): raise ValueError('Continuation not admitted')
        if C.inventory(workspace)!=first['stage']['snapshot']['workspace']: raise ValueError('Workspace changed after critic')
        g=first['grade']; meta=g.get('local_module_binding') or {}
        # Adapt detailed grader identity to the controller's actor-safe status field.
        safe=C.feedback({**g,'local_module_binding':meta.get('binding_errors')==[]},first['stage'])
        packet={'cell_id':cell_id,'grade_receipt_sha256':sha(cell/'main/evaluation/receipt.json'),'decision':decision,'feedback':safe}
        write(cell/'continuation-feedback.json',packet)
        prompt+='\nContinue from the retained workspace with a fresh context. Actual independent feedback:\n'+json.dumps(safe)
    stage.mkdir(); before=capture(task,workspace,stage/'before'); policy_before=C.inventory(row['policy'])
    built=adapter().build_stage(task,workspace,stage/'call',prompt,limits)
    plain=C.stage_snapshot(str(workspace),row['policy'],policy_before,task['production_paths'])
    def snap():
        initial=C.inventory(workspace); captured=capture(task,workspace,stage/'after')
        frozen=C.inventory(stage/'after/source'); current=plain()
        current['source_stable']=current['source_stable'] and initial==frozen==current['workspace']
        current['capture_bound']=initial==frozen==current['workspace']
        if not current['capture_bound']: raise ValueError('Captured source differs from retained workspace')
        return {**current,'captured':captured,'after_directory':str(stage/'after')}
    receipt=C.run_stage(str(HERE),str(stage),role,built['argv'],limits['seconds'],cwd=str(workspace),env=built.get('env'),
                        service=built['service'],snapshot=snap)
    grade=evaluate(task,stage/'after/source',stage/'evaluation'); verify(study)
    write(stage/'bridge.json',built.get('metadata',{}))
    result={'cell_id':cell_id,'arm_id':row['arm_id'],'task_id':row['task_id'],'role':role,'stage':receipt,'grade':grade,
            'before':before,'after':receipt['snapshot']['captured'],'registration_sha256':sha(study/'registration.json')}
    write(stage/'result.json',result); return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','main','continuation']);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--config',type=Path);p.add_argument('--cell');a=p.parse_args()
    result=prepare(a.config,a.study) if a.action=='prepare' else verify(a.study) if a.action=='verify' else execute(a.study,a.cell,a.action)
    print(json.dumps({'action':a.action,'cell':a.cell,'product_passed':result.get('grade',{}).get('product_passed'),'prepared':result.get('prepared')}))
