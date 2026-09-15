"""Configured time limits must remain real, finite deadlines."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'confidence.py'


class TimeoutInputTest(unittest.TestCase):
    def test_nonfinite_timeout_rejects_before_launch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for value in ('NaN', 'Infinity'):
                with self.subTest(value=value):
                    marker = root / 'launched'
                    result = subprocess.run([
                        sys.executable, str(SCRIPT), 'run', '--timeout-seconds', value,
                        '--directory', str(root / '.confidence'), '--', sys.executable,
                        '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()',
                    ], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(marker.exists())
                    self.assertIn('finite and greater than zero', result.stderr)


if __name__ == '__main__':
    unittest.main()
