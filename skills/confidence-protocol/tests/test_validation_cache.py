"""Validation cache boundaries with real Git state and deterministic mutation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from support import SCRIPT, load_confidence

confidence = load_confidence('confidence_cache')


class ValidationCacheTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-cache-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.directory = self.root / 'evidence'
        (self.directory / 'runs').mkdir(parents=True)
        self.repo = self.git_repo('first')

    def git_repo(self, name):
        root = self.root / name
        root.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
        git('init', '-q')
        (root / 'source.txt').write_text('stable source\n')
        git('add', 'source.txt')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        return root

    def record(self, run_id, repo=None):
        repo = repo or self.repo
        workspace = confidence.git_workspace_fingerprint(repo, self.directory)
        path = self.directory / 'runs' / f'{run_id}.log'
        path.write_text('fixture output\n')
        confidence.write_json(self.directory / 'runs' / f'{run_id}.json', {
            'version': 2, 'id': run_id, 'argv': ['fixture'], 'cwd': str(repo),
            'started_at': '2026-09-15T00:00:00Z', 'ended_at': '2026-09-15T00:00:01Z',
            'exit_code': 0, 'workspace_start': workspace, 'workspace': workspace,
            'log': f'runs/{run_id}.log', 'log_sha256': confidence.sha256_file(path),
        })

    def documents(self, run_ids):
        contract = confidence.initial_contract('Cache boundary', 'standard', 'research')
        contract['proof_obligations'] = [
            {'id': f'P{i}', 'claim': 'fixture', 'verification': 'fixture'}
            for i in range(len(run_ids))
        ]
        report = confidence.initial_report('Cache boundary', 'standard')
        report.update(outcome='fixture', rollback='Not applicable')
        report['simplicity']['notes'] = 'fixture'
        report['review']['reason'] = 'fixture'
        report['evidence'] = [
            {'obligation_id': f'P{i}', 'status': 'pass', 'details': 'fixture',
             'artifacts': [], 'run_ids': [run_id], 'diagnostic_run_ids': []}
            for i, run_id in enumerate(run_ids)
        ]
        return report, contract

    def validate(self, documents):
        report, contract = documents
        return confidence.validate_report(report, contract, self.directory)

    def test_single_reference_keeps_one_fingerprint_read(self):
        self.record('one')
        documents = self.documents(['one'])
        with patch.object(confidence, 'git_workspace_fingerprint', wraps=confidence.git_workspace_fingerprint) as fingerprint:
            self.assertEqual(self.validate(documents), [])
        self.assertEqual(fingerprint.call_count, 1)

    def test_repeated_run_uses_two_workspace_reads_but_rechecks_each_log(self):
        self.record('one')
        documents = self.documents(['one'] * 5)
        with patch.object(confidence, 'git_workspace_fingerprint', wraps=confidence.git_workspace_fingerprint) as fingerprint, patch.object(confidence, 'validate_run_record', wraps=confidence.validate_run_record) as records:
            self.assertEqual(self.validate(documents), [])
        self.assertEqual(fingerprint.call_count, 2)
        self.assertEqual(records.call_count, 5)

    def test_persistent_mutation_during_validation_is_rejected(self):
        self.record('one')
        documents = self.documents(['one'] * 3)
        original = confidence.git_workspace_fingerprint
        calls = 0
        def mutate_after_snapshot(*args):
            nonlocal calls
            result = original(*args)
            calls += 1
            if calls == 1:
                (self.repo / 'source.txt').write_text('changed during validation\n')
            return result
        with patch.object(confidence, 'git_workspace_fingerprint', side_effect=mutate_after_snapshot):
            errors = self.validate(documents)
        self.assertTrue(any('changed during validation' in error for error in errors), errors)

    def test_source_mutation_between_calls_is_not_cached(self):
        self.record('one')
        documents = self.documents(['one'] * 3)
        self.assertEqual(self.validate(documents), [])
        (self.repo / 'source.txt').write_text('changed source\n')
        self.assertTrue(any('stale' in error for error in self.validate(documents)))
        (self.repo / 'source.txt').write_text('stable source\n')
        self.assertEqual(self.validate(documents), [])
        (self.repo / 'untracked.txt').write_text('new source\n')
        self.assertTrue(any('stale' in error for error in self.validate(documents)))

    def test_distinct_roots_have_separate_initial_and_final_reads(self):
        other = self.git_repo('second')
        self.record('first')
        self.record('second', other)
        documents = self.documents(['first', 'second', 'first', 'second'])
        with patch.object(confidence, 'git_workspace_fingerprint', wraps=confidence.git_workspace_fingerprint) as fingerprint:
            self.assertEqual(self.validate(documents), [])
        roots = [call.args[0] for call in fingerprint.call_args_list]
        self.assertEqual(roots.count(self.repo.resolve()), 2)
        self.assertEqual(roots.count(other.resolve()), 2)

    def test_duplicate_run_within_one_obligation_still_rejected(self):
        self.record('one')
        report, contract = self.documents(['one'])
        report['evidence'][0]['run_ids'] = ['one', 'one']
        errors = self.validate((report, contract))
        self.assertTrue(any('must not contain duplicates' in error for error in errors))

    def test_log_mutation_between_references_is_not_hidden(self):
        self.record('one')
        documents = self.documents(['one'] * 3)
        original = confidence.validate_run_record
        calls = 0
        def mutate_after_read(*args):
            nonlocal calls
            result = original(*args)
            calls += 1
            if calls == 1:
                (self.directory / 'runs' / 'one.log').write_text('changed output\n')
            return result
        with patch.object(confidence, 'validate_run_record', side_effect=mutate_after_read):
            errors = self.validate(documents)
        self.assertTrue(any('log hash does not match' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
