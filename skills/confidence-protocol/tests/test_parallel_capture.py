"""Protocol atomic staging must not invalidate concurrent source observations."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import SCRIPT, load_confidence

core = load_confidence('parallel_core')


class ParallelCaptureTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve(); self.root = self.base / 'repo'; self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'source').write_text('stable')
        self.directory = self.root / '.confidence'; (self.directory / 'runs').mkdir(parents=True)

    def capture(self, runid, script=SCRIPT):
        return subprocess.run([sys.executable, str(script), 'run', '--id', runid, '--directory', str(self.directory), '--cwd', str(self.root), '--', sys.executable, '-c', "from pathlib import Path; assert Path('source').read_text()=='stable'"], capture_output=True, text=True, timeout=15)

    def assert_bound(self, runid):
        record, errors = core.validate_run_record(self.directory, runid)
        self.assertEqual(errors, [])
        self.assertEqual(core.validate_supporting_workspace(record, self.directory), [])

    def test_distinct_parallel_captures_remain_bound(self):
        ids = [f'parallel-{i}' for i in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.capture, ids))
        self.assertEqual([r.returncode for r in results], [0] * 8)
        for runid in ids: self.assert_bound(runid)

    def test_paused_atomic_publish_does_not_stale_observer(self):
        ready = self.base / 'ready'; release = self.base / 'release'; adapter = self.base / 'adapter.py'
        adapter.write_text(f'''import importlib.util,time
from pathlib import Path
s=importlib.util.spec_from_file_location('c',{str(SCRIPT)!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
original=c.os.link
def paused(source,destination,*args,**kwargs):
 if Path(destination).name=='holder.json':
  Path({str(ready)!r}).write_text(str(source))
  until=time.monotonic()+10
  while not Path({str(release)!r}).exists():
   if time.monotonic()>until: raise TimeoutError('test release missing')
   time.sleep(.01)
 return original(source,destination,*args,**kwargs)
c.os.link=paused
raise SystemExit(c.main())
''')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            holder = pool.submit(self.capture, 'holder', adapter)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists():
                    if time.monotonic() > deadline: self.fail('publisher did not reach pause')
                    time.sleep(.01)
                self.assertEqual(self.capture('observer').returncode, 0)
                self.assert_bound('observer')
            finally:
                release.write_text('continue')
            self.assertEqual(holder.result().returncode, 0)
        self.assert_bound('observer'); self.assert_bound('holder')

    def test_record_and_capture_can_run_together(self):
        contract = json.loads((Path(__file__).parents[1] / 'assets/contract.example.json').read_text())
        report = core.initial_report(contract['task']['title'], contract['task']['mode'])
        core.write_json(self.directory / 'contract.json', contract)
        core.write_json(self.directory / 'report.json', report)
        command = [sys.executable, str(SCRIPT), 'record', '--directory', str(self.directory), '--obligation', 'P1', '--status', 'partial', '--details', 'Required observation remains incomplete']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            recording = pool.submit(subprocess.run, command, capture_output=True, text=True, timeout=15)
            capturing = pool.submit(self.capture, 'during-record')
            result = recording.result()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(capturing.result().returncode, 0)
        self.assert_bound('during-record')

    def test_vanished_source_retries_fresh_inventory_without_hiding_change(self):
        source = self.root / 'untracked.py'; source.write_text('source input')
        before = core.git_workspace_fingerprint(self.root, self.directory)
        original = Path.lstat
        def disappearing(path, *args, **kwargs):
            if path == source and path.exists():
                path.unlink()
                raise FileNotFoundError(str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', disappearing):
            after = core.git_workspace_fingerprint(self.root, self.directory)
        self.assertIsNotNone(after)
        self.assertNotEqual(before, after)

    def test_repeated_untracked_instability_remains_unknown(self):
        original = core.subprocess.run
        enumerations = []
        def unstable(argv, *args, **kwargs):
            result = original(argv, *args, **kwargs)
            if '--others' in argv:
                enumerations.append(argv)
                result.stdout += b'vanished-source.py\0'
            return result
        with patch.object(core.subprocess, 'run', unstable):
            self.assertIsNone(core.git_workspace_fingerprint(self.root, self.directory))
        self.assertEqual(len(enumerations), 2)

    def test_only_known_untracked_regular_temporary_names_are_excluded(self):
        fingerprint = lambda: core.git_workspace_fingerprint(self.root, self.directory)
        before = fingerprint()
        for name in ('runs/.valid-id.json.tmp-abcd012_', '.report.json.tmp-abcd012_', '.REPORT.md.tmp-abcd012_'):
            path = self.directory / name; path.write_text('temporary')
            self.assertEqual(before, fingerprint(), name); path.unlink()
        for name in ('runs/.source.py.tmp-abcd012_', '.source.py.tmp-abcd012_', 'runs/._invalid.json.tmp-abcd012_', 'runs/.valid.json.tmp-short'):
            path = self.directory / name; path.write_text('source')
            self.assertNotEqual(before, fingerprint(), name); path.unlink()
        path = self.directory / 'runs/.valid.json.tmp-abcd012_'
        path.write_text('tracked source')
        subprocess.run(['git', '-C', str(self.root), 'add', str(path)], check=True)
        tracked = fingerprint(); path.write_text('changed')
        self.assertNotEqual(tracked, fingerprint())
        subprocess.run(['git', '-C', str(self.root), 'rm', '--cached', '-f', str(path)], check=True, capture_output=True)
        path.unlink(); path.symlink_to(self.root / 'source')
        self.assertNotEqual(before, fingerprint()); path.unlink()
        if hasattr(os, 'mkfifo'):
            path.write_text('tracked before special replacement')
            subprocess.run(['git', '-C', str(self.root), 'add', str(path)], check=True)
            path.unlink(); os.mkfifo(path); self.assertIsNone(fingerprint())

if __name__ == '__main__': unittest.main()
