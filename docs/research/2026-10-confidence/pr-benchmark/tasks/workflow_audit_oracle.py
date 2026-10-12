"""Retrospective public run_phase routing audit; independent of filter location.

Exercise actual AppServerPhaseDriver construction and run_phase against a real
line-oriented deterministic native-process fixture. No direct calls or asserted
return shapes of observe_notification, nor new implementation-private fields.
"""
import json
import unittest
from unittest import mock
import bonaparte_native as native
from tests.test_bonaparte import AppServerFixture, ROOT, RUNNER, SESSION_ID, SUBAGENT_ID, receipt


class WorkflowRoutingAudit(unittest.TestCase):
    def run_routing_case(self, completion_thread, completion_turn, *, legacy=False):
        expected = receipt()
        expected['summary'] = 'Coordinator receipt survives the routing matrix.'

        def handler(fixture, message, output):
            if message.get('method') != 'turn/start':
                return False
            fixture._emit(output, {'id': message['id'], 'result': {'turn': {'id': 'turn-1'}}})
            if completion_thread != SESSION_ID or completion_turn != 'turn-1':
                # A foreign terminal arrives before the legitimate final receipt.
                fixture._emit(output, {'method': 'turn/completed', 'params': {
                    'threadId': completion_thread,
                    'turn': {'id': completion_turn, 'status': 'completed'}}})
            fixture._emit(output, {'method': 'item/completed', 'params': {
                'threadId': SESSION_ID, 'turnId': 'turn-1', 'item': {
                    'type': 'agentMessage', 'text': json.dumps(expected), 'status': 'completed'}}})
            params = {'turn': {'id': 'turn-1', 'status': 'completed'}}
            if not legacy:
                params['threadId'] = SESSION_ID
            fixture._emit(output, {'method': 'turn/completed', 'params': params})
            return True

        server = AppServerFixture(expected, handler=handler)
        with (mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
              mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=server)):
            observed = RUNNER.run_phase(ROOT, 'rca', 'Continue.', SESSION_ID)
        for field in expected:
            self.assertEqual(observed[field], expected[field], 'Coordinator public receipt field changed: ' + field)
        self.assertEqual(observed['resume_session_id'], None)
        self.assertIsNotNone(server.process.poll(), 'Native coordinator process was not stopped')
        self.assertTrue(server.process.stdin.closed, 'Native process input remained open')

    def test_wrong_thread_same_turn_cannot_finish_phase(self):
        self.run_routing_case(SUBAGENT_ID, 'turn-1')

    def test_same_thread_wrong_turn_cannot_finish_phase(self):
        self.run_routing_case(SESSION_ID, 'foreign-turn')

    def test_wrong_thread_wrong_turn_cannot_finish_phase(self):
        self.run_routing_case(SUBAGENT_ID, 'foreign-turn')

    def test_matching_thread_turn_finishes_phase(self):
        self.run_routing_case(SESSION_ID, 'turn-1')

    def test_legacy_absent_thread_matching_turn_finishes_phase(self):
        self.run_routing_case(SESSION_ID, 'turn-1', legacy=True)

    def test_foreign_messages_cannot_replace_coordinator_receipt(self):
        expected = receipt()
        expected['summary'] = 'The actual coordinator receipt.'

        def handler(fixture, message, output):
            if message.get('method') != 'turn/start':
                return False
            fixture._emit(output, {'id': message['id'], 'result': {'turn': {'id': 'turn-1'}}})
            for thread, turn, summary in [(SESSION_ID, 'turn-1', expected['summary']),
                                          (SUBAGENT_ID, 'turn-1', 'Wrong thread receipt.'),
                                          (SESSION_ID, 'foreign-turn', 'Wrong turn receipt.'),
                                          (SUBAGENT_ID, 'foreign-turn', 'Both foreign receipt.')]:
                payload = {**expected, 'summary': summary}
                fixture._emit(output, {'method': 'item/completed', 'params': {
                    'threadId': thread, 'turnId': turn, 'item': {
                        'type': 'agentMessage', 'text': json.dumps(payload), 'status': 'completed'}}})
            fixture._emit(output, {'method': 'turn/completed', 'params': {
                'threadId': SESSION_ID, 'turn': {'id': 'turn-1', 'status': 'completed'}}})
            return True

        server = AppServerFixture(expected, handler=handler)
        with (mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
              mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=server)):
            observed = RUNNER.run_phase(ROOT, 'rca', 'Continue.', SESSION_ID)
        for field in expected:
            self.assertEqual(observed[field], expected[field])
        self.assertIsNotNone(server.process.poll())
        self.assertTrue(server.process.stdin.closed)

    def test_malformed_active_transport_stops_process(self):
        def malformed(fixture, message, output):
            if message.get('method') != 'turn/start':
                return False
            fixture._emit(output, {'id': message['id'], 'result': {'turn': {'id': 'turn-1'}}})
            output.put('not-json\n')
            return True
        server = AppServerFixture(handler=malformed)
        with (mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
              mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=server)):
            with self.assertRaises(RuntimeError):
                RUNNER.run_phase(ROOT, 'rca', 'Continue.', SESSION_ID)
        self.assertIsNotNone(server.process.poll(), 'Failed native coordinator process was not stopped')
        self.assertTrue(server.process.stdin.closed, 'Failed process input remained open')
