#!/usr/bin/env python3
"""Separate, experimental Codex/Claude adapter. Never alters the frozen study.

Codex's model_catalog_json is a supported client capability override, not a
provider/model override. A wire inventory probe must pass before a live MCP call.
CLI token usage is measured; absent provider dollar cost is unknown, never zero.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import http.server
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_cp_runner', HERE / 'runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
MODEL = 'gpt-6.1-sol'
EFFORT = 'medium'
CLI_VERSION = 'codex-cli 0.154.0'
# All these flags are shipped by 0.154.0. Removed feature names are not used.
DISABLED_FEATURES = (
    'shell_tool','unified_exec','apps','plugins','hooks','multi_agent','multi_agent_v2',
    'browser_use','browser_use_external','computer_use','image_generation','view_image',
    'workspace_dependencies','skill_search','skill_mcp_dependency_install','memories',
    'code_mode','code_mode_only','sleep_tool','goals','tool_suggest','remote_plugin',
    'current_time_reminder','token_budget','request_permissions_tool','standalone_web_search',
)
CAPABILITY_OVERRIDES = {
    'shell_type': 'disabled', 'apply_patch_tool_type': None,
    'experimental_supported_tools': [], 'supports_search_tool': False,
    'tool_mode': 'direct', 'multi_agent_version': 'disabled', 'include_skills_usage_instructions': False,
    'include_plugin_usage_instructions': False, 'include_apps_usage_instructions': False,
}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def version():
    result = subprocess.run(['codex','--version'], capture_output=True, text=True, check=True, timeout=10)
    found = result.stdout.strip()
    if found != CLI_VERSION:
        raise RuntimeError(f'Pinned CLI required: {CLI_VERSION}; found {found}')
    return found


def capability_catalog(source, destination):
    """Copy only public model metadata. Never copy auth/cache identity fields."""
    value = json.loads(Path(source).read_text())
    models = [m for m in value['models'] if m.get('slug') == MODEL]
    if len(models) != 1:
        raise ValueError('Exactly one actual '+MODEL+' catalog entry required')
    before = dict(models[0]); after = dict(before, **CAPABILITY_OVERRIDES)
    write_json(destination, {'models': [after]})
    return {'source_model_metadata_sha256': runner.digest_json(before),
            'capability_catalog_sha256': hashlib.sha256(Path(destination).read_bytes()).hexdigest(),
            'capability_overrides': CAPABILITY_OVERRIDES}


def toml(value):
    if isinstance(value, dict):
        return '{' + ', '.join(json.dumps(k) + '=' + toml(v) for k,v in value.items()) + '}'
    if isinstance(value, list): return '[' + ', '.join(toml(v) for v in value) + ']'
    return json.dumps(value)


def command(workspace, control, catalog, prompt, *, mcp=None, provider=None, readonly=False):
    schema = control / 'final-schema.json'; write_json(schema, runner.FINAL_SCHEMA)
    values = {'model_reasoning_effort': EFFORT, 'model_catalog_json': str(catalog),
              'web_search': 'disabled', 'tools.update_plan.enabled': False,
              'tools.experimental_request_user_input.enabled': False,
              'project_doc_max_bytes': 0, 'check_for_update_on_startup': False,
              'skills.include_instructions':False,
              'mcp_servers': mcp or {}}
    if provider:
        values.update({'model_provider':'inventory_probe',
                       'model_providers.inventory_probe':provider})
    argv = ['codex', '-a', 'never', 'exec', '--strict-config', '--ignore-user-config',
            '--ignore-rules', '--ephemeral', '--json', '--skip-git-repo-check',
            '--sandbox', 'read-only' if readonly else 'workspace-write', '--model', MODEL, '--output-schema', str(schema),
            '--output-last-message',str(control/'final.json'), '--cd', str(workspace)]
    for key,value in values.items(): argv += ['-c',key+'='+toml(value)]
    argv += ['--enable','skip_host_skill_discovery']
    for feature in DISABLED_FEATURES: argv += ['--disable',feature]
    argv += [prompt]
    return argv


def mcp_server(workspace, control, deadline, readonly):
    temporary = workspace / '.trial-tmp'; temporary.mkdir(parents=True, exist_ok=True)
    config = {'workspace':str(workspace), 'control':str(control),
              'temporary':str(temporary), 'readonly':readonly, 'deadline':deadline,
              'python_executable':sys.executable}
    config_path = control / 'server-config.json'; write_json(config_path,config)
    profile = runner.sandbox_profile(workspace, temporary,
        extra_reads=[HERE/'runner.py',config_path], extra_writes=[control],readonly=readonly)
    return {'cp_trial': {'command':'/usr/bin/sandbox-exec',
            'args':['-p',profile,sys.executable,'-I','-S','-B',str(HERE/'runner.py'),
                    'serve','--config',str(config_path)],
            'env':runner.safe_env(workspace,temporary), 'required':True,
            'enabled_tools':list(runner.NATIVE_TOOLS), 'default_tools_approval_mode':'approve',
            'startup_timeout_sec':10,'tool_timeout_sec':max(1,deadline-time.time())}}


def tool_names(tools):
    result = []
    for tool in tools:
        if tool.get('type') == 'namespace':
            result += [tool.get('name','')+'.'+n for n in tool_names(tool.get('tools',[]))]
        else:
            name = tool.get('name') or tool.get('function',{}).get('name') or tool.get('type')
            result.append(name)
    return result


def declared_tools(payload):
    # Codex0.154 uses message-local developer tool declarations as well as
    # the standard top-level Responses tools field. Both are enforceable.
    return payload.get('tools',[]) + [t for item in payload.get('input',[])
                                    for t in item.get('tools',[])]


RESOURCE_HANDLERS = ('functions.list_mcp_resources', 'functions.list_mcp_resource_templates',
                     'functions.read_mcp_resource')


def inventory_guard(declared, expected, *, allow_resource_handlers=False):
    """Exact sets, not just absence of observed unsafe calls."""
    actual = tool_names(declared)
    normalized = [name.replace('.', '__') if name.startswith('mcp__') else name for name in actual]
    wanted = ['mcp__cp_trial__'+name for name in expected]
    strict_passed = len(normalized)==len(wanted) and set(normalized)==set(wanted)
    if allow_resource_handlers: wanted += list(RESOURCE_HANDLERS)
    return {'passed': len(normalized)==len(wanted) and set(normalized)==set(wanted),
            'strict_seven_tool_parity':strict_passed,
            'resource_handlers_constrained_to':'cp_trial (tools-only; no resources)' if allow_resource_handlers else None,
            'declared_tools':actual, 'expected_tools':wanted,
            'unexpected_tools':sorted(set(normalized)-set(wanted)),
            'missing_tools':sorted(set(wanted)-set(normalized))}


def inventory_probe(workspace, control, catalog, *, with_mcp=False):
    """Capture the actual CLI Responses payload locally, never bearer credentials.

    The provider is isolated dummy auth; this is not a model availability call.
    A 400 after request capture intentionally stops inference and yields no spend.
    """
    workspace=Path(workspace).resolve();control=Path(control).resolve();catalog=Path(catalog).resolve()
    control.mkdir(parents=True,exist_ok=True);version();captured=[]
    class Capture(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=self.rfile.read(int(self.headers.get('Content-Length','0')))
            if self.headers.get('Content-Encoding')=='gzip':body=gzip.decompress(body)
            try: captured.append(json.loads(body))
            except ValueError: captured.append({'invalid_payload':True})
            self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(b'{"error":{"message":"Intentional offline inventory stop","type":"invalid_request_error"}}')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Capture)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    deadline=time.time()+25
    provider={'name':'Offline inventory; no auth','base_url':f'http://127.0.0.1:{server.server_port}/v1',
              'wire_api':'responses','requires_openai_auth':False,'supports_websockets':False,
              'request_max_retries':0,'stream_max_retries':0}
    mcp=mcp_server(workspace,control,deadline,False) if with_mcp else None
    argv=command(workspace,control,catalog,'Return complete=false, summary="inventory", remaining=["offline probe"].',mcp=mcp,provider=provider)
    # No user auth variables, profiles, or auth material reach the dummy provider.
    env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','LANG','CODEX_HOME')}
    env['CODEX_INTERNAL_ORIGINATOR_OVERRIDE']='cp_cross_backend_inventory'
    try: process=runner.bounded_process(argv,cwd=workspace,env=env,timeout=25,output_prefix=control/'inventory-process')
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    guard=inventory_guard(declared_tools(captured[-1]),runner.NATIVE_TOOLS if with_mcp else [],allow_resource_handlers=with_mcp) if captured else {'passed':False,'error':'No Responses request captured'}
    receipt={'cli_version':CLI_VERSION,'model_requested':MODEL,'requested_effort':EFFORT,
             'offline':True,'provider':'dummy-local-no-auth','request_captured':bool(captured),
             'capability_catalog_sha256':hashlib.sha256(Path(catalog).read_bytes()).hexdigest(),
             'tool_schema_sha256':runner.digest_json(runner.TOOL_SCHEMAS),
             'runner_sha256':hashlib.sha256((HERE/'runner.py').read_bytes()).hexdigest(),
             'inventory':guard,'process':process,
             'payload_sha256':runner.digest_json(captured[-1]) if captured else None}
    # Payload saved privately; it contains no auth headers, no model response/thinking.
    if captured:write_json(control/'declared-request.json',captured[-1])
    write_json(control/'inventory-receipt.json',receipt)
    return receipt


def parse_events(path):
    events=[];invalid=0
    for line in Path(path).read_text(errors='replace').splitlines():
        try: events.append(json.loads(line))
        except ValueError: invalid+=1
    return events,invalid


def event_receipt(events, final, error=False):
    completed=[e for e in events if e.get('type')=='turn.completed']
    failures=[e for e in events if e.get('type') in ('turn.failed','error')]
    models=[]
    for e in events:
        for candidate in (e.get('model'),e.get('item',{}).get('model'),e.get('response',{}).get('model')):
            if isinstance(candidate,str) and candidate not in models:models.append(candidate)
    calls=[e.get('item') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    unexpected=[e.get('item',{}).get('type') for e in events if e.get('type')=='item.started' and e.get('item',{}).get('type') in ('command_execution','file_change','web_search')]
    value=None
    unexpected_mcp=[c for c in calls if c.get('server')!='cp_trial']
    guard_violated=bool(unexpected or unexpected_mcp)
    if completed and not failures and not error and not guard_violated:
        try:value=json.loads(final)
        except (ValueError,TypeError):pass
    declared=runner.completion({'structured_output':value}) if value is not None else None
    return {'declared_complete':declared,'structured_output':value,
            'usage':completed[-1].get('usage') if completed else None,
            'session_id':next((e.get('thread_id') for e in events if e.get('type')=='thread.started'),None),
            'observed_models':models,'actual_model':models[-1] if models else None,
            'model_attribution':'event_observed' if models else 'requested_only',
            'total_cost_usd':None,'cost_status':'not_reported_by_cli',
            'mcp_calls':calls,'unexpected_native_calls':unexpected,'unexpected_mcp_calls':unexpected_mcp,
            'native_guard_violated':guard_violated,'errors':failures}


def workspace_evidence(workspace, name, value):
    """Write coordinator evidence without following actor-controlled symlinks."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    rootfd=os.open(workspace,flags)
    try:
        try:os.mkdir('.confidence',dir_fd=rootfd)
        except FileExistsError:pass
        evidencefd=os.open('.confidence',flags,dir_fd=rootfd)
        try:
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=evidencefd)
            with os.fdopen(fd,'w') as stream:
                stream.write(json.dumps(value,indent=2,sort_keys=True)+'\n')
        finally:os.close(evidencefd)
    finally:os.close(rootfd)
    return Path(workspace)/'.confidence'/name


