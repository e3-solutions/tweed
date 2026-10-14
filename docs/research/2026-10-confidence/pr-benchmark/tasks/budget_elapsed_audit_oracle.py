"""Prospective disabled-resume deadline crossing through actual CLI/driver flow."""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import bonaparte_native as native
from tests.test_bonaparte import AppServerFixture, ROOT, RUNNER, SESSION_ID, receipt
from tests.test_budget_resume_audit import provider_only_popen


class DisabledResumeElapsedAudit(unittest.TestCase):
    def test_disabled_resume_waits_beyond_prior_budget_without_steering(self):
        previous_budget = 0.001
        provider_delay = 0.05
        delivered = threading.Event()
        expected = receipt()
        expected['summary'] = 'Provider finished after the former soft deadline.'

        def handler(fixture, message, output):
            if message.get('method') != 'turn/start':
                return False
            fixture._emit(output, {'id': message['id'], 'result': {'turn': {'id': 'turn-1'}}})
            def finish_after_old_deadline():
                time.sleep(provider_delay)
                fixture._emit(output, {'method': 'item/completed', 'params': {
                    'threadId': SESSION_ID, 'turnId': 'turn-1', 'item': {
                        'type': 'agentMessage', 'text': json.dumps(expected), 'status': 'completed'}}})
                fixture._emit(output, {'method': 'turn/completed', 'params': {
                    'threadId': SESSION_ID, 'turn': {'id': 'turn-1', 'status': 'completed'}}})
                delivered.set()
            threading.Thread(target=finish_after_old_deadline, daemon=True).start()
            return True

        with tempfile.TemporaryDirectory() as home:
            output = io.StringIO()
            server = AppServerFixture(expected, handler=handler)
            with mock.patch.dict(os.environ, {'BONAPARTE_HOME': home}, clear=False):
                os.environ.pop('BONAPARTE_SOFT_PHASE_BUDGET', None)
                os.environ.pop(RUNNER.PHASE_CHILD_ENV, None)
                RUNNER.new_question_checkpoint(
                    ROOT, 'rca', receipt('needs-input'), SESSION_ID, None, 'medium',
                    {'session_id': SESSION_ID}, RUNNER.capture_git_state(ROOT), previous_budget)
                with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT),
                                                     '--no-soft-phase-budget', 'resume', SESSION_ID, 'Production']),
                      mock.patch.object(sys, 'stdout', output), mock.patch.object(sys, 'stderr', io.StringIO()),
                      mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
                      mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=provider_only_popen(server))):
                    status = RUNNER.main()
                self.assertEqual(status, 0, output.getvalue())
                self.assertTrue(delivered.wait(0.5), 'Provider did not finish the delayed fixture')
                self.assertEqual(json.loads(output.getvalue())['summary'], expected['summary'])
                self.assertEqual(json.loads(output.getvalue())['state'], 'completed')
                self.assertIsNone(RUNNER.read_checkpoint(SESSION_ID)['soft_phase_budget_seconds'])
            self.assertNotIn('turn/steer', [message.get('method') for message in server.requests])
            self.assertIsNotNone(server.process.poll())
