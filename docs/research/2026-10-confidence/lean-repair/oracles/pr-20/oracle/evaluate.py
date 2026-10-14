"""Sealed PR acceptance grader: clean source, immutable tests, bounded OS sandbox."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

RUNTIME_READS = [Path('/System'), Path('/usr'), Path('/bin'), Path('/sbin'),
                 Path('/opt/homebrew'), Path('/Library/Frameworks'),
                 Path('/Library/Developer/CommandLineTools'), Path('/private/etc'), Path('/dev')]


def ancestors(path):
    return [path, *path.parents]


def sandbox_profile(workspace, scratch, entry):
    readers = RUNTIME_READS + [workspace, scratch]
    directories = {Path('/')}
    for path in [*readers, Path(sys.executable).resolve()]:
        directories.update(ancestors(path.parent))
    quoted = lambda value: json.dumps(str(value))
    rules = ['(version 1)', '(deny default)', '(allow process-fork)', '(allow process-exec)', '(allow signal (target same-sandbox))']
    rules.append('(allow file-read* ' + ' '.join('(subpath ' + quoted(p) + ')' for p in readers) + ')')
    rules.append('(allow file-read* ' + ' '.join('(literal ' + quoted(p) + ')' for p in directories) + ')')
    rules.append('(allow file-write* (subpath ' + quoted(workspace) + ') (subpath ' + quoted(scratch) + ') (literal "/dev/null"))')
    rules.append('(deny file-write* (subpath ' + quoted(workspace / 'tests') + '))')
    rules.append('(deny file-write* (literal ' + quoted(entry) + '))')
    rules.append('(deny network*)')
    return '\n'.join(rules)


def safe_regular(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise ValueError('Submitted production path must be a regular nonsymlink file')
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('Submitted production path has a symlink ancestor')
    return True


def copy_candidate(base, candidate, destination, production_paths):
    shutil.copytree(base, destination, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', '.claude', '.codex', '__pycache__', '.confidence'))
    allowed = set(production_paths)
    baseline_names = {p.name for p in base.iterdir()}
    reserved = {'sitecustomize.py', 'usercustomize.py', 'conftest.py', 'tests.py'} | {name + '.py' for name in sys.stdlib_module_names}
    for path in candidate.glob('*.py'):
        if path.name not in baseline_names and path.name not in reserved:
            allowed.add(path.name)
    for name in sorted(allowed):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Production scope escapes grading workspace')
        path = candidate / relative
        if not safe_regular(path):
            continue
        target = destination / relative
        if target.is_symlink():
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target, follow_symlinks=False)
        target.chmod(path.stat().st_mode & 0o777)
    return sorted(allowed)


ENTRY = '''import json,os,pathlib,subprocess,unittest
root=pathlib.Path.cwd()
for argv in [['git','init','-q'],['git','add','.'],['git','-c','user.name=Benchmark','-c','user.email=benchmark@example.invalid','commit','-qm','fixture']]:
 result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if result.returncode:raise RuntimeError('Git fixture preparation failed: '+result.stderr)
ids=json.loads(os.environ['CP_ORACLE_TEST_IDS'])
suite=unittest.defaultTestLoader.loadTestsFromNames(ids)
def leaves(s):
 for x in s:
  if isinstance(x,unittest.TestSuite):yield from leaves(x)
  else:yield x
for case in leaves(suite):
 original=getattr(case,case._testMethodName)
 def checked(original=original):
  try:original()
  except AssertionError:raise
  except BaseException as e:raise AssertionError("Required behavior raised an unexpected exception: "+type(e).__name__+": "+str(e)) from e
 setattr(case,case._testMethodName,checked)
r=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if r.wasSuccessful() and not r.skipped and r.testsRun==len(ids) else 1)
'''


def evaluate(args):
    oracle = Path(__file__).resolve().parent
    config = json.loads((oracle / 'oracle.json').read_text())
    base = oracle.parent / 'base'
    candidate = Path(args.workspace).resolve()
    if not candidate.is_dir():
        raise ValueError('Candidate workspace is unavailable')
    if not Path('/usr/bin/sandbox-exec').is_file():
        raise ValueError('This grading environment requires macOS sandbox-exec')
    with tempfile.TemporaryDirectory(prefix='cp-heldout-eval-') as name:
        outer = Path(name).resolve()
        root, scratch = outer / 'workspace', outer / 'scratch'
        scratch.mkdir()
        allowed = copy_candidate(base, candidate, root, config['production_paths'])
        for path in (oracle / 'modules').glob('*.py'):
            if not safe_regular(path):
                raise ValueError('Held-out module must be a regular file')
            shutil.copyfile(path, root / 'tests' / path.name)
        entry = root / '_sealed_grading_entry.py'
        entry.write_text(ENTRY)
        environment = {'PATH': '/Library/Developer/CommandLineTools/usr/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                       'HOME': str(scratch / 'home'), 'TMPDIR': str(scratch),
                       'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
                       'CP_ORACLE_TEST_IDS': json.dumps(config['test_ids'])}
        (scratch / 'home').mkdir()
        argv = ['/usr/bin/sandbox-exec', '-p', sandbox_profile(root, scratch, entry),
                sys.executable, '-B', str(entry)]
        try:
            result = subprocess.run(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=150)
            code, output = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as error:
            code, output = 124, str(error)
        print(json.dumps({'task_id': config['task_id'], 'exit_code': code,
                          'passed': code == 0, 'tests': config['test_ids'],
                          'production_scope': allowed,
                          'output_sha256': hashlib.sha256(output.encode()).hexdigest()}))
        print(output)
        return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    try:
        raise SystemExit(evaluate(parser.parse_args()))
    except (ValueError, OSError) as error:
        print(json.dumps({'passed': False, 'infrastructure_error': str(error)}))
        raise SystemExit(2)
