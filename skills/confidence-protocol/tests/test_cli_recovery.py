"""Recovery hints preserve failure states and never fabricate verification commands."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

from support import SCRIPT, load_confidence

core = load_confidence('recovery_core')

class RecoveryTest(unittest.TestCase):
    def test_run_help_explains_distinct_path_defaults(self):
        result=subprocess.run([sys.executable,str(SCRIPT),'run','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        text=' '.join(result.stdout.split())
        self.assertIn('relative to caller cwd, not --cwd',text)
        self.assertIn('generated when omitted',text)

    def test_duplicate_capture_retains_record_and_exit_code(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)/'.confidence'
            argv=[sys.executable,str(SCRIPT),'run','--directory',str(directory),'--id','same','--',sys.executable,'-c','print(1)']
            self.assertEqual(subprocess.run(argv,capture_output=True).returncode,0)
            path=directory/'runs/same.json';before=path.read_bytes()
            result=subprocess.run(argv,capture_output=True,text=True)
            self.assertEqual(result.returncode,125)
            self.assertIn('omit --id',result.stderr)
            self.assertIn('reuse the existing record',result.stderr)
            self.assertEqual(path.read_bytes(),before)

    def test_missing_evidence_offers_choice_without_initializing(self):
        with tempfile.TemporaryDirectory() as name:
            missing=Path(name)/'absent'
            result=subprocess.run([sys.executable,str(SCRIPT),'validate','--directory',str(missing)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('If starting a new task',result.stderr)
            self.assertFalse((missing / "contract.json").exists())
            self.assertFalse((missing / "report.json").exists())

    def test_completion_hint_preserves_required_gap_failure(self):
        args=SimpleNamespace(directory='.confidence',require_complete=True)
        output=io.StringIO()
        with patch.object(core,'load_and_validate',return_value=({}, {}, [])), patch.object(core,'completion_errors',return_value=['required proof remains partial']),redirect_stderr(output):
            self.assertEqual(core.command_validate(args),1)
        self.assertIn('without --require-complete',output.getvalue())
        self.assertIn('does not establish completion',output.getvalue())

    def test_stale_hint_does_not_echo_or_execute_original_command(self):
        binding={'kind':'git-content-v1','root':'/tmp','sha256':'a'*64}
        record={'version':2,'id':'old','cwd':'/tmp','workspace_start':binding,'workspace':binding,'argv':['sensitive-original-argument']}
        with patch.object(core,'git_workspace_fingerprint',return_value={**binding,'sha256':'b'*64}):
            errors=core.validate_supporting_workspace(record,Path('/tmp/.confidence'))
        self.assertIn('then record that ID',errors[0])
        self.assertNotIn('sensitive-original-argument',errors[0])

if __name__=='__main__':unittest.main()
