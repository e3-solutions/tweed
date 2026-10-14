"""Optimized-interpreter and missing-cache refusal at real filesystem boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('verify_delivery.py')
PRELUDE = '''import json, pathlib, types, sys
namespace = {"__file__": sys.argv[1], "__name__": "component_probe"}
exec(compile(pathlib.Path(sys.argv[1]).read_text(), sys.argv[1], "exec", optimize=1), namespace)
root = pathlib.Path(sys.argv[2])
'''


class DeliveryRefusal(unittest.TestCase):
    def child(self, body):
        with tempfile.TemporaryDirectory(prefix='cp-delivery-refusal-') as directory:
            call = subprocess.run([sys.executable, '-B', '-O', '-c', PRELUDE + body,
                                   str(SCRIPT), directory], capture_output=True, text=True, timeout=20)
            self.assertEqual(call.returncode, 0, call.stderr)
            return json.loads(call.stdout)

    def test_optimized_regular_inventory_and_symlink_refusal(self):
        result = self.child('''
(root / "file").write_text("control")
regular = namespace["inventory"](root)
(root / "link").symlink_to(root / "file")
try: namespace["inventory"](root)
except ValueError as error: refusal = str(error)
else: refusal = None
print(json.dumps({"regular": list(regular), "refusal": refusal}))
''')
        self.assertEqual(result['regular'], ['file'])
        self.assertEqual(result['refusal'], 'Installed symlink refused')

    def test_optimized_installed_and_repository_drift_refused(self):
        result = self.child('''
for name in ("source", "cache", "repo"):
    (root / name).mkdir(); (root / name / "file").write_text("control")
installed = {"enabled": True, "installed_plugin": {"version": "0.7.1"},
             "source_directory": str(root / "source"), "cache_directory": str(root / "cache"),
             "files": namespace["inventory"](root / "source")}
namespace["check_installation"](installed, root / "repo")
refusals = []
for name in ("cache", "repo"):
    (root / name / "file").write_text("drift")
    try: namespace["check_installation"](installed, root / "repo")
    except ValueError as error: refusals.append(str(error))
    (root / name / "file").write_text("control")
print(json.dumps(refusals))
''')
        self.assertEqual(result, ['Installed source/cache differs', 'Installed file differs from current repository source'])

    def test_missing_main_or_followup_cache_refused_without_writes(self):
        for followup in (False, True):
            body = '''
evidence = root / "evidence"; evidence.mkdir()
cache = evidence / "current-source-rechecks"
'''
            if followup:
                body += '''cache.mkdir(); (cache / "trial").mkdir()
(cache / "input-seal.json").write_text(json.dumps({"sources": {"trial": "digest"}}))
(cache / "trial/receipt.json").write_text("{}")
'''
            body += '''before = sorted(str(p.relative_to(evidence)) for p in evidence.rglob("*"))
try: namespace["verify"](evidence)
except ValueError as error: refusal = str(error)
else: refusal = None
after = sorted(str(p.relative_to(evidence)) for p in evidence.rglob("*"))
print(json.dumps({"before": before, "after": after, "refusal": refusal}))
'''
            with self.subTest(followup=followup):
                result = self.child(body)
                self.assertEqual(result['before'], result['after'])
                self.assertEqual(result['refusal'], 'Completed CPU cache root required')

    def test_write_guard_blocks_partial_run_preparation_without_artifacts(self):
        result = self.child('''
evidence = root / "evidence"; evidence.mkdir()
namespace["protect_evidence"](evidence)
refusals = []
for action in (lambda: (evidence / "new-cache").mkdir(),
               lambda: (evidence / "input-seal.json").write_text("{}"),
               lambda: (evidence / "started.json").write_text("{}")):
    try: action()
    except ValueError as error: refusals.append(str(error))
print(json.dumps({"refusals": refusals, "remaining": list(evidence.iterdir())}))
''')
        self.assertEqual(result['remaining'], [])
        self.assertEqual(len(result['refusals']), 3)

    def test_optimized_public_projection_drift_refused_before_later_analysis(self):
        result = self.child('''
evidence = root / "evidence"; evidence.mkdir()
for name, sources in (("current-source-rechecks", {"trial": "digest"}),
                      ("followup-source-rechecks", {"trial/initial": "digest"})):
    cache = evidence / name; cache.mkdir()
    (cache / "input-seal.json").write_text(json.dumps({"sources": sources}))
    directories = ["trial"] if name.startswith("current") else ["trial/initial-original", "trial/initial-novel"]
    for relative in directories:
        (cache / relative).mkdir(parents=True)
        (cache / relative / "receipt.json").write_text("{}")
result = {"assigned": 48, "rows": [], "current_recheck_summary": {"known_agreements": 35}}
(evidence / "main-analysis.json").write_text(json.dumps(result))
public = root / "public"; (public / "results").mkdir(parents=True)
(public / "results/analysis.json").write_text(json.dumps({"assigned": 49, "rows": []}))
main = types.SimpleNamespace(r=types.SimpleNamespace(), analyze=lambda *args: result,
                            TOP_KEYS={"assigned", "rows"}, ROW_KEYS=set())
namespace["HERE"] = public
def load(name):
    if name != "analyze": raise RuntimeError("Later analysis unexpectedly called")
    return main
namespace["load"] = load
try: namespace["verify"](evidence)
except ValueError as error: refusal = str(error)
else: refusal = None
print(json.dumps(refusal))
''')
        self.assertEqual(result, 'Published main projection differs')


if __name__ == '__main__':
    unittest.main()
