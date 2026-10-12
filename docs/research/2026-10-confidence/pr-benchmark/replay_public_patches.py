#!/usr/bin/env python3
"""Independent exact-byte production patch replay; no solvers or task oracles.

This audits published artifacts from the closed original and invalid-V1 blocks.
It neither repairs patch bytes nor revises historical receipt grading.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import shutil,stat,subprocess,tempfile,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
GIT='/Library/Developer/CommandLineTools/usr/bin/git' if Path('/Library/Developer/CommandLineTools/usr/bin/git').exists() else '/usr/bin/git'
COHORTS=(('original-comparison','study','manifest.json'),('hybrid-v1','hybrid-study-final','hybrid-manifest.json'))


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def byte_sha(data):return hashlib.sha256(data).hexdigest()
def mode(path):return stat.S_IMODE(path.stat().st_mode)
def git_mode(path):return '100755' if path.stat().st_mode & stat.S_IXUSR else '100644'

def tree_hash(root,curation=False):
    digest=hashlib.sha256()
    for p in sorted(Path(root).rglob('*')):
        rel=p.relative_to(root)
        if not curation and any(part in ('.git','.trial-tmp') for part in rel.parts):continue
        if p.is_symlink():raise ValueError('Symlink in bound material')
        if p.is_file():
            digest.update(rel.as_posix().encode()+b'\0'+str(mode(p)).encode()+b'\0')
            digest.update(hashlib.sha256(p.read_bytes()).digest() if curation else p.read_bytes())
            digest.update(b'' if curation else b'\0')
        elif not p.is_dir():raise ValueError('Nonregular bound material')
    return digest.hexdigest()

def env(scratch):
    # No inherited Git config, auth, shell startup, or filesystem-monitor hook.
    return {'PATH':'/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin',
        'LANG':'C.UTF-8','TMPDIR':str(scratch),'DEVELOPER_DIR':'/Library/Developer/CommandLineTools',
        'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0'}

def command(args,tree,scratch):
    return subprocess.run([GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',
        '-c','core.filemode=true',*args],cwd=tree,env=env(scratch),capture_output=True,timeout=30)

def initialize(tree,scratch):
    for args in (['init','-q'],['add','-A'],['-c','user.name=PatchReplayAudit','-c','user.email=audit@example.invalid','commit','-qm','Frozen public base']):
        p=command(args,tree,scratch)
        if p.returncode:raise RuntimeError('Git fixture initialization failed: '+p.stderr.decode(errors='replace'))

def projection(source,candidate,production):
    names=set(production)
    names.update(p.name for p in candidate.glob('*.py') if not (source/p.name).exists())
    return sorted(names)

def verify_projection(tree,candidate,names):
    checks=[]
    for name in names:
        wanted,actual=candidate/name,tree/name
        if wanted.is_symlink() or actual.is_symlink():raise ValueError('Unexpected production symlink')
        wanted_exists=wanted.is_file();actual_exists=actual.is_file()
        exists_match=wanted_exists==actual_exists
        content_match=exists_match and (not wanted_exists or actual.read_bytes()==wanted.read_bytes())
        gm_match=exists_match and (not wanted_exists or git_mode(wanted)==git_mode(actual))
        permissions_match=exists_match and (not wanted_exists or mode(wanted)==mode(actual))
        checks.append(dict(path=name,candidate_exists=wanted_exists,replay_exists=actual_exists,
            content_match=content_match,git_mode_match=gm_match,full_permission_bits_match=permissions_match,
            candidate_sha256=sha(wanted) if wanted_exists else None,replay_sha256=sha(actual) if actual_exists else None,
            candidate_git_mode=git_mode(wanted) if wanted_exists else None,replay_git_mode=git_mode(actual) if actual_exists else None,
            candidate_permission_bits=oct(mode(wanted)) if wanted_exists else None,
            replay_permission_bits=oct(mode(actual)) if actual_exists else None))
    return checks

def transitions(source,candidate,names):
    counts=Counter()
    for name in names:
        before,after=source/name,candidate/name
        if before.is_file() and not after.is_file():counts['deleted']+=1
        elif not before.is_file() and after.is_file():counts['added']+=1
        elif before.is_file() and after.is_file():
            if before.read_bytes()!=after.read_bytes():counts['modified_content']+=1
            elif git_mode(before)==git_mode(after):counts['unchanged']+=1
            if git_mode(before)!=git_mode(after):counts['changed_git_executable_mode']+=1
            if mode(before)!=mode(after):counts['changed_permission_bits']+=1
    return dict(counts)

def structural_control():
    """Independent add/delete/executable/binary replay and malformed-byte negative."""
    with tempfile.TemporaryDirectory(prefix='public-patch-control-') as name:
        root=Path(name).resolve();base=root/'base';base.mkdir();scratch=root/'scratch';scratch.mkdir()
        (base/'delete.py').write_text('old=1\n');(base/'mode.py').write_text('value=2\n');initialize(base,scratch)
        (base/'delete.py').unlink();(base/'mode.py').chmod(0o755)
        (base/'added.py').write_text('value=3\n');(base/'binary.bin').write_bytes(b'\x00CONTROL\xff\n')
        command(['add','-A'],base,scratch)
        delta=command(['diff','--cached','--binary','--no-ext-diff','--no-textconv','HEAD'],base,scratch).stdout
        candidate=root/'candidate';shutil.copytree(base,candidate,ignore=shutil.ignore_patterns('.git'))
        command(['reset','--hard','HEAD'],base,scratch)
        positive=subprocess.run([GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','apply','--index','--binary','--allow-empty','-'],
            cwd=base,env=env(scratch),input=delta,capture_output=True,timeout=30)
        checks=verify_projection(base,candidate,['added.py','binary.bin','delete.py','mode.py'])
        command(['reset','--hard','HEAD'],base,scratch)
        truncated=delta[:16]
        negative=subprocess.run([GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','apply','--index','--binary','--allow-empty','-'],
            cwd=base,env=env(scratch),input=truncated,capture_output=True,timeout=30)
        negative_checks=verify_projection(base,candidate,['added.py','binary.bin','delete.py','mode.py'])
        negative_matches=all(c['content_match'] and c['git_mode_match'] for c in negative_checks)
        return dict(kind='non-task_structural_control',model_calls=0,task_oracle_calls=0,
            positive_exact_patch_sha256=byte_sha(delta),positive_apply_exit=positive.returncode,
            positive_projection=checks,positive_passed=positive.returncode==0 and all(c['content_match'] and c['git_mode_match'] for c in checks),
            truncated_negative_sha256=byte_sha(truncated),truncated_negative_apply_exit=negative.returncode,
            truncated_negative_projection=negative_checks,truncated_negative_projection_matches=negative_matches,
            truncated_negative_rejected_by_replay_verification=negative.returncode!=0 or not negative_matches,
            note='With --allow-empty Git may accept truncated nonpatch input as no changes; successful process exit alone is not replay proof.')

def audit(public_root,private_root):
    began=time.monotonic();results=[];missing=[];sources={};cohort_pins={}
    for label,study_name,manifest_name in COHORTS:
        public=public_root/label;study=private_root/study_name
        manifest_path=private_root/'curation'/manifest_name;manifest=read(manifest_path)
        tasks={t['task_id']:t for t in manifest['tasks']}
        rows=read(public/'results.json');artifacts={r['trial_id']:r for r in read(public/'artifact-hashes.json')}
        if len(artifacts)!=len(rows):raise ValueError('Published schedule/artifact identities differ')
        cohort_pins[label]={n:sha(public/n) for n in ('results.json','artifact-hashes.json','closure.json')}
        cohort_pins[label]['private_manifest_sha256']=sha(manifest_path)
        for row in rows:
            identity=row['trial_id'];artifact=artifacts[identity]
            patch_ref=row.get('production_patch')
            if patch_ref is None:
                missing.append(dict(cohort=label,trial_id=identity,status=row['status'],assignment_state=row.get('assignment_state'),
                    oracle_passed=row.get('oracle_passed'),patch_unavailable=True))
                continue
            task=tasks[row['task_id']];source=Path(task['base_snapshot']);trial=study/'trials'/identity;candidate=trial/'result_snapshot'
            patch=public/patch_ref;data=patch.read_bytes();raw_path=trial/'receipt.json';graded_path=trial/'graded-receipt.json'
            raw=read(raw_path);graded=read(graded_path);normalized=graded['normalized']
            bindings={
                'public_patch_hash':byte_sha(data)==artifact['production_patch_sha256']==row['patch_sha256']==raw['patch_sha256'],
                'private_submitted_bytes':data==(trial/'submitted.patch').read_bytes(),
                'raw_receipt_hash':sha(raw_path)==artifact['raw_receipt_sha256']==graded['raw_receipt_sha256'],
                'graded_receipt_hash':sha(graded_path)==artifact['graded_receipt_sha256'],
                'candidate_bound_hash':tree_hash(candidate)==raw['result_sha256']==normalized['result_sha256']==row['result_sha256'],
                'base_bound_hash':tree_hash(source)==raw['source_sha256']==normalized['source_sha256']==row['source_sha256'],
                'identities':all(raw[k]==normalized[k]==row[k] for k in ('trial_id','task_id','arm_id','repeat'))}
            source_key=label+'/'+task['task_id']
            if source_key not in sources:
                observed=tree_hash(source,curation=True)
                sources[source_key]=dict(base_sha=task['base_sha'],expected_source_sha256=task['source_sha256'],observed_source_sha256=observed,
                    source_hash_matches=observed==task['source_sha256'])
            bindings['frozen_base_material']=sources[source_key]['source_hash_matches']
            names=projection(source,candidate,task['production_paths'])
            if set(raw['production_paths'])!=set(names):raise ValueError('Projection path enumeration differs from trusted submitted paths')
            with tempfile.TemporaryDirectory(prefix='public-patch-replay-') as temp:
                root=Path(temp).resolve();tree=root/'tree';scratch=root/'scratch';scratch.mkdir()
                shutil.copytree(source,tree);initialize(tree,scratch)
                process=subprocess.run([GIT,'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-c','core.filemode=true',
                    'apply','--index','--binary','--allow-empty','-'],cwd=tree,env=env(scratch),input=data,capture_output=True,timeout=30)
                checks=verify_projection(tree,candidate,names)
                # Git's index records regular-file blobs and executable modes;
                # verify no unexpected path changed outside the projection.
                changed=command(['diff','--cached','--name-only','-z','HEAD'],tree,scratch).stdout.decode().split('\0')
                changed=[x for x in changed if x]
                unexpected=sorted(set(changed)-set(names))
                replay_passed=all(bindings.values()) and process.returncode==0 and not unexpected and all(c['content_match'] and c['git_mode_match'] for c in checks)
                record=dict(cohort=label,trial_id=identity,task_id=row['task_id'],empty_patch=len(data)==0,
                    patch_sha256=byte_sha(data),patch_bytes=len(data),bindings=bindings,git_apply_exit=process.returncode,
                    git_apply_stdout_sha256=byte_sha(process.stdout),git_apply_stderr_sha256=byte_sha(process.stderr),
                    projection=checks,transitions=transitions(source,candidate,names),unexpected_changed_paths=unexpected,
                    exact_content_and_git_modes_replayed=replay_passed,
                    exact_permission_bits_replayed=replay_passed and all(c['full_permission_bits_match'] for c in checks))
                if process.returncode:record['private_apply_error']=process.stderr.decode(errors='replace')
                results.append(record)
                if len(results)%20==0:print(json.dumps({'replayed':len(results),'passing':sum(r['exact_content_and_git_modes_replayed'] for r in results)}),flush=True)
    control=structural_control()
    return dict(schema_version=1,created_at_utc=datetime.now(timezone.utc).isoformat(),audit_script_sha256=sha(Path(__file__)),
        git_version=subprocess.run([GIT,'--version'],capture_output=True,text=True,check=True).stdout.strip(),
        no_patch_repairs=True,whitespace_fix_used=False,model_calls=0,task_oracle_calls=0,scheduled_assignments=132,
        published_patch_denominator=len(results),missing_patch_assignments=len(missing),
        exact_content_and_git_mode_passes=sum(r['exact_content_and_git_modes_replayed'] for r in results),
        exact_permission_bit_passes=sum(r['exact_permission_bits_replayed'] for r in results),
        empty_patch_count=sum(r['empty_patch'] for r in results),cohort_public_file_pins=cohort_pins,
        frozen_base_sources=sources,structural_control=control,results=results,missing_assignments=missing,wall_seconds=time.monotonic()-began,
        limitations=['Reviewer authored the publication exporter; the frozen production patch builder is independently reviewed here.',
            'Production paths and new regular root Python helpers are replayed; tests, proof packets, protocol copies, synthetic Git history and unrelated actor files are outside this projection.',
            'Git records file existence, blob bytes and owner executable-bit modes; other permission bits are reported separately, not assumed reconstructible.',
            'Successful replay is artifact reproducibility, not task acceptance, whole-application correctness or proof-packet quality.',
            'Missing interrupted/unstarted assignments have no patch and remain outside the101 published-patch denominator; full132 scheduled assignments remain enumerated.'])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--public-root',type=Path,default=HERE/'results')
    parser.add_argument('--private-root',type=Path,default=ROOT/'.confidence/benchmark');parser.add_argument('--private-output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.public_root.resolve(),args.private_root.resolve())
    args.private_output.parent.mkdir(parents=True,exist_ok=True);args.private_output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','missing_assignments','frozen_base_sources','structural_control','cohort_public_file_pins','limitations')},indent=2))

if __name__=='__main__':main()
