"""Evidence exclusions cannot hide source, and nested Git requires explicit scope."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/confidence.py'
SPEC = importlib.util.spec_from_file_location('confidence_evidence_subtree', SCRIPT)
confidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(confidence)


class EvidenceSubtreeTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='confidence-subtree-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.git(self.root, 'init', '-q')
        (self.root / 'README.md').write_text('fixture')
        self.commit(self.root)

    def git(self, root, *args):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)

    def commit(self, root):
        self.git(root, 'add', '.')
        self.git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')

    def capture(self, directory, code):
        result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--id', 'check', '--directory', str(directory), '--cwd', str(self.root), '--', sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record, errors = confidence.validate_run_record(directory, 'check')
        self.assertEqual(errors, [])
        return record

    def test_tracked_source_subtree_mutation_is_rejected(self):
        source = self.root / 'src/value.txt'
        source.parent.mkdir()
        source.write_text('good')
        self.commit(self.root)
        record = self.capture(source.parent, "from pathlib import Path; p=Path('src/value.txt'); assert p.read_text()=='good'; p.write_text('broken')")
        self.assertTrue(any('during execution' in e for e in confidence.validate_supporting_workspace(record, source.parent)))

    def test_tracked_reserved_filename_is_not_hidden(self):
        directory = self.root / 'src'
        directory.mkdir()
        source = directory / 'report.json'
        source.write_text('{"rule": "good"}')
        self.commit(self.root)
        before = confidence.git_workspace_fingerprint(self.root, directory)
        source.write_text('{"rule": "broken"}')
        after = confidence.git_workspace_fingerprint(self.root, directory)
        self.assertIsNotNone(before)
        self.assertNotEqual(before, after)

    def test_untracked_non_evidence_source_inside_directory_is_not_hidden(self):
        directory = self.root / '.confidence'
        directory.mkdir()
        source = directory / 'rules.py'
        source.write_text('good')
        before = confidence.git_workspace_fingerprint(self.root, directory)
        source.write_text('broken')
        self.assertNotEqual(before, confidence.git_workspace_fingerprint(self.root, directory))

    def test_generated_evidence_does_not_stale_normal_or_literal_directory(self):
        for name in ('.confidence', 'evidence[1]'):
            with self.subTest(name=name):
                directory = self.root / name
                directory.mkdir()
                before = confidence.git_workspace_fingerprint(self.root, directory)
                for relative in ('contract.json', 'report.json', 'REPORT.md', 'runs/check.json', 'runs/check.log', 'telemetry/events.jsonl', 'telemetry/installation-id'):
                    path = directory / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('generated')
                self.assertEqual(before, confidence.git_workspace_fingerprint(self.root, directory))

    def test_nested_git_dependency_is_unknown_and_not_current_code_proof(self):
        component = self.root / 'component'
        component.mkdir()
        self.git(component, 'init', '-q')
        (component / 'value.txt').write_text('good')
        self.commit(component)
        directory = self.root / '.confidence'
        record = self.capture(directory, "from pathlib import Path; p=Path('component/value.txt'); assert p.read_text()=='good'; p.write_text('broken')")
        self.assertIsNone(record['workspace_start'])
        self.assertIsNone(record['workspace'])
        self.assertTrue(any('unknown' in e for e in confidence.validate_supporting_workspace(record, directory)))

if __name__ == '__main__':
    unittest.main()
