"""Behavioral parser checks; source binding is independently supplied by entry."""
import io
import unittest
import product_under_test as M

class Owner(unittest.TestCase):
 def test_positive_configured_whitespace_delimiters(self):
  for delimiter in (' ', '\t'):
   for key,value in [('colour','dark blue'),('fee_cents','125'),('unicode','café')]:
    with self.subTest(delimiter=repr(delimiter),key=key):
     parser=M.ConfigParser(delimiters=(delimiter,'='))
     parser.read_file(io.StringIO('[settings]\n'+key+delimiter+value+'\nextra=ordinary\n'))
     self.assertEqual(parser.get('settings',key),value)
     self.assertEqual(parser.get('settings','extra'),'ordinary')
 def test_positive_values_and_no_value_options(self):
  p=M.ConfigParser(delimiters=(' ','='),allow_no_value=True)
  p.read_string('[s]\nmode fast safe\ncount 27\nflag\n')
  self.assertEqual(p['s']['mode'],'fast safe');self.assertEqual(p.getint('s','count'),27);self.assertIsNone(p['s']['flag'])
 def test_negative_non_delimiter_whitespace_keeps_key_meaning(self):
  for delimiters,key in [(('=',':'),'full name'),((' ','='),'full\tname'),(('\t','='),'full name')]:
   p=M.ConfigParser(delimiters=delimiters);p.read_string('[s]\n'+key+'=Ada Lovelace\n')
   self.assertEqual(p.get('s',key),'Ada Lovelace')
 def test_negative_malformed_and_duplicate_still_rejected(self):
  for text,error in [('[s]\nmissing_value\n',M.ParsingError),('[s]\nkey one\nkey two\n',M.DuplicateOptionError)]:
   with self.subTest(error=error):
    p=M.ConfigParser(delimiters=(' ','='),strict=True,allow_no_value=False)
    with self.assertRaises(error):p.read_string(text)
 def test_regression_default_interpolation_comments_and_roundtrip(self):
  p=M.ConfigParser();p.read_string('[DEFAULT]\nroot=/data\n[s]\n# ignored\npath=%(root)s/report\nfull name = Ada\n')
  self.assertEqual(p.get('s','path'),'/data/report');self.assertEqual(p.get('s','full name'),'Ada')
  output=io.StringIO();p.write(output);q=M.ConfigParser();q.read_string(output.getvalue())
  self.assertEqual(q.get('s','path'),'/data/report');self.assertEqual(q.get('s','full name'),'Ada')
