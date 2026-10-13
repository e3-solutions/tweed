#!/usr/bin/env python3
"""Six-cell sealed staged evaluation, using the existing qualified adapters.

No actor controls scheduling. Original controllers/studies remain unchanged.
Prepare/controls/analyze are offline; run needs an explicit committed activation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = next(parent for parent in HERE.parents if (parent/'.git').exists() and (parent/'docs').is_dir())
OLD = ROOT / 'docs/research/2026-10-confidence/claude-first-evaluation'

def load(path):
    spec = importlib.util.spec_from_file_location('lean_' + uuid.uuid4().hex, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

sys.path.insert(0,str(HERE))
r = load(OLD / 'runner.py')
a = load(OLD / 'analyze.py')
read, write, sha, digest, inventory = r.read, r.write, r.sha, r.digest, r.inventory
DEV = dict(backend='claude', model='claude-opus-5-5', effort='high')
REVIEW = dict(backend='codex', model='gpt-6-astra', effort='medium')
CAPS = {'main': (480, 4), 'review': (180, None), 'closure': (300, 3)}
FEEDBACK = 'executed_public_boundary_diagnostics_no_oracle_source'

def require(value, reason):
    if not value: raise ValueError(reason)

def claim(path, identity):
    """Create before any operation; even crashed stages cannot be retried."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=False)
    write(path / 'started.json', dict(identity=identity, started_at_unix=time.time()))
    return path

def validate_roster(requests, tasks):
    expected = {(t['task_id'], arm, 1) for t in tasks for arm in ('original', 'revised')}
    actual = [(q.get('task_id'), q.get('arm_id'), q.get('repeat')) for q in requests]
    require(len(tasks) == 3 and len({t['task_id'] for t in tasks}) == 3, 'Three unique tasks required')
    require(len(actual) == 6 and len(set(actual)) == 6 and set(actual) == expected, 'Six exact single-trial cells required')
    require(all(q['trial_id'] == q['task_id'] + '--' + q['arm_id'] + '--r1' for q in requests), 'Noncanonical identity')

def bounded_time(cap, deadline):
    remaining = deadline - time.time()
    require(remaining > 0, 'Aggregate cell deadline exhausted')
    return min(cap, remaining)

def snapshot(base, task, workspace, directory):
    target = directory / 'source'; base.safe_copy(workspace, target)
    patch, paths = base.build_patch(Path(task['base_snapshot']), target, directory / 'submitted.patch', task['production_paths'])
    return dict(source_sha256=base.tree_digest(target), patch_sha256=hashlib.sha256(patch).hexdigest(),
                submitted_paths=paths, scope_violations=base.scope_diff(Path(task['base_snapshot']), target, task['production_paths']))

def execute(adapter, workspace, directory, commands, deadline):
    """Same command service, readonly source and outside scratch as actor tools."""
    claim(directory, 'executed-checks')
    base = adapter.frozen.base; output = []
    for index, item in enumerate(commands):
        item = {'id': 'visible-' + str(index), 'argv': item} if isinstance(item, list) else item
        argv = item['argv']; error = a.command_guard_error('run_command', {'argv': argv})
        require(error is None, 'Unsafe witness/check command')
        mapped = {'python3':sys.executable, 'python':sys.executable, 'git':base.GIT, 'bash':'/bin/bash', 'sh':'/bin/sh'}
        command = [mapped.get(argv[0], argv[0]), *argv[1:]]
        ident = 'check-' + str(index); timeout = bounded_time(min(item.get('timeout_seconds', 30), 90), deadline)
        write(directory / (ident + '.command-request.json'), {'id': ident, 'argv': command, 'timeout': timeout})
        before = base.tree_digest(workspace)
        base.service_commands(directory, workspace, workspace / '.trial-tmp', True, deadline)
        result = read(directory / (ident + '.command-response.json'))
        result.update(id=item['id'], requested_argv=argv, source_sha256=before, source_unchanged=before == base.tree_digest(workspace))
        result['passed'] = result.get('exit_code') == 0 and result.get('timed_out') is False and result['source_unchanged']
        output.append(result)
    write(directory / 'receipt.json', output)
    return output

def grade(adapter, task, source, directory, deadline):
    """Reuse existing grader; clamp its fixed 180s wait to aggregate deadline."""
    claim(directory, 'frozen-public-boundary-grade')
    grader = adapter.frozen.grader; processes = adapter.frozen.processes
    real = grader.subprocess
    if not isinstance(real, processes.SubprocessProxy): real = processes.SubprocessProxy(real)
    class Bounded:
        def __getattr__(self, key): return getattr(real, key)
        def Popen(self, *args, **kwargs):
            process = real.Popen(*args, **kwargs); original = process.wait
            def wait(timeout=None):
                return original(timeout=min(timeout if timeout is not None else 180, max(.01, deadline-time.time())))
            process.wait = wait
            return process
    grader.subprocess = Bounded()
    before=adapter.frozen.base.tree_digest(source)
    try: result = r.invoke_oracle(adapter, Path(task['oracle_script']), source, directory)
    finally: grader.subprocess = real
    result['source_sha256'] = before
    require(adapter.frozen.base.tree_digest(source)==before,'Grader source changed during execution')
    write(directory / 'receipt.json', result)
    return result

