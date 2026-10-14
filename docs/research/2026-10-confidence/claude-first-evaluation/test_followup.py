"""Pre-outcome controls; never issue hosted calls or inspect current main results."""
import ast
import copy
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('followup_test_target', HERE / 'followup.py')
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
r = f.r
TRUSTED = HERE.parents[3] / '.confidence/benchmark/curation/hybrid-pr-40/oracle'
HEAD = HERE.parents[3] / '.confidence/benchmark/curation/pr-40/head'


class FollowupControls(unittest.TestCase):
    def fixture(self, root):
        oracle = root / 'original' / 'oracle'; (oracle / 'modules').mkdir(parents=True)
        (oracle.parent / 'base').mkdir(); (oracle.parent / 'base' / 'bonaparte').write_text('original base')
        (oracle / 'evaluate.py').write_text('trusted evaluator')
        (oracle / 'modules' / 'test_budget_resume_audit.py').write_text(
            "import unittest\nclass BudgetResumeAudit(unittest.TestCase):\n"
            "    def " + f.METHOD + "(self):\n"
            "        inputs = {'BONAPARTE_SOFT_PHASE_BUDGET': 'off'}\n"
            "        self.assertEqual(inputs['BONAPARTE_SOFT_PHASE_BUDGET'], 'off' if False else inputs['BONAPARTE_SOFT_PHASE_BUDGET'])\n")
        # Exactly one off constant in the true copied fixture requirement.
        text = (oracle / 'modules' / 'test_budget_resume_audit.py').read_text()
        text = text.replace("'off' if False else inputs", "inputs")
        (oracle / 'modules' / 'test_budget_resume_audit.py').write_text(text)
        r.write(oracle / 'oracle.json', {'task_id': 'tweed-pr40', 'test_ids': ['old.test'], 'production_paths': ['bonaparte']})
        return oracle

    def test_oracle_derivation_changes_only_public_token_and_method_name(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); original = self.fixture(root); destination = root / 'novel' / 'oracle'
            destination.parent.mkdir()
            derivation = f.build_oracle(original, destination)
            old = ast.parse((original / 'modules' / 'test_budget_resume_audit.py').read_text()).body[-1].body[0]
            new = ast.parse((destination / 'modules' / 'test_budget_unbounded_probe.py').read_text()).body[-1].body
            self.assertEqual(len(new), 2)
            for method, token, name in zip(new, f.TOKENS, f.NAMES):
                expected = copy.deepcopy(old); expected.name = name
                for node in ast.walk(expected):
                    if isinstance(node, ast.Constant) and node.value == 'off': node.value = token
                self.assertEqual(ast.dump(method, include_attributes=False), ast.dump(expected, include_attributes=False))
            config = r.read(destination / 'oracle.json')
            self.assertEqual(config['test_ids'], derivation['test_ids'])
            self.assertEqual(len(config['test_ids']), 2)
            self.assertNotIn('old.test', config['test_ids'])
            self.assertEqual(r.sha(destination / 'evaluate.py'), r.sha(original / 'evaluate.py'))

    def test_oracle_source_fixture_drift_fails_before_call(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); original = self.fixture(root)
            source = original / 'modules' / 'test_budget_resume_audit.py'
            source.write_text(source.read_text().replace("'off'", "'never'"))
            destination = root / 'novel' / 'oracle'; destination.parent.mkdir()
            with self.assertRaisesRegex(ValueError, 'one off input'): f.build_oracle(original, destination)

    def test_input_seal_keeps_incorrect_and_missing_artifacts_without_selection(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); initial = root / 'initial'; initial.mkdir(); out = root / 'probe'; out.mkdir()
            roster = [{'trial_id': 'tweed-pr40--arm' + str(n // 2) + '--r' + str(n % 2 + 1), 'task_id': 'tweed-pr40', 'arm_id': 'arm' + str(n // 2), 'repeat': n % 2 + 1} for n in range(8)]
            r.write(initial / 'requests.json', roster + [{'trial_id': 'other' + str(n)} for n in range(40)])
            r.write(initial / 'results.json', roster + [{'trial_id': 'other' + str(n)} for n in range(40)])
            r.write(out / 'declaration.json', {'fixture': True})
            for n, row in enumerate(roster[:7]):
                directory = initial / 'trials' / row['trial_id']; snapshot = directory / 'result_snapshot'; snapshot.mkdir(parents=True)
                (snapshot / 'bonaparte').write_text('wrong-but-regular' if n else 'correct-regular')
                adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
                r.write(directory / 'receipt.json', dict(row, eligible=n == 0, accepted=n == 0, result_sha256=adapter.frozen.base.tree_digest(snapshot)))
            declaration = {'initial_study': str(initial), 'roster': roster, 'arm': {'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'}}
            with patch.object(f, 'verify_declaration', return_value=declaration): value = f.seal(out)
            self.assertEqual(len(value['inputs']), 8)
            self.assertEqual(sum(row['available'] for row in value['inputs']), 7)
            self.assertFalse(value['inputs'][1]['initial_accepted'])
            self.assertTrue(value['inputs'][1]['available'])
            self.assertFalse(value['inputs'][7]['available'])
            with self.assertRaisesRegex(ValueError, 'overwrite'): f.seal(out)

    def test_missing_source_records_not_run_without_call(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); row = {'trial_id': 'assigned', 'task_id': 'tweed-pr40', 'arm_id': 'enhanced-haiku', 'repeat': 1,
                                      'initial_eligible': None, 'initial_accepted': None, 'available': False, 'missing_reason': 'absent'}
            with patch.object(r, 'route', side_effect=AssertionError('no model call')):
                value = f.run_cell(row, {}, root)
            self.assertEqual(value['status'], 'not_run_missing_initial_source')
            self.assertIsNone(value['novel_passed'])
            self.assertFalse((root / 'trials' / 'assigned' / 'started.json').exists())

    def test_existing_started_probe_is_preserved_without_call(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); prior = root / 'trials' / 'assigned'; prior.mkdir(parents=True)
            (prior / 'started.json').write_text('previous unknown')
            with patch.object(r, 'route', side_effect=AssertionError('no retry')):
                value = f.run_cell({'trial_id': 'assigned'}, {}, root)
            self.assertEqual(value['status'], 'preserved_previously_started')
            self.assertEqual((prior / 'started.json').read_text(), 'previous unknown')

    def test_first_stage_log_and_source_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); initial = root / 'initial'; initial.mkdir(); out = root / 'probe'; out.mkdir()
            rows = []
            for n in range(8):
                row = {'trial_id': 'trial' + str(n), 'task_id': 'tweed-pr40', 'arm_id': 'arm' + str(n // 2), 'repeat': n % 2 + 1}
                directory = initial / 'trials' / row['trial_id']; directory.mkdir(parents=True)
                (directory / 'stream.jsonl').write_text('bound stream')
                rows.append(dict(row, source=str(directory / 'result_snapshot'), available=False, first_stage_artifact_inventory=r.inventory(directory)))
            r.write(initial / 'results.json', [{'trial_id': 'trial' + str(n)} for n in range(48)])
            r.write(out / 'declaration.json', {'fixture': True})
            declaration = {'initial_study': str(initial), 'roster': [{k: row[k] for k in ('trial_id', 'task_id', 'arm_id', 'repeat')} for row in rows]}
            payload = {'declaration_sha256': r.sha(out / 'declaration.json'), 'initial_results_sha256': r.sha(initial / 'results.json'), 'inputs': rows}
            r.write(out / 'input-seal.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
            with patch.object(f, 'verify_declaration', return_value=declaration):
                f.verify(out)
                (initial / 'trials' / 'trial3' / 'stream.jsonl').write_text('changed after freeze')
                with self.assertRaisesRegex(ValueError, 'artifact/log drift'): f.verify(out)

    @unittest.skipUnless(Path('/usr/bin/sandbox-exec').is_file() and TRUSTED.is_dir() and HEAD.is_dir(), 'Needs trusted historical fixture and macOS sandbox')
    def test_real_novel_oracle_rejects_old_head_and_accepts_bounded_extension(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); novel = root / 'novel' / 'oracle'; novel.parent.mkdir()
            f.build_oracle(TRUSTED, novel)
            adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
            bad = root / 'bad'; bad.mkdir()
            self.assertIs(r.invoke_oracle(adapter, novel / 'evaluate.py', HEAD, bad)['oracle_passed'], False)
            alternative = root / 'alternative'; adapter.frozen.base.safe_copy(HEAD, alternative)
            path = alternative / 'bonaparte'; path.write_text(path.read_text().replace('configured.strip().casefold() == "off"', 'configured.strip().casefold() in ("off", "unbounded")', 1))
            for label, script in [('new', novel / 'evaluate.py'), ('original', TRUSTED / 'evaluate.py')]:
                directory = root / label; directory.mkdir()
                self.assertIs(r.invoke_oracle(adapter, script, alternative, directory)['oracle_passed'], True)


if __name__ == '__main__': unittest.main()
