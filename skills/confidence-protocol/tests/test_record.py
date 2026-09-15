"""Public record command authoring and concurrency boundaries."""
try:
    import fcntl
except ImportError:
    fcntl = None
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'confidence.py'
SPEC = importlib.util.spec_from_file_location('record_result_prototype_test', SCRIPT)
confidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(confidence)


@unittest.skipUnless(fcntl is not None and os.name == 'posix', 'record requires Unix locking')
class RecordResultTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-record-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.directory = self.root / '.confidence'
        self.directory.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'source.txt').write_text('stable\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'source.txt'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        assets = Path(__file__).parents[1] / 'assets'
        self.contract = json.loads((assets / 'contract.example.json').read_text())
        self.report = confidence.initial_report(self.contract['task']['title'], self.contract['task']['mode'])
        self.report['kept_extension'] = {'data': 'untouched'}
        confidence.write_json(self.directory / 'contract.json', self.contract)
        confidence.write_json(self.directory / 'report.json', self.report)
        captured = subprocess.run([sys.executable, str(SCRIPT), 'run', '--json', '--id', 'passing', '--directory', str(self.directory), '--cwd', str(self.root), '--', sys.executable, '-c', "print('fixture')"], capture_output=True)
        self.assertEqual(captured.returncode, 0, captured.stderr)

    def invoke(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), 'record', '--directory', str(self.directory), '--obligation', 'P1', '--status', 'pass', '--details', 'Explicit claim judgment', '--run', 'passing', *extra], capture_output=True, text=True)

    def current(self):
        return json.loads((self.directory / 'report.json').read_text())

    def test_selected_result_updates_while_unrelated_fields_stay_incomplete(self):
        before_run = (self.directory / 'runs/passing.json').read_bytes()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout)
        after = self.current()
        expected = dict(self.report)
        expected['evidence'] = [dict(self.report['evidence'][0], status='pass', details='Explicit claim judgment', run_ids=['passing'])]
        self.assertEqual(after, expected)
        self.assertFalse(json.loads(result.stdout)['completion_checked'])
        self.assertEqual((self.directory / 'runs/passing.json').read_bytes(), before_run)

    def test_new_contract_obligation_can_be_added_without_replacing_other_result(self):
        result = self.invoke('--obligation', 'P2')
        self.assertEqual(result.returncode, 0, result.stdout)
        after = self.current()
        self.assertEqual(after['evidence'][0], self.report['evidence'][0])
        self.assertEqual(after['evidence'][1]['obligation_id'], 'P2')

    def test_repeat_is_idempotent_and_does_not_duplicate_evidence(self):
        self.assertEqual(self.invoke().returncode, 0)
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)['changed'])
        self.assertEqual(len(self.current()['evidence']), 1)

    def test_explicit_diagnostic_failure_and_artifact_are_preserved(self):
        captured = subprocess.run([sys.executable, str(SCRIPT), 'run', '--json', '--id', 'diagnostic', '--directory', str(self.directory), '--cwd', str(self.root), '--', sys.executable, '-c', 'import sys; sys.exit(1)'], capture_output=True)
        self.assertEqual(captured.returncode, 1)
        result = self.invoke('--diagnostic-run', 'diagnostic', '--artifact', 'tests/regression.py')
        self.assertEqual(result.returncode, 0, result.stdout)
        evidence = self.current()['evidence'][0]
        self.assertEqual(evidence['diagnostic_run_ids'], ['diagnostic'])
        self.assertEqual(evidence['artifacts'], ['tests/regression.py'])
        self.assertEqual(evidence['run_ids'], ['passing'])

    def test_failed_support_cannot_become_pass_and_leaves_report_intact(self):
        path = self.directory / 'runs/passing.json'
        record = json.loads(path.read_text())
        record['exit_code'] = 7
        path.write_text(json.dumps(record))
        before = (self.directory / 'report.json').read_bytes()
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['code'], 'RESULT_INVALID')
        self.assertEqual((self.directory / 'report.json').read_bytes(), before)

    def test_stale_support_cannot_become_pass(self):
        (self.root / 'source.txt').write_text('changed\n')
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn('stale', result.stdout)
        self.assertEqual(self.current(), self.report)

    def test_no_run_is_not_inferred_from_successful_history(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'record', '--directory', str(self.directory), '--obligation', 'P1', '--status', 'pass', '--details', 'Explicit'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('needs a captured run', result.stdout)

    def test_bad_status_returns_json_without_mutation(self):
        result = self.invoke('--status', 'proved')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['code'], 'ARGUMENT_INVALID')
        self.assertEqual(self.current(), self.report)

    def test_unknown_record_option_returns_json_but_other_commands_keep_argparse(self):
        result = self.invoke('--bogus')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['code'], 'ARGUMENT_INVALID')
        other = subprocess.run([sys.executable, str(SCRIPT), 'validate', '--bogus'], capture_output=True, text=True)
        self.assertEqual(other.returncode, 2)
        self.assertEqual(other.stdout, '')
        self.assertIn('unrecognized arguments', other.stderr)

    def test_fifo_contract_and_report_are_rejected_without_blocking(self):
        for filename in ('contract.json', 'report.json'):
            with self.subTest(filename=filename):
                path = self.directory / filename
                original = path.read_bytes()
                path.unlink()
                os.mkfifo(path)
                try:
                    result = subprocess.run([sys.executable, str(SCRIPT), 'record',
                        '--directory', str(self.directory), '--obligation', 'P1',
                        '--status', 'partial', '--details', 'Explicit'],
                        capture_output=True, text=True, timeout=3)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(json.loads(result.stdout)['code'], 'DOCUMENT_INVALID')
                    self.assertIn('regular file', result.stdout)
                finally:
                    path.unlink()
                    path.write_bytes(original)
        self.assertEqual(self.invoke().returncode, 0)

    def test_validate_rejects_fifo_instead_of_blocking(self):
        path = self.directory / 'report.json'
        original = path.read_bytes()
        path.unlink()
        os.mkfifo(path)
        try:
            result = subprocess.run([sys.executable, str(SCRIPT), 'validate',
                '--directory', str(self.directory)], capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('regular file', result.stdout + result.stderr)
        finally:
            path.unlink()
            path.write_bytes(original)

    def test_strict_json_rules_survive_regular_file_reader(self):
        path = self.directory / 'report.json'
        original = path.read_bytes()
        for payload in (b'{"version":3,"version":3}', b'\xff', b'[]'):
            with self.subTest(payload=payload):
                path.write_bytes(payload)
                result = self.invoke()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)['code'], 'DOCUMENT_INVALID')
        path.write_bytes(original)

    def test_symlink_report_is_rejected(self):
        path = self.directory / 'report.json'
        target = self.root / 'other.json'
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['code'], 'EVIDENCE_UNSAFE')
        self.assertEqual(json.loads(target.read_text()), self.report)

    def test_active_writer_lock_returns_actionable_busy_and_then_recovers(self):
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.invoke()
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['code'], 'LOCK_BUSY')
        finally:
            os.close(descriptor)
        self.assertEqual(self.invoke().returncode, 0)

    def test_killed_writer_does_not_leave_a_stale_lock(self):
        holder = subprocess.Popen([sys.executable, '-c',
            "import fcntl,os,sys,time; f=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(60)",
            str(self.directory)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), 'locked')
            holder.kill()
            holder.wait(timeout=5)
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=5)
            holder.stdout.close()
        self.assertEqual(self.invoke().returncode, 0)

    def test_concurrent_different_obligations_survive_retry(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        def update(obligation):
            for _ in range(20):
                result = self.invoke('--obligation', obligation)
                if result.returncode == 0:
                    return
                self.assertEqual(json.loads(result.stdout)['code'], 'LOCK_BUSY')
                time.sleep(0.01)
            self.fail('writer did not make progress')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(update, ['P1', 'P2']))
        self.assertEqual({entry['obligation_id']: entry['status'] for entry in self.current()['evidence']}, {'P1': 'pass', 'P2': 'pass'})

    def test_case_aliases_contend_on_the_same_directory_inode(self):
        alias = self.directory.with_name('.CONFIDENCE')
        if not alias.exists():
            self.skipTest('filesystem distinguishes case')
        descriptor = os.open(alias, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.invoke()
            self.assertEqual(json.loads(result.stdout)['code'], 'LOCK_BUSY')
        finally:
            os.close(descriptor)
        self.assertEqual(self.invoke().returncode, 0)

    def test_atomic_report_replacement_does_not_release_directory_lock(self):
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = self.directory / 'report.json'
            confidence.write_text_atomic(path, path.read_text(), replace=True)
            result = self.invoke()
            self.assertEqual(json.loads(result.stdout)['code'], 'LOCK_BUSY')
        finally:
            os.close(descriptor)
        self.assertEqual(self.invoke().returncode, 0)

    def test_symlink_evidence_directory_is_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.directory, target_is_directory=True)
        result = self.invoke('--directory', str(alias))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['code'], 'DIRECTORY_UNSAFE')
        self.assertEqual(self.current(), self.report)

    def test_atomic_write_failure_leaves_prior_report_and_releases_lock(self):
        args = type('Args', (), dict(directory=str(self.directory), obligation='P1', status='pass', details='Explicit', run=['passing'], diagnostic_run=[], artifact=[]))()
        with patch.object(confidence.os, 'replace', side_effect=OSError('injected replace failure')):
            with self.assertRaises(OSError):
                confidence.record_result(args)
        self.assertEqual(self.current(), self.report)
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(list(self.directory.glob('.report.json.tmp-*')), [])

    def test_current_set_replacement_preserves_old_capture_files(self):
        self.assertEqual(self.invoke().returncode, 0)
        result = subprocess.run([sys.executable, str(SCRIPT), 'record', '--directory', str(self.directory), '--obligation', 'P1', '--status', 'partial', '--details', 'New explicit scope has no supporting run yet'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.current()['evidence'][0]['run_ids'], [])
        self.assertTrue((self.directory / 'runs/passing.json').exists())
        self.assertTrue((self.directory / 'runs/passing.log').exists())


class RecordUnsupportedTest(unittest.TestCase):
    def test_missing_unix_locking_returns_structured_error_without_report_change(self):
        with tempfile.TemporaryDirectory(prefix='confidence-record-unsupported-') as location:
            directory = Path(location)
            report = directory / 'report.json'
            report.write_text('unchanged report')
            command = [str(SCRIPT), 'record', '--directory', location,
                       '--obligation', 'P1', '--status', 'partial', '--details', 'not checked']
            bootstrap = "import runpy,sys; sys.modules['fcntl']=None; sys.argv=" + repr(command) + "; runpy.run_path(sys.argv[0],run_name='__main__')"
            result = subprocess.run([sys.executable, '-c', bootstrap], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)['code'], 'PLATFORM_UNSUPPORTED')
            self.assertEqual(report.read_text(), 'unchanged report')


if __name__ == '__main__':
    unittest.main()
