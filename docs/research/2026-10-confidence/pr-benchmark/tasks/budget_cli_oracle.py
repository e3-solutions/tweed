"""Held-out user-facing budget behavior; no representation-constant assumptions."""
import io
import json
import os
import sys
import unittest
from unittest import mock
from tests.test_bonaparte import ROOT, RUNNER, receipt


class BudgetCLIEdges(unittest.TestCase):
    def invoke(self, options, environment):
        output = io.StringIO()
        with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), *options, 'RCA', 'COR-1']),
              mock.patch.dict(os.environ, environment, clear=True),
              mock.patch.object(RUNNER, 'run_and_checkpoint', return_value=(receipt(), 0)) as run,
              mock.patch.object(sys, 'stdout', output), mock.patch.object(sys, 'stderr', io.StringIO())):
            status = RUNNER.main()
        return status, run, json.loads(output.getvalue())

    def test_disabled_flag_and_environment_deliver_disabled_execution(self):
        for options, environment in [(['--no-soft-phase-budget'], {}), ([], {'BONAPARTE_SOFT_PHASE_BUDGET': 'off'})]:
            with self.subTest(options=options, environment=environment):
                status, run, result = self.invoke(options, environment)
                self.assertEqual(status, 0)
                run.assert_called_once()
                self.assertIsNone(run.call_args.args[-1])
                self.assertEqual(result['state'], 'completed')

    def test_explicit_numeric_budget_overrides_environment(self):
        status, run, result = self.invoke(['--soft-phase-budget-seconds', '12.5'], {'BONAPARTE_SOFT_PHASE_BUDGET': 'off'})
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args.args[-1], 12.5)
        self.assertEqual(result['state'], 'completed')

    def test_invalid_budgets_never_start_execution(self):
        for value in ['0', '-1', 'nan', 'inf', 'not-seconds']:
            with self.subTest(value=value):
                status, run, result = self.invoke(['--soft-phase-budget-seconds', value], {})
                self.assertEqual(status, 1)
                run.assert_not_called()
                self.assertEqual(result['state'], 'failed')
