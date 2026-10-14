"""Lean task-trial controller: seal, serial provider admission, owned-group
reap (qualified hybrid_process_v2), sandbox composition, single conditional
continuation. Taskblind. No detached-descendant containment claim."""
import fcntl, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hybrid_process_v2  # qualified helper, copied unchanged; hash bound below

TASK_FIELDS = ("task_id", "prompt", "requirements", "base_snapshot", "source_directory",
               "production_paths", "visible_commands", "source_sha256", "interpreter",
               "runtime_read_paths", "forbidden_runtime_read_paths")
TOOLS = ["mcp__cp_trial__list_files", "mcp__cp_trial__read_file", "mcp__cp_trial__write_file",
         "mcp__cp_trial__replace_text", "mcp__cp_trial__run_tests"]
INVENTORY = sorted(TOOLS + ["StructuredOutput"])  # exact, never a superset
MODEL = "claude-opus-5-5"
MAIN = {"model": MODEL, "effort": "high", "seconds": 300, "usd": 3.0}
CONT = {"model": MODEL, "effort": "high", "seconds": 180, "usd": 2.0}


def file_sha(path):
    with open(path, "rb") as h: return hashlib.sha256(h.read()).hexdigest()


CLEANUP_SHA = file_sha(hybrid_process_v2.__file__)
cleanup_group = hybrid_process_v2.cleanup_group


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
    """Full tree material; symlinks recorded, never followed (no recursion)."""
    out = {}
    if not os.path.isdir(root): return {"<missing>": str(root)}
    for base, dirs, files in os.walk(root, followlinks=False):
        keep = []
        for d in sorted(dirs):
            p = os.path.join(base, d)
            if os.path.islink(p): out[os.path.relpath(p, root)] = {"symlink": os.readlink(p)}
            elif d not in scratch: keep.append(d)
        dirs[:] = keep
        for f in sorted(files):
            p = os.path.join(base, f); rel = os.path.relpath(p, root)
            out[rel] = {"symlink": os.readlink(p)} if os.path.islink(p) else file_sha(p)
    return out


# ---- immutable inputs seal (separate from per-run PREFLIGHT outputs) ----
def _seal_now(task, policy_root):
    missing = [k for k in TASK_FIELDS if k not in task]
    if missing: raise ValueError(f"task missing fields {missing}")
    if not task.get("base_snapshot") or not os.path.isdir(task["base_snapshot"]):
        raise ValueError("base_snapshot must be an existing pinned tree")
    return {"task": digest({k: task[k] for k in TASK_FIELDS}), "policy": inventory(policy_root),
            "base_snapshot": inventory(task["base_snapshot"])}


def seal_inputs(study, task, policy_root):
    seal, path = _seal_now(task, policy_root), os.path.join(study, "inputs", "SEAL.json")
    old = read(path)
    if old is None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # never overwritten
        os.write(fd, json.dumps(seal, indent=2, sort_keys=True).encode()); os.close(fd)
    elif old != seal: raise RuntimeError("input seal changed")
    return seal


def check_seal(study, task, policy_root):
    if read(os.path.join(study, "inputs", "SEAL.json")) != _seal_now(task, policy_root):
        raise RuntimeError("seal mismatch: task, base snapshot, or policy docs changed")
    return True


def _mutation_rejected(study, task, policy_root, target):
    """Edit an actual file, require check_seal rejection, restore exact bytes."""
    with open(target, "rb") as h: original = h.read()
    st = os.stat(target)
    try:
        with open(target, "ab") as h: h.write(b"\n#mutation-control\n")
        try: check_seal(study, task, policy_root); return False
        except RuntimeError: return True
    finally:
        with open(target, "wb") as h: h.write(original)
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))


def _first_file(root):
    for rel, v in sorted(inventory(root).items()):
        if isinstance(v, str): return os.path.join(root, rel)
    raise RuntimeError(f"no regular file for mutation control in {root}")


def prepare(study, task, policy_root):
    seal_inputs(study, task, policy_root)
    controls = {"base": _mutation_rejected(study, task, policy_root, _first_file(task["base_snapshot"])),
                "policy": _mutation_rejected(study, task, policy_root, _first_file(policy_root))}
    if not all(controls.values()): raise RuntimeError(f"mutation control not rejected: {controls}")
    check_seal(study, task, policy_root)  # recheck after real prepare + restore
    write(os.path.join(study, "runs", task["task_id"], "PREFLIGHT.json"),
          {"task_id": task["task_id"], "prepared": time.time(), "mutation_controls": controls})
    return controls


