"""Qualification verifier controls; no hosted calls or historical task fixtures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pipeline_controls_test', HERE / 'v2_controls.py')
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)


class PipelineVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        snapshot = self.output / 'result_snapshot'
        snapshot.mkdir()
        (snapshot / 'toy.py').write_text('def answer():\n    return 2\n')
        self.receipt = dict(stages=[], wall_seconds=30, harness_invalid=False)
        for role, assigned in [('test_designer', 'opus'), ('main_implementation', 'astra'),
                               ('adversarial_reviewer', 'opus'), ('main_repair', 'astra')]:
            directory = self.output / role
            directory.mkdir()
            events = [{'name': name, 'ok': True} for name in ('read_file', 'run_tests')]
            if role == 'main_implementation':
                events.append({'name': 'confidence', 'ok': True})
                (directory / 'captured.command-request.json').write_text(json.dumps(dict(
                    argv=['python3', '-B', '/source/.protocol/scripts/confidence.py', 'run'])))
                (directory / 'captured.command-response.json').write_text('{"exit_code": 0}')
            (directory / 'tool-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            model = 'claude-opus-5-5' if assigned == 'opus' else 'gpt-6-astra'
            self.receipt['stages'].append(dict(role=role, assigned_model=assigned,
                model_requested=model, requested_effort='medium', observed_assistant_models=[model] if assigned == 'opus' else [],
                adapter_qualification={'passed': True}, source_sha256_at_launch='source', source_sha256_after='source',
                process_exit=0, timed_out=False, structured_output={'complete': True, 'summary': 'checks', 'remaining': []}))
        (self.output / 'receipt.json').write_text(json.dumps(self.receipt))
        self.terminal = patch.object(controls.v2.frozen, 'terminal_value', side_effect=lambda s: s['structured_output'])
        self.terminal.start()

    def tearDown(self):
        self.terminal.stop()
        self.temp.cleanup()

    def test_complete_mechanical_pipeline_passes_with_codex_dollars_unknown(self):
        self.receipt['total_cost_usd'] = None
        self.assertTrue(controls.inspect_trial(self.receipt, self.output)['passed'])

    def test_implementation_can_truthfully_retain_the_scheduled_future_review_gap(self):
        self.receipt['stages'][1]['structured_output'] = dict(complete=False, summary='implemented', remaining=['Scheduled adversarial review'])
        self.assertTrue(controls.inspect_trial(self.receipt, self.output)['passed'])

    def test_model_assertions_without_actual_test_are_rejected(self):
        (self.output / 'adversarial_reviewer/tool-events.jsonl').write_text('{"name":"read_file","ok":true}\n')
        self.assertIn('adversarial_reviewer:missing_actual_source_read_or_test',
                      controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_missing_live_claude_inventory_or_unknown_qualification_is_rejected(self):
        self.receipt['stages'][0]['adapter_qualification']['passed'] = None
        self.assertIn('test_designer:inventory_or_transport_unqualified',
                      controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_missing_claude_observed_model_cannot_be_promoted_to_observed(self):
        self.receipt['stages'][0]['observed_assistant_models'] = []
        self.assertIn('test_designer:model_attribution', controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_peer_source_change_is_rejected_even_with_valid_model_terminal(self):
        self.receipt['stages'][2]['source_sha256_after'] = 'drifted'
        self.assertIn('adversarial_reviewer:readonly_source_drift', controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_valid_terminal_cannot_hide_wrong_final_behavior(self):
        (self.output / 'result_snapshot/toy.py').write_text('def answer():\n    return 1\n')
        self.assertIn('final_observable_behavior', controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_failed_capture_command_does_not_prove_successful_source_capture(self):
        (self.output / 'main_implementation/captured.command-response.json').write_text('{"exit_code": 1}')
        self.assertIn('actual_confidence_capture_missing', controls.inspect_trial(self.receipt, self.output)['reasons'])

    def test_remaining_gap_and_overbudget_block_qualification(self):
        self.receipt['stages'][-1]['structured_output']['remaining'] = ['unfinished review']
        self.receipt['wall_seconds'] = 601
        reasons = controls.inspect_trial(self.receipt, self.output)['reasons']
        self.assertIn('main_repair:missing_or_incomplete_terminal', reasons)
        self.assertIn('aggregate_deadline', reasons)


if __name__ == '__main__':
    unittest.main()
