import json
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
            (self.codex / "skills/use-bonaparte").resolve(),
            current / "skills/use-bonaparte",
        )
        shutil.rmtree(self.source)
        result = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=self.environment
        )
        self.assertIn("usage: bonaparte", result.stdout)

    def test_update_switches_to_a_complete_snapshot(self):
        self.install()
        self.publish("v1.1.0")
        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}
        self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        self.assertEqual((self.home / "current").resolve().name, "v1.1.0")

    def test_failed_update_keeps_the_current_runtime_usable(self):
        original = self.install()
        (self.source / "workflows/scope.md").unlink()
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

    @unittest.skipUnless(os.name == "posix", "file-descriptor ABI requires POSIX")
    def test_launcher_preserves_only_the_host_progress_channel_for_the_runner(self):
        self.install()
        release = (self.home / "current").resolve()
        progress_reader, progress_writer = os.pipe()
        self.addCleanup(os.close, progress_reader)

        probe = release / "bonaparte"
        probe.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "fd = int(os.environ['BONAPARTE_PROGRESS_FD'])\n"
            "os.write(fd, (json.dumps({\n"
            "    'version': 1, 'sequence': 1, 'phase': 'review',\n"
            "    'state': 'started', 'elapsed_seconds': 0,\n"
            "}, separators=(',', ':')) + '\\n').encode())\n"
            "print('runner stdout')\n"
            "print('runner stderr', file=sys.stderr)\n"
        )
        probe.chmod(0o755)

        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        updater_called = self.root / "updater-called"
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            f"open({str(updater_called)!r}, 'w').close()\n"
            "fd = int(os.environ['BONAPARTE_PROGRESS_FD'])\n"
            "try:\n"
            "    os.write(fd, b'updater wrote to progress\\n')\n"
            "except OSError:\n"
            "    pass\n"
            "print('0' * 40, 'refs/tags/v1.0.0')\n"
        )
        fake_git.chmod(0o755)

        environment = {
            **self.environment,
            "BONAPARTE_AUTO_UPDATE": "1",
            "BONAPARTE_PROGRESS_FD": str(progress_writer),
            "PATH": f"{fake_bin}{os.pathsep}{self.environment['PATH']}",
        }
        completed = subprocess.run(
            [str(self.bin / "bonaparte"), "review", "COR-3451"],
            cwd=self.source,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            pass_fds=(progress_writer,),
            timeout=45,
        )
        os.close(progress_writer)
        progress = os.read(progress_reader, 4096).decode()

        self.assertGreaterEqual(int(environment["BONAPARTE_PROGRESS_FD"]), 3)
        self.assertTrue(updater_called.exists())
        self.assertEqual(completed.stdout, "runner stdout\n")
        self.assertEqual(completed.stderr, "runner stderr\n")
        self.assertEqual(
            json.loads(progress),
            {
                "version": 1,
                "sequence": 1,
                "phase": "review",
                "state": "started",
                "elapsed_seconds": 0,
            },
        )
