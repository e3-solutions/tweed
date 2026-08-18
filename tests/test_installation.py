import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
        self.assertIn("autoresearch", LAUNCHER.REQUIRED)
        self.install()
        release = self.home / "current"
        self.assertTrue(all((release / name).exists() for name in runtime_modules))

    def test_readme_documents_the_release_contract(self):
        readme = (ROOT / "README.md").read_text()
        for marker in (
            "bonaparte status",
            "latest: unavailable",
            "BONAPARTE_AUTO_UPDATE=0",
            "bonaparte update",
            "local-v0.3.0-8b75b707dce8",
            "unique staging directory",
            "use-bonaparte",
            "`autoresearch` companion command",
            "higher corrective stable tag",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, readme)

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

    def test_status_reports_installed_latest_and_current(self):
        installed = self.install()

        result = self.run_command(str(self.bin / "bonaparte"), "status")

        self.assertEqual(
            result.stdout.splitlines(),
            [f"installed: {installed}", "latest: v1.0.0", "current: yes"],
        )
        self.publish("v1.1.0")
        result = self.run_command(str(self.bin / "bonaparte"), "status")
        self.assertEqual(
            result.stdout.splitlines()[-2:], ["latest: v1.1.0", "current: no"]
        )

    def test_status_ignores_nonstable_tags_and_reports_offline(self):
        installed = self.install()
        self.git("tag", "v9.0.0-rc1")
        result = self.run_command(str(self.bin / "bonaparte"), "status")
        self.assertEqual(
            result.stdout.splitlines()[-2:], ["latest: v1.0.0", "current: yes"]
        )
        before = (self.home / "current").readlink()
        releases = sorted(path.name for path in (self.home / "releases").iterdir())
        environment = {
            **self.environment,
            "BONAPARTE_REPOSITORY": str(self.root / "offline"),
        }

        result = self.run_command(
            str(self.bin / "bonaparte"),
            "status",
            check=False,
            environment=environment,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout.splitlines(),
            [f"installed: {installed}", "latest: unavailable", "current: unknown"],
        )
        self.assertEqual((self.home / "current").readlink(), before)
        self.assertEqual(
            sorted(path.name for path in (self.home / "releases").iterdir()), releases
        )

    def test_ordinary_check_alerts_once_without_installing(self):
        self.install()
        self.publish("v1.1.0")
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        calls = self.root / "git-calls"
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            f"path = pathlib.Path({str(calls)!r})\n"
            "with path.open('a') as output: output.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "print('1' * 40, 'refs/tags/v1.1.0')\n"
        )
        fake_git.chmod(0o755)
        environment = {
            **self.environment,
            "BONAPARTE_AUTO_UPDATE": "1",
            "PATH": f"{fake_bin}{os.pathsep}{self.environment['PATH']}",
        }
        before = (self.home / "current").readlink()
        releases = sorted(path.name for path in (self.home / "releases").iterdir())

        first = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        second = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )

        self.assertIn("run 'bonaparte update'", first.stderr)
        self.assertNotIn("update available", second.stderr)
        self.assertEqual(
            calls.read_text().splitlines(),
            [f"ls-remote --tags --refs {self.source}"],
        )
        self.assertEqual((self.home / "current").readlink(), before)
        self.assertEqual(
            sorted(path.name for path in (self.home / "releases").iterdir()), releases
        )

    def test_explicit_update_switches_to_a_complete_snapshot(self):
        self.install()
        self.publish("v1.1.0")

        self.run_command(str(self.bin / "bonaparte"), "update")

        self.assertEqual((self.home / "current").resolve().name, "v1.1.0")
        self.assertEqual((self.bin / "bonaparte").resolve().parent.name, "v1.1.0")
        self.assertEqual((self.bin / "autoresearch").resolve().parent.name, "v1.1.0")
        self.assertEqual(
            (self.codex / "skills/use-bonaparte").resolve().parents[1].name,
            "v1.1.0",
        )

    def test_exact_v030_launcher_upgrades_with_one_update_command(self):
        legacy = self.root / "legacy-source"
        legacy_revision = "8b75b707dce819bab5aeeea5f90ae482495d5ce9"
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

        result = self.run_command(str(self.bin / "bonaparte"), "status")
        self.assertEqual(
            result.stdout.splitlines()[-2:], ["latest: v1.0.0", "current: yes"]
        )
        self.assertFalse((self.bin / "autoresearch").exists())
        result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", result.stdout)
        self.assertEqual(
            (self.bin / "autoresearch").resolve(), current / "autoresearch"
        )
        result = self.run_command(str(self.bin / "autoresearch"), "--help")
        self.assertIn("usage: autoresearch", result.stdout)

    def test_update_preflights_every_managed_target(self):
        original = self.install()
        self.publish("v1.1.0")
        launcher = (self.home / "current" / "bonaparte-launcher").resolve()
        targets = (
            self.bin / "bonaparte",
            self.bin / "autoresearch",
            self.codex / "skills/use-bonaparte",
        )
        for target in targets:
            with self.subTest(target=target):
                saved_link = target.readlink()
                target.unlink()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("keep me")
                result = self.run_command(
                    sys.executable,
                    str(launcher),
                    "update",
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("refusing to replace non-symlink", result.stderr)
                self.assertEqual(target.read_text(), "keep me")
                self.assertEqual((self.home / "current").resolve().name, original)
                target.unlink()
                target.symlink_to(saved_link)

    def test_failed_update_keeps_the_current_runtime_usable(self):
        original = self.install()
        (self.source / "workflows/autoresearch-critic.md").unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "incomplete")
        self.git("tag", "v1.1.0")
        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )

        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}
        result = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )
        self.assertIn("usage: bonaparte", result.stdout)
        self.assertEqual((self.home / "current").resolve().name, original)

    def test_moved_tag_is_rejected_and_staging_is_cleaned(self):
        self.home.mkdir()
        (self.home / "releases").mkdir()

        def fake_git(_directory, *arguments, output=False):
            if arguments == ("rev-parse", "FETCH_HEAD"):
                return mock.Mock(stdout="b" * 40 + "\n")
            return mock.Mock()

        with mock.patch.object(LAUNCHER, "git", side_effect=fake_git):
            with self.assertRaisesRegex(RuntimeError, "tag v1.1.0 moved"):
                LAUNCHER.fetch_release(self.home, "v1.1.0", "a" * 40)

        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )

    def test_retained_release_for_old_tag_object_is_not_activated(self):
        original = self.install()
        self.publish("v1.1.0")
        oid_a = self.git("rev-parse", "v1.1.0").stdout.strip()
        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            retained = LAUNCHER.fetch_release(self.home, "v1.1.0", oid_a)
        LAUNCHER.validate_release(retained)

        readme = self.source / "README.md"
        readme.write_text(readme.read_text() + "\nmoved v1.1.0\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "move v1.1.0")
        self.git("tag", "-f", "v1.1.0")
        oid_b = self.git("rev-parse", "v1.1.0").stdout.strip()
        self.assertNotEqual(oid_a, oid_b)

        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            with self.assertRaisesRegex(RuntimeError, "advertised object"):
                LAUNCHER.update(self.home)

        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertEqual(
            (retained / LAUNCHER.RELEASE_OID_FILE).read_text(), f"{oid_a}\n"
        )

    def test_oidless_legacy_cache_is_verified_and_attested(self):
        self.install()
        self.publish("v1.1.0")
        expected_oid = self.git("rev-parse", "v1.1.0").stdout.strip()
        legacy = self.home / "releases" / "v1.1.0"
        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            LAUNCHER.fetch_release(self.home, "v1.1.0", expected_oid)
        (legacy / LAUNCHER.RELEASE_OID_FILE).unlink()

        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            retained = LAUNCHER.fetch_release(self.home, "v1.1.0", expected_oid)

        self.assertEqual(retained, legacy)
        self.assertEqual(
            (legacy / LAUNCHER.RELEASE_OID_FILE).read_text(), f"{expected_oid}\n"
        )

        (legacy / LAUNCHER.RELEASE_OID_FILE).unlink()
        (legacy / "README.md").write_text("altered")
        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            with self.assertRaisesRegex(RuntimeError, "cannot be verified"):
                LAUNCHER.fetch_release(self.home, "v1.1.0", expected_oid)
        self.assertFalse((legacy / LAUNCHER.RELEASE_OID_FILE).exists())

    def test_required_directory_is_rejected_and_current_remains_usable(self):
        original = self.install()
        workflow = self.source / "workflows/autoresearch-critic.md"
        workflow.unlink()
        workflow.mkdir()
        (workflow / "not-a-workflow").write_text("invalid bundle entry\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "directory in required manifest")
        self.git("tag", "v1.1.0")

        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release is missing workflows/autoresearch-critic.md", result.stderr)
        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )
        help_result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", help_result.stdout)

    def test_required_symlink_is_rejected_and_current_remains_usable(self):
        original = self.install()
        workflow = self.source / "workflows/autoresearch-critic.md"
        workflow.unlink()
        workflow.symlink_to("scope.md")
        self.git("add", "-A")
        self.git("commit", "-qm", "symlink in required manifest")
        self.git("tag", "v1.1.0")

        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release is missing workflows/autoresearch-critic.md", result.stderr)
        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )
        help_result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", help_result.stdout)

    def test_smoke_failure_keeps_old_release_and_cleans_staging(self):
        original = self.install()
        (self.source / "bonaparte").write_text(
            "#!/usr/bin/env python3\nraise SystemExit(1)\n"
        )
        self.git("add", "bonaparte")
        self.git("commit", "-qm", "broken smoke test")
        self.git("tag", "v1.1.0")

        result = self.run_command(str(self.bin / "bonaparte"), "update", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertIn("returned non-zero exit status", result.stderr)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )
        help_result = self.run_command(str(self.bin / "bonaparte"), "--help")
        self.assertIn("usage: bonaparte", help_result.stdout)

    def test_interruption_exposes_only_the_old_or_new_complete_release(self):
        original = self.install()
        self.publish("v1.1.0")
        real_atomic_link = LAUNCHER.atomic_link

        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            with mock.patch.object(
                LAUNCHER,
                "atomic_link",
                side_effect=KeyboardInterrupt("before activation"),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    LAUNCHER.update(self.home)

        self.assertEqual((self.home / "current").resolve().name, original)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )
        self.assertIn(
            "usage: bonaparte",
            self.run_command(str(self.bin / "bonaparte"), "--help").stdout,
        )

        def activate_then_interrupt(target, link):
            real_atomic_link(target, link)
            raise KeyboardInterrupt("after activation")

        with mock.patch.object(LAUNCHER, "REPOSITORY", str(self.source)):
            with mock.patch.object(
                LAUNCHER, "atomic_link", side_effect=activate_then_interrupt
            ):
                with self.assertRaises(KeyboardInterrupt):
                    LAUNCHER.update(self.home)

        release = (self.home / "current").resolve()
        self.assertEqual(release.name, "v1.1.0")
        LAUNCHER.validate_release(release)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )
        self.assertIn(
            "usage: bonaparte",
            self.run_command(str(self.bin / "bonaparte"), "--help").stdout,
        )
        self.assertIn(
            "usage: autoresearch",
            self.run_command(str(self.bin / "autoresearch"), "--help").stdout,
        )

    def test_competing_updates_publish_one_complete_release(self):
        self.install()
        self.publish("v1.1.0")
        command = [str(self.bin / "bonaparte"), "update"]

        first = subprocess.Popen(
            command,
            cwd=self.source,
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        second = subprocess.Popen(
            command,
            cwd=self.source,
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        first_output = first.communicate(timeout=45)
        second_output = second.communicate(timeout=45)

        self.assertEqual(
            (first.returncode, second.returncode),
            (0, 0),
            (first_output, second_output),
        )
        release = (self.home / "current").resolve()
        self.assertEqual(release.name, "v1.1.0")
        LAUNCHER.validate_release(release)
        self.assertFalse(
            any(path.name.startswith(".update-") for path in self.home.iterdir())
        )

    def test_concurrent_ordinary_checks_claim_the_daily_interval_once(self):
        self.install()
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        calls = self.root / "git-calls"
        started = self.root / "git-started"
        release = self.root / "release-git"
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, time\n"
            f"calls = pathlib.Path({str(calls)!r})\n"
            "with calls.open('a') as output: output.write('ls-remote\\n')\n"
            f"pathlib.Path({str(started)!r}).touch()\n"
            f"release = pathlib.Path({str(release)!r})\n"
            "while not release.exists(): time.sleep(0.01)\n"
            "print('1' * 40, 'refs/tags/v1.1.0')\n"
        )
        fake_git.chmod(0o755)
        environment = {
            **self.environment,
            "BONAPARTE_AUTO_UPDATE": "1",
            "PATH": f"{fake_bin}{os.pathsep}{self.environment['PATH']}",
        }
        command = [str(self.bin / "bonaparte"), "--help"]
        first = subprocess.Popen(
            command,
            cwd=self.source,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(started.exists(), "first update check did not start")

        second = subprocess.run(
            command,
            cwd=self.source,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        release.touch()
        first_output = first.communicate(timeout=10)

        self.assertEqual(first.returncode, 0, first_output)
        self.assertEqual(calls.read_text().splitlines(), ["ls-remote"])
        alerts = sum(
            "bonaparte: update available:" in stderr
            for stderr in (first_output[1], second.stderr)
        )
        self.assertLessEqual(alerts, 1)

    def test_failed_daily_claim_does_not_block_ordinary_command(self):
        self.install()
        (self.home / "last-check.lock").mkdir()
        environment = {**self.environment, "BONAPARTE_AUTO_UPDATE": "1"}

        result = self.run_command(
            str(self.bin / "bonaparte"), "--help", environment=environment
        )

        self.assertIn("usage: bonaparte", result.stdout)

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
