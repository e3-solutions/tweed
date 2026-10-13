"""Synthetic prospective custody controls; no hosted calls or live study reads."""
import copy
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('followup_v2_control_target', HERE / 'followup_v2.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
r = v.r
ARMS = ('baseline-opus', 'enhanced-opus', 'enhanced-haiku', 'enhanced-codex')


class ProspectiveCustodyControls(unittest.TestCase):
    def fixture(self, root):
        initial = root / 'initial'; initial.mkdir(); prepared = root / 'old-preparation'; prepared.mkdir()
        r.write(initial / 'registration.json', {'synthetic': True})
        requests = [{'trial_id': task + '--' + arm + '--r' + str(repeat), 'task_id': task, 'arm_id': arm, 'repeat': repeat}
                    for task in ('tweed-pr32', 'tweed-pr31', 'tweed-pr40', 'tweed-pr34', 'tweed-pr39', 'tweed-pr35') for arm in ARMS for repeat in (1, 2)]
        roster = [row for row in requests if row['task_id'] == 'tweed-pr40']
        adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
        closure = []
        for index, row in enumerate(requests):
            directory = initial / 'trials' / row['trial_id']; directory.mkdir(parents=True)
            raw = dict(row, eligible=index % 2 == 0, accepted=index % 3 == 0)
            if row['task_id'] == 'tweed-pr40':
                snapshot = directory / 'result_snapshot'; snapshot.mkdir(); (snapshot / 'bonaparte').write_text('regular candidate ' + str(index))
                patchfile = directory / 'submitted.patch'; patchfile.write_text('exact patch ' + str(index))
                main = directory / 'main'; main.mkdir(); (main / 'stream.jsonl').write_text('bound stream')
                (main / 'request.json').write_text('bound request'); (directory / 'grader.stdout').write_text('bound grade')
                raw.update(result_sha256=adapter.frozen.base.tree_digest(snapshot), patch_sha256=r.sha(patchfile))
            r.write(directory / 'receipt.json', raw); closure.append(raw)
        r.write(initial / 'requests.json', requests); r.write(initial / 'results.json', closure)
        novel = prepared / 'novel'; novel.mkdir(); (novel / 'oracle').mkdir(); (novel / 'oracle/evaluate.py').write_text('never execute')
        (novel / 'base').mkdir(); (novel / 'base/bonaparte').write_text('trusted fixture')
        controls = prepared / 'controls'; controls.mkdir(); r.write(controls / 'results.json', {'passed': True, 'observations': []})
        payload = {'initial_study': str(initial), 'initial_registration_sha256': r.sha(initial / 'registration.json'),
                   'roster': roster, 'arm': {'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'},
                   'requirements': v.REQUIREMENTS, 'seconds': 120, 'claude_budget_usd': 1, 'model': 'claude-opus-5-5', 'effort': 'medium',
                   'files': {str(controls / 'results.json'): r.sha(controls / 'results.json')},
                   'trees': {str(novel): r.inventory(novel), str(controls): r.inventory(controls)}, 'limitations': [], 'oracle_script': str(novel / 'oracle/evaluate.py')}
        r.write(prepared / 'declaration.json', {'payload': payload, 'payload_sha256': r.digest(payload)})
        analysis = root / 'analysis.json'; r.write(analysis, {'neutral': True}); rechecks = root / 'rechecks'; rechecks.mkdir(); (rechecks / 'receipt.json').write_text('closed CPU receipt')
        amendment = root / 'amendment.md'; amendment.write_text('Prospective exact scratch exclusion; no source selection.')
        return initial, prepared, root / 'v2', analysis, rechecks, amendment, roster, payload

    def prepare(self, fixture):
        _, prepared, output, analysis, rechecks, amendment, _, _ = fixture
        return v.prepare(prepared, output, analysis, rechecks, amendment)

    def test_old_seal_rejects_scratch_symlink_v2_keeps_same_eight_sources(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = self.fixture(Path(name).resolve()); initial, prepared, output, _, _, _, roster, _ = fixture
            scratch = initial / 'trials' / roster[1]['trial_id'] / v.EXCLUSION['path']; scratch.mkdir(parents=True)
            (scratch / 'legitimate-fixture-link').symlink_to('/bin/sh')
            with patch.object(r, 'verify', return_value={}), patch.object(v, 'current_witness', return_value={}):
                with self.assertRaisesRegex(ValueError, 'symlink'): v.original.seal(prepared)
                self.assertFalse((prepared / 'input-seal.json').exists())
                original_sha = r.sha(prepared / 'declaration.json'); self.prepare(fixture); sealed = v.seal(output)
                self.assertEqual(len(sealed['inputs']), 8); self.assertTrue(all(row['available'] for row in sealed['inputs']))
                self.assertTrue(any(row['initial_accepted'] is False for row in sealed['inputs']))
                self.assertEqual(r.sha(prepared / 'declaration.json'), original_sha)
                for row in sealed['inputs']:
                    self.assertEqual(row['source_inventory'], r.inventory(row['source']))
                    self.assertFalse(any(key.startswith(v.EXCLUSION['path'] + '/') for key in row['first_stage_artifact_inventory']))
                    self.assertIn('main/stream.jsonl', row['first_stage_artifact_inventory'])
                    self.assertIn('submitted.patch', row['first_stage_artifact_inventory'])
                v.verify(output)
                (scratch / 'another-unconsumed-link').symlink_to('/bin/sh'); v.verify(output)

    def test_any_nonexcluded_symlink_is_rejected(self):
        for location in ('main/request.json', 'main/stream.jsonl', 'result_snapshot/bonaparte', 'submitted.patch',
                         'grader.stdout', 'main/execution-scratch', 'main/execution-scratch-other/link', 'other/link', 'source-root', 'trial-root', 'trial-parent'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name).resolve()); initial, _, _, _, _, _, roster, payload = fixture
                directory = initial / 'trials' / roster[0]['trial_id']
                if location in ('source-root', 'trial-root', 'trial-parent'):
                    path = directory / 'result_snapshot' if location == 'source-root' else directory if location == 'trial-root' else directory.parent
                    moved = path.with_name(path.name + '-real'); path.rename(moved); path.symlink_to(moved, target_is_directory=True)
                else:
                    path = directory / location; path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists(): path.unlink()
                    path.symlink_to('/bin/sh')
                with self.assertRaisesRegex(ValueError, '[Ss]ymlink'): v.closed_inputs(payload)

    def test_closure_mismatch_and_missing_source_or_patch_fail_before_seal(self):
        for fault in ('closure', 'missing-source', 'missing-patch', 'patch-drift'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name).resolve()); initial, _, _, _, _, _, roster, payload = fixture
                directory = initial / 'trials' / roster[0]['trial_id']
                if fault == 'closure':
                    values = r.read(initial / 'results.json'); values[0]['accepted'] = not values[0]['accepted']; r.write(initial / 'results.json', values)
                elif fault == 'missing-source': (directory / 'result_snapshot/bonaparte').unlink()
                elif fault == 'missing-patch': (directory / 'submitted.patch').unlink()
                else: (directory / 'submitted.patch').write_text('drift')
                with self.assertRaises(ValueError): v.closed_inputs(payload)

    def test_source_log_request_grader_and_mode_drift_fail_after_seal(self):
        for location in ('main/stream.jsonl', 'main/request.json', 'grader.stdout', 'result_snapshot/bonaparte', 'submitted.patch', 'mode'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name).resolve()); initial, _, output, _, _, _, roster, _ = fixture
                with patch.object(r, 'verify', return_value={}), patch.object(v, 'current_witness', return_value={}):
                    self.prepare(fixture); v.seal(output)
                    directory = initial / 'trials' / roster[0]['trial_id']
                    if location == 'mode':
                        path = directory / 'main/stream.jsonl'; path.chmod(path.stat().st_mode ^ 0o100)
                    else: (directory / location).write_text('drift')
                    with self.assertRaises(ValueError): v.verify(output)

    def test_prepare_refuses_overwrite_and_sealed_or_started_original(self):
        for fault in ('output', 'sealed', 'started'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name:
                fixture = self.fixture(Path(name).resolve())
                if fault == 'output': fixture[2].mkdir()
                elif fault == 'sealed': (fixture[1] / 'input-seal.json').write_text('sealed')
                else: (fixture[1] / 'trials').mkdir()
                with self.assertRaises(ValueError): self.prepare(fixture)

    def test_witness_requires_exact_current_analysis_and_agreement_no_regrading(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve(); analysis = root / 'analysis.json'; current = {'rows': [{'eligible': True}], 'current_recheck_summary': {'known_agreements': 1, 'known_disagreements': 0}}
            r.write(analysis, current); proxy = SimpleNamespace(invoke_oracle=lambda *_: None)
            module = SimpleNamespace(r=proxy, analyze=lambda *_: copy.deepcopy(current))
            payload = {'initial_study': str(root), 'analysis_witness': {'analysis': str(analysis), 'rechecks': str(root)}}
            with patch.object(v, 'load', return_value=module):
                self.assertEqual(v.current_witness(payload), current)
                with self.assertRaisesRegex(ValueError, 'only reuse'): proxy.invoke_oracle()
                r.write(analysis, {'different': True})
                with self.assertRaisesRegex(ValueError, 'differs'): v.current_witness(payload)
                current['current_recheck_summary']['known_disagreements'] = 1; r.write(analysis, current)
                with self.assertRaisesRegex(ValueError, 'must agree'): v.current_witness(payload)


if __name__ == '__main__': unittest.main()
