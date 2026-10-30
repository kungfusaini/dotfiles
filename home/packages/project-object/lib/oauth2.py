"""Reusable OAuth 2.0 authorization-code connector for confidential and PKCE clients.

Provider-specific settings (URLs, scopes, client authentication) are data, not code.
Secrets are stored in Secret Service; API availability stays in the shared catalog.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import webbrowser

from api_access import add_api, load_credential, store_credential, validate_api_id, validate_base_url


@dataclass(frozen=True)
class OAuthConfig:
    authorization_url: str
    token_url: str
    client_auth: str = "basic"  # basic, post, or none (public PKCE client)
    scope: str = ""
    pkce: bool = False

    def validate(self):
        for url in (self.authorization_url, self.token_url):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError("OAuth endpoints must be HTTPS URLs without userinfo or fragments")
        if self.client_auth not in ("basic", "post", "none") or (self.client_auth == "none" and not self.pkce):
            raise ValueError("Public clients must use PKCE; client authentication must be basic, post or none")
        if any(ord(c) < 32 or ord(c) == 127 for c in self.scope):
            raise ValueError("Invalid OAuth scope")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def oauth_key(api_id: str, part: str) -> str:
    validate_api_id(api_id)
    return f"{api_id}-{part}"


def ensure_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS oauth_connections (api_id TEXT PRIMARY KEY REFERENCES apis(id), client_id TEXT NOT NULL, config TEXT NOT NULL)")


def configure(db, api_id: str, base_url: str, docs_url: str, client_id: str, config: OAuthConfig) -> None:
    validate_api_id(api_id)
    base_url = validate_base_url(base_url)
    config.validate()
    if not client_id or len(client_id) > 256 or any(c.isspace() for c in client_id):
        raise ValueError("Invalid OAuth client ID")
    with db:
        current = db.execute("SELECT base_url, auth_type FROM apis WHERE id = ?", (api_id,)).fetchone()
        if current is None:
            add_api(db, api_id, base_url, "bearer", docs_url)
        elif current != (base_url, "bearer"):
            raise ValueError("Existing API must have matching base URL and bearer authentication")
        ensure_table(db)
        db.execute("INSERT INTO oauth_connections VALUES (?, ?, ?) ON CONFLICT(api_id) DO UPDATE SET client_id=excluded.client_id, config=excluded.config",
                   (api_id, client_id, json.dumps(asdict(config))))


def is_configured(db, api_id: str) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oauth_connections'").fetchone()
                and db.execute("SELECT 1 FROM oauth_connections WHERE api_id = ?", (api_id,)).fetchone())


def token_request(config: OAuthConfig, client_id: str, client_secret: str, fields: dict, *, opener=None) -> dict:
    config.validate()
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    fields = dict(fields)
    if config.client_auth == "basic":
        headers["Authorization"] = "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    else:
        fields["client_id"] = client_id
        if config.client_auth == "post":
            fields["client_secret"] = client_secret
    req = Request(config.token_url, data=urlencode(fields).encode("ascii"), headers=headers, method="POST")
    client = opener or build_opener(NoRedirect())
    try:
        with client.open(req, timeout=20) as response:
            raw = response.read(16385)
    except Exception:
        # Never echo token endpoint response bodies or secret-bearing request details.
        raise ValueError("OAuth token exchange failed; check credentials and authorization") from None
    if len(raw) > 16384:
        raise ValueError("OAuth token response is too large")
    try:
        token = json.loads(raw)
        if not isinstance(token, dict) or str(token.get("token_type", "Bearer")).lower() != "bearer":
            raise ValueError("Invalid OAuth token type")
        if not isinstance(token.get("access_token"), str) or not token["access_token"]:
            raise ValueError("OAuth response missing access token")
        # A refresh response may omit refresh_token; caller retains the prior one.
        refresh = token.get("refresh_token")
        if refresh is not None and (not isinstance(refresh, str) or not refresh):
            raise ValueError("Invalid OAuth refresh token")
        expiry = int(token["expires_in"])
        if not 0 < expiry <= 86400 * 365:
            raise ValueError("Invalid OAuth token lifetime")
        return {"access_token": token["access_token"], "refresh_token": refresh,
                "expires_at": int(time.time()) + expiry}
    except (KeyError, TypeError, OverflowError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid OAuth token response") from None


def callback_parts(uri: str) -> tuple[str, int, str]:
    parsed = urlsplit(uri)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or not parsed.port or parsed.query or parsed.fragment
            or not parsed.path.startswith("/") or parsed.path.startswith("//")):
        raise ValueError("Redirect URI must be a registered http://127.0.0.1:<port>/<path> callback")
    return parsed.hostname, parsed.port, parsed.path


def authorization_code(config: OAuthConfig, client_id: str, redirect_uri: str, *,
                       open_browser=webbrowser.open, timeout=180) -> tuple[str, str | None]:
    config.validate()
    host, port, path = callback_parts(redirect_uri)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64) if config.pkce else None
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query, keep_blank_values=True)
            if parsed.path != path or params.get("state") != [state]:
                self.send_error(400, "Invalid OAuth callback")
                return
            result["code"] = params.get("code", [""])[0]
            result["error"] = params.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorization received. You can close this tab.")

        def log_message(self, *_args):
            pass  # Callback query strings contain authorization codes.

    params = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri, "state": state}
    if config.scope:
        params["scope"] = config.scope
    if verifier:
        params["code_challenge"] = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params["code_challenge_method"] = "S256"
    with HTTPServer((host, port), Callback) as server:
        server.timeout = 1
        separator = "&" if urlsplit(config.authorization_url).query else "?"
        print("Opening authorization in your browser. Waiting up to three minutes for the callback...")
        open_browser(config.authorization_url + separator + urlencode(params))
        deadline = time.monotonic() + timeout
        while "code" not in result and "error" not in result and time.monotonic() < deadline:
            server.handle_request()
    if result.get("error"):
        raise ValueError("OAuth authorization was denied")
    if not result.get("code"):
        raise ValueError("No authorization code received before timeout")
    return result["code"], verifier


@contextmanager
def refresh_lock(data_root: Path):
    path = data_root / "oauth-refresh.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def login(db, api_id: str, base_url: str, docs_url: str, client_id: str, client_secret: str,
          redirect_uri: str, config: OAuthConfig, *, authorize=authorization_code,
          exchange=token_request, store=store_credential) -> None:
    validate_api_id(api_id)
    validate_base_url(base_url)
    callback_parts(redirect_uri)
    config.validate()
    if config.client_auth != "none" and not client_secret:
        raise ValueError("OAuth app client secret is required")
    existing = db.execute("SELECT base_url, auth_type FROM apis WHERE id = ?", (api_id,)).fetchone()
    if existing and existing != (base_url, "bearer"):
        raise ValueError("Conflicting existing API definition")
    code, verifier = authorize(config, client_id, redirect_uri)
    fields = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    if verifier:
        fields["code_verifier"] = verifier
    token = exchange(config, client_id, client_secret, fields)
    if not token.get("refresh_token"):
        raise ValueError("Provider did not issue a refresh token; this connector requires refresh support")
    if config.client_auth != "none":
        store(oauth_key(api_id, "client-secret"), client_secret)
    store(api_id, json.dumps(token, separators=(",", ":")))
    configure(db, api_id, base_url, docs_url, client_id, config)


def access_token(db, data_root: Path, api_id: str, *, load=load_credential, store=store_credential,
                 exchange=token_request) -> str:
    with refresh_lock(data_root):
        row = db.execute("SELECT client_id, config FROM oauth_connections WHERE api_id = ?", (api_id,)).fetchone()
        if row is None:
            raise ValueError("OAuth connection not configured")
        client_id, config_json = row
        config = OAuthConfig(**json.loads(config_json))
        try:
            token = json.loads(load(api_id))
            if (not isinstance(token, dict) or not isinstance(token.get("access_token"), str)
                    or not isinstance(token.get("refresh_token"), str) or not token["refresh_token"]):
                raise ValueError("Malformed OAuth token in keyring")
            if int(token["expires_at"]) > time.time() + 60:
                return token["access_token"]
        except (json.JSONDecodeError, KeyError, TypeError, OverflowError):
            raise ValueError("Malformed OAuth credentials in keyring") from None
        secret = load(oauth_key(api_id, "client-secret")) if config.client_auth != "none" else ""
        new_token = exchange(config, client_id, secret,
                             {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
        new_token["refresh_token"] = new_token.get("refresh_token") or token["refresh_token"]
        store(api_id, json.dumps(new_token, separators=(",", ":")))
        return new_token["access_token"]
