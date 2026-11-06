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
    def test_rejects_cross_session_and_install_controls(self):
        for args in (["kill-all"], ["close-all"], ["install"], ["install-browser"],
                     ["--json", "close-all"], ["-s=x", "open"], ["open", "-sx"],
                     ["open", "-hsx"], ["open", "--session=x"], ["goto", "--s=x"],
                     ["open", "--no-session"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                browser.validate_args(args)

    def test_workflow_capabilities_are_not_blocked(self):
        for args in (["open", "--headed", "--persistent", "https://example.com"],
                     ["open", "--profile", "profile"], ["open", "--config=custom.json"],
                     ["open", "--idle-timeout=0"], ["open", "--browser=chrome"],
                     ["attach", "--cdp=http://localhost:9222"],
                     ["attach", "--extension=chrome"], ["attach", "--endpoint=ws://localhost:3000"],
                     ["detach"], ["show"], ["list"], ["delete-data"],
                     ["webmcp-list"], ["video-start"], ["snapshot", "--future-upstream-option"]):
            browser.validate_args(args)

    def test_supported_commands_and_literal_terminator(self):
        for args in (["open", "http://localhost:8000"], ["snapshot", "--depth=4"],
                     ["fill", "e1", "a b"], ["mousewheel", "0", "-100"],
                     ["screenshot", "--filename=/tmp/image.png"], ["--help"], ["-h"],
                     ["fill", "e1", "--", "-draft"], ["fill", "e1", "--", "--session=x"],
                     ["open", "--", "--headed"], ["paths"], ["close"]):
            browser.validate_args(args)

    def test_relative_config_and_profile_paths(self):
        self.assertEqual(browser.absolute_inputs(["open", "--config=a.json", "--profile", "p"], Path("/tmp/work")),
                         ["open", "--config=/tmp/work/a.json", "--profile", "/tmp/work/p"])
        self.assertEqual(browser.absolute_inputs(["fill", "e1", "--", "--config=a.json"], Path("/tmp/work")),
                         ["fill", "e1", "--", "--config=a.json"])
        self.assertFalse(browser.has_option(["open", "--", "--config=a.json"], "--config"))
        malformed = ["open", "--profile", "--", "--session=literal"]
        self.assertEqual(browser.absolute_inputs(malformed, Path("/tmp/work")), malformed)
        for args in (["open", "--profile="], ["open", "--profile", ""],
                     ["open", "--config="], ["open", "--config", ""]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                browser.absolute_inputs(args, Path("/tmp/work"))

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

    def test_environment_keeps_graphical_routing_but_not_implicit_connections(self):
        result = browser.child_env({"DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-1",
                                   "PLAYWRIGHT_MCP_CDP_ENDPOINT": "evil", "PWTEST_X": "evil",
                                   "XAUTHORITY": "x", "HOME": "/home/test", "PATH": "/bin",
                                   "PROJECT_OBJECT_LAUNCH_ID": "test", "HL_EXEC_RULE_TOKEN": "token"}, Path("/tmp/test"))
        self.assertEqual(result["DISPLAY"], ":1")
        self.assertEqual(result["WAYLAND_DISPLAY"], "wayland-1")
        self.assertEqual(result["PROJECT_OBJECT_LAUNCH_ID"], "test")
        self.assertEqual(result["HL_EXEC_RULE_TOKEN"], "token")
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", result)
        self.assertNotIn("PWTEST_X", result)
        self.assertEqual(result["NO_UPDATE_NOTIFIER"], "1")

    def test_launch_and_returncode(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "XDG_STATE_HOME": temp, "PI_SESSION_ID": "unit-test"}, clear=True), patch.object(
                browser.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as call, patch.object(
                    browser, "runtime_root", return_value=Path(temp) / "runtime" / "test"):
            self.assertEqual(browser.run(["open", "--headed", "--persistent", "http://localhost"],
                                         cli="cli", chromium="chromium"), 7)
            command = call.call_args.args[0]
            self.assertEqual(command[:2], ["cli", "-s=agent"])
            self.assertEqual(command[-4:], ["open", "--headed", "--persistent", "http://localhost"])
            config = json.loads((call.call_args.kwargs["cwd"] / "config.json").read_text())
            self.assertNotIn("isolated", config["browser"])
            self.assertTrue(config["browser"]["launchOptions"]["chromiumSandbox"])
            self.assertNotIn("--idle-timeout=900000", command)
            browser.run(["close"], cli="cli", chromium="chromium")
            self.assertNotIn("--config", " ".join(call.call_args.args[0]))
            browser.run(["open", "--config=/custom/config.json"], cli="cli", chromium="chromium")
            self.assertEqual(sum(arg.startswith("--config=") for arg in call.call_args.args[0]), 1)
            browser.run(["attach", "--cdp=http://localhost:9222"], cli="cli", chromium="chromium")
            self.assertIn("--cdp=http://localhost:9222", call.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
