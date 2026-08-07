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
            "TWEED_HOME": str(self.home),
            "TWEED_BIN_DIR": str(self.bin),
            "CODEX_HOME": str(self.codex),
            "TWEED_REPOSITORY": str(self.source),
            "TWEED_AUTO_UPDATE": "0",
        }
        for arguments in (
            ("init", "-q"),
            ("config", "user.name", "Tweed Test"),
            ("config", "user.email", "tweed@example.com"),
            ("add", "."),
            ("commit", "-qm", "initial"),
            ("tag", "v1.0.0"),
        ):
            self.git(*arguments)

    def run_command(self, *command, check=True, environment=None):
        return subprocess.run(
            command,
            cwd=self.source if self.source.exists() else ROOT,
            env=environment or self.environment,
            check=check,
            capture_output=True,
            text=True,
            timeout=45,
        )

    def git(self, *arguments):
        return self.run_command("git", *arguments)

    def install(self):
        self.run_command(str(self.source / "install"))
        return (self.home / "current").resolve().name

    def publish(self, tag):
        readme = self.source / "README.md"
        readme.write_text(readme.read_text() + f"\n{tag}\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", tag)
        self.git("tag", tag)

    def test_install_is_independent_of_the_checkout(self):
        old_skill = self.root / "old-skill"
        old_skill.mkdir()
        (self.codex / "skills").mkdir(parents=True)
        (self.codex / "skills/use-tweed").symlink_to(old_skill)
        self.install()
        current = (self.home / "current").resolve()
        self.assertEqual((self.bin / "tweed").resolve(), current / "tweed-launcher")
        self.assertEqual(
            (self.codex / "skills/use-tweed").resolve(),
            current / "skills/use-tweed",
        )
        shutil.rmtree(self.source)
        result = self.run_command(
            str(self.bin / "tweed"), "--help", environment=self.environment
        )
        self.assertIn("usage: tweed", result.stdout)

    def test_update_switches_to_a_complete_snapshot(self):
        self.install()
        self.publish("v1.1.0")
        environment = {**self.environment, "TWEED_AUTO_UPDATE": "1"}
        self.run_command(str(self.bin / "tweed"), "--help", environment=environment)
        self.assertEqual((self.home / "current").resolve().name, "v1.1.0")

    def test_failed_update_keeps_the_current_runtime_usable(self):
        original = self.install()
        (self.source / "workflows/scope.md").unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "incomplete")
        self.git("tag", "v1.1.0")
        result = self.run_command(str(self.bin / "tweed"), "update", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / "current").resolve().name, original)

        environment = {**self.environment, "TWEED_AUTO_UPDATE": "1"}
        result = self.run_command(
            str(self.bin / "tweed"), "--help", environment=environment
        )
        self.assertIn("usage: tweed", result.stdout)
        self.assertEqual((self.home / "current").resolve().name, original)
