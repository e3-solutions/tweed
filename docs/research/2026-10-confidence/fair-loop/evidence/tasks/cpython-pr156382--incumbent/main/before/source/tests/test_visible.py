import hashlib,importlib.util,io,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"configparser.py"
s=importlib.util.spec_from_file_location("actor_local",p);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
assert Path(M.__file__).resolve()==p.resolve()
assert Path(M.__spec__.origin).resolve()==p.resolve()
print("ACTOR_LOCAL_SOURCE",p.name,hashlib.sha256(p.read_bytes()).hexdigest())
class Visible(unittest.TestCase):
 def test_existing_default_delimiters(self):
  p=M.ConfigParser();p.read_string("[s]\nfull name=Ada\ncount: 7\n");self.assertEqual(p.get("s","full name"),"Ada");self.assertEqual(p.getint("s","count"),7)
