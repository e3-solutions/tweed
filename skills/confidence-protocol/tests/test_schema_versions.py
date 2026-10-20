"""Malformed JSON schema versions must be ordinary validation failures."""
from pathlib import Path
import tempfile
import unittest

from support import load_confidence, run_cli, write_documents

confidence = load_confidence('confidence_schema_versions')


class SchemaVersionTest(unittest.TestCase):
    def test_non_integer_versions_exit_one(self):
        for filename, versions in (('contract.json', (True, 1.0)),
                                   ('report.json', (3.0,))):
            for version in versions:
                with self.subTest(filename=filename, version=version), tempfile.TemporaryDirectory() as name:
                    directory = Path(name)
                    write_documents(confidence, directory)
                    # Avoid requiring a capture for these structural-only checks.
                    report = confidence.read_json(directory / 'report.json')
                    report['evidence'][0].update(status='partial', run_ids=[])
                    confidence.write_json(directory / 'report.json', report)
                    document = confidence.read_json(directory / filename)
                    document['version'] = version
                    confidence.write_json(directory / filename, document)
                    result = run_cli('validate', '--directory', str(directory))
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(filename.split('.')[0] + '.version', result.stderr)