def stage_snapshot(workspace, policy_root, policy_before, production_paths=None):
    """Snapshot callback factory: genuine production/full-scope/policy digests."""
    def snap():
        first = inventory(workspace); second = inventory(workspace); pol = inventory(policy_root)
        prod = {p: first.get(p) for p in (production_paths or [])}
        return {"workspace": first, "workspace_digest": digest(first), "production": prod,
                "policy": pol, "policy_digest": digest(pol), "policy_unchanged": pol == policy_before,
                "source_stable": first == second, "paths": {"workspace": str(workspace), "policy": str(policy_root)}}
    return snap


# ---- sandbox: EXACT qualified base profile, then task composition ----
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


def _both(p):
    r = os.path.realpath(p)
    return [p] if r == p else [p, r]


def task_profile(workspace, temporary, task, policy_paths=(), protocol_allow=None):
    """Base + task support allows (+ancestor literals), then FULL forbidden
    literal denies unchanged, actor .protocol allowlist denies, policy write denies."""
    q = json.dumps
    rules = [sandbox_profile(workspace, temporary)]
    support = [x for p in (task.get("runtime_read_paths") or []) for x in _both(str(p))]
    if support:
        anc = sorted({str(a) for p in support for a in Path(p).parents})
        rules.append("(allow file-read* " + " ".join([f"(literal {q(a)})" for a in anc] +
                                                     [f"(subpath {q(p)})" for p in support]) + ")")
    if protocol_allow is not None:
        proto = os.path.join(os.path.realpath(workspace), ".protocol")
        for rel, _ in sorted(inventory(proto).items()):
            if rel not in protocol_allow and rel != "<missing>":
                rules.append(f"(deny file-read* (literal {q(os.path.join(proto, rel))}))")
    for p in task.get("forbidden_runtime_read_paths") or []:
        for x in _both(str(p)): rules.append(f"(deny file-read* (literal {q(x)}))")
    for p in policy_paths:
        for x in _both(str(p)): rules.append(f"(deny file-write* (subpath {q(x)}))")
    return "\n".join(rules)


def command_prefix(workspace, temporary, task, policy_paths=(), protocol_allow=None):
    return ["/usr/bin/sandbox-exec", "-p", task_profile(workspace, temporary, task, policy_paths, protocol_allow)]


def visible_argv(task, command):
    """Visible commands always run with the task's exact qualified interpreter."""
    argv = list(command)
    if argv and argv[0] in ("python", "python3", "interpreter"): argv[0] = task["interpreter"]
    return argv


def mcp_config(task, server_script, workspace, prefix=()):
    """MCP execute config using exact task interpreter (bridge: native adapter)."""
    argv = [*prefix, task["interpreter"], server_script, str(workspace)]
    return {"mcpServers": {"cp_trial": {"command": argv[0], "args": argv[1:]}}}


# ---- global serial provider admission (one state_dir for ALL entrypoints) ----
class Admission:
    def __init__(self, state_dir, recovering=False):
        self.dir, self.recovering = state_dir, recovering; os.makedirs(state_dir, exist_ok=True)
        self.lock_path = os.path.join(state_dir, "provider.lock")
        self.ledger = os.path.join(state_dir, "ADMISSION.json")

    def __enter__(self):
        self.h = open(self.lock_path, "a+")
        waited = time.monotonic(); fcntl.flock(self.h, fcntl.LOCK_EX)
        self.queue_wait = time.monotonic() - waited  # separate from provider timer
        led = read(self.ledger)
        if not self.recovering and led and led.get("state") != "settled":
            fcntl.flock(self.h, fcntl.LOCK_UN); self.h.close()
            raise RuntimeError(f"unsettled admission blocks dispatch: {led.get('state')} {led.get('stage')}")
        return self

    def record(self, **kw):
        write(self.ledger, dict(read(self.ledger, {}), **kw))

    def __exit__(self, *exc):  # exceptions leave ledger durable/unsettled
        fcntl.flock(self.h, fcntl.LOCK_UN); self.h.close()