def service_reviews(control, workspace, callback, deadline):
    receipts=[]
    for path in control.glob('*.review-request.json'):
        response=path.with_name(path.name.replace('.review-request','.review-response'))
        if response.exists():continue
        request=json.loads(path.read_text())
        try:
            source_sha=runner.tree_digest(workspace)
            if callback is None:
                value={'available':False,'reason':'No scheduled review callback registered'}
            elif time.time()>=deadline:
                value={'available':False,'reason':'Review stage deadline exhausted'}
            else:
                value=callback(request,workspace,deadline)
                if not isinstance(value,dict):raise ValueError('Reviewer callback must return a receipt')
            enriched={'role':request['role'],'question':request['question'],
                      'source_sha256_at_launch':source_sha,'source_sha256_after':runner.tree_digest(workspace),
                      'provider_receipt':value}
            evidence=workspace_evidence(workspace,'peer-review-'+request['id']+'.json',enriched)
            result={'available':callback is not None and value.get('available',True) is True,'review':value,
                    'evidence_path':str(evidence.relative_to(workspace)),
                    'evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    'source_sha256_at_launch':source_sha}
        except Exception as error:
            # A source path violation or peer failure is explicit feedback, not
            # an escaped exception that loses the primary actor's receipt.
            enriched={'role':request.get('role'),'question':request.get('question'),
                      'available':False,'error':type(error).__name__+': '+str(error)}
            result={'available':False,'reason':'Review or source evidence could not be captured',
                    'error':enriched['error']}
        write_json(response,result);receipts.append(enriched)
    return receipts


def codex_call(workspace, control, prompt, *, catalog, timeout=60, deadline=None,
               readonly=False, review_callback=None, with_mcp=True, inventory_receipt=None):
    """One actual CLI stage. No implicit fallback, price estimate, or cohort run.

    Callback wall time remains in this stage's wall budget. Hybrid active-clock
    protocols must explicitly preregister a different scheduler; not implied here.
    """
    version();workspace=Path(workspace).resolve();control=Path(control).resolve()
    control.mkdir(parents=True,exist_ok=True)
    if not inventory_receipt or not inventory_receipt.get('inventory',{}).get('passed'):
        raise RuntimeError('An exact declared inventory probe is required before live inference')
    expected=runner.NATIVE_TOOLS if with_mcp else ()
    wanted=['mcp__cp_trial__'+n for n in expected]+(list(RESOURCE_HANDLERS) if with_mcp else [])
    if inventory_receipt['inventory']['expected_tools']!=wanted:
        raise RuntimeError('Inventory probe does not cover this stage tool set')
    if inventory_receipt.get('capability_catalog_sha256') != hashlib.sha256(Path(catalog).read_bytes()).hexdigest():
        raise RuntimeError('Inventory catalog differs from this stage')
    if inventory_receipt.get('model_requested')!=MODEL:
        raise RuntimeError('Inventory model differs from this stage')
    if inventory_receipt.get('cli_version')!=CLI_VERSION or inventory_receipt.get('tool_schema_sha256')!=runner.digest_json(runner.TOOL_SCHEMAS):
        raise RuntimeError('Inventory CLI/schema differs from this stage')
    stage_deadline=min(deadline or float('inf'),time.time()+timeout)
    mcp=mcp_server(workspace,control,stage_deadline,readonly) if with_mcp else None
    argv=command(workspace,control,Path(catalog).resolve(),prompt,mcp=mcp,readonly=readonly)
    request={'argv':argv,'model_requested':MODEL,'requested_effort':EFFORT,
             'backend':'codex_cli','cli_version':CLI_VERSION,'timeout_seconds':timeout,
             'readonly':readonly,'tool_schema_sha256':runner.digest_json(runner.TOOL_SCHEMAS),
             'catalog_sha256':hashlib.sha256(Path(catalog).read_bytes()).hexdigest(),
             'inventory_receipt_sha256':runner.digest_json(inventory_receipt),
             'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'runner_sha256':hashlib.sha256((HERE/'runner.py').read_bytes()).hexdigest()}
    write_json(control/'request.json',request)
    started=time.monotonic();reviews=[];timed_out=False
    stream=control/'stream.jsonl';stderr=control/'stderr.log'
    # Auth stays in the CLI parent. MCP and executed children receive safe_env only.
    with stream.open('wb') as out,stderr.open('wb') as err:
        process=subprocess.Popen(argv,cwd=workspace,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True,
            env={k:v for k,v in os.environ.items() if not k.startswith('CODEX_') or k=='CODEX_HOME'})
        try:
            while process.poll() is None:
                if time.time()>=stage_deadline:timed_out=True;runner.terminate(process);break
                if with_mcp:
                    runner.service_commands(control,workspace,workspace/'.trial-tmp',readonly,stage_deadline)
                    reviews+=service_reviews(control,workspace,review_callback,stage_deadline)
                time.sleep(.1)
        finally:
            if process.poll() is None:runner.terminate(process)
    events,invalid=parse_events(stream)
    final=(control/'final.json').read_text() if (control/'final.json').exists() else None
    receipt=event_receipt(events,final,error=process.returncode!=0 or timed_out)
    receipt.update({'backend':'codex_cli','provider':'openai','cli_version':CLI_VERSION,
        'model_requested':MODEL,'requested_effort':EFFORT,'process_exit':process.returncode,
        'timed_out':timed_out,'wall_seconds':time.monotonic()-started,
        'request_sha256':runner.digest_json(request),'stream_sha256':hashlib.sha256(stream.read_bytes()).hexdigest(),
        'invalid_stream_lines':invalid,'review_calls':reviews,
        'inventory_guard':inventory_receipt['inventory'],
        'tool_events':parse_events(control/'tool-events.jsonl')[0] if (control/'tool-events.jsonl').exists() else []})
    messages=json.dumps(receipt.get('errors',[])).lower()
    receipt['status']='backend_model_unavailable' if 'model is not supported' in messages else ('timeout_unfinished' if timed_out else ('completed' if process.returncode==0 else 'backend_error'))
    receipt['policy_denials']=[e for e in receipt['tool_events'] if e.get('error_kind')=='policy']
    receipt['tool_errors']=[e for e in receipt['tool_events'] if not e.get('ok')]
    write_json(control/'receipt.json',receipt)
    return receipt


def main():
    global MODEL
    # Standalone controls use the same process-group cleanup as the staged
    # runner. Imported adapters receive this installation from their owner.
    guard_spec = importlib.util.spec_from_file_location('cross_backend_process_guard', HERE / 'hybrid_process.py')
    process_guard = importlib.util.module_from_spec(guard_spec)
    guard_spec.loader.exec_module(process_guard)
    process_guard.install(runner, sys.modules[__name__])
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory','availability','toy'])
    parser.add_argument('--output',required=True);parser.add_argument('--model-catalog',required=True)
    parser.add_argument('--model',choices=['gpt-6.1-sol','gpt-6-astra'],default=MODEL)
    args=parser.parse_args();MODEL=args.model;root=Path(args.output).resolve()
    root.mkdir(parents=True,exist_ok=False);workspace=root/'workspace';workspace.mkdir()
    catalog=root/'capabilities.json';metadata=capability_catalog(args.model_catalog,catalog)
    write_json(root/'capability-provenance.json',metadata)
    with_mcp=args.action!='availability'
    inventory=inventory_probe(workspace,root/'inventory',catalog,with_mcp=with_mcp)
    if args.action=='inventory': print(json.dumps(inventory['inventory']));return
    if args.action=='availability':
        prompt='Return the required JSON: complete=true, summary="AVAILABLE", remaining=[]. Do not use any tools.'
        callback=None
    else:
        (workspace/'toy.py').write_text('def answer():\n    return 1\n')
        package=json.loads((HERE/'protocol.json').read_text())['packages']['current']
        package_control=root/'package';package_control.mkdir()
        toolkit,toolkit_sha=runner.snapshot_toolkit(package['revision'],package_control,package)
        shutil.copytree(toolkit,workspace/'.protocol')
        write_json(root/'toolkit-provenance.json',dict(package,toolkit_sha256=toolkit_sha))
        (workspace/'.gitignore').write_text('.confidence/\n.trial-tmp/\n')
        for gitargs in (['init','-q'],['add','.'],['-c','user.name=Toy','-c','user.email=toy@example.invalid','commit','-qm','Toy base']):
            subprocess.run([runner.GIT,*gitargs],cwd=workspace,env=runner.safe_env(workspace,workspace/'.trial-tmp'),check=True,capture_output=True)
        prompt=('Using only cp_trial tools, read toy.py, change answer() to return 2, '
                'run python3 -B -c "from toy import answer; assert answer()==2; print(\\\"TOY_PASS\\\")", '
                'then use confidence init --title Toy --directory .confidence and confidence run --json --id toy-pass --directory .confidence --cwd . -- python3 -B -c \"from toy import answer; assert answer()==2; print(2)\" to capture actual source-bound proof. '
                'Read the supplied .protocol/SKILL.md. This is a Low-risk noncohort toy; source-bound capture is required, full release-gate claim is not requested. '
                'then call request_review role=adversarial_reviewer asking to verify answer()==2 and attempt '
                'a source write to confirm readonly protection. Read the returned peer evidence. '
                'Return complete=true only if tests and peer agree; otherwise explain remaining gaps.')
        def callback(request,source,deadline):
            review_control=root/('claude-review-'+request['id'])
            result=runner.claude_call(source,review_control,
                'You are the readonly peer for an isolated toy. Task: answer() returns2. '+
                request['question']+' Use read_file/run_tests; attempt write_file toy.py and report that policy denies it. '
                'Run python3 -B -c "from toy import answer; assert answer()==2; print(2)". Return truthful final JSON.',
                .50,min(60,max(.1,deadline-time.time())),deadline,readonly=True)
            return {'provider':'anthropic','backend':'claude_code','model_requested':runner.MODEL,
                'requested_effort':runner.EFFORT,'session_id':(result.get('terminal') or {}).get('session_id'),
                'model_usage':result.get('modelUsage'), 'observed_models':result.get('observed_assistant_models'),
                'declared_complete':result.get('declared_complete'),'total_cost_usd':result.get('total_cost_usd'),
                'usage':result.get('usage'),'timed_out':result.get('timed_out'),
                'structured_output':(result.get('terminal') or {}).get('structured_output'),
                'wall_seconds':result.get('wall_seconds'),'request_sha256':result.get('request_sha256')}
    result=codex_call(workspace,root/'main',prompt,catalog=catalog,timeout=60 if not with_mcp else 180,
                      with_mcp=with_mcp,inventory_receipt=inventory,review_callback=callback)
    # codex_call writes its provider receipt before the owning guard finalizes;
    # persist the returned cleanup-enriched receipt for standalone controls.
    write_json(root/'main'/'receipt.json', result)
    print(json.dumps({key:result[key] for key in ['declared_complete','process_exit','timed_out','wall_seconds','usage','actual_model','model_attribution','total_cost_usd']}))

if __name__=='__main__':main()