def qualify_stage(adapter, stage, local, route):
    stage['backend'] = route['backend']
    q = r.qualification(stage, local, route, adapter)
    if stage.get('requested_effort') != route['effort']:
        q['failures'].append('requested_effort_mismatch'); q['eligible'] = False
    return q

def invoke(adapter, workspace, directory, prompt, role, deadline, payload):
    claim(directory, role)
    route = REVIEW if role == 'review' else DEV
    readonly = role == 'review'; alias = 'astra' if readonly else 'opus'
    local = adapter.local_mcp_probe(alias, workspace, directory / 'qualification', readonly=readonly)
    require(local.get('passed') is True, 'Local transport failed before inference')
    cap, budget = CAPS[role]; seconds = bounded_time(cap, deadline)
    before = adapter.frozen.base.tree_digest(workspace)
    if readonly:
        info = payload['review_inventory']
        stage = adapter.frozen.backend.codex_call(workspace, directory / 'call', prompt,
            catalog=Path(info['catalog']), timeout=seconds, deadline=deadline, readonly=True,
            inventory_receipt=info['receipt'], review_callback=lambda *_: {'available': False, 'reason': 'Staged reviewer only'})
    else:
        stage = adapter.frozen.base.claude_call(workspace, directory / 'call', prompt, budget, seconds, deadline)
    q = qualify_stage(adapter, stage, local, route)
    stage.update(qualification=q, source_sha256_at_launch=before, source_sha256_after=adapter.frozen.base.tree_digest(workspace))
    if readonly and before != stage['source_sha256_after']:
        q['failures'].append('readonly_review_source_changed'); q['eligible'] = False
    stage['artifact_files']={str(path.relative_to(directory)):sha(path) for path in sorted(directory.rglob('*')) if path.is_file() and path != directory/'receipt.json'}
    write(directory / 'receipt.json', stage)
    return stage

def witness_safe(argv):
    return isinstance(argv,list) and len(argv) in (3,4) and argv[0] in ('python3','python',sys.executable) and (argv[1:2]==['-c'] and len(argv)==3 or argv[1:3]==['-B','-c'] and len(argv)==4) and all(isinstance(value,str) and '\0' not in value for value in argv)

def witness_projection(base,task,candidate,target):
    """Freeze tests/dependencies to baseline, overlay candidate production only."""
    base.safe_copy(Path(task['base_snapshot']),target)
    candidates=set(task['production_paths'])
    candidates.update(path.name for path in candidate.glob('*.py') if not (Path(task['base_snapshot'])/path.name).exists())
    for relative in sorted(candidates):
        source=candidate/relative;destination=target/relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and not source.is_symlink(),'Witness projection path unsafe')
        if source.is_file():destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        elif destination.is_file():destination.unlink()
    return base.tree_digest(target)

def witnesses_execute(adapter,task,candidate,directory,commands,deadline):
    with tempfile.TemporaryDirectory(prefix='cp-frozen-witness-') as temporary:
        source=Path(temporary).resolve()/'source'
        source_sha=witness_projection(adapter.frozen.base,task,candidate,source)
        rows=execute(adapter,source,directory,commands,deadline)
        adapter.frozen.base.safe_copy(source,directory/'source')
    return rows,source_sha

def review_payload(stage):
    terminal = r.terminal(stage)
    require(stage.get('qualification', {}).get('eligible') is True and terminal is not None and terminal['complete'] is True and terminal['remaining'] == [], 'Independent review incomplete/unqualified')
    result = json.loads(terminal['summary'])
    require(set(result) == {'findings', 'scope_limits'} and isinstance(result['findings'], list) and isinstance(result['scope_limits'], list), 'Review schema invalid')
    ids = []
    for finding in result['findings']:
        require(set(finding) == {'id','blocking','path','line','claim','witness'}, 'Finding schema invalid')
        require(isinstance(finding['id'], str) and re.fullmatch(r'[a-z0-9-]+',finding['id']), 'Finding ID unsafe')
        require(type(finding['blocking']) is bool and isinstance(finding['path'],str) and type(finding['line']) is int and finding['line']>0 and isinstance(finding['claim'],str), 'Finding fields invalid')
        witness = finding['witness']
        require(witness is None or witness_safe(witness), 'Finding witness unsafe')
        ids.append(finding['id'])
    require(len(set(ids)) == len(ids), 'Duplicate review findings')
    return result

def unresolved_findings(findings, before, after):
    initial = {v['id']:v for v in before}; final = {v['id']:v for v in after}
    unresolved = []
    for finding in findings:
        if not finding['blocking']: continue
        left, right = initial.get(finding['id'],{}), final.get(finding['id'],{})
        # Only an actually failing witness followed by a bound pass demonstrates
        # correction. Mere inability, an always-passing command or prose does not.
        failed = type(left.get('exit_code')) is int and left['exit_code'] != 0 and left.get('timed_out') is False and left.get('source_unchanged') is True
        if finding['witness'] is None or not failed or right.get('passed') is not True:
            unresolved.append(finding['id'])
    return unresolved

