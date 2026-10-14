"""Lean task-trial controller: seal, serial provider admission, owned-group
reap, sandbox composition, single conditional continuation. Taskblind."""
import fcntl, hashlib, json, os, signal, subprocess, sys, time

TASK_FIELDS = ("task_id", "prompt", "requirements", "base_snapshot", "source_directory",
               "production_paths", "visible_commands", "source_sha256", "interpreter",
               "runtime_read_paths", "forbidden_runtime_read_paths")
TOOLS = ["mcp__cp_trial__list_files", "mcp__cp_trial__read_file", "mcp__cp_trial__write_file",
         "mcp__cp_trial__replace_text", "mcp__cp_trial__run_tests"]
MAIN = {"model": "claude-opus-5-5", "effort": "high", "seconds": 300, "usd": 3.0}
CONT = {"model": "claude-opus-5-5", "effort": "high", "seconds": 180, "usd": 2.0}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write(path, value):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as h:
        json.dump(value, h, indent=2, sort_keys=True); h.flush(); os.fsync(h.fileno())
    os.replace(tmp, path)


def read(path, default=None):
    try:
        with open(path) as h: return json.load(h)
    except FileNotFoundError: return default


def inventory(root, scratch=(".git", "__pycache__", ".pytest_cache")):
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in scratch)
        for f in sorted(files):
            p = os.path.join(base, f); rel = os.path.relpath(p, root)
            if os.path.islink(p): out[rel] = {"symlink": os.readlink(p)}; continue
            with open(p, "rb") as h: out[rel] = hashlib.sha256(h.read()).hexdigest()
    return out


# ---- immutable inputs seal (separate from per-run outputs) ----
def seal_inputs(study, task, policy_root):
    missing = [k for k in TASK_FIELDS if k not in task]
    if missing: raise ValueError(f"task missing fields {missing}")
    seal = {"task": digest({k: task[k] for k in TASK_FIELDS}), "policy": inventory(policy_root)}
    path = os.path.join(study, "inputs", "SEAL.json")
    if read(path) is None: write(path, seal)
    elif read(path) != seal: raise RuntimeError("input seal changed")
    return seal


def check_seal(study, task, policy_root):
    sealed = read(os.path.join(study, "inputs", "SEAL.json"))
    now = {"task": digest({k: task[k] for k in TASK_FIELDS}), "policy": inventory(policy_root)}
    if sealed != now: raise RuntimeError("seal mismatch: inputs or policy docs changed")
    return True


def prepare(study, task, policy_root):
    seal_inputs(study, task, policy_root)
    write(os.path.join(study, "runs", task["task_id"], "PREFLIGHT.json"),
          {"task_id": task["task_id"], "prepared": time.time()})
    check_seal(study, task, policy_root)  # recheck after real prepare


# ---- sandbox composition: allow support reads, then literal denies ----
def sandbox_profile(workspace, task, policy_paths=()):
    q = lambda p: json.dumps(p)
    rules = ["(version 1)", "(deny default)", "(allow process-fork)", "(allow process-exec*)",
             "(allow signal (target same-sandbox))", "(allow sysctl-read)", "(allow mach-lookup)",
             "(allow file-read-metadata)", "(deny network*)",
             f"(allow file-read* (subpath {q(workspace)}))", f"(allow file-write* (subpath {q(workspace)}))",
             '(allow file-write* (literal "/dev/null"))']
    rules += [f"(allow file-read* (subpath {q(p)}))" for p in task["runtime_read_paths"]]
    for p in task["forbidden_runtime_read_paths"]:  # unchanged, no resolving away aliases
        rules.append(f"(deny file-read* (literal {q(p)}))")
        rules.append(f"(deny file-read* (subpath {q(p)}))")
    rules += [f"(deny file-write* (subpath {q(p)}))" for p in policy_paths]
    return "\n".join(rules)


def command_prefix(workspace, task, policy_paths=()):
    return ["/usr/bin/sandbox-exec", "-p", sandbox_profile(workspace, task, policy_paths)]


def visible_argv(task, command):
    """Visible commands always run with the task's exact qualified interpreter."""
    argv = list(command)
    if argv and argv[0] in ("python", "python3", "interpreter"): argv[0] = task["interpreter"]
    return argv


# ---- global serial provider admission ----
class Admission:
    def __init__(self, state_dir):
        self.dir = state_dir; os.makedirs(state_dir, exist_ok=True)
        self.lock_path = os.path.join(state_dir, "provider.lock")
        self.ledger = os.path.join(state_dir, "ADMISSION.json")

    def __enter__(self):
        self.h = open(self.lock_path, "a+")
        waited = time.monotonic(); fcntl.flock(self.h, fcntl.LOCK_EX)
        self.queue_wait = time.monotonic() - waited  # not debited from provider timer
        led = read(self.ledger)
        if led and led.get("state") != "settled":
            fcntl.flock(self.h, fcntl.LOCK_UN); self.h.close()
            raise RuntimeError(f"unsettled admission blocks dispatch: {led}")
        return self

    def admit(self, record):
        write(self.ledger, dict(record, state="admitted", admitted=time.time()))

    def settle(self, outcome):
        write(self.ledger, dict(read(self.ledger, {}), state="settled", outcome=outcome))

    def __exit__(self, *exc):  # on exception the admission stays durable/unsettled
        fcntl.flock(self.h, fcntl.LOCK_UN); self.h.close()


