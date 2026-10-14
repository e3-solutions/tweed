#!/usr/bin/env python3
"""Absolute-path adapter and fail-closed MCP qualification for a NEW cohort.

The registered first hybrid cohort is never resumed or rewritten. This module
imports its unchanged controller, normalizes paths before preparation/execution,
and adds local transport qualification and provider inventory evidence to new
stage receipts. No qualification probe makes a hosted inference request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
spec = __import__('importlib.util', fromlist=['']).spec_from_file_location('hybrid_v2_frozen', HERE / 'hybrid_runner.py')
frozen = __import__('importlib.util', fromlist=['']).module_from_spec(spec)
spec.loader.exec_module(frozen)
process_spec = __import__('importlib.util', fromlist=['']).spec_from_file_location('hybrid_v2_cleanup', HERE / 'hybrid_process_v2.py')
process_v2 = __import__('importlib.util', fromlist=['']).module_from_spec(process_spec)
process_spec.loader.exec_module(process_v2)
process_v2.install(frozen.processes)
runtime_spec = __import__('importlib.util', fromlist=['']).spec_from_file_location('hybrid_v2_runtime', HERE / 'hybrid_runtime_v2.py')
runtime_v2 = __import__('importlib.util', fromlist=['']).module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime_v2)
runtime_v2.install(frozen.base, frozen.backend)
EXPECTED = list(frozen.base.NATIVE_TOOLS)
RESOURCE_HANDLERS = list(frozen.backend.RESOURCE_HANDLERS)


def normalize_args(args):
    """Resolve against the coordinator cwd, before any actor cwd is selected."""
    for key in ('protocol', 'manifest', 'study', 'model_catalog'):
        value = getattr(args, key, None)
        if value is not None:
            setattr(args, key, Path(value).resolve())
    return args


def claude_mcp_configuration(workspace, control, *, readonly):
    """Capture the exact unchanged Claude adapter's argv without launching Claude."""
    captured = {}

    class NoInference:
        returncode = 0
        def poll(self):
            return 0

    def capture(argv, **kwargs):
        captured['argv'] = argv
        captured['cwd'] = str(kwargs['cwd'])
        return NoInference()

    # Do not patch the global subprocess module or the process-group guard.
    raw = frozen.base.claude_call.__wrapped__
    private_globals = {**raw.__globals__, 'subprocess': SimpleNamespace(Popen=capture)}
    isolated = FunctionType(raw.__code__, private_globals, raw.__name__, raw.__defaults__, raw.__closure__)
    isolated.__kwdefaults__ = raw.__kwdefaults__
    isolated(workspace, control, 'LOCAL TRANSPORT QUALIFICATION ONLY', .01,
        15, time.time() + 15, readonly=readonly)
    argv = captured['argv']
    servers = json.loads(argv[argv.index('--mcp-config') + 1])['mcpServers']
    return servers['cp_trial']


