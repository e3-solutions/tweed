"""Native mechanical bridge to the Opus-authored controller.

Reuses the checked-in WorkspaceTools, command service, environment and process
helpers; the Opus core owns admission, lifecycle, seals and continuation rules.
This module does not choose tasks, grade products, or call a hosted provider.
"""
from pathlib import Path
from types import FunctionType, SimpleNamespace
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = next(p for p in (HERE, *HERE.parents) if
            (p / 'docs/research/2026-10-confidence/claude-first-evaluation/runner.py').is_file())
LEGACY = REPO / 'docs/research/2026-10-confidence'


def load(path):
    spec = importlib.util.spec_from_file_location('fair_bridge_' + uuid.uuid4().hex, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load(LEGACY / 'claude-first-evaluation/runner.py')
TOOLS = ('list_files', 'read_file', 'write_file', 'replace_text', 'run_tests')


def _core():
    return load(HERE / 'runtime/controller.py')


def _base():
    base = load(LEGACY / 'pr-benchmark/runner.py')
    guard = load(LEGACY / 'pr-benchmark/hybrid_process.py')
    guard.cleanup_group = load(LEGACY / 'pr-benchmark/hybrid_process_v2.py').cleanup_group
    base.bounded_process = guard.bounded_process
    return base, guard


def _function(function, globals_patch):
    cloned = FunctionType(function.__code__, {**function.__globals__, **globals_patch},
                          function.__name__, function.__defaults__, function.__closure__)
    cloned.__kwdefaults__ = function.__kwdefaults__
    return cloned


def _configuration(task, workspace, call_dir):
    C = _core()
    base, guard = _base()
    workspace, call_dir = Path(workspace).resolve(), Path(call_dir).resolve()
    if call_dir.is_relative_to(workspace):
        raise ValueError('Tool custody/scratch must be outside the actor source')
    call_dir.mkdir(parents=True, exist_ok=True)
    scratch = call_dir / 'execution-scratch'
    scratch.mkdir(exist_ok=True)
    (scratch / 'home').mkdir(exist_ok=True)
    config_path = call_dir / 'server-config.json'
    config = {'workspace': str(workspace), 'control': str(call_dir), 'temporary': str(scratch),
              'readonly': False, 'deadline': time.time() + 86400,
              'python_executable': task['interpreter'],
              'borrowed_runner': str(LEGACY / 'pr-benchmark/runner.py')}
    R.write(config_path, config)
    policy = workspace / '.protocol'
    policy_allow = list(C.inventory(str(policy)))
    server_base = lambda w, t: C.sandbox_profile(w, t,
        extra_reads=[Path(__file__).resolve(), config_path, Path(config['borrowed_runner']),
                     LEGACY / 'claude-first-evaluation/runner.py'],
        extra_writes=[call_dir])
    server_profile = _function(C.task_profile, {'sandbox_profile': server_base})(
        str(workspace), str(scratch), task, [str(policy)], policy_allow)
    env = base.safe_env(workspace, scratch)
    env['HOME'] = str(scratch / 'home')
    mcp = {'mcpServers': {'cp_trial': {'command': '/usr/bin/sandbox-exec',
        'args': ['-p', server_profile, sys.executable, '-I', '-S', '-B',
                 str(Path(__file__).resolve()), 'serve', str(config_path)], 'env': env}}}
    command_profile = C.task_profile(str(workspace), str(scratch), task,
                                    [str(policy)], policy_allow)

    def captured_process(argv, **kwargs):
        # Python 3.9 initializes stdio with fstat. Preserve custody outside the
        # source, granting metadata only for these already-open capture files.
        prefix = Path(kwargs['output_prefix'])
        literals = ' '.join('(literal ' + json.dumps(str(prefix.with_suffix(suffix))) + ')'
                            for suffix in ('.stdout', '.stderr'))
        confined = list(argv)
        confined[2] += '\n(allow file-read-metadata ' + literals + ')'
        return base.bounded_process(confined, **kwargs)

    command_service = _function(base.service_commands, {
        'sys': SimpleNamespace(executable=task['interpreter']),
        'sandbox_profile': lambda *a, **kw: command_profile,
        'safe_env': lambda *a: dict(env), 'bounded_process': captured_process})

    def service(process, monotonic_deadline):
        wall_deadline = time.time() + max(0, monotonic_deadline - time.monotonic())
        config['deadline'] = wall_deadline
        R.write(config_path, config)
        command_service(call_dir, workspace, scratch, False, wall_deadline)
        time.sleep(.05)

    metadata = {'effective_tools': list(TOOLS), 'interpreter': task['interpreter'],
        'runtime_read_paths': list(task.get('runtime_read_paths', [])),
        'forbidden_runtime_read_paths': list(task.get('forbidden_runtime_read_paths', [])),
        'policy_before': C.inventory(str(policy)), 'command_profile_sha256': R.digest(command_profile),
        'server_profile_sha256': R.digest(server_profile), 'server_config': str(config_path),
        'borrowed_runner_sha256': R.sha(config['borrowed_runner']),
        'adapter_sha256': R.sha(__file__), 'scratch_outside_source': True}
    metadata['stdio_metadata_only'] = 'Exact per-command stdout/stderr literals; no contents permission'
    return C, base, guard, mcp, service, metadata


def build_stage(task, workspace, call_dir, prompt, limits):
    C, base, guard, mcp, service, metadata = _configuration(task, workspace, call_dir)
    system = ('Work only through the five bounded coding tools. Read .protocol/SKILL.md. '
              'Policy documents are immutable. No network, outside source or history is available. '
              'Ordinary legitimate test additions/updates are allowed; preserve unrelated regressions. '
              'For files above the read_file 1MB bound, use run_tests with the task Python to print '
              'explicit source line ranges. Return the required JSON truthfully.')
    return {'argv': C.claude_argv(prompt, system, mcp, base.FINAL_SCHEMA, limits),
            'env': None, 'service': service, 'metadata': metadata}


def transport_preflight(task, workspace, control):
    """No provider: exercise the actual MCP server and command-service prefix."""
    C, base, guard, mcp, service, metadata = _configuration(task, workspace, control)
    workspace, control = Path(workspace).resolve(), Path(control).resolve()
    before = C.inventory(str(workspace))
    outside = control / 'outside-secret.txt'
    outside.write_text('unreadable-by-actor')
    denied = [p for p in task.get('forbidden_runtime_read_paths', []) if Path(p).is_file()]
    policy_file = workspace / '.protocol/SKILL.md'
    denial_code = (
        'import errno,json,socket\n'
        'def denied_open(p,mode):\n'
        ' try:\n'
        '  with open(p,mode) as f:\n'
        '   if mode=="rb":f.read(1)\n'
        '  return False\n'
        ' except PermissionError:return True\n'
        f'paths={denied!r}\n'
        f'r={{"outside_read":denied_open({str(outside)!r},"rb"),'
        f'"outside_write":denied_open({str(control / "must-not-write")!r},"wb"),'
        f'"policy_write":denied_open({str(policy_file)!r},"wb"),'
        '"runtime_source_denies":all(denied_open(p,"rb") for p in paths),'
        '"runtime_existing_count":len(paths)}\n'
        'try:\n'
        ' s=socket.socket();s.settimeout(.5);s.connect(("127.0.0.1",9));r["network"]=False\n'
        'except OSError as e:r["network"]=e.errno in (errno.EPERM,errno.EACCES)\n'
        'print(json.dumps(r));assert all(r[k] for k in '
        '("outside_read","outside_write","policy_write","runtime_source_denies","network"))\n')
    source = next((Path(p) for p in task['production_paths'] if (workspace / p).is_file()), None)
    if source is None:
        raise ValueError('Preflight needs a declared regular production source')
    tail_code = ('import hashlib,json,pathlib;'
        f'lines=pathlib.Path({str(source)!r}).read_text().splitlines();'
        'print(json.dumps({"line_count":len(lines),"tail_sha256":'
        'hashlib.sha256("\\n".join(lines[-3:]).encode()).hexdigest()}))')
    calls = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2024-11-05', 'capabilities': {},
            'clientInfo': {'name': 'fair-loop-offline-prefix', 'version': '1'}}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
            'name': 'read_file', 'arguments': {'path': '/etc/passwd'}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {
            'name': 'write_file', 'arguments': {'path': '.protocol/SKILL.md', 'content': 'DENIED'}}},
    ]
    baseline_ids = []
    for command in task['visible_commands']:
        ident = len(calls) + 1
        baseline_ids.append(ident)
        calls.append({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {
            'name': 'run_tests', 'arguments': {'argv': C.visible_argv(task, command), 'timeout_seconds': 8}}})
    denial_id = len(calls) + 1
    calls.append({'jsonrpc': '2.0', 'id': denial_id, 'method': 'tools/call', 'params': {
        'name': 'run_tests', 'arguments': {'argv': [task['interpreter'], '-I', '-S', '-B', '-c', denial_code],
                                        'timeout_seconds': 8}}})
    tail_id = len(calls) + 1
    calls.append({'jsonrpc': '2.0', 'id': tail_id, 'method': 'tools/call', 'params': {
        'name': 'run_tests', 'arguments': {'argv': [task['interpreter'], '-I', '-S', '-B', '-c', tail_code],
                                        'timeout_seconds': 8}}})
    server = mcp['mcpServers']['cp_trial']
    input_path = control / 'preflight-input.jsonl'
    input_path.write_text(''.join(json.dumps(c) + '\n' for c in calls))
    stdout, stderr = control / 'preflight.stdout', control / 'preflight.stderr'
    deadline = time.monotonic() + 40
    with input_path.open('rb') as inp, stdout.open('wb') as out, stderr.open('wb') as err:
        proc = subprocess.Popen([server['command'], *server['args']], cwd=workspace,
            env=server['env'], stdin=inp, stdout=out, stderr=err, start_new_session=True)
        try:
            while proc.poll() is None and time.monotonic() < deadline:
                service(proc, deadline)
        finally:
            guard.cleanup_group(proc)
    rows = []
    for line in stdout.read_text(errors='replace').splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    byid = {r.get('id'): r for r in rows}
    inventory = [t['name'] for t in byid.get(2, {}).get('result', {}).get('tools', [])]

    def tool_result(ident):
        result = byid.get(ident, {}).get('result', {})
        if result.get('isError') is not False:
            return None
        try:
            return json.loads(result['content'][0]['text'])
        except (KeyError, IndexError, ValueError):
            return None

    baseline = [tool_result(i) for i in baseline_ids]
    denial, tail = tool_result(denial_id), tool_result(tail_id)
    same_source = C.inventory(str(workspace)) == before
    group_after = C.probe_group(proc.pid)
    passed = (proc.returncode == 0 and group_after == 'absent' and inventory == list(TOOLS) and bool(baseline_ids)
        and byid.get(3, {}).get('result', {}).get('isError') is True
        and byid.get(4, {}).get('result', {}).get('isError') is True
        and all(isinstance(r, dict) and r.get('exit_code') == 0 and r.get('timed_out') is False for r in baseline)
        and isinstance(denial, dict) and denial.get('exit_code') == 0 and not denial.get('timed_out')
        and bool(denied) and isinstance(tail, dict) and tail.get('exit_code') == 0
        and same_source and not (control / 'must-not-write').exists())
    receipt = {'passed': passed, 'hosted_calls': 0, 'process_exit': proc.returncode,
        'effective_inventory': inventory, 'baseline_receipts': baseline,
        'denial_receipt': denial, 'tail_receipt': tail, 'source_unchanged': same_source,
        'source_before_sha256': R.digest(before), 'source_after_sha256': R.digest(C.inventory(str(workspace))),
        'stdout_sha256': R.sha(stdout), 'stderr_sha256': R.sha(stderr),
        'input_sha256': R.sha(input_path), 'metadata': metadata,
        'group_after': group_after, 'existing_runtime_denies_count': len(denied)}
    R.write(control / 'TRANSPORT-PREFLIGHT.json', receipt)
    R.write(control / 'receipt.json', receipt)
    return receipt


def _serve(config_path):
    config = R.read(config_path)
    base = load(config['borrowed_runner'])
    base.NATIVE_TOOLS = TOOLS
    base.TOOL_SCHEMAS = {name: base.TOOL_SCHEMAS[name] for name in TOOLS}
    original = base.WorkspaceTools.call

    def bounded(self, name, args):
        if name not in TOOLS:
            return {'error': 'Tool unavailable'}, {'name': name, 'ok': False, 'error_kind': 'policy'}
        return original(self, name, args)

    base.WorkspaceTools.call = bounded
    base.serve(config_path)


if __name__ == '__main__':
    if sys.argv[1:2] != ['serve']:
        raise SystemExit('Usage: runtime_adapter.py serve SERVER_CONFIG')
    _serve(Path(sys.argv[2]))