def main_provenance(stage):
    q=stage.get('qualification',{})
    failures=q.get('failures')
    return q.get('eligible') is True or (isinstance(failures,list) and bool(failures) and set(failures)<= {'stage_did_not_finish','terminal_missing_or_invalid'} and type(stage.get('timed_out')) is bool and type(stage.get('process_exit')) is int)

def accepted(receipt):
    final = receipt.get('closure',{}); terminal = r.terminal(final)
    return bool(receipt.get('status') == 'completed' and main_provenance(receipt.get('main',{})) and receipt.get('first',{}).get('scope_violations')==[] and final.get('qualification',{}).get('eligible') is True
        and terminal is not None and terminal['complete'] is True and terminal['remaining'] == []
        and receipt.get('review_qualified') is True and receipt.get('final_grade',{}).get('oracle_passed') is True
        and receipt.get('final_binding_valid') is True and receipt.get('final_checks_passed') is True
        and receipt.get('unresolved_findings') == [] and receipt.get('final',{}).get('scope_violations') == [])

def feedback(checks, result, directory):
    disclosed_checks=[{key:value for key,value in check.items() if key in ('id','requested_argv','exit_code','timed_out','wall_seconds','output','error_output','passed')} for check in checks]
    disclosed_grade={key:value for key,value in result.items() if key in ('oracle_passed','exit_code','timed_out','wall_seconds','header')}
    return {'executed_checks':disclosed_checks,'frozen_grade':disclosed_grade,
        'grade_stdout':(directory/'grader.stdout').read_text(errors='replace')[-60000:],
        'grade_stderr':(directory/'grader.stderr').read_text(errors='replace')[-20000:]}

