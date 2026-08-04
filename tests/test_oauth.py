from __future__ import annotations

import json
import http.client
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import tweed_linear_adapter as adapter
import tweed_linear_oauth as oauth


CLIENT_ID = "tweed-client-id"
OFFICIAL_CLIENT_ID = "6e807fb3d574eb3e13bee2dc0bf3337e"


def token_payload(access: str = "access-new", refresh: str = "refresh-new") -> dict:
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": 86_399,
        "scope": "read issues:create comments:create",
    }


def credentials(now: int = 1_000, *, expired: bool = False) -> dict:
    return {
        "schema_version": oauth.STORE_SCHEMA,
        "client_id": CLIENT_ID,
        "access_token": "access-old",
        "refresh_token": "refresh-old",
        "token_type": "Bearer",
        "scopes": sorted(oauth.SCOPES),
        "issued_at": now - 100,
        "expires_at": now - 1 if expired else now + 10_000,
        "generation": 1,
    }


class FakeHTTP:
    def __init__(self, *responses: object):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def post_form(self, path: str, fields: dict[str, str]):
        self.calls.append((path, dict(fields)))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class Response:
    def __init__(self, status: int, payload: object):
        self.status = status
        self.raw = (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        )

    def getheader(self, _name: str):
        return None

    def read(self, amount: int) -> bytes:
        return self.raw[:amount]


class ScriptedConnections:
    def __init__(self, *responses: object):
        self.responses = list(responses)
        self.hosts: list[tuple[str, int]] = []
        self.requests: list[tuple[tuple, dict]] = []

    def __call__(self, host: str, *, timeout: int):
        self.hosts.append((host, timeout))
        owner = self

        class Connection:
            def request(self, *args, **kwargs):
                owner.requests.append((args, kwargs))

            def getresponse(self):
                response = owner.responses.pop(0)
                if isinstance(response, BaseException):
                    raise response
                return response

            def close(self):
                pass

        return Connection()


