#!/usr/bin/env python3
"""POST-OUTCOME supplemental export, never a replacement for sealed metrics.

Created after the first scored cell; unregistered for outcome selection. No
hosted calls, new graders, retries, alternate acceptance or repairs. Requires
all six recorded cells closed before execution. Writes only beneath its new
post-analysis output directory. Publication is a separate owner action.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import sys
from types import FunctionType

HERE=Path(__file__).resolve().parent
RUNTIME=HERE.parent/'runtime'
spec=importlib.util.spec_from_file_location('lean_sealed_controller',RUNTIME/'controller.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
PRIVATE=re.compile(r'/(?:Users|private|var/folders)/[^\s\"\'<>`;,\]\[()]*')
SECRET=re.compile(r'\b(?:sk-proj-|sk-ant-|sk-live-)[A-Za-z0-9_\-]{12,}')


def safe_text(value):
    value=PRIVATE.sub('[private-path-redacted]',str(value))
    return SECRET.sub('[credential-pattern-redacted]',value)


def safe_value(value):
    if isinstance(value,str):return safe_text(value)
    if isinstance(value,list):return [safe_value(item) for item in value]
    if isinstance(value,dict):return {key:safe_value(item) for key,item in value.items()}
    return value


def exact_safe_bytes(data,label):
    text=data.decode('utf-8')
    c.require(PRIVATE.search(text) is None and SECRET.search(text) is None,label+' contains private-path/credential-like bytes; exact public copy refused')
    return data


def numeric(value):
    return value if type(value) in (int,float) and math.isfinite(value) and value>=0 else None


def usage(stage):
    raw=stage.get('usage')
    if not isinstance(raw,dict):return None
    return {key:numeric(raw[key]) for key in c.a.USAGE_KEYS if key in raw}


def common_prompt(task,config):
    receipt=c.read(config['discovery_receipts'][task['task_id']])
    facts=[{key:fact[key] for key in ('path','start_line','end_line','quote')} for fact in receipt['validated_facts']]
    common='Task:\n'+task['prompt']+'\nVisible checks:\n'+json.dumps(task['test_commands'])+'\nShared checked Haiku source facts:\n'+json.dumps(facts)
    return ('Read .protocol/SKILL.md and relevant references. Follow the full supplied guidance. '
        'This controlled delegated lifecycle supplies bounded Haiku discovery and an independent Codex review after your stage. '
        'request_review is unavailable inside your timer. Finish implementation and execute checks truthfully.\n'+common)


def reconstructed_envelope(receipt,request,task,payload,directory):
    """Independent full developer launch/prompt/MCP/argv reconstruction."""
    adapter=c.runtime(c.DEV);config=payload['config'];arm=config['arms'][request['arm_id']]
    launch=c.a.launch_digest(task,arm,config,adapter)
    c.require(launch==receipt['main']['source_sha256_at_launch'],'Reconstructed main source launch differs')
    prompt=common_prompt(task,config)
    checks=c.feedback(receipt['first_checks'],receipt['first_grade'],directory/'first-grade')
    closure=(prompt+'\nIndependent Codex review:\n'+json.dumps(receipt['review_findings'])+'\nExecuted feedback:\n'+json.dumps(checks)+
        '\nExecuted review witnesses:\n'+json.dumps(receipt['witness_before'])+
        '\nThis is your sole final repair/verification stage. Correct defects and missing required proof, rerun checks, and report remaining gaps truthfully. If already correct, verify and close without a gratuitous edit. No new reviewer is available.')
    receipts={}
    for role,text in (('main',prompt),('closure',closure)):
        control=directory/role/'call';actual=c.read(control/'request.json')
        c.require(actual.get('prompt')==text,'Actual developer prompt differs from reconstructed input: '+role)
        c.a.request_envelope(control,actual,c.DEV,{'claude_budget_usd':c.CAPS[role][1]},text,adapter,payload)
        receipts[role]={'request_json_sha256':c.sha(control/'request.json'),'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'server_config_sha256':c.sha(control/'server-config.json'),'full_argv_mcp_prompt_reconstruction_passed':True}
    reviewer=c.runtime(c.REVIEW);backend=reviewer.frozen.backend;control=directory/'review'/'call';actual=c.read(control/'request.json');server=c.read(control/'server-config.json')
    blind='Independent read-only review. Do not implement or consult policy. Task:\n'+task['prompt']+'\nCandidate diff:\n'+(directory/'first'/'submitted.patch').read_text()+'\nExecuted checks/grade:\n'+json.dumps(checks)
    blind+='\nReturn complete/summary/remaining. complete means review finished. summary MUST be JSON string with exactly findings (list) and scope_limits (list of strings). Each finding has exactly id (lowercase hyphenated), blocking (bool), path, line (positive int), claim, witness (argv list or null). Witness must fail on current candidate and pass when corrected; use only self-contained python3 -B -c INLINE_CODE argv. Witnesses execute on candidate production over immutable baseline tests, without actor scratch or added/modified tests. Absent executable witness keeps blocking finding unresolved. Remaining holds unfinished review work.'
    workspace=Path(server['workspace']);temporary=Path(server['temporary'])
    c.require(server.get('readonly') is True and server.get('python_executable')==sys.executable and temporary==workspace/'.trial-tmp','Reviewer readonly server envelope differs')
    overrides={}
    for index,item in enumerate(actual['argv']):
        if item=='-c':
            key,value=actual['argv'][index+1].split('=',1);c.require(key not in overrides,'Duplicate reviewer configuration override');overrides[key]=value
    tokens=re.findall(r'"tool_timeout_sec"=([0-9][0-9.eE+\-]*)',overrides.get('mcp_servers',''))
    c.require(len(tokens)==1,'Reviewer wire timeout unavailable/duplicated');timeout=json.loads(tokens[0])
    c.require(numeric(timeout) is not None and 1<=timeout<=actual['timeout_seconds']+1,'Reviewer wire timeout out of bounds')
    profile=backend.runner.sandbox_profile(workspace,temporary,extra_reads=[backend.HERE/'runner.py',control/'server-config.json'],extra_writes=[control],readonly=True)
    mcp={'cp_trial':{'command':'/usr/bin/sandbox-exec','args':['-p',profile,sys.executable,'-I','-S','-B',str(backend.HERE/'runner.py'),'serve','--config',str(control/'server-config.json')],
        'env':backend.runner.safe_env(workspace,temporary),'required':True,'enabled_tools':list(backend.runner.NATIVE_TOOLS),'default_tools_approval_mode':'approve','startup_timeout_sec':10,'tool_timeout_sec':timeout}}
    original=backend.command;isolated=FunctionType(original.__code__,{**original.__globals__,'write_json':lambda *_:None},original.__name__,original.__defaults__,original.__closure__);isolated.__kwdefaults__=original.__kwdefaults__
    expected=isolated(workspace,control,Path(payload['review_inventory']['catalog']),blind,mcp=mcp,readonly=True)
    c.require(actual['argv']==expected,'Actual reviewer argv/MCP/prompt differs from full readonly reconstruction')
    receipts['review']={'request_json_sha256':c.sha(control/'request.json'),'prompt_sha256':hashlib.sha256(blind.encode()).hexdigest(),'server_config_sha256':c.sha(control/'server-config.json'),'full_argv_mcp_prompt_reconstruction_passed':True}
    return {'main_launch_source_sha256':launch,'stage_envelopes':receipts}


def stage_summary(stage,role,directory):
    route=c.REVIEW if role=='review' else c.DEV
    qualification=stage.get('qualification',{})
    terminal=c.r.terminal(stage)
    actual_request=c.read(directory/role/'call'/'request.json')
    public={key:stage.get(key) for key in ('backend','requested_effort','process_exit','timed_out','wall_seconds','total_cost_usd','stream_sha256','request_sha256','process_cleanup_scope','detached_descendants_contained','guarded_new_session_processes','stream_changed_during_cleanup','source_sha256_at_launch','source_sha256_after')}
    public.update(model_requested=actual_request.get('model_requested',route['model']),
        actual_model=qualification.get('actual_model'),model_attribution=qualification.get('model_attribution'),
        observed_models=stage.get('observed_assistant_models') if role!='review' else stage.get('observed_models'),
        qualified=qualification.get('eligible'),qualification_failures=qualification.get('failures'),usage=usage(stage),
        terminal_known=terminal is not None,complete=terminal.get('complete') if terminal else None,
        remaining=terminal.get('remaining') if terminal else None,
        assigned_timeout_seconds=actual_request.get('timeout_seconds'),assigned_budget_usd=actual_request.get('budget_usd'),
        stage_receipt_sha256=c.sha(directory/role/'receipt.json'),raw_request_sha256=c.sha(directory/role/'call'/'request.json'))
    if role in ('main','closure'):
        public['summary']=terminal.get('summary') if terminal else None
    else:
        public['scope_limits']=[]
        if terminal:
            try:public['scope_limits']=json.loads(terminal['summary']).get('scope_limits',[])
            except (TypeError,ValueError):pass
    return safe_value(public)


def checks_summary(rows,receipt_sha):
    keys=('id','requested_argv','exit_code','timed_out','wall_seconds','source_sha256','source_unchanged','passed','stdout_sha256','stderr_sha256','process_cleanup_scope','detached_descendants_contained')
    return {'receipt_sha256':receipt_sha,'rows':[safe_value({key:row.get(key) for key in keys}) for row in rows]}


def grade_summary(grade,receipt_sha):
    public={key:grade.get(key) for key in ('oracle_passed','exit_code','timed_out','wall_seconds','source_sha256','stdout_sha256','stderr_sha256','process_cleanup_scope','detached_descendants_contained','output_changed_during_cleanup')}
    header=grade.get('header');public['header']={key:header.get(key) for key in ('task_id','exit_code','passed','tests','production_scope','output_sha256') if key in header} if isinstance(header,dict) else None
    public['receipt_sha256']=receipt_sha
    return safe_value(public)


def changed_paths(base,candidate):
    left=c.inventory(base);right=c.inventory(candidate)
    return [path for path in sorted(set(left)|set(right)) if left.get(path)!=right.get(path)]


def out_of_scope_diff(base,candidate,paths,destination):
    pieces=[];metadata=[]
    for relative in paths:
        c.require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'Unsafe out-of-scope path')
        old=base/relative;new=candidate/relative
        before=old.read_bytes() if old.is_file() else b'';after=new.read_bytes() if new.is_file() else b''
        exact_safe_bytes(before,'Out-of-scope original '+relative);exact_safe_bytes(after,'Out-of-scope candidate '+relative)
        left=before.decode('utf-8').splitlines(keepends=True);right=after.decode('utf-8').splitlines(keepends=True)
        pieces.append(''.join(difflib.unified_diff(left,right,fromfile='a/'+relative if old.exists() else '/dev/null',tofile='b/'+relative if new.exists() else '/dev/null')))
        metadata.append({'path':relative,'before_sha256':hashlib.sha256(before).hexdigest() if old.exists() else None,
            'after_sha256':hashlib.sha256(after).hexdigest() if new.exists() else None,'before_mode':old.stat().st_mode&0o777 if old.exists() else None,'after_mode':new.stat().st_mode&0o777 if new.exists() else None,
            'change':'modified' if old.exists() and new.exists() else 'added' if new.exists() else 'deleted'})
    data=''.join(pieces).encode();exact_safe_bytes(data,'Out-of-scope unified diff');destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
    return {'path':destination.name,'sha256':c.sha(destination),'files':metadata,
        'format':'Exact UTF-8 line diff plus separate original/candidate byte hashes and modes; no production scope substitution'}


def rejection_reasons(receipt):
    reasons=[]
    if receipt.get('status')!='completed':reasons.append('cell_status_'+str(receipt.get('status')))
    if not c.main_provenance(receipt.get('main',{})):reasons.append('main_model_tool_lifecycle_provenance_unqualified')
    for side in ('first','final'):
        if receipt.get(side,{}).get('scope_violations'):reasons.append(side+'_source_scope_violations')
    closure=receipt.get('closure',{});terminal=c.r.terminal(closure)
    if closure.get('qualification',{}).get('eligible') is not True:reasons.append('final_developer_stage_unqualified')
    if terminal is None:reasons.append('final_terminal_missing_or_invalid')
    else:
        if terminal['complete'] is not True:reasons.append('final_developer_complete_false')
        if terminal['remaining']!=[]:reasons.append('final_developer_remaining_nonempty')
    if receipt.get('review_qualified') is not True:reasons.append('independent_review_unqualified_or_incomplete')
    if receipt.get('final_grade',{}).get('oracle_passed') is not True:reasons.append('final_frozen_behavioral_grade_not_passed')
    if receipt.get('final_binding_valid') is not True:reasons.append('final_source_patch_grade_binding_invalid')
    if receipt.get('final_checks_passed') is not True:reasons.append('final_immutable_required_checks_not_passed')
    if receipt.get('unresolved_findings')!=[]:reasons.append('blocking_review_findings_unresolved_or_unknown')
    c.require(bool(reasons) is (receipt.get('accepted') is not True),'Rejection reasons contradict sealed primary acceptance')
    return reasons


def export_cell(receipt,request,task,payload,study,output,primary):
    directory=study/'trials'/request['trial_id'];patchdir=output/'patches'/request['trial_id'];patchdir.mkdir(parents=True)
    # Re-use the sealed controller's independent reconstruction before exporting
    # any acceptance claims. This does not re-execute a grader or infer a model.
    derived=c.derive_receipt(receipt,request,task,payload,directory,study)
    inputs=reconstructed_envelope(derived,request,task,payload,directory)
    patches={};scope={};base=Path(task['base_snapshot'])
    for side in ('first','final'):
        source=directory/side/'source';original=directory/side/'submitted.patch';data=exact_safe_bytes(original.read_bytes(),side+' production patch')
        destination=patchdir/(side+'.production.patch');destination.write_bytes(data)
        c.require(c.sha(destination)==derived[side]['patch_sha256'],'Copied production patch differs')
        patches[side]={'path':destination.relative_to(output).as_posix(),'sha256':c.sha(destination),'source_sha256':derived[side]['source_sha256']}
        diff=out_of_scope_diff(base,source,derived[side]['scope_violations'],patchdir/(side+'.out-of-scope.patch'))
        diff['path']=(patchdir/diff['path']).relative_to(output).as_posix()
        scope[side]={'scope_violations':derived[side]['scope_violations'],'out_of_scope_diff':diff,
            'all_changed_paths':changed_paths(base,source),'submitted_paths':derived[side]['submitted_paths']}
    stages={role:stage_summary(derived[role],role,directory) for role in ('main','review','closure')}
    checks={key:checks_summary(derived[key],c.sha(directory/folder/'receipt.json')) for key,folder in (('first_checks','first-checks'),('final_checks','final-checks'),('witness_before','witness-before'),('witness_after','witness-after'))}
    return {**request,'primary':{key:primary.get(key) for key in ('status','first_pass','actual_repair','accepted','unresolved_findings')},
        'recorded_primary_receipt_sha256':c.sha(directory/'receipt.json'),'supplemental_input_reconstruction':inputs,
        'stages':stages,'grades':{side:grade_summary(derived[side+'_grade'],c.sha(directory/(side+'-grade')/'receipt.json')) for side in ('first','final')},
        'checks_and_witnesses':checks,'review_findings':safe_value(derived['review_findings']),
        'rejection_reasons':rejection_reasons(derived),'scope':safe_value(scope),'patches':patches,
        'delivery_distinction':{'first_selected_behavioral_grade_passed':derived['first_grade']['oracle_passed'],'final_selected_behavioral_grade_passed':derived['final_grade']['oracle_passed'],
            'primary_final_delivery_accepted':derived['accepted'],'production_patch_changed_in_closure':derived['actual_repair'],
            'full_confidence_protocol_release_certified':False}}


def available_artifacts(receipt,request,task,study,output):
    """Inspect available bound patches even when the whole cell cannot qualify."""
    directory=study/'trials'/request['trial_id'];patchdir=output/'patches'/request['trial_id'];patchdir.mkdir(parents=True,exist_ok=True)
    result={};adapter=c.runtime(c.DEV);base=Path(task['base_snapshot'])
    for side in ('first','final'):
        source=directory/side/'source';patch=directory/side/'submitted.patch';record=receipt.get(side,{})
        if not source.is_dir() or not patch.is_file():
            result[side]={'status':'artifact_absent'};continue
        try:
            c.a.bound(patch,record.get('patch_sha256'),'Available production patch')
            current=adapter.frozen.base.tree_digest(source);c.require(current==record.get('source_sha256'),'Available source digest differs')
            violations=adapter.frozen.base.scope_diff(base,source,task['production_paths'])
            data=exact_safe_bytes(patch.read_bytes(),'Available production patch');destination=patchdir/(side+'.production.patch');destination.write_bytes(data)
            scope=out_of_scope_diff(base,source,violations,patchdir/(side+'.out-of-scope.patch'));scope['path']=(patchdir/scope['path']).relative_to(output).as_posix()
            result[side]={'status':'current_artifacts_hash_bound_whole_cell_unqualified','source_sha256':current,'production_patch':{'path':destination.relative_to(output).as_posix(),'sha256':c.sha(destination)},'scope_violations':violations,'out_of_scope_diff':scope}
        except Exception as error:result[side]={'status':'artifact_custody_or_privacy_failure','error':safe_text(str(error))}
    return result

def export(study,output):
    study=Path(study).resolve();output=Path(output).resolve()
    c.require(output.is_relative_to(HERE),'Output must stay within new private post-analysis directory')
    c.require(not output.exists(),'Fresh post-outcome export directory required')
    closure=c.read(study/'closure.json');c.require(closure.get('closed') is True and closure.get('assigned')==6,'All six assigned cells must be closed before post-outcome analysis')
    payload=c.verify(study);requests=c.read(study/'requests.json');c.validate_roster(requests,c.read(payload['config']['manifest'])['tasks'])
    c.a.bound(study/'registration.json',closure['registration_sha256'],'Closure registration')
    c.a.bound(study/'results.json',closure['results_sha256'],'Closure results')
    c.require(all((study/'trials'/r['trial_id']/'receipt.json').is_file() for r in requests),'Missing final assigned cell receipt')
    output.mkdir(parents=True)
    # The existing analyze() writes one new analysis JSON; redirect only that
    # destination to preserve all sealed study files and this agent's ownership.
    original_write=c.write
    def redirect(path,value):
        c.require(Path(path).resolve()==study/'analysis.json','Unexpected sealed analyzer write')
        return original_write(output/'sealed-controller-analysis.private.json',value)
    c.write=redirect
    try:primary=c.analyze(study)
    finally:c.write=original_write
    tasks={t['task_id']:t for t in c.read(payload['config']['manifest'])['tasks']};indexed={row['trial_id']:row for row in primary['rows']};rows=[];failures=[]
    for request in requests:
        directory=study/'trials'/request['trial_id'];receipt=c.read(directory/'receipt.json')
        try:
            c.require(indexed[request['trial_id']]['status']!='analysis_binding_error','Sealed controller reported analysis custody failure: '+str(indexed[request['trial_id']].get('error')))
            rows.append(export_cell(receipt,request,tasks[request['task_id']],payload,study,output,indexed[request['trial_id']]))
        except Exception as error:
            failures.append({'trial_id':request['trial_id'],'error':safe_text(type(error).__name__+': '+str(error))})
            rows.append({**request,'primary':safe_value(indexed[request['trial_id']]),'supplemental_export_status':'custody_or_privacy_failure','error':failures[-1]['error'],
                'available_patch_artifacts':available_artifacts(receipt,request,tasks[request['task_id']],study,output)})
    public={'schema_version':1,'post_outcome':True,'assigned':6,'sealed_primary_metric_unchanged':True,
        'registration_sha256':c.sha(study/'registration.json'),'requests_sha256':c.sha(study/'requests.json'),'closure_sha256':c.sha(study/'closure.json'),
        'sealed_controller_sha256':c.sha(RUNTIME/'controller.py'),'post_outcome_exporter_sha256':c.sha(__file__),
        'primary_by_arm':primary['by_arm'],'rows':rows,'supplemental_custody_failures':failures,
        'limitations':payload['limitations']+['This helper was written after the first scored outcome; all supplemental fields are descriptive and cannot redefine primary acceptance.',
            'Selected frozen grader/check success is scoped behavioral evidence, not complete Confidence Protocol certification.',
            'Public fields are allowlisted; raw streams, command output, session identifiers, authentication and private paths remain private.',
            'Out-of-scope diffs are exported separately so excluded edits remain inspectable. No primary scope rejection is erased.']}
    public=safe_value(public);encoded=(json.dumps(public,indent=2)+'\n').encode();exact_safe_bytes(encoded,'Public supplemental JSON')
    (output/'RESULTS.public.json').write_bytes(encoded)
    c.write(output/'export-receipt.private.json',{'post_outcome':True,'public_results_sha256':c.sha(output/'RESULTS.public.json'),'supplemental_custody_passed':not failures,'failures':failures})
    return public

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=export(args.study,args.output)
    print(json.dumps({'assigned':result['assigned'],'supplemental_custody_failures':result['supplemental_custody_failures']}))
    raise SystemExit(1 if result['supplemental_custody_failures'] else 0)
