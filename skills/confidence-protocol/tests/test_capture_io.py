"""Public CLI persistence errors retain evidence and allow fresh capture."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).parents[1]/'scripts/confidence.py'

class CaptureIOTest(unittest.TestCase):
    def test_storage_failures_are_actionable_and_recoverable(self):
        for mode in ('fsync','append','publish','publish_cleanup'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();ev=root/'evidence';adapter=root/'adapter.py'
                adapter.write_text(f'''import os, pathlib, runpy, sys, errno
script={str(SCRIPT)!r}
original_sync=os.fsync;original_open=pathlib.Path.open;original_link=os.link;original_unlink=pathlib.Path.unlink
def sync(fd):
 if {mode!r}=='fsync' and os.fstat(fd).st_ino==os.stat({str(ev/'runs/fault.log')!r}).st_ino:raise OSError(errno.ENOSPC,'injected full storage')
 return original_sync(fd)
def opening(path,*args,**kwargs):
 if {mode!r}=='append' and str(path)=={str(ev/'runs/fault.log')!r} and args and args[0]=='ab':raise OSError(errno.EIO,'injected append failure')
 return original_open(path,*args,**kwargs)
def link(src,dst,*args,**kwargs):
 if {mode!r}=='publish' and str(dst)=={str(ev/'runs/fault.json')!r}:raise OSError(errno.ENOSPC,'injected publication failure')
 return original_link(src,dst,*args,**kwargs)
def unlink(path,*args,**kwargs):
 if {mode!r}=='publish_cleanup' and path.name.startswith('.fault.json.tmp-'):raise OSError(errno.EIO,'injected temporary cleanup failure')
 return original_unlink(path,*args,**kwargs)
os.fsync=sync;pathlib.Path.open=opening;os.link=link;pathlib.Path.unlink=unlink
sys.argv[0]=script;runpy.run_path(script,run_name='__main__')
''')
                def run(script,ident,child):
                    return subprocess.run([sys.executable,str(script),'run','--json','--directory',str(ev),'--cwd',str(root),'--id',ident,'--timeout-seconds','.15','--',sys.executable,'-c',child],capture_output=True,text=True,timeout=8)
                self.assertEqual(run(SCRIPT,'prior','print("prior")').returncode,0)
                prior={p.name:p.read_bytes() for p in (ev/'runs').iterdir()}
                result=run(adapter,'fault','import time;print("output",flush=True);'+('time.sleep(30)' if mode=='append' else 'pass'))
                self.assertEqual(result.returncode,125,result.stderr)
                self.assertEqual(result.stdout,'')
                self.assertIn('RUN_CAPTURE_FAILED',result.stderr)
                self.assertIn('After storage recovery',result.stderr)
                self.assertIn('fresh run ID',result.stderr)
                self.assertNotIn('internal error',result.stderr)
                self.assertEqual((ev/'runs/fault.json').exists(), mode=='publish_cleanup')
                if mode.startswith('publish'):
                    self.assertIn('publication could not be confirmed',result.stderr)
                    self.assertNotIn('no evidence record written',result.stderr)
                else:self.assertIn('no evidence record written',result.stderr)
                for name,content in prior.items():self.assertEqual((ev/'runs'/name).read_bytes(),content)
                self.assertEqual(run(SCRIPT,'recovered','print("recovered")').returncode,0)

    @unittest.skipUnless(os.name=='posix','POSIX signal control')
    def test_signal_during_finalization_closes_log_and_preserves_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ev=root/'evidence';adapter=root/'interrupt_adapter.py'
            adapter.write_text(f'''import importlib.util,os,signal,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('core',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
opened=[];original=Path.open;sync=os.fsync
def opening(path,*args,**kwargs):
 handle=original(path,*args,**kwargs)
 if path.name=='signal.log' and args and args[0]=='xb':opened.append(handle)
 return handle
def syncing(fd):
 if opened and fd==opened[0].fileno():os.kill(os.getpid(),signal.SIGTERM)
 return sync(fd)
Path.open=opening;os.fsync=syncing
status=c.main()
assert opened and all(h.closed for h in opened),'log descriptor was not closed'
raise SystemExit(status)
''')
            p=subprocess.run([sys.executable,str(adapter),'run','--json','--directory',str(ev),'--cwd',str(root),'--id','signal','--',sys.executable,'-c','print("done")'],capture_output=True,text=True,timeout=8)
            self.assertEqual(p.returncode,143,p.stderr)
            self.assertEqual(p.stdout,'')
            self.assertFalse((ev/'runs/signal.json').exists())
