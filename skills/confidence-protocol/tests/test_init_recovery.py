"""Public initialization and preserving recovery under cooperative writer locks."""
import concurrent.futures
import json
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT=Path(__file__).parents[1]/'scripts/confidence.py'


class InitRecoveryTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.directory=self.root/'evidence'
        self.env=dict(os.environ,CONFIDENCE_DISABLE_DIAGNOSTICS='1',PYTHONDONTWRITEBYTECODE='1')

    def command(self,*args,script=SCRIPT):
        return [sys.executable,str(script),'init','--directory',str(self.directory),*args]

    def call(self,*args):
        return subprocess.run(self.command(*args),env=self.env,capture_output=True,text=True,timeout=8)

    def files(self):
        return {p.name:p.read_bytes() for p in self.directory.glob('*.json')}

    def paused(self,*args,target='report.json'):
        marker=self.root/'paused';release=self.root/'release';adapter=self.root/'adapter.py'
        adapter.write_text(f'''import importlib.util,time
from pathlib import Path
s=importlib.util.spec_from_file_location('init_target',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
original=c.write_text_atomic
def paused(path,*args,**kwargs):
 if Path(path).name=={target!r}:
  Path({str(marker)!r}).touch()
  until=time.monotonic()+6
  while not Path({str(release)!r}).exists():
   if time.monotonic()>until:raise TimeoutError('release missing')
   time.sleep(.005)
 return original(path,*args,**kwargs)
c.write_text_atomic=paused
raise SystemExit(c.main())
''')
        p=subprocess.Popen(self.command(*args,script=adapter),env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def cleanup():
            if p.poll() is None:p.kill()
            p.communicate()
        self.addCleanup(cleanup)
        deadline=time.monotonic()+6
        while not marker.exists():
            if p.poll() is not None:self.fail('writer stopped before pause: '+str(p.communicate()))
            if time.monotonic()>deadline:self.fail('writer did not reach pause')
            time.sleep(.005)
        return p,release

    def test_concurrent_initializers_have_one_consistent_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda title:self.call('--title',title),['A','B']))
        self.assertEqual(sorted(r.returncode for r in results),[0,2])
        c=json.loads((self.directory/'contract.json').read_text());r=json.loads((self.directory/'report.json').read_text())
        self.assertEqual(c['task']['title'],r['task_title'])
        self.assertFalse(list(self.directory.glob('*.tmp-*')))

    def test_paused_writer_blocks_init_and_record_then_releases(self):
        first,release=self.paused('--title','A',target='contract.json')
        other=self.call('--title','B');self.assertEqual(other.returncode,2);self.assertIn('writer',other.stderr)
        record=subprocess.run([sys.executable,str(SCRIPT),'record','--directory',str(self.directory),'--obligation','P1','--status','partial','--details','pending'],env=self.env,capture_output=True,text=True,timeout=8)
        self.assertEqual(json.loads(record.stdout)['code'],'LOCK_BUSY')
        release.touch();first.communicate(timeout=8);self.assertEqual(first.returncode,0)
        self.assertEqual(self.call('--resume').returncode,0)

    def test_interrupted_contract_only_resume_preserves_authored_bytes_and_ids(self):
        process,_=self.paused('--title','Original');process.send_signal(signal.SIGTERM);process.communicate(timeout=8)
        self.assertEqual(process.returncode,-signal.SIGTERM)
        path=self.directory/'contract.json';contract=json.loads(path.read_text())
        contract['intent']['goal']='Authored goal';contract['custom']={'retain':'exactly'}
        contract['proof_obligations'].append({'id':'P2','claim':'','verification':''})
        path.write_text(json.dumps(contract));before=path.read_bytes()
        self.assertEqual(self.call('--title','Other').returncode,2)
        result=self.call('--resume');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(path.read_bytes(),before)
        report=json.loads((self.directory/'report.json').read_text())
        self.assertEqual(report['task_title'],'Original');self.assertEqual([i['obligation_id'] for i in report['evidence']],['P1','P2'])
        pair=self.files();self.assertEqual(self.call('--resume').returncode,0);self.assertEqual(self.files(),pair)

    def test_resume_conflicting_requested_identity_preserves_partial_work(self):
        self.assertEqual(self.call('--title','Original','--mode','critical','--task-type','security').returncode,0)
        (self.directory/'report.json').unlink();before=self.files()
        for args in [('--title','Other'),('--mode','standard'),('--task-type','bug')]:
            result=self.call('--resume',*args);self.assertEqual(result.returncode,2);self.assertEqual(self.files(),before)

    def test_resume_refuses_report_only_and_mismatched_pair(self):
        self.assertEqual(self.call('--title','Original').returncode,0)
        contract=(self.directory/'contract.json').read_bytes();(self.directory/'contract.json').unlink();before=self.files()
        self.assertEqual(self.call('--resume').returncode,2);self.assertEqual(self.files(),before)
        (self.directory/'contract.json').write_bytes(contract)
        report=json.loads((self.directory/'report.json').read_text());report['task_title']='Different';(self.directory/'report.json').write_text(json.dumps(report));before=self.files()
        self.assertEqual(self.call('--resume').returncode,2);self.assertEqual(self.files(),before)

    def test_force_interruption_never_pairs_new_contract_with_old_report(self):
        self.assertEqual(self.call('--title','Old').returncode,0)
        process,_=self.paused('--title','New','--force')
        self.assertFalse((self.directory/'report.json').exists())
        self.assertEqual(json.loads((self.directory/'contract.json').read_text())['task']['title'],'New')
        process.send_signal(signal.SIGTERM);process.communicate(timeout=8)
        self.assertEqual(self.call('--resume').returncode,0)
        self.assertEqual(json.loads((self.directory/'report.json').read_text())['task_title'],'New')

    def test_ordinary_existing_pair_is_unchanged(self):
        self.assertEqual(self.call('--title','Original').returncode,0);before=self.files()
        self.assertEqual(self.call('--title','Other').returncode,2);self.assertEqual(self.files(),before)
        self.assertEqual(self.call('--force','--title','Other').returncode,0)

    def test_special_or_malformed_contract_is_refused_without_replacement(self):
        self.directory.mkdir();path=self.directory/'contract.json';path.write_text('{invalid')
        self.assertEqual(self.call('--resume').returncode,2);self.assertEqual(path.read_text(),'{invalid')
        path.unlink();os.mkfifo(path)
        self.assertEqual(self.call('--resume').returncode,2)
        self.assertEqual(self.call('--force','--title','Other').returncode,2)
        path.unlink();outside=self.root/'outside';outside.write_text('preserve');path.symlink_to(outside)
        self.assertEqual(self.call('--resume').returncode,2);self.assertEqual(outside.read_text(),'preserve')


    def test_contract_atomic_temp_namespace_preserves_source_boundaries(self):
        project=self.root/'project';project.mkdir()
        subprocess.run(['git','init','-q',str(project)],check=True)
        self.directory=project/'.confidence';self.directory.mkdir()
        spec=importlib.util.spec_from_file_location('init_core',SCRIPT)
        core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
        fingerprint=lambda:core.git_workspace_fingerprint(project,self.directory)
        before=fingerprint();self.assertIsNotNone(before)
        path=self.directory/'.contract.json.tmp-abcd012_';path.write_text('temporary')
        self.assertEqual(fingerprint(),before)
        subprocess.run(['git','-C',str(project),'add','-f',str(path)],check=True)
        tracked=fingerprint();path.write_text('changed tracked source')
        self.assertNotEqual(fingerprint(),tracked)
        subprocess.run(['git','-C',str(project),'rm','--cached','-f',str(path)],check=True)
        path.unlink();path.symlink_to('target-one');symlink=fingerprint()
        self.assertNotEqual(symlink,before)
        path.unlink();path.symlink_to('target-two');self.assertNotEqual(fingerprint(),symlink)
        path.unlink();path=self.directory/'.contract.json.tmp-short';path.write_text('source')
        self.assertNotEqual(fingerprint(),before)

    def test_init_atomic_publication_overlaps_capture_without_staleness(self):
        project=self.root/'project';project.mkdir()
        subprocess.run(['git','init','-q',str(project)],check=True)
        (project/'source').write_text('stable')
        self.directory=project/'.confidence'
        marker=self.root/'ready';release=self.root/'release';adapter=self.root/'publish.py'
        adapter.write_text(f'''import importlib.util,time
from pathlib import Path
s=importlib.util.spec_from_file_location('c',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
original=c.os.link
def paused(source,destination,*args,**kwargs):
 if Path(destination).name=='contract.json':
  Path({str(marker)!r}).write_text(str(source))
  until=time.monotonic()+6
  while not Path({str(release)!r}).exists():
   if time.monotonic()>until:raise TimeoutError('release missing')
   time.sleep(.005)
 return original(source,destination,*args,**kwargs)
c.os.link=paused
raise SystemExit(c.main())
''')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            initializing=pool.submit(subprocess.run,self.command('--title','Concurrent',script=adapter),env=self.env,capture_output=True,text=True,timeout=10)
            try:
                deadline=time.monotonic()+6
                while not marker.exists():
                    if time.monotonic()>deadline:self.fail('publication pause missing')
                    time.sleep(.005)
                self.assertTrue(Path(marker.read_text()).is_file())
                result=subprocess.run([sys.executable,str(SCRIPT),'run','--id','observer','--cwd',str(project),'--directory',str(self.directory),'--',sys.executable,'-c',"from pathlib import Path; assert Path('source').read_text()=='stable'"],env=self.env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
            finally:release.touch()
            result=initializing.result();self.assertEqual(result.returncode,0,result.stderr)
        spec=importlib.util.spec_from_file_location('init_overlap',SCRIPT)
        core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
        record,errors=core.validate_run_record(self.directory,'observer')
        self.assertEqual(errors,[])
        self.assertEqual(core.validate_supporting_workspace(record,self.directory),[])
        self.assertFalse(list(self.directory.glob('.*.tmp-*')))

    def test_missing_locking_refuses_without_creating_documents(self):
        adapter=self.root/'unsupported.py';adapter.write_text(f"import importlib.util,sys\ns=importlib.util.spec_from_file_location('c',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)\nsys.modules['fcntl']=None\nraise SystemExit(c.main())\n")
        result=subprocess.run(self.command('--title','Task',script=adapter),env=self.env,capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,2);self.assertIn('Unix',result.stderr);self.assertFalse(self.directory.exists())


if __name__=='__main__':unittest.main()
