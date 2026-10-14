import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("csv_local_fieldnames", ROOT / "csv.py")
csv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csv)


def rows(text):
    return list(csv.reader(io.StringIO(text)))


class DictReaderFieldnamesIter(unittest.TestCase):
    def test_iterator_fieldnames_multiple_rows(self):
        r = csv.DictReader(io.StringIO("1,2,3\n4,5,6\n"), iter(["a", "b", "c"]))
        self.assertEqual(r.fieldnames, ["a", "b", "c"])
        self.assertEqual(list(r), [{"a": "1", "b": "2", "c": "3"},
                                   {"a": "4", "b": "5", "c": "6"}])
        self.assertEqual(r.fieldnames, ["a", "b", "c"])

    def test_generator_fieldnames_restkey_restval(self):
        r = csv.DictReader(io.StringIO("1,2,3,4\n5\n"),
                           (k for k in ["a", "b", "c"]),
                           restkey="_rest", restval="DEF")
        self.assertEqual(list(r), [
            {"a": "1", "b": "2", "c": "3", "_rest": ["4"]},
            {"a": "5", "b": "DEF", "c": "DEF"},
        ])

    def test_list_fieldnames_identity_preserved(self):
        names = ["a", "b"]
        r = csv.DictReader(io.StringIO("1,2,3\n4,5,6\n"), names)
        self.assertIs(r.fieldnames, names)
        self.assertEqual(next(r), {"a": "1", "b": "2", None: ["3"]})
        names.append("c")
        self.assertEqual(next(r), {"a": "4", "b": "5", "c": "6"})

    def test_tuple_and_default_header(self):
        r = csv.DictReader(io.StringIO("1,2\n"), ("x", "y"))
        self.assertEqual(r.fieldnames, ("x", "y"))
        self.assertEqual(list(r), [{"x": "1", "y": "2"}])
        r = csv.DictReader(io.StringIO("h1,h2\n1,2\n"))
        self.assertEqual(list(r), [{"h1": "1", "h2": "2"}])
        self.assertEqual(r.fieldnames, ["h1", "h2"])

    def test_noniterable_fieldnames_raise(self):
        for bad in (1, object(), 3.5):
            with self.assertRaises(TypeError):
                csv.DictReader(io.StringIO(""), bad)


class DictWriterFieldnamesIter(unittest.TestCase):
    def test_iterator_fieldnames_header_and_rows(self):
        out = io.StringIO()
        w = csv.DictWriter(out, iter(["b", "a"]))
        w.writeheader()
        w.writerow({"a": "1", "b": "2"})
        w.writerows([{"a": "x,y"}, {"b": 'q"uo\nte', "a": "é€"}])
        self.assertEqual(rows(out.getvalue()), [
            ["b", "a"], ["2", "1"], ["", "x,y"], ['q"uo\nte', "é€"]])
        self.assertIn('"x,y"', out.getvalue())
        self.assertIn('"q""uo\nte"', out.getvalue())

    def test_iterator_extrasaction(self):
        w = csv.DictWriter(io.StringIO(), iter(["a"]))
        with self.assertRaises(ValueError):
            w.writerow({"a": 1, "z": 2})
        with self.assertRaises(ValueError):
            w.writerow({"a": 1, "z": 2})
        out = io.StringIO()
        w = csv.DictWriter(out, (k for k in ["a", "b"]), extrasaction="ignore",
                           restval="R")
        w.writerow({"a": 1, "z": 2})
        w.writerow({"b": 3, "z": 2})
        self.assertEqual(rows(out.getvalue()), [["1", "R"], ["R", "3"]])

    def test_list_fieldnames_identity_preserved(self):
        names = ["a"]
        out = io.StringIO()
        w = csv.DictWriter(out, names)
        self.assertIs(w.fieldnames, names)
        names.append("b")
        w.writerow({"a": 1, "b": 2})
        self.assertEqual(rows(out.getvalue()), [["1", "2"]])

    def test_noniterable_fieldnames_raise(self):
        for bad in (1, object(), 3.5):
            with self.assertRaises(TypeError):
                csv.DictWriter(io.StringIO(), bad)


if __name__ == "__main__":
    unittest.main()
