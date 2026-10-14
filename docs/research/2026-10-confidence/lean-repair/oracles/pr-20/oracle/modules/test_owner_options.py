"""Public main-to-provider checks; TOML compared by value, never source spelling."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SESSION = '019fd385-da76-77f3-bd3a-2f1e4e49b936'
loader = importlib.machinery.SourceFileLoader('owner_options_runner', str(ROOT / 'bonaparte'))
spec = importlib.util.spec_from_loader(loader.name, loader)
RUNNER = importlib.util.module_from_spec(spec)
loader.exec_module(RUNNER)


def provider_config(command):
    config = {}
    for i, token in enumerate(command[:-1]):
        if token == '-c':
            parsed = tomllib.loads(command[i + 1])
            for key, value in parsed.items():
                config.setdefault(key, {}).update(value) if isinstance(value, dict) else config.update({key: value})
    return config


class PublicOptions(unittest.TestCase):
    def invoke(self, options=(), environment=None, *, resume=True):
        observed = []
        def provider(command, **kwargs):
            observed.append(list(command))
            self.assertEqual(command[:2], ['/offline/codex', 'exec'])
            if resume:
                self.assertEqual(command[2], 'resume')
                self.assertEqual(command[-2:], [SESSION, '-'])
                self.assertIn('Continue from the saved question.', kwargs['input'])
            else:
                self.assertNotIn('resume', command[:3])
                self.assertEqual(command[command.index('-C') + 1], str(ROOT))
            target = Path(command[command.index('--output-last-message') + 1])
            target.write_text(json.dumps({
                'phase': 'rca', 'state': 'completed', 'issue': 'COR-1',
                'linear_url': 'https://linear.example/COR-1', 'result': 'established',
                'summary': 'offline option control', 'question': None, 'next_action': None,
                'branch': None, 'commit': None, 'pull_request_url': None,
            }))
            return subprocess.CompletedProcess(command, 0, stderr='')
        output, errors = io.StringIO(), io.StringIO()
        with (mock.patch.object(sys, 'argv', ['bonaparte', '--repo', str(ROOT), *options,
                    *(['resume', 'RCA', SESSION, 'Continue from the saved question.'] if resume else ['RCA', 'COR-1'])]),
              mock.patch.dict(os.environ, environment or {}, clear=True),
              mock.patch.object(RUNNER, 'find_codex', return_value='/offline/codex'),
              mock.patch.object(RUNNER, 'call_linear', return_value=({'identifier': 'COR-1', 'title': 'Example', 'url': 'https://linear.example/COR-1', 'description': '**Kind:** Bug', 'gitBranchName': 'fixture-branch', 'labels': []}, [])) as remote,
              mock.patch.object(RUNNER.subprocess, 'run', side_effect=provider),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
            try:
                code = RUNNER.main()
            except SystemExit as error:
                code = error.code
        if resume:
            remote.assert_not_called()
        return code, observed, output.getvalue(), errors.getvalue()

    def assert_model(self, command, expected):
        if expected is None:
            self.assertNotIn('-m', command, 'Unconfigured coordinator must use provider defaults')
        else:
            self.assertIn('-m', command, 'Requested coordinator model was lost')
            self.assertEqual(command[command.index('-m') + 1], expected)
        children = provider_config(command)['agents']
        self.assertEqual(set(children), {'default', 'worker', 'explorer'})
        for role, value in children.items():
            self.assertEqual(value.get('model'), expected, 'Child model diverged: ' + role)
            self.assertEqual(value['model_reasoning_effort'], 'medium')

    def test_model_omitted_preserves_provider_defaults(self):
        code, commands, *_ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(len(commands), 1)
        self.assert_model(commands[0], None)

    def test_model_environment_and_explicit_override_are_semantic_values(self):
        opaque = 'deployment/opaque:"v2"'
        for options, environment, expected in [
            ((), {'BONAPARTE_MODEL': '  global-profile  '}, 'global-profile'),
            (('--model', '  ' + opaque + '  '), {'BONAPARTE_MODEL': 'global-profile'}, opaque),
            (('--model', 'explicit-profile'), {'BONAPARTE_MODEL': '   '}, 'explicit-profile'),
        ]:
            with self.subTest(options=options, environment=environment):
                for resume in (False, True):
                    code, commands, *_ = self.invoke(options, environment, resume=resume)
                    self.assertEqual(code, 0)
                    self.assertEqual(len(commands), 1)
                    self.assert_model(commands[0], expected)

    def test_model_empty_inputs_fail_before_provider(self):
        for options, environment in [((), {'BONAPARTE_MODEL': '   '}),
                                    (('--model', '  '), {'BONAPARTE_MODEL': 'valid-profile'})]:
            with self.subTest(options=options):
                code, commands, *_ = self.invoke(options, environment)
                self.assertNotEqual(code, 0, 'Empty selected model was accepted')
                self.assertEqual(commands, [], 'Invalid option reached the provider')

    def test_reasoning_omitted_is_medium(self):
        code, commands, *_ = self.invoke()
        self.assertEqual(code, 0)
        self.assert_effort(commands[0], 'medium')

    def assert_effort(self, command, expected):
        config = provider_config(command)
        self.assertEqual(config['model_reasoning_effort'], expected, 'Coordinator effort was lost')
        self.assertEqual(set(config['agents']), {'default', 'worker', 'explorer'})
        for role, value in config['agents'].items():
            self.assertEqual(value['model_reasoning_effort'], expected, 'Child effort diverged: ' + role)

    def test_reasoning_override_reaches_coordinator_and_every_child_on_resume(self):
        for effort in ('high', '  xhigh  '):
            with self.subTest(effort=effort):
                for resume in (False, True):
                    code, commands, *_ = self.invoke(('--reasoning', effort, '--model', 'chosen-model'), resume=resume)
                    self.assertEqual(code, 0)
                    self.assertEqual(len(commands), 1)
                    self.assert_effort(commands[0], effort.strip())
                    self.assertEqual(commands[0][commands[0].index('-m') + 1], 'chosen-model')
                    for value in provider_config(commands[0])['agents'].values():
                        self.assertEqual(value['model'], 'chosen-model')

    def test_reasoning_blank_fails_before_provider(self):
        code, commands, *_ = self.invoke(('--reasoning', '  '))
        self.assertNotEqual(code, 0)
        self.assertEqual(commands, [], 'Blank reasoning reached the provider')
