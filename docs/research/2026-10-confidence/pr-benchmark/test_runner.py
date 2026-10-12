"""Infrastructure-only controls; no real-PR solver outcomes or oracle access."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SPEC=importlib.util.spec_from_file_location("pr_runner",Path(__file__).with_name("runner.py"))
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)

class RunnerControls(unittest.TestCase):
    def setUp(self):
        scratch=tempfile.TemporaryDirectory(prefix="cp-runner-tests-")
        self.addCleanup(scratch.cleanup)
        self.root=Path(scratch.name).resolve();self.workspace=self.root/"workspace";self.workspace.mkdir()
        self.tmp=self.workspace/".trial-tmp";self.tmp.mkdir()
        self.control=self.root/"control";self.control.mkdir()
        (self.workspace/".protocol").mkdir()
        (self.workspace/".protocol/SKILL.md").write_text("Frozen skill")
        (self.workspace/".git").mkdir();(self.workspace/".git/config").write_text("Frozen Git")
        (self.workspace/"source.py").write_text("print(1)\n")

    def tools(self,readonly=False):
        return runner.WorkspaceTools({"workspace":str(self.workspace),"control":str(self.control),
            "temporary":str(self.tmp),"readonly":readonly,"deadline":time.time()+10,
            "python_executable":sys.executable})

    def command(self,argv,readonly=False):
        box={};worker=self.tools(readonly)
        thread=threading.Thread(target=lambda:box.update(result=worker.execute(argv,5)));thread.start()
        while thread.is_alive():
            runner.service_commands(self.control,self.workspace,self.tmp,readonly,time.time()+10)
            time.sleep(.02)
        thread.join();return box["result"]

    def test_unknown_cost_is_not_zero(self):
        self.assertEqual(runner.known_cost([{"total_cost_usd":None},{"total_cost_usd":.5}]),(None,.5))
        self.assertEqual(runner.known_cost([{"total_cost_usd":.2},{"total_cost_usd":.5}]),(.7,.7))

    def test_missing_completion_remains_unknown(self):
        self.assertIsNone(runner.completion(None))
        self.assertIsNone(runner.completion({"result":"unfinished prose"}))
        self.assertFalse(runner.completion({"structured_output":{"complete":False,"summary":"Partial","remaining":["Check"]}}))
        for value in ({"complete":True},{"complete":True,"summary":1,"remaining":[]},
                      {"complete":True,"summary":"Done","remaining":[1]},
                      {"complete":True,"summary":"Done","remaining":[],"extra":"invalid"}):
            self.assertIsNone(runner.completion({"structured_output":value}))
        valid={"complete":True,"summary":"Done","remaining":[]}
        self.assertIsNone(runner.completion({"is_error":True,"structured_output":valid}))
        self.assertTrue(runner.completion({"structured_output":dict(valid,remaining=["Contradiction retained"])}))

    def test_path_symlink_and_immutable_package_guards(self):
        outside=self.root/"hidden";outside.write_text("Sealed")
        (self.workspace/"alias").symlink_to(outside)
        for path in ("../hidden",str(outside),"alias"):
            value,event=self.tools().call("read_file",{"path":path})
            self.assertFalse(event["ok"]);self.assertIn("error",value)
        value,event=self.tools().call("write_file",{"path":".protocol/SKILL.md","content":"tamper"})
        self.assertFalse(event["ok"]);self.assertEqual(event["error_kind"],"policy")
        self.assertEqual((self.workspace/".protocol/SKILL.md").read_text(),"Frozen skill")

    def test_callback_executes_actual_python_without_exposing_control(self):
        secret=self.control/"secret";secret.write_text("DO_NOT_READ")
        code=("from pathlib import Path\n"
              f"try:print(Path({str(secret)!r}).read_text())\n"
              "except PermissionError:print('CONTROL_DENIED')\n"
              "print(2)\n")
        result=self.command(["python3","-B","-c",code])
        self.assertEqual(result["exit_code"],0,result.get("error_output"))
        self.assertIn("CONTROL_DENIED",result["output"])
        self.assertNotIn("DO_NOT_READ",result["output"])

    def test_command_cannot_modify_protocol_or_synthetic_git(self):
        code=("from pathlib import Path\n"
              "for name in ['.protocol/SKILL.md','.git/config']:\n"
              " try:Path(name).write_text('tamper');print('UNSAFE')\n"
              " except PermissionError:print('DENIED')\n")
        result=self.command(["python3","-B","-c",code])
        self.assertEqual(result["exit_code"],0,result.get("error_output"))
        self.assertEqual(result["output"].count("DENIED"),2)
        self.assertNotIn("UNSAFE",result["output"])

    def test_reviewer_can_write_scratch_but_not_source(self):
        code=("from pathlib import Path\nimport os\n"
              "Path(os.environ['TMPDIR'],'scratch.txt').write_text('test')\n"
              "try:Path('source.py').write_text('tamper');print('UNSAFE')\n"
              "except PermissionError:print('SOURCE_DENIED')\n")
        result=self.command(["python3","-B","-c",code],True)
        self.assertEqual(result["exit_code"],0,result.get("error_output"))
        self.assertIn("SOURCE_DENIED",result["output"])
        self.assertEqual((self.workspace/"source.py").read_text(),"print(1)\n")

    def test_crossprocess_inspection_is_denied(self):
        code=("import subprocess\n"
              "try:p=subprocess.run(['/bin/ps','-ax','-o','command'],capture_output=True,text=True);print(p.returncode);print(p.stdout)\n"
              "except PermissionError:print('PS_DENIED')\n")
        result=self.command(["python3","-B","-c",code])
        self.assertEqual(result["exit_code"],0,result.get("error_output"))
        self.assertNotEqual(result["output"].splitlines()[0],"0")
        self.assertNotIn("claude",result["output"])

    def test_artifact_copy_refuses_symlink_before_read(self):
        outside=self.root/"hidden";outside.write_text("Sealed")
        (self.workspace/"alias").symlink_to(outside)
        with self.assertRaisesRegex(ValueError,"symlink"):
            runner.safe_copy(self.workspace,self.root/"result")
        self.assertFalse((self.root/"result").exists())

    def test_new_production_file_is_in_patch_and_replays(self):
        base=self.root/"base";base.mkdir();(base/"main.py").write_text("print(1)\n")
        result=self.root/"result";result.mkdir();(result/"main.py").write_text("print(2)\n")
        (result/"helper_new.py").write_text("ANSWER=2\n")
        patch=self.root/"submitted.patch"
        raw,submitted=runner.build_patch(base,result,patch,["main.py"])
        self.assertIn("helper_new.py",submitted);self.assertIn(b"ANSWER=2",raw)
        replay=self.root/"replay";runner.safe_copy(base,replay)
        subprocess.run(["/usr/bin/git","apply",str(patch)],cwd=replay,check=True,capture_output=True)
        self.assertEqual((replay/"helper_new.py").read_text(),"ANSWER=2\n")

    def test_exact_original_and_current_archive_skill_and_script(self):
        protocol=json.loads(Path(__file__).with_name("protocol.json").read_text())
        for key in ("original","current"):
            with self.subTest(package=key):
                destination=self.root/key;destination.mkdir()
                toolkit,digest=runner.snapshot_toolkit(protocol["packages"][key]["revision"],destination,protocol["packages"][key])
                self.assertTrue((toolkit/"SKILL.md").is_file());self.assertEqual(len(digest),64)

    def test_actual_cp_capture_and_validation_for_both_packages(self):
        protocol=json.loads(Path(__file__).with_name("protocol.json").read_text())
        for key in ("original","current"):
            with self.subTest(package=key):
                destination=self.root/(key+"-dispatch");destination.mkdir()
                toolkit,_=runner.snapshot_toolkit(protocol["packages"][key]["revision"],destination,protocol["packages"][key])
                self.workspace=destination/"workspace";self.workspace.mkdir()
                self.tmp=self.workspace/".trial-tmp";self.tmp.mkdir()
                self.control=destination/"control";self.control.mkdir()
                shutil.copytree(toolkit,self.workspace/".protocol")
                (self.workspace/"source.py").write_text("print(2)\n")
                (self.workspace/".gitignore").write_text(".trial-tmp/\n.confidence/\n")
                env=runner.safe_env(self.workspace,self.tmp)
                for args in (["init","-q"],["add","."],["-c","user.name=Test","-c","user.email=test@example.invalid","commit","-qm","Base"]):
                    subprocess.run([runner.GIT,*args],cwd=self.workspace,env=env,check=True,capture_output=True)
                script=str(self.workspace/".protocol/scripts/confidence.py")
                result=self.command(["python3","-B",script,"init","--title","Actual dispatch","--directory",".confidence"])
                self.assertEqual(result["exit_code"],0,result.get("error_output"))
                result=self.command(["python3","-B",script,"run","--json","--id","dispatch","--directory",".confidence","--cwd",".","--",sys.executable,"-B","source.py"])
                self.assertEqual(result["exit_code"],0,result.get("error_output"))
                capture=json.loads(result["output"])
                self.assertEqual(capture["exit_code"],0)
                record=json.loads((self.workspace/".confidence/runs/dispatch.json").read_text())
                self.assertEqual(record["workspace_start"],record["workspace"])
                self.assertEqual(record["workspace"]["kind"],"git-content-v1")
                # Author a minimal valid partial report, then validate via the
                # same exact toolkit. Missing release gates stay partial.
                contract=json.loads((self.workspace/".confidence/contract.json").read_text())
                contract["intent"].update(goal="Print two",must_happen=["Two is printed"],must_not_happen=["Wrong output"])
                contract["proof_obligations"][0].update(claim="Print two",verification="Execute source.py")
                (self.workspace/".confidence/contract.json").write_text(json.dumps(contract))
                report=json.loads((self.workspace/".confidence/report.json").read_text())
                report.update(outcome="Partial fixture",rollback="Not applicable")
                report["simplicity"]["notes"]="Pending release gates"
                report["review"]["reason"]="No required review for fixture"
                report["evidence"][0].update(status="pass",details="Actual source printed two",run_ids=["dispatch"])
                (self.workspace/".confidence/report.json").write_text(json.dumps(report))
                result=self.command(["python3","-B",script,"validate","--directory",".confidence"])
                self.assertEqual(result["exit_code"],0,result.get("error_output"))

    def test_input_mistakes_are_not_permission_denials(self):
        value,event=self.tools().call("replace_text",{"path":"source.py","old":"missing","new":"fixed"})
        self.assertFalse(event["ok"]);self.assertEqual(event["error_kind"],"tool_input")

    def test_scope_detects_unrelated_production_edits(self):
        base=self.root/"scope-base";base.mkdir()
        (base/"allowed.py").write_text("old")
        (base/"unrelated.md").write_text("old")
        result=self.root/"scope-result";shutil.copytree(base,result)
        (result/"allowed.py").write_text("new")
        (result/"unrelated.md").write_text("new")
        (result/"helper_new.py").write_text("helper")
        (result/"tests").mkdir();(result/"tests/new_test.py").write_text("test")
        self.assertEqual(runner.scope_diff(base,result,["allowed.py"]),["unrelated.md"])

    def test_context_digest_ignores_scratch_symlink_but_not_production_symlink(self):
        outside=self.root/"hidden";outside.write_text("Sealed")
        before=runner.tree_digest(self.workspace)
        (self.tmp/"fixture-link").symlink_to(outside)
        self.assertEqual(runner.tree_digest(self.workspace),before)
        (self.workspace/"production-link").symlink_to(outside)
        with self.assertRaisesRegex(ValueError,"Symlink"):
            runner.tree_digest(self.workspace)

if __name__=="__main__":unittest.main()
