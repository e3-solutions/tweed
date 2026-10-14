#!/usr/bin/env python3
"""One shared bounded Haiku fact packet per task, empty tools, exact citations."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import controller as c

MODEL='claude-haiku-5-5'
SCHEMA={'type':'object','properties':{'facts':{'type':'array','maxItems':6,'items':{'type':'object','properties':{'path':{'type':'string'},'start_line':{'type':'integer','minimum':1},'end_line':{'type':'integer','minimum':1},'quote':{'type':'string'},'fact':{'type':'string'}},'required':['path','start_line','end_line','quote','fact'],'additionalProperties':False}}},'required':['facts'],'additionalProperties':False}

def packet(task):
    paths=task.get('discovery_paths',task['production_paths'])
    root=Path(task['base_snapshot']).resolve();sources={}
    c.require(0<len(paths)<=8,'Discovery needs 1-8 paths')
    for name in paths:
        path=root/name
        c.require(not Path(name).is_absolute() and '..' not in Path(name).parts and path.is_file() and not path.is_symlink(),'Discovery path unsafe')
        raw=path.read_bytes().decode('utf-8');c.require(len(raw.encode())<=150000,'Discovery file exceeds packet bound')
        sources[name]={'sha256':c.sha(path),'content':raw}
    result={'task_id':task['task_id'],'task_prompt':task['prompt'],'sources':sources}
    c.require(len(json.dumps(result).encode())<=250000,'Combined discovery packet too large')
    return result

def validate_receipt(receipt,task):
    expected=packet(task)
    artifact_root=Path(receipt['artifact_root'])
    c.require(set(receipt['artifact_files'])=={'packet.json','request.json','stream.stdout','stream.stderr'},'Discovery artifact roster differs')
    for relative,digest in receipt['artifact_files'].items():c.a.bound(artifact_root/relative,digest,'Discovery artifact')
    c.require(c.read(artifact_root/'packet.json')==expected,'Actual discovery packet differs')
    request=c.read(artifact_root/'request.json');argv=request['argv']
    c.require(argv==request_argv(expected),'Actual discovery argv/prompt/schema differs from packet contract')
    c.require(request.get('model_requested')==MODEL and request.get('effort')=='medium' and request.get('timeout_seconds')==120 and request.get('budget_usd')==.6,'Actual discovery request bounds differ')
    for flag,wanted in (('--model',MODEL),('--effort','medium'),('--tools',''),('--mcp-config','{"mcpServers":{}}'),('--max-budget-usd','0.6')):
        c.require(flag in argv and argv[argv.index(flag)+1]==wanted,'Actual discovery tool/model request differs')
    raw_events=[]
    for line in (artifact_root/'stream.stdout').read_text(errors='replace').splitlines():raw_events.append(json.loads(line))
    actual=parse_events(raw_events)
    for key,value in actual.items():c.require(receipt['stage'].get(key)==value,'Discovery actual provider fact differs: '+key)
    c.require(receipt.get('packet_sha256')==c.digest(expected),'Discovery source packet changed')
    stage=receipt['stage'];terminal=stage.get('terminal')
    c.require(stage.get('stdout_sha256')==c.sha(artifact_root/'stream.stdout') and stage.get('stderr_sha256')==c.sha(artifact_root/'stream.stderr'),'Discovery lifecycle output binding differs')
    c.require(stage.get('model_requested')==MODEL and stage.get('observed_assistant_models')==[MODEL],'Haiku actual model mismatch/unknown')
    c.require(stage.get('timed_out') is False and stage.get('process_exit')==0 and stage.get('process_cleanup_scope')=='original_process_group' and stage.get('detached_descendants_contained') is False,'Discovery lifecycle unqualified')
    init=stage.get('harness_initialization',{})
    c.require(init.get('tools') in ([],['StructuredOutput']) and init.get('mcp_servers')==[],'Discovery tools/server inventory not empty')
    c.require(stage.get('tool_calls')==[],'Discovery tool call detected')
    c.require(isinstance(terminal,dict) and terminal.get('type')=='result' and terminal.get('subtype')=='success' and terminal.get('is_error') is False,'Discovery terminal invalid')
    output=terminal.get('structured_output');c.require(isinstance(output,dict) and set(output)=={'facts'} and isinstance(output['facts'],list) and 0<len(output['facts'])<=6,'Discovery fact schema invalid')
    c.require(output['facts']==receipt.get('validated_facts'),'Validated facts differ from actual terminal')
    quoted=0
    for fact in output['facts']:
        c.require(set(fact)=={'path','start_line','end_line','quote','fact'} and isinstance(fact['quote'],str) and isinstance(fact['fact'],str),'Fact fields invalid')
        source=expected['sources'].get(fact['path']);c.require(source is not None,'Fact path outside packet')
        start,end=fact['start_line'],fact['end_line'];lines=source['content'].splitlines(keepends=True)
        c.require(type(start) is int and type(end) is int and 1<=start<=end<=len(lines),'Fact line range invalid')
        exact=''.join(lines[start-1:end]);c.require(fact['quote'] in (exact,exact.removesuffix('\n')),'Fact quote bytes do not match complete cited source lines (optional sole terminal LF)')
        quoted+=len(fact['quote'].encode())
    c.require(quoted<=8000,'Quote budget exceeded')
    return True

def parse_events(events):
    assistants=[e.get('message',{}) for e in events if e.get('type')=='assistant']
    models=sorted({m['model'] for m in assistants if isinstance(m.get('model'),str)})
    calls=[block for message in assistants for block in message.get('content',[]) if isinstance(block,dict) and block.get('type')=='tool_use' and block.get('name')!='StructuredOutput']
    terminals=[e for e in events if e.get('type')=='result'];c.require(len(terminals)==1,'Discovery needs exactly one actual terminal')
    initial=[e for e in events if e.get('type')=='system' and e.get('subtype')=='init'];c.require(len(initial)==1,'Discovery needs exactly one actual inventory')
    return {'observed_assistant_models':models,'tool_calls':calls,'terminal':terminals[0],'harness_initialization':initial[0]}

def request_argv(value):
    numbered={**value,'sources':{name:{'sha256':source['sha256'],'numbered_lines':''.join(str(index)+'| '+line for index,line in enumerate(source['content'].splitlines(keepends=True),1))} for name,source in value['sources'].items()}}
    prompt=('Extract at most 6 source facts relevant to the task from this supplied bounded packet. '
        'Do not solve, propose edits or judge correctness. No tools are available. Each fact must give path, '
        'start_line, end_line, quote and short factual description. quote must reproduce the COMPLETE cited source '
        'lines excluding only an optional final newline, with line numbering starting at 1. The numbered prefixes are NOT quote bytes. Return the required JSON.\n'+json.dumps(numbered))
    argv=['claude','--print','--model',MODEL,'--effort','medium','--output-format','stream-json','--verbose',
        '--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','',
        '--no-session-persistence','--restricted','--disable-slash-commands','--permission-mode','dontAsk',
        '--max-budget-usd','0.6','--json-schema',json.dumps(SCHEMA),
        '--system-prompt','You extract read-only source facts solely from the supplied packet. No tool use.',prompt]
    return argv

def discover(task,directory):
    directory=Path(directory).resolve();c.claim(directory,{'task_id':task['task_id'],'role':'shared-discovery'})
    value=packet(task);c.write(directory/'packet.json',value)
    argv=request_argv(value)
    c.write(directory/'request.json',{'argv':argv,'model_requested':MODEL,'effort':'medium','timeout_seconds':120,'budget_usd':.6})
    adapter=c.runtime(c.DEV);base=adapter.frozen.base
    with tempfile.TemporaryDirectory(prefix='cp-haiku-packet-') as temp:
        result=base.bounded_process(argv,cwd=Path(temp),env=os.environ.copy(),timeout=120,output_prefix=directory/'stream')
    events=[];invalid=0
    for line in Path(result['stdout']).read_text(errors='replace').splitlines():
        try:events.append(json.loads(line))
        except ValueError:invalid+=1
    assistants=[e.get('message',{}) for e in events if e.get('type')=='assistant']
    models=sorted({m['model'] for m in assistants if isinstance(m.get('model'),str)})
    calls=[block for message in assistants for block in message.get('content',[]) if isinstance(block,dict) and block.get('type')=='tool_use' and block.get('name')!='StructuredOutput']
    terminals=[e for e in events if e.get('type')=='result'];terminal=terminals[-1] if terminals else None
    initial=[e for e in events if e.get('type')=='system' and e.get('subtype')=='init']
    stage={**result,'process_exit':result['exit_code'],'model_requested':MODEL,'observed_assistant_models':models,
        'harness_initialization':initial[-1] if initial else None,'tool_calls':calls,'terminal':terminal,'invalid_stream_lines':invalid}
    receipt={'artifact_root':str(directory),'artifact_files':{name:c.sha(directory/name) for name in ('packet.json','request.json','stream.stdout','stream.stderr')},'quote_normalization':'exact complete source lines; optional sole trailing LF omitted; numbered prefixes excluded','task_id':task['task_id'],'packet_sha256':c.digest(value),'stage':stage,
        'validated_facts':terminal.get('structured_output',{}).get('facts') if terminal else None,'qualified':False}
    try:validate_receipt(receipt,task);receipt['qualified']=True
    except Exception as error:receipt['error']=str(error)
    c.write(directory/'receipt.json',receipt);return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--task',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();tasks=c.read(args.manifest)['tasks'];task=next(t for t in tasks if t['task_id']==args.task)
    result=discover(task,args.output);print(json.dumps({'task_id':args.task,'qualified':result['qualified'],'error':result.get('error')}));sys.exit(0 if result['qualified'] else 1)
