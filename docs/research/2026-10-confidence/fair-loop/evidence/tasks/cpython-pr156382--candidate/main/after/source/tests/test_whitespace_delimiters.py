import importlib.util
import io
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "configparser_local_ws", ROOT / "configparser.py")
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


class WhitespaceDelimiterTests(unittest.TestCase):
    def test_space_delimiter_splits_at_first_space(self):
        p = cp.ConfigParser(delimiters=(" ", "="))
        p.read_string("[s]\ncolour dark blue\nfull=x y\nwide   a  b\n")
        self.assertEqual(dict(p["s"]),
                         {"colour": "dark blue", "full": "x y", "wide": "a  b"})

    def test_tab_delimiter(self):
        p = cp.ConfigParser(delimiters=("\t",))
        p.read_string("[s]\nfull name\tdark\tblue\nother key \t v\n")
        self.assertEqual(p.get("s", "full name"), "dark\tblue")
        self.assertEqual(p.get("s", "other key"), "v")

    def test_space_and_tab_delimiters(self):
        p = cp.ConfigParser(delimiters=(" ", "\t"))
        p.read_string("[s]\na\tb c\nd e\tf\n")
        self.assertEqual(dict(p["s"]), {"a": "b c", "d": "e\tf"})

    def test_default_delimiters_keep_spaces_in_names(self):
        p = cp.ConfigParser()
        p.read_string("[s]\nfull  name = Ada Lovelace\nn\tx: 7\n")
        self.assertEqual(p.get("s", "full  name"), "Ada Lovelace")
        self.assertEqual(p.getint("s", "n\tx"), 7)

    def test_custom_non_whitespace_delimiter_keeps_spaces_in_names(self):
        p = cp.ConfigParser(delimiters=("->",))
        p.read_string("[s]\nmy key -> a = b\n")
        self.assertEqual(p.get("s", "my key"), "a = b")

    def test_allow_no_value_with_space_delimiter(self):
        p = cp.ConfigParser(delimiters=(" ",), allow_no_value=True)
        p.read_string("[s]\nflag\nkey some value\n")
        self.assertIsNone(p.get("s", "flag"))
        self.assertEqual(p.get("s", "key"), "some value")

    def test_strict_duplicate_with_space_delimiter(self):
        p = cp.ConfigParser(delimiters=(" ",))
        with self.assertRaises(cp.DuplicateOptionError):
            p.read_string("[s]\nkey one\nkey two\n")

    def test_malformed_line_rejected(self):
        p = cp.ConfigParser(delimiters=(" ",))
        with self.assertRaises(cp.ParsingError):
            p.read_string("[s]\nnodelimiter\n")
        p = cp.ConfigParser()
        with self.assertRaises(cp.ParsingError):
            p.read_string("[s]\njust some words\n")

    def test_typed_and_interpolation(self):
        p = cp.ConfigParser(delimiters=(" ",))
        p.read_string("[s]\nn 42\nb yes\nf 1.5\nbase /tmp\npath %(base)s/x\n")
        self.assertEqual(p.getint("s", "n"), 42)
        self.assertIs(p.getboolean("s", "b"), True)
        self.assertEqual(p.getfloat("s", "f"), 1.5)
        self.assertEqual(p.get("s", "path"), "/tmp/x")

    def test_round_trip(self):
        for delims in ((" ", "="), ("\t",)):
            for space in (True, False):
                with self.subTest(delims=delims, space=space):
                    p = cp.ConfigParser(delimiters=delims)
                    p.read_dict({"s": {"colour": "dark blue", "n": "1"}})
                    buf = io.StringIO()
                    p.write(buf, space_around_delimiters=space)
                    q = cp.ConfigParser(delimiters=delims)
                    q.read_string(buf.getvalue())
                    self.assertEqual(dict(q["s"]), dict(p["s"]))

    def test_no_delimiter_long_line_is_fast(self):
        line = "a " * 50000
        for delims in ((" ",), ("=", ":")):
            p = cp.ConfigParser(delimiters=delims)
            start = time.perf_counter()
            if delims == (" ",):
                p.read_string("[s]\n" + line + "\n")
            else:
                with self.assertRaises(cp.ParsingError):
                    p.read_string("[s]\n" + line + "\n")
            self.assertLess(time.perf_counter() - start, 2.0)


if __name__ == "__main__":
    unittest.main()