def probe_group(pgid, wait=2.0):
    """absent | alive | unknown. Only ProcessLookupError proves absence."""
    end = time.monotonic() + wait
    while True:
        try: os.killpg(pgid, 0); state = "alive"
        except ProcessLookupError: return "absent"
        except PermissionError: state = "unknown"
        if time.monotonic() >= end: return state
        time.sleep(0.05)


def _request_identity(argv):
    def after(flag):
        return argv[argv.index(flag) + 1] if flag in argv[:-1] else None
    tools = []
    if "--allowedTools" in argv:
        for a in argv[argv.index("--allowedTools") + 1:]:
            if a.startswith("--"): break
            tools.append(a)
    return {"model": after("--model"), "allowed_tools": tools, "mcp_config": after("--mcp-config"),
            "tools_flag": after("--tools"), "effort": after("--effort"), "budget": after("--max-budget-usd")}


def run_stage(state_dir, run_dir, stage, argv, seconds, *, cwd=None, env=None, service=None,
              snapshot=None, cleanup=None, stdin=None):
    """One provider stage holding the global lock from before Popen through
    cleanup/reap/closed streams/snapshot/receipt; settle only on proven
    group absence + reaped leader + snapshot. service(process, deadline) is
    called repeatedly while the child is alive (mechanical MCP adapter)."""
    cleanup = cleanup or cleanup_group
    os.makedirs(run_dir, exist_ok=True)
    out, err = os.path.join(run_dir, f"{stage}.stdout"), os.path.join(run_dir, f"{stage}.stderr")
    with Admission(state_dir) as adm:
        request = {"stage": stage, "argv": list(argv), "argv_sha256": digest(list(argv)), "seconds": seconds,
                   "cwd": cwd, "env_keys": sorted(env) if env is not None else None,
                   "env_sha256": digest(env) if env is not None else None,
                   "identity": _request_identity(list(argv)), "cleanup_sha256": CLEANUP_SHA,
                   "queue_wait": adm.queue_wait, "requested_at": time.time()}
        write(os.path.join(run_dir, f"{stage}.request.json"), request)
        adm.record(state="admitted", stage=stage, run_dir=run_dir, pgid=None, admitted=time.time())
        proc, timed_out, cutoff = None, False, None
        with open(out, "wb") as o, open(err, "wb") as e:
            try:
                proc = subprocess.Popen(argv, stdout=o, stderr=e, start_new_session=True, cwd=cwd, env=env,
                                        stdin=stdin if stdin is not None else subprocess.DEVNULL)
            except Exception as exc:
                adm.record(launch_error=type(exc).__name__); raise
            start = time.monotonic(); deadline = start + seconds
            adm.record(pgid=proc.pid)
            write(os.path.join(run_dir, f"{stage}.process.json"), {"pid": proc.pid, "pgid": proc.pid,
                                                                   "started": time.time()})
            try:
                while proc.poll() is None:
                    if time.monotonic() >= deadline:
                        timed_out = True; o.flush(); cutoff = os.fstat(o.fileno()).st_size; break
                    if service: service(proc, deadline)
                    else: time.sleep(0.05)
            finally:  # always kill descendants, even when the leader already exited
                cleanup(proc)
            elapsed = time.monotonic() - start
        # streams closed here
        group = probe_group(proc.pid)
        reap = {"helper": "hybrid_process_v2" if cleanup is cleanup_group else getattr(cleanup, "__name__", "custom"),
                "helper_sha256": CLEANUP_SHA if cleanup is cleanup_group else None,
                "reaped": proc.returncode is not None, "returncode": proc.returncode, "group": group}
        snap = snapshot() if snapshot else None
        receipt = {"stage": stage, "timed_out": timed_out, "deadline_known": timed_out, "bytes_at_deadline": cutoff,
                   "elapsed": elapsed, "queue_wait": adm.queue_wait, "reap": reap, "request": request,
                   "stdout_sha256": file_sha(out), "stderr_sha256": file_sha(err),
                   "snapshot": snap, "snapshot_sha256": digest(snap) if snap is not None else None,
                   **parse_stream(out, cutoff)}
        clean = group == "absent" and reap["reaped"] and snap is not None
        receipt["settled"] = clean
        write(os.path.join(run_dir, f"{stage}.receipt.json"), receipt)
        if clean:
            adm.record(state="settled", outcome={"stage": stage, "timed_out": timed_out,
                                                 "receipt_sha256": file_sha(os.path.join(run_dir, f"{stage}.receipt.json"))})
        else:
            adm.record(state="unsettled", reason={"group": group, "reaped": reap["reaped"], "snapshot": snap is not None})
    return receipt