def settle_explicitly(state_dir, note):
    led = os.path.join(state_dir, "ADMISSION.json")
    write(led, dict(read(led, {}), state="settled", outcome={"explicit": note}))


def cleanup_group(proc):
    try: os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()
    try: os.killpg(proc.pid, 0); alive = True
    except ProcessLookupError: alive = False
    return {"reaped": True, "group_alive": alive, "returncode": proc.returncode}


def run_stage(state_dir, run_dir, stage, argv, seconds, cleanup=cleanup_group, env=None):
    """Launch one provider stage under the global lock; retain partial streams."""
    os.makedirs(run_dir, exist_ok=True)
    out, err = os.path.join(run_dir, f"{stage}.stdout"), os.path.join(run_dir, f"{stage}.stderr")
    with Admission(state_dir) as adm:
        write(os.path.join(run_dir, f"{stage}.request.json"), {"argv": argv, "seconds": seconds})
        adm.admit({"stage": stage, "run_dir": run_dir})
        with open(out, "wb") as o, open(err, "wb") as e:
            start = time.monotonic()
            proc = subprocess.Popen(argv, stdout=o, stderr=e, start_new_session=True, env=env)
            write(os.path.join(run_dir, f"{stage}.process.json"), {"pid": proc.pid, "pgid": proc.pid})
            try: proc.wait(timeout=seconds); timed_out = False
            except subprocess.TimeoutExpired: timed_out = True
            reap = cleanup(proc)
        receipt = {"stage": stage, "timed_out": timed_out, "elapsed": time.monotonic() - start,
                   "queue_wait": adm.queue_wait, "reap": reap, **parse_stream(out)}
        if timed_out: receipt["terminal"] = None  # never fabricate a terminal
        write(os.path.join(run_dir, f"{stage}.receipt.json"), receipt)
        adm.settle({"stage": stage, "timed_out": timed_out})
    return receipt


def parse_stream(path):
    models, tools, terminal = set(), None, None
    with open(path, "rb") as h:
        for line in h:
            try: ev = json.loads(line)
            except ValueError: continue
            if ev.get("type") == "system" and ev.get("subtype") == "init": tools = ev.get("tools")
            if ev.get("type") == "assistant": models.add((ev.get("message") or {}).get("model"))
            if ev.get("type") == "result": terminal = ev
    return {"observed_models": sorted(m for m in models if m), "init_tools": tools, "terminal": terminal}


def claude_argv(prompt, system, mcp_config, final_schema, limits):
    return ["claude", "--print", "--model", limits["model"], "--effort", limits["effort"],
            "--output-format", "stream-json", "--verbose", "--tools", "", "--strict-mcp-config",
            "--mcp-config", json.dumps(mcp_config), "--setting-sources", "", "--no-session-persistence",
            "--restricted", "--disable-slash-commands", "--permission-mode", "dontAsk",
            "--allowedTools", *TOOLS, "--max-budget-usd", str(limits["usd"]),
            "--json-schema", json.dumps(final_schema), "--system-prompt", system, prompt]


# ---- continuation decision (max one, durable) ----
def continuation_decision(grade, receipt, source_stable):
    if grade.get("evaluation_status") != "observed":
        return {"admit": False, "reason": "unknown grade"}
    gap = not all(grade.get(k) for k in ("product_passed", "negative_passed",
                                          "regression_passed", "scope_valid"))
    deadline = bool(receipt.get("timed_out")) and receipt.get("observed_models") == [MAIN["model"]] \
        and set(receipt.get("init_tools") or []) >= set(TOOLS) \
        and receipt.get("reap", {}).get("group_alive") is False and source_stable
    if gap: return {"admit": True, "reason": "observed artifact gap"}
    if deadline: return {"admit": True, "reason": "known settled provider deadline"}
    return {"admit": False, "reason": "no observed gap or qualified deadline"}


def feedback(grade):
    """Actor-safe feedback only: no raw tracebacks, oracle source, or head."""
    return {"failed_requirements": [{k: r.get(k) for k in ("id", "claim", "observed", "expected")}
                                    for r in grade.get("failed_requirements", [])],
            **{k: grade.get(k) for k in ("source_current", "scope_valid", "local_module_binding")}}


def claim_continuation(run_dir, decision):
    """Durable max-one cap enforced at every entrypoint (O_EXCL marker)."""
    if not decision["admit"]: return False
    try: fd = os.open(os.path.join(run_dir, "CONTINUATION.claim"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError: return False
    os.write(fd, json.dumps(decision).encode()); os.close(fd)
    return True


# ---- local module origin probe (grader owns binding; this is the actual probe) ----
def module_origin(interpreter, workspace, module):
    code = ("import importlib,json,sys;sys.path.insert(0,sys.argv[2]);"
            "m=importlib.import_module(sys.argv[1]);print(json.dumps(getattr(m,'__file__',None)))")
    r = subprocess.run([interpreter, "-I", "-c", code, module, workspace], cwd=workspace,
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    origin = json.loads(r.stdout) if r.returncode == 0 else None
    real_ws = os.path.realpath(workspace)
    local = bool(origin) and os.path.realpath(origin).startswith(real_ws + os.sep)
    return {"module": module, "origin": origin, "local": local}


if __name__ == "__main__":
    print(json.dumps({"tools": TOOLS, "main": MAIN, "continuation": CONT}))
    sys.exit(0)
