"""V2 reaping regression plus the existing original-group boundary controls."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

v2=load('cleanup_v2_test','hybrid_process_v2.py')
previous=load('cleanup_v1_boundary_tests','test_hybrid_process.py')

class V2OriginalGroupControls(previous.HybridProcessControls):
    def setUp(self):
        replacement=patch.object(previous.processes,'cleanup_group',v2.cleanup_group)
        replacement.start();self.addCleanup(replacement.stop)
        super().setUp()

class ReapingRegression(unittest.TestCase):
    def test_poll_occurs_before_group_escalation(self):
        events=[]
        class Child:
            pid=12345
            def poll(self):events.append('reap');return -15
        def kill(pid,sig):events.append(sig)
        with patch.object(v2.os,'killpg',side_effect=kill),patch.object(v2.time,'sleep'):
            v2.cleanup_group(Child())
        self.assertEqual(events[:3],[signal.SIGTERM,'reap',signal.SIGKILL])

    @unittest.skipUnless(sys.platform=='darwin','macOS unreaped-group EPERM')
    def test_actual_unreaped_child_reproduces_old_failure(self):
        process=subprocess.Popen(['sleep','30'],start_new_session=True)
        self.addCleanup(lambda:process.poll() is None and process.kill())
        os.killpg(process.pid,signal.SIGTERM);time.sleep(.05)
        with self.assertRaises(PermissionError):os.killpg(process.pid,signal.SIGKILL)
        self.assertEqual(process.poll(),-signal.SIGTERM)
        with self.assertRaises(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)

    def test_actual_cooperative_timeout_cleanup_preserves_receipt(self):
        process=subprocess.Popen(['sleep','30'],start_new_session=True)
        v2.cleanup_group(process)
        self.assertEqual(process.returncode,-signal.SIGTERM)
        self.assertTrue(process._hybrid_group_cleanup_complete)

    def test_real_permission_failure_remains_failure(self):
        class Child:
            pid=12345
            def poll(self):return None
        with patch.object(v2.os,'killpg',side_effect=[None,PermissionError('denied')]),patch.object(v2.time,'sleep'):
            with self.assertRaises(PermissionError):v2.cleanup_group(Child())

if __name__=='__main__':unittest.main()