def recover_settle(state_dir, snapshot):
    """Only settle path for unsettled admissions: under the SAME lock require
    actual group absence (or proven launch failure) + retained streams + snapshot."""
    with Admission(state_dir, recovering=True) as adm:
        led = read(adm.ledger) or {}
        if led.get("state") == "settled": return True
        pgid, run_dir, stage = led.get("pgid"), led.get("run_dir"), led.get("stage")
        if pgid is None and not led.get("launch_error"): return False
        group = probe_group(pgid) if pgid is not None else "never_started"
        if group not in ("absent", "never_started"): return False
        streams = {}
        for s in ("stdout", "stderr"):
            p = os.path.join(run_dir or "", f"{stage}.{s}")
            if not os.path.isfile(p): return False
            streams[s] = file_sha(p)
        snap = snapshot()
        if snap is None: return False
        proof = {"group": group, "streams": streams, "snapshot_sha256": digest(snap), "recovered_at": time.time()}
        write(os.path.join(run_dir, f"{stage}.recovery.json"), dict(proof, snapshot=snap))
        adm.record(state="settled", outcome={"recovered": proof})  # receipt stays unsettled: never continuation-qualified
        return True


def parse_stream(path, cutoff=None):
    r = {"observed_models": [], "init_tools": None, "init_model": None, "terminal": None,
         "terminal_before_deadline": None, "session_ids": [], "tool_uses": [], "anomalies": [],
         "truncated_tail": False}
    inits = results = 0; offset = 0
    with open(path, "rb") as h:
        for n, line in enumerate(h, 1):
            offset += len(line)
            if not line.strip(): continue
            try: ev = json.loads(line)
            except ValueError:
                if not line.endswith(b"\n"): r["truncated_tail"] = True
                else: r["anomalies"].append({"line": n, "kind": "invalid_json"})
                continue
            if not isinstance(ev, dict): r["anomalies"].append({"line": n, "kind": "non_object"}); continue
            sid = ev.get("session_id")
            if sid and sid not in r["session_ids"]: r["session_ids"].append(sid)
            t = ev.get("type")
            if results and t != "result": r["anomalies"].append({"line": n, "kind": "event_after_result"})
            if t == "system" and ev.get("subtype") == "init":
                inits += 1
                if inits > 1: r["anomalies"].append({"line": n, "kind": "multiple_init"})
                else: r["init_tools"], r["init_model"] = ev.get("tools"), ev.get("model")
            elif t == "assistant":
                msg = ev.get("message") or {}
                m = msg.get("model")
                if m and m not in r["observed_models"]: r["observed_models"].append(m)
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        r["tool_uses"].append({"id": b.get("id"), "name": b.get("name")})
            elif t == "result":
                results += 1
                if results > 1: r["anomalies"].append({"line": n, "kind": "multiple_result"})
                else: r["terminal"], r["terminal_before_deadline"] = ev, (cutoff is None or offset <= cutoff)
    if len(r["observed_models"]) > 1: r["anomalies"].append({"kind": "multiple_models"})
    if len(r["session_ids"]) > 1: r["anomalies"].append({"kind": "multiple_sessions"})
    ids = [u["id"] for u in r["tool_uses"]]
    if len(ids) != len(set(ids)): r["anomalies"].append({"kind": "duplicate_tool_use_id"})
    if r["init_model"] and r["init_model"] != MODEL: r["anomalies"].append({"kind": "init_model_mismatch"})
    return r


