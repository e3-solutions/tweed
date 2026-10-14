import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "local_configparser_ws", ROOT / "configparser.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def parse(text, **kwargs):
    p = M.ConfigParser(**kwargs)
    p.read_string(text)
    return p


class WhitespaceDelimiterTests(unittest.TestCase):
    def test_space_delimiter_splits_at_first_space(self):
        p = parse("[s]\ncolour dark blue\nkey = v\nk=w\n",
                  delimiters=(" ", "="))
        self.assertEqual(dict(p["s"]),
                         {"colour": "dark blue", "key": "v", "k": "w"})

    def test_tab_delimiter(self):
        p = parse("[s]\ncolour\tdark blue\nfull name\tAda\na\tb\tc\n",
                  delimiters=("\t",))
        self.assertEqual(dict(p["s"]), {"colour": "dark blue",
                                         "full name": "Ada",
                                         "a": "b\tc"})

    def test_space_delimiter_with_tab_inside_name_is_name(self):
        # Tab is not a delimiter here, so it may join words of the name.
        p = parse("[s]\nfull\tname value here\n", delimiters=(" ",))
        self.assertEqual(dict(p["s"]), {"full\tname": "value here"})

    def test_default_delimiters_keep_whitespace_in_names(self):
        p = parse("[s]\nfull name = Ada Lovelace\nother key: 3\n")
        self.assertEqual(p.get("s", "full name"), "Ada Lovelace")
        self.assertEqual(p.getint("s", "other key"), 3)

    def test_default_delimiters_reject_line_without_delimiter(self):
        with self.assertRaises(M.ParsingError):
            parse("[s]\ncolour dark blue\n")

    def test_space_delimiter_rejects_single_word_without_no_value(self):
        with self.assertRaises(M.ParsingError):
            parse("[s]\nlonely\n", delimiters=(" ",))

    def test_allow_no_value_with_space_delimiter(self):
        p = parse("[s]\nflag\ncolour dark blue\n",
                  delimiters=(" ",), allow_no_value=True)
        self.assertIsNone(p.get("s", "flag"))
        self.assertEqual(p.get("s", "colour"), "dark blue")

    def test_strict_duplicate_with_space_delimiter(self):
        with self.assertRaises(M.DuplicateOptionError):
            parse("[s]\ncolour red\ncolour blue\n", delimiters=(" ",))
        p = parse("[s]\ncolour red\ncolour blue\n",
                  delimiters=(" ",), strict=False)
        self.assertEqual(p.get("s", "colour"), "blue")

    def test_typed_and_interpolation_with_space_delimiter(self):
        p = parse("[s]\ncount 7\nratio 0.5\non yes\n"
                  "base /usr\npath %(base)s/lib\n", delimiters=(" ",))
        self.assertEqual(p.getint("s", "count"), 7)
        self.assertEqual(p.getfloat("s", "ratio"), 0.5)
        self.assertIs(p.getboolean("s", "on"), True)
        self.assertEqual(p.get("s", "path"), "/usr/lib")

    def test_round_trip(self):
        for delims in ((" ",), ("\t",), (" ", "=")):
            for spaced in (True, False):
                with self.subTest(delims=delims, spaced=spaced):
                    p = M.ConfigParser(delimiters=delims)
                    p["s"] = {"colour": "dark blue", "count": "7"}
                    buf = io.StringIO()
                    p.write(buf, space_around_delimiters=spaced)
                    q = parse(buf.getvalue(), delimiters=delims)
                    self.assertEqual(dict(q["s"]), dict(p["s"]))

    def test_long_malformed_line_is_rejected(self):
        line = "a " * 20000 + "a"
        with self.assertRaises(M.ParsingError):
            parse("[s]\n" + line + "\n")
        with self.assertRaises(M.ParsingError):
            parse("[s]\n" + line.replace(" ", "\t") + "\n",
                  delimiters=(" ",))


if __name__ == "__main__":
    unittest.main()
