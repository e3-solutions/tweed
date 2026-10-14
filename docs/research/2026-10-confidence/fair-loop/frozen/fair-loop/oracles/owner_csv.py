import io
import unittest
import product_under_test as M

class Owner(unittest.TestCase):
 def test_positive_reader_iterator_reused_across_rows(self):
  reader=M.DictReader(io.StringIO('tea,120,green\ncoffee,250,black,imported\nwater,0\n'),fieldnames=iter(('drink','cents','note')),restkey='overflow',restval='<missing>')
  self.assertEqual(list(reader),[{'drink':'tea','cents':'120','note':'green'},{'drink':'coffee','cents':'250','note':'black','overflow':['imported']},{'drink':'water','cents':'0','note':'<missing>'}])
 def test_positive_writer_iterator_header_and_data_roundtrip(self):
  output=io.StringIO(newline='');fields=(name for name in ('drink','note'))
  writer=M.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows([{'drink':'café','note':'a, b'},{'drink':'tea','note':'first\nsecond'}])
  self.assertEqual(list(M.reader(io.StringIO(output.getvalue(),newline=''))),[['drink','note'],['café','a, b'],['tea','first\nsecond']])
 def test_negative_extra_key_and_invalid_argument(self):
  w=M.DictWriter(io.StringIO(),fieldnames=iter(('a','b')),extrasaction='raise')
  with self.assertRaises(ValueError):w.writerow({'a':'1','unknown':'2'})
  for factory in (M.DictReader,M.DictWriter):
   with self.subTest(factory=factory):
    with self.assertRaises(TypeError):factory(io.StringIO(),fieldnames=42)
 def test_regression_sequences_default_header_and_ignore(self):
  self.assertEqual(list(M.DictReader(io.StringIO('a,b\n1,2\n'))),[{'a':'1','b':'2'}])
  fields=['a'];output=io.StringIO();writer=M.DictWriter(output,fieldnames=fields,extrasaction='ignore',restval='missing')
  fields.append('b');writer.writerow({'a':'one','unused':'ignored'})
  self.assertEqual(list(M.reader(io.StringIO(output.getvalue()))),[['one','missing']])
  output=io.StringIO();writer=M.DictWriter(output,fieldnames=('b','a'));writer.writerow({'a':'A','b':'B'})
  self.assertEqual(list(M.reader(io.StringIO(output.getvalue()))),[['B','A']])
