#!/usr/bin/env python3
"""Post-hoc public-run_phase counterexample; never changes primary study grades.

Run once per restored candidate tree containing original test fixture support.
The native process is mocked: no provider call, credentials or network access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest import mock


def probe(source, event_turn='old-turn'):
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    from tests.test_bonaparte import AppServerFixture, RUNNER, SESSION_ID, receipt
    import bonaparte_native as native
    expected = receipt('needs-input')
    expected['summary'] = 'Active coordinator receipt; remaining proof is unverified.'
    expected['question'] = RUNNER.SOFT_BUDGET_CONTINUE_QUESTION

    def handler(fixture, message, output):
        if message.get('method') == 'turn/start':
            fixture._emit(output, {'id': message['id'], 'result': {'turn': {'id': 'turn-1'}}})
            return True
        if message.get('method') != 'turn/steer':
            return False
        fixture._emit(output, {'id': message['id'], 'result': {'turnId': 'turn-1'}})
        fixture._emit(output, {'method': 'item/started', 'params': {
            'threadId': SESSION_ID, 'turnId': event_turn,
            'item': {'id': 'stale-work', 'type': 'commandExecution', 'command': 'echo stale'}}})
        fixture._emit(output, {'method': 'item/completed', 'params': {
            'threadId': SESSION_ID, 'turnId': 'turn-1', 'item': {
                'id': 'actual-receipt', 'type': 'agentMessage',
                'text': json.dumps(expected), 'status': 'completed'}}})
        fixture._emit(output, {'method': 'turn/completed', 'params': {
            'threadId': SESSION_ID, 'turn': {'id': 'turn-1', 'status': 'completed'}}})
        return True

    fixture = AppServerFixture(expected, handler=handler)
    verdict = {'case': 'same_thread_work_after_steer', 'event_turn': event_turn,
               'primary_grade_unchanged': True,
               'source_files': {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                for name in ('bonaparte', 'bonaparte_native.py')}}
    with (mock.patch.object(native, 'find_codex', return_value='/bin/codex'),
          mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=fixture)):
        try:
            actual = RUNNER.run_phase(source, 'rca', 'Continue.', SESSION_ID,
                                      soft_phase_budget_seconds=0.01)
            verdict.update(accepted_active_receipt=all(actual.get(key) == value for key, value in expected.items()),
                           error=None)
        except Exception as error:
            verdict.update(accepted_active_receipt=False, error=str(error), error_type=type(error).__name__)
    verdict['steer_exercised'] = any(row.get('method') == 'turn/steer' for row in fixture.requests)
    verdict['process_closed'] = fixture.process is not None and fixture.process.poll() is not None and fixture.process.stdin.closed
    return verdict


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--event-turn', choices=['old-turn', 'turn-1'], default='old-turn')
    args = parser.parse_args()
    print(json.dumps(probe(args.source, args.event_turn), sort_keys=True))
