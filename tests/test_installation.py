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
            "BONAPARTE_REPOSITORY": str(self.source),
            "BONAPARTE_AUTO_UPDATE": "0",
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
        (self.codex / "skills/use-bonaparte").symlink_to(old_skill)
        self.install()
        current = (self.home / "current").resolve()
        self.assertEqual(
            (self.bin / "bonaparte").resolve(), current / "bonaparte-launcher"
        )
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )
        self.assertEqual(
            (self.codex / "skills/use-bonaparte").resolve(),
            current / "skills/use-bonaparte",
        )
        shutil.rmtree(self.source)
        result = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=self.environment
        )
        self.assertIn("usage: bonaparte", result.stdout)
        result = self.run_command(
            str(self.bin / "autoresearch"), "--help", environment=self.environment
        )
        self.assertIn("usage: autoresearch", result.stdout)

    def test_install_refuses_a_non_symlink_autoresearch_target(self):
        self.bin.mkdir()
        target = self.bin / "autoresearch"
        target.write_text("keep me")

        result = self.run_command(str(self.source / "install"), check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace non-symlink", result.stderr)
        self.assertEqual(target.read_text(), "keep me")
        self.assertFalse((self.home / "current").exists())

    def test_update_switches_to_a_complete_snapshot(self):
        self.install()
        # Model a pre-autoresearch release selected by the legacy two-link layout.
        ((self.home / "current").resolve() / "autoresearch").unlink()
        (self.bin / "autoresearch").unlink()
        bonaparte_link = (self.bin / "bonaparte").readlink()
        skill_link = (self.codex / "skills/use-bonaparte").readlink()
        self.publish("v1.1.0")
        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}
        self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        current = (self.home / "current").resolve()
        self.assertEqual(current.name, "v1.1.0")
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )
        self.assertEqual((self.bin / "bonaparte").readlink(), bonaparte_link)
        self.assertEqual(
            (self.codex / "skills/use-bonaparte").readlink(), skill_link
        )

        # A legacy launcher may have switched current and recently checked for
        # updates without creating the new CLI link. Startup still migrates it.
        (self.bin / "autoresearch").unlink()
        (self.home / "last-check").touch()
        self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )

    def test_update_refuses_a_non_symlink_autoresearch_target(self):
        original = self.install()
        target = self.bin / "autoresearch"
        target.unlink()
        target.write_text("keep me")
        bonaparte_link = (self.bin / "bonaparte").readlink()
        skill_link = (self.codex / "skills/use-bonaparte").readlink()
        self.publish("v1.1.0")

        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace non-symlink", result.stderr)
        self.assertEqual(target.read_text(), "keep me")
        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertEqual((self.bin / "bonaparte").readlink(), bonaparte_link)
        self.assertEqual(
            (self.codex / "skills/use-bonaparte").readlink(), skill_link
        )

    def test_failed_update_keeps_the_current_runtime_usable(self):
        original = self.install()
        (self.source / "workflows/autoresearch-critic.md").unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "incomplete")
        self.git("tag", "v1.1.0")
        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / "current").resolve().name, original)

        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}
        result = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        self.assertIn("usage: bonaparte", result.stdout)
        self.assertEqual((self.home / "current").resolve().name, original)
        result = self.run_command(
            str(self.bin / "autoresearch"), "--help", environment=environment
        )
        self.assertIn("usage: autoresearch", result.stdout)
        self.assertEqual((self.home / "current").resolve().name, original)
