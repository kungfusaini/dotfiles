import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen
from threading import Thread
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from api_access import available, grant, open_catalog
from freeagent_oauth import PRODUCTION, DOCS, settings, migrate_legacy
from oauth2 import (OAuthConfig, access_token, authorization_code, callback_parts, configure,
                    is_configured, login, token_request)


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = open_catalog(self.root)
        self.addCleanup(self.db.close)

    def test_login_keeps_tokens_in_keyring_and_reuses_connection(self):
        stored = {}
        def save(key, value): stored[key] = value
        token = {"access_token": "access", "refresh_token": "refresh", "expires_at": int(time.time()) + 3600}
        login(self.db, "freeagent", PRODUCTION, DOCS, "public-client", "private-secret",
              "http://127.0.0.1:8765/callback", settings(PRODUCTION),
              authorize=lambda *_: ("code", None), exchange=lambda *args: token, store=save)
        self.assertTrue(is_configured(self.db, "freeagent"))
        self.assertEqual(stored["freeagent-client-secret"], "private-secret")
        self.assertEqual(json.loads(stored["freeagent"]), token)
        raw = (self.root / "apis.sqlite").read_bytes().decode("latin1")
        self.assertNotIn("private-secret", raw)
        self.assertNotIn("refresh", raw)
        x, y = str(uuid.uuid4()), str(uuid.uuid4())
        grant(self.db, "freeagent", x)
        grant(self.db, "freeagent", y)
        self.assertEqual(len(available(self.db, x)), 1)
        self.assertEqual(len(available(self.db, y)), 1)
        self.assertEqual(access_token(self.db, self.root, "freeagent", load=stored.__getitem__, store=save), "access")

    def test_refresh_rotates_or_retains_refresh_token(self):
        configure(self.db, "freeagent", PRODUCTION, DOCS, "client-id", settings(PRODUCTION))
        stored = {"freeagent-client-secret": "secret", "freeagent": json.dumps({
            "access_token": "old", "refresh_token": "old-refresh", "expires_at": 1})}
        calls = []
        def refresh(config, cid, secret, fields):
            calls.append((config.token_url, cid, secret, fields))
            return {"access_token": "new", "refresh_token": None, "expires_at": int(time.time()) + 3600}
        def save(key, value): stored[key] = value
        self.assertEqual(access_token(self.db, self.root, "freeagent", load=stored.__getitem__, store=save,
                                      exchange=refresh), "new")
        self.assertEqual(calls, [(PRODUCTION + "/v2/token_endpoint", "client-id", "secret",
                                  {"grant_type": "refresh_token", "refresh_token": "old-refresh"})])
        self.assertEqual(json.loads(stored["freeagent"])["refresh_token"], "old-refresh")
        access_token(self.db, self.root, "freeagent", load=stored.__getitem__, store=save, exchange=refresh)
        self.assertEqual(len(calls), 1)

    def test_token_exchange_uses_basic_auth_and_form_not_query(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n):
                return b'{"access_token":"a","refresh_token":"r","expires_in":3600,"token_type":"bearer"}'
        class Client:
            def open(self, req, timeout):
                self.req = req
                return Response()
        client = Client()
        result = token_request(settings(PRODUCTION), "client", "private",
                               {"grant_type": "refresh_token", "refresh_token": "old"}, opener=client)
        self.assertEqual(result["access_token"], "a")
        self.assertEqual(client.req.full_url, PRODUCTION + "/v2/token_endpoint")
        self.assertIn("Basic ", client.req.get_header("Authorization"))
        self.assertIn(b"refresh_token=old", client.req.data)

    def test_generic_provider_supports_pkce_public_client(self):
        config = OAuthConfig("https://id.example.com/authorize", "https://id.example.com/token",
                             "none", "read data", True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        errors = []
        def browser(url):
            def send():
                try:
                    qs = parse_qs(urlsplit(url).query)
                    self.assertEqual(qs["scope"], ["read data"])
                    self.assertEqual(qs["code_challenge_method"], ["S256"])
                    callback = qs["redirect_uri"][0]
                    with self.assertRaises(HTTPError):
                        urlopen(callback + "?state=wrong&code=bad", timeout=2)
                    with urlopen(callback + "?state=" + qs["state"][0] + "&code=good", timeout=2):
                        pass
                except Exception as error:
                    errors.append(error)
            Thread(target=send, daemon=True).start()
        code, verifier = authorization_code(config, "client", f"http://127.0.0.1:{port}/callback",
                                            open_browser=browser, timeout=3)
        self.assertEqual(code, "good")
        self.assertTrue(verifier)
        self.assertEqual(errors, [])
        self.assertTrue(config.pkce)
        for uri in ("https://example.com/cb", "http://evil.com:1234/cb", "http://127.0.0.1:1234/cb?x=1"):
            with self.assertRaises(ValueError):
                callback_parts(uri)
        class Client:
            def open(self, req, timeout):
                self.req = req
                class Response:
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def read(self, n): return b'{"access_token":"a","refresh_token":"r","expires_in":120}'
                return Response()
        client = Client()
        token_request(config, "client", "", {"grant_type": "authorization_code", "code": code,
                                              "code_verifier": verifier}, opener=client)
        self.assertIsNone(client.req.get_header("Authorization"))
        self.assertIn(b"client_id=client", client.req.data)
        self.assertIn(b"code_verifier=", client.req.data)

    def test_generic_provider_login_and_refresh(self):
        config = OAuthConfig("https://accounts.example.com/authorize", "https://accounts.example.com/token",
                             "post", "files.read", True)
        saved = {}
        calls = []
        def exchange(settings, client_id, client_secret, fields):
            calls.append((settings, client_id, client_secret, fields))
            return {"access_token": "new", "refresh_token": "refresh", "expires_at": int(time.time()) + 1200}
        login(self.db, "files", "https://api.example.com", "https://example.com/docs", "public-id", "private",
              "http://127.0.0.1:8765/callback", config,
              authorize=lambda *_: ("auth-code", "verifier"), exchange=exchange,
              store=lambda key, value: saved.__setitem__(key, value))
        self.assertEqual(calls[0][3]["code_verifier"], "verifier")
        self.assertEqual(calls[0][3]["code"], "auth-code")
        self.assertEqual(access_token(self.db, self.root, "files", load=saved.__getitem__), "new")
        self.assertTrue(is_configured(self.db, "files"))

    def test_migrate_initial_freeagent_connection(self):
        with self.db:
            self.db.execute("INSERT INTO apis VALUES (?, ?, ?, ?, ?)", ("freeagent", PRODUCTION, DOCS, "bearer", ""))
            self.db.execute("CREATE TABLE freeagent_oauth (api_id TEXT PRIMARY KEY, client_id TEXT NOT NULL)")
            self.db.execute("INSERT INTO freeagent_oauth VALUES (?, ?)", ("freeagent", "client"))
        migrate_legacy(self.db)
        self.assertTrue(is_configured(self.db, "freeagent"))
        self.assertEqual(self.db.execute("SELECT client_id FROM oauth_connections").fetchone(), ("client",))
        migrate_legacy(self.db)


if __name__ == "__main__":
    unittest.main()
