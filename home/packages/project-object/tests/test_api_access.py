import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from api_access import add_api, available, grant, lookup, open_catalog, store_credential, load_credential
from project_object import RegistryError

loader = importlib.machinery.SourceFileLoader("project_api_test", str(ROOT / "bin/project-api"))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class ApiAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.db = open_catalog(self.root)
        self.addCleanup(self.db.close)
        self.x, self.y, self.z = (str(uuid.uuid4()) for _ in range(3))
        add_api(self.db, "freeagent", "https://api.freeagent.com", "bearer", "https://example.com/docs")

    def test_shared_credential_and_scoped_discovery(self):
        grant(self.db, "freeagent", self.x)
        grant(self.db, "freeagent", self.y)
        self.assertEqual([r[0] for r in available(self.db, self.x)], ["freeagent"])
        self.assertEqual([r[0] for r in available(self.db, self.y)], ["freeagent"])
        with self.assertRaisesRegex(ValueError, "not available"):
            lookup(self.db, self.z, "freeagent")
        self.assertEqual(self.db.execute("SELECT count(*) FROM apis").fetchone()[0], 1)
        grant(self.db, "freeagent", "")
        self.assertEqual([r[0] for r in available(self.db, self.z)], ["freeagent"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM apis").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM access WHERE api_id = 'freeagent'").fetchone()[0], 3)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "apis.sqlite").stat().st_mode & 0o777, 0o600)

    def test_invalid_catalog_and_scopes(self):
        with self.assertRaises(ValueError):
            add_api(self.db, "evil", "http://example.com", "bearer")
        with self.assertRaises(ValueError):
            grant(self.db, "unknown", self.x)
        with self.assertRaises(RegistryError):
            grant(self.db, "freeagent", "../../other")
        with self.assertRaises(ValueError):
            add_api(self.db, "bad", "https://user:pass@example.com", "bearer")
        with self.assertRaises(ValueError):
            add_api(self.db, "bad", "https://example.com", "header", header_name="Authorization")

    def test_request_checks_access_before_keyring_and_never_redirects(self):
        calls = []
        def credential(api_id):
            calls.append(api_id)
            return "private-value"
        with self.assertRaises(ValueError):
            cli.request(self.db, self.y, "freeagent", "GET", "/v2/contacts", credential_loader=credential)
        self.assertEqual(calls, [])
        grant(self.db, "freeagent", self.x)
        for path in ("//evil.com", "https://evil.com", "/../admin", "/x#fragment", "/x\\y"):
            with self.assertRaises(ValueError, msg=path):
                cli.request(self.db, self.x, "freeagent", "GET", path, credential_loader=credential)
        self.assertEqual(calls, [])
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return b'{"ok":true}'
        class Client:
            def open(self, req, timeout):
                self.req = req
                return Response()
        client = Client()
        status, body = cli.request(self.db, self.x, "freeagent", "GET", "/v2/contacts",
                                   credential_loader=credential, opener=client)
        self.assertEqual((status, body), (200, b'{"ok":true}'))
        self.assertEqual(client.req.full_url, "https://api.freeagent.com/v2/contacts")
        self.assertEqual(client.req.get_header("Authorization"), "Bearer private-value")
        self.assertIsNone(cli.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.com"))

    def test_keyring_invocation_never_uses_argv_for_secret(self):
        from subprocess import CompletedProcess
        with patch("api_access.subprocess.run", return_value=CompletedProcess([], 0, "private-value\n")) as run:
            store_credential("freeagent", "private-value")
            self.assertNotIn("private-value", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["input"], "private-value")
            self.assertEqual(load_credential("freeagent"), "private-value")

    def test_catalog_rejects_symlink(self):
        self.db.close()
        (self.root / "apis.sqlite").unlink()
        (self.root / "apis.sqlite").symlink_to(Path(self.temp.name) / "another")
        with self.assertRaises(Exception):
            open_catalog(self.root)


if __name__ == "__main__":
    unittest.main()
