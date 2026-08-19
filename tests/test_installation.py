import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.home = self.root / "data"
        self.bin = self.root / "bin"
        self.codex = self.root / "codex"
        shutil.copytree(
            ROOT,
            self.source,
            ignore=shutil.ignore_patterns(
                ".git", ".codex", ".ruff_cache", "__pycache__"
            ),
        )
        self.environment = {
            **os.environ,
            "BONAPARTE_HOME": str(self.home),
            "BONAPARTE_BIN_DIR": str(self.bin),
            "CODEX_HOME": str(self.codex),
        }
        for arguments in (
            ("init", "-q"),
            ("config", "user.name", "Bonaparte Test"),
            ("config", "user.email", "bonaparte@example.com"),
            ("add", "."),
            ("commit", "-qm", "initial"),
            ("tag", "v1.0.0"),
        ):
            self.git(*arguments)

    def run_command(self, *command, check=True, cwd=None):
        return subprocess.run(
            command,
            cwd=cwd or (self.source if self.source.exists() else ROOT),
            env=self.environment,
            check=check,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def git(self, *arguments):
        return self.run_command("git", *arguments)

    def install(self):
        result = self.run_command(str(self.source / "install"))
        return result, (self.home / "current").resolve()

    def test_install_is_checkout_independent_and_has_no_launcher_modules(self):
        _, current = self.install()
        self.assertEqual((self.bin / "bonaparte").resolve(), current / "bonaparte")
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )
        self.assertEqual(
            (self.codex / "skills/use-bonaparte").resolve(),
            current / "skills/use-bonaparte",
        )
        for removed in (
            "bonaparte-launcher",
            "bonaparte_checkpoint.py",
            "bonaparte_linear.py",
            "bonaparte_native.py",
            "bonaparte_progress.py",
        ):
            self.assertFalse((current / removed).exists())

        shutil.rmtree(self.source)
        result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", result.stdout)
        result = self.run_command(str(self.bin / "autoresearch"), "--help")
        self.assertIn("usage: autoresearch", result.stdout)

    def test_install_refuses_non_symlink_targets(self):
        self.bin.mkdir()
        target = self.bin / "bonaparte"
        target.write_text("keep me")

        result = self.run_command(str(self.source / "install"), check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace non-symlink", result.stderr)
        self.assertEqual(target.read_text(), "keep me")
        self.assertFalse((self.home / "current").exists())

    def test_reinstall_atomically_selects_the_new_snapshot(self):
        _, first = self.install()
        readme = self.source / "README.md"
        readme.write_text(readme.read_text() + "\nnew snapshot\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "new snapshot")

        _, second = self.install()

        self.assertNotEqual(first, second)
        self.assertEqual((self.bin / "bonaparte").resolve(), second / "bonaparte")
        self.assertTrue(first.is_dir())


if __name__ == "__main__":
    unittest.main()
