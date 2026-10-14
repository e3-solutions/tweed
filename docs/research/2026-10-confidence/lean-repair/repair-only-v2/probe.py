#!/usr/bin/env python3
"""Prospective separate pair correcting one authentic observed README scope breach.

No new task, development trial, primary rescore, production-defect injection,
reviewer/discovery, retry or guidance superiority claim. One call per policy.

v2 is a new prospectively registered setup correction: the original separately
sealed scope pair retained two FileExistsError failures before any hosted call
(the authentic copy already carried .protocol). Those failures and the six
primary outcomes are unchanged; this is not a hidden retry or added primary
success. After verifying the authentic copied tree digest, only the copied
.protocol directory is removed before mounting the assigned frozen policy.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('scope_probe_sealed_helpers',HERE.parent/'runtime'/'controller.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
PIN={'source_sha256':'6d1fb324622cea73a8ee315be8ca9127ab7a39ab35ead33e4e8bf89934323a26',
 'patch_sha256':'852ed393133fcfc218230ffb23af6eec6599c565c53846678f5816107a1c2ea0',
 'README.md':'5738d12966bc6514ef965be7e0cc470d6a5f2ed51d2784e5f2c7ff6cdcf3f10c',
 'base_README.md':'5a8bbcd1546d8c6c6279037dc4cfbf9b884bc8af871ea54749ce968279921b7e',
 'bonaparte':'2c2e9edfcaf5d06074b419c083873d72459d5195a7f3c1c8a7f4cb02d6287f88',
 'receipt_sha256':'93dca369b04271bdb80b6b0b14ded3c2607c83858121962202f7648d7e905994'}
ORDER=('original','revised')


def production(base,candidate,paths):
    names=set(paths);names.update(p.name for p in candidate.glob('*.py') if not (base/p.name).exists())
    result={}
    for name in sorted(names):
        path=candidate/name
        c.require(not path.is_symlink(),'Production symlink refused')
        result[name]={'sha256':c.sha(path),'mode':path.stat().st_mode&0o777} if path.is_file() else None
    return result


def changes(before,after):
    left=c.inventory(before);right=c.inventory(after)
    return [path for path in sorted(set(left)|set(right)) if left.get(path)!=right.get(path)]


def authentic(primary):
    payload=c.verify(primary);closure=c.read(primary/'closure.json')
    c.require(closure.get('closed') is True and closure.get('assigned')==6,'Six primary cells must finish before supplemental preparation')
    c.a.bound(primary/'registration.json',closure['registration_sha256'],'Primary closure registration')
    c.a.bound(primary/'results.json',closure['results_sha256'],'Primary closure results')
    requests=c.read(primary/'requests.json');c.validate_roster(requests,c.read(payload['config']['manifest'])['tasks'])
    for request in requests:
        row=c.read(primary/'trials'/request['trial_id']/'receipt.json')
        c.require(row.get('actual_repair') is False,'A primary production repair was observed; supplemental pair is not admitted')
    task=next(t for t in c.read(payload['config']['manifest'])['tasks'] if t['task_id']=='tweed-pr20')
    origin=primary/'trials'/'tweed-pr20--revised--r1';candidate=origin/'final'/'source';base=Path(task['base_snapshot'])
    c.a.bound(origin/'receipt.json',PIN['receipt_sha256'],'Authentic origin receipt')
    c.a.bound(origin/'final'/'submitted.patch',PIN['patch_sha256'],'Authentic production patch')
    c.a.bound(candidate/'README.md',PIN['README.md'],'Authentic candidate README')
    c.a.bound(candidate/'bonaparte',PIN['bonaparte'],'Authentic candidate production')
    c.a.bound(base/'README.md',PIN['base_README.md'],'Pinned baseline README')
    adapter=c.runtime(c.DEV);c.require(adapter.frozen.base.tree_digest(candidate)==PIN['source_sha256'],'Authentic full candidate source differs')
    receipt=c.read(origin/'receipt.json');c.require(receipt['first_grade']['oracle_passed'] is True and receipt['final_grade']['oracle_passed'] is True and receipt['actual_repair'] is False,'Authentic observed candidate facts differ')
    c.require(adapter.frozen.base.scope_diff(base,candidate,task['production_paths'])==['README.md'],'Authentic README scope breach changed')
    return payload,task,origin,candidate


def prepare(primary,study):
    primary=Path(primary).resolve();study=Path(study).resolve();c.require(study.is_relative_to(HERE) and not study.exists(),'Fresh private repair-only output required')
    payload,task,origin,candidate=authentic(primary);study.mkdir(parents=True)
    adapter=c.runtime(c.DEV);base=Path(task['base_snapshot']);checkdir=study/'candidate-controls'
    # Fresh current-byte behavioral verification, outside both repair clocks.
    grade=c.grade(adapter,task,candidate,checkdir,time.time()+60);c.require(grade['oracle_passed'] is True,'Authentic candidate behavioral precheck failed')
    checks,check_source=c.witnesses_execute(adapter,task,candidate,study/'candidate-checks',task['required_checks'],time.time()+60)
    c.require(all(row['passed'] for row in checks),'Authentic candidate focused precheck failed')
    diff=''.join(difflib.unified_diff((base/'README.md').read_text().splitlines(keepends=True),(candidate/'README.md').read_text().splitlines(keepends=True),fromfile='a/README.md',tofile='b/README.md'))
    disclosed=c.feedback(checks,grade,checkdir)
    packet={'task_id':'tweed-pr20','accepted_task_prompt':task['prompt'],'visible_commands':task['test_commands'],
        'authentic_origin_trial':'tweed-pr20--revised--r1','authentic_candidate_source_sha256':PIN['source_sha256'],
        'failed_machine_scope_verdict':{'scope_violations':['README.md'],'passed':False},'nonproduction_README_diff':diff,
        'baseline_README_bytes':(base/'README.md').read_text(),'baseline_README_sha256':PIN['base_README.md'],
        'existing_executed_passing_behavior_and_checks':disclosed}
    prompt=('Read .protocol/SKILL.md and relevant references. This is a separate, sole bounded scope-correction attempt of an existing candidate, not a new implementation. '
        'The entire authentic candidate is already in the workspace. Correct the explicit failed scope gate below by restoring README.md to the supplied pinned baseline bytes; this restoration is expressly authorized solely to remove that breach. '
        'Preserve bonaparte and all existing candidate production helpers byte-for-byte. Do not add product features, new production helpers or other documentation changes. '
        'No reviewer or discovery stage is available. Execute relevant verification and report remaining work truthfully. Distinguish required unfinished work from limitations already excluded by the offline task. '
        'This exercise cannot certify full Confidence Protocol release gates.\nCommon packet:\n'+json.dumps(packet))
    c.write(study/'packet.json',packet)
    roster=[{'attempt_id':'pr20-observed-scope-v2-'+arm+'-r1','task_id':'tweed-pr20','arm_id':arm,'repeat':1,'prompt':prompt} for arm in ORDER]
    c.write(study/'requests.json',roster)
    files={str(path):c.sha(path) for path in (Path(__file__).resolve(),primary/'registration.json',primary/'closure.json',primary/'results.json',origin/'receipt.json',origin/'final'/'submitted.patch',study/'packet.json',study/'requests.json',checkdir/'receipt.json',study/'candidate-checks'/'receipt.json')}
    for path,expected in payload['material']['files'].items():files[path]=expected
    trees={str(candidate):c.inventory(candidate),str(base):c.inventory(base)}
    trees.update({path:c.inventory(path) for path in [payload['config']['toolkit_directory'],*[payload['config']['arms'][arm]['policy_directory'] for arm in ORDER]]})
    repair_payload={'primary_study':str(primary),'primary_registration_sha256':c.sha(primary/'registration.json'),'candidate':str(candidate),'candidate_pin':PIN,
        'task':task,'config':payload['config'],'roster':[{key:row[key] for key in ('attempt_id','task_id','arm_id','repeat')} for row in roster],
        'requests_sha256':c.sha(study/'requests.json'),'packet_sha256':c.sha(study/'packet.json'),'material':{'files':files,'trees':trees},
        'developer':c.DEV,'call_seconds':90,'call_budget_usd':1,'owner_checks_seconds':60,'sequence':list(ORDER),
        'qualified_scope_correction_rule':'Qualified actual Opus terminal/process/tools; README restored to pinned baseline; prior scope breach removed; production bytes/patch unchanged; immutable focused checks and unchanged public-boundary grader pass within owner allowance. Complete/remaining recorded separately; excluded limitations never rewrite primary acceptance.',
        'limitations':['Two separate correction attempts of one outcome-selected revised-origin README scope breach; not new development tasks or production bug repairs.',
            'Common supplemental feedback explicitly discloses the scope verdict/nonproduction diff absent from primary closure packets; no causal policy-improvement claim.',
            'Original primary strict acceptance and six-cell scores remain untouched. Full source corrections and production patch changes are distinct.',
            'Stage policy context is the sole assigned instruction difference; the complete authentic candidate is copied and digest-verified, then only its copied .protocol directory is removed before mounting each frozen policy.',
            'New prospectively registered setup correction after the original sealed scope pair retained two pre-inference FileExistsError infrastructure failures; those failures and six primary outcomes stay unchanged. Not a hidden retry or added primary success.']}
    c.write(study/'registration.json',{'payload':repair_payload,'payload_sha256':c.digest(repair_payload)})
    return repair_payload


def verify(study):
    study=Path(study).resolve();seal=c.read(study/'registration.json');payload=seal['payload']
    c.require(c.digest(payload)==seal['payload_sha256'],'Repair-only registration changed')
    for path,expected in payload['material']['files'].items():c.a.bound(path,expected,'Repair-only input')
    for path,expected in payload['material']['trees'].items():c.require(c.inventory(path)==expected,'Repair-only input tree changed')
    roster=c.read(study/'requests.json');c.require([{key:row[key] for key in ('attempt_id','task_id','arm_id','repeat')} for row in roster]==payload['roster'],'Fixed pair roster changed')
    c.require([row['arm_id'] for row in roster]==list(ORDER) and roster[0]['prompt']==roster[1]['prompt'],'Pair order/common packet differs')
    c.verify(Path(payload['primary_study']))
    return payload


def run_attempt(request,payload,study):
    directory=study/'attempts'/request['attempt_id'];c.claim(directory,request)
    receipt={key:request[key] for key in ('attempt_id','task_id','arm_id','repeat')};receipt.update(status='started',registration_sha256=c.sha(study/'registration.json'),scope_correction_observed=None,qualified_scope_correction=False)
    try:
        adapter=c.runtime(c.DEV);base=adapter.frozen.base;task=payload['task'];candidate=Path(payload['candidate']);baseline=Path(task['base_snapshot'])
        with tempfile.TemporaryDirectory(prefix='cp-real-scope-correction-') as temporary:
            workspace=Path(temporary).resolve()/'workspace';base.safe_copy(candidate,workspace)
            receipt['authentic_pre_mount_source_sha256']=base.tree_digest(workspace)
            c.require(receipt['authentic_pre_mount_source_sha256']==PIN['source_sha256'],'Candidate changed before mounting policy')
            copied=workspace/'.protocol';c.require(copied.is_dir() and not copied.is_symlink(),'Copied candidate .protocol directory missing');shutil.rmtree(copied)
            c.r.mount(base,payload['config']['toolkit_directory'],payload['config']['arms'][request['arm_id']]['policy_directory'],workspace)
            scratch=workspace/'.trial-tmp';scratch.mkdir(exist_ok=True)
            for args in (['init','-q'],['add','.'],['-c','user.name=ScopeRepair','-c','user.email=scope-repair@example.invalid','commit','-qm','Authentic candidate']):
                subprocess.run([base.GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',*args],cwd=workspace,env=base.safe_env(workspace,scratch),capture_output=True,check=True)
            before=directory/'before';base.safe_copy(workspace,before)
            source_before=base.tree_digest(before);production_before=production(baseline,before,task['production_paths'])
            call=c.claim(directory/'repair','sole-opus-scope-repair')
            local=adapter.local_mcp_probe('opus',workspace,call/'qualification',readonly=False)
            c.require(local.get('passed') is True,'Offline transport failed before inference')
            stage=base.claude_call(workspace,call/'call',request['prompt'],1,90,time.time()+90)
            stage['backend']='claude';stage['qualification']=c.qualify_stage(adapter,stage,local,c.DEV)
            stage.update(source_sha256_at_launch=source_before,source_sha256_after=base.tree_digest(workspace))
            stage['artifact_files']={str(path.relative_to(call)):c.sha(path) for path in call.rglob('*') if path.is_file() and path!=call/'receipt.json' and 'execution-scratch' not in path.parts}
            # Ephemeral command scratch may contain actor-created symlinks. It is
            # not source and not essential receipt evidence; record only actual
            # request/stream/config/tool events/qualification and command outputs.
            c.write(call/'receipt.json',stage);receipt['repair']=stage
            owner_deadline=time.time()+payload['owner_checks_seconds']
            final=directory/'final';base.safe_copy(workspace,final)
            production_after=production(baseline,final,task['production_paths']);receipt['before_source_sha256']=source_before;receipt['final_source_sha256']=base.tree_digest(final)
            receipt['source_changed_paths']=changes(before,final);receipt['full_snapshot_changed']=source_before!=receipt['final_source_sha256']
            receipt['candidate_content_changed_paths']=[path for path in changes(candidate,final) if Path(path).parts[0]!='.protocol']
            receipt['README_restored']=c.sha(final/'README.md')==PIN['base_README.md'];receipt['README_changed']=c.sha(final/'README.md')!=PIN['README.md']
            receipt['scope_before']=base.scope_diff(baseline,before,task['production_paths']);receipt['scope_after']=base.scope_diff(baseline,final,task['production_paths'])
            receipt['production_before']=production_before;receipt['production_after']=production_after;receipt['production_bytes_preserved']=production_before==production_after
            patch,_=c.a.rebuild_patch(adapter,baseline,final,directory/'final.production.patch',task['production_paths']);receipt['production_patch_sha256']=hashlib.sha256(patch).hexdigest();receipt['production_patch_changed']=receipt['production_patch_sha256']!=PIN['patch_sha256']
            checks,check_source=c.witnesses_execute(adapter,task,final,directory/'owner-checks',task['required_checks'],owner_deadline)
            receipt['owner_checks']=checks;receipt['owner_check_source_sha256']=check_source
            receipt['final_grade']=c.grade(adapter,task,final,directory/'final-grade',owner_deadline)
            receipt['owner_checks_completed_at_unix']=time.time();receipt['owner_deadline_met']=receipt['owner_checks_completed_at_unix']<=owner_deadline
            receipt['scope_correction_observed']=receipt['README_restored'] and receipt['README_changed'] and receipt['scope_before']==['README.md'] and receipt['scope_after']==[]
            receipt['qualified_scope_correction']=bool(stage['qualification']['eligible'] and receipt['scope_correction_observed'] and receipt['production_bytes_preserved'] and not receipt['production_patch_changed'] and all(row['passed'] for row in checks) and receipt['final_grade']['oracle_passed'] is True and receipt['owner_deadline_met'])
            receipt['status']='completed';receipt['owner_deadline_unix']=owner_deadline
    except Exception as error:receipt.update(status='infrastructure_or_artifact_error',error=type(error).__name__+': '+str(error))
    receipt['ended_at_unix']=time.time();c.write(directory/'receipt.json',receipt);return receipt


def run(study):
    study=Path(study).resolve();payload=verify(study);c.activated(study);c.claim(study/'run-start','sole-sequential-pair')
    roster=c.read(study/'requests.json');closed=False
    try:
        for request in roster:
            verify(study);row=run_attempt(request,payload,study)
            print(json.dumps({key:row.get(key) for key in ('attempt_id','status','scope_correction_observed','qualified_scope_correction','production_patch_changed')}),flush=True)
        closed=True
    finally:
        rows=[]
        for request in roster:
            path=study/'attempts'/request['attempt_id']/'receipt.json';rows.append(c.read(path) if path.exists() else {key:request[key] for key in ('attempt_id','task_id','arm_id','repeat')}|{'status':'started_unknown' if path.parent.exists() else 'never_started','qualified_scope_correction':False})
        c.write(study/'results.json',rows);c.write(study/'closure.json',{'closed':closed,'assigned':2,'registration_sha256':c.sha(study/'registration.json'),'results_sha256':c.sha(study/'results.json')})
    return rows


def derive(request,payload,directory,study):
    raw=c.read(directory/'receipt.json');c.require(all(raw.get(key)==request[key] for key in ('attempt_id','task_id','arm_id','repeat')),'Attempt identity differs')
    c.a.bound(study/'registration.json',raw['registration_sha256'],'Attempt registration')
    c.require(raw.get('status')=='completed','Supplemental attempt did not complete; retained failure/unknown')
    adapter=c.runtime(c.DEV);base=adapter.frozen.base;task=payload['task'];baseline=Path(task['base_snapshot']);candidate=Path(payload['candidate']);before=directory/'before';final=directory/'final';stage=raw['repair']
    # Re-use sealed stream/provider/model/tool qualification with private,
    # prospectively registered role caps. No sealed source/global study changes.
    previous=c.CAPS
    c.CAPS={**previous,'closure':(90,1)}
    try:c.validate_stage(stage,directory/'repair','closure',adapter)
    finally:c.CAPS=previous
    request_raw=c.read(directory/'repair'/'call'/'request.json');c.require(request_raw.get('prompt')==request['prompt'],'Sole repair prompt differs from sealed common packet')
    c.a.request_envelope(directory/'repair'/'call',request_raw,c.DEV,{'claude_budget_usd':1},request['prompt'],adapter,payload)
    with tempfile.TemporaryDirectory(prefix='cp-scope-launch-rederive-') as temporary:
        launch=Path(temporary).resolve()/'workspace';base.safe_copy(candidate,launch)
        c.require(base.tree_digest(launch)==raw['authentic_pre_mount_source_sha256']==PIN['source_sha256'],'Authentic source launch differs')
        copied=launch/'.protocol';c.require(copied.is_dir() and not copied.is_symlink(),'Copied candidate .protocol directory missing');shutil.rmtree(copied)
        c.r.mount(base,payload['config']['toolkit_directory'],payload['config']['arms'][request['arm_id']]['policy_directory'],launch)
        c.require(c.inventory(launch)==c.inventory(before),'Assigned policy launch source reconstruction differs')
    before_sha=base.tree_digest(before);final_sha=base.tree_digest(final)
    c.require(before_sha==raw['before_source_sha256']==stage['source_sha256_at_launch'] and final_sha==raw['final_source_sha256']==stage['source_sha256_after'],'Repair source associations differ')
    c.require(c.a.oracle_truth(raw['final_grade'],directory/'final-grade')==raw['final_grade']['oracle_passed'] and raw['final_grade']['source_sha256']==final_sha,'Final unchanged grader binding differs')
    with tempfile.TemporaryDirectory(prefix='cp-scope-owner-rederive-') as temporary:
        projected=Path(temporary).resolve()/'source';check_sha=c.witness_projection(base,task,final,projected)
        c.require(c.inventory(projected)==c.inventory(directory/'owner-checks'/'source') and check_sha==raw['owner_check_source_sha256'],'Immutable owner check input differs')
        patch,_=c.a.rebuild_patch(adapter,baseline,final,Path(temporary)/'rebuilt.patch',task['production_paths'])
    c.a.bound(directory/'final.production.patch',raw['production_patch_sha256'],'Final production patch')
    c.require(hashlib.sha256(patch).hexdigest()==raw['production_patch_sha256'],'Current final production patch reconstruction differs')
    c.validate_checks(raw['owner_checks'],directory/'owner-checks',task['required_checks'],check_sha)
    expected={
        'source_changed_paths':changes(before,final),'full_snapshot_changed':before_sha!=final_sha,
        'candidate_content_changed_paths':[path for path in changes(candidate,final) if Path(path).parts[0]!='.protocol'],
        'README_restored':c.sha(final/'README.md')==PIN['base_README.md'],'README_changed':c.sha(final/'README.md')!=PIN['README.md'],
        'scope_before':base.scope_diff(baseline,before,task['production_paths']),'scope_after':base.scope_diff(baseline,final,task['production_paths']),
        'production_before':production(baseline,before,task['production_paths']),'production_after':production(baseline,final,task['production_paths']),
        'production_patch_changed':raw['production_patch_sha256']!=PIN['patch_sha256']}
    expected['production_bytes_preserved']=expected['production_before']==expected['production_after']
    expected['scope_correction_observed']=expected['README_restored'] and expected['README_changed'] and expected['scope_before']==['README.md'] and expected['scope_after']==[]
    # Ended receipt is saved after these checks; the registered owner deadline is
    # receipt-derived, not an actor completion claim.
    c.require(type(raw.get('owner_deadline_met')) is bool and type(raw.get('owner_deadline_unix')) in (int,float),'Owner deadline receipt unknown')
    c.require(type(raw.get('owner_checks_completed_at_unix')) in (int,float) and raw['owner_deadline_met'] is (raw['owner_checks_completed_at_unix']<=raw['owner_deadline_unix']),'Recorded owner deadline success contradicts check completion time')
    expected['qualified_scope_correction']=bool(stage['qualification']['eligible'] and expected['scope_correction_observed'] and expected['production_bytes_preserved'] and not expected['production_patch_changed'] and all(row['passed'] for row in raw['owner_checks']) and raw['final_grade']['oracle_passed'] is True and raw['owner_deadline_met'])
    for key,value in expected.items():c.require(raw.get(key)==value,'Recorded supplemental fact differs: '+key)
    return raw


def public_text(value):
    return re.sub(r'/(?:Users|private|var/folders)/[^\s\"\'<>`;,\]\[()]*','[private-path-redacted]',str(value))


def export(study,output):
    study=Path(study).resolve();output=Path(output).resolve();c.require(output.is_relative_to(HERE) and not output.exists(),'Fresh repair-only export output required')
    payload=verify(study);closure=c.read(study/'closure.json');c.require(closure.get('closed') is True and closure.get('assigned')==2,'Sole pair must close before export')
    c.a.bound(study/'registration.json',closure['registration_sha256'],'Pair closure registration');c.a.bound(study/'results.json',closure['results_sha256'],'Pair closure results')
    output.mkdir(parents=True);rows=[];failures=[]
    for request in c.read(study/'requests.json'):
        directory=study/'attempts'/request['attempt_id']
        try:
            raw=derive(request,payload,directory,study);stage=raw['repair'];terminal=c.r.terminal(stage)
            metadata={key:raw[key] for key in ('attempt_id','task_id','arm_id','repeat','status','scope_correction_observed','qualified_scope_correction','full_snapshot_changed','README_restored','README_changed','scope_before','scope_after','production_bytes_preserved','production_patch_changed','production_patch_sha256','before_source_sha256','final_source_sha256','source_changed_paths','candidate_content_changed_paths','owner_deadline_met')}
            metadata['repair_stage']={key:stage.get(key) for key in ('process_exit','timed_out','wall_seconds','observed_assistant_models','requested_effort','total_cost_usd','usage','stream_sha256','request_sha256','process_cleanup_scope','detached_descendants_contained','guarded_new_session_processes','stream_changed_during_cleanup')}
            metadata['repair_stage']['model_requested']=c.DEV['model'];metadata['repair_stage']['qualification']={key:stage['qualification'].get(key) for key in ('eligible','failures','actual_model','model_attribution')}
            metadata['completion_declaration']={'complete':terminal['complete'],'summary':public_text(terminal['summary']),'remaining':[public_text(item) for item in terminal['remaining']]} if terminal else None
            metadata['owner_checks']=[{key:row.get(key) for key in ('id','requested_argv','exit_code','timed_out','source_sha256','source_unchanged','passed','stdout_sha256','stderr_sha256')} for row in raw['owner_checks']]
            metadata['final_grade']={key:raw['final_grade'].get(key) for key in ('oracle_passed','exit_code','timed_out','source_sha256','stdout_sha256','stderr_sha256','output_changed_during_cleanup')}
            metadata['private_receipt_sha256']=c.sha(directory/'receipt.json')
            # Exact product patch and real README correction diff are separate.
            patchdir=output/'patches';patchdir.mkdir(exist_ok=True)
            prod=patchdir/(request['attempt_id']+'.production.patch');shutil.copy2(directory/'final.production.patch',prod)
            before=(directory/'before'/'README.md').read_text().splitlines(keepends=True);after=(directory/'final'/'README.md').read_text().splitlines(keepends=True)
            docdiff=''.join(difflib.unified_diff(before,after,fromfile='a/README.md',tofile='b/README.md'))
            correction=patchdir/(request['attempt_id']+'.README-correction.patch');correction.write_text(docdiff)
            metadata['patches']={kind:{'path':path.relative_to(output).as_posix(),'sha256':c.sha(path)} for kind,path in (('production',prod),('README_scope_correction',correction))}
            c.require('/Users/' not in prod.read_text() and '/private/' not in prod.read_text() and '/Users/' not in docdiff and '/private/' not in docdiff,'Exact patch public privacy check failed')
            rows.append(metadata)
        except Exception as error:
            failure={'attempt_id':request['attempt_id'],'error':public_text(type(error).__name__+': '+str(error))};failures.append(failure);rows.append({**failure,'qualified_scope_correction':False,'status':'supplemental_custody_failure'})
    result={'supplement':'prospectively sealed sole observed README scope-correction pair','assigned_correction_attempts':2,'task_id':'tweed-pr20','primary_six_cell_metrics_changed':False,
        'registration_sha256':c.sha(study/'registration.json'),'origin_primary_registration_sha256':payload['primary_registration_sha256'],'rows':rows,'custody_failures':failures,
        'limitations':payload['limitations']+['Qualified scope correction is based on independently executed source/preservation/behavior checks; completion/remaining declarations are separate and do not certify full protocol release gates.']}
    encoded=json.dumps(result,indent=2)+'\n';c.require('/Users/' not in encoded and '/private/' not in encoded and 'session_id' not in encoded,'Public export contains private metadata')
    (output/'RESULTS.public.json').write_text(encoded);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run','export']);parser.add_argument('--study',type=Path,required=True);parser.add_argument('--primary',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':c.require(args.primary is not None,'--primary required');result=prepare(args.primary,args.study)
    elif args.action=='run':result=run(args.study)
    else:c.require(args.output is not None,'--output required');result=export(args.study,args.output)
    print(json.dumps({'action':args.action,'custody_failures':result.get('custody_failures',[]) if isinstance(result,dict) else []}))
