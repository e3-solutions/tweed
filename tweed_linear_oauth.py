#!/usr/bin/env python3
"""First-party Linear OAuth2/PKCE credentials for Tweed's GraphQL adapter."""

from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import tempfile
import time
from typing import Any, Callable, Iterator
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

try:
    import pwd
except ImportError:  # pragma: no cover - Windows
    pwd = None


AUTHORIZE_URL = "https://linear.app/oauth/authorize"
OAUTH_HOST = "api.linear.app"
TOKEN_PATH = "/oauth/token"
REVOKE_PATH = "/oauth/revoke"
GRAPHQL_PATH = "/graphql"
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 43817
REDIRECT_PATH = "/oauth/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"
SCOPES = ("read", "issues:create", "comments:create")
DEFAULT_CLIENT_ID = "6e807fb3d574eb3e13bee2dc0bf3337e"
STORE_SCHEMA = 1
TIMEOUT_SECONDS = 30
CALLBACK_TIMEOUT_SECONDS = 300
MAX_OAUTH_RESPONSE_BYTES = 65_536
MAX_TOKEN_BYTES = 8_192
REFRESH_SKEW_SECONDS = 300
REFRESH_REPLAY_SECONDS = 25 * 60
KEYRING_SERVICE = "dev.tweed.linear.oauth"
KEYRING_ACCOUNT = "default"
KEYRING_SLOT_PREFIX = "record-"
KEYRING_SLOTS = (KEYRING_SLOT_PREFIX + "a", KEYRING_SLOT_PREFIX + "b")


class OAuthError(RuntimeError):
    """A bounded, deliberately redacted OAuth failure."""


class OAuthTransportError(OAuthError):
    """A request may have reached Linear but no valid response was received."""


class OAuthUnauthorized(OAuthError):
    """Linear rejected an access token during a read-only validation."""


def oauth_store_path() -> Path:
    override = os.environ.get("TWEED_LINEAR_OAUTH_FILE", "").strip()
    if override:
        return Path(os.path.abspath(Path(override).expanduser()))
    # The system-keyring lock and nonsecret active-slot pointer must be shared by
    # every process that can address the fixed keyring service. Do not key them
    # by caller-controlled XDG_STATE_HOME.
    if pwd is not None and hasattr(os, "getuid"):
        base = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state"
    else:  # pragma: no cover - Windows uses its canonical profile directory.
        base = Path.home() / ".local/state"
    return Path(os.path.abspath(base / "tweed/auth/linear.json"))


def _secure_directory(path: Path) -> None:
    existed = path.exists()
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise OAuthError("Linear credential directory is not a real directory")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise OAuthError("Linear credential directory has the wrong owner")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        if existed:
            raise OAuthError("Linear credential directory permissions must be 0700")
        path.chmod(0o700)


def _uses_system_keyring(path: Path) -> bool:
    return not os.environ.get("TWEED_LINEAR_OAUTH_FILE", "").strip() and path == oauth_store_path()


def _keyring_module():
    try:
        import keyring
        import keyring.errors
    except ImportError as error:
        raise OAuthError("system credential storage is unavailable") from error
    backend = keyring.get_keyring()
    module = type(backend).__module__
    allowed = (
        "keyring.backends.macOS",
        "keyring.backends.Windows",
        "keyring.backends.SecretService",
    )
    if not module.startswith(allowed) or getattr(backend, "priority", 0) <= 0:
        raise OAuthError(
            "a supported system credential store is unavailable; configure the OS keyring"
        )
    return keyring


def _keyring_read(account: str = KEYRING_ACCOUNT) -> bytes | None:
    keyring = _keyring_module()
    try:
        value = keyring.get_password(KEYRING_SERVICE, account)
    except keyring.errors.KeyringError as error:
        raise OAuthError("system credential storage could not be read") from error
    return value.encode("utf-8") if value is not None else None


def _keyring_write(account: str, encoded: bytes) -> None:
    keyring = _keyring_module()
    try:
        keyring.set_password(KEYRING_SERVICE, account, encoded.decode("utf-8"))
    except keyring.errors.KeyringError as error:
        raise OAuthError("system credential storage could not be updated") from error


def _keyring_delete(account: str) -> None:
    keyring = _keyring_module()
    try:
        if keyring.get_password(KEYRING_SERVICE, account) is None:
            return
        keyring.delete_password(KEYRING_SERVICE, account)
    except keyring.errors.KeyringError as error:
        raise OAuthError("system credential storage could not be updated") from error


