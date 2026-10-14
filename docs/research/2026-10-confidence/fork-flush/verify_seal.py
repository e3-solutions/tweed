"""Fail closed on changed prospectively frozen inputs before inference."""
import hashlib,json,pathlib
E=pathlib.Path(__file__).resolve().parent;R=E.parents[1]
def verify():
 reg=json.loads((E/'REGISTRATION.json').read_text())
 for rel,expected in reg['files_sha256'].items():
  p=R/rel
  assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected, 'Changed sealed input: '+rel
 return reg
if __name__=='__main__':
 verify();print('Frozen input hashes verified.')