def sanitize(base, task, workspace):
    base.safe_copy(Path(task['base_snapshot']), workspace)
    for pattern in ('AGENTS.md','CLAUDE.md','.claude','.codex','.agents','.git'):
        for path in list(workspace.rglob(pattern)):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    (workspace/'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
    ignore=workspace/'.gitignore'; ignore.write_text((ignore.read_text() if ignore.exists() else '')+'\n.trial-tmp/\n.confidence/\n')
    scratch=workspace/'.trial-tmp';scratch.mkdir(exist_ok=True)
    for args in (['init','-q'],['add','.'],['-c','user.name=Comparison','-c','user.email=comparison@example.invalid','commit','-qm','Frozen base']):
        subprocess.run([base.GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',*args],cwd=workspace,env=base.safe_env(workspace,scratch),capture_output=True,check=True)

def runtime(route):
    adapter = r.route(route)
    adapter.frozen.backend.service_reviews = r.deny_reviews
    original = adapter.frozen.base.service_commands
    def service(control,workspace,temporary,readonly,deadline):
        r.deny_reviews(control,workspace,None,deadline)
        return original(control,workspace,temporary,readonly,deadline)
    adapter.frozen.base.service_commands = service
    return adapter

def run_cell(request, task, arm, payload, study):
    out = study/'trials'/request['trial_id']
    if out.exists(): return {'trial_id':request['trial_id'],'status':'preserved_previously_started','accepted':False}
    claim(out, request)
    receipt = {**request,'status':'started','accepted':False,'registration_sha256':sha(study/'registration.json')}
    deadline = time.time()+payload['config']['aggregate_seconds']
    try:
        verify(study); adapter=runtime(DEV);base=adapter.frozen.base
        with tempfile.TemporaryDirectory(prefix='cp-lean-cell-') as temp:
            workspace=Path(temp).resolve()/'workspace';sanitize(base,task,workspace)
            r.mount(base,payload['config']['toolkit_directory'],arm['policy_directory'],workspace)
            facts=[{key:fact[key] for key in ('path','start_line','end_line','quote')} for fact in read(payload['config']['discovery_receipts'][task['task_id']])['validated_facts']]
            common='Task:\n'+task['prompt']+'\nVisible checks:\n'+json.dumps(task['test_commands'])+'\nShared checked Haiku source facts:\n'+json.dumps(facts)
            prompt=('Read .protocol/SKILL.md and relevant references. Follow the full supplied guidance. '
                'This controlled delegated lifecycle supplies bounded Haiku discovery and an independent Codex review after your stage. '
                'request_review is unavailable inside your timer. Finish implementation and execute checks truthfully.\n'+common)
            receipt['main']=invoke(adapter,workspace,out/'main',prompt,'main',deadline,payload)
            receipt['first']=snapshot(base,task,workspace,claim(out/'first','first-artifacts'))
            commands=task['test_commands']+task.get('required_checks',[])+payload['config'].get('policy_checks',[])
            receipt['first_checks'],receipt['checks_first_source_sha256']=witnesses_execute(adapter,task,workspace,out/'first-checks',commands,deadline)
            receipt['first_grade']=grade(adapter,task,out/'first'/'source',out/'first-grade',deadline)
            receipt['first_pass']=receipt['main']['qualification']['eligible'] and receipt['first_grade']['oracle_passed'] is True and all(v['passed'] for v in receipt['first_checks']) and not receipt['first']['scope_violations']
            # Fresh reviewer checkout excludes policy, protocol artifacts and actor
            # instructions. It receives only task/source/diff/executed diagnostics.
            review_workspace=Path(temp).resolve()/'review';base.safe_copy(workspace,review_workspace)
            for name in ('.protocol','.confidence','AGENTS.md'):
                path=review_workspace/name
                if path.is_dir():shutil.rmtree(path)
                elif path.exists():path.unlink()
            base.safe_copy(review_workspace,out/'review-source')
            receipt['review_source_sha256']=base.tree_digest(out/'review-source')
            check_feedback=feedback(receipt['first_checks'],receipt['first_grade'],out/'first-grade')
            blind='Independent read-only review. Do not implement or consult policy. Task:\n'+task['prompt']+'\nCandidate diff:\n'+(out/'first'/'submitted.patch').read_text()+'\nExecuted checks/grade:\n'+json.dumps(check_feedback)
            blind+='\nReturn complete/summary/remaining. complete means review finished. summary MUST be JSON string with exactly findings (list) and scope_limits (list of strings). Each finding has exactly id (lowercase hyphenated), blocking (bool), path, line (positive int), claim, witness (argv list or null). Witness must fail on current candidate and pass when corrected; use only self-contained python3 -B -c INLINE_CODE argv. Witnesses execute on candidate production over immutable baseline tests, without actor scratch or added/modified tests. Absent executable witness keeps blocking finding unresolved. Remaining holds unfinished review work.'
            reviewer=runtime(REVIEW);receipt['review']=invoke(reviewer,review_workspace,out/'review',blind,'review',deadline,payload)
            report=review_payload(receipt['review']);receipt['review_qualified']=True;receipt['review_findings']=report
            witnesses=[{'id':f['id'],'argv':f['witness'],'timeout_seconds':30} for f in report['findings'] if f['blocking'] and f['witness'] is not None]
            receipt['witness_before'],receipt['witness_first_source_sha256']=witnesses_execute(adapter,task,workspace,out/'witness-before',witnesses,deadline)
            closure_prompt=prompt+'\nIndependent Codex review:\n'+json.dumps(report)+'\nExecuted feedback:\n'+json.dumps(check_feedback)+'\nExecuted review witnesses:\n'+json.dumps(receipt['witness_before'])+'\nThis is your sole final repair/verification stage. Correct defects and missing required proof, rerun checks, and report remaining gaps truthfully. If already correct, verify and close without a gratuitous edit. No new reviewer is available.'
            receipt['closure']=invoke(adapter,workspace,out/'closure',closure_prompt,'closure',deadline,payload)
            receipt['final']=snapshot(base,task,workspace,claim(out/'final','final-artifacts'))
            receipt['actual_repair']=receipt['first']['patch_sha256']!=receipt['final']['patch_sha256']
            receipt['final_checks'],receipt['checks_final_source_sha256']=witnesses_execute(adapter,task,workspace,out/'final-checks',commands,deadline)
            receipt['witness_after'],receipt['witness_final_source_sha256']=witnesses_execute(adapter,task,workspace,out/'witness-after',witnesses,deadline)
            receipt['unresolved_findings']=unresolved_findings(report['findings'],receipt['witness_before'],receipt['witness_after'])
            receipt['final_grade']=grade(adapter,task,out/'final'/'source',out/'final-grade',deadline)
            receipt['final_binding_valid']=receipt['final']['source_sha256']==receipt['final_grade']['source_sha256'] and sha(out/'final'/'submitted.patch')==receipt['final']['patch_sha256']
            receipt['final_checks_passed']=all(v['passed'] for v in receipt['final_checks'])
            receipt['status']='completed' if time.time()<=deadline else 'aggregate_timeout'
            receipt['accepted']=accepted(receipt)
    except Exception as error:
        receipt.update(status='infrastructure_or_artifact_error',error=type(error).__name__+': '+str(error))
    receipt.update(ended_at_unix=time.time(),aggregate_deadline_unix=deadline)
    write(out/'receipt.json',receipt);return receipt

def prepare(config_path, study):
    config_path=Path(config_path).resolve();study=Path(study).resolve();config=read(config_path)
    require(not study.exists(),'Fresh study directory required')
    require(config.get('feedback_rule')==FEEDBACK,'Feedback disclosure rule must be explicit')
    require(not config.get('policy_checks'),'Protocol ledger checks are outside this scoped behavioral loop')
    require(config.get('aggregate_seconds')==1100,'Aggregate cap must be 1100 seconds')
    require(set(config['arms'])=={'original','revised'},'Exactly original/revised guidance required')
    for key in ('manifest','toolkit_directory','codex_catalog','codex_qualification','original_registration'):
        config[key]=str(Path(config[key]).resolve())
    for arm in config['arms'].values(): arm['policy_directory']=str(Path(arm['policy_directory']).resolve())
    config['discovery_receipts']={key:str(Path(value).resolve()) for key,value in config['discovery_receipts'].items()}
    tasks=read(config['manifest'])['tasks'];requests=[]
    for task in tasks:
        for arm in ('original','revised'):
            requests.append(dict(trial_id=task['task_id']+'--'+arm+'--r1',task_id=task['task_id'],arm_id=arm,repeat=1))
    validate_roster(requests,tasks)
    require(not ({t['task_id'] for t in tasks}&{'tweed-pr31','tweed-pr32','tweed-pr34','tweed-pr35','tweed-pr39','tweed-pr40'}),'Previously replayed task admitted')
    source_pins=load(r.BENCH/'tasks'/'prepare.py')
    for task in tasks:
        require(source_pins.tree_sha256(Path(task['base_snapshot']))==task['source_sha256'] and source_pins.tree_sha256(Path(task['head_snapshot']))==task['head_source_sha256'],'Declared historical task source pin differs')
        require(sha(task['oracle_script'])==task['oracle_script_sha256'],'Declared oracle script pin differs')
    random.Random(config['seed']).shuffle(requests)
    availability=read(config['codex_qualification']);versions=r.cli_versions()
    require(availability.get('qualified') is True and availability.get('model_requested')==REVIEW['model'] and availability.get('cohort') is False,'Qualified fresh exact Codex route required')
    require(availability.get('cli_versions',{}).get('codex')==versions['codex'],'Codex qualification version mismatch')
    require(set(config['discovery_receipts'])=={t['task_id'] for t in tasks},'One shared discovery receipt per task required')
    discovery=load(HERE/'discovery.py')
    for task in tasks: discovery.validate_receipt(read(config['discovery_receipts'][task['task_id']]),task)
    historic=read(config['original_registration'])
    require(digest(historic['payload'])==historic['payload_sha256'],'Historical original registration changed')
    original_tree=str(Path(config['arms']['original']['policy_directory']).resolve())
    require(historic['payload']['material']['trees'].get(original_tree)==inventory(original_tree),'Original guidance differs from historical seal')
    study.mkdir(parents=True)
    write(study/'requests.json',requests)
    adapter=runtime(REVIEW);base=adapter.frozen.base
    confinement=base.sandbox_check(study/'confinement')
    workspace=study/'offline-workspace';workspace.mkdir()
    local=adapter.local_mcp_probe('astra',workspace,study/'review-transport',readonly=True)
    require(local.get('passed') is True,'Readonly Codex transport unqualified; stop before inference')
    backend=adapter.frozen.backend;catalog=study/'review-catalog.json';backend.capability_catalog(config['codex_catalog'],catalog)
    probe=backend.inventory_probe(workspace,study/'review-inventory',catalog,with_mcp=True)
    require(probe.get('inventory',{}).get('passed') is True,'Codex inventory unqualified; stop before inference')
    files={str(path):sha(path) for path in [config_path,*sorted(HERE.glob('*.py')),OLD/'runner.py',OLD/'analyze.py',*sorted(r.BENCH.glob('*.py')),r.BENCH/'tasks'/'prepare.py']}
    for receipt_path in config['discovery_receipts'].values():
        discovery_receipt=read(receipt_path)
        for relative,expected in discovery_receipt['artifact_files'].items():
            path=str(Path(discovery_receipt['artifact_root'])/relative);a.bound(path,expected,'Discovery artifact');files[path]=expected
    for path in [config['manifest'],config['codex_catalog'],config['codex_qualification'],config['original_registration'],str(catalog),*config['discovery_receipts'].values()]: files[path]=sha(path)
    trees={config['toolkit_directory']:inventory(config['toolkit_directory'])}
    for arm in config['arms'].values(): trees[arm['policy_directory']]=inventory(arm['policy_directory'])
    for task in tasks:
        for key in ('base_snapshot','head_snapshot'):
            path=str(Path(task[key]).resolve());trees[path]=inventory(path)
        path=str(Path(task['oracle_script']).resolve().parent);trees[path]=inventory(path)
    payload=dict(config=config,material={'files':files,'trees':trees},requests_sha256=sha(study/'requests.json'),planned_cells=6,
        developer=DEV,reviewer=REVIEW,stage_caps=CAPS,review_inventory={'catalog':str(catalog),'receipt':probe},
        confinement=confinement,cli_versions=versions,prepared_at_unix=time.time(),
        limitations=['Controlled delegated lifecycle, not free orchestration or complete CP release certification',
            'Three fresh historical behavior slices, one trial per arm; no population inference',
            'Final frozen acceptance grader disclosed during repair; not an unseen post-repair holdout',
            'Codex model attribution may be requested-only; inventory is offline declared plus local transport',
            'Original-process-group cleanup does not contain detached setsid escapees',
            'Main timeout/missing terminal may recover only if model/tool/lifecycle/source provenance otherwise qualifies; first pass remains failed/unknown',
            'Claude dollar guards and estimated CLI usage do not equal invoices'])
    write(study/'registration.json',{'payload':payload,'payload_sha256':digest(payload)})
    return payload

def verify(study):
    study=Path(study).resolve();seal=read(study/'registration.json')
    require(digest(seal['payload'])==seal['payload_sha256'],'Registration content changed')
    payload=seal['payload']
    for path,expected in payload['material']['files'].items(): a.bound(path,expected,'Registered input')
    for path,expected in payload['material']['trees'].items(): require(inventory(path)==expected,'Registered tree changed: '+path)
    a.bound(study/'requests.json',payload['requests_sha256'],'Roster')
    require(r.cli_versions()==payload['cli_versions'],'CLI versions changed')
    validate_roster(read(study/'requests.json'),read(payload['config']['manifest'])['tasks'])
    return payload

def controls(study):
    study=Path(study).resolve();payload=verify(study);adapter=runtime(DEV);root=claim(study/'controls','base-head-controls');rows=[]
    for task in read(payload['config']['manifest'])['tasks']:
        for side in ('base','head'):
            result=grade(adapter,task,Path(task[side+'_snapshot']),root/(task['task_id']+'--'+side),time.time()+180)
            rows.append(dict(task_id=task['task_id'],side=side,**result))
    passed=all(row['oracle_passed'] is (row['side']=='head') for row in rows)
    write(root/'receipt.json',{'passed':passed,'rows':rows})
    require(passed,'Frozen grader controls failed')
    return rows

def require_controls(study,payload):
    control=read(study/'controls'/'receipt.json');rows=control['rows']
    expected={(task['task_id'],side) for task in read(payload['config']['manifest'])['tasks'] for side in ('base','head')}
    require(control.get('passed') is True and len(rows)==6 and {(r['task_id'],r['side']) for r in rows}==expected,'Grader control roster failed')
    for row in rows:
        require(a.oracle_truth(row,study/'controls'/(row['task_id']+'--'+row['side'])) is (row['side']=='head'),'Control changed')

def activated(study):
    activation=read(study/'activation.json');a.bound(study/'registration.json',activation['registration_sha256'],'Activated registration')
    commit=activation['git_commit'];public_path=activation['public_registration_path']
    require(re.fullmatch(r'[0-9a-f]{40}',commit) is not None and not Path(public_path).is_absolute() and '..' not in Path(public_path).parts,'Activation commit/path invalid')
    committed=subprocess.run(['git','show',commit+':'+public_path],cwd=ROOT,capture_output=True,check=True,timeout=10).stdout
    require(hashlib.sha256(committed).hexdigest()==activation['public_registration_sha256'],'Public registration envelope differs from nominated commit')
    public=json.loads(committed)
    require(public.get('private_registration_sha256')==activation['registration_sha256'],'Committed public envelope does not pin private registration')

def run(study):
    study=Path(study).resolve();payload=verify(study);activated(study);require_controls(study,payload)
    # One durable roster-level invocation. Restart cannot silently continue later
    # assigned cells; preserved missing/started identities appear in analysis.
    claim(study/'run-start','six-cell-run')
    tasks={t['task_id']:t for t in read(payload['config']['manifest'])['tasks']}
    roster=read(study/'requests.json');closed=False
    try:
        for request in roster:
            verify(study)
            row=run_cell(request,tasks[request['task_id']],payload['config']['arms'][request['arm_id']],payload,study)
            print(json.dumps({key:row.get(key) for key in ('trial_id','status','first_pass','actual_repair','accepted')}),flush=True)
        closed=True
    finally:
        rows=[]
        for request in roster:
            path=study/'trials'/request['trial_id']/'receipt.json'
            rows.append(read(path) if path.exists() else {**request,'status':'started_unknown' if path.parent.exists() else 'never_started','accepted':False})
        write(study/'results.json',rows)
        write(study/'closure.json',{'closed':closed,'assigned':6,'registration_sha256':sha(study/'registration.json'),'results_sha256':sha(study/'results.json')})
    return rows

def validate_stage(stage,directory,role,adapter):
    require(read(directory/'receipt.json')==stage,'Stage receipt differs from cell record')
    require(isinstance(stage.get('artifact_files'),dict) and bool(stage['artifact_files']),'Stage artifact manifest missing')
    for relative,expected in stage['artifact_files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'Stage artifact path unsafe')
        a.bound(directory/relative,expected,'Stage artifact')
    control=directory/'call';request=read(control/'request.json');route=REVIEW if role=='review' else DEV
    argv=request['argv']
    require(request.get('model_requested')==route['model'],'Requested stage model differs')
    require((request.get('effort') if role!='review' else request.get('requested_effort'))==route['effort'],'Requested stage effort differs')
    require(request.get('readonly') is (role=='review'),'Readonly request differs')
    require(type(request.get('timeout_seconds')) in (int,float) and 0<request['timeout_seconds']<=CAPS[role][0],'Stage time cap differs')
    if role!='review':
        require(request.get('budget_usd')==CAPS[role][1],'Stage dollar cap differs')
        for flag,wanted in (('--model',route['model']),('--effort',route['effort']),('--tools',''),('--allowedTools','mcp__cp_trial__*'),('--max-budget-usd',str(CAPS[role][1]))):
            require(flag in argv and argv[argv.index(flag)+1]==wanted,'Claude argv envelope differs')
        events=[]
        for line in (control/'stream.jsonl').read_text(errors='replace').splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        terminals=[event for event in events if event.get('type')=='result']
        require(len(terminals)<=1 and stage.get('terminal')==(terminals[-1] if terminals else None),'Claude actual terminal differs')
        models=[];init=None
        for event in events:
            if event.get('type')=='assistant':
                message=event.get('message',{});model=message.get('model')
                if isinstance(model,str) and model not in models:models.append(model)
                for block in message.get('content',[]):
                    if isinstance(block,dict) and block.get('type')=='tool_use':
                        require(block.get('name') in ['StructuredOutput',*['mcp__cp_trial__'+name for name in adapter.EXPECTED]],'Unexpected actual Claude tool call')
            elif event.get('type')=='system' and event.get('subtype')=='init':
                init={key:event.get(key) for key in ('model','tools','mcp_servers','mcp_server_errors','claude_code_version','permissionMode')}
        require(stage.get('observed_assistant_models')==models and stage.get('harness_initialization')==init,'Claude actual provider facts differ')
    else:
        backend=adapter.frozen.backend;events,_=backend.parse_events(control/'stream.jsonl')
        raw=backend.event_receipt(events,(control/'final.json').read_text() if (control/'final.json').exists() else None,error=stage.get('process_exit')!=0 or stage.get('timed_out') is True)
        for key in raw:require(stage.get(key)==raw[key],'Codex actual provider fact differs: '+key)
    local=read(directory/'qualification'/'local-qualification.json')
    q=qualify_stage(adapter,dict(stage),local,route)
    if role=='review' and stage['source_sha256_at_launch']!=stage['source_sha256_after']:
        q['failures'].append('readonly_review_source_changed');q['eligible']=False
    require(q==stage['qualification'],'Stage eligibility differs from factual qualification')
    return q

def validate_checks(rows,directory,commands,source_sha256):
    require(read(directory/'receipt.json')==rows and len(rows)==len(commands),'Check roster/receipt differs')
    passed=[]
    for index,(row,item) in enumerate(zip(rows,commands)):
        item={'id':'visible-'+str(index),'argv':item} if isinstance(item,list) else item
        require(row['id']==item['id'] and row['requested_argv']==item['argv'],'Check command identity differs')
        require(row['source_sha256']==source_sha256 and row['source_unchanged'] is True,'Executed check source binding differs')
        request=read(directory/('check-'+str(index)+'.command-request.json'))
        mapped={'python3':sys.executable,'python':sys.executable,'git':'/usr/bin/git','bash':'/bin/bash','sh':'/bin/sh'}
        argv=item['argv'];require(request['argv']==[mapped.get(argv[0],argv[0]),*argv[1:]],'Actual check argv differs')
        require(0<request['timeout']<=min(item.get('timeout_seconds',30),90),'Check cap differs')
        response=read(directory/('check-'+str(index)+'.command-response.json'))
        mandatory={'argv','exit_code','timed_out','wall_seconds','stdout','stderr','stdout_sha256','stderr_sha256','process_cleanup_scope','detached_descendants_contained'}
        require(mandatory<=set(response),'Executed command process/output artifacts missing')
        require(type(response['exit_code']) is int and type(response['timed_out']) is bool and type(response['wall_seconds']) in (int,float) and math.isfinite(response['wall_seconds']) and response['wall_seconds']>=0,'Executed command lifecycle invalid')
        require(response['process_cleanup_scope']=='original_process_group' and response['detached_descendants_contained'] is False,'Executed command cleanup unqualified')
        require(response['argv'][:2]==['/usr/bin/sandbox-exec','-p'] and response['argv'][3:]==request['argv'],'Executed command sandbox envelope differs')
        for kind in ('stdout','stderr'):
            expected_output=(directory/('command-check-'+str(index)+'.'+kind)).resolve()
            require(Path(response[kind]).resolve()==expected_output,'Executed command output file association differs')
        require(all(row.get(key)==value for key,value in response.items()),'Executed command response differs')
        for kind in ('stdout','stderr'):
            if response.get(kind):a.bound(response[kind],response[kind+'_sha256'],'Command '+kind)
        actual=response.get('exit_code')==0 and response.get('timed_out') is False
        require(row['passed'] is actual,'Recorded check pass contradicts command facts');passed.append(actual)
    return all(passed)

def derive_receipt(receipt,request,task,payload,directory,study):
    require(all(receipt[key]==request[key] for key in request),'Cell identity mismatch')
    require(receipt['registration_sha256']==sha(study/'registration.json'),'Cell registration mismatch')
    adapter=runtime(DEV);base=adapter.frozen.base
    commands=task['test_commands']+task.get('required_checks',[])+payload['config'].get('policy_checks',[])
    for role in ('main','closure'):validate_stage(receipt[role],directory/role,role,adapter)
    validate_stage(receipt['review'],directory/'review','review',runtime(REVIEW))
    report=review_payload(receipt['review']);require(report==receipt['review_findings'],'Review findings differ from actual terminal')
    for side in ('first','final'):
        artifact=receipt[side];require(base.tree_digest(directory/side/'source')==artifact['source_sha256'],'Source changed')
        a.bound(directory/side/'submitted.patch',artifact['patch_sha256'],'Patch')
        with tempfile.TemporaryDirectory(prefix='cp-lean-analysis-') as temp:
            patch,_=base.build_patch(Path(task['base_snapshot']),directory/side/'source',Path(temp)/'reconstructed.patch',task['production_paths'])
            require(hashlib.sha256(patch).hexdigest()==artifact['patch_sha256'],'Patch does not reconstruct current submitted source')
        violations=base.scope_diff(Path(task['base_snapshot']),directory/side/'source',task['production_paths'])
        require(violations==artifact['scope_violations'],'Scope verdict changed')
        require(a.oracle_truth(receipt[side+'_grade'],directory/(side+'-grade'))==receipt[side+'_grade']['oracle_passed'],'Grade changed')
        require(receipt[side+'_grade']['source_sha256']==artifact['source_sha256'],'Grade source association differs')
        with tempfile.TemporaryDirectory(prefix='cp-verify-checks-') as temporary:
            projected=Path(temporary)/'source';check_sha=witness_projection(base,task,directory/side/'source',projected)
            require(inventory(projected)==inventory(directory/(side+'-checks')/'source'),'Required checks frozen source projection differs')
        require(receipt['checks_'+side+'_source_sha256']==check_sha,'Required check source digest differs')
        validate_checks(receipt[side+'_checks'],directory/(side+'-checks'),commands,check_sha)
    require(receipt['main']['source_sha256_after']==receipt['first']['source_sha256'],'Main/first source binding differs')
    require(receipt['closure']['source_sha256_at_launch']==receipt['first']['source_sha256'] and receipt['closure']['source_sha256_after']==receipt['final']['source_sha256'],'Closure source bindings differ')
    review_source=directory/'review-source';review_sha=base.tree_digest(review_source)
    require(review_sha==receipt['review_source_sha256']==receipt['review']['source_sha256_at_launch']==receipt['review']['source_sha256_after'],'Reviewer source changed/unassociated')
    before=inventory(directory/'first'/'source');normalized={path:record for path,record in before.items() if Path(path).parts[0] not in ('.protocol','.confidence','AGENTS.md')}
    require(inventory(review_source)==normalized,'Reviewer source is not normalized first source')
    witnesses=[{'id':f['id'],'argv':f['witness'],'timeout_seconds':30} for f in report['findings'] if f['blocking'] and f['witness'] is not None]
    for side,label in (('first','before'),('final','after')):
        with tempfile.TemporaryDirectory(prefix='cp-verify-witness-') as temporary:
            projected=Path(temporary)/'source';expected_sha=witness_projection(base,task,directory/side/'source',projected)
            require(inventory(projected)==inventory(directory/('witness-'+label)/'source'),'Witness frozen source projection differs')
        require(receipt['witness_'+side+'_source_sha256']==expected_sha,'Witness source digest differs')
        validate_checks(receipt['witness_'+label],directory/('witness-'+label),witnesses,expected_sha)
    derived=dict(receipt)
    derived['review_qualified']=True
    derived['unresolved_findings']=unresolved_findings(report['findings'],receipt['witness_before'],receipt['witness_after'])
    derived['final_binding_valid']=True
    derived['final_checks_passed']=all(v['passed'] for v in receipt['final_checks'])
    derived['first_pass']=receipt['main']['qualification']['eligible'] and receipt['first_grade']['oracle_passed'] is True and all(v['passed'] for v in receipt['first_checks']) and not receipt['first']['scope_violations']
    derived['actual_repair']=receipt['first']['patch_sha256']!=receipt['final']['patch_sha256']
    require(receipt['accepted'] is accepted(derived),'Recorded acceptance contradicts derived facts')
    for key in ('review_qualified','unresolved_findings','final_binding_valid','final_checks_passed','first_pass','actual_repair'):require(derived[key]==receipt[key],'Recorded derived field differs: '+key)
    return derived

def analyze(study):
    study=Path(study).resolve();payload=verify(study);rows=[];tasks={task['task_id']:task for task in read(payload['config']['manifest'])['tasks']}
    for request in read(study/'requests.json'):
        directory=study/'trials'/request['trial_id'];path=directory/'receipt.json'
        if not path.exists():
            rows.append({**request,'status':'started_unknown' if directory.exists() else 'never_started','accepted':False});continue
        receipt=read(path)
        try:
            derived=derive_receipt(receipt,request,tasks[request['task_id']],payload,directory,study)
            row={**request,**{key:derived.get(key) for key in ('status','first_pass','actual_repair','accepted','unresolved_findings')}}
        except Exception as error:row={**request,'status':'analysis_binding_error','accepted':False,'error':str(error)}
        rows.append(row)
    result={'assigned':6,'rows':rows,'by_arm':{arm:{'assigned':3,'first_pass':sum(v.get('first_pass') is True for v in rows if v['arm_id']==arm),'final_accepted':sum(v.get('accepted') is True for v in rows if v['arm_id']==arm),'actual_repairs':sum(v.get('actual_repair') is True for v in rows if v['arm_id']==arm)} for arm in ('original','revised')},'limitations':payload['limitations']}
    write(study/'analysis.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','controls','run','analyze']);parser.add_argument('--study',type=Path,required=True);parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':require(args.config is not None,'--config required');prepare(args.config,args.study)
    else: print(json.dumps(globals()[args.action](args.study),indent=2))
