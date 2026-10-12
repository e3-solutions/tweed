#!/usr/bin/env python3
"""Export an honestly closed full schedule, including sealed unknown assignments.

This changes no scoring. Existing aggregate rows must exactly equal independently
bound graded receipts. Missing rows require a separately documented, hash-bound
stop inventory and retain null outcomes. No transcripts or free-form model/error
text are projected. Production patches retain their original bytes and hashes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib,importlib.util,json,math
from pathlib import Path,PurePosixPath
import re

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('closed_export_helpers',HERE/'export_results.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
ID=re.compile(r'^[A-Za-z0-9_-]+$')
SHA=re.compile(r'^[a-f0-9]{64}$')
CODE=re.compile(r'^[A-Za-z0-9_.-]+$')
GRADED_FILES={'graded-receipt.json','v2-graded-receipt.json'}
ROLES={'test_designer','main_implementation','adversarial_reviewer','main_repair'}
QUAL_FIELDS={'passed','offline','hosted_inference_calls','readonly','connected','list_files_succeeded',
 'readonly_write_denied','exit_code','stderr_sha256','stdout_sha256','config_argument_is_absolute',
 'live_wire_inventory_observed','strict_seven_tool_parity','local_pipeline_observed'}
MODEL_FIELDS={'model_requested','requested_effort','observed_effort','main_model','peer_model','backend','provider','model_attribution'}
TOKEN_FIELDS={'input_tokens','output_tokens','cached_input_tokens','cache_read_input_tokens','cache_creation_input_tokens',
 'cache_write_input_tokens','reasoning_output_tokens','total_tokens','inputTokens','outputTokens','cacheReadInputTokens',
 'cacheCreationInputTokens','reasoningTokens'}
STAGE_NUMERIC={'declared_complete','total_cost_usd','wall_seconds','timed_out','process_exit',
 'detached_descendants_contained','guarded_new_session_processes','process_cleanup_seconds','stream_changed_during_cleanup'}
PRIVATE_PATH=re.compile(r'/Users/|/private/var/|/var/folders/|[A-Za-z]:\\Users\\')


def read(path):return json.loads(regular(path).read_text())
def sha(path):return hashlib.sha256(regular(path).read_bytes()).hexdigest()
def regular(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('Expected regular evidence file: '+path.name)
    return path

def scalar(value):
    if value is None or isinstance(value,bool):return value
    if isinstance(value,(int,float)) and math.isfinite(value):return value
    raise ValueError('Expected numeric/boolean/null evidence')
def code(value):
    if value is None:return None
    if isinstance(value,str) and CODE.fullmatch(value):return value
    raise ValueError('Unsafe metadata code')
def codes(value):
    if value is None:return None
    if isinstance(value,list):return [codes(v) if isinstance(v,list) else code(v) for v in value]
    raise ValueError('Expected metadata code list')
def counts(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Expected token-count object')
    # Ignore strings and non-count usage properties (geo, errors, model output).
    return {k:scalar(v) for k,v in value.items() if k in TOKEN_FIELDS and
            (v is None or isinstance(v,(int,float,bool)))}

def source_binding_projection(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Expected source binding object')
    out={}
    for key in ('at_launch','after'):
        if key not in value:continue
        item=value[key]
        valid=isinstance(item,str) and re.fullmatch(r'[a-fA-F0-9]{64}',item) is not None
        out[key]=item if valid else None
        if item is not None and not valid:out[key+'_invalid_redacted']=True
    return out

def lifecycle_projection(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Expected lifecycle object')
    out={}
    for key in ('timed_out','process_exit','detached_descendants_contained','guarded_new_session_processes',
                'stream_changed_during_cleanup','process_cleanup_seconds'):
        if key in value:out[key]=scalar(value[key])
    if 'process_cleanup_scope' in value:out['process_cleanup_scope']=code(value['process_cleanup_scope'])
    return out

def qualification(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Expected qualification object')
    out={}
    for k,v in value.items():
        if k in QUAL_FIELDS:
            if k.endswith('_sha256'):
                if v is not None and (not isinstance(v,str) or not SHA.fullmatch(v)):raise ValueError('Unsafe qualification digest')
                out[k]=v
            else:out[k]=scalar(v)
    if 'skipped' in value:out['skipped']=scalar(value['skipped'])
    if 'reasons' in value:out['reasons']=codes(value['reasons'])
    for k in ('basis','provider','schema_output_tool','role'):
        if k in value:out[k]=code(value[k])
    for k in ('missing_tools','unexpected_tools','effective_tools','effective_mcp_tools','expected_mcp_tools',
              'additional_resource_handlers','observed_tool_call_names','declared_tools','expected_tools'):
        if k in value:out[k]=codes(value[k])
    for k in ('local','declared_inventory','local_transport','recorded_qualification'):
        if k in value:out[k]=qualification(value[k])
    if 'source_binding' in value:out['source_binding']=source_binding_projection(value['source_binding'])
    if 'lifecycle' in value:out['lifecycle']=lifecycle_projection(value['lifecycle'])
    # Free-form reason, local cwd/config paths and source explanations omitted.
    return out

def stage_projection(stage):
    out={k:scalar(v) for k,v in stage.items() if k in STAGE_NUMERIC}
    for k in MODEL_FIELDS|{'role','status','process_cleanup_scope'}:
        if k in stage:out[k]=code(stage[k])
    for k in ('observed_models','observed_assistant_models'):
        if k in stage:out[k]=codes(stage[k])
    if 'usage' in stage:out['usage']=counts(stage['usage'])
    if 'adapter_qualification' in stage:out['adapter_qualification']=qualification(stage['adapter_qualification'])
    return out

def project(row):
    # The historical allowlist is kept; nested structures receive stricter
    # type-specific projection rather than trusting arbitrary nested text.
    out=legacy.project(row)
    if 'stage_usage' in row:out['stage_usage']=[stage_projection(s) for s in row['stage_usage']]
    if 'stage_qualification' in row:
        out['stage_qualification']=None if row['stage_qualification'] is None else [qualification(q) for q in row['stage_qualification']]
    if 'source_binding' in row:out['source_binding']=source_binding_projection(row['source_binding'])
    if 'lifecycle' in row:out['lifecycle']=lifecycle_projection(row['lifecycle'])
    for k in MODEL_FIELDS|{'status','trial_id','task_id','arm_id'}:
        if k in out:out[k]=code(out[k])
    for k in ('observed_assistant_models','usage_models','missing_required_reviews'):
        if k in out:out[k]=codes(out[k])
    if 'tokens' in out:out['tokens']=counts(out['tokens'])
    out['harness_invalid_reasons']=[code(v.split(':',1)[0]) for v in row.get('harness_invalid_reasons',[])]
    for k,v in list(out.items()):
        if k.endswith('_sha256') and v is not None and (not isinstance(v,str) or not SHA.fullmatch(v)):
            raise ValueError('Invalid evidence digest')
    for k in ('proof_packet_grade','semantic_correctness_beyond_oracle'):
        if k in out:out[k]=scalar(out[k])
    return out

def identity(row):return row['task_id'],row['arm_id'],row['repeat']
def validate_schedule(schedule):
    keys=[identity(r) for r in schedule]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate schedule identity')
    ids=[r.get('trial_id',r['task_id']+'--'+r['arm_id']+'--r'+str(r['repeat'])) for r in schedule]
    if len(set(ids))!=len(ids) or any(not ID.fullmatch(x) for x in ids):raise ValueError('Unsafe/duplicate trial identity')
    return {identity(r):x for r,x in zip(schedule,ids)}

def seal(study,schedule_path,inventory_path,closure_path,reason,*,graded_filename='graded-receipt.json',completion_evidence=None):
    """Explicit stopped-study snapshot, never a claim that missing trials ran."""
    if graded_filename not in GRADED_FILES:raise ValueError('Unsupported grading receipt filename')
    study=Path(study).resolve();inventory_path=Path(inventory_path).resolve();closure_path=Path(closure_path).resolve()
    if inventory_path.exists() or closure_path.exists():raise ValueError('Fresh closure/inventory paths required')
    schedule=read(schedule_path);mapping=validate_schedule(schedule);entries=[];missing=[]
    for key,trial_id in mapping.items():
        directory=study/'trials'/trial_id
        raw=directory/'receipt.json'
        state='completed_receipt' if raw.exists() else ('interrupted_no_receipt' if directory.exists() else 'never_started')
        files=[]
        if directory.exists():
            wanted=[directory/n for n in ('receipt.json','graded-receipt.json','v2-graded-receipt.json','submitted.patch')]
            wanted += list(directory.glob('*/request.json'))+list(directory.glob('*/receipt.json'))
            for p in sorted(set(wanted)):
                if p.exists():files.append({'path':p.relative_to(directory).as_posix(),'sha256':sha(p)})
        entries.append(dict(trial_id=trial_id,state=state,files=files))
        if state!='completed_receipt':missing.append(dict(trial_id=trial_id,task_id=key[0],arm_id=key[1],repeat=key[2],state=state))
    now=datetime.now(timezone.utc).isoformat()
    inventory=dict(schema_version=1,sealed_at_utc=now,classification=dict(Counter(e['state'] for e in entries)),inventory=entries,
        scope='Retrospective explicitly stopped filesystem inventory; absent assignments were not executed')
    inventory_path.parent.mkdir(parents=True,exist_ok=True);inventory_path.write_text(json.dumps(inventory,indent=2)+'\n')
    closure=dict(schema_version=1,closed_at_utc=now,reason=reason,grading_receipt_filename=graded_filename,schedule_sha256=sha(schedule_path),
        inventory_path=str(inventory_path),inventory_sha256=sha(inventory_path),missing_assignments=missing)
    if completion_evidence is not None:
        completion_evidence=Path(completion_evidence).resolve()
        audit=read(completion_evidence)
        if audit.get('passed') is not True or audit.get('violations'):raise ValueError('Completion audit must pass')
        closure['completion_evidence_path']=str(completion_evidence)
        closure['completion_evidence_sha256']=sha(completion_evidence)
    closure_path.parent.mkdir(parents=True,exist_ok=True);closure_path.write_text(json.dumps(closure,indent=2)+'\n')
    return closure

def validate_closure(study,schedule_path,closure_path,rows):
    closure=read(closure_path)
    if closure.get('schedule_sha256')!=sha(schedule_path):raise ValueError('Closure schedule mismatch')
    if not closure.get('closed_at_utc') or not isinstance(closure.get('reason'),str) or not closure['reason'].strip():raise ValueError('Documented closure required')
    if closure.get('completion_evidence_path') is not None:
        evidence=Path(closure['completion_evidence_path'])
        if sha(evidence)!=closure.get('completion_evidence_sha256') or read(evidence).get('passed') is not True or read(evidence).get('violations'):
            raise ValueError('Completion audit evidence changed or failed')
    inventory_path=Path(closure['inventory_path'])
    if sha(inventory_path)!=closure['inventory_sha256']:raise ValueError('Closure inventory mismatch')
    inventory=read(inventory_path);entries={e['trial_id']:e for e in inventory['inventory']}
    if len(entries)!=len(inventory['inventory']):raise ValueError('Duplicate sealed inventory identity')
    closed={identity(r):r for r in closure['missing_assignments']}
    if len(closed)!=len(closure['missing_assignments']):raise ValueError('Duplicate closure identity')
    expected={identity(r) for r in rows if r.get('status')=='missing_receipt'}
    if set(closed)!=expected:raise ValueError('Closure must cover exactly every missing assignment')
    for row in rows:
        entry=entries.get(row['trial_id'])
        if not entry:raise ValueError('Full schedule must appear in sealed inventory')
        directory=study/'trials'/row['trial_id']
        wanted=[directory/n for n in ('receipt.json','graded-receipt.json','v2-graded-receipt.json','submitted.patch')]
        wanted+=list(directory.glob('*/request.json'))+list(directory.glob('*/receipt.json')) if directory.exists() else []
        actual_files={p.relative_to(directory).as_posix() for p in wanted if p.exists()}
        if actual_files!={f['path'] for f in entry['files']}:raise ValueError('Sealed evidence inventory gained or lost files')
        for f in entry['files']:
            rel=PurePosixPath(f['path'])
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe sealed evidence path')
            if sha(directory/rel)!=f['sha256']:raise ValueError('Sealed evidence changed')
        if row.get('status')!='missing_receipt' and entry['state']!='completed_receipt':raise ValueError('Completed classification differs from sealed inventory')
        if row.get('status')=='missing_receipt':
            item=closed[identity(row)]
            if item['trial_id']!=row['trial_id'] or item['state']!=entry['state'] or item['state'] not in ('interrupted_no_receipt','never_started'):
                raise ValueError('Missing classification differs from sealed inventory')
            if (directory/'receipt.json').exists():raise ValueError('Missing assignment gained a receipt after closure')
            if item['state']=='never_started' and directory.exists():raise ValueError('Never-started assignment directory exists')
            for k in ('passed','oracle_passed','declared_complete','total_cost_usd','known_cost_subtotal','wall_seconds','human_interventions','harness_invalid'):
                if row.get(k) is not None:raise ValueError('Missing assignment must retain unknown '+k)
            for k in ('truthful_success','false_completion'):
                if k in row and row[k] is not None:raise ValueError('Missing assignment outcome must remain unknown')
    return closure,closed

def patch_data(directory,row,raw):
    p=directory/'submitted.patch'
    if not p.exists() and row.get('artifact_invalid') is True:return None
    data=regular(p).read_bytes()
    if hashlib.sha256(data).hexdigest()!=row.get('patch_sha256'):raise ValueError('Patch digest mismatch')
    text=data.decode('utf-8');allowed=set(raw.get('production_paths',[]))
    for line in text.splitlines():
        if line.startswith('diff --git '):
            m=re.fullmatch(r'diff --git a/(\S+) b/(\S+)',line)
            if not m:raise ValueError('Unsupported production patch header')
            for name in m.groups():
                path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or any(part.startswith('.') for part in path.parts) or name not in allowed:
                    raise ValueError('Nonproduction path in patch')
        if line.startswith(('--- ', '+++ ')):
            name=line[4:]
            if name!='/dev/null' and (not name.startswith(('a/','b/')) or name[2:] not in allowed):
                raise ValueError('Nonproduction patch file header')
        if PRIVATE_PATH.search(line):raise ValueError('Host path in production patch; public export refused')
    return data

def error_class(value):
    if value is None:return None
    prefix=value.split(':',1)[0] if isinstance(value,str) else ''
    known={'PermissionError','OSError','RuntimeError','ValueError','TypeError','FileNotFoundError','TimeoutError','TimeoutExpired','JSONDecodeError','KeyError','AssertionError'}
    return prefix if prefix in known else 'unclassified_error'

def supplement_projection(value):
    out={k:value[k] for k in ('schema_version','analysis','registered_primary_unchanged','assignments','assignment_counts',
         'independently_graded_observed','opus_observed_inventory_counts','supplemental_verified_success_count','schedule_sha256','original_registration_sha256') if k in value}
    out['astra_error_classes']=dict(Counter(error_class(error) for error,count in value.get('astra_errors',{}).items() for _ in range(count)))
    out['rows']=[]
    for row in value.get('rows',[]):
        item={k:row.get(k) for k in ('trial_id','task_id','arm_id','repeat','assignment_state','recorded_provider_requests',
           'supplemental_harness_invalid','supplemental_verified_success','raw_receipt_sha256','graded_receipt_sha256')}
        if row.get('raw_receipt_sha256') is None:
            item['supplemental_verified_success']=None
        item['stage_qualifications']=[{**stage_projection(stage),'qualification':qualification(stage.get('qualification')),
             'error_class':error_class(stage.get('error'))} for stage in row.get('stage_qualifications',[])]
        out['rows'].append(item)
    return out

def export(study,schedule_path,destination,*,closure_path,supplement_path=None,graded_filename='graded-receipt.json'):
    if graded_filename not in GRADED_FILES:raise ValueError('Unsupported grading receipt filename')
    study=Path(study).resolve();destination=Path(destination)
    schedule=read(schedule_path);mapping=validate_schedule(schedule);rows=read(study/'results-normalized.json')
    actual=[identity(r) for r in rows]
    if len(set(actual))!=len(actual) or set(actual)!=set(mapping):raise ValueError('Aggregate must contain the exact full schedule')
    if any(r['trial_id']!=mapping[identity(r)] for r in rows):raise ValueError('Aggregate trial identity mismatch')
    closure,closed=validate_closure(study,schedule_path,closure_path,rows)
    if closure.get('grading_receipt_filename','graded-receipt.json')!=graded_filename:raise ValueError('Closure grading receipt filename mismatch')
    projected=[];artifacts=[];patches={}
    for row in sorted(rows,key=lambda r:(r['task_id'],r['repeat'],r['arm_id'])):
        identity_id=row['trial_id'];directory=study/'trials'/identity_id
        pub=project(row)
        if row.get('status')=='missing_receipt':
            for count in ('tool_input_error_count','policy_denial_count','scope_violation_count'):
                pub[count]=None
            pub['oracle_false_completion']=None
            pub['assignment_state']=closed[identity(row)]['state']
            pub['production_patch']=None
            artifacts.append(dict(trial_id=identity_id,raw_receipt_sha256=None,graded_receipt_sha256=None,production_patch_sha256=None))
        else:
            raw_path=directory/'receipt.json';graded_path=directory/graded_filename
            graded=read(graded_path);raw=read(raw_path)
            if graded['normalized']!=row:raise ValueError('Aggregate differs from graded normalized receipt')
            if graded.get('raw_receipt_sha256')!=sha(raw_path):raise ValueError('Grade/raw receipt binding mismatch')
            data=patch_data(directory,row,raw)
            artifact=dict(trial_id=identity_id,grading_receipt_filename=graded_filename,raw_receipt_sha256=sha(raw_path),graded_receipt_sha256=sha(graded_path),
                production_patch_sha256=hashlib.sha256(data).hexdigest() if data is not None else None)
            for name in ('grader.stdout','grader.stderr'):
                p=directory/name
                artifact[name.replace('.','_')+'_sha256']=sha(p) if p.exists() else None
            artifacts.append(artifact);pub['assignment_state']='completed_receipt'
            if data is not None:
                patch_name='patches/'+identity_id+'.patch';patches[patch_name]=data;pub['production_patch']=patch_name
            else:pub['production_patch']=None;pub['production_patch_unavailable']=True
            if raw.get('stages'):
                pub['stage_adapter_qualifications']=[dict(role=code(s.get('role')),qualification=qualification(s.get('adapter_qualification'))) for s in raw['stages']]
        projected.append(pub)
    sanitized_supplement=None
    if supplement_path:
        value=read(supplement_path)
        if value.get('schedule_sha256')!=sha(schedule_path):raise ValueError('Supplement schedule mismatch')
        supplied=value.get('rows',[])
        if len(supplied)!=len(rows) or {identity(r) for r in supplied}!=set(actual):raise ValueError('Supplement must cover exact full schedule')
        bound={a['trial_id']:a for a in artifacts}
        for row in supplied:
            if any(row.get(k)!=bound[row['trial_id']][k] for k in ('raw_receipt_sha256','graded_receipt_sha256')):
                raise ValueError('Supplement receipt binding differs')
        sanitized_supplement=supplement_projection(value)
        sanitized_supplement['source_supplement_sha256']=sha(supplement_path)
    # Validation completes before any public file is written.
    destination.mkdir(parents=True,exist_ok=True)
    if destination.is_symlink():raise ValueError('Public destination cannot be a symlink')
    for name,data in patches.items():
        p=destination/name;p.parent.mkdir(exist_ok=True)
        if p.parent.is_symlink() or p.is_symlink():raise ValueError('Public patch destination cannot be a symlink')
        p.write_bytes(data)
    public_closure=dict(schema_version=1,closed_at_utc=closure['closed_at_utc'],grading_receipt_filename=graded_filename,schedule_sha256=closure['schedule_sha256'],
        private_inventory_sha256=closure['inventory_sha256'],closure_manifest_sha256=sha(closure_path),
        classification=dict(Counter(r['assignment_state'] for r in projected)),assignments=len(projected),
        missing_assignments=[{k:r[k] for k in ('trial_id','task_id','arm_id','repeat','assignment_state')} for r in projected if r['status']=='missing_receipt'],
        completion_evidence_sha256=closure.get('completion_evidence_sha256'),
        note='Missing scheduled outcomes remain null. This closure does not turn interrupted or unstarted assignments into attempted failures.')
    for name,value in (('results.json',projected),('artifact-hashes.json',artifacts),('closure.json',public_closure)):
        p=destination/name
        if p.is_symlink():raise ValueError('Public destination file cannot be a symlink')
        p.write_text(json.dumps(value,indent=2)+'\n')
    if sanitized_supplement is not None:
        p=destination/'retrospective-inventory-supplement.json'
        if p.is_symlink():raise ValueError('Public supplement destination cannot be a symlink')
        p.write_text(json.dumps(sanitized_supplement,indent=2)+'\n')
    return public_closure

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('seal','export'))
    parser.add_argument('--study',type=Path,required=True);parser.add_argument('--schedule',type=Path,required=True)
    parser.add_argument('--closure',type=Path,required=True);parser.add_argument('--inventory',type=Path)
    parser.add_argument('--completion-evidence',type=Path)
    parser.add_argument('--graded-filename',choices=sorted(GRADED_FILES),default='graded-receipt.json')
    parser.add_argument('--reason');parser.add_argument('--output',type=Path);parser.add_argument('--supplement',type=Path)
    args=parser.parse_args()
    if args.action=='seal':
        if not args.inventory or not args.reason:parser.error('Explicit stopped-study reason and fresh inventory path required')
        value=seal(args.study,args.schedule,args.inventory,args.closure,args.reason,graded_filename=args.graded_filename,completion_evidence=args.completion_evidence)
    else:
        if not args.output:parser.error('Public output directory required')
        value=export(args.study,args.schedule,args.output,closure_path=args.closure,supplement_path=args.supplement,graded_filename=args.graded_filename)
    print(json.dumps({k:v for k,v in value.items() if k!='missing_assignments'},indent=2))

if __name__=='__main__':main()