def claude_argv(prompt, system, mcp_config, final_schema, limits):
    return ["claude", "--print", "--model", limits["model"], "--effort", limits["effort"],
            "--output-format", "stream-json", "--verbose", "--tools", "", "--strict-mcp-config",
            "--mcp-config", json.dumps(mcp_config), "--setting-sources", "", "--no-session-persistence",
            "--restricted", "--disable-slash-commands", "--permission-mode", "dontAsk",
            "--allowedTools", *TOOLS, "--max-budget-usd", str(limits["usd"]),
            "--json-schema", json.dumps(final_schema), "--system-prompt", system, prompt]


# ---- continuation decision (max one, durable) ----
def qualification(grade, receipt):
    """Reasons the main stage is NOT qualified; empty list means qualified."""
    bad, rq = [], (receipt or {}).get("request") or {}
    ident, snap = rq.get("identity") or {}, (receipt or {}).get("snapshot") or {}
    if (receipt or {}).get("stage") != "main": bad.append("not main stage")
    if ident.get("model") != MODEL: bad.append("requested model")
    if ident.get("allowed_tools") != TOOLS: bad.append("requested tools")
    if (receipt or {}).get("observed_models") != [MODEL]: bad.append("observed model")
    inv = (receipt or {}).get("init_tools")
    if not isinstance(inv, list) or sorted(inv) != INVENTORY: bad.append("tool inventory")
    if any(u.get("name") not in INVENTORY for u in (receipt or {}).get("tool_uses") or []): bad.append("unexpected tool use")
    if (receipt or {}).get("anomalies"): bad.append("stream anomalies")
    reap = (receipt or {}).get("reap") or {}
    if not (reap.get("group") == "absent" and reap.get("reaped") and receipt.get("settled")): bad.append("unsettled group")
    if snap.get("source_stable") is not True or snap.get("policy_unchanged") is not True: bad.append("source/policy")
    if grade.get("evaluation_status") != "observed": bad.append("grade not observed")
    if grade.get("source_current") is not True: bad.append("source not current")
    return bad


def continuation_decision(grade, receipt):
    bad = qualification(grade, receipt)
    if bad: return {"admit": False, "reason": "unqualified: " + ", ".join(bad)}
    gap = not all(grade.get(k) is True for k in ("product_passed", "negative_passed",
                                                  "regression_passed", "scope_valid"))
    missing_terminal = receipt.get("timed_out") and receipt.get("deadline_known") and receipt.get("terminal") is None
    first = {"first_timed_out": bool(receipt.get("timed_out")), "first_terminal_missing": receipt.get("terminal") is None}
    if gap: return dict(first, admit=True, kind="product_repair", reason="observed artifact gap",
                        delivery_gap=bool(missing_terminal))
    if missing_terminal: return dict(first, admit=True, kind="delivery_recovery",
                                     reason="known clean settled deadline, missing terminal")
    return {"admit": False, "reason": "no observed gap or qualified deadline"}


_ABS = re.compile(r"(?<![\w.])(?:/[^\s/:'\"<>]+){2,}/?")


def _scrub(v):
    if not isinstance(v, str): return v
    v = v.split("Traceback (most recent call last)")[0]
    return _ABS.sub("<path>", v).strip()


def feedback(grade, receipt=None):
    """Actor-safe: required rows + scope/source/binding/status + delivery gap.
    No tracebacks, absolute owner paths, oracle source, raw owner output, head."""
    rows = [{k: _scrub(r.get(k)) for k in ("id", "claim", "observed", "expected", "status")}
            for r in grade.get("required_rows", grade.get("failed_requirements", []))]
    out = {"required_rows": rows, **{k: grade.get(k) for k in
           ("evaluation_status", "scope_valid", "source_current", "local_module_binding")}}
    if receipt is not None:
        out["delivery_gap"] = bool(receipt.get("timed_out") and receipt.get("terminal") is None)
    return out


def claim_continuation(run_dir, decision):
    """Durable max-one cap enforced at every entrypoint (O_EXCL marker)."""
    if not decision.get("admit"): return False
    try: fd = os.open(os.path.join(run_dir, "CONTINUATION.claim"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError: return False
    os.write(fd, json.dumps(decision).encode()); os.close(fd)
    return True


if __name__ == "__main__":
    print(json.dumps({"tools": TOOLS, "inventory": INVENTORY, "main": MAIN, "continuation": CONT,
                      "cleanup_sha256": CLEANUP_SHA}))
    sys.exit(0)