def local_mcp_probe(model, workspace, control, *, readonly):
    """Start the actual sandboxed MCP subprocess from the actual actor cwd.

    Exercise initialize/tools/list, list_files, and the readonly write denial.
    Source/read outputs are not returned; hashes and qualification facts suffice.
    """
    workspace = Path(workspace)
    control = Path(control)
    control.mkdir(parents=True, exist_ok=True)
    if model == 'opus':
        server = claude_mcp_configuration(workspace, control, readonly=readonly)
    elif model == 'astra':
        server = frozen.backend.mcp_server(workspace, control, time.time() + 15, readonly)['cp_trial']
    else:
        raise ValueError('Only registered Astra/Opus assignments are supported')
    calls = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'v2-qualification', 'version': '1'}}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'list_files', 'arguments': {}}},
    ]
    if readonly:
        calls.append({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {
            'name': 'write_file', 'arguments': {'path': 'qualification-must-not-create.py', 'content': 'FORBIDDEN'}}})
    argv = [server['command'], *server['args']]
    try:
        process = subprocess.run(argv, cwd=workspace, env=server['env'],
            input=''.join(json.dumps(c) + '\n' for c in calls), capture_output=True,
            text=True, timeout=20)
        events = [json.loads(line) for line in process.stdout.splitlines()]
        by_id = {event.get('id'): event for event in events}
        tools = [tool['name'] for tool in by_id.get(2, {}).get('result', {}).get('tools', [])]
        connected = by_id.get(1, {}).get('result', {}).get('serverInfo', {}).get('name') == 'cp-controlled-workspace'
        listed = by_id.get(3, {}).get('result', {}).get('isError') is False
        denied = by_id.get(4, {}).get('result', {}).get('isError') is True if readonly else None
        forbidden = workspace / 'qualification-must-not-create.py'
        passed = (process.returncode == 0 and connected and listed and
                  len(tools) == len(EXPECTED) and set(tools) == set(EXPECTED) and
                  (not readonly or denied is True and not forbidden.exists()))
        receipt = dict(passed=passed, offline=True, hosted_inference_calls=0,
            provider=model, actor_cwd=str(workspace.resolve()), readonly=readonly,
            connected=connected, effective_mcp_tools=tools, expected_mcp_tools=EXPECTED,
            list_files_succeeded=listed, readonly_write_denied=denied,
            exit_code=process.returncode,
            stderr_sha256=hashlib.sha256(process.stderr.encode()).hexdigest(),
            stdout_sha256=hashlib.sha256(process.stdout.encode()).hexdigest(),
            config_argument=server['args'][-1], config_argument_is_absolute=Path(server['args'][-1]).is_absolute())
        (control / 'qualification.stderr').write_text(process.stderr)
        (control / 'qualification.stdout').write_text(process.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError) as error:
        receipt = dict(passed=False, offline=True, hosted_inference_calls=0,
            provider=model, readonly=readonly, error=type(error).__name__ + ': ' + str(error))
    frozen.write(control / 'local-qualification.json', receipt)
    return receipt


def effective_inventory(stage, local=None):
    """Reject missing Claude tools; distinguish missing evidence from false facts.

    Codex exposes its offline declared Responses inventory, not a live wire
    inventory. Its three resource handlers are retained and explicitly disclosed.
    Claude init is a live effective inventory and includes StructuredOutput.
    """
    model = stage.get('assigned_model')
    if local is not None and local.get('passed') is not True:
        return dict(passed=False, basis='local_pipeline_transport', reason='MCP qualification failed', local=local)
    if model == 'opus':
        init = stage.get('harness_initialization')
        if not isinstance(init, dict):
            return dict(passed=None, basis='live_claude_init', reason='Initialization inventory unavailable', local=local)
        tools, servers = init.get('tools'), init.get('mcp_servers')
        if not isinstance(tools, list) or not isinstance(servers, list):
            return dict(passed=None, basis='live_claude_init', reason='Initialization fields unavailable', local=local)
        wanted = ['mcp__cp_trial__' + name for name in EXPECTED]
        missing = sorted(set(wanted) - set(tools))
        unexpected = sorted(set(tools) - set(wanted) - {'StructuredOutput'})
        connected = any(s.get('name') == 'cp_trial' and s.get('status') == 'connected' for s in servers)
        return dict(passed=connected and not missing and not unexpected and len(tools) == len(set(tools)),
            basis='live_claude_init', connected=connected, missing_tools=missing,
            unexpected_tools=unexpected, effective_tools=tools,
            schema_output_tool='StructuredOutput', strict_seven_tool_parity=False, local=local)
    if model == 'astra':
        guard = stage.get('inventory_guard')
        if not isinstance(guard, dict):
            return dict(passed=None, basis='offline_declared_codex_inventory', reason='Bound inventory unavailable', local=local)
        wanted = ['mcp__cp_trial__' + name for name in EXPECTED] + RESOURCE_HANDLERS
        actual_expected = guard.get('expected_tools', [])
        passed = guard.get('passed') is True and len(actual_expected) == len(wanted) and set(actual_expected) == set(wanted)
        return dict(passed=passed, basis='offline_declared_codex_inventory_and_local_pipeline',
            live_wire_inventory_observed=False, strict_seven_tool_parity=False,
            additional_resource_handlers=RESOURCE_HANDLERS, resource_source='cp_trial tools-only server; no resources',
            observed_tool_call_names=sorted({e.get('name') for e in stage.get('tool_events', []) if isinstance(e.get('name'), str)}),
            declared_inventory=guard, local=local)
    return dict(passed=False, reason='Unregistered provider')


