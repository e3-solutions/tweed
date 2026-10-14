import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("csv_local_fieldnames", ROOT / "csv.py")
csv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csv)


class DictWriterFieldnamesTests(unittest.TestCase):
    def test_iterator_fieldnames_header_and_rows(self):
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=iter(["f1", "f2", "f3"]))
        w.writeheader()
        w.writerow({"f1": 10, "f3": "abc"})
        w.writerows([{"f2": "x"}, {"f1": 1, "f2": 2, "f3": 3}])
        self.assertEqual(out.getvalue(),
                         "f1,f2,f3\r\n10,,abc\r\n,x,\r\n1,2,3\r\n")
        self.assertEqual(w.fieldnames, ["f1", "f2", "f3"])

    def test_generator_fieldnames_quoting_unicode_newlines(self):
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=(n for n in ["é", "b,c"]))
        w.writeheader()
        w.writerow({"é": "line1\nline2", "b,c": 'q"t'})
        w.writerow({"é": "ü"})
        self.assertEqual(list(csv.reader(io.StringIO(out.getvalue()))),
                         [["é", "b,c"], ["line1\nline2", 'q"t'], ["ü", ""]])

    def test_iterator_extrasaction(self):
        w = csv.DictWriter(io.StringIO(), fieldnames=iter(["a"]))
        with self.assertRaises(ValueError):
            w.writerow({"a": 1, "z": 2})
        with self.assertRaises(ValueError):
            w.writerow({"a": 1, "z": 2})
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=iter(["a"]), extrasaction="ignore")
        w.writerow({"a": 1, "z": 2})
        w.writerow({"a": 3, "z": 4})
        self.assertEqual(out.getvalue(), "1\r\n3\r\n")

    def test_sequence_fieldnames_not_copied(self):
        names = ["a"]
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=names)
        self.assertIs(w.fieldnames, names)
        names.append("b")
        w.writerow({"a": 1, "b": 2})
        self.assertEqual(out.getvalue(), "1,2\r\n")
        t = ("x", "y")
        self.assertIs(csv.DictWriter(io.StringIO(), fieldnames=t).fieldnames, t)

    def test_noniterable_fieldnames_rejected(self):
        with self.assertRaises(TypeError):
            csv.DictWriter(io.StringIO(), fieldnames=5)


class DictReaderFieldnamesTests(unittest.TestCase):
    def test_iterator_fieldnames_multiple_rows(self):
        r = csv.DictReader(io.StringIO("1,2,3\r\n4,5,6\r\n"),
                           fieldnames=iter(["a", "b", "c"]))
        self.assertEqual(list(r), [{"a": "1", "b": "2", "c": "3"},
                                   {"a": "4", "b": "5", "c": "6"}])
        self.assertEqual(r.fieldnames, ["a", "b", "c"])

    def test_iterator_restkey_restval(self):
        r = csv.DictReader(io.StringIO("1,2,3,4\r\n5\r\n"),
                           fieldnames=(n for n in ["a", "b"]),
                           restkey="_rest", restval="DEF")
        self.assertEqual(list(r), [{"a": "1", "b": "2", "_rest": ["3", "4"]},
                                   {"a": "5", "b": "DEF"}])

    def test_default_header_and_sequence(self):
        r = csv.DictReader(io.StringIO('h1,"h,2"\r\n"x\ny",é\r\n'))
        self.assertEqual(list(r), [{"h1": "x\ny", "h,2": "é"}])
        names = ["a"]
        r = csv.DictReader(io.StringIO("1,2\r\n"), fieldnames=names)
        self.assertIs(r.fieldnames, names)
        names.append("b")
        self.assertEqual(list(r), [{"a": "1", "b": "2"}])

    def test_noniterable_fieldnames_rejected(self):
        with self.assertRaises(TypeError):
            csv.DictReader(io.StringIO("1\r\n"), fieldnames=5)


if __name__ == "__main__":
    unittest.main()
