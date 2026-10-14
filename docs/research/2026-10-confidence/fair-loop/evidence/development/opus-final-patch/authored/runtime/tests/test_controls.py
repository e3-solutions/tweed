import fcntl, json, os, signal, subprocess, sys, tempfile, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import controller as c


def task(tmp, **kw):
    base = os.path.join(tmp, "base"); os.makedirs(base, exist_ok=True)
    if not os.path.exists(os.path.join(base, "mod.py")): open(os.path.join(base, "mod.py"), "w").write("X=1\n")
    t = {k: None for k in c.TASK_FIELDS}
    t.update(task_id="t1", prompt="p", requirements=[], interpreter=sys.executable, base_snapshot=base,
             runtime_read_paths=[os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix)],
             forbidden_runtime_read_paths=[], visible_commands=[], production_paths=["mod.py"])
    t.update(kw); return t


def alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.policy = os.path.join(self.tmp, "policy"); os.makedirs(self.policy)
        open(os.path.join(self.policy, "SKILL.md"), "w").write("skill")
        self.study = os.path.join(self.tmp, "study")
        self.ws = os.path.join(self.tmp, "ws"); os.makedirs(self.ws)
        self.snap = c.stage_snapshot(self.ws, self.policy, c.inventory(self.policy), ["mod.py"])

    def test_1_seal_base_policy_mutation_controls(self):
        t = task(self.tmp)
        ctl = c.prepare(self.study, t, self.policy)
        self.assertEqual(ctl, {"base": True, "policy": True})
        sealed = open(os.path.join(self.study, "inputs", "SEAL.json")).read()
        self.assertEqual(open(os.path.join(t["base_snapshot"], "mod.py")).read(), "X=1\n")  # restored
        c.prepare(self.study, t, self.policy)  # input seal never overwritten
        self.assertEqual(sealed, open(os.path.join(self.study, "inputs", "SEAL.json")).read())
        self.assertTrue(os.path.exists(os.path.join(self.study, "runs", "t1", "PREFLIGHT.json")))
        open(os.path.join(t["base_snapshot"], "mod.py"), "a").write("Y=2\n")  # authentic base drift
        with self.assertRaises(RuntimeError): c.check_seal(self.study, t, self.policy)
        open(os.path.join(t["base_snapshot"], "mod.py"), "w").write("X=1\n")
        c.check_seal(self.study, t, self.policy)
        open(os.path.join(self.policy, "SKILL.md"), "w").write("tampered")  # shadow policy drift
        with self.assertRaises(RuntimeError): c.check_seal(self.study, t, self.policy)
        os.symlink(self.tmp, os.path.join(t["base_snapshot"], "loop"))  # no symlink recursion
        self.assertEqual(c.inventory(t["base_snapshot"])["loop"], {"symlink": self.tmp})

    def test_2_resistant_grandchild_cleanup_or_unsettled(self):
        g, pidf = os.path.join(self.tmp, "g"), os.path.join(self.tmp, "gc.pid")
        gc = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"
        parent = f"import subprocess,sys;p=subprocess.Popen([sys.executable,'-c',{gc!r}]);open({pidf!r},'w').write(str(p.pid))"
        held = []
        def snap():  # source capture happens while the global lock is still held
            h = open(os.path.join(g, "provider.lock"), "a+")
            try: fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB); held.append(False)
            except BlockingIOError: held.append(True)
            h.close(); return self.snap()
        r = c.run_stage(g, os.path.join(self.tmp, "run"), "main", [sys.executable, "-c", parent], 20, snapshot=snap)
        self.assertEqual(held, [True]); self.assertFalse(r["timed_out"])
        self.assertEqual(r["reap"]["group"], "absent"); self.assertTrue(r["settled"])
        self.assertEqual(r["reap"]["helper_sha256"], c.CLEANUP_SHA)
        self.assertFalse(alive(int(open(pidf).read())), "grandchild survived parent exit")
        # negative: cleanup that does not kill descendants -> durable unsettled, blocks dispatch
        os.remove(pidf)
        r2 = c.run_stage(g, os.path.join(self.tmp, "run2"), "main", [sys.executable, "-c", parent], 20,
                         snapshot=self.snap, cleanup=lambda p: p.wait())
        self.assertFalse(r2["settled"]); self.assertEqual(r2["reap"]["group"], "alive")
        self.assertEqual(json.load(open(os.path.join(g, "ADMISSION.json")))["state"], "unsettled")
        with self.assertRaises(RuntimeError):
            c.run_stage(g, os.path.join(self.tmp, "run3"), "main", [sys.executable, "-c", "0"], 5, snapshot=self.snap)
        self.assertFalse(hasattr(c, "settle_explicitly"))  # no clearing note
        self.assertFalse(c.recover_settle(g, self.snap))  # group still alive
        gpid = int(open(pidf).read()); os.kill(gpid, signal.SIGKILL)
        for _ in range(40):
            if not alive(gpid): break
            time.sleep(0.05)
        self.assertTrue(c.recover_settle(g, self.snap))
        # missing snapshot never settles
        r4 = c.run_stage(g, os.path.join(self.tmp, "run4"), "main", [sys.executable, "-c", "0"], 5)
        self.assertFalse(r4["settled"])

    def test_3_global_serial_admission_queue_separate(self):
        g, marks = os.path.join(self.tmp, "g"), os.path.join(self.tmp, "marks")
        prog = f"import time;open({marks!r},'a').write('s');time.sleep(0.4);open({marks!r},'a').write('e')"
        rs = []
        ths = [threading.Thread(target=lambda s=s: rs.append(c.run_stage(g, os.path.join(self.tmp, s), s,
                                [sys.executable, "-c", prog], 10, snapshot=self.snap))) for s in ("main", "continuation", "m2")]
        [t.start() for t in ths]; [t.join() for t in ths]
        self.assertEqual(open(marks).read(), "se" * 3)
        self.assertTrue(max(r["queue_wait"] for r in rs) > 0.3 and all(r["elapsed"] < 5 for r in rs))
        calls = []
        r = c.run_stage(g, os.path.join(self.tmp, "svc"), "main", [sys.executable, "-c", "import time;time.sleep(0.3)"], 10,
                        snapshot=self.snap, cwd=self.ws, env={"PATH": "/usr/bin:/bin"},
                        service=lambda p, d: (calls.append(p.poll()), time.sleep(0.02)))
        self.assertTrue(len(calls) > 3 and r["settled"] and r["request"]["cwd"] == self.ws)
        with self.assertRaises(FileNotFoundError):
            c.run_stage(g, os.path.join(self.tmp, "x"), "main", ["/nonexistent-binary"], 5, snapshot=self.snap)
        with self.assertRaises(RuntimeError):
            c.run_stage(g, os.path.join(self.tmp, "y"), "main", [sys.executable, "-c", "0"], 5, snapshot=self.snap)
        self.assertTrue(c.recover_settle(g, self.snap))  # proven never-started + retained streams
        self.assertTrue(c.run_stage(g, os.path.join(self.tmp, "y"), "main", [sys.executable, "-c", "0"], 5,
                                    snapshot=self.snap)["settled"])

    @unittest.skipUnless(os.path.exists("/usr/bin/sandbox-exec") and subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True).returncode == 0, "GAP: nested sandbox_apply blocked; root native runs after settlement")
    def test_4_sandbox_prefix_denies_and_exact_interpreter(self):
        tmpd = os.path.join(self.tmp, "scratch"); os.makedirs(tmpd)
        outside = os.path.join(self.tmp, "outside.txt"); open(outside, "w").write("secret")
        tgt = os.path.join(self.ws, "target.py"); open(tgt, "w").write("X=1")
        t = task(self.tmp, forbidden_runtime_read_paths=[tgt])
        pre = c.command_prefix(self.ws, tmpd, t, policy_paths=[self.policy])
        def run(code):
            return subprocess.run(pre + c.visible_argv(t, ["python", "-I", "-S", "-B", "-c", code]),
                                  cwd=self.ws, capture_output=True, text=True, timeout=30)
        base = run("print(1)")
        self.assertEqual(base.stdout.strip(), "1", f"baseline cannot start: {base.returncode} {base.stderr}")
        self.assertEqual(run(f"open({os.path.join(self.ws,'w')!r},'w').write('x')").returncode, 0)
        self.assertNotEqual(run(f"open({outside!r}).read()").returncode, 0, "outside read")
        self.assertNotEqual(run(f"open({os.path.join(self.tmp,'o2')!r},'w')").returncode, 0, "outside write")
        self.assertNotEqual(run(f"open({os.path.join(self.policy,'SKILL.md')!r},'w')").returncode, 0, "policy write")
        self.assertNotEqual(run(f"open({tgt!r}).read()").returncode, 0, "forbidden literal after allow")
        self.assertEqual(c.visible_argv(t, ["python", "x"])[0], sys.executable)

    def test_5_parse_stream_retains_terminal_and_anomalies(self):
        g, run = os.path.join(self.tmp, "g"), os.path.join(self.tmp, "run")
        lines = ['{"type":"system","subtype":"init","tools":[],"session_id":"s"}',
                 '{"type":"assistant","message":{"model":"claude-opus-5-5","content":[{"type":"tool_use","id":"t1","name":"x"}]}}',
                 '{"type":"result","subtype":"success","result":"done"}']
        prog = "import time\n" + "".join(f"print({l!r},flush=True)\n" for l in lines) + "time.sleep(60)\n"
        r = c.run_stage(g, run, "main", [sys.executable, "-c", prog], 1.5, snapshot=self.snap)
        self.assertTrue(r["timed_out"]); self.assertEqual(r["terminal"]["result"], "done")
        self.assertTrue(r["terminal_before_deadline"]); self.assertEqual(r["tool_uses"], [{"id": "t1", "name": "x"}])
        p = os.path.join(self.tmp, "s.jsonl")
        open(p, "w").write("\n".join([lines[0], "not json", lines[0],
                                      lines[1].replace("claude-opus-5-5", "other"), lines[1], lines[2], lines[2], lines[1]]) + "\n{\"trunc")
        kinds = {a["kind"] for a in c.parse_stream(p)["anomalies"]}
        self.assertTrue({"invalid_json", "multiple_init", "multiple_result", "multiple_models",
                         "duplicate_tool_use_id", "event_after_result"} <= kinds, kinds)
        self.assertTrue(c.parse_stream(p)["truncated_tail"])

    def test_6_continuation_exact_qualification_max_one(self):
        ok = dict(evaluation_status="observed", source_current=True, product_passed=True, negative_passed=True,
                  regression_passed=True, scope_valid=True)
        snap = {"source_stable": True, "policy_unchanged": True}
        good = {"stage": "main", "timed_out": True, "deadline_known": True, "terminal": None, "settled": True,
                "observed_models": [c.MODEL], "init_tools": c.TOOLS + ["StructuredOutput"], "anomalies": [],
                "tool_uses": [{"id": "a", "name": c.TOOLS[1]}], "reap": {"group": "absent", "reaped": True},
                "snapshot": snap, "request": {"identity": c._request_identity(c.claude_argv("p", "s", {}, {}, c.MAIN))}}
        D = c.continuation_decision
        self.assertEqual(D(ok, good)["kind"], "delivery_recovery")  # even if artifact passes
        self.assertEqual(D(dict(ok, negative_passed=False), dict(good, timed_out=False, deadline_known=False))["kind"], "product_repair")
        self.assertFalse(D(dict(ok, negative_passed=False), {})["admit"])  # receipt={} rejected
        for bad in (dict(good, observed_models=["other"]), dict(good, init_tools=c.TOOLS + ["StructuredOutput", "Bash"]),
                    dict(good, init_tools=c.TOOLS), dict(good, tool_uses=[{"id": "b", "name": "Bash"}]),
                    dict(good, snapshot=dict(snap, policy_unchanged=False)), dict(good, snapshot=dict(snap, source_stable=False)),
                    dict(good, reap={"group": "unknown", "reaped": True}), dict(good, settled=False),
                    dict(good, anomalies=[{"kind": "multiple_result"}]), dict(good, stage="continuation"),
                    dict(good, terminal={"type": "result", "result": "complete"}, timed_out=False, deadline_known=False)):
            self.assertFalse(D(dict(ok, negative_passed=False) if bad.get("terminal") is None else ok, bad)["admit"]
                             if bad.get("terminal") is None else D(ok, bad)["admit"])
        self.assertFalse(D(dict(ok, evaluation_status="unknown"), good)["admit"])
        self.assertFalse(D(dict(ok, source_current=False), good)["admit"])
        fb = c.feedback({"required_rows": [{"id": "r1", "claim": "c", "status": "fail", "expected": "e",
                         "observed": "bad at /Users/owner/secret/x.py line 3\nTraceback (most recent call last): SECRET"}],
                         "source_current": True, "evaluation_status": "observed"}, good)
        s = json.dumps(fb); self.assertNotIn("SECRET", s); self.assertNotIn("/Users/owner", s); self.assertTrue(fb["delivery_gap"])
        run = os.path.join(self.tmp, "run"); os.makedirs(run)
        d = D(ok, good)
        self.assertTrue(c.claim_continuation(run, d)); self.assertFalse(c.claim_continuation(run, d))
        a = c.claude_argv("p", "s", {}, {}, c.CONT)
        self.assertEqual(a[a.index("--model") + 1], c.MODEL); self.assertEqual(a[a.index("--max-budget-usd") + 1], "2.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
