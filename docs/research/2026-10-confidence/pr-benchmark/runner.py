#!/usr/bin/env python3
"""Controlled, budgeted real-PR replay runner and workspace-only MCP server."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

MODEL = "claude-opus-5-5"
EFFORT = "medium"
GIT = "/Library/Developer/CommandLineTools/usr/bin/git" if Path("/Library/Developer/CommandLineTools/usr/bin/git").exists() else "/usr/bin/git"
ROOT = Path(__file__).resolve().parents[4]
FINAL_SCHEMA = {"type": "object", "properties": {"complete": {"type": "boolean"},
    "summary": {"type": "string"}, "remaining": {"type": "array", "items": {"type": "string"}}},
    "required": ["complete", "summary", "remaining"], "additionalProperties": False}
NATIVE_TOOLS = ("list_files", "read_file", "write_file", "replace_text", "run_tests", "confidence", "request_review")
TOOL_SCHEMAS = {
    "list_files": {"type":"object","properties":{"path":{"type":"string"}}},
    "read_file": {"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},
    "write_file": {"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]},
    "replace_text": {"type":"object","properties":{"path":{"type":"string"},"old":{"type":"string"},"new":{"type":"string"}},"required":["path","old","new"]},
    "run_tests": {"type":"object","properties":{"argv":{"type":"array","items":{"type":"string"}},"timeout_seconds":{"type":"number"}},"required":["argv"]},
    "confidence": {"type":"object","properties":{"argv":{"type":"array","items":{"type":"string"}}},"required":["argv"]},
    "request_review": {"type":"object","properties":{"role":{"type":"string","enum":["test_designer","adversarial_reviewer","critic"]},"question":{"type":"string"}},"required":["role","question"]},
}

def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",",":")).encode()).hexdigest()

def tree_digest(root):
    """Path/mode/content inventory, excluding synthetic Git and scratch only.

    This is benchmark context identity, not CP's git-content-v1 fingerprint.
    """
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if any(part in (".git",".trial-tmp") for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink in frozen material: {path}")
        if path.is_file():
            relative=path.relative_to(root).as_posix()
            digest.update(relative.encode()+b"\0"+str(path.stat().st_mode & 0o777).encode()+b"\0"+path.read_bytes()+b"\0")
    return digest.hexdigest()

def safe_env(workspace, temporary):
    # Authentication is intentionally absent from every executable workspace tool.
    env={"PATH":"/Library/Developer/CommandLineTools/usr/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
         "LANG":"C.UTF-8", "TMPDIR":str(temporary), "PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1",
         "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,
         "GIT_TERMINAL_PROMPT":"0","CONFIDENCE_DISABLE_DIAGNOSTICS":"1",
         "DEVELOPER_DIR":"/Library/Developer/CommandLineTools","GIT_OPTIONAL_LOCKS":"0"}
    return env

def sandbox_profile(workspace, temporary, *, extra_reads=(), extra_writes=(), readonly=False):
    read_roots=[Path("/System"),Path("/usr"),Path("/bin"),
                *(Path("/opt/homebrew")/part for part in ("bin","lib","opt","Cellar","Frameworks")),
                Path("/Library/Frameworks"),Path("/Library/Developer/CommandLineTools"),
                Path(workspace).resolve(),Path(temporary).resolve(),*(Path(p).resolve() for p in extra_writes)]
    literals=[Path(p).resolve() for p in extra_reads]
    # macOS requires directory traversal/read permission on exact ancestors.
    ancestors={str(parent) for path in [*read_roots,*literals] for parent in path.parents}
    rules=["(version 1)","(deny default)","(allow process-fork)","(allow process-exec)",
           "(allow signal (target same-sandbox))"]
    readers=[f"(literal {json.dumps(p)})" for p in sorted(ancestors)]
    readers += [f"(subpath {json.dumps(str(p))})" for p in read_roots]
    readers += [f"(literal {json.dumps(str(p))})" for p in literals]
    readers += ['(literal "/dev/null")','(literal "/dev/urandom")','(literal "/dev/random")']
    rules.append("(allow file-read* "+" ".join(readers)+")")
    writable=([Path(workspace).resolve()] if not readonly else []) + [Path(temporary).resolve(),*(Path(p).resolve() for p in extra_writes)]
    rules.append("(allow file-write* "+" ".join(f"(subpath {json.dumps(str(p))})" for p in writable)+")")
    rules.append('(allow file-write* (literal "/dev/null"))')
    rules.append(f"(deny file-write* (subpath {json.dumps(str(Path(workspace).resolve()/'.protocol'))}))")
    rules.append(f"(deny file-write* (subpath {json.dumps(str(Path(workspace).resolve()/'.git'))}))")
    rules.append(f"(deny file-write* (literal {json.dumps(str(Path(workspace).resolve()/'AGENTS.md'))}))")
    return "\n".join(rules)

def terminate(process):
    if process.poll() is not None:
        return
    try:os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=3)

def bounded_process(argv, *, cwd, env, timeout, output_prefix):
    started=time.monotonic()
    output_prefix=Path(output_prefix);output_prefix.parent.mkdir(parents=True,exist_ok=True)
    out=output_prefix.with_suffix(".stdout");err=output_prefix.with_suffix(".stderr")
    with out.open("wb") as stdout,err.open("wb") as stderr:
        process=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        timeout_hit=False
        try:code=process.wait(timeout=max(0.1,timeout))
        except subprocess.TimeoutExpired:
            timeout_hit=True;terminate(process);code=process.returncode
        # A returned leader must not leave late writers or background processes.
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    return {"argv":argv,"exit_code":code,"timed_out":timeout_hit,"wall_seconds":time.monotonic()-started,
            "stdout":str(out),"stderr":str(err),"stdout_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
            "stderr_sha256":hashlib.sha256(err.read_bytes()).hexdigest()}

def sandbox_check(output):
    if not Path("/usr/bin/sandbox-exec").exists():
        raise RuntimeError("Required macOS confinement unavailable; no trials allowed")
    with tempfile.TemporaryDirectory(prefix="cp-confinement-") as name:
        root=Path(name).resolve();workspace=root/"workspace";workspace.mkdir();tmp=workspace/".tmp";tmp.mkdir()
        hidden=root/"oracle-sentinel";hidden.write_text("HELD-OUT-NOT-FOR-WORKER")
        outside=root/"outside-write";alias=workspace/"alias";alias.symlink_to(hidden)
        script=("import json,pathlib,socket;checks={}\n"
                "for name,operation in ["
                f"('outside_read',lambda:pathlib.Path({str(hidden)!r}).read_text()),"
                f"('symlink_read',lambda:pathlib.Path({str(alias)!r}).read_text()),"
                f"('outside_write',lambda:pathlib.Path({str(outside)!r}).write_text('bad')),"
                "('network',lambda:socket.create_connection(('127.0.0.1',9),timeout=1))]:\n"
                " try:operation();checks[name]='ALLOWED'\n"
                " except OSError as e:checks[name]=type(e).__name__\n"
                "print(json.dumps(checks))")
        profile=sandbox_profile(workspace,tmp)
        receipt=bounded_process(["/usr/bin/sandbox-exec","-p",profile,sys.executable,"-B","-c",script],
            cwd=workspace,env=safe_env(workspace,tmp),timeout=15,output_prefix=Path(output)/"confinement")
        checks=json.loads(Path(receipt["stdout"]).read_text()) if receipt["exit_code"]==0 else {}
        receipt["checks"]=checks;receipt["profile_sha256"]=hashlib.sha256(profile.encode()).hexdigest()
        receipt["passed"]=bool(checks) and all(v=="PermissionError" for v in checks.values()) and not outside.exists()
        (Path(output)/"confinement.receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        if not receipt["passed"]:raise RuntimeError("Confinement sentinel failed; no trials allowed")
        return receipt

class WorkspaceTools:
    def __init__(self,config):
        self.workspace=Path(config["workspace"]).resolve()
        self.control=Path(config["control"]).resolve()
        self.temporary=Path(config["temporary"]).resolve()
        self.readonly=bool(config.get("readonly",False))
        self.python=config.get("python_executable",sys.executable)
        self.deadline=float(config["deadline"])
        self.control.mkdir(parents=True,exist_ok=True)
        self.profile=sandbox_profile(self.workspace,self.temporary,readonly=self.readonly)

    def path(self,name):
        if not isinstance(name,str) or "\0" in name:
            raise ValueError("Expected workspace-relative path")
        candidate=self.workspace/name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Path must remain inside workspace")
        for parent in [candidate,*candidate.parents]:
            if parent==self.workspace.parent:break
            if parent.is_symlink():raise ValueError("Symlink paths are refused")
        resolved=candidate.resolve()
        if not resolved.is_relative_to(self.workspace) or ".git" in resolved.relative_to(self.workspace).parts:
            raise ValueError("History/outside paths are refused")
        return resolved

    def execute(self,argv,timeout=90):
        if not isinstance(argv,list) or not argv or not all(isinstance(item,str) and "\0" not in item for item in argv):
            raise ValueError("argv must contain strings")
        executable=argv[0]
        permitted={"python3":self.python,"python":self.python,self.python:self.python,
                   "git":GIT,"bash":"/bin/bash","sh":"/bin/sh"}
        if executable not in permitted:
            raise ValueError("Use python3, git, bash, or sh; confinement covers descendants")
        command=[permitted[executable],*argv[1:]]
        if executable in ("bash","sh") and command[1:2] not in (["-c"],):
            raise ValueError("Shell tools require -c without login/global startup files")
        remaining=self.deadline-time.time()
        if remaining<=0:raise TimeoutError("Trial deadline exhausted")
        # The trusted coordinator executes a separately confined child. Actor
        # code never inherits access to tool events or review control files.
        ident=uuid.uuid4().hex
        request=self.control/(ident+".command-request.json")
        request.write_text(json.dumps({"id":ident,"argv":command,"timeout":min(float(timeout),90,remaining)})+"\n")
        response=self.control/(ident+".command-response.json")
        while not response.exists() and time.time()<self.deadline:time.sleep(.1)
        if not response.exists():raise TimeoutError("Command deadline exhausted")
        return json.loads(response.read_text())

    def call(self,name,args):
        started=time.monotonic()
        try:
            if name=="list_files":
                path=self.path(args.get("path","."))
                result={"files":[p.relative_to(self.workspace).as_posix() for p in sorted(path.rglob("*"))
                    if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(self.workspace).parts][:5000]}
            elif name=="read_file":
                path=self.path(args["path"])
                if not path.is_file() or path.stat().st_size>1000000:raise ValueError("Readable files are regular and at most1MB")
                result={"path":args["path"],"content":path.read_text()}
            elif name in ("write_file","replace_text"):
                if self.readonly:raise ValueError("Reviewer is read-only")
                path=self.path(args["path"])
                if ".protocol" in path.relative_to(self.workspace).parts or path.name=="AGENTS.md":
                    raise ValueError("Supplied protocol/envelope is immutable")
                if name=="write_file":value=args["content"]
                else:
                    content=path.read_text()
                    if not args["old"] or content.count(args["old"])!=1:raise ValueError("old must match exactly once")
                    value=content.replace(args["old"],args["new"],1)
                if not isinstance(value,str) or len(value.encode())>1000000:raise ValueError("Write limited to1MB text")
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value);result={"written":args["path"]}
            elif name=="run_tests":
                result=self.execute(args["argv"],args.get("timeout_seconds",90))
            elif name=="confidence":
                argv=args["argv"]
                if not argv or argv[0] not in ("init","run","record","validate","render","next"):
                    raise ValueError("Use confidence init/run/record/validate/render/next")
                result=self.execute(["python3","-B",str(self.workspace/".protocol/scripts/confidence.py"),*argv])
            elif name=="request_review":
                if self.readonly:raise ValueError("Recursive reviews unavailable")
                if args.get("role") not in ("test_designer","adversarial_reviewer","critic"):
                    raise ValueError("Unknown review role")
                question=args.get("question")
                if not isinstance(question,str) or not question.strip() or len(question)>8000:
                    raise ValueError("Review question required (≤8000characters)")
                ident=uuid.uuid4().hex;request=self.control/(ident+".review-request.json")
                request.write_text(json.dumps({"id":ident,"role":args["role"],"question":question})+"\n")
                response=self.control/(ident+".review-response.json")
                while not response.exists() and time.time()<self.deadline:
                    time.sleep(.1)
                if not response.exists():raise TimeoutError("Review deadline exhausted")
                result=json.loads(response.read_text())
            else:raise ValueError("Unknown tool")
            event={"name":name,"arguments_sha256":digest_json(args),"ok":True,"wall_seconds":time.monotonic()-started}
            if name in ("run_tests","confidence"):
                event.update(command_exit_code=result.get("exit_code"),command_timed_out=result.get("timed_out"))
            return result,event
        except Exception as error:
            event={"name":name,"arguments_sha256":digest_json(args),"ok":False,"error":f"{type(error).__name__}: {error}"}
            markers=("outside","inside workspace","Symlink","History","immutable","read-only","Recursive","budget","deadline","Unknown tool","executable","Shell tools require")
            event["error_kind"]="policy" if any(marker in str(error) for marker in markers) else "tool_input"
            return {"error":event["error"]},event

def serve(config_path):
    config=json.loads(Path(config_path).read_text());worker=WorkspaceTools(config)
    for line in sys.stdin:
        try:
            request=json.loads(line);method=request.get("method");ident=request.get("id")
            if ident is None:continue
            if method=="initialize":result={"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"cp-controlled-workspace","version":"1"}}
            elif method=="ping":result={}
            elif method=="tools/list":result={"tools":[{"name":name,"description":f"Controlled workspace {name}; no network/oracle/history access","inputSchema":TOOL_SCHEMAS[name]} for name in NATIVE_TOOLS]}
            elif method=="tools/call":
                params=request["params"];value,event=worker.call(params["name"],params.get("arguments",{}))
                with (worker.control/"tool-events.jsonl").open("a") as log:log.write(json.dumps(event)+"\n")
                result={"content":[{"type":"text","text":json.dumps(value)}],"isError":not event["ok"]}
            else:
                print(json.dumps({"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Unknown method"}}),flush=True);continue
            print(json.dumps({"jsonrpc":"2.0","id":ident,"result":result}),flush=True)
        except Exception as error:
            print(json.dumps({"jsonrpc":"2.0","id":request.get("id"),"error":{"code":-32603,"message":str(error)}}),flush=True)

def terminal_events(path):
    events=[];invalid=0
    for line in Path(path).read_text(errors="replace").splitlines():
        try:
            event=json.loads(line)
            if event.get("type")=="result":events.append(event)
        except ValueError:invalid+=1
    return events,invalid

def service_commands(control,workspace,temporary,readonly,deadline):
    for request_path in control.glob("*.command-request.json"):
        response_path=request_path.with_name(request_path.name.replace(".command-request",".command-response"))
        if response_path.exists():continue
        try:request=json.loads(request_path.read_text())
        except ValueError:continue
        argv=request.get("argv")
        if not isinstance(argv,list) or not argv or argv[0] not in (sys.executable,GIT,"/bin/bash","/bin/sh"):
            receipt={"exit_code":None,"error":"Coordinator refused command executable"}
        else:
            profile=sandbox_profile(workspace,temporary,readonly=readonly)
            remaining=deadline-time.time()
            if remaining<=0:
                receipt={"exit_code":None,"error":"Operational deadline exhausted"}
            else:
                receipt=bounded_process(["/usr/bin/sandbox-exec","-p",profile,*argv],
                    cwd=workspace,env=safe_env(workspace,temporary),timeout=min(float(request["timeout"]),90,remaining),
                    output_prefix=control/("command-"+request["id"]))
                receipt["output"]=Path(receipt["stdout"]).read_text(errors="replace")[-120000:]
                receipt["error_output"]=Path(receipt["stderr"]).read_text(errors="replace")[-30000:]
        response_path.write_text(json.dumps(receipt)+"\n")

def completion(terminal):
    if not terminal or terminal.get("is_error") is True:return None
    value=terminal.get("structured_output")
    if not isinstance(value,dict):
        text=terminal.get("result","")
        try:value=json.loads(text)
        except (ValueError,TypeError):return None
    if not isinstance(value,dict) or set(value)!={"complete","summary","remaining"}:return None
    if type(value.get("complete")) is not bool or not isinstance(value.get("summary"),str):return None
    if not isinstance(value.get("remaining"),list) or not all(isinstance(item,str) for item in value["remaining"]):return None
    return value["complete"]

def known_cost(calls):
    values=[item.get("total_cost_usd") for item in calls]
    known=all(type(value) in (int,float) and math.isfinite(value) and value>=0 for value in values)
    subtotal=sum(value for value in values if type(value) in (int,float) and math.isfinite(value) and value>=0)
    return subtotal if known else None,subtotal

def safe_copy(source,destination):
    """Never dereference actor-authored symlinks with coordinator privileges."""
    ignored={".git",".trial-tmp"}
    for path in Path(source).rglob("*"):
        if any(part in ignored for part in path.relative_to(source).parts):continue
        if path.is_symlink():raise ValueError(f"Actor symlink refused before artifact copy: {path.relative_to(source)}")
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns(*ignored),symlinks=True)

def build_patch(base,result,output,production_paths):
    """Generate a production artifact using a new trusted Git index/config."""
    with tempfile.TemporaryDirectory(prefix="cp-trusted-patch-") as name:
        root=Path(name).resolve();safe_copy(base,root/"tree");tree=root/"tree"
        temporary=tree/".trial-tmp";temporary.mkdir(exist_ok=True)
        env=safe_env(tree,temporary)
        git=["/usr/bin/git","-c","core.fsmonitor=false","-c","core.hooksPath=/dev/null"]
        for args in (["init","-q"],["add","."],["-c","user.name=Benchmark","-c","user.email=benchmark@example.invalid","commit","-qm","Frozen base"]):
            subprocess.run([*git,*args],cwd=tree,env=env,capture_output=True,check=True)
        submitted=[]
        candidates=set(production_paths)
        # New ordinary root helpers may accompany a production edit; hidden
        # grader independently rejects reserved/stdlib-shadowing helper names.
        candidates.update(p.name for p in Path(result).glob("*.py") if not (Path(base)/p.name).exists())
        for relative in sorted(candidates):
            path=Path(relative)
            if path.is_absolute() or ".." in path.parts:raise ValueError("Unsafe production path")
            source=Path(result)/path;target=tree/path
            if source.is_symlink():raise ValueError("Production symlink refused")
            if source.is_file():
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);submitted.append(relative)
            elif target.exists() and target.is_file():target.unlink();submitted.append(relative)
        subprocess.run([*git,"add","-A"],cwd=tree,env=env,capture_output=True,check=True)
        patch=subprocess.run([*git,"diff","--cached","--binary","--no-ext-diff","--no-textconv","HEAD"],cwd=tree,env=env,capture_output=True,check=True).stdout
        Path(output).write_bytes(patch)
        return patch,submitted

def scope_diff(base,result,production_paths):
    allowed=set(production_paths)
    def inventory(root):
        return {p.relative_to(root).as_posix():p.read_bytes() for p in Path(root).rglob("*")
                if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(root).parts}
    before=inventory(base);after=inventory(result);violations=[]
    injected="Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n".encode()
    for name in sorted(set(before)|set(after)):
        if before.get(name)==after.get(name):continue
        parts=Path(name).parts
        if parts[0] in (".protocol",".confidence",".trial-tmp","tests"):continue
        if name=="AGENTS.md" and after.get(name)==injected:continue
        if name==".gitignore" and after.get(name)==before.get(name,b"")+b"\n.trial-tmp/\n.confidence/\n":continue
        if name in allowed or any(name.startswith(path.rstrip("/")+"/") for path in allowed):continue
        if name not in before and len(parts)==1 and name.endswith(".py"):continue
        violations.append(name)
    return violations

def claude_call(workspace,control,prompt,budget,timeout,deadline,*,readonly=False):
    control.mkdir(parents=True,exist_ok=True)
    temporary=workspace/".trial-tmp";temporary.mkdir(parents=True,exist_ok=True)
    stage_deadline=min(deadline,time.time()+timeout)
    config={"workspace":str(workspace),"control":str(control),"temporary":str(temporary),"readonly":readonly,"deadline":stage_deadline,"python_executable":sys.executable}
    config_path=control/"server-config.json";config_path.write_text(json.dumps(config))
    server_profile=sandbox_profile(workspace,temporary,extra_reads=[Path(__file__).resolve(),config_path],extra_writes=[control],readonly=readonly)
    mcp={"mcpServers":{"cp_trial":{"command":"/usr/bin/sandbox-exec","args":["-p",server_profile,sys.executable,"-I","-S","-B",str(Path(__file__).resolve()),"serve","--config",str(config_path)],
        "env":safe_env(workspace,temporary)}}}
    argv=["claude","--print","--model",MODEL,"--effort",EFFORT,"--output-format","stream-json","--verbose",
        "--tools","","--strict-mcp-config","--mcp-config",json.dumps(mcp),"--setting-sources","",
        "--no-session-persistence","--restricted","--disable-slash-commands","--permission-mode","dontAsk",
        "--allowedTools","mcp__cp_trial__*","--max-budget-usd",str(budget),
        "--json-schema",json.dumps(FINAL_SCHEMA),"--system-prompt",
        "You are a software engineer working only through the controlled workspace tools. No native tools, network, history, or outside files are available. Read the actual supplied .protocol/SKILL.md before work. Complete the requested behavior and return the required final JSON truthfully; remaining gaps remain explicit.",
        prompt]
    request={"argv":argv,"prompt":prompt,"model_requested":MODEL,"effort":EFFORT,"budget_usd":budget,"timeout_seconds":timeout,"readonly":readonly}
    (control/"request.json").write_text(json.dumps(request,indent=2)+"\n")
    started=time.monotonic();stdout=control/"stream.jsonl";stderr=control/"stderr.log"
    with stdout.open("wb") as out,stderr.open("wb") as err:
        process=subprocess.Popen(argv,cwd=workspace,stdout=out,stderr=err,start_new_session=True)
        timeout_hit=False
        while process.poll() is None:
            service_commands(control,workspace,temporary,readonly,stage_deadline)
            if time.monotonic()-started>timeout or time.time()>deadline:
                timeout_hit=True;terminate(process);break
            time.sleep(.1)
    terminals,invalid=terminal_events(stdout)
    terminal=terminals[-1] if terminals else None
    observed_models=[];initialization=None
    for line in stdout.read_text(errors="replace").splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if event.get("type")=="assistant":
            observed=event.get("message",{}).get("model")
            if isinstance(observed,str) and observed not in observed_models:observed_models.append(observed)
        elif event.get("type")=="system" and event.get("subtype")=="init":
            initialization={key:event.get(key) for key in ("model","tools","mcp_servers","mcp_server_errors","claude_code_version","permissionMode")}
    return {"process_exit":process.returncode,"timed_out":timeout_hit,"wall_seconds":time.monotonic()-started,
        "terminal":terminal,"declared_complete":completion(terminal),"total_cost_usd":terminal.get("total_cost_usd") if terminal else None,
        "usage":terminal.get("usage") if terminal else None,"modelUsage":terminal.get("modelUsage") if terminal else {},
        "permission_denials":terminal.get("permission_denials",[]) if terminal else [],
        "request_sha256":digest_json(request),"invalid_stream_lines":invalid,"stream_sha256":hashlib.sha256(stdout.read_bytes()).hexdigest(),
        "observed_assistant_models":observed_models,"harness_initialization":initialization,"requested_effort":EFFORT}

def snapshot_toolkit(revision,destination,expected=None):
    archive=destination/"toolkit.tar"
    with archive.open("wb") as output:
        subprocess.run(["git","archive","--format=tar",revision],cwd=ROOT,check=True,stdout=output)
    archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected and archive_sha!=expected["git_archive_sha256"]:raise ValueError("Frozen package archive hash mismatch")
    staging=destination/"extract";staging.mkdir()
    subprocess.run(["tar","-xf",str(destination/"toolkit.tar"),"-C",str(staging)],check=True)
    toolkit=staging/"skills/confidence-protocol"
    if expected:
        for path,key in ((toolkit/"SKILL.md","skill_sha256"),(toolkit/"scripts/confidence.py","confidence_script_sha256")):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected[key]:raise ValueError(f"Frozen {key} mismatch")
    return toolkit,tree_digest(toolkit)

def visible_transcript(path):
    messages=[]
    for line in Path(path).read_text(errors="replace").splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if event.get("type") not in ("assistant","user"):continue
        message=event.get("message",{})
        content=message.get("content",[])
        if isinstance(content,list):
            content=[block for block in content if block.get("type") not in ("thinking","redacted_thinking")]
        messages.append({"role":event["type"],"content":content})
    return messages

def run_trial(spec,task,arm,output,protocol_digest,packages):
    trial_id=spec["trial_id"];trial_out=Path(output)/"trials"/trial_id;trial_out.mkdir(parents=True,exist_ok=True)
    begin=time.monotonic();deadline=time.time()+570
    with tempfile.TemporaryDirectory(prefix="cp-pr-trial-") as scratch:
        job=Path(scratch).resolve();workspace=job/"workspace"
        source=Path(task.get("base_snapshot",task.get("source_directory")))
        safe_copy(source,workspace)
        for pattern in ("AGENTS.md","CLAUDE.md",".claude",".codex",".git"):
            for path in list(workspace.rglob(pattern)):
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink()
        package=packages[arm["package"]]
        toolkit,toolkit_sha=snapshot_toolkit(arm["toolkit_revision"],job,package)
        shutil.copytree(toolkit,workspace/".protocol")
        shutil.copytree(job/"extract",workspace/".protocol/package")
        temporary=workspace/".trial-tmp";temporary.mkdir()
        (workspace/"AGENTS.md").write_text("Use the supplied .protocol/SKILL.md and controlled tools. No source history or held-out oracle is available.\n")
        ignore=workspace/".gitignore"
        ignore.write_text((ignore.read_text() if ignore.exists() else "")+"\n.trial-tmp/\n.confidence/\n")
        env=safe_env(workspace,temporary)
        for argv in (["git","init","-q"],["git","-c","core.fsmonitor=false","-c","core.hooksPath=/dev/null","add","."],["git","-c","core.hooksPath=/dev/null","-c","user.name=Benchmark","-c","user.email=benchmark@example.invalid","commit","-qm","Frozen base"]):
            subprocess.run(argv,cwd=workspace,env=env,check=True,capture_output=True)
        calls=[];reviews=[];review_count=0
        episode_errors=[]
        def episode(prompt,budget,control):
            nonlocal review_count
            control.mkdir(parents=True,exist_ok=True);box={}
            stage_deadline=min(deadline,time.time()+240)
            def launch():
                try:box["result"]=claude_call(workspace,control,prompt,budget,max(.1,stage_deadline-time.time()),deadline)
                except Exception as error:box["error"]=f"{type(error).__name__}: {error}"
            thread=threading.Thread(target=launch);thread.start()
            while thread.is_alive():
                for request_path in control.glob("*.review-request.json"):
                    response_path=request_path.with_name(request_path.name.replace(".review-request",".review-response"))
                    if response_path.exists():continue
                    try:request=json.loads(request_path.read_text())
                    except ValueError:continue
                    used,subtotal=known_cost([*calls,*reviews])
                    available=None if used is None else 3.75-used-budget
                    if review_count>=2 or time.time()>=stage_deadline or available is None or available<=0:
                        response={"available":False,"reason":"Common review budget/deadline exhausted or prior cost unknown"}
                    else:
                        review_count+=1
                        review_control=job/f"review-{review_count}"
                        try:review_source_sha=tree_digest(workspace)
                        except ValueError as error:
                            response_path.write_text(json.dumps({"available":False,"reason":str(error)})+"\n")
                            continue
                        question=("Independent "+request["role"]+" review. Read the actual supplied protocol and current source. "
                            "The source and toolkit are read-only. You may execute visible checks with scratch under TMPDIR. "
                            "Do not see or request hidden oracle/history/gold. Do not edit source. "
                            "Task requirements:\n"+task["prompt"]+"\nFalsifiable review question:\n"+request["question"])
                        try:
                            review=claude_call(workspace,review_control,question,min(1,available),
                                min(240,max(.1,stage_deadline-time.time())),stage_deadline,readonly=True)
                        except Exception as error:
                            review={"terminal":None,"declared_complete":None,"total_cost_usd":None,"usage":None,
                                "modelUsage":{},"permission_denials":[],"timed_out":False,"error":str(error)}
                        reviews.append(review)
                        response={"available":bool(review.get("terminal")),"review":
                            review["terminal"].get("structured_output",review["terminal"].get("result")) if review.get("terminal") else None,
                            "declared_complete":review.get("declared_complete"),"timed_out":review.get("timed_out")}
                        response.update(session_id=review.get("terminal",{}).get("session_id") if review.get("terminal") else None,
                            model_usage=review.get("modelUsage"),requested_model=MODEL,requested_effort=EFFORT,
                            role=request["role"],question=request["question"],source_sha256=review_source_sha)
                        try:
                            evidence=workspace/".confidence"
                            if evidence.is_symlink():raise ValueError("Symlink peer evidence directory refused")
                            evidence.mkdir(exist_ok=True)
                            peer=evidence/f"peer-review-{review_count}.json"
                            content=json.dumps({"role":request["role"],"question":request["question"],
                                "task_requirements":task["prompt"],"source_sha256":review_source_sha,
                                "model_requested":MODEL,"effort":EFFORT,"result":review},indent=2)+"\n"
                            descriptor=os.open(peer,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
                            with os.fdopen(descriptor,"w") as file:file.write(content)
                            response.update(reference=str(peer.relative_to(workspace)),reference_sha256=hashlib.sha256(content.encode()).hexdigest())
                        except (ValueError,OSError) as error:response["evidence_write_error"]=str(error)
                        if review_control.exists():shutil.copytree(review_control,trial_out/f"review-{review_count}")
                    response_path.write_text(json.dumps(response)+"\n")
                time.sleep(.1)
            thread.join()
            if control.exists():shutil.copytree(control,trial_out/control.name)
            if "error" in box:
                episode_errors.append(box["error"])
                return {"terminal":None,"declared_complete":None,"total_cost_usd":None,"usage":None,
                    "modelUsage":{},"permission_denials":[],"timed_out":False,"error":box["error"]}
            return box["result"]
        frozen_prompt=spec["prompt"]
        main_control=job/"main"
        calls.append(episode(frozen_prompt,1.75,main_control))
        spent,subtotal=known_cost([*calls,*reviews])
        review_reserve=(2-review_count)*1.0
        remaining=None if spent is None else 3.75-spent-review_reserve
        if calls[-1]["declared_complete"] is not True and remaining is not None and remaining>.01 and time.time()<deadline:
            # Common continuation, preserving all visible turns/tool results but
            # excluding hidden reasoning and any external grader feedback.
            history=visible_transcript(main_control/"stream.jsonl") if (main_control/"stream.jsonl").exists() else []
            prompt=frozen_prompt+"\nContinue the unfinished task on the same workspace under the same requirements. Prior visible main transcript:\n"+json.dumps(history)
            calls.append(episode(prompt,remaining,job/"continuation"))
        result=trial_out/"result_snapshot";artifact_error=None
        scope_violations=[]
        try:
            safe_copy(workspace,result)
            scope_violations=scope_diff(source,result,task["production_paths"])
            patch,submitted=build_patch(source,result,trial_out/"submitted.patch",task["production_paths"])
            result_sha=tree_digest(result)
        except Exception as error:
            artifact_error=f"{type(error).__name__}: {error}";patch=b"";submitted=[];result_sha=None
        tool_events=[]
        for path in trial_out.rglob("tool-events.jsonl"):
            for line in path.read_text().splitlines():
                try:tool_events.append(json.loads(line))
                except ValueError:pass
        declared=calls[-1]["declared_complete"]
        total,subtotal=known_cost([*calls,*reviews])
        missing=any(item.get("terminal") is None for item in [*calls,*reviews])
        status="submitted" if declared is True else "unfinished"
        if missing:status="terminal_missing"
        if artifact_error:status="artifact_invalid"
        over_budget=total is not None and total>4 or time.monotonic()-begin>600
        if over_budget:status="budget_violation"
        receipt={"schema_version":1,"trial_id":trial_id,"task_id":spec["task_id"],"arm_id":spec["arm_id"],"repeat":spec["repeat"],
            "status":status,"declared_complete":declared,"wall_seconds":time.monotonic()-begin,
            "total_cost_usd":total,"known_cost_subtotal":subtotal,"cost_known":total is not None,
            "usage":[item.get("usage") for item in [*calls,*reviews]],
            "actual_model":[list(item.get("modelUsage",{})) for item in [*calls,*reviews]],
            "observed_assistant_models":[item.get("observed_assistant_models",[]) for item in [*calls,*reviews]],
            "model_requested":MODEL,"effort":EFFORT,"calls":calls,"review_calls":reviews,"tool_calls":tool_events,
            "tool_errors":[event for event in tool_events if not event["ok"]],
            "policy_denials":[event for event in tool_events if event.get("error_kind")=="policy"],
            "permission_denials":[denial for item in [*calls,*reviews] for denial in item.get("permission_denials",[])],
            "protocol_sha256":protocol_digest,"task_sha256":digest_json(task),"request_sha256":spec["request_sha256"],
            "source_sha256":tree_digest(source),"toolkit_sha256":toolkit_sha,"result_snapshot":str(result) if result.exists() else None,
            "production_paths":submitted,"patch_sha256":hashlib.sha256(patch).hexdigest(),"result_sha256":result_sha,
            "over_budget":over_budget,"operational_over_budget":total is not None and total>3.75,
            "scope_violations":scope_violations,
            "artifact_error":artifact_error,"episode_errors":episode_errors,"grade":None}
        (trial_out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        return receipt

def prepare(protocol,manifest,output):
    tasks={task.get("id",task.get("task_id")):task for task in manifest["tasks"]}
    arms={arm["id"]:arm for arm in protocol["arms"]}
    shuffled=sorted(tasks);random.Random(6102026).shuffle(shuffled)
    entries=[];trial_order=[]
    arm_ids=list(arms)
    for repeat in (1,2):
        for task_index,task_id in enumerate(shuffled):
            offset=(task_index+3*(repeat-1))%len(arm_ids)
            rotated=arm_ids[offset:]+arm_ids[:offset]
            if repeat==2:rotated=list(reversed(rotated))
            trial_order.extend({"task_id":task_id,"arm_id":arm_id,"repeat":repeat} for arm_id in rotated)
    package_skill={}
    with tempfile.TemporaryDirectory(prefix="cp-package-freeze-") as name:
        for key,package in protocol["packages"].items():
            if key=="materialization":continue
            destination=Path(name)/key;destination.mkdir()
            toolkit,toolkit_sha=snapshot_toolkit(package["revision"],destination,package)
            package_skill[key]=toolkit.joinpath("SKILL.md").read_text()
    runner_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for item in trial_order:
        task_id=item["task_id"];arm_id=item["arm_id"];repeat=item["repeat"]
        task=tasks[task_id];arm=arms[arm_id]
        prompt=("Supplied exact Confidence Protocol skill, verbatim:\n\n"+package_skill[arm["package"]]+
            "\n\nImplement the requested behavior on this frozen historical base. Run visible checks and record actual uncertainty. "
            "No held-out tests or gold implementation are available. Supplied toolkit files are immutable under .protocol.\n\n"+
            task["prompt"]+"\n\n"+arm["prompt_overlay"]+
            "\n\nCommon authorization: The user authorizes isolated local source edits, offline fixtures/tests, "
            "and fresh same-model support reviews within this shared cost/data envelope. No further permission is needed for those actions. "
            "No network, original history, other trial data, or hidden grading is authorized. "
            "Allowed production paths: "+json.dumps(task["production_paths"])+
            "; legitimate new ordinary root Python helpers may accompany the production change, but must not shadow stdlib/test framework names. "
            "Agent-written tests supplement visible proof; grading restores original tests. Place tests under tests/, "
            "proof packets under .confidence/, and disposable repro files under .trial-tmp/. "
            "Do not edit unrelated production paths or the injected AGENTS.md/.gitignore envelope.\n\nVisible test commands:\n"+json.dumps(task.get("test_commands",[]))+
            "\n\n"+protocol.get("common_terminal_instruction","Return complete/summary/remaining JSON truthfully."))
        spec={"trial_id":f"{task_id}--{arm_id}--r{repeat}","task_id":task_id,"arm_id":arm_id,"repeat":repeat,
            "prompt":prompt,"source_sha256":tree_digest(task.get("base_snapshot",task.get("source_directory"))),
            "toolkit_revision":arm["toolkit_revision"],"model":MODEL,"effort":EFFORT,"operational_budget_usd":3.75,
            "operational_timeout_seconds":570,"per_call_timeout_seconds":240,"runner_sha256":runner_sha,
            "tool_schema_sha256":digest_json(TOOL_SCHEMAS),"resource_policy_sha256":digest_json(protocol["resources"])}
        spec["request_sha256"]=digest_json(spec);entries.append(spec)
    frozen={"schema_version":1,"protocol_sha256":digest_json(protocol),"manifest_sha256":digest_json(manifest),
            "runner_sha256":runner_sha,"queue_sha256":digest_json(trial_order),"parallel_trials":3,"trials":entries}
    target=Path(output)/"frozen-requests.json"
    if target.exists() and json.loads(target.read_text())!=frozen:raise ValueError("Existing freeze differs; never overwrite after outcomes")
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(frozen,indent=2)+"\n")
    return frozen,tasks,arms

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="action",required=True)
    server=sub.add_parser("serve");server.add_argument("--config",required=True)
    smoke=sub.add_parser("confinement-smoke");smoke.add_argument("--output",required=True)
    for action in ("prepare","run"):
        command=sub.add_parser(action);command.add_argument("--protocol",required=True);command.add_argument("--manifest",required=True);command.add_argument("--output",required=True)
        if action=="run":command.add_argument("--concurrency",type=int,default=3);command.add_argument("--trial",action="append");command.add_argument("--freeze-confirmed",action="store_true")
    args=parser.parse_args()
    if args.action=="serve":serve(args.config);return
    if args.action=="confinement-smoke":print(json.dumps(sandbox_check(args.output)));return
    protocol=json.loads(Path(args.protocol).read_text());manifest=json.loads(Path(args.manifest).read_text())
    frozen,tasks,arms=prepare(protocol,manifest,args.output)
    if args.action=="prepare":print(json.dumps({"freeze":str(Path(args.output)/"frozen-requests.json"),"trials":len(frozen["trials"])}));return
    if not args.freeze_confirmed:raise ValueError("Parent must commit/review freeze and pass --freeze-confirmed before trials")
    sandbox_check(args.output)
    selected=[spec for spec in frozen["trials"] if not args.trial or spec["trial_id"] in args.trial]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures={pool.submit(run_trial,spec,tasks[spec["task_id"]],arms[spec["arm_id"]],args.output,frozen["protocol_sha256"],protocol["packages"]):spec for spec in selected}
        for future in concurrent.futures.as_completed(futures):
            spec=futures[future]
            try:result=future.result();print(json.dumps({"trial_id":result["trial_id"],"status":result["status"],"cost":result["total_cost_usd"]}),flush=True)
            except Exception as error:
                result={"schema_version":1,**{key:spec[key] for key in ("trial_id","task_id","arm_id","repeat")},
                    "status":"harness_failed","declared_complete":None,"grade":None,"error":f"{type(error).__name__}: {error}"}
                directory=Path(args.output)/"trials"/spec["trial_id"];directory.mkdir(parents=True,exist_ok=True)
                (directory/"receipt.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result),flush=True)

if __name__=="__main__":main()
