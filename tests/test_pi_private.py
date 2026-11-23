"""Pure policy tests; optional packaged sandbox/inference tests with --package PATH."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


chat = load("private_chat", ROOT / "home/packages/pi-private/chat.py")
launcher = load("private_launcher", ROOT / "home/packages/pi-private/launcher.py")
PACKAGE = None
if "--package" in sys.argv:
    index = sys.argv.index("--package")
    PACKAGE = Path(sys.argv[index + 1])
    del sys.argv[index:index + 2]


class Policy(unittest.TestCase):
    def test_commands_fail_closed(self):
        for value in ["/share", "/export /tmp/leak", "/model", "!curl example.org", "@/etc/passwd", "/resume ../x", "/resume -1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                chat.action(value)
        self.assertEqual(chat.action("hello @someone"), ("prompt", "hello @someone"))
        self.assertEqual(chat.action("/resume 2"), ("resume", 2))

    def test_no_terminal_control_sequences(self):
        self.assertEqual(chat.plain("hi\x1b]52;c;abc\x07\u202e"), "hi]52;c;abc")
        self.assertEqual(chat.plain("line\n\ttext"), "line\n\ttext")

    def test_rpc_tool_and_resource_options(self):
        argv = chat.pi_command("/pi")
        for option in ["--offline", "--no-tools", "--no-extensions", "--no-skills", "--no-context-files", "--no-approve"]:
            self.assertIn(option, argv)
        self.assertNotIn("bash", chat.ALLOWED_RPC)
        self.assertNotIn("export_html", chat.ALLOWED_RPC)
        self.assertNotIn("set_model", chat.ALLOWED_RPC)

    def test_sandbox_has_no_host_mount_or_env_inheritance(self):
        argv = launcher.sandbox_command(Path("/private-history"), Path("/weights"))
        for option in ["--unshare-all", "--unshare-user", "--disable-userns", "--clearenv", "--new-session"]:
            self.assertIn(option, argv)
        self.assertNotIn("--share-net", argv)
        self.assertNotIn("/run/user", argv)
        self.assertNotIn(str(Path.home()), argv)

    def test_symlink_storage_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target").mkdir()
            (root / "link").symlink_to(root / "target")
            with self.assertRaises(RuntimeError):
                launcher.private_directory(root / "link")

    def test_history_excludes_symlinks(self):
        old = chat.HISTORY
        with tempfile.TemporaryDirectory() as tmp:
            chat.HISTORY = Path(tmp)
            try:
                (chat.HISTORY / "real.jsonl").write_text("{}")
                (chat.HISTORY / "link.jsonl").symlink_to(chat.HISTORY / "real.jsonl")
                self.assertEqual([p.name for p in chat.session_files()], ["real.jsonl"])
            finally:
                chat.HISTORY = old


@unittest.skipUnless(PACKAGE, "pass --package to test the built sandbox")
class Packaged(unittest.TestCase):
    def test_real_isolation_and_persistence(self):
        built = load("built_private_launcher", PACKAGE / "bin/pi-private")
        with tempfile.TemporaryDirectory(prefix="pi-private-test-") as tmp:
            history = Path(tmp) / "sessions"
            history.mkdir(mode=0o700)
            # Validate kernel isolation, not just command-line strings.
            result = subprocess.run(built.sandbox_command(history, None, True),
                                    capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "OPENAI_API_KEY": "synthetic-must-not-inherit"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS:", result.stdout)
            self.assertNotIn("Network namespace: " + os.readlink("/proc/self/ns/net"), result.stdout)
            model = Path.home() / built.MODEL_RELATIVE
            command = built.sandbox_command(history, model)
            first = subprocess.run(command, input="Reply with exactly LOCAL_TEST_OK.\n/exit\n",
                                   capture_output=True, text=True, timeout=300)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("PRIVATE · LOCAL ONLY", first.stdout)
            files = list(history.glob("*.jsonl"))
            self.assertEqual(len(files), 1, first.stdout + first.stderr)
            records = [json.loads(line) for line in files[0].read_text().splitlines()]
            messages = [r["message"] for r in records if r.get("type") == "message"]
            self.assertTrue(any(m.get("role") == "user" for m in messages))
            self.assertTrue(any(m.get("role") == "assistant" and m.get("stopReason") != "error" for m in messages), first.stdout)
            self.assertEqual(files[0].stat().st_mode & 0o077, 0)
            second = subprocess.run(command, input="/history\n/resume 1\n/exit\n",
                                    capture_output=True, text=True, timeout=240)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("Reply with exactly LOCAL_TEST_OK.", second.stdout)
            self.assertEqual(len(list(history.glob("*.jsonl"))), 1)


if __name__ == "__main__":
    unittest.main()
