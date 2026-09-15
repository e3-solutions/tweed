"""Command observations and partial reports are useful without source certification."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_confidence as fixtures

SCRIPT = fixtures.SCRIPT
confidence = fixtures.confidence


class ReportingScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / '.confidence'
        fixture = fixtures.ConfidenceTest('test_valid_evidence_passes')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.valid_files(self.directory)
        result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--id', 'calculation',
            '--cwd', str(self.root), '--directory', str(self.directory), '--',
            sys.executable, '-c', 'assert 2 + 2 == 4'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.contract = confidence.read_json(self.directory / 'contract.json')
        self.report = confidence.read_json(self.directory / 'report.json')
        self.report['evidence'][0]['run_ids'] = ['calculation']

    def save(self):
        confidence.write_json(self.directory / 'contract.json', self.contract)
        confidence.write_json(self.directory / 'report.json', self.report)

    def call(self, action, *args):
        return subprocess.run([sys.executable, str(SCRIPT), action, '--directory', str(self.directory), *args], capture_output=True, text=True)

    def test_partial_unbound_evidence_renders_but_cannot_complete(self):
        self.report['evidence'][0].update(status='partial', details='Calculation succeeded; source correctness was not checked.')
        self.save()
        self.assertEqual(self.call('validate').returncode, 0)
        self.assertEqual(self.call('render').returncode, 0)
        self.assertNotEqual(self.call('validate', '--require-complete').returncode, 0)
        self.assertIn('partial', (self.directory / 'REPORT.md').read_text())

    def test_noncode_research_can_finish_without_claiming_current_code(self):
        self.contract['task']['type'] = 'research'
        self.contract['proof_obligations'][0].update(claim='Two plus two is four.', verification='Run the arithmetic assertion.')
        self.report['outcome'] = 'The arithmetic assertion passed.'
        self.report['evidence'][0]['details'] = 'Captured arithmetic, not current-code verification.'
        self.save()
        result = self.call('validate', '--require-complete')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('does not certify current code', result.stdout)
        self.assertEqual(self.call('render').returncode, 0)
        self.assertIn('does not certify current code', (self.directory / 'REPORT.md').read_text())

    def test_code_pass_still_requires_binding(self):
        self.save()
        result = self.call('validate', '--require-complete')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('binding is unknown', result.stderr)

    def test_legacy_partial_record_remains_renderable(self):
        path = self.directory / 'runs/calculation.json'
        record = confidence.read_json(path)
        record['version'] = 1
        record.pop('workspace_start')
        confidence.write_json(path, record)
        self.report['evidence'][0].update(status='partial', details='Historical command evidence; source binding not established.')
        self.save()
        self.assertEqual(self.call('render').returncode, 0)
        self.assertNotEqual(self.call('validate', '--require-complete').returncode, 0)


if __name__ == '__main__':
    unittest.main()
