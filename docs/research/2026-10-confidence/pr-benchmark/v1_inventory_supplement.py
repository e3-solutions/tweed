#!/usr/bin/env python3
"""Read-only retrospective tool qualification; never edits registered grading."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v1_supplement_v2',HERE/'hybrid_v2.py')
v2=importlib.util.module_from_spec(spec);spec.loader.exec_module(v2)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())


def supplement(study):
    study=Path(study).resolve()
    registration=read(study/'registration.json')
    for name,expected in registration['files'].items():
        if sha(Path(name))!=expected:raise ValueError('Registered material changed: '+name)
    queue=read(study/'requests.json')
    rows=[]
    for request in queue:
        trial=study/'trials'/request['trial_id']
        raw_path=trial/'receipt.json'
        graded_path=trial/'graded-receipt.json'
        provider_requests=list(trial.glob('*/request.json')) if trial.exists() else []
        state='completed_receipt' if raw_path.exists() else ('interrupted_before_receipt' if trial.exists() else 'never_started')
        row={k:request[k] for k in ('trial_id','task_id','arm_id','repeat','main_model','peer_model')}
        row.update(assignment_state=state,recorded_provider_requests=len(provider_requests),
                   registered_primary=None,stage_qualifications=[],supplemental_harness_invalid=None,
                   supplemental_verified_success=False,raw_receipt_sha256=None,graded_receipt_sha256=None)
        if raw_path.exists():
            raw=read(raw_path);row['raw_receipt_sha256']=sha(raw_path)
            if not graded_path.exists():raise ValueError('Observed receipt is not independently graded: '+request['trial_id'])
            graded=read(graded_path)
            if graded['raw_receipt_sha256']!=sha(raw_path):raise ValueError('Graded receipt no longer binds raw receipt')
            if graded['adapter_sha256']!=sha(HERE/'hybrid_grader.py'):raise ValueError('Frozen grader identity differs')
            row['graded_receipt_sha256']=sha(graded_path)
            row['registered_primary']=graded['normalized']
            stages=raw.get('stages',[])
        else:
            stages=[]
            # Interrupted assignments have no final artifact or primary grade.
            # Preserve available stage observations without inventing completion.
            for role in ('test_designer','main_implementation','adversarial_reviewer','main_repair'):
                p=trial/role/'receipt.json'
                if p.exists():stages.append(read(p))
        for stage in stages:
            inv=v2.effective_inventory(stage)
            if stage.get('assigned_model')=='astra':
                inv['basis']='historical_offline_declared_codex_inventory_only'
                inv['local_pipeline_observed']=False
            row['stage_qualifications'].append(dict(role=stage.get('role'),assigned_model=stage.get('assigned_model'),
                qualification=inv,model_requested=stage.get('model_requested'),
                observed_models=stage.get('observed_assistant_models',stage.get('observed_models')),
                total_cost_usd=stage.get('total_cost_usd'),usage=stage.get('usage'),error=stage.get('error'),
                status=stage.get('status'),timed_out=stage.get('timed_out')))
        qualified=[s['qualification'].get('passed') for s in row['stage_qualifications']]
        primary=row['registered_primary']
        row['supplemental_harness_invalid']=True if False in qualified else (None if len(qualified)!=4 or None in qualified else bool(primary and primary.get('harness_invalid')))
        row['supplemental_verified_success']=bool(primary and primary.get('truthful_success') is True and row['supplemental_harness_invalid'] is False)
        rows.append(row)
    status=Counter(r['assignment_state'] for r in rows)
    op=Counter(str(s['qualification']['passed']) for r in rows for s in r['stage_qualifications'] if s['assigned_model']=='opus')
    astra_errors=Counter(s['error'] for r in rows for s in r['stage_qualifications'] if s['assigned_model']=='astra' and s['error'])
    return dict(schema_version=1,analysis='retrospective_supplement_only_no_accuracy_ranking',
        registered_primary_unchanged=True,schedule_sha256=sha(study/'schedule.json'),
        original_registration_sha256=sha(study/'registration.json'),assignments=len(rows),
        assignment_counts=dict(status),independently_graded_observed=sum(r['registered_primary'] is not None for r in rows),
        opus_observed_inventory_counts=dict(op),astra_errors=dict(astra_errors),
        supplemental_verified_success_count=sum(r['supplemental_verified_success'] for r in rows),
        conclusions={'provider_accuracy_comparison_valid':False,
          'reason':'Asymmetric missing Claude MCP tools and interrupted assignments prevent model accuracy ranking',
          'billing_comparable':False,'unknown_costs_imputed_zero':False},rows=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();value=supplement(a.study)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