def _check_private_file(path: Path) -> None:
    if not path.exists():
        return
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise OAuthError("Linear credential file is not a regular file")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise OAuthError("Linear credential file has the wrong owner")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise OAuthError("Linear credential file permissions must be 0600")


def _validate_private_descriptor(descriptor: int, label: str) -> None:
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        raise OAuthError(f"Linear {label} is not a regular file")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise OAuthError(f"Linear {label} has the wrong owner")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise OAuthError(f"Linear {label} permissions must be 0600")


def _read_private_file(path: Path, label: str) -> bytes | None:
    _check_private_file(path)
    if not path.exists():
        return None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            _validate_private_descriptor(descriptor, label)
            chunks: list[bytes] = []
            remaining = MAX_OAUTH_RESPONSE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise OAuthError(f"Linear {label} could not be read safely") from error
    if len(raw) > MAX_OAUTH_RESPONSE_BYTES:
        raise OAuthError(f"Linear {label} exceeds the byte limit")
    return raw


def _atomic_write_private(path: Path, encoded: bytes) -> None:
    _secure_directory(path.parent)
    _check_private_file(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".linear.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _keyring_active_account(path: Path) -> str | None:
    raw = _read_private_file(path, "credential pointer")
    if raw is None:
        return None
    try:
        pointer = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OAuthError("Linear credential pointer is invalid") from error
    account = pointer.get("account") if isinstance(pointer, dict) else None
    if (
        not isinstance(account, str)
        or account not in KEYRING_SLOTS
    ):
        raise OAuthError("Linear credential pointer is invalid")
    return account


@contextlib.contextmanager
def _named_lock(path: Path | None, suffix: str) -> Iterator[Path]:
    store = path or oauth_store_path()
    _secure_directory(store.parent)
    lock_path = store.with_suffix(store.suffix + suffix)
    _check_private_file(lock_path)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise OAuthError("Linear credential lock could not be opened safely") from error
    try:
        os.fchmod(descriptor, 0o600)
        _validate_private_descriptor(descriptor, "credential lock")
        with os.fdopen(descriptor, "r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield store
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        raise


@contextlib.contextmanager
def credential_lock(path: Path | None = None) -> Iterator[Path]:
    with _named_lock(path, ".lock") as store:
        yield store


@contextlib.contextmanager
def login_lock(path: Path | None = None) -> Iterator[Path]:
    with _named_lock(path, ".login.lock") as store:
        yield store


def load_credentials(path: Path) -> dict[str, Any]:
    if _uses_system_keyring(path):
        account = _keyring_active_account(path)
        if account is None:
            # A first-write crash can leave a deterministic slot before any
            # pointer exists. Neither slot is authoritative in that state.
            for stale in KEYRING_SLOTS:
                _keyring_delete(stale)
        raw = _keyring_read(account or KEYRING_ACCOUNT)
        if raw is None:
            if account is not None:
                raise OAuthError("system credential record is missing")
            return {}
        if account is not None:
            for stale in (*KEYRING_SLOTS, KEYRING_ACCOUNT):
                if stale != account:
                    _keyring_delete(stale)
        if len(raw) > MAX_OAUTH_RESPONSE_BYTES:
            raise OAuthError("Linear credential record exceeds the byte limit")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OAuthError("Linear credential record is invalid") from error
        if not isinstance(value, dict) or value.get("schema_version") != STORE_SCHEMA:
            raise OAuthError("unsupported Linear credential record")
        return value
    raw = _read_private_file(path, "credential file")
    if raw is None:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OAuthError("Linear credential file is invalid") from error
    if not isinstance(value, dict) or value.get("schema_version") != STORE_SCHEMA:
        raise OAuthError("unsupported Linear credential file")
    return value


def save_credentials(path: Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(encoded) > MAX_OAUTH_RESPONSE_BYTES:
        raise OAuthError("Linear credential file exceeds the byte limit")
    if _uses_system_keyring(path):
        previous = _keyring_active_account(path)
        account = KEYRING_SLOTS[1] if previous == KEYRING_SLOTS[0] else KEYRING_SLOTS[0]
        _keyring_write(account, encoded)
        pointer = json.dumps(
            {"schema_version": STORE_SCHEMA, "account": account},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        try:
            _atomic_write_private(path, pointer)
        except BaseException:
            _keyring_delete(account)
            raise
        if previous is not None:
            _keyring_delete(previous)
        _keyring_delete(KEYRING_ACCOUNT)
        return
    _atomic_write_private(path, encoded)


def clear_tokens(path: Path, credentials: dict[str, Any]) -> None:
    client_id = credentials.get("client_id")
    if client_id:
        save_credentials(path, {"schema_version": STORE_SCHEMA, "client_id": client_id})
    else:
        if _uses_system_keyring(path):
            active = _keyring_active_account(path)
            for account in (*KEYRING_SLOTS, KEYRING_ACCOUNT):
                if account != active:
                    _keyring_delete(account)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                raise OAuthError("Linear credential pointer could not be removed") from error
            if active is not None:
                _keyring_delete(active)
        else:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def _client_id(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 512:
        raise OAuthError("Linear OAuth client identity is missing; run tweed auth login")
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise OAuthError("Linear OAuth client ID is invalid")
    return value


def _scope_set(value: object) -> set[str]:
    if isinstance(value, str):
        scopes = {item for item in value.replace(",", " ").split() if item}
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        scopes = set(value)
    else:
        raise OAuthError("Linear returned invalid OAuth scopes")
    required = set(SCOPES)
    if not required.issubset(scopes):
        raise OAuthError("Linear OAuth grant is missing required scopes")
    if scopes - required:
        raise OAuthError("Linear OAuth grant contains unexpected scopes")
    return scopes


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > MAX_TOKEN_BYTES:
        raise OAuthError(f"Linear returned an invalid {label}")
    if "\r" in value or "\n" in value:
        raise OAuthError(f"Linear returned an invalid {label}")
    return value


def _pkce_verifier(value: object) -> str:
    if not isinstance(value, str) or not 43 <= len(value) <= 128:
        raise OAuthError("PKCE verifier is invalid")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise OAuthError("PKCE verifier is invalid") from error
    allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    if any(character not in allowed for character in encoded):
        raise OAuthError("PKCE verifier is invalid")
    return value


def validate_token_response(
    value: object,
    *,
    client_id: str,
    now: float,
    generation: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OAuthError("Linear returned an invalid OAuth response")
    if str(value.get("token_type", "")).lower() != "bearer":
        raise OAuthError("Linear returned an unsupported token type")
    expires = value.get("expires_in")
    if not isinstance(expires, (int, float)) or not 60 <= expires <= 172_800:
        raise OAuthError("Linear returned an invalid token lifetime")
    scopes = _scope_set(value.get("scope"))
    return {
        "schema_version": STORE_SCHEMA,
        "client_id": _client_id(client_id),
        "access_token": _token(value.get("access_token"), "access token"),
        "refresh_token": _token(value.get("refresh_token"), "refresh token"),
        "token_type": "Bearer",
        "scopes": sorted(scopes),
        "issued_at": int(now),
        "expires_at": int(now + float(expires)),
        "generation": generation,
    }


class OAuthHTTP:
    def __init__(
        self,
        connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    ) -> None:
        self.connection_factory = connection_factory

    def post_form(self, path: str, fields: dict[str, str]) -> tuple[int, object]:
        if path not in {TOKEN_PATH, REVOKE_PATH}:
            raise OAuthError("unsupported Linear OAuth endpoint")
        encoded = urlencode(fields).encode("ascii")
        if len(encoded) > 32_768:
            raise OAuthError("Linear OAuth request exceeds the byte limit")
        connection = None
        try:
            connection = self.connection_factory(OAUTH_HOST, timeout=TIMEOUT_SECONDS)
            connection.request(
                "POST",
                path,
                body=encoded,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "tweed-linear-oauth/1",
                },
            )
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length) > MAX_OAUTH_RESPONSE_BYTES:
                        raise OAuthError("Linear OAuth response exceeds the byte limit")
                except ValueError as error:
                    raise OAuthError("Linear returned an invalid OAuth response") from error
            raw = response.read(MAX_OAUTH_RESPONSE_BYTES + 1)
        except OAuthError:
            raise
        except (TimeoutError, OSError, http.client.HTTPException) as error:
            raise OAuthTransportError("Linear OAuth transport failed") from error
        finally:
            if connection is not None:
                with contextlib.suppress(OSError, http.client.HTTPException):
                    connection.close()
        if len(raw) > MAX_OAUTH_RESPONSE_BYTES:
            raise OAuthError("Linear OAuth response exceeds the byte limit")
        if not raw:
            return response.status, {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OAuthError("Linear returned an invalid OAuth response") from error
        return response.status, payload

    def graphql_viewer(self, access_token_value: str) -> dict[str, str]:
        token = _token(access_token_value, "access token")
        encoded = json.dumps(
            {"query": "query TweedOAuthViewer { viewer { id name } }"},
            separators=(",", ":"),
        ).encode("utf-8")
        connection = None
        try:
            connection = self.connection_factory(OAUTH_HOST, timeout=TIMEOUT_SECONDS)
            connection.request(
                "POST",
                GRAPHQL_PATH,
                body=encoded,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                    "User-Agent": "tweed-linear-oauth/1",
                },
            )
            response = connection.getresponse()
            raw = response.read(MAX_OAUTH_RESPONSE_BYTES + 1)
        except (TimeoutError, OSError, http.client.HTTPException) as error:
            raise OAuthTransportError("Linear OAuth status check failed") from error
        finally:
            if connection is not None:
                with contextlib.suppress(OSError, http.client.HTTPException):
                    connection.close()
        if len(raw) > MAX_OAUTH_RESPONSE_BYTES:
            raise OAuthError("Linear OAuth status response exceeds the byte limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OAuthError("Linear returned an invalid OAuth status response") from error
        if response.status == 401:
            raise OAuthUnauthorized("Linear OAuth credential validation failed")
        if response.status != 200 or not isinstance(payload, dict) or payload.get("errors"):
            raise OAuthError("Linear OAuth credential validation failed")
        viewer = (payload.get("data") or {}).get("viewer")
        if (
            not isinstance(viewer, dict)
            or not isinstance(viewer.get("id"), str)
            or not isinstance(viewer.get("name"), str)
        ):
            raise OAuthError("Linear returned an invalid OAuth viewer")
        return {"id": viewer["id"], "name": viewer["name"]}


def exchange_code(
    http: OAuthHTTP,
    *,
    code: str,
    verifier: str,
    client_id: str,
    now: float,
) -> dict[str, Any]:
    status, payload = http.post_form(
        TOKEN_PATH,
        {
            "grant_type": "authorization_code",
            "code": _token(code, "authorization code"),
            "redirect_uri": REDIRECT_URI,
            "client_id": _client_id(client_id),
            "code_verifier": _pkce_verifier(verifier),
        },
    )
    if status != 200:
        raise OAuthError("Linear rejected the OAuth authorization")
    return validate_token_response(payload, client_id=client_id, now=now, generation=1)


def refresh_credentials(
    path: Path,
    credentials: dict[str, Any],
    *,
    http: OAuthHTTP,
    now: float,
) -> dict[str, Any]:
    refresh_token = _token(credentials.get("refresh_token"), "refresh token")
    client_id = _client_id(credentials.get("client_id"))
    generation = credentials.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise OAuthError("Linear credential generation is invalid")
    pending = credentials.get("pending_refresh")
    if pending is None:
        pending = {
            "generation": generation,
            "started_at": int(now),
            "refresh_fingerprint": hashlib.sha256(refresh_token.encode()).hexdigest(),
        }
        save_credentials(path, {**credentials, "pending_refresh": pending})
    fields = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    last_error: OAuthError | None = None
    for attempt in range(2):
        try:
            status, payload = http.post_form(TOKEN_PATH, fields)
            if status != 200:
                if status == 429:
                    raise OAuthError("Linear OAuth rate limit reached; retry later")
                if 400 <= status < 500 and status not in {408, 429}:
                    terminal = {
                        key: value
                        for key, value in credentials.items()
                        if key != "pending_refresh"
                    }
                    terminal["reauthorization_required"] = True
                    save_credentials(path, terminal)
                    raise OAuthError(
                        "Linear rejected the OAuth refresh; run tweed auth login"
                    )
                raise OAuthTransportError("Linear OAuth refresh outcome is ambiguous")
            refreshed = validate_token_response(
                payload,
                client_id=client_id,
                now=now,
                generation=generation + 1,
            )
            save_credentials(path, refreshed)
            return refreshed
        except OAuthTransportError as error:
            last_error = error
            if attempt == 0:
                continue
            break
    raise last_error or OAuthError("Linear OAuth refresh failed")


def access_token(
    *,
    path: Path | None = None,
    http: OAuthHTTP | None = None,
    clock: Callable[[], float] = time.time,
) -> str:
    with credential_lock(path) as store:
        credentials = load_credentials(store)
        token = credentials.get("access_token")
        expires_at = credentials.get("expires_at")
        now = clock()
        if isinstance(token, str) and isinstance(expires_at, (int, float)):
            if expires_at > now + REFRESH_SKEW_SECONDS:
                return _token(token, "access token")
        pending = credentials.get("pending_refresh")
        if pending is not None:
            if not isinstance(pending, dict) or not isinstance(
                pending.get("started_at"), (int, float)
            ):
                raise OAuthError("Linear refresh recovery state is invalid")
            refresh = credentials.get("refresh_token")
            fingerprint = (
                hashlib.sha256(refresh.encode()).hexdigest()
                if isinstance(refresh, str)
                else None
            )
            if (
                pending.get("generation") != credentials.get("generation")
                or pending.get("refresh_fingerprint") != fingerprint
            ):
                raise OAuthError("Linear refresh recovery state does not match")
            age = now - float(pending["started_at"])
            if age < 0 or age > REFRESH_REPLAY_SECONDS:
                raise OAuthError("Linear refresh recovery grace expired; run tweed auth login")
        if not credentials.get("refresh_token"):
            raise OAuthError("Linear OAuth login required; run tweed auth login")
        if credentials.get("reauthorization_required") is True:
            raise OAuthError("Linear OAuth login required; run tweed auth login")
        refreshed = refresh_credentials(
            store, credentials, http=http or OAuthHTTP(), now=now
        )
        return refreshed["access_token"]


def invalidate_access_token(expected: str, *, path: Path | None = None) -> None:
    """Expire only the credential generation that produced an observed 401."""
    with credential_lock(path) as store:
        credentials = load_credentials(store)
        if credentials.get("access_token") != expected:
            return
        save_credentials(store, {**credentials, "expires_at": 0})


def authorization_url(client_id: str, state_value: str, verifier: str) -> str:
    verifier = _pkce_verifier(verifier)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return AUTHORIZE_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": _client_id(client_id),
            "redirect_uri": REDIRECT_URI,
            "scope": ",".join(SCOPES),
            "state": state_value,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",
        }
    )


def parse_callback_url(value: str, expected_state: str) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 8_192:
        raise OAuthError("Linear OAuth callback URL is invalid")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise OAuthError("Linear OAuth callback URL is invalid") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname != REDIRECT_HOST
        or port != REDIRECT_PORT
        or parsed.path != REDIRECT_PATH
        or parsed.fragment
    ):
        raise OAuthError("Linear OAuth callback URL is invalid")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise OAuthError("Linear OAuth callback is invalid") from error
    if set(query) - {"code", "state", "error", "error_description"}:
        raise OAuthError("Linear OAuth callback has unexpected parameters")
    if "error" in query:
        raise OAuthError("Linear authorization was denied")
    if set(query) != {"code", "state"} or any(len(values) != 1 for values in query.values()):
        raise OAuthError("Linear OAuth callback is incomplete")
    if not hmac.compare_digest(query["state"][0], expected_state):
        raise OAuthError("Linear OAuth callback state did not match")
    return _token(query["code"][0], "authorization code")


def _loopback_callback(expected_state: str, timeout: int) -> str:
    result: dict[str, str] = {}

    class CallbackServer(HTTPServer):
        allow_reuse_address = False

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address

        def handle_error(self, _request, _client_address) -> None:
            return

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            host = self.headers.get("Host", "")
            try:
                if host != f"{REDIRECT_HOST}:{REDIRECT_PORT}":
                    raise OAuthError("Linear OAuth callback host is invalid")
                result["code"] = parse_callback_url(
                    f"http://{host}{self.path}", expected_state
                )
                body = b"Tweed is connected to Linear. You may close this window.\n"
                self.send_response(200)
            except OAuthError:
                body = b"Tweed could not accept this Linear authorization.\n"
                self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            return

    try:
        server = CallbackServer(("127.0.0.1", REDIRECT_PORT), Handler)
    except OSError as error:
        raise OAuthError(
            f"localhost port {REDIRECT_PORT} is unavailable; use tweed auth login --manual"
        ) from error
    try:
        deadline = time.monotonic() + timeout
        while "code" not in result:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            server.timeout = remaining
            try:
                server.handle_request()
            except (TimeoutError, OSError):
                continue
    finally:
        server.server_close()
    if "code" not in result:
        raise OAuthError("Linear OAuth callback timed out or was rejected")
    return result["code"]


def manual_timeout_supported() -> bool:
    return all(
        hasattr(signal, attribute) for attribute in ("SIGALRM", "ITIMER_REAL", "setitimer")
    )


def login(
    client_id: str | None,
    *,
    manual: bool = False,
    callback_timeout: int = CALLBACK_TIMEOUT_SECONDS,
    http: OAuthHTTP | None = None,
    clock: Callable[[], float] = time.time,
    browser_open: Callable[[str], bool] = webbrowser.open,
    input_fn: Callable[[str], str] = input,
) -> dict[str, Any]:
    if not 30 <= callback_timeout <= 600:
        raise OAuthError("OAuth callback timeout must be between 30 and 600 seconds")
    with login_lock() as store:
        with credential_lock(store):
            existing = load_credentials(store)
        selected_source = (
            client_id
            if client_id is not None
            else existing.get("client_id") or DEFAULT_CLIENT_ID
        )
        selected = _client_id(selected_source)
        state_value = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        _pkce_verifier(verifier)
        url = authorization_url(selected, state_value, verifier)
        if manual:
            print("Open this URL in a browser, authorize Tweed, then paste the full redirected URL:")
            print(url)
            if input_fn is input:
                if not manual_timeout_supported():
                    raise OAuthError(
                        "bounded manual login is unavailable on this platform; use browser callback"
                    )

                def timed_out(_signum: int, _frame: Any) -> None:
                    raise OAuthError("Linear OAuth manual callback timed out")

                previous = signal.signal(signal.SIGALRM, timed_out)
                signal.setitimer(signal.ITIMER_REAL, callback_timeout)
                try:
                    callback = input_fn("Redirected URL: ")
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, previous)
            else:
                callback = input_fn("Redirected URL: ")
            code = parse_callback_url(callback, state_value)
        else:
            print("Opening Linear authorization in your browser...")
            if not browser_open(url):
                print("Open this URL manually:")
                print(url)
            code = _loopback_callback(state_value, callback_timeout)
        credentials = exchange_code(
            http or OAuthHTTP(),
            code=code,
            verifier=verifier,
            client_id=selected,
            now=clock(),
        )
        with credential_lock(store):
            save_credentials(store, credentials)
        return credentials


def status(
    *,
    path: Path | None = None,
    http: OAuthHTTP | None = None,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    with credential_lock(path) as store:
        credentials = load_credentials(store)
    configured = bool(credentials.get("client_id") or DEFAULT_CLIENT_ID)
    logged_in = bool(credentials.get("access_token") and credentials.get("refresh_token"))
    if not configured or not logged_in:
        return {
            "configured": configured,
            "logged_in": False,
            "refresh_required": False,
            "expires_at": None,
            "scopes": [],
            "viewer": None,
        }
    client = http or OAuthHTTP()
    token = access_token(path=path, http=client, clock=clock)
    try:
        viewer = client.graphql_viewer(token)
    except OAuthUnauthorized:
        invalidate_access_token(token, path=path)
        token = access_token(path=path, http=client, clock=clock)
        viewer = client.graphql_viewer(token)
    with credential_lock(path) as store:
        credentials = load_credentials(store)
    expires_at = credentials.get("expires_at")
    scopes = sorted(_scope_set(credentials.get("scopes"))) if logged_in else []
    if logged_in and not isinstance(expires_at, (int, float)):
        raise OAuthError("Linear credential expiry is invalid")
    return {
        "configured": configured,
        "logged_in": logged_in,
        "refresh_required": bool(
            logged_in and isinstance(expires_at, (int, float)) and expires_at <= clock() + REFRESH_SKEW_SECONDS
        ),
        "expires_at": int(expires_at) if isinstance(expires_at, (int, float)) else None,
        "scopes": scopes,
        "viewer": viewer,
    }


def logout(
    *,
    local_only: bool = False,
    http: OAuthHTTP | None = None,
) -> bool:
    # Order logout after any in-flight interactive login so a completed logout
    # cannot be undone by that login installing tokens later.
    with login_lock() as store:
        with credential_lock(store):
            credentials = load_credentials(store)
            if not credentials.get("access_token") and not credentials.get("refresh_token"):
                return True
            confirmed = True
            if not local_only:
                client = http or OAuthHTTP()
                for name in ("refresh_token", "access_token"):
                    token = credentials.get(name)
                    if not token:
                        continue
                    try:
                        code, _payload = client.post_form(
                            REVOKE_PATH,
                            {
                                "token": _token(token, name.replace("_", " ")),
                                "token_type_hint": name,
                            },
                        )
                        if code != 200:
                            confirmed = False
                    except OAuthError:
                        confirmed = False
            clear_tokens(store, credentials)
            return confirmed
