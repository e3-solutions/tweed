"""Native lifecycle observations through real driver construction and phase flow."""
import json
import unittest
from unittest import mock
import bonaparte_native as native
from tests.test_bonaparte import AppServerFixture, ROOT, RUNNER, SESSION_ID, linear_issue, receipt


class NativeLifecycleEdges(unittest.TestCase):
    def phase(self, fail_child=False):
        def handler(fixture, message, output):
            method = message.get('method')
            if method == 'thread/start':
                fixture._emit(output, {'method': 'thread/started', 'params': {'thread': {'id': SESSION_ID}}})
            if method == 'turn/start':
                for child in ['child-b', 'child-a']:
                    fixture._emit(output, {'method': 'thread/started', 'params': {'thread': {'id': child}}})
            if method in ['thread/metadata/update', 'thread/archive', 'thread/unsubscribe']:
                value = {'id': message['id'], 'result': {}}
                if fail_child and method == 'thread/metadata/update' and message['params']['threadId'].startswith('child-'):
                    value = {'id': message['id'], 'error': {'message': 'child metadata rejected'}}
                fixture._emit(output, value)
                return True
            return False
        server = AppServerFixture(receipt(), handler=handler)
        with (mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
              mock.patch.object(RUNNER, 'call_linear', return_value=(linear_issue(), [])),
              mock.patch.object(RUNNER, 'trusted_git_target', return_value=('o/r', 'main'), create=True),
              mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=server)):
            if fail_child:
                with self.assertRaisesRegex(RuntimeError, 'child metadata rejected'):
                    RUNNER.run_phase(ROOT, 'rca', 'COR-1')
            else:
                result = RUNNER.run_phase(ROOT, 'rca', 'COR-1')
                self.assertEqual(result['state'], 'completed')
        return server

    def test_terminal_phase_updates_owned_children_and_archives_root(self):
        server = self.phase()
        targets = {message['params']['threadId'] for message in server.requests
                   if message['method'] == 'thread/metadata/update' and message['params']['threadId'] != SESSION_ID}
        self.assertEqual(targets, {'child-a', 'child-b'})
        archived = [message['params']['threadId'] for message in server.requests if message['method'] == 'thread/archive']
        self.assertEqual(archived, [SESSION_ID])
        self.assertIsNotNone(server.process.poll())

    def test_child_cleanup_failure_still_attempts_root_archive_and_reaps(self):
        server = self.phase(fail_child=True)
        archived = [message['params']['threadId'] for message in server.requests if message['method'] == 'thread/archive']
        self.assertEqual(archived, [SESSION_ID])
        self.assertIsNotNone(server.process.poll())
