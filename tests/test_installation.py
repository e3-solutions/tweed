import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_launcher():
    loader = importlib.machinery.SourceFileLoader(
        "bonaparte_launcher", str(ROOT / "bonaparte-launcher")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


LAUNCHER = load_launcher()


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

    def test_release_bundle_requires_all_runtime_modules(self):
        runtime_modules = {
            "bonaparte_checkpoint.py",
            "bonaparte_linear.py",
            "bonaparte_native.py",
            "bonaparte_progress.py",
        }
        self.assertTrue(runtime_modules.issubset(LAUNCHER.REQUIRED))
        self.install()
        release = self.home / "current"
        self.assertTrue(all((release / name).exists() for name in runtime_modules))

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
        self.publish("v1.1.0")
        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}
        self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        self.assertEqual((self.home / "current").resolve().name, "v1.1.0")

    def test_legacy_launcher_bootstraps_autoresearch_on_second_invocation(self):
        legacy = self.root / "legacy-source"
        installer_revisions = self.run_command(
            "git", "-C", str(ROOT), "rev-list", "origin/main", "--", "install"
        ).stdout.splitlines()
        legacy_revision = next(
            revision
            for revision in installer_revisions
            if self.run_command(
                "git",
                "-C",
                str(ROOT),
                "cat-file",
                "-e",
                f"{revision}:autoresearch",
                check=False,
            ).returncode
            != 0
        )
        self.run_command(
            "git", "clone", "-q", "--no-hardlinks", str(ROOT), str(legacy)
        )
        self.run_command(
            "git", "-C", str(legacy), "checkout", "-q", "--detach", legacy_revision
        )
        self.assertFalse((legacy / "autoresearch").exists())
        self.run_command(str(legacy / "install"))
        self.assertFalse((self.bin / "autoresearch").exists())

        result = self.run_command(str(self.bin / "bonaparte"), "update")

        self.assertIn("Updated Bonaparte to v1.0.0", result.stdout)
        current = (self.home / "current").resolve()
        self.assertEqual(current.name, "v1.0.0")
        self.assertFalse((self.bin / "autoresearch").exists())

        result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", result.stdout)
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )
        result = self.run_command(str(self.bin / "autoresearch"), "--help")
        self.assertIn("usage: autoresearch", result.stdout)

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

    def test_release_validation_scrubs_the_host_progress_channel(self):
        environment = {**os.environ, "BONAPARTE_PROGRESS_FD": "37"}
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(LAUNCHER.subprocess, "run") as run,
        ):
            LAUNCHER.validate_release(ROOT)

        self.assertNotIn("BONAPARTE_PROGRESS_FD", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["BONAPARTE_AUTO_UPDATE"], "0")

    @unittest.skipUnless(os.name == "posix", "file-descriptor ABI requires POSIX")
    def test_launcher_preserves_only_the_host_progress_channel_for_all_runner_routes(self):
        self.install()
        release = (self.home / "current").resolve()

        probe = release / "bonaparte"
        probe.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "fd = int(os.environ['BONAPARTE_PROGRESS_FD'])\n"
            "os.write(fd, (json.dumps({\n"
            "    'version': 2, 'sequence': 1,\n"
            "    'phase': os.environ['TEST_EXPECTED_PHASE'],\n"
            "    'state': 'started', 'elapsed_seconds': 0,\n"
            "    'semantic': {\n"
            "        'stage': 'coordinating', 'actor': 'coordinator',\n"
            "        'activity': 'lifecycle', 'status': 'started', 'count': None,\n"
            "    },\n"
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
            "import json, os, pathlib\n"
            "fd = int(os.environ.get('TEST_PROGRESS_FD', '-1'))\n"
            "inherited = True\n"
            "try:\n"
            "    os.write(fd, b'updater wrote to progress\\n')\n"
            "except OSError:\n"
            "    inherited = False\n"
            f"pathlib.Path({str(updater_called)!r}).write_text(json.dumps({{\n"
            "    'env_present': 'BONAPARTE_PROGRESS_FD' in os.environ,\n"
            "    'fd_inherited': inherited,\n"
            "}))\n"
            "print('0' * 40, 'refs/tags/v1.0.0')\n"
        )
        fake_git.chmod(0o755)

        routes = (
            ("create", ("create", "feature", "request")),
            ("rca", ("RCA", "COR-3451")),
            ("scope", ("scope", "COR-3451")),
            ("implement", ("implement", "COR-3451")),
            ("review", ("review", "COR-3451")),
            ("publish", ("publish", "COR-3451")),
            ("scope", ("resume", "opaque-token", "answer")),
            ("scope", ("resume", "scope", "session-id", "answer")),
        )
        for expected_phase, arguments in routes:
            with self.subTest(route=arguments):
                progress_reader, progress_writer = os.pipe()
                try:
                    (self.home / "last-check").unlink(missing_ok=True)
                    updater_called.unlink(missing_ok=True)
                    environment = {
                        **self.environment,
                        "BONAPARTE_AUTO_UPDATE": "1",
                        "BONAPARTE_PROGRESS_FD": str(progress_writer),
                        "TEST_PROGRESS_FD": str(progress_writer),
                        "TEST_EXPECTED_PHASE": expected_phase,
                        "PATH": f"{fake_bin}{os.pathsep}{self.environment['PATH']}",
                    }
                    completed = subprocess.run(
                        [str(self.bin / "bonaparte"), *arguments],
                        cwd=self.source,
                        env=environment,
                        check=True,
                        capture_output=True,
                        text=True,
                        pass_fds=(progress_writer,),
                        timeout=45,
                    )
                    os.close(progress_writer)
                    progress_writer = -1
                    progress = os.read(progress_reader, 4096).decode()

                    self.assertGreaterEqual(
                        int(environment["BONAPARTE_PROGRESS_FD"]), 3
                    )
                    self.assertTrue(updater_called.exists())
                    self.assertEqual(
                        json.loads(updater_called.read_text()),
                        {"env_present": False, "fd_inherited": False},
                    )
                    self.assertEqual(completed.stdout, "runner stdout\n")
                    self.assertEqual(completed.stderr, "runner stderr\n")
                    self.assertEqual(
                        json.loads(progress),
                        {
                            "version": 2,
                            "sequence": 1,
                            "phase": expected_phase,
                            "state": "started",
                            "elapsed_seconds": 0,
                            "semantic": {
                                "stage": "coordinating",
                                "actor": "coordinator",
                                "activity": "lifecycle",
                                "status": "started",
                                "count": None,
                            },
                        },
                    )
                finally:
                    if progress_writer >= 0:
                        os.close(progress_writer)
                    os.close(progress_reader)
