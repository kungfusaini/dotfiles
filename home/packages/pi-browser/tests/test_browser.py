import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("browser", Path(__file__).resolve().parents[1] / "browser.py")
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class BrowserTests(unittest.TestCase):
    def test_rejects_launch_and_global_controls(self):
        for args in (["attach"], ["show"], ["kill-all"], ["close-all"], ["install"],
                     ["-s=x", "open"], ["open", "--headed"], ["open", "--headed=false"],
                     ["open", "--config=evil"], ["open", "--profile", "/home"],
                     ["open", "--persistent"], ["open", "--cdp=x"],
                     ["open", "--browser=chrome"], ["open", "--session=x"],
                     ["open", "--endpoint=x"], ["open", "--extension"],
                     ["goto", "--s=x"], ["open", "--__proto__.headed=true"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                browser.validate_args(args)

    def test_supported_commands(self):
        for args in (["open", "http://localhost:8000"], ["snapshot", "--depth=4"],
                     ["fill", "e1", "a b"], ["mousewheel", "0", "-100"],
                     ["screenshot", "--filename=/tmp/image.png"], ["--help"],
                     ["fill", "e1", "--", "-draft"], ["fill", "e1", "--", "--help"],
                     ["open", "--", "--headed"],
                     ["paths"], ["eval", "document.title"], ["close"]):
            browser.validate_args(args)

    def test_session_required(self):
        with self.assertRaises(ValueError):
            browser.session_root({})

    def test_identity_and_private_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {"XDG_STATE_HOME": temp, "PI_SESSION_ID": "../../agent-a"}
            first = browser.session_root(env)
            self.assertEqual(first, browser.session_root(env))
            self.assertNotEqual(first, browser.session_root({**env, "PI_SESSION_ID": "agent-b"}))
            self.assertEqual(first.parent, Path(temp) / "pi-browser")
            self.assertEqual(first.stat().st_mode & 0o777, 0o700)

    def test_session_file_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(browser.session_root({"XDG_STATE_HOME": temp, "PI_SESSION_FILE": "/tmp/a"}).is_dir())

    def test_reject_symlink_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError):
                browser.private_dir(root / "link")

    def test_environment(self):
        result = browser.child_env({"DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-1",
                                   "PLAYWRIGHT_MCP_CDP_ENDPOINT": "evil", "PWTEST_X": "evil",
                                   "XAUTHORITY": "x", "HOME": "/home/test", "PATH": "/bin"}, Path("/tmp/test"))
        self.assertNotIn("DISPLAY", result)
        self.assertNotIn("WAYLAND_DISPLAY", result)
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", result)
        self.assertNotIn("PWTEST_X", result)
        self.assertEqual(result["HOME"], "/home/test")
        self.assertEqual(result["NO_UPDATE_NOTIFIER"], "1")

    def test_launch_and_returncode(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "XDG_STATE_HOME": temp, "PI_SESSION_ID": "unit-test"}, clear=True), patch.object(
                browser.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as call, patch.object(
                    browser, "runtime_root", return_value=Path(temp) / "runtime" / "test"):
            self.assertEqual(browser.run(["open", "http://localhost"], cli="cli", chromium="chromium"), 7)
            args, kwargs = call.call_args
            command = args[0]
            self.assertEqual(command[:2], ["cli", "-s=agent"])
            self.assertEqual(command[-2:], ["open", "http://localhost"])
            config = json.loads((kwargs["cwd"] / "config.json").read_text())
            self.assertTrue(config["browser"]["isolated"])
            self.assertTrue(config["browser"]["launchOptions"]["headless"])
            self.assertTrue(config["browser"]["launchOptions"]["chromiumSandbox"])
            self.assertIn("--idle-timeout=900000", command)
            browser.run(["close"], cli="cli", chromium="chromium")
            self.assertNotIn("--config", " ".join(call.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()
