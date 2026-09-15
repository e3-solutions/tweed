"""Real child cleanup when signals arrive during resource acquisition."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT=Path(__file__).parents[1]/'scripts/confidence.py'

@unittest.skipUnless(os.name=='posix','POSIX signals and process groups')
class LaunchCancellationTest(unittest.TestCase):
    def check_boundary(self,boundary,signum,repeated=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'pid';adapter=root/'adapter.py';child=root/'child.py';evidence=root/'evidence'
            child.write_text(f"import os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(20)\n")
            adapter.write_text(f'''import importlib.util,os,signal,sys,time
from pathlib import Path
s=importlib.util.spec_from_file_location('c',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
fired=False
original=c.subprocess.Popen
original_open=Path.open
def interrupt(wait=False):
 global fired
 if fired:return
 if wait:
  until=time.monotonic()+3
  while not Path({str(marker)!r}).exists():
   if time.monotonic()>until:raise RuntimeError('child marker missing')
   time.sleep(.005)
 fired=True
 os.kill(os.getpid(),{int(signum)})
 if {repeated!r}:os.kill(os.getpid(),signal.SIGINT);os.kill(os.getpid(),signal.SIGTERM)
def launch(*args,**kwargs):
 if not kwargs.get('start_new_session'):return original(*args,**kwargs)
 if {boundary!r}=='launch_error':interrupt();raise OSError('seeded launch failure')
 p=original(*args,**kwargs)
 if {boundary!r}=='return':interrupt(True)
 return p
def opening(path,*args,**kwargs):
 if Path(path).name=='probe.log' and args and args[0]=='xb' and {boundary!r}=='log_error':interrupt();raise OSError('seeded log open failure')
 handle=original_open(path,*args,**kwargs)
 if Path(path).name=='probe.log' and args and args[0]=='xb' and {boundary!r}=='log_return':interrupt()
 return handle
c.subprocess.Popen=launch
Path.open=opening
def trace(frame,event,arg):
 if event=='line' and frame.f_code.co_name=='command_run' and {boundary!r}=='assigned' and frame.f_locals.get('process') is not None and 'deadline' not in frame.f_locals:interrupt(True)
 return trace
sys.settrace(trace)
before={{sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}}
status=c.main()
assert all(signal.getsignal(sig)==handler for sig,handler in before.items()),'signal handlers were not restored'
raise SystemExit(status)
''')
            runner=None;pid=None
            try:
                runner=subprocess.Popen([sys.executable,'-B',str(adapter),'run','--json','--directory',str(evidence),'--cwd',str(root),'--id','probe','--',sys.executable,'-B',str(child)],env=dict(os.environ,CONFIDENCE_DISABLE_DIAGNOSTICS='1'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                out,err=runner.communicate(timeout=8)
                if marker.exists():pid=int(marker.read_text())
                self.assertEqual(runner.returncode,128+signum,err)
                self.assertEqual(out,'')
                self.assertFalse((evidence/'runs/probe.json').exists())
                self.assertFalse((evidence/'runs/probe.log').exists())
                if boundary in ('log_return','log_error','launch_error'):self.assertIsNone(pid)
                else:
                    self.assertIsNotNone(pid)
                    with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                if runner and runner.poll() is None:runner.kill();runner.communicate(timeout=2)
                if pid is None and marker.exists():pid=int(marker.read_text())
                if pid:
                    try:os.killpg(pid,signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_launch_return_signals_cleanup_real_child(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('return',sig)

    def test_assigned_handle_signals_cleanup_real_child(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('assigned',sig)

    def test_log_acquisition_signal_prevents_launch(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('log_return',sig)

    def test_pending_signal_takes_precedence_over_launch_error(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('launch_error',sig)

    def test_repeated_pending_signals_preserve_first_status(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('return',sig,repeated=True)

    def test_pending_signal_takes_precedence_over_log_open_error(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=sig):self.check_boundary('log_error',sig)
