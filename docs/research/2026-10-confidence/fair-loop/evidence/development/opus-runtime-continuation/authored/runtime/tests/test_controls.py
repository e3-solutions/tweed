import json, os, subprocess, sys, tempfile, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import controller as c


def task(tmp, **kw):
    t = {k: None for k in c.TASK_FIELDS}
    t.update(task_id="t1", prompt="p", requirements=[], interpreter=sys.executable,
             runtime_read_paths=["/usr", "/System", "/Library", "/private/var/db", "/dev",
                                 os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix)],
             forbidden_runtime_read_paths=[], visible_commands=[], production_paths=[])
    t.update(kw); return t


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.policy = os.path.join(self.tmp, "policy"); os.makedirs(self.policy)
        open(os.path.join(self.policy, "SKILL.md"), "w").write("skill")
        self.study = os.path.join(self.tmp, "study")

    def test_1_seal_after_prepare_and_io_separation(self):
        t = task(self.tmp)
        c.prepare(self.study, t, self.policy)
        sealed = open(os.path.join(self.study, "inputs", "SEAL.json")).read()
        c.prepare(self.study, t, self.policy)  # prepare again must not overwrite inputs
        self.assertEqual(sealed, open(os.path.join(self.study, "inputs", "SEAL.json")).read())
        self.assertTrue(os.path.exists(os.path.join(self.study, "runs", "t1", "PREFLIGHT.json")))
        open(os.path.join(self.policy, "SKILL.md"), "w").write("tampered")
        with self.assertRaises(RuntimeError): c.check_seal(self.study, t, self.policy)

    def test_2_timeout_reaps_owned_group_keeps_partial_no_terminal(self):
        child = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);" \
                "print('{\"type\":\"system\",\"subtype\":\"init\",\"tools\":[]}',flush=True);time.sleep(60)"
        r = c.run_stage(os.path.join(self.tmp, "g"), os.path.join(self.tmp, "run"), "main",
                        [sys.executable, "-c", child], 1)
        self.assertTrue(r["timed_out"]); self.assertIsNone(r["terminal"])
        self.assertFalse(r["reap"]["group_alive"]); self.assertEqual(r["init_tools"], [])
        self.assertEqual(json.load(open(os.path.join(self.tmp, "g", "ADMISSION.json")))["state"], "settled")

    def test_3_global_serial_admission_main_and_repair(self):
        g, marks = os.path.join(self.tmp, "g"), os.path.join(self.tmp, "marks")
        prog = f"import os,time;open({marks!r},'a').write('s');time.sleep(0.4);open({marks!r},'a').write('e')"
        ths = [threading.Thread(target=c.run_stage, args=(g, os.path.join(self.tmp, s), s,
                                [sys.executable, "-c", prog], 10)) for s in ("main", "continuation", "main2")]
        [t.start() for t in ths]; [t.join() for t in ths]
        self.assertEqual(open(marks).read(), "se" * 3)  # never overlapping
        # incomplete admission on exception stays durable and blocks dispatch
        with self.assertRaises(FileNotFoundError):
            c.run_stage(g, os.path.join(self.tmp, "x"), "main", ["/nonexistent-binary"], 5)
        with self.assertRaises(RuntimeError):
            c.run_stage(g, os.path.join(self.tmp, "y"), "main", [sys.executable, "-c", "0"], 5)
        c.settle_explicitly(g, "operator settled failed launch")
        self.assertFalse(c.run_stage(g, os.path.join(self.tmp, "y"), "main", [sys.executable, "-c", "0"], 5)["timed_out"])

    @unittest.skipUnless(os.path.exists("/usr/bin/sandbox-exec") and subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True).returncode == 0, "GAP: sandbox_apply not permitted (nested sandbox)")
    def test_4_sandbox_prefix_denies_and_exact_interpreter(self):
        ws = os.path.join(self.tmp, "ws"); os.makedirs(ws)
        outside = os.path.join(self.tmp, "outside.txt"); open(outside, "w").write("secret")
        denied = os.path.join(os.path.realpath(sys.base_prefix), "lib")
        t = task(self.tmp, forbidden_runtime_read_paths=[os.path.join(denied, "this_is_denied.py")])
        pre = c.command_prefix(ws, t, policy_paths=[self.policy])
        def run(code):
            return subprocess.run(pre + c.visible_argv(t, ["python", "-I", "-S", "-B", "-c", code]),
                                  cwd=ws, capture_output=True, text=True, timeout=30)
        self.assertEqual(run("print(1)").stdout.strip(), "1", "baseline")
        self.assertEqual(run(f"open({os.path.join(ws,'w')!r},'w').write('x')").returncode, 0)
        self.assertNotEqual(run(f"open({outside!r}).read()").returncode, 0, "outside read")
        self.assertNotEqual(run(f"open({os.path.join(self.tmp,'o2')!r},'w')").returncode, 0, "outside write")
        self.assertNotEqual(run(f"open({os.path.join(self.policy,'SKILL.md')!r},'w')").returncode, 0, "policy write")
        self.assertNotEqual(run("import socket;socket.create_connection(('1.1.1.1',80),timeout=3)").returncode, 0)
        self.assertEqual(c.visible_argv(t, ["python", "x"])[0], sys.executable)
        # forbidden literal: create a probe file under workspace and deny it explicitly
        tgt = os.path.join(ws, "target.py"); open(tgt, "w").write("X=1")
        t2 = task(self.tmp, forbidden_runtime_read_paths=[tgt])
        pre = c.command_prefix(ws, t2)
        r = subprocess.run(pre + [sys.executable, "-I", "-S", "-c", f"open({tgt!r}).read()"],
                           cwd=ws, capture_output=True, timeout=30)
        self.assertNotEqual(r.returncode, 0, "forbidden source read denied after allow")

    def test_5_local_module_origin_rejects_installed_or_forged(self):
        ws = os.path.join(self.tmp, "ws"); os.makedirs(ws)
        open(os.path.join(ws, "localmod.py"), "w").write("X=1")
        self.assertTrue(c.module_origin(sys.executable, ws, "localmod")["local"])
        self.assertFalse(c.module_origin(sys.executable, ws, "json")["local"])  # installed stdlib
        open(os.path.join(ws, "shadow.py"), "w").write("import sys,json;sys.modules['shadow']=json")
        self.assertFalse(c.module_origin(sys.executable, ws, "shadow")["local"])

    def test_6_continuation_only_observed_gap_or_settled_deadline_max_one(self):
        ok = dict(evaluation_status="observed", product_passed=True, negative_passed=True,
                  regression_passed=True, scope_valid=True)
        settled = {"timed_out": True, "observed_models": ["claude-opus-5-5"], "init_tools": c.TOOLS + ["StructuredOutput"],
                   "reap": {"group_alive": False}}
        self.assertFalse(c.continuation_decision(ok, {"timed_out": False}, True)["admit"])
        self.assertFalse(c.continuation_decision({"evaluation_status": "unknown"}, settled, True)["admit"])
        self.assertTrue(c.continuation_decision(dict(ok, negative_passed=False), {}, True)["admit"])
        self.assertTrue(c.continuation_decision(ok, settled, True)["admit"])
        self.assertFalse(c.continuation_decision(ok, dict(settled, observed_models=["other"]), True)["admit"])
        self.assertFalse(c.continuation_decision(ok, settled, False)["admit"])
        self.assertFalse(c.continuation_decision(ok, dict(settled, reap={"group_alive": True}), True)["admit"])
        fb = c.feedback({"failed_requirements": [{"id": "r1", "claim": "c", "observed": "o", "expected": "e",
                                                  "traceback": "SECRET"}], "source_current": True})
        self.assertNotIn("SECRET", json.dumps(fb))
        run = os.path.join(self.tmp, "run"); os.makedirs(run)
        d = c.continuation_decision(ok, settled, True)
        self.assertTrue(c.claim_continuation(run, d)); self.assertFalse(c.claim_continuation(run, d))
        a = c.claude_argv("p", "s", {}, {}, c.CONT)
        self.assertEqual(a[a.index("--model") + 1], "claude-opus-5-5"); self.assertIn("--no-session-persistence", a)
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "2.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
