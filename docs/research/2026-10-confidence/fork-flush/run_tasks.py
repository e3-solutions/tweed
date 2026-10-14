#!/usr/bin/env python3
"""Small durable task driver: one fixed Opus solve, one conditional repair.

All policy arms share tools, references, model, effort and budgets. Owner-only
independent evaluation never exposes oracle source to actors. No automatic call,
retry, model fallback, scratch collector or benchmark orchestration framework.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'.git').exists() and (p/'docs').is_dir())
LEGACY=ROOT/'docs/research/2026-10-confidence/claude-first-evaluation/runner.py'
spec=importlib.util.spec_from_file_location('fork_driver_qualified_helpers',LEGACY)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
MODEL={'backend':'claude','model':'claude-opus-5-5','effort':'high'}
BUDGET={'solve':(150,1.5),'repair':(90,1)}
read,write,sha,digest=r.read,r.write,r.sha,r.digest


def require(value,message):
    if not value:raise ValueError(message)


def claim(path,identity):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.mkdir(exist_ok=False)
    write(path/'started.json',{'identity':identity,'started_at_unix':time.time()});return path


def runtime():
    adapter=r.route(MODEL);base=adapter.frozen.base;original=base.service_commands
    def service(control,workspace,temporary,readonly,deadline):
        r.deny_reviews(control,workspace,None,deadline)
        return original(control,workspace,temporary,readonly,deadline)
    base.service_commands=service
    return adapter


def transport_preflight(adapter,workspace,control,commands):
    """Actual MCP run_tests → WorkspaceTools.execute → command-service prefix.

    This is not an unconfined subprocess.run baseline check. Both lexical API
    and executed-child outside-read denial are observed, without hosted calls.
    """
    control=claim(control,'actual-tool-path-preflight');base=adapter.frozen.base
    server=adapter.claude_mcp_configuration(workspace,control,readonly=False)
    server_config=read(control/'server-config.json');server_config['deadline']=time.time()+90;write(control/'server-config.json',server_config)
    sentinel=control/'outside-sentinel.txt';sentinel.write_text('OWNER-ONLY-PREFLIGHT')
    denial=('from pathlib import Path\ntry:\n Path('+repr(str(sentinel))+').read_text()\nexcept PermissionError:\n print("OUTSIDE_READ_DENIED")\nelse:\n raise AssertionError("outside read allowed")\n')
    calls=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'fork-flush-preflight','version':'1'}}},
        {'jsonrpc':'2.0','id':2,'method':'tools/list'},
        {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'read_file','arguments':{'path':'../outside-sentinel.txt'}}},
        {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'run_tests','arguments':{'argv':['python3','-B','-c',denial],'timeout_seconds':10}}}]
    for index,command in enumerate(commands,5):calls.append({'jsonrpc':'2.0','id':index,'method':'tools/call','params':{'name':'run_tests','arguments':{'argv':command,'timeout_seconds':30}}})
    write(control/'mcp-requests.json',calls);stdout=control/'mcp.stdout';stderr=control/'mcp.stderr';deadline=time.time()+90
    with stdout.open('wb') as out,stderr.open('wb') as err:
        process=base.subprocess.Popen([server['command'],*server['args']],cwd=workspace,env=server['env'],stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
        process.stdin.write(''.join(json.dumps(item)+'\n' for item in calls).encode());process.stdin.close();timed_out=False
        try:
            while process.poll() is None:
                base.service_commands(control,workspace,workspace/'.trial-tmp',False,deadline)
                if time.time()>=deadline:timed_out=True;base.terminate(process);break
                time.sleep(.05)
        finally:adapter.frozen.processes.cleanup_group(process)
    events=[json.loads(line) for line in stdout.read_text(errors='replace').splitlines()];by_id={item.get('id'):item for item in events}
    names=[item['name'] for item in by_id.get(2,{}).get('result',{}).get('tools',[])]
    def response(ident):
        result=by_id.get(ident,{}).get('result',{});content=result.get('content',[])
        try:return result,json.loads(content[0]['text'])
        except (IndexError,KeyError,TypeError,ValueError):return result,{}
    denied_api=response(3)[0].get('isError') is True;child=response(4)[1]
    child_denied=child.get('exit_code')==0 and child.get('timed_out') is False and 'OUTSIDE_READ_DENIED' in child.get('output','')
    baseline=[response(index)[1] for index in range(5,5+len(commands))]
    passed=(process.returncode==0 and not timed_out and names==adapter.EXPECTED and denied_api and child_denied and bool(baseline) and all(row.get('exit_code')==0 and row.get('timed_out') is False for row in baseline))
    receipt={'passed':passed,'hosted_model_calls':0,'effective_tools':names,'expected_tools':adapter.EXPECTED,
        'outside_read_denied_api':denied_api,'outside_read_denied_executed_child':child_denied,'baseline_commands':commands,'baseline_results':baseline,
        'process_exit':process.returncode,'timed_out':timed_out,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),
        'command_path':'actual MCP run_tests -> WorkspaceTools.execute -> existing sandbox service_commands','control_scope':'workspace only; fresh outside execution scratch; no oracle/history/network'}
    write(control/'receipt.json',receipt);return receipt


def context(adapter,task,config,arm,workspace):
    base=adapter.frozen.base;base.safe_copy(Path(task['base_snapshot']),workspace)
    for pattern in ('AGENTS.md','CLAUDE.md','.claude','.codex','.agents','.git','.protocol'):
        for path in list(workspace.rglob(pattern)):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    base.safe_copy(Path(config['common_protocol']),workspace/'.protocol')
    shutil.copy2(arm['skill_file'],workspace/'.protocol'/'SKILL.md')
    (workspace/'AGENTS.md').write_text('Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n')
    ignore=workspace/'.gitignore';ignore.write_text((ignore.read_text() if ignore.exists() else '')+'\n.trial-tmp/\n.confidence/\n')
    scratch=workspace/'.trial-tmp';scratch.mkdir(exist_ok=True)
    for args in (['init','-q'],['add','.'],['-c','user.name=ForkTask','-c','user.email=fork-task@example.invalid','commit','-qm','Frozen task base']):
        subprocess.run([base.GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',*args],cwd=workspace,env=base.safe_env(workspace,scratch),capture_output=True,check=True)


def capture(adapter,task,workspace,directory):
    claim(directory,'durable-source-and-production');base=adapter.frozen.base;base.safe_copy(workspace,directory/'source')
    patch,paths=r.load(r.HERE/'analyze.py').rebuild_patch(adapter,Path(task['base_snapshot']),directory/'source',directory/'production.patch',task['production_paths'])
    raw={'source_sha256':base.tree_digest(directory/'source'),'production_patch_sha256':hashlib.sha256(patch).hexdigest(),'production_paths':paths,
        'scope_violations':base.scope_diff(Path(task['base_snapshot']),directory/'source',task['production_paths'])}
    write(directory/'receipt.json',raw);return raw


def evaluate(adapter,task,source,control,evaluator):
    claim(control,'independent-fixed-requirement-evaluator');before=adapter.frozen.base.tree_digest(source)
    process=adapter.frozen.base.bounded_process([sys.executable,'-B',str(evaluator),'--workspace',str(source),'--task-id',task['task_id']],
        cwd=HERE,env=adapter.frozen.grader.clean_env(),timeout=60,output_prefix=control/'grader')
    header=None
    lines=Path(process['stdout']).read_text(errors='replace').splitlines()
    if lines:
        try:header=json.loads(lines[0])
        except ValueError:pass
    result={'process':process,'header':header,'source_sha256':before,'source_unchanged':before==adapter.frozen.base.tree_digest(source)}
    result['qualified_evaluation']=bool(not process['timed_out'] and result['source_unchanged'] and isinstance(header,dict) and type(header.get('passed')) is bool and header.get('source_current') is True and header.get('setup_status')=='verified')
    write(control/'receipt.json',result);return result


def prepare(config_file,study):
    config_file=Path(config_file).resolve();study=Path(study).resolve();config=read(config_file)
    require(not study.exists(),'Fresh output required')
    for key in ('tasks','common_protocol','evaluator'):config[key]=str(Path(config[key]).resolve())
    for arm in config['arms']:arm['skill_file']=str(Path(arm['skill_file']).resolve())
    require(len({arm['id'] for arm in config['arms']})==len(config['arms']),'Unique frozen guidance arms required')
    manifest=read(config['tasks']);tasklist=manifest['tasks'];tasks={task['task_id']:task for task in tasklist};selected=config['task_ids']
    arm_ids={arm['id'] for arm in config['arms']}
    selection=(len(config['arms'])==3 and arm_ids=={'incumbent','branch-a','branch-b'} and set(selected)==set(manifest['selection_task_ids']))
    confirmation=(selected==['tweed-pr18'] and manifest['confirmation_task_id']=='tweed-pr18' and len(config['arms'])==2 and 'incumbent' in arm_ids and len(arm_ids&{'branch-a','branch-b'})==1)
    require(selection or confirmation,'Selection requires all3 arms on the2 selection tasks; reserved PR18 confirmation requires incumbent plus one branch only')
    require(len(selected)==len(set(selected)) and set(selected)<=set(tasks),'Explicit unique known task IDs required')
    study.mkdir(parents=True);rows=[];preflight=[];trees={config['common_protocol']:r.inventory(config['common_protocol'])}
    files={str(config_file):sha(config_file),str(Path(__file__).resolve()):sha(__file__),config['tasks']:sha(config['tasks']),config['evaluator']:sha(config['evaluator']),str(LEGACY):sha(LEGACY)}
    files.update({str(path):sha(path) for path in sorted(r.BENCH.glob('*.py'))})
    for task_id in selected:
        task=tasks[task_id];trees[task['base_snapshot']]=r.inventory(task['base_snapshot'])
        oracle_tree=HERE/'oracles'
        trees[str(oracle_tree.resolve())]=r.inventory(oracle_tree)
        for arm in config['arms']:
            require(all(char.isalnum() or char=='-' for char in arm['id']),'Unsafe arm ID')
            cell_id=task_id+'--'+arm['id'];cell=claim(study/'cells'/cell_id,cell_id);adapter=runtime();workspace=cell/'workspace';context(adapter,task,config,arm,workspace)
            check=transport_preflight(adapter,workspace,cell/'preflight',task.get('visible_commands',task['test_commands']));preflight.append({'cell_id':cell_id,**check});require(check['passed'],'Actual tool-path preflight failed: '+cell_id)
            # Preflight is source-read-only in intent; generated bytecode/scratch
            # is excluded from owned acceptance tests by the evaluator projection.
            before=capture(adapter,task,workspace,cell/'baseline')
            files[arm['skill_file']]=sha(arm['skill_file'])
            rows.append({'cell_id':cell_id,'task_id':task_id,'arm_id':arm['id'],'prompt':'Read .protocol/SKILL.md and relevant common references. Complete this bounded real task and execute the visible checks. Peer calls are unavailable inside this stage; independent Codex checking occurs externally. Return the required JSON truthfully.\nTask:\n'+task['prompt']+'\nVisible checks:\n'+json.dumps(task.get('visible_commands',task['test_commands']))+'\nAllowed production paths:\n'+json.dumps(task['production_paths']),'baseline_source_sha256':before['source_sha256']})
    write(study/'requests.json',rows);write(study/'RUNTIME-PREFLIGHT.json',{'passed':True,'model_calls':0,'cells':preflight})
    write(HERE/'RUNTIME-PREFLIGHT.json',{'passed':True,'model_calls':0,'study':str(study),'preflight_sha256':sha(study/'RUNTIME-PREFLIGHT.json'),'cells':[{'cell_id':row['cell_id'],'passed':row['passed'],'effective_tools':row['effective_tools'],'outside_read_denied_api':row['outside_read_denied_api'],'outside_read_denied_executed_child':row['outside_read_denied_executed_child']} for row in preflight]})
    payload={'config':config,'tasks':{key:tasks[key] for key in selected},'files':files,'trees':trees,'requests_sha256':sha(study/'requests.json'),'preflight_sha256':sha(study/'RUNTIME-PREFLIGHT.json'),'model':MODEL,'budgets':BUDGET,
        'limits':['Small fixed task selection, not broad model/policy generalization.','At most one repair per cell, only after current-source requirement failure.','Native independent Codex review is coordinated outside the developer timers.','Source snapshots persist; arbitrary execution scratch/symlinks are not provider evidence.']}
    write(study/'registration.json',{'payload':payload,'payload_sha256':digest(payload)});return payload


def verify(study):
    seal=read(study/'registration.json');payload=seal['payload'];require(digest(payload)==seal['payload_sha256'],'Registration changed')
    for path,expected in payload['files'].items():require(sha(path)==expected,'Frozen file changed: '+path)
    for path,expected in payload['trees'].items():require(r.inventory(path)==expected,'Frozen input tree changed: '+path)
    require(sha(study/'requests.json')==payload['requests_sha256'] and sha(study/'RUNTIME-PREFLIGHT.json')==payload['preflight_sha256'],'Frozen roster/preflight changed')
    return payload


def root_seals():
    guard=r.load(HERE/'verify_seal.py');registration=guard.verify()
    policies=read(HERE/'POST-DESIGN-SEAL.json')
    entries=policies.get('files_sha256') or policies.get('policy_files_sha256')
    require(isinstance(entries,dict) and len(entries)>=3,'Authoritative post-design policy seal missing')
    for relative,expected in entries.items():
        path=Path(relative);path=path if path.is_absolute() else ROOT/path
        require(sha(path)==expected,'Changed post-design policy: '+relative)
    return registration


def preflight(tasks_file,common_protocol):
    tasks_file=Path(tasks_file).resolve();common_protocol=Path(common_protocol).resolve();out=claim(HERE/'runtime-preflight','offline-actual-tool-path')
    rows=[]
    for task in read(tasks_file)['tasks']:
        if task.get('role')!='selection':continue
        adapter=runtime();directory=claim(out/task['task_id'],task['task_id']);workspace=directory/'workspace'
        context(adapter,task,{'common_protocol':str(common_protocol)},{'skill_file':str(common_protocol/'SKILL.md')},workspace)
        check=transport_preflight(adapter,workspace,directory/'controlled-prefix',task.get('visible_commands',task['test_commands']))
        rows.append({'task_id':task['task_id'],**check});require(check['passed'],'Offline actual tool-path preflight failed')
    receipt={'passed':True,'scope':'Two selection tasks only; reserved confirmation preflight is separate','hosted_model_calls':0,'driver_sha256':sha(__file__),'tasks_sha256':sha(tasks_file),'common_protocol_inventory_sha256':digest(r.inventory(common_protocol)),'tasks':rows}
    write(HERE/'RUNTIME-PREFLIGHT.json',receipt);return receipt


def execute_stage(study,cell_id,role,feedback=None):
    study=Path(study).resolve();root_seals();payload=verify(study);authorization=read(study/'CALLS-AUTHORIZED.json')
    require(authorization.get('registration_sha256')==sha(study/'registration.json') and role in authorization.get('stages',[]),'Explicit root call dispatch required')
    request=next(row for row in read(study/'requests.json') if row['cell_id']==cell_id);task=payload['tasks'][request['task_id']];cell=study/'cells'/cell_id;workspace=cell/'workspace'
    if role=='repair':
        first=read(cell/'solve'/'evaluation'/'receipt.json');header=first.get('header',{})
        require(first.get('qualified_evaluation') is True,'Missing/unknown actual requirement evaluation cannot trigger repair')
        failure=bool(header.get('failed_requirements')) or header.get('required_behavior_passed') is False or header.get('negative_boundaries_passed') is False or bool(header.get('scope_violations'))
        require(failure,'Repair allowed only on independent requirement/scope failure')
        require(feedback is not None,'Explicit safe full gate feedback required')
        feedback=Path(feedback).resolve();packet=read(feedback)
        require(packet.get('cell_id')==cell_id and packet.get('evaluation_receipt_sha256')==sha(cell/'solve'/'evaluation'/'receipt.json'),'Repair feedback does not bind this actual evaluation')
        require(adapter_source_digest(workspace)==read(cell/'solve'/'receipt.json')['after']['source_sha256'],'Workspace changed after independent initial evaluation')
        safe_feedback=packet['feedback'];require(isinstance(safe_feedback,dict) and safe_feedback.get('failed_requirements')==header.get('failed_requirements') and safe_feedback.get('scope_violations')==header.get('scope_violations'),'Full exact requirement/scope feedback missing')
        allowed={'task_id','failed_requirements','scope_violations','required_behavior_passed','negative_boundaries_passed','baseline_commands_passed','passed','setup_status','source_current','scope_restore_baseline_bytes','notes'}
        require(set(safe_feedback)<=allowed,'Repair feedback must not leak raw oracle diagnostics/source')
        prompt=request['prompt']+'\nActual independent requirement feedback (including scope):\n'+json.dumps(safe_feedback)+'\nThis is the sole repair attempt. Address all supplied requirement failures and scope violations, then rerun relevant verification. No peer or retry is available.'
    else:prompt=request['prompt']
    arm=next(arm for arm in payload['config']['arms'] if arm['id']==request['arm_id'])
    require(sha(workspace/'.protocol'/'SKILL.md')==sha(arm['skill_file']),'Assigned live policy context changed')
    expected_protocol=r.inventory(payload['config']['common_protocol']);actual_protocol=r.inventory(workspace/'.protocol')
    require({key:value for key,value in actual_protocol.items() if key!='SKILL.md'}=={key:value for key,value in expected_protocol.items() if key!='SKILL.md'},'Common live toolkit/references changed')
    control=claim(cell/role,role);adapter=runtime();receipt={'cell_id':cell_id,'task_id':task['task_id'],'arm_id':request['arm_id'],'role':role,'status':'started','registration_sha256':sha(study/'registration.json')}
    try:
        receipt['protocol_inventory_before']=r.inventory(workspace/'.protocol')
        receipt['before']=capture(adapter,task,workspace,control/'before')
        local=adapter.local_mcp_probe('opus',workspace,control/'qualification',readonly=False);require(local.get('passed') is True,'Local MCP transport failed before inference')
        seconds,budget=BUDGET[role];stage=adapter.frozen.base.claude_call(workspace,control/'call',prompt,budget,seconds,time.time()+seconds)
        stage.update(backend='claude',source_sha256_at_launch=receipt['before']['source_sha256'],source_sha256_after=adapter.frozen.base.tree_digest(workspace));stage['qualification']=r.qualification(stage,local,MODEL,adapter)
        if stage.get('requested_effort')!='high':stage['qualification']['eligible']=False;stage['qualification']['failures'].append('requested_effort_mismatch')
        receipt['protocol_inventory_after']=r.inventory(workspace/'.protocol')
        receipt['protocol_context_unchanged']=receipt['protocol_inventory_before']==receipt['protocol_inventory_after']
        if not receipt['protocol_context_unchanged']:
            stage['qualification']['eligible']=False;stage['qualification']['failures'].append('policy_or_common_toolkit_modified')
        root_seals()
        # Bind provider and real command evidence; skip ephemeral scratch trees.
        stage['artifacts']={str(path.relative_to(control/'call')):sha(path) for path in (control/'call').rglob('*') if path.is_file() and 'execution-scratch' not in path.parts}
        write(control/'stage.json',stage);receipt['stage']=stage
        receipt['after']=capture(adapter,task,workspace,control/'after')
        receipt['evaluation']=evaluate(adapter,task,control/'after'/'source',control/'evaluation',Path(payload['config']['evaluator']))
        receipt['production_patch_changed_in_stage']=receipt['before']['production_patch_sha256']!=receipt['after']['production_patch_sha256'];receipt['full_source_changed_in_stage']=receipt['before']['source_sha256']!=receipt['after']['source_sha256'];receipt['status']='completed'
    except Exception as error:receipt.update(status='infrastructure_or_artifact_error',error=type(error).__name__+': '+str(error))
    receipt['ended_at_unix']=time.time();write(control/'receipt.json',receipt);return receipt

def adapter_source_digest(workspace):
    return runtime().frozen.base.tree_digest(workspace)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['preflight','prepare','solve','repair']);parser.add_argument('--study',type=Path);parser.add_argument('--config',type=Path);parser.add_argument('--cell');parser.add_argument('--feedback',type=Path);parser.add_argument('--tasks',type=Path);parser.add_argument('--common-protocol',type=Path)
    args=parser.parse_args()
    if args.action=='preflight':require(args.tasks is not None and args.common_protocol is not None,'--tasks --common-protocol required');result=preflight(args.tasks,args.common_protocol)
    elif args.action=='prepare':require(args.config is not None,'--config required');result=prepare(args.config,args.study)
    else:require(args.cell is not None,'--cell required');result=execute_stage(args.study,args.cell,args.action,args.feedback)
    print(json.dumps({'action':args.action,'cell_id':result.get('cell_id'),'status':result.get('status'),'error':result.get('error')}))
