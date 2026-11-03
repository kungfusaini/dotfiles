import io
import http.client
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

import discovery as d


def entry(slug="test-model", **kw):
    return dict(slug=slug, visibility="list", supported_in_api=True,
                supported_reasoning_levels=[{"effort": "medium", "description": "ignored"}],
                instructions="never persist this", **kw)


class DiscoveryTests(unittest.TestCase):
    def test_allowlist_and_hidden_models(self):
        value = entry()
        hidden = entry("hidden")
        hidden["visibility"] = "hide"
        result = d.parse_catalog({"models": [value, hidden], "private": "do not persist"})
        self.assertEqual(result[0], {"id": "hidden", "listed": False, "supportedInApi": True, "thinkingLevels": ["medium"]})
        self.assertNotIn("instructions", json.dumps(result))

    def test_new_reasoning_labels_are_metadata_not_selectable_pi_efforts(self):
        model = entry()
        model["supported_reasoning_levels"].append({"effort": "ultra"})
        self.assertIn("ultra", d.parse_catalog({"models": [model]})[0]["thinkingLevels"])
        model["supported_reasoning_levels"].append({"effort": "bad\x1b[31m"})
        with self.assertRaises(d.CheckError):
            d.parse_catalog({"models": [model]})

    def test_malformed_and_empty_catalogs_fail_closed(self):
        for data in [{}, {"models": []}, {"models": [None]}, {"models": [entry(), entry()]},
                     {"models": [entry("bad\x1b[31m")]}, {"models": [{"slug": "incomplete"}]}]:
            with self.subTest(data=data), self.assertRaises(d.CheckError):
                d.parse_catalog(data)

    def test_collect_preserves_good_catalog_and_atomic_private_state(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state/catalog.json"
            auth = Path(root) / "auth.json"
            models = d.parse_catalog({"models": [entry()]})
            good = d.collect(auth, state, "1.2.3", fetch=lambda *_: models)
            def fail(*_):
                raise d.CheckError("network_error")
            bad = d.collect(auth, state, "1.2.3", fetch=fail)
            self.assertEqual(bad["models"], models)
            self.assertEqual(bad["lastSuccessAt"], good["lastSuccessAt"])
            self.assertEqual(bad["status"], "network_error")
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(list(state.parent.glob(".catalog-*")), [])
            self.assertFalse(auth.exists())

    def test_truncated_http_response_records_failure_preserving_good_catalog(self):
        with tempfile.TemporaryDirectory() as root:
            auth = Path(root) / "auth.json"
            auth.write_text(json.dumps({"openai-codex": {"access": "fake", "accountId": "fake", "expires": 1e15}}))
            state = Path(root) / "state/catalog.json"
            models = d.parse_catalog({"models": [entry()]})
            good = d.collect(auth, state, "1.2.3", fetch=lambda *_: models)
            class Broken(io.BytesIO):
                def read(self, *_):
                    raise http.client.IncompleteRead(b"sensitive-response")
            class Opener:
                def open(self, *_, **__):
                    return Broken()
            with patch.object(d.urllib.request, "build_opener", return_value=Opener()):
                result = d.collect(auth, state, "1.2.3")
            self.assertEqual(result["status"], "network_error")
            self.assertEqual(result["models"], good["models"])
            self.assertEqual(result["lastSuccessAt"], good["lastSuccessAt"])
            self.assertNotIn("sensitive", state.read_text())

    def test_first_failure_and_corrupt_state(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "catalog.json"
            path.write_text("{")
            def fail(*_):
                raise d.CheckError("auth_missing")
            state = d.collect(Path(root) / "absent", path, "1.2.3", fetch=fail)
            self.assertIsNone(state["lastSuccessAt"])
            self.assertEqual(state["models"], [])

    def test_network_contract_auth_unchanged_no_sensitive_payloads(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "auth.json"
            text = json.dumps({"openai-codex": {"access": "fake-access", "accountId": "fake-account",
                                               "refresh": "fake-refresh", "expires": time.time() * 1000 + 60000}})
            path.write_text(text)
            class Opener:
                def open(self, request, timeout):
                    self.request = request
                    self.timeout = timeout
                    return io.BytesIO(json.dumps({"models": [entry()]}).encode())
            opener = Opener()
            result = d.fetch_catalog(path, "1.2.3", opener)
            self.assertEqual(opener.request.get_method(), "GET")
            self.assertEqual(opener.request.full_url, "https://chatgpt.com/backend-api/codex/models?client_version=1.2.3")
            self.assertEqual(opener.request.get_header("Originator"), "codex_cli_rs")
            self.assertEqual(opener.timeout, 20)
            self.assertEqual(path.read_text(), text)
            self.assertNotIn("fake-", json.dumps(result))
            with patch.object(time, "time", return_value=time.time() + 1000):
                with self.assertRaisesRegex(d.CheckError, "auth_expired"):
                    d.fetch_catalog(path, "1.2.3", opener)

    def test_http_and_size_errors_are_sanitized(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "auth.json"
            path.write_text(json.dumps({"openai-codex": {"access": "fake", "accountId": "fake", "expires": 1e15}}))
            class Opener:
                def open(self, *_, **__):
                    raise urllib.error.HTTPError("sensitive-url", 401, "sensitive-body", {}, None)
            with self.assertRaisesRegex(d.CheckError, "^auth_expired$"):
                d.fetch_catalog(path, "1.2.3", Opener())
            class Large:
                def open(self, *_, **__):
                    return io.BytesIO(b"x" * (d.LIMIT + 1))
            with self.assertRaisesRegex(d.CheckError, "^response_too_large$"):
                d.fetch_catalog(path, "1.2.3", Large())
            self.assertIsNone(d.NoRedirect().redirect_request(None, None, None, None, None, None))


if __name__ == "__main__":
    unittest.main()
