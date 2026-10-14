"""Synthetic guards only. Never read actual intake outcomes or run inference."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
import subprocess

import analyze_intake as a


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


class ClosureTests(unittest.TestCase):
    def fixture(self, root):
        # Source constants are public; no import/call of the inference controller.
        source = (a.HERE / 'intake.py').read_text()
        constants = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(source).body
                     if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ('CASES', 'SCHEMA')}
        base = root / 'private-intake'
        study, review = base / 'intake-study', base / 'intake-review'
        study.mkdir(parents=True)
        files = {}
        for filename, text in [('intake.py', source), ('runner.py', 'synthetic runner'), ('hybrid_process_v2.py', 'synthetic cleanup')]:
            path = root / filename
            path.write_text(text)
            files[str(path)] = a.sha(path)
        policies, paths = {}, {}
        for policy in a.POLICIES:
            names = ['SKILL.md', 'references/intent-flows.md'] + (['references/question-patterns.md'] if policy == 'enhanced' else [])
            policies[policy] = {n: 'Synthetic PRIVATE_NEVER_EXPORT /Users/private/source ' + n for n in names}
            directory = root / 'policies' / policy
            paths[policy] = str(directory)
            for filename, content in policies[policy].items():
                path = directory / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        schedule = [{'case': c, 'policy': p, 'repeat': r} for c in a.CASE_IDS for p in a.POLICIES for r in (1, 2)]
        payload = {'files': files, 'policies': policies, 'cases': constants['CASES'], 'schema': constants['SCHEMA'],
                   'config': {'policies': paths}, 'cli_version': 'synthetic (Claude Code)', 'schedule': schedule}
        write(study / 'registration.json', {'payload': payload, 'sha256': a.digest(payload)})
        write(base / 'intake-config.json', payload['config'])
        previous = base / 'previous-preparation'
        write(previous / 'registration.json', {'payload': {'synthetic': True}, 'sha256': a.digest({'synthetic': True})})
        write(base / 'intake-adoption.json', {'adopted_intake_registration_sha256': a.sha(study / 'registration.json'), 'previous_intake_preparation': str(previous)})
        argv = a.frozen_contract(source, payload)
        questions = {
            'resume-precedence': ['Should explicit numeric on resume override saved?', 'Does omitted resume preserve saved checkpoint?', 'Does environment replace saved checkpoint?'],
            'publish-identity': ['Should publishing update existing identity or create duplicate?', 'Should multiple conflicting publish identity block?', 'Use latest complete review or newer incomplete review?'],
            'notification-ownership': ['Should legacy missing threadId match active turn?', 'Should child progress remain visible?', 'Should active coordinator thread and turn establish completion?'],
        }
        results, packets, mapping, judgments = [], [], {}, []
        for anonymous_number, spec in enumerate(schedule, 1):
            case = next(c for c in payload['cases'] if c['id'] == spec['case'])
            directory = study / a.name(spec)
            write(directory / 'started.json', {'spec': spec, 'time': 1.0})
            history = []
            for index in (1, 2):
                value = {'questions': questions[case['id']] if index == 1 else [],
                         'settled': ['PRIVATE_NEVER_EXPORT source fact ' + a.name(spec)] if index == 1 else [d['answer'] for d in case['decisions']],
                         'ready': index == 2, 'missing': ['private choices'] if index == 1 else []}
                prompt = 'Policy instructions:\n' + json.dumps(policies[spec['policy']]) + '\nUser request:\n' + case['request'] + '\nKnown context:\n' + case['known'] + '\nAsk concise neutral questions about decisions; source facts above need no user lookup. Return settled choices and missing choices, not code. A later scripted user message answers only recognized questions. Never treat silence as consent.\nConversation so far:\n' + json.dumps(history)
                round_dir = directory / ('round-' + str(index))
                request = {'argv': argv, 'prompt': prompt, 'model_requested': a.MODEL, 'effort': 'medium', 'timeout_seconds': 120}
                write(round_dir / 'request.json', request)
                (round_dir / 'input.txt').write_text(prompt)
                init = {'type': 'system', 'subtype': 'init', 'model': a.MODEL, 'tools': ['StructuredOutput'], 'mcp_servers': [], 'permissionMode': 'dontAsk', 'claude_code_version': 'synthetic'}
                terminal = {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': value,
                            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_creation_input_tokens': 2, 'cache_read_input_tokens': 3},
                            'total_cost_usd': 0.1, 'modelUsage': {a.MODEL: {'costBasis': 'list'}}}
                events = [init, {'type': 'assistant', 'message': {'model': a.MODEL, 'content': [{'type': 'tool_use', 'name': 'StructuredOutput'}]}}, terminal]
                (round_dir / 'stream.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
                (round_dir / 'stderr.log').write_text('PRIVATE_NEVER_EXPORT /Users/private/stderr')
                receipt = {'eligible': True, 'value': value, 'requested_model': a.MODEL, 'observed_models': [a.MODEL],
                           'timeout': False, 'exit_code': 0, 'cleanup_error': None, 'wall_seconds': 1.0, 'terminal': terminal,
                           'stream_sha256': a.sha(round_dir / 'stream.jsonl'), 'request_sha256': a.sha(round_dir / 'request.json'), 'tools_used': []}
                write(round_dir / 'receipt.json', receipt)
                history.append({'assistant': value})
                history.append({'user': [d['answer'] for d in case['decisions']] if index == 1 else ['No new consequential decision was recognized. Use known source facts and ask the missing behavior choice.']})
            decision_ids = sorted(d['id'] for d in case['decisions'])
            raw = {'spec': spec, 'eligible': True, 'covered_decisions': decision_ids, 'required_decisions': 3, 'premature_ready': False,
                   'final_ready': True, 'answered_before_terminal': decision_ids, 'repeat_decision_questions': 0,
                   'history': history, 'rounds': 2, 'semantic_choice_accuracy': 'requires independent transcript review',
                   'limitation': 'Frozen keyword scripted-user oracle; no code implementation or real-user satisfaction measured'}
            write(directory / 'result.json', raw)
            results.append(raw)
            anonymous = 'I' + str(anonymous_number).zfill(2)
            mapping[anonymous] = spec
            packets.append({'id': anonymous, 'user_request': case['request'], 'known_context': case['known'],
                            'authoritative_decisions': [{'id': d['id'], 'answer': d['answer']} for d in case['decisions']],
                            'conversation': history, 'execution_eligible': True, 'round_limit': 3})
            judgments.append({'id': anonymous, 'authoritative_decisions': [
                {'decision_id': d['id'], 'question_assessment': 'substantive', 'question_references': ['A1.Q' + str(i)], 'human_answer_references': ['U1']}
                for i, d in enumerate(case['decisions'], 1)], 'latest_settled_follows_answers': True,
                'invented_choices_or_premature_readiness': [], 'additional_unanswered_ambiguities': [],
                'explicit_missing_authoritative_decisions': [], 'redundancy_or_source_fact_requests': {
                    'already_answered_preference_reasked': False, 'supplied_source_fact_requested': False},
                'readiness_assessment': 'PRIVATE_NEVER_EXPORT reviewer prose'})
        write(study / 'results.json', results)
        write(review / 'packet.json', packets)
        write(review / 'private-mapping.json', mapping)
        jury = review / 'primary-jury.json'
        write(jury, {'packetSHA256': a.sha(review / 'packet.json'), 'packet_path': str(review / 'packet.json'), 'rows': judgments})
        return study, review, jury, root

    def evaluate(self, fixture):
        return a.analyze(*fixture)

    def reseal(self, fixture):
        study = fixture[0]
        seal = a.read(study / 'registration.json')
        seal['sha256'] = a.digest(seal['payload'])
        write(study / 'registration.json', seal)
        adoption = a.read(study.parent / 'intake-adoption.json')
        adoption['adopted_intake_registration_sha256'] = a.sha(study / 'registration.json')
        write(study.parent / 'intake-adoption.json', adoption)

    def first_round(self, fixture):
        spec = a.read(fixture[0] / 'registration.json')['payload']['schedule'][0]
        return fixture[0] / a.name(spec) / 'round-1'

    def change_request(self, fixture, change):
        directory = self.first_round(fixture)
        request = a.read(directory / 'request.json')
        change(request)
        write(directory / 'request.json', request)
        receipt = a.read(directory / 'receipt.json')
        receipt['request_sha256'] = a.sha(directory / 'request.json')
        write(directory / 'receipt.json', receipt)

    def change_stream(self, fixture, change):
        directory = self.first_round(fixture)
        events = [json.loads(line) for line in (directory / 'stream.jsonl').read_text().splitlines()]
        change(events)
        (directory / 'stream.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        receipt = a.read(directory / 'receipt.json')
        receipt['stream_sha256'] = a.sha(directory / 'stream.jsonl')
        receipt['terminal'] = events[-1]
        receipt['value'] = events[-1]['structured_output']
        write(directory / 'receipt.json', receipt)

    def test_positive_closes_twelve_and_preserves_separate_measurements(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            self.assertEqual(report['assigned'], 12)
            self.assertEqual(len(report['rows']), 12)
            self.assertTrue(all(row['eligible'] for row in report['rows']))
            self.assertTrue(all(row['answered_before_terminal'] for row in report['rows']))
            self.assertIsNone(report['winner'])
            self.assertFalse(report['analyst_blinded'])
            self.assertIsNone(report['policies']['baseline']['observed_subscription_charge_usd'])

    def test_missing_duplicated_or_wrong_assigned_roster_fails_closed(self):
        for mutation in ('missing', 'duplicate', 'wrong'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); path = fixture[0] / 'registration.json'; seal = a.read(path)
                schedule = seal['payload']['schedule']
                if mutation == 'missing': schedule.pop()
                elif mutation == 'duplicate': schedule[-1] = schedule[0]
                else: schedule[0]['repeat'] = True
                write(path, seal); self.reseal(fixture)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_request_mismatches_are_rejected_even_when_receipt_rebound(self):
        for option, value in [('--model', 'other-model'), ('--effort', 'high'), ('--tools', 'Read'), ('--mcp-config', '{"mcpServers":{"other":{}}}'), ('--setting-sources', 'user'), ('--max-budget-usd', '6')]:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                self.change_request(fixture, lambda q: q['argv'].__setitem__(q['argv'].index(option) + 1, value))
                with self.assertRaisesRegex(ValueError, 'Actual request'): self.evaluate(fixture)
        for field, value in [('prompt', 'changed intervention'), ('timeout_seconds', 240)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); self.change_request(fixture, lambda q: q.__setitem__(field, value))
                with self.assertRaisesRegex(ValueError, 'Actual request'): self.evaluate(fixture)

    def test_stdin_and_stream_drift_fail_closed(self):
        for filename in ('input.txt', 'stream.jsonl'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); path = self.first_round(fixture) / filename
                path.write_bytes(path.read_bytes() + b'changed')
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_terminal_error_and_shape_cannot_be_laundered_by_rebound_digest(self):
        for field, value in [('is_error', True), ('subtype', 'error'), ('structured_output', {'questions': [], 'ready': True})]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); self.change_stream(fixture, lambda events: events[-1].__setitem__(field, value))
                with self.assertRaisesRegex(ValueError, 'eligibility'): self.evaluate(fixture)

    def test_models_tools_and_effective_inventory_are_checked(self):
        changes = [lambda events: events[1]['message'].__setitem__('model', 'other-model'),
                   lambda events: events[1]['message']['content'].append({'type': 'tool_use', 'name': 'Read'}),
                   lambda events: events[0].__setitem__('tools', ['StructuredOutput', 'Read']),
                   lambda events: events[0].__setitem__('mcp_servers', [{'name': 'other'}])]
        for change in changes:
            with tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); self.change_stream(fixture, change)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_question_recognition_does_not_authorize_prior_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td))
            self.change_stream(fixture, lambda events: events[-1]['structured_output'].__setitem__('ready', True))
            # Even current digests and terminal metadata cannot preserve the old
            # false premature_ready flag, extra round or pre-answer readiness.
            with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_raw_and_aggregate_normalized_equality_is_required(self):
        for mutation in ('missing', 'duplicate', 'false-ready', 'altered-answer'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); path = fixture[0] / 'results.json'; rows = a.read(path)
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[-1] = rows[0]
                elif mutation == 'false-ready': rows[0]['premature_ready'] = True
                else: rows[0]['history'][1]['user'].append('invented authority')
                write(path, rows)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_registered_source_policy_and_schema_drift_fail_closed(self):
        for kind in ('runner', 'policy', 'schema'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td))
                if kind == 'runner': (Path(td) / 'runner.py').write_text('changed runner')
                elif kind == 'policy': (Path(td) / 'policies/baseline/SKILL.md').write_text('changed policy')
                else:
                    path = fixture[0] / 'registration.json'; seal = a.read(path); seal['payload']['schema']['required'].pop(); write(path, seal); self.reseal(fixture)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_cosmetic_exception_requires_frozen_historical_bytes_and_only_whitespace(self):
        for changed in (False, True):
            with self.subTest(executable_change=changed), tempfile.TemporaryDirectory() as td:
                root = Path(td); fixture = self.fixture(root)
                path = root / 'intake.py'; original = path.read_bytes()
                subprocess.check_call(['git', 'init', '-q', str(root)])
                subprocess.check_call(['git', '-C', str(root), 'add', 'intake.py'])
                subprocess.check_call(['git', '-C', str(root), '-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid', 'commit', '-q', '-m', 'Synthetic frozen runtime'])
                commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
                frozen = fixture[0].parent / 'intake-runtime-frozen.py'; frozen.write_bytes(original)
                current = original.decode().replace('import runner\n', 'import runner  \n', 1)
                if changed: current += '\nCONSEQUENTIAL_CHANGE = True\n'
                path.write_text(current)
                note = {'historical_commit': commit, 'registered_runtime_sha256': a.sha(frozen), 'frozen_runtime_copy': str(frozen), 'current_runtime_sha256': a.sha(path)}
                write(fixture[0].parent / 'intake-cosmetic-revision.json', note)
                if changed:
                    with self.assertRaisesRegex(ValueError, 'trailing whitespace'): self.evaluate(fixture)
                else:
                    report = self.evaluate(fixture)
                    self.assertFalse(report['material_bindings']['cosmetic_revision']['copy_is_prelaunch_snapshot'])
                    self.assertEqual(report['material_bindings']['cosmetic_revision']['registered_runtime_sha256'], a.sha(frozen))
                    self.assertNotIn(td, json.dumps(a.public_projection(report)))

    def test_semantic_question_false_negative_does_not_become_an_actual_answer(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); report = self.evaluate(fixture)
            observed = report['rows'][0]
            observed['actual_answered_decisions'] = ['omitted-preserves', 'env-versus-saved']
            raw = a.read(fixture[0] / observed['episode_id'] / 'result.json')
            case = a.read(fixture[0] / 'registration.json')['payload']['cases'][0]
            judgment = a.read(fixture[2])['rows'][0]
            judgment['authoritative_decisions'][0]['human_answer_references'] = []
            raw['history'][1]['user'].remove(case['decisions'][0]['answer'])
            self.assertEqual(a.semantic_row(judgment, observed, raw, case)['substantive_question_without_keyword_answer_decisions'], ['numeric-over-saved'])

    def test_apostrophe_only_quote_typography_is_disclosed_without_changing_judgment(self):
        for quote, actual, verbatim in [
            ("Running children don't hold back completion.", "Running children don't hold back completion.", True),
            ("Running children don’t hold back completion.", "Running children don't hold back completion.", False),
            ("Running children don't hold back completion.", "Running children don’t hold back completion.", False),
        ]:
            with self.subTest(verbatim=verbatim), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); report = self.evaluate(fixture)
                observed = report['rows'][0]
                raw = a.read(fixture[0] / observed['episode_id'] / 'result.json')
                raw['history'][2]['assistant']['settled'].append(actual)
                case = a.read(fixture[0] / 'registration.json')['payload']['cases'][0]
                judgment = a.read(fixture[2])['rows'][0]
                judgment['invented_choices_or_premature_readiness'] = [{'kind': 'invented_choice_and_premature_readiness', 'references': ['A2.settled[-1]'], 'quote': quote}]
                semantic = a.semantic_row(judgment, observed, raw, case)
                self.assertEqual(semantic['issue_categories'], ['invented_choice_and_premature_readiness'])
                self.assertTrue(semantic['unsupported_final_ready'])
                self.assertEqual(semantic['quote_fidelity'][0]['quote_verbatim'], verbatim)
                self.assertEqual(semantic['quote_fidelity'][0]['typographic_normalization_used'], not verbatim)
                observed['jury'] = semantic
                public = a.public_projection(report)
                self.assertEqual(public['rows'][0]['jury']['quote_fidelity'], semantic['quote_fidelity'])
                self.assertNotIn(quote, json.dumps(public))

    def test_quote_typography_does_not_accept_wrong_words_punctuation_or_reference(self):
        for quote, ref in [
            ('Running children do hold back completion.', 'A2.settled[-1]'),
            ('Running children don’t hold back completion!', 'A2.settled[-1]'),
            ('Running children don’t hold back completion.', 'A2.settled[0]'),
            ('Running children don’t hold back completion.', 'A3.settled[-1]'),
        ]:
            with self.subTest(quote=quote, ref=ref), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); report = self.evaluate(fixture)
                observed = report['rows'][0]
                raw = a.read(fixture[0] / observed['episode_id'] / 'result.json')
                raw['history'][2]['assistant']['settled'].append("Running children don't hold back completion.")
                case = a.read(fixture[0] / 'registration.json')['payload']['cases'][0]
                judgment = a.read(fixture[2])['rows'][0]
                judgment['invented_choices_or_premature_readiness'] = [{'kind': 'invented_choice_and_premature_readiness', 'references': [ref], 'quote': quote}]
                with self.assertRaises(ValueError): a.semantic_row(judgment, observed, raw, case)

    def test_public_projector_rejects_free_text_in_defined_fields(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            report['rows'][0]['missing_decisions_before_terminal'] = ['/Users/private/PRIVATE_NEVER_EXPORT']
            with self.assertRaisesRegex(ValueError, 'public decision'): a.public_projection(report)

    def test_jury_packet_mapping_and_references_rebind_exact_histories(self):
        for kind in ('mapping', 'packet', 'jury-digest', 'answer-reference', 'question-reference'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                fixture = self.fixture(Path(td)); review, jury_path = fixture[1:3]
                if kind == 'mapping':
                    path = review / 'private-mapping.json'; data = a.read(path); data['I01'], data['I02'] = data['I02'], data['I01']; write(path, data)
                elif kind == 'packet':
                    path = review / 'packet.json'; data = a.read(path); data[0]['conversation'][1]['user'].append('changed'); write(path, data)
                    jury = a.read(jury_path); jury['packetSHA256'] = a.sha(path); write(jury_path, jury)
                else:
                    jury = a.read(jury_path)
                    if kind == 'jury-digest': jury['packetSHA256'] = '0' * 64
                    elif kind == 'answer-reference': jury['rows'][0]['authoritative_decisions'][0]['human_answer_references'] = ['U2']
                    else: jury['rows'][0]['authoritative_decisions'][0]['question_references'] = ['A1.Q99']
                    write(jury_path, jury)
                with self.assertRaises(ValueError): self.evaluate(fixture)

    def test_jury_semantics_stays_separate_from_keyword_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); jury = a.read(fixture[2]); row = jury['rows'][0]
            row['invented_choices_or_premature_readiness'] = [{'kind': 'invented_choice_and_premature_readiness', 'references': ['A2.ready']}]
            row['latest_settled_follows_answers'] = False
            write(fixture[2], jury)
            report = self.evaluate(fixture); observed = report['rows'][0]
            self.assertFalse(observed['keyword_premature_ready'])
            self.assertTrue(observed['jury']['unsupported_final_ready'])
            self.assertFalse(observed['jury']['latest_settled_follows_answers'])
            self.assertIsNone(report['winner'])

    def test_public_projection_contains_no_private_text_history_or_paths(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.evaluate(self.fixture(Path(td)))
            report['material_bindings']['private_path'] = '/Users/PRIVATE_NEVER_EXPORT'
            report['rows'][0]['bindings']['private_note'] = 'PRIVATE_NEVER_EXPORT'
            report['rows'][0]['jury']['private_quote'] = 'PRIVATE_NEVER_EXPORT'
            report['rows'][0]['round_evidence'][0]['usage']['private_path'] = '/Users/PRIVATE_NEVER_EXPORT'
            serialized = json.dumps(a.public_projection(report))
            for secret in ('PRIVATE_NEVER_EXPORT', '/Users/', str(Path(td)), 'Conversation so far:', 'user_request', 'known_context', 'readiness_assessment', 'cleanup_error', 'lexical_question_references'):
                self.assertNotIn(secret, serialized)
            self.assertEqual(len(a.public_projection(report)['rows']), 12)

    def test_missing_cost_is_unknown_and_outputs_cannot_be_overwritten(self):
        self.assertIsNone(a.number(True)); self.assertIsNone(a.number(float('nan')))
        with tempfile.TemporaryDirectory() as td:
            fixture = self.fixture(Path(td)); report = self.evaluate(fixture)
            for row in report['rows']:
                for round_ in row['round_evidence']:
                    round_['cost_estimate_usd'] = None; round_['cost_basis'] = 'unknown'
            summary = a.aggregate(report['rows'])
            self.assertIsNone(summary['baseline']['cost_estimate_usd_total'])
            self.assertIsNone(summary['baseline']['known_cost_estimate_usd_subtotal'])
            path = Path(td) / 'new.json'
            a.write_new_or_matching(path, {'same': True}); a.write_new_or_matching(path, {'same': True})
            with self.assertRaisesRegex(ValueError, 'overwrite'): a.write_new_or_matching(path, {'same': False})
            self.assertEqual(a.read(path), {'same': True})


if __name__ == '__main__':
    unittest.main()
