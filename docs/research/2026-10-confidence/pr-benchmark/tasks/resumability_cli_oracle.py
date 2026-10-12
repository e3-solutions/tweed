"""CLI receipts and durable continuation, independent of helper return shapes."""
import io
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from tests.test_bonaparte import ROOT, RUNNER, SESSION_ID, receipt


PHASE_SIGNATURE = inspect.signature(RUNNER.run_phase)


class ResumabilityCLIEdges(unittest.TestCase):
    def invoke(self, argv, effect):
        output = io.StringIO()
        with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), *argv]),
              mock.patch.object(RUNNER, 'run_phase', side_effect=effect),
              mock.patch.object(sys, 'stdout', output), mock.patch.object(sys, 'stderr', io.StringIO())):
            code = RUNNER.main()
        return code, json.loads(output.getvalue())

    def test_soft_guard_failure_has_durable_cli_continuation(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'BONAPARTE_HOME': home}):
            def fails(*args, **kwargs):
                PHASE_SIGNATURE.bind_partial(*args, **kwargs).arguments['observation'].update(session_id=SESSION_ID, soft_budget_steered=True)
                raise RuntimeError('soft-budget guard observed root work after steer acknowledgement')
            code, result = self.invoke(['RCA', 'COR-1'], fails)
            self.assertEqual(code, 1)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result.get('resume_token'), SESSION_ID)
            self.assertTrue(result.get('question'))
            stored = RUNNER.read_checkpoint(SESSION_ID, active_only=True)
            self.assertEqual(stored['status'], 'waiting-input')
            delivered = []
            def resumes(*args, **kwargs):
                delivered.append(PHASE_SIGNATURE.bind_partial(*args, **kwargs).arguments)
                return receipt('completed')
            code, result = self.invoke(['resume', SESSION_ID, 'Continue'], resumes)
            self.assertEqual(code, 0)
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(delivered[0]['resume_session_id'], SESSION_ID)
            self.assertEqual(delivered[0]['phase_input'], 'Continue')

    def test_interrupt_has_exit130_receipt_and_durable_continuation(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'BONAPARTE_HOME': home}):
            def interrupts(*args, **kwargs):
                PHASE_SIGNATURE.bind_partial(*args, **kwargs).arguments['observation'].update(session_id=SESSION_ID, soft_budget_steered=True)
                raise KeyboardInterrupt
            code, result = self.invoke(['RCA', 'COR-1'], interrupts)
            self.assertEqual(code, 130)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result.get('resume_token'), SESSION_ID)
            self.assertEqual(RUNNER.read_checkpoint(SESSION_ID, active_only=True)['status'], 'waiting-input')

    def test_unrelated_transport_failure_does_not_claim_continuation(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'BONAPARTE_HOME': home}):
            def fails(*args, **kwargs):
                PHASE_SIGNATURE.bind_partial(*args, **kwargs).arguments['observation'].update(session_id=SESSION_ID)
                raise RuntimeError('timed out during turn/start')
            code, result = self.invoke(['RCA', 'COR-1'], fails)
            self.assertEqual(code, 1)
            self.assertEqual(result['state'], 'failed')
            self.assertFalse(result.get('resume_token'))
            self.assertEqual(list(Path(home).rglob('checkpoints/*.json')), [])
