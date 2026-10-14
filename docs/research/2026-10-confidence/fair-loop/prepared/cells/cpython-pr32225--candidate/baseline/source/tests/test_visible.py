import hashlib,importlib.util,io,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"csv.py"
s=importlib.util.spec_from_file_location("actor_local",p);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
assert Path(M.__file__).resolve()==p.resolve()
assert Path(M.__spec__.origin).resolve()==p.resolve()
print("ACTOR_LOCAL_SOURCE",p.name,hashlib.sha256(p.read_bytes()).hexdigest())
class Visible(unittest.TestCase):
 def test_existing_sequence_fields(self):
  self.assertEqual(list(M.DictReader(io.StringIO("a,b\n1,2\n"))),[{"a":"1","b":"2"}]);o=io.StringIO();M.DictWriter(o,fieldnames=("b","a")).writerow({"a":"A","b":"B"});self.assertEqual(list(M.reader(io.StringIO(o.getvalue()))),[["B","A"]])
