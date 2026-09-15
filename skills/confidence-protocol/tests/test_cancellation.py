"""A terminated agent runner must clean up the entire captured process group."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'confidence.py'


@unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
class CancellationTest(unittest.TestCase):
    def check_cancellation(self, cancellation, repeated=False):
        with tempfile.TemporaryDirectory(prefix='confidence-cancel-') as td:
            root = Path(td)
            grandchild = "from pathlib import Path; import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path('ready').touch(); time.sleep(0.6); Path('orphan').touch()"
            child = f"import subprocess,sys,time,signal; from pathlib import Path; signal.signal(signal.SIGTERM, lambda *_: (Path('stopping').touch(), time.sleep(0.08))); subprocess.Popen([sys.executable,'-c',{grandchild!r}]); time.sleep(10)"
            runner = subprocess.Popen([sys.executable, str(SCRIPT), 'run', '--json', '--id', 'cancelled', '--directory', str(root/'.confidence'), '--cwd', td, '--', sys.executable, '-c', child], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not (root/'ready').exists() and runner.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((root/'ready').exists(), 'captured descendant did not start')
                runner.send_signal(cancellation)
                if repeated:
                    deadline = time.monotonic() + 5
                    while not (root/'stopping').exists() and runner.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue((root/'stopping').exists())
                    runner.send_signal(signal.SIGTERM)
                    runner.send_signal(signal.SIGINT)
                out, err = runner.communicate(timeout=10)
                time.sleep(0.8)
                self.assertFalse((root/'orphan').exists(), 'descendant survived cancellation')
                self.assertEqual(runner.returncode, 128 + cancellation, err)
                self.assertEqual(out, b'')
                self.assertFalse((root/'.confidence/runs/cancelled.json').exists())
                self.assertIn(b'interrupted', err)
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.communicate()

    def test_sigterm_cleans_up_descendants(self):
        self.check_cancellation(signal.SIGTERM)

    def test_sigint_cleans_up_descendants(self):
        self.check_cancellation(signal.SIGINT)

    def test_repeated_signals_do_not_interrupt_cleanup(self):
        self.check_cancellation(signal.SIGTERM, repeated=True)
