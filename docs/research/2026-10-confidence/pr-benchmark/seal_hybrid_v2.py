#!/usr/bin/env python3
"""Final V2 launch seal; bare adapter prepare is provisional, not a launch gate.

Requires qualified staged hosted evidence, exact independent grader/baseline
controls, a resolved adversarial audit and zero historical-task allocation.
Only after this seal is publicly committed may the registered V2 cohort run.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v2_final_seal',HERE/'hybrid_v2.py')
v2=importlib.util.module_from_spec(spec);spec.loader.exec_module(v2)

def require_material_hashes(value, key):
    hashes=value[key]
    if not hashes:
        raise ValueError('Missing qualification source pins')
    for name, expected in hashes.items():
        path=Path(name)
        if not path.is_absolute():path=HERE/path
        if v2.frozen.file_sha(path)!=expected:
            raise ValueError('Qualification source changed: '+path.name)

def seal(args):
    v2.normalize_args(args)
    args.host_qualification=args.host_qualification.resolve()
    args.grader_controls=args.grader_controls.resolve()
    args.adversarial_review=args.adversarial_review.resolve()
    host=v2.frozen.read(args.host_qualification)
    toy_registration=v2.frozen.read(args.host_qualification.parent/'toy-registration.json')
    if host.get('passed') is not True or host.get('efficacy_trials')!=0 or host.get('registered_source_files_changed')!=[]:
        raise ValueError('Hosted pipeline qualification is incomplete')
    if len(host.get('checks',[]))!=2 or any(c.get('passed') is not True for c in host['checks']):
        raise ValueError('Both hosted cross pairings must qualify')
    # Protocol descriptive registration fields can be finalized later; role
    # prompts/windows/package/material remain bound by identical queue templates.
    source_pins={name:sha for name,sha in toy_registration['files'].items() if Path(name).resolve()!=args.protocol}
    require_material_hashes({'files':source_pins},'files')
    controls=v2.frozen.read(args.grader_controls)
    if controls.get('all_controls_passed') is not True or controls.get('code_stable_during_controls') is not True or controls.get('model_calls')!=0:
        raise ValueError('Independent grading/baseline controls are incomplete')
    require_material_hashes(controls,'code_sha256_at_end')
    review=v2.frozen.read(args.adversarial_review)
    if review.get('passed') is not True or review.get('unresolved_findings')!=[]:
        raise ValueError('Adversarial review is unresolved')
    require_material_hashes(review,'reviewed_files')
    protocol=v2.frozen.read(args.protocol)
    original_design=v2.frozen.read(HERE/'hybrid-protocol.json')
    for field in ('package','models','arms','common_workflow_instruction','review_roles',
                  'resources','tasks','schedule','terminal_schema','outcomes','analysis'):
        if protocol[field]!=original_design[field]:
            raise ValueError('V2 task/model/prompt/resource contract changed: '+field)
    # Fresh preparation owns offline probes and request generation. It refuses
    # an existing directory and does not make historical-task model requests.
    v2.frozen.prepare(args)
    workspace=args.study/'probe-workspace'
    probes=[v2.local_mcp_probe(model,workspace,args.study/('pipeline-'+model+'-'+str(readonly)),readonly=readonly)
            for model in ('astra','opus') for readonly in (False,True)]
    if any(p.get('passed') is not True for p in probes):
        raise ValueError('Fresh local pipeline qualification failed')
    pipeline=args.study/'pipeline-qualification.json';v2.frozen.write(pipeline,probes)
    registration=v2.frozen.read(args.study/'registration.json')
    extra=[Path(__file__).resolve(),HERE/'hybrid_v2.py',HERE/'hybrid_process_v2.py',
           HERE/'hybrid_runtime_v2.py',HERE/'hybrid_v2_grader.py',HERE/'v2_controls.py',
           HERE/'v2_grading_controls.py',HERE/'HYBRID-V2-PREREGISTRATION.md',
           args.host_qualification,args.host_qualification.parent/'toy-registration.json',
           args.grader_controls,args.adversarial_review,pipeline]
    registration['files'].update({str(p.resolve()):v2.frozen.file_sha(p) for p in extra})
    registration.update(adapter_version=2,final_launch_sealed=True,
        zero_v2_historical_task_outcomes=True,final_sealed_at_utc=v2.frozen.now(),
        prior_v1_status='Invalid; preserved separately; not resumed or pooled')
    if (args.study/'trials').exists() or len(v2.frozen.read(args.study/'requests.json'))!=48:
        raise ValueError('Zero-outcome full48 fresh study required')
    if v2.frozen.read(args.study/'requests.json')!=v2.frozen.read(HERE/'hybrid-requests.json'):
        raise ValueError('V2 complete queue differs from the retained48 assignments')
    # Qualify the exact generated task/window/provider request templates against
    # the ones exercised by the hosted toy, apart from the explicit toy task.
    toy_protocol=v2.frozen.read(args.protocol)
    for request in toy_registration['requests']:
        arm=next(a for a in toy_protocol['arms'] if a['id']==request['arm_id'])
        if request['main_model']!=arm['main_model'] or request['peer_model']!=arm['peer_model']:
            raise ValueError('Toy provider assignment differs')
    v2.frozen.write(args.study/'registration.json',registration)
    public=dict(schema_version=2,experiment_id=toy_protocol['benchmark_id'],
        final_sealed_at_utc=registration['final_sealed_at_utc'],adapter_version=2,
        final_launch_sealed=True,zero_v2_historical_task_outcomes=True,trials=48,
        protocol_canonical_sha256=registration['protocol_sha256'],
        manifest_canonical_sha256=registration['manifest_sha256'],
        governing_file_hashes={str(Path(name).relative_to(HERE)) if Path(name).is_relative_to(HERE) else
             ('private-evidence/'+str(Path(name).parent.name)+'/'+Path(name).name):sha for name,sha in registration['files'].items()},
        hosted_qualification_sha256=v2.frozen.file_sha(args.host_qualification),
        independent_grader_controls_sha256=v2.frozen.file_sha(args.grader_controls),
        adversarial_review_sha256=v2.frozen.file_sha(args.adversarial_review),
        private_registration_sha256=v2.frozen.file_sha(args.study/'registration.json'),
        interpretation='Exploratory fixed-main peer-provider contrast; no pooling with original84 or invalidV148; unknowns retained; totalcost often unknown')
    v2.frozen.write(HERE/'HYBRID-V2-REGISTRATION.json',public)
    print(json.dumps(public,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','manifest','study','model-catalog','host-qualification','grader-controls','adversarial-review'):
        p.add_argument('--'+name,type=Path,required=True)
    seal(p.parse_args())
