"""Actual local lifecycle controls. No hosted inference or trial outcomes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


processes = load('hybrid_process_control', 'hybrid_process.py')


@unittest.skipUnless(os.name == 'posix', 'POSIX process-group lifecycle')
class HybridProcessControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hybrid-process-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.scratch = self.workspace / '.trial-tmp'
        self.scratch.mkdir()
        self.control = self.root / 'control'
        self.control.mkdir()
        self.base = load('guard_base_fixture', 'runner.py')
        self.backend = load('guard_backend_fixture', 'cross_backend.py')
        processes.install(self.base, self.backend)

    def leader(self, *, detached=False, leader_wait=False):
        ready = self.workspace / ('detached-ready' if detached else 'ready')
        marker = self.workspace / ('detached-late' if detached else 'late')
        child = ('import pathlib,signal,time,os;'
                 + ('os.setsid();' if detached else '')
                 + 'signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                 + 'pathlib.Path(' + repr(str(ready)) + ').write_text("ready");'
                 + 'time.sleep(.4);pathlib.Path(' + repr(str(marker)) + ').write_text("late")')
        leader = ('import pathlib,subprocess,sys,time\n'
                  'child=subprocess.Popen([sys.executable,"-B","-c",' + repr(child) + '])\n'
                  'until=time.monotonic()+2\n'
                  'while not pathlib.Path(' + repr(str(ready)) + ').exists() and time.monotonic()<until:time.sleep(.005)\n'
                  + ('time.sleep(2)\n' if leader_wait else ''))
        return leader, ready, marker

    def command(self, code, timeout=2):
        argv = [sys.executable, '-B', '-c', code]
        if Path('/usr/bin/sandbox-exec').exists():
            argv = ['/usr/bin/sandbox-exec', '-p', self.base.sandbox_profile(self.workspace, self.scratch), *argv]
        return processes.bounded_process(argv, cwd=self.workspace,
            env=self.base.safe_env(self.workspace, self.scratch), timeout=timeout,
            output_prefix=self.control / 'command')

    def test_normal_success_preserves_exit_and_final_hash(self):
        result = self.command('print("observed")')
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['timed_out'])
        self.assertEqual(result['stdout_sha256'], hashlib.sha256(Path(result['stdout']).read_bytes()).hexdigest())

    def test_successful_leader_cannot_leave_sigterm_ignoring_group_writer(self):
        code, ready, marker = self.leader()
        result = self.command(code)
        self.assertTrue(ready.exists())
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['timed_out'])
        time.sleep(.5)
        self.assertFalse(marker.exists(), 'Original-group writer survived successful leader exit')

    def test_timeout_reaps_leader_and_sigterm_ignoring_group_writer(self):
        code, ready, marker = self.leader(leader_wait=True)
        result = self.command(code, timeout=.3)
        self.assertTrue(ready.exists())
        self.assertTrue(result['timed_out'])
        self.assertIsInstance(result['exit_code'], int)
        self.assertLess(result['wall_seconds'], 1)
        time.sleep(.5)
        self.assertFalse(marker.exists())

    def test_setsid_escape_is_a_real_disclosed_limit(self):
        code, ready, marker = self.leader(detached=True)
        result = self.command(code)
        self.assertTrue(ready.exists())
        self.assertFalse(result['detached_descendants_contained'])
        time.sleep(.5)
        # The child finishes itself; this control leaves no perpetual orphan.
        self.assertTrue(marker.exists(), 'Do not replace an exercised limitation with a full-tree claim')

    def test_proxy_install_does_not_mutate_shared_subprocess_or_other_modules(self):
        original = subprocess.Popen
        frozen = load('unmodified_other_cohort', 'runner.py')
        self.assertIs(subprocess.Popen, original)
        self.assertIs(frozen.subprocess, subprocess)
        self.assertIs(self.base.bounded_process, processes.bounded_process)
        self.assertIs(self.backend.runner.bounded_process, processes.bounded_process)
        processes.install(self.base, self.backend)
        self.assertIs(subprocess.Popen, original)

    def test_parallel_guards_do_not_kill_other_invocation_group(self):
        marker = self.workspace / 'other-trial-finished'
        errors = []
        started = threading.Event()
        def long_call():
            try:
                with processes.ProcessGuard():
                    child = self.base.subprocess.Popen([sys.executable, '-B', '-c',
                        'import time,pathlib;time.sleep(.3);pathlib.Path(' + repr(str(marker)) + ').write_text("owned")'],
                        start_new_session=True)
                    started.set()
                    self.assertEqual(child.wait(timeout=2), 0)
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=long_call)
        thread.start()
        self.assertTrue(started.wait(timeout=2))
        with processes.ProcessGuard():
            own = self.base.subprocess.Popen([sys.executable, '-B', '-c', 'pass'], start_new_session=True)
            self.assertEqual(own.wait(timeout=2), 0)
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(marker.exists())

    def test_dummy_claude_success_cleans_cli_descendants(self):
        code, ready, marker = self.leader()
        terminal = {'type': 'result', 'is_error': False, 'structured_output': {
            'complete': False, 'summary': 'dummy lifecycle control', 'remaining': ['toy']},
            'total_cost_usd': 0, 'usage': {}, 'modelUsage': {}}
        binary = self.root / 'bin'
        binary.mkdir()
        cli = binary / 'claude'
        cli.write_text('#!' + sys.executable + '\n' + code + '\nprint(' + repr(json.dumps(terminal)) + ')\n')
        cli.chmod(0o755)
        with patch.dict(os.environ, {'PATH': str(binary) + os.pathsep + os.environ['PATH']}):
            result = self.base.claude_call(self.workspace, self.control, 'dummy control', .1, 2, time.time() + 3)
        self.assertTrue(ready.exists())
        self.assertEqual(result['process_exit'], 0)
        self.assertEqual(result['guarded_new_session_processes'], 1)
        time.sleep(.5)
        self.assertFalse(marker.exists())

    def test_dummy_codex_success_cleans_cli_descendants(self):
        code, ready, marker = self.leader()
        terminal = {'complete': False, 'summary': 'dummy lifecycle control', 'remaining': ['toy']}
        code += '\npathlib.Path(' + repr(str(self.control / 'final.json')) + ').write_text(' + repr(json.dumps(terminal)) + ')\n'
        code += 'print(' + repr(json.dumps({'type': 'turn.completed', 'usage': {}})) + ')\n'
        catalog = self.root / 'catalog.json'
        catalog.write_text('{}')
        inventory = {'inventory': {'passed': True, 'expected_tools': []},
            'capability_catalog_sha256': hashlib.sha256(catalog.read_bytes()).hexdigest(),
            'model_requested': self.backend.MODEL, 'cli_version': self.backend.CLI_VERSION,
            'tool_schema_sha256': self.backend.runner.digest_json(self.backend.runner.TOOL_SCHEMAS)}
        with patch.object(self.backend, 'version', return_value=self.backend.CLI_VERSION), \
                patch.object(self.backend, 'command', return_value=[sys.executable, '-B', '-c', code]):
            result = self.backend.codex_call(self.workspace, self.control, 'dummy control', catalog=catalog,
                timeout=2, with_mcp=False, inventory_receipt=inventory)
        self.assertTrue(ready.exists())
        self.assertEqual(result['process_exit'], 0)
        self.assertEqual(result['guarded_new_session_processes'], 1)
        time.sleep(.5)
        self.assertFalse(marker.exists())

    def test_wrapper_refreshes_stream_digest_after_cleanup(self):
        stream = self.control / 'stream.jsonl'
        def function(workspace, control):
            stream.write_text('final bytes\n')
            return {'stream_sha256': 'obsolete'}
        result = processes.guarded_call(function)(self.workspace, self.control)
        self.assertTrue(result['stream_changed_during_cleanup'])
        self.assertEqual(result['stream_sha256'], hashlib.sha256(stream.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