_ORIGINAL_INVOKE = frozen.invoke


def qualified_invoke(model, workspace, control, prompt, seconds, deadline, readonly, study, *, budget=None):
    workspace, control, study = (Path(p).resolve() for p in (workspace, control, study))
    local = local_mcp_probe(model, workspace, control / 'qualification', readonly=readonly)
    if local['passed'] is True:
        stage = _ORIGINAL_INVOKE(model, workspace, control, prompt, seconds, deadline, readonly, study, budget=budget)
    else:
        stage = dict(assigned_model=model, declared_complete=None, terminal=None, usage=None,
            total_cost_usd=None, process_exit=None, source_sha256_after=frozen.base.tree_digest(workspace),
            status='qualification_failed_before_inference', started_at_utc=frozen.now(), ended_at_utc=frozen.now())
    qualification = effective_inventory(stage, local)
    stage['adapter_qualification'] = qualification
    if qualification['passed'] is not True:
        stage['native_guard_violated'] = True
        stage['declared_complete'] = None
    frozen.write(control / 'receipt.json', stage)
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'qualify'))
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--model-catalog', type=Path)
    args = normalize_args(parser.parse_args())
    if args.action == 'qualify':
        workspace = args.study / 'qualification-workspace'
        workspace.mkdir(parents=True, exist_ok=True)
        reports = [local_mcp_probe(model, workspace, args.study / ('qualification-' + model + '-' + str(ro)), readonly=ro)
                   for model in ('astra', 'opus') for ro in (False, True)]
        frozen.write(args.study / 'pipeline-qualification.json', reports)
        print(json.dumps(reports, indent=2))
        if any(r['passed'] is not True for r in reports):
            raise SystemExit(1)
    elif args.action == 'prepare':
        frozen.prepare(args)
        workspace = args.study / 'probe-workspace'
        reports = [local_mcp_probe(model, workspace, args.study / ('pipeline-' + model + '-' + str(ro)), readonly=ro)
                   for model in ('astra', 'opus') for ro in (False, True)]
        pipeline_path = args.study / 'pipeline-qualification.json'
        frozen.write(pipeline_path, reports)
        if any(r['passed'] is not True for r in reports):
            raise ValueError('Both provider pipelines must qualify before V2 registration')
        registration = frozen.read(args.study / 'registration.json')
        registration['files'][str(pipeline_path)] = frozen.file_sha(pipeline_path)
        registration['adapter_version'] = 2
        registration['files'][str(Path(__file__).resolve())] = frozen.file_sha(Path(__file__))
        registration['qualification_rule'] = 'Absolute coordinator paths; per-stage local MCP probe; fail closed on missing/unknown effective inventory; no seven-tool parity claim'
        frozen.write(args.study / 'registration.json', registration)
    else:
        registration = frozen.read(args.study / 'registration.json')
        if registration.get('adapter_version') != 2 or registration['files'].get(str(Path(__file__).resolve())) != frozen.file_sha(Path(__file__)):
            raise ValueError('Fresh V2 registration matching this adapter is required')
        if not all(r.get('passed') is True for r in frozen.read(args.study / 'pipeline-qualification.json')):
            raise ValueError('Prepared pipelines are not qualified')
        frozen.invoke = qualified_invoke
        frozen.run(args)


if __name__ == '__main__':
    main()
