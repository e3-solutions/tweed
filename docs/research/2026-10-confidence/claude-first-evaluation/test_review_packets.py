"""Synthetic packet privacy/anonymization qualification; no actual outcomes read."""
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('packet_test_target', HERE / 'review_packets.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
r, a = p.r, p.a


class PacketControls(unittest.TestCase):
    def fixture(self, root, missing=False):
        study = root / 'study'; study.mkdir(); public = root / 'public'; public.mkdir()
        r.write(study / 'registration.json', {'synthetic': True})
        adapter = r.route({'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})
        tasks, requests, rows = [], [], []
        hashes = {}
        for n in (32, 31, 40, 34, 39, 35):
            task_id = 'tweed-pr' + str(n); base = root / ('base-' + str(n)); base.mkdir()
            (base / 'public.py').write_text('answer = 1\n')
            (base / 'README.md').write_text('Historical public baseline\n')
            (base / 'AGENTS.md').write_text('PRIVATE_BASE_AUTOLOAD')
            tasks.append({'task_id': task_id, 'base_snapshot': str(base), 'requirements': 'Required answer is 2. Preserve compatibility.',
                          'prompt': 'PRIVATE_SOLVER_PROMPT', 'head_snapshot': 'PRIVATE_ACCEPTED_HEAD', 'oracle_script': 'PRIVATE_ORACLE', 'production_paths': ['public.py']})
            for arm in a.ARMS:
                for repeat in (1, 2):
                    trial = task_id + '--' + arm + '--r' + str(repeat)
                    requests.append({'trial_id': trial, 'task_id': task_id, 'arm_id': arm, 'repeat': repeat, 'prompt': 'PRIVATE_SOLVER_PROMPT'})
                    directory = study / 'trials' / trial; directory.mkdir(parents=True)
                    row = {'trial_id': trial, 'task_id': task_id, 'arm_id': arm, 'repeat': repeat, 'model_requested': 'claude-opus-5-5',
                           'eligible': False, 'oracle_passed': False, 'artifact_bindings': {}, 'patch_bound': False}
                    if not (missing and not rows):
                        candidate = directory / 'result_snapshot'; adapter.frozen.base.safe_copy(base, candidate)
                        (candidate / 'public.py').write_text('answer = 2\n')
                        (candidate / 'support.py').write_text('def support(): return 2\n')
                        (candidate / 'MODEL_SUMMARY.txt').write_text('PRIVATE_MODEL_SUMMARY_AND_OUTCOME')
                        (candidate / '.confidence').mkdir(); (candidate / '.confidence' / 'outcome.json').write_text('PRIVATE_ORACLE_OUTCOME')
                        a.rebuild_patch(adapter, base, candidate, directory / 'submitted.patch', ['public.py'])
                        row.update(patch_bound=True, artifact_bindings={'result_sha256': adapter.frozen.base.tree_digest(candidate), 'patch_sha256': r.sha(directory / 'submitted.patch')})
                        relative = 'patches/' + trial + '.patch'; (public / 'patches').mkdir(exist_ok=True)
                        (public / relative).write_bytes((directory / 'submitted.patch').read_bytes()); hashes[relative] = r.sha(public / relative)
                    rows.append(row)
        manifest = root / 'manifest.json'; r.write(manifest, {'tasks': tasks}); r.write(study / 'requests.json', requests)
        analysis = {'rows': rows, 'registration_sha256': r.sha(study / 'registration.json'), 'current_recheck_summary': None}
        r.write(public / 'analysis.json', analysis); hashes['analysis.json'] = r.sha(public / 'analysis.json')
        r.write(public / 'artifact-hashes.json', {'files': hashes, 'privacy_excluded_patches': {}})
        payload = {'config': {'manifest': str(manifest), 'arms': [{'backend': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'}]}}
        return study, public, payload, analysis

    def build(self, fixture, output):
        study, public, payload, analysis = fixture
        with ExitStack() as stack:
            stack.enter_context(patch.object(a, 'analyze', return_value=analysis))
            stack.enter_context(patch.object(r, 'verify', return_value=payload))
            return p.build(study, public, output)

    def test_anonymous48_packets_omit_routes_outcomes_prompts_and_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root); out = root / 'review'; owner = self.build(fixture, out)
            self.assertEqual(len(owner['mapping']), 48); self.assertEqual(len({item['anonymous_candidate'] for item in owner['mapping']}), 48)
            groups = [path for path in (out / 'visible').iterdir() if path.is_dir()]
            self.assertEqual(len(groups), 6)
            for group in groups: self.assertEqual(len(list((group / 'candidates').iterdir())), 8)
            text = '\n'.join(path.read_text(errors='replace') for path in (out / 'visible').rglob('*') if path.is_file())
            for forbidden in ('PRIVATE_SOLVER_PROMPT', 'PRIVATE_MODEL_SUMMARY', 'PRIVATE_ORACLE', 'PRIVATE_ACCEPTED_HEAD', 'PRIVATE_BASE_AUTOLOAD', 'enhanced-opus', '--r1', str(fixture[0]), str(root)):
                self.assertNotIn(forbidden, text)
            for item in owner['mapping']:
                candidate = out / 'visible' / item['anonymous_task'] / 'candidates' / item['anonymous_candidate']
                self.assertTrue((candidate / 'production/support.py').is_file())
                self.assertFalse((candidate / 'production/MODEL_SUMMARY.txt').exists())
            self.assertEqual(owner['visible_inventory'], r.inventory(out / 'visible'))
            self.assertIn('arm_id', (out / 'private-owner.json').read_text())
            self.assertFalse((out / 'visible/private-owner.json').exists())

    def test_missing_source_is_only_missing_source_without_reason_or_score(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root, missing=True); owner = self.build(fixture, root / 'review')
            missing = next(item for item in owner['mapping'] if item['source_binding'] == 'missing-source')
            target = root / 'review/visible' / missing['anonymous_task'] / 'candidates' / missing['anonymous_candidate']
            self.assertEqual([path.name for path in target.iterdir()], ['status.txt'])
            self.assertEqual((target / 'status.txt').read_text(), 'missing-source\n')
            self.assertEqual(len(owner['mapping']), 48)

    def test_source_and_patch_drift_rejected_before_output(self):
        for artifact in ('result_snapshot/public.py', 'submitted.patch'):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as name:
                root = Path(name); fixture = self.fixture(root); trial = fixture[3]['rows'][0]['trial_id']
                file = fixture[0] / 'trials' / trial / artifact; file.write_bytes(file.read_bytes() + b'changed')
                with self.assertRaises(ValueError): self.build(fixture, root / 'review')
                self.assertFalse((root / 'review').exists())

    def test_reserved_helper_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); base = root / 'base'; candidate = root / 'candidate'; base.mkdir(); candidate.mkdir()
            (base / 'public.py').write_text('baseline'); (candidate / 'public.py').write_text('candidate')
            (candidate / 'json.py').write_text('stdlib shadow')
            with self.assertRaisesRegex(ValueError, 'helper name'): p.production_files(base, candidate, ['public.py'])
            (candidate / 'json.py').unlink(); (candidate / 'new.py').symlink_to(base / 'public.py')
            with self.assertRaisesRegex(ValueError, 'symlink'): p.production_files(base, candidate, ['public.py'])
            with self.assertRaisesRegex(ValueError, 'Unsafe production'): p.production_files(base, candidate, ['../outside'])

    def test_original_model_business_string_is_not_self_attribution(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); before = root / 'before.py'; after = root / 'after.py'
            before.write_text("DEFAULT_MODEL = 'claude-opus-5-5'\n")
            after.write_text(before.read_text() + 'answer = 2\n')
            self.assertEqual(p.potential_unblinding({'public.py': before}, {'public.py': after}), [])
            after.write_text(before.read_text() + '# implemented by Opus 5.5\n')
            warnings = p.potential_unblinding({'public.py': before}, {'public.py': after})
            self.assertEqual(len(warnings), 1); self.assertEqual(warnings[0]['line'], 2)
            self.assertIn('implemented by Opus', after.read_text())


if __name__ == '__main__': unittest.main()
