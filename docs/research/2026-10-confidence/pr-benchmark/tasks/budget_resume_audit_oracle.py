"""Retrospective CLI budget audit; no parse-token-to-helper shortcut.

Invoke main with the real public resume CLI, actual run_phase/native driver and
checkpoint storage, backed only by deterministic provider transport fixtures.
No disable constants, parse return representations or helper call shapes tested.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
import bonaparte_native as native
from tests.test_bonaparte import AppServerFixture, ROOT, RUNNER, SESSION_ID, linear_issue, receipt


def provider_only_popen(server):
    original = RUNNER.subprocess.Popen
    def dispatch(command, *arguments, **keywords):
        if isinstance(command, (list, tuple)) and len(command) > 1 and command[1] == 'app-server':
            return server(command, **keywords)
        return original(command, *arguments, **keywords)
    return dispatch


class BudgetResumeAudit(unittest.TestCase):
    def invoke_resume(self, saved_budget, options=()):
        with tempfile.TemporaryDirectory() as home:
            output = io.StringIO()
            with mock.patch.dict(os.environ, {'BONAPARTE_HOME': home}, clear=False):
                os.environ.pop('BONAPARTE_SOFT_PHASE_BUDGET', None)
                os.environ.pop(RUNNER.PHASE_CHILD_ENV, None)
                checkpoint = RUNNER.new_question_checkpoint(
                    ROOT, 'rca', receipt('needs-input'), SESSION_ID, None, 'medium',
                    {'session_id': SESSION_ID}, RUNNER.capture_git_state(ROOT), saved_budget)
                # The durable checkpoint is written by its existing constructor.
                expected = receipt()
                server = AppServerFixture(expected)
                with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), *options,
                                                     'resume', SESSION_ID, 'Production']),
                      mock.patch.object(sys, 'stdout', output),
                      mock.patch.object(sys, 'stderr', io.StringIO()),
                      mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
                      mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=provider_only_popen(server))):
                    status = RUNNER.main()
                persisted = RUNNER.read_checkpoint(SESSION_ID)
            self.assertEqual(status, 0, output.getvalue())
            result = json.loads(output.getvalue())
            for key in expected:
                self.assertEqual(result[key], expected[key])
            resume = [m for m in server.requests if m.get('method') == 'thread/resume']
            self.assertEqual(len(resume), 1)
            self.assertEqual(resume[0]['params']['threadId'], SESSION_ID)
            self.assertNotIn('turn/steer', [m.get('method') for m in server.requests])
            self.assertIsNotNone(server.process.poll())
            return persisted['soft_phase_budget_seconds']

    def test_explicit_resume_disable_replaces_saved_numeric_budget(self):
        self.assertIsNone(self.invoke_resume(45.0, ['--no-soft-phase-budget']))

    def test_explicit_resume_disable_preserves_saved_disabled_budget(self):
        self.assertIsNone(self.invoke_resume(None, ['--no-soft-phase-budget']))

    def test_resume_without_override_preserves_saved_disabled_budget(self):
        self.assertIsNone(self.invoke_resume(None))

    def test_numeric_resume_override_replaces_saved_disabled_budget(self):
        self.assertEqual(self.invoke_resume(None, ['--soft-phase-budget-seconds', '12.5']), 12.5)

    def test_resume_without_override_preserves_saved_numeric_budget(self):
        self.assertEqual(self.invoke_resume(45.0), 45.0)

    def assert_rejected_before_provider(self, options):
        with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), *options,
                                             'resume', SESSION_ID, 'Production']),
              mock.patch.object(sys, 'stdout', io.StringIO()),
              mock.patch.object(sys, 'stderr', io.StringIO()),
              mock.patch.object(RUNNER.subprocess, 'Popen') as provider):
            try:
                status = RUNNER.main()
            except SystemExit as error:
                status = error.code
        self.assertNotEqual(status, 0)
        provider.assert_not_called()

    def test_invalid_numeric_resume_inputs_never_start_provider(self):
        for value in ['0', '-1', 'nan', 'inf', 'not-seconds']:
            with self.subTest(value=value):
                self.assert_rejected_before_provider(['--soft-phase-budget-seconds', value])

    def test_mutually_exclusive_flags_never_start_provider(self):
        self.assert_rejected_before_provider(['--no-soft-phase-budget', '--soft-phase-budget-seconds', '12.5'])

    def test_environment_disabled_default_runs_real_phase_and_persists_disabled(self):
        with tempfile.TemporaryDirectory() as home:
            output = io.StringIO()
            server = AppServerFixture(receipt('needs-input'))
            with (mock.patch.dict(os.environ, {'BONAPARTE_HOME': home, 'BONAPARTE_SOFT_PHASE_BUDGET': 'off'}, clear=False),
                  mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), 'RCA', 'COR-1']),
                  mock.patch.object(sys, 'stdout', output), mock.patch.object(sys, 'stderr', io.StringIO()),
                  mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
                  mock.patch.object(RUNNER, 'call_linear', return_value=(linear_issue(), [])),
                  mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=provider_only_popen(server))):
                os.environ.pop(RUNNER.PHASE_CHILD_ENV, None)
                status = RUNNER.main()
                persisted = RUNNER.read_checkpoint(SESSION_ID)
            self.assertEqual(status, 0, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())['state'], 'needs-input')
            self.assertIsNone(persisted['soft_phase_budget_seconds'])
            self.assertNotIn('turn/steer', [m.get('method') for m in server.requests])
            self.assertIsNotNone(server.process.poll())
