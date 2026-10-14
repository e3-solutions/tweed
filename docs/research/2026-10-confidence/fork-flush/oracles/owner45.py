import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
SCRIPT=Path.cwd()/'skills/confidence-protocol/scripts/confidence.py'
class Owner(unittest.TestCase):
 def capture(self,code,json_mode=True,git=True):
  temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);root=Path(temporary.name)
  (root/'data.txt').write_text('original')
  if git:
   subprocess.run(['git','init','-q',str(root)],check=True,timeout=2)
   subprocess.run(['git','-C',str(root),'add','data.txt'],check=True,timeout=2)
   subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True,timeout=2)
  evidence=root/'.confidence'
  result=subprocess.run([sys.executable,'-B',str(SCRIPT),'run','--id','owner','--directory',str(evidence),'--cwd',str(root),*(['--json'] if json_mode else []),'--',sys.executable,'-c',code],capture_output=True,timeout=3)
  return result,evidence
 def test_positive_compact_capture_and_default_output(self):
  expected=b'Z'*16384+b'\xff\x00END'
  r,d=self.capture("import os;os.write(1,b'Z'*16384+b'\\xff\\x00END')")
  self.assertEqual(r.returncode,0,r.stderr);receipt=json.loads(r.stdout);self.assertLess(len(r.stdout),1024)
  self.assertEqual(receipt['id'],'owner');self.assertEqual(receipt['exit_code'],0);self.assertEqual(receipt['workspace_binding'],'unchanged')
  self.assertFalse(Path(receipt['record']).is_absolute());self.assertFalse(Path(receipt['log']).is_absolute())
  self.assertNotIn('..',Path(receipt['record']).parts);self.assertNotIn('..',Path(receipt['log']).parts)
  record=json.loads((d/receipt['record']).read_text());raw=(d/receipt['log']).read_bytes()
  self.assertEqual(raw,expected);self.assertEqual(record['log_sha256'],hashlib.sha256(expected).hexdigest())
  r,d=self.capture("import os;os.write(1,b'plain\\n');os.write(2,b'error\\n')",False)
  self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'plain\nerror\n')
  r,d=self.capture("print('unbound evidence')",git=False)
  self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['workspace_binding'],'unknown')
 def test_negative_failed_child_stays_failed(self):
  r,d=self.capture("import sys;print('failure evidence');sys.exit(7)")
  self.assertEqual(r.returncode,7);receipt=json.loads(r.stdout);self.assertEqual(receipt['exit_code'],7)
  self.assertEqual(json.loads((d/receipt['record']).read_text())['exit_code'],7)
 def test_negative_mutated_source_is_not_unchanged(self):
  r,d=self.capture("from pathlib import Path;Path('data.txt').write_text('changed')")
  self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['workspace_binding'],'changed')