class OAuthTests(unittest.TestCase):
    def test_keyring_worker_is_bounded_and_never_places_secret_in_argv(self):
        secret = b"credential-secret-that-must-stay-on-stdin"
        completed = subprocess.CompletedProcess(
            ["worker"],
            0,
            json.dumps(
                {
                    "status": "ok",
                    "value": __import__("base64").b64encode(secret).decode("ascii"),
                }
            ).encode(),
            b"",
        )
        with mock.patch.object(oauth.subprocess, "run", return_value=completed) as run:
            self.assertEqual(oauth._run_keyring_worker("read", "default"), secret)
        args, kwargs = run.call_args
        self.assertNotIn(secret.decode(), " ".join(args[0]))
        self.assertEqual(kwargs["input"], b"")
        self.assertEqual(kwargs["timeout"], oauth.KEYRING_TIMEOUT_SECONDS)
        self.assertTrue(kwargs["start_new_session"])

        with mock.patch.object(
            oauth.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["worker"], 1),
        ):
            with self.assertRaisesRegex(oauth.OAuthError, "timed out") as caught:
                oauth._run_keyring_worker("write", "default", secret)
        self.assertNotIn(secret.decode(), str(caught.exception))

    def test_keyring_worker_rejects_invalid_or_oversized_protocol_output(self):
        for stdout in (
            b"not-json",
            json.dumps({"status": "ok", "value": "%%%"}).encode(),
            b"x" * (oauth.KEYRING_MAX_BYTES * 2 + 1),
        ):
            completed = subprocess.CompletedProcess(["worker"], 0, stdout, b"")
            with (
                self.subTest(stdout=stdout[:20]),
                mock.patch.object(oauth.subprocess, "run", return_value=completed),
                self.assertRaises(oauth.OAuthError),
            ):
                oauth._run_keyring_worker("read", "default")

    def test_official_public_client_id_is_the_builtin_default(self):
        self.assertEqual(oauth.DEFAULT_CLIENT_ID, OFFICIAL_CLIENT_ID)

    def test_oauth_http_is_fixed_bounded_and_upstream_errors_are_redacted(self):
        secret = "refresh-secret-that-must-not-leak"
        connections = ScriptedConnections(Response(400, {"error_description": secret}))
        http = oauth.OAuthHTTP(connections)
        status, _payload = http.post_form(
            oauth.TOKEN_PATH,
            {"grant_type": "refresh_token", "refresh_token": secret},
        )
        self.assertEqual(status, 400)
        self.assertEqual(connections.hosts, [(oauth.OAUTH_HOST, oauth.TIMEOUT_SECONDS)])
        args, kwargs = connections.requests[0]
        self.assertEqual(args[:2], ("POST", oauth.TOKEN_PATH))
        self.assertNotIn(secret, json.dumps(kwargs["headers"]))
        oversized = oauth.OAuthHTTP(
            ScriptedConnections(
                Response(200, b"x" * (oauth.MAX_OAUTH_RESPONSE_BYTES + 1))
            )
        )
        with self.assertRaisesRegex(oauth.OAuthError, "byte limit") as caught:
            oversized.post_form(oauth.TOKEN_PATH, {"grant_type": "refresh_token"})
        self.assertNotIn(secret, str(caught.exception))

    def test_authorization_url_is_exact_pkce_s256_and_least_privilege(self):
        verifier = "v" * 64
        value = oauth.authorization_url(CLIENT_ID, "csrf-state", verifier)
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}", oauth.AUTHORIZE_URL
        )
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], [CLIENT_ID])
        self.assertEqual(query["redirect_uri"], [oauth.REDIRECT_URI])
        self.assertEqual(query["scope"], [",".join(oauth.SCOPES)])
        self.assertEqual(query["state"], ["csrf-state"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn(verifier, value)
        self.assertNotIn("client_secret", query)

    def test_callback_requires_exact_url_unique_code_and_matching_state(self):
        good = f"{oauth.REDIRECT_URI}?code=abc&state=expected"
        self.assertEqual(oauth.parse_callback_url(good, "expected"), "abc")
        invalid = (
            f"{oauth.REDIRECT_URI}?code=abc&code=def&state=expected",
            f"{oauth.REDIRECT_URI}?code=abc&state=wrong",
            f"{oauth.REDIRECT_URI}?error=denied&state=expected",
            "http://127.0.0.1:43817/oauth/callback?code=abc&state=expected",
            f"{oauth.REDIRECT_URI}?code=abc&state=expected&extra=1",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(oauth.OAuthError):
                oauth.parse_callback_url(value, "expected")

    def test_exchange_omits_secret_and_validates_rotating_token_pair(self):
        http = FakeHTTP((200, token_payload()))
        result = oauth.exchange_code(
            http,
            code="one-time-code",
            verifier="v" * 64,
            client_id=CLIENT_ID,
            now=1_000,
        )
        path, fields = http.calls[0]
        self.assertEqual(path, oauth.TOKEN_PATH)
        self.assertEqual(fields["grant_type"], "authorization_code")
        self.assertEqual(fields["redirect_uri"], oauth.REDIRECT_URI)
        self.assertEqual(fields["code_verifier"], "v" * 64)
        self.assertNotIn("client_secret", fields)
        self.assertEqual(result["generation"], 1)
        self.assertEqual(result["expires_at"], 87_399)

    def test_token_response_rejects_scope_expansion_and_bad_types(self):
        for change in (
            {"token_type": "Basic"},
            {"scope": "read issues:create comments:create write"},
            {"scope": "read issues:create"},
            {"expires_in": 0},
            {"refresh_token": ""},
        ):
            payload = {**token_payload(), **change}
            with self.subTest(change=change), self.assertRaises(oauth.OAuthError):
                oauth.validate_token_response(
                    payload, client_id=CLIENT_ID, now=0, generation=1
                )

    def test_private_store_is_atomic_and_rejects_permissive_or_symlink_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth" / "linear.json"
            oauth.save_credentials(path, credentials())
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(oauth.load_credentials(path)["access_token"], "access-old")
            path.chmod(0o644)
            with self.assertRaisesRegex(oauth.OAuthError, "0600"):
                oauth.load_credentials(path)
            path.unlink()
            target = Path(directory) / "target"
            target.write_text("{}")
            path.symlink_to(target)
            with self.assertRaisesRegex(oauth.OAuthError, "regular file"):
                oauth.load_credentials(path)

    def test_file_override_never_chmods_an_existing_shared_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "shared"
            parent.mkdir(mode=0o755)
            parent.chmod(0o755)
            with self.assertRaisesRegex(oauth.OAuthError, "0700"):
                oauth.save_credentials(parent / "linear.json", credentials())
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)

    def test_default_backend_uses_system_keyring_not_plaintext_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records: dict[str, bytes] = {}

            def write(account: str, encoded: bytes) -> None:
                records[account] = encoded

            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(oauth, "_keyring_write", side_effect=write),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_delete",
                    side_effect=lambda account: records.pop(account, None),
                ),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                oauth.save_credentials(path, credentials())
                self.assertEqual(oauth.load_credentials(path), credentials())
                self.assertNotIn("access-old", path.read_text())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_keyring_slot_switch_preserves_old_record_on_pointer_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records: dict[str, bytes] = {}

            def write(account: str, encoded: bytes) -> None:
                records[account] = encoded

            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(oauth, "_keyring_write", side_effect=write),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_delete",
                    side_effect=lambda account: records.pop(account, None),
                ),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                oauth.save_credentials(path, credentials())
                first_pointer = path.read_bytes()
                original_atomic = oauth._atomic_write_private

                def fail_pointer(target: Path, encoded: bytes) -> None:
                    if target == path:
                        raise oauth.OAuthError("simulated pointer failure")
                    original_atomic(target, encoded)

                with mock.patch.object(
                    oauth, "_atomic_write_private", side_effect=fail_pointer
                ):
                    with self.assertRaisesRegex(oauth.OAuthError, "pointer failure"):
                        oauth.save_credentials(
                            path, {**credentials(), "access_token": "new"}
                        )
                self.assertEqual(path.read_bytes(), first_pointer)
                self.assertEqual(
                    oauth.load_credentials(path)["access_token"], "access-old"
                )

    def test_keyring_slot_failures_leave_one_complete_selected_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records: dict[str, bytes] = {}

            def write(account: str, encoded: bytes) -> None:
                records[account] = encoded

            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(oauth, "_keyring_write", side_effect=write),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_delete",
                    side_effect=lambda account: records.pop(account, None),
                ),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                oauth.save_credentials(path, credentials())
                with mock.patch.object(
                    oauth,
                    "_keyring_write",
                    side_effect=oauth.OAuthError("write failed"),
                ):
                    with self.assertRaisesRegex(oauth.OAuthError, "write failed"):
                        oauth.save_credentials(
                            path, {**credentials(), "access_token": "lost"}
                        )
                self.assertEqual(
                    oauth.load_credentials(path)["access_token"], "access-old"
                )
                with mock.patch.object(
                    oauth,
                    "_keyring_delete",
                    side_effect=oauth.OAuthError("cleanup failed"),
                ):
                    with self.assertRaisesRegex(oauth.OAuthError, "cleanup failed"):
                        oauth.save_credentials(
                            path, {**credentials(), "access_token": "new"}
                        )
                self.assertEqual(oauth.load_credentials(path)["access_token"], "new")
                self.assertEqual(len(records), 1)

    def test_system_keyring_lock_path_ignores_xdg_state_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/one"}, clear=False):
            first = oauth.oauth_store_path()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/two"}, clear=False):
            second = oauth.oauth_store_path()
        self.assertEqual(first, second)

    def test_keyring_logout_retries_discoverable_inactive_token_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records: dict[str, bytes] = {}
            fail_cleanup = [False]

            def delete(account: str) -> None:
                if account in records and fail_cleanup[0]:
                    raise oauth.OAuthError("cleanup failed")
                records.pop(account, None)

            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(
                    oauth,
                    "_keyring_write",
                    side_effect=lambda account, encoded: records.__setitem__(
                        account, encoded
                    ),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(oauth, "_keyring_delete", side_effect=delete),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                oauth.save_credentials(path, credentials())
                fail_cleanup[0] = True
                with self.assertRaisesRegex(oauth.OAuthError, "cleanup failed"):
                    oauth.logout(local_only=True)
                self.assertEqual(len(records), 2)
                fail_cleanup[0] = False
                self.assertTrue(oauth.logout(local_only=True))
                self.assertEqual(len(records), 1)
                remaining = json.loads(next(iter(records.values())))
                self.assertNotIn("access_token", remaining)
                self.assertNotIn("refresh_token", remaining)

    def test_keyring_load_cleans_first_write_slot_without_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records = {
                oauth.KEYRING_SLOTS[0]: json.dumps(credentials()).encode("utf-8")
            }
            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_delete",
                    side_effect=lambda account: records.pop(account, None),
                ),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                self.assertEqual(oauth.load_credentials(path), {})
                self.assertEqual(records, {})

    def test_keyring_logout_without_client_id_strictly_removes_every_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "linear.json"
            records: dict[str, bytes] = {}

            def delete(account: str) -> None:
                records.pop(account, None)

            without_client = credentials()
            without_client.pop("client_id")
            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(oauth, "oauth_store_path", return_value=path),
                mock.patch.object(
                    oauth,
                    "_keyring_write",
                    side_effect=lambda account, encoded: records.__setitem__(
                        account, encoded
                    ),
                ),
                mock.patch.object(
                    oauth,
                    "_keyring_read",
                    side_effect=lambda account: records.get(account),
                ),
                mock.patch.object(oauth, "_keyring_delete", side_effect=delete),
            ):
                os.environ.pop("TWEED_LINEAR_OAUTH_FILE", None)
                oauth.save_credentials(path, without_client)
                active = oauth._keyring_active_account(path)

                def fail_active(account: str) -> None:
                    if account == active:
                        raise oauth.OAuthError("cleanup failed")
                    delete(account)

                with mock.patch.object(
                    oauth, "_keyring_delete", side_effect=fail_active
                ):
                    with self.assertRaisesRegex(oauth.OAuthError, "cleanup failed"):
                        oauth.logout(local_only=True)
                self.assertFalse(path.exists())
                self.assertIn(active, records)
                records[oauth.KEYRING_ACCOUNT] = json.dumps(without_client).encode()
                self.assertTrue(oauth.logout(local_only=True))
                self.assertEqual(records, {})
                self.assertFalse(path.exists())

    def test_credential_lock_serializes_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth" / "linear.json"
            marker = Path(directory) / "acquired"
            script = (
                "from pathlib import Path; import tweed_linear_oauth as o; "
                f"p=Path({str(path)!r}); m=Path({str(marker)!r}); "
                "\nwith o.credential_lock(p): m.write_text('yes')"
            )
            with oauth.credential_lock(path):
                process = subprocess.Popen(
                    [sys.executable, "-c", script],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                time.sleep(0.2)
                self.assertFalse(marker.exists())
                self.assertIsNone(process.poll())
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, (stdout, stderr))
            self.assertEqual(marker.read_text(), "yes")

    def test_login_lock_does_not_block_normal_credential_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth" / "linear.json"
            oauth.save_credentials(path, credentials())
            script = (
                "from pathlib import Path; import tweed_linear_oauth as o; "
                f"print(o.access_token(path=Path({str(path)!r}), clock=lambda:1000))"
            )
            with oauth.login_lock(path):
                completed = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "access-old")

    def test_logout_waits_for_inflight_login_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth" / "linear.json"
            oauth.save_credentials(path, credentials())
            script = "import tweed_linear_oauth as o; print(o.logout(local_only=True))"
            environment = {**os.environ, "TWEED_LINEAR_OAUTH_FILE": str(path)}
            with oauth.login_lock(path):
                process = subprocess.Popen(
                    [sys.executable, "-c", script],
                    cwd=Path(__file__).resolve().parents[1],
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                time.sleep(0.2)
                self.assertIsNone(process.poll())
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), "True")
            self.assertNotIn("access_token", oauth.load_credentials(path))

    def test_refresh_is_locked_rotates_atomically_and_replays_ambiguous_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth" / "linear.json"
            oauth.save_credentials(path, credentials(expired=True))
            http = FakeHTTP(
                oauth.OAuthTransportError("offline"),
                (200, token_payload()),
            )
            value = oauth.access_token(path=path, http=http, clock=lambda: 1_000)
            self.assertEqual(value, "access-new")
            self.assertEqual(len(http.calls), 2)
            self.assertEqual(http.calls[0], http.calls[1])
            self.assertNotIn("client_secret", http.calls[0][1])
            stored = oauth.load_credentials(path)
            self.assertEqual(stored["refresh_token"], "refresh-new")
            self.assertEqual(stored["generation"], 2)
            self.assertNotIn("pending_refresh", stored)

    def test_refresh_pending_state_must_match_and_remain_inside_grace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            value = credentials(expired=True)
            value["pending_refresh"] = {
                "generation": 1,
                "started_at": 1_000 - oauth.REFRESH_REPLAY_SECONDS - 1,
                "refresh_fingerprint": "wrong",
            }
            oauth.save_credentials(path, value)
            with self.assertRaises(oauth.OAuthError):
                oauth.access_token(path=path, http=FakeHTTP(), clock=lambda: 1_000)
            value["pending_refresh"]["refresh_fingerprint"] = (
                __import__("hashlib").sha256(b"refresh-old").hexdigest()
            )
            oauth.save_credentials(path, value)
            with self.assertRaisesRegex(oauth.OAuthError, "grace expired"):
                oauth.access_token(path=path, http=FakeHTTP(), clock=lambda: 1_000)

    def test_definitive_refresh_rejection_requires_login_without_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials(expired=True))
            http = FakeHTTP((400, {"error": "invalid_grant"}))
            with self.assertRaisesRegex(oauth.OAuthError, "run tweed auth login"):
                oauth.access_token(path=path, http=http, clock=lambda: 1_000)
            stored = oauth.load_credentials(path)
            self.assertTrue(stored["reauthorization_required"])
            self.assertNotIn("pending_refresh", stored)
            with self.assertRaisesRegex(oauth.OAuthError, "login required"):
                oauth.access_token(path=path, http=FakeHTTP(), clock=lambda: 1_001)
            self.assertEqual(len(http.calls), 1)

    def test_refresh_rate_limit_is_not_immediately_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials(expired=True))
            http = FakeHTTP((429, {"error": "rate_limited"}))
            with self.assertRaisesRegex(oauth.OAuthError, "rate limit"):
                oauth.access_token(path=path, http=http, clock=lambda: 1_000)
            self.assertEqual(len(http.calls), 1)
            self.assertIn("pending_refresh", oauth.load_credentials(path))

    def test_ambiguous_refresh_recovery_does_not_extend_grace_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials(expired=True))
            first = FakeHTTP(
                oauth.OAuthTransportError("lost"),
                oauth.OAuthTransportError("lost"),
            )
            with self.assertRaises(oauth.OAuthTransportError):
                oauth.access_token(path=path, http=first, clock=lambda: 1_000)
            started = oauth.load_credentials(path)["pending_refresh"]["started_at"]
            second = FakeHTTP(
                oauth.OAuthTransportError("lost"),
                oauth.OAuthTransportError("lost"),
            )
            with self.assertRaises(oauth.OAuthTransportError):
                oauth.access_token(path=path, http=second, clock=lambda: 1_100)
            self.assertEqual(
                oauth.load_credentials(path)["pending_refresh"]["started_at"], started
            )

    def test_refresh_crash_after_response_recovers_with_old_token_inside_grace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials(expired=True))
            original_save = oauth.save_credentials

            def crash_on_rotated(target: Path, value: dict) -> None:
                if value.get("generation") == 2:
                    raise oauth.OAuthError("simulated crash before durable rotation")
                original_save(target, value)

            with mock.patch.object(
                oauth, "save_credentials", side_effect=crash_on_rotated
            ):
                with self.assertRaisesRegex(oauth.OAuthError, "simulated crash"):
                    oauth.access_token(
                        path=path,
                        http=FakeHTTP((200, token_payload())),
                        clock=lambda: 1_000,
                    )
            self.assertIn("pending_refresh", oauth.load_credentials(path))
            recovered = oauth.access_token(
                path=path,
                http=FakeHTTP((200, token_payload("access-replay", "refresh-replay"))),
                clock=lambda: 1_001,
            )
            self.assertEqual(recovered, "access-replay")
            self.assertNotIn("pending_refresh", oauth.load_credentials(path))

    def test_manual_login_checks_state_and_never_stores_code_or_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            http = FakeHTTP((200, token_payload()))
            redirected = f"{oauth.REDIRECT_URI}?code=secret-code&state=fixed-state"
            with (
                mock.patch.dict(os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}),
                mock.patch.object(
                    oauth.secrets,
                    "token_urlsafe",
                    side_effect=["fixed-state", "v" * 64],
                ),
                mock.patch("builtins.print"),
            ):
                result = oauth.login(
                    CLIENT_ID,
                    manual=True,
                    http=http,
                    clock=lambda: 1_000,
                    input_fn=lambda _prompt: redirected,
                )
            stored = json.loads(path.read_text())
            self.assertEqual(result["access_token"], "access-new")
            self.assertNotIn("secret-code", path.read_text())
            self.assertNotIn("v" * 64, path.read_text())
            self.assertNotIn("pending_refresh", stored)
            self.assertEqual(stored["client_id"], CLIENT_ID)

    def test_login_without_override_uses_and_persists_official_client_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            http = FakeHTTP((200, token_payload()))
            redirected = f"{oauth.REDIRECT_URI}?code=code&state=fixed-state"
            with (
                mock.patch.dict(os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}),
                mock.patch.object(
                    oauth.secrets,
                    "token_urlsafe",
                    side_effect=["fixed-state", "v" * 64],
                ),
                mock.patch("builtins.print"),
            ):
                oauth.login(
                    None,
                    manual=True,
                    http=http,
                    clock=lambda: 1_000,
                    input_fn=lambda _prompt: redirected,
                )
            self.assertEqual(http.calls[0][1]["client_id"], OFFICIAL_CLIENT_ID)
            self.assertEqual(
                oauth.load_credentials(path)["client_id"], OFFICIAL_CLIENT_ID
            )

    def test_explicit_empty_client_id_override_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            with mock.patch.dict(os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}):
                with self.assertRaisesRegex(oauth.OAuthError, "identity is missing"):
                    oauth.login("", manual=True, input_fn=lambda _prompt: "unused")
            self.assertFalse(path.exists())

    def test_status_is_ready_for_login_without_stored_client_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            value = oauth.status(path=path)
            self.assertTrue(value["configured"])
            self.assertFalse(value["logged_in"])

    def test_manual_login_rejects_platform_without_bounded_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            with (
                mock.patch.dict(os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}),
                mock.patch.object(
                    oauth, "manual_timeout_supported", return_value=False
                ),
                mock.patch("builtins.print"),
            ):
                with self.assertRaisesRegex(oauth.OAuthError, "bounded manual login"):
                    oauth.login(CLIENT_ID, manual=True, input_fn=input)

    def test_loopback_ignores_invalid_request_then_accepts_valid_callback(self):
        result: dict[str, object] = {}

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        def listen() -> None:
            try:
                result["code"] = oauth._loopback_callback("expected", 3)
            except BaseException as error:  # noqa: BLE001 - asserted by test
                result["error"] = error

        with (
            mock.patch.object(oauth, "REDIRECT_PORT", port),
            mock.patch.object(
                oauth,
                "REDIRECT_URI",
                f"http://{oauth.REDIRECT_HOST}:{port}{oauth.REDIRECT_PATH}",
            ),
        ):
            thread = threading.Thread(target=listen)
            thread.start()
            for _ in range(50):
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port)
                    connection.request(
                        "GET",
                        "/wrong?code=bad&state=expected",
                        headers={"Host": f"{oauth.REDIRECT_HOST}:{port}"},
                    )
                    self.assertEqual(connection.getresponse().status, 400)
                    connection.close()
                    break
                except OSError:
                    time.sleep(0.02)
            for _ in range(50):
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port)
                    connection.request(
                        "GET",
                        f"{oauth.REDIRECT_PATH}?code=good&state=expected",
                        headers={"Host": f"{oauth.REDIRECT_HOST}:{port}"},
                    )
                    self.assertEqual(connection.getresponse().status, 200)
                    connection.close()
                    break
                except OSError:
                    time.sleep(0.02)
            else:
                self.fail(f"loopback server stopped before valid callback: {result!r}")
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", result)
        self.assertEqual(result.get("code"), "good")

    def test_live_status_refreshes_and_validates_viewer_without_returning_token(self):
        class ViewerHTTP(FakeHTTP):
            def graphql_viewer(self, access_token_value: str):
                self.viewer_token = access_token_value
                return {"id": "user-1", "name": "Arya"}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials())
            http = ViewerHTTP()
            value = oauth.status(path=path, http=http, clock=lambda: 1_000)
            self.assertEqual(value["viewer"], {"id": "user-1", "name": "Arya"})
            self.assertEqual(http.viewer_token, "access-old")
            self.assertNotIn("access_token", value)

    def test_logout_revokes_refresh_and_access_then_clears_local_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials())
            http = FakeHTTP((200, {}), (200, {}))
            with mock.patch.dict(os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}):
                self.assertTrue(oauth.logout(http=http))
            self.assertEqual([item[0] for item in http.calls], [oauth.REVOKE_PATH] * 2)
            self.assertEqual(http.calls[0][1]["token_type_hint"], "refresh_token")
            self.assertEqual(http.calls[1][1]["token_type_hint"], "access_token")
            stored = oauth.load_credentials(path)
            self.assertEqual(stored, {"schema_version": 1, "client_id": CLIENT_ID})

    def test_logout_clears_local_tokens_but_does_not_confirm_400_or_401(self):
        for status in (400, 401):
            with (
                self.subTest(status=status),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "linear.json"
                oauth.save_credentials(path, credentials())
                http = FakeHTTP((status, {}), (200, {}))
                with mock.patch.dict(
                    os.environ, {"TWEED_LINEAR_OAUTH_FILE": str(path)}
                ):
                    self.assertFalse(oauth.logout(http=http))
                self.assertNotIn("access_token", oauth.load_credentials(path))

    def test_401_invalidation_expires_only_matching_access_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "linear.json"
            oauth.save_credentials(path, credentials())
            oauth.invalidate_access_token("different", path=path)
            self.assertGreater(oauth.load_credentials(path)["expires_at"], 0)
            oauth.invalidate_access_token("access-old", path=path)
            self.assertEqual(oauth.load_credentials(path)["expires_at"], 0)

    def test_checked_manifest_is_private_pkce_only_with_exact_redirect(self):
        manifest = json.loads(
            (Path(__file__).resolve().parents[1] / "linear-oauth-app.json").read_text()
        )
        self.assertEqual(manifest["schemaVersion"], "1.0.0")
        self.assertEqual(manifest["distribution"], "private")
        self.assertEqual(manifest["oauth"]["redirect_uris"], [oauth.REDIRECT_URI])
        self.assertEqual(manifest["oauth"]["grant_types"], ["authorization_code"])
        self.assertNotIn("client_secret", json.dumps(manifest))

    def test_adapter_defaults_to_oauth_and_api_key_requires_explicit_mode(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                adapter.oauth, "access_token", return_value="oauth-secret"
            ),
        ):
            self.assertEqual(
                adapter.authorization_from_environment(), "Bearer oauth-secret"
            )
        with mock.patch.dict(
            os.environ,
            {"TWEED_LINEAR_AUTH": "api-key", "LINEAR_API_KEY": "api-secret"},
            clear=True,
        ):
            self.assertEqual(adapter.authorization_from_environment(), "api-secret")
        with mock.patch.dict(os.environ, {"LINEAR_API_KEY": "ignored"}, clear=True):
            with mock.patch.object(
                adapter.oauth, "access_token", return_value="oauth-secret"
            ):
                self.assertEqual(
                    adapter.authorization_from_environment(), "Bearer oauth-secret"
                )
        with mock.patch.dict(os.environ, {"TWEED_LINEAR_AUTH": "api-key"}, clear=True):
            with self.assertRaises(adapter.AdapterError):
                adapter.authorization_from_environment()


if __name__ == "__main__":
    unittest.main()
