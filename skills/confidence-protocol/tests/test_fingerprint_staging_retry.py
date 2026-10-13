"""Bounded fresh inventories tolerate atomic publication without hiding source."""
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from support import load_confidence

core = load_confidence('staging_retry_core')


class FingerprintStagingRetryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'source').write_text('stable')
        self.directory = self.root / '.confidence'
        self.runs = self.directory / 'runs'; self.runs.mkdir(parents=True)

    def fingerprint(self, directory=None):
        return core.git_workspace_fingerprint(self.root, directory or self.directory)

    def test_successive_real_atomic_publishers_retry_complete_inventory(self):
        for publishers in (2, 8):
            with self.subTest(publishers=publishers):
                baseline = self.fingerprint(); self.assertIsNotNone(baseline)
                ready = [threading.Event() for _ in range(publishers)]
                release = [threading.Event() for _ in range(publishers)]
                finished = [threading.Event() for _ in range(publishers)]
                staging = {}; errors = []; observed_cleanup = []; workers = []
                original_link = core.os.link; original_lstat = Path.lstat

                def paused_link(source, destination, *args, **kwargs):
                    index = int(Path(destination).stem.split('-')[-1])
                    staging[index] = Path(source); ready[index].set()
                    if not release[index].wait(5):
                        raise TimeoutError('publisher not released')
                    return original_link(source, destination, *args, **kwargs)

                def publish(index):
                    try:
                        core.write_json_exclusive_atomic(self.runs / f'p{publishers}-{index}.json', {'id': index})
                    except BaseException as error:
                        errors.append(repr(error))
                    finally:
                        finished[index].set()

                def start(index):
                    worker = threading.Thread(target=publish, args=(index,))
                    workers.append(worker); worker.start()
                    self.assertTrue(ready[index].wait(5), 'publisher staging not ready')

                def disappearing(path, *args, **kwargs):
                    for index, candidate in list(staging.items()):
                        if path == candidate and not finished[index].is_set():
                            self.assertTrue(candidate.is_file())
                            observed_cleanup.append(index); release[index].set()
                            self.assertTrue(finished[index].wait(5), 'publisher cleanup not complete')
                            if index + 1 < publishers:
                                start(index + 1)
                            # Preserve real Git enumeration and the writer's real unlink.
                            return original_lstat(path, *args, **kwargs)
                    return original_lstat(path, *args, **kwargs)

                with patch.object(core.os, 'link', paused_link):
                    start(0)
                    try:
                        with patch.object(Path, 'lstat', disappearing):
                            observed = self.fingerprint()
                    finally:
                        for event in release: event.set()
                        for worker in workers: worker.join(5)
                self.assertEqual(errors, [])
                self.assertFalse(any(worker.is_alive() for worker in workers))
                self.assertEqual(self.fingerprint(), baseline)
                self.assertEqual((self.root / 'source').read_text(), 'stable')
                self.assertEqual(observed, baseline)
                self.assertEqual(observed_cleanup, list(range(publishers)))

    def missing_inventories(self, names, *, directory=None):
        """Use real Git, appending the prescribed missing name on each inventory."""
        original = core.subprocess.run; enumerations = []
        def enumerate_missing(argv, *args, **kwargs):
            result = original(argv, *args, **kwargs)
            if '--others' in argv:
                index = len(enumerations); enumerations.append(argv)
                result.stdout += os.fsencode(names[min(index, len(names) - 1)]) + b'\0'
            return result
        with patch.object(core.subprocess, 'run', enumerate_missing):
            observed = self.fingerprint(directory)
        return observed, len(enumerations)

    def test_staging_retry_exhaustion_remains_unknown(self):
        for name in ('runs/.vanished.json.tmp-abcd012_', '.contract.json.tmp-abcd012_',
                     '.report.json.tmp-abcd012_', '.REPORT.md.tmp-abcd012_'):
            with self.subTest(name=name):
                observed, enumerations = self.missing_inventories(['.confidence/' + name])
                self.assertIsNone(observed)
                self.assertEqual(enumerations, 9)  # Initial inventory plus eight staging retries.

    def test_staging_retry_never_restores_ordinary_source_budget(self):
        staging = '.confidence/runs/.vanished.json.tmp-abcd012_'
        for names in (['vanished-source.py', staging, staging, 'other-source.py'],
                      [staging, 'vanished-source.py', staging, 'other-source.py']):
            with self.subTest(names=names):
                observed, enumerations = self.missing_inventories(names)
                self.assertIsNone(observed)
                self.assertEqual(enumerations, 4)

    def test_missing_tracked_staging_name_is_bound_without_retry(self):
        path = self.runs / '.tracked.json.tmp-abcd012_'; path.write_text('tracked source')
        subprocess.run(['git', '-C', str(self.root), 'add', str(path)], check=True)
        baseline = self.fingerprint(); path.unlink()
        observed, enumerations = self.missing_inventories(['.confidence/runs/' + path.name])
        self.assertIsNotNone(observed)
        self.assertNotEqual(observed, baseline)
        self.assertEqual(enumerations, 1)

    def test_casing_alias_retains_staging_retry_allowance(self):
        alias = self.root / '.CONFIDENCE'
        if not alias.exists():
            self.skipTest('filesystem has case-sensitive directory names')
        observed, enumerations = self.missing_inventories(
            ['.confidence/runs/.vanished.json.tmp-abcd012_'], directory=alias)
        self.assertIsNone(observed)
        self.assertEqual(enumerations, 9)

    def test_lookalike_and_outside_anchor_missing_names_use_ordinary_budget(self):
        for name in ('vanished-source.py', '.confidence/runs/.source.py.tmp-abcd012_',
                     '.confidence/runs/._invalid.json.tmp-abcd012_',
                     '.confidence/runs/.valid.json.tmp-short',
                     '.confidence/nested/.report.json.tmp-abcd012_',
                     'runs/.valid.json.tmp-abcd012_'):
            with self.subTest(name=name):
                observed, enumerations = self.missing_inventories([name])
                self.assertIsNone(observed)
                self.assertEqual(enumerations, 2)

    def test_symlink_evidence_anchor_uses_ordinary_budget(self):
        alias = self.root / 'evidence-alias'; alias.symlink_to(self.directory, target_is_directory=True)
        observed, enumerations = self.missing_inventories(
            ['.confidence/runs/.vanished.json.tmp-abcd012_'], directory=alias)
        self.assertIsNone(observed)
        self.assertEqual(enumerations, 2)

    def test_fresh_inventory_retains_tracked_symlink_and_special_source_rules(self):
        baseline = self.fingerprint()
        path = self.runs / '.surviving.json.tmp-abcd012_'
        for kind in ('tracked', 'symlink', 'special'):
            if kind == 'special' and not hasattr(os, 'mkfifo'):
                continue
            with self.subTest(kind=kind):
                original = core.subprocess.run; enumerations = []
                def replace_after_first_inventory(argv, *args, **kwargs):
                    if '--stage' in argv and enumerations:
                        if kind == 'symlink':
                            path.symlink_to(self.root / 'source')
                        else:
                            path.write_text('source under staging name')
                            original(['git', '-C', str(self.root), 'add', str(path)], check=True)
                            if kind == 'special':
                                path.unlink(); os.mkfifo(path)
                    result = original(argv, *args, **kwargs)
                    if '--others' in argv:
                        enumerations.append(argv)
                        if len(enumerations) == 1:
                            result.stdout += b'.confidence/runs/.vanished.json.tmp-abcd012_\0'
                    return result
                try:
                    with patch.object(core.subprocess, 'run', replace_after_first_inventory):
                        observed = self.fingerprint()
                    self.assertEqual(len(enumerations), 2)
                    if kind == 'special':
                        self.assertIsNone(observed)
                    else:
                        self.assertIsNotNone(observed)
                        self.assertNotEqual(observed, baseline)
                finally:
                    subprocess.run(['git', '-C', str(self.root), 'rm', '--cached', '-f', '--ignore-unmatch', str(path)], check=True, capture_output=True)
                    path.unlink(missing_ok=True)


if __name__ == '__main__': unittest.main()
