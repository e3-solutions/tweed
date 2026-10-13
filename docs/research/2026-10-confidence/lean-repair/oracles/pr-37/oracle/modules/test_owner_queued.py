"""Real native driver receives offline JSON lines; assertions use phase outcomes."""
import json
import unittest
from unittest import mock
import bonaparte_native as NATIVE
from tests.test_bonaparte import AppServerFixture, ROOT, RUNNER, SESSION_ID, receipt

QUESTION = 'Soft phase budget reached. Resume this token with Continue.'

class QueuedWrapup(unittest.TestCase):
    def execute(self, *, item=None, question=QUESTION, summary='Proof for the next slice remains unverified.', state='needs-input'):
        final = receipt(state)
        final.update(question=question, summary=summary)
        def handler(fixture, message, output):
            method, request_id = message.get('method'), message.get('id')
            if method == 'turn/start':
                # Acknowledge the live turn, then wait for real budget expiry.
                fixture._emit(output, {'id': request_id, 'result': {'turn': {'id': 'turn-1'}}})
                return True
            if method == 'turn/steer':
                fixture._emit(output, {'id': request_id, 'result': {'turnId': 'turn-1'}})
                if item is not None:
                    fixture._emit(output, {'method': 'item/started', 'params': {
                        'threadId': SESSION_ID, 'turnId': 'turn-1', 'item': item}})
                fixture._emit(output, {'method': 'item/completed', 'params': {
                    'threadId': SESSION_ID, 'turnId': 'turn-1', 'item': {
                        'id': 'final', 'type': 'agentMessage', 'status': 'completed', 'text': json.dumps(final)}}})
                fixture._emit(output, {'method': 'turn/completed', 'params': {
                    'threadId': SESSION_ID, 'turn': {'id': 'turn-1', 'status': 'completed'}}})
                return True
            return False
        server = AppServerFixture(final, handler=handler)
        with (mock.patch.object(NATIVE, 'find_codex', return_value='/offline/codex'),
              mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=server)):
            result = RUNNER.run_phase(ROOT, 'rca', 'Continue.', SESSION_ID, soft_phase_budget_seconds=0.005)
        self.assertEqual(sum(m.get('method') == 'turn/steer' for m in server.requests), 1)
        self.assertIsNotNone(server.process.poll(), 'Successful wrap-up left the provider process running')
        server.process.wait.assert_called()
        return result

    def test_queued_activity_after_ack_keeps_valid_continuation(self):
        for item in ({'type': 'commandExecution'}, {'type': 'fileChange'},
                     {'type': 'collabAgentToolCall', 'tool': 'spawnAgent'},
                     {'type': 'subAgentActivity', 'kind': 'started', 'agentThreadId': 'child-offline'}):
            with self.subTest(item=item):
                result = self.execute(item=item)
                self.assertEqual(result['state'], 'needs-input')
                self.assertEqual(result['question'], QUESTION)
                self.assertEqual(result['resume_session_id'], SESSION_ID)
                self.assertIn('unverified', result['summary'])

    def test_no_queued_activity_and_clarification_remain_valid(self):
        result = self.execute()
        self.assertEqual(result['state'], 'needs-input')
        result = self.execute(item={'type': 'webSearch'}, question='Clarification required: Choose target environment.')
        self.assertEqual(result['question'], 'Clarification required: Choose target environment.')

    def test_queued_activity_cannot_make_invalid_receipt_valid(self):
        for changes in ({'question': 'Continue maybe?'}, {'summary': 'All proof completed.'},
                        {'state': 'completed', 'question': None}):
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError, msg='Malformed wrap-up was accepted'):
                    self.execute(item={'type': 'agentMessage'}, **changes)
