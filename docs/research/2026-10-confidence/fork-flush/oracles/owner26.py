import contextlib,importlib.machinery,importlib.util,io,json
from pathlib import Path
import unittest
loader=importlib.machinery.SourceFileLoader('receipt_owner',str(Path.cwd()/'bonaparte'))
spec=importlib.util.spec_from_loader(loader.name,loader);R=importlib.util.module_from_spec(spec);loader.exec_module(R)
class Owner(unittest.TestCase):
 def test_positive_boundary_and_unicode(self):
  for value in ('small','x'*4083,'é'*2000):
   data={'value':value};out=io.StringIO()
   with contextlib.redirect_stdout(out):R.emit(data)
   raw=out.getvalue().encode('utf-8')
   self.assertLessEqual(len(raw),4096);self.assertTrue(raw.endswith(b'\n'));self.assertEqual(json.loads(raw),data)
 def test_negative_overflow_is_not_emitted(self):
  for value in ('x'*4084,'😀'*1024):
   out=io.StringIO()
   with contextlib.redirect_stdout(out):
    try:R.emit({'value':value})
    except RuntimeError:pass
   self.assertEqual(out.getvalue(),'','Oversized receipt leaked to stdout')
