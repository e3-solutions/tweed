"""Pretrial OS-boundary controls using dummy files, never actual credentials."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sealed_oracle_runner', HERE / 'oracle_runner.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


def boundary_checks():
    with tempfile.TemporaryDirectory(prefix='cp-grade-boundary-') as name:
        outer = Path(name).resolve()
        workspace, scratch = outer / 'grade', outer / 'scratch'
        workspace.mkdir()
        scratch.mkdir()
        (workspace / 'tests').mkdir()
        protected = workspace / 'tests' / 'fixed.py'
        protected.write_text('trusted')
        outside = outer / 'dummy-secret'
        outside.write_text('dummy, not a real secret')
        (workspace / 'escape-link').symlink_to(outside)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        entry = workspace / '_sealed.py'
        program = '''import json,os,pathlib,socket
checks={}
def denied(name, operation):
 try:operation();checks[name]=False
 except PermissionError:checks[name]=True
outside=pathlib.Path(OUTSIDE)
root=pathlib.Path(ROOT)
denied('outside_read',outside.read_text)
denied('symlink_read',(root/'escape-link').read_text)
denied('outside_write',lambda: outside.write_text('changed'))
denied('immutable_test',lambda:(root/'tests/fixed.py').write_text('changed'))
denied('immutable_entry',lambda:pathlib.Path(__file__).write_text('changed'))
s=socket.socket();s.settimeout(1)
denied('network',lambda:s.connect(('127.0.0.1',PORT)))
checks['no_auth_env']=not any(k in os.environ for k in ['ANTHROPIC_API_KEY','OPENAI_API_KEY','GITHUB_TOKEN'])
(pathlib.Path(SCRATCH)/'allowed').write_text('allowed');checks['scratch_write']=True
print(json.dumps(checks));raise SystemExit(0 if all(checks.values())else1)
'''.replace('OUTSIDE', repr(str(outside))).replace('ROOT', repr(str(workspace))).replace('PORT', str(port)).replace('SCRATCH', repr(str(scratch))).replace('else1', 'else 1')
        entry.write_text(program)
        environment = {'PATH': '/Library/Developer/CommandLineTools/usr/bin:/opt/homebrew/bin:/usr/bin:/bin',
                       'HOME': str(scratch), 'TMPDIR': str(scratch),
                       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
        result = subprocess.run(['/usr/bin/sandbox-exec', '-p',
                                 grader.sandbox_profile(workspace, scratch, entry),
                                 sys.executable, '-B', str(entry)], cwd=workspace,
                                env=environment, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10)
        listener.close()
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        checks = json.loads(result.stdout)
        assert protected.read_text() == 'trusted'
        assert outside.read_text() == 'dummy, not a real secret'
        try:
            grader.safe_regular(workspace / 'escape-link')
            raise AssertionError('Symlink production source accepted')
        except ValueError:
            checks['symlink_submission_refused'] = True
        return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = boundary_checks()
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
