import importlib.util
import io
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

    def test_open_url_parsing_matches_native_options(self):
        self.assertEqual(browser.open_target(["open", "--headed", "--device", "Pixel 10", "data:text/html,fixture"]),
                         "data:text/html,fixture")
        self.assertEqual(browser.open_target(["open", "--profile=p", "file:///tmp/fixture.html"]),
                         "file:///tmp/fixture.html")
        self.assertEqual(browser.open_target(["open", "--headed", "false", "--", "example.com"]), "example.com")
        for args in (["open", "--headed=true"], ["open", "--persistent=false"],
                     ["open", "--device"], ["open", "--unknown"], ["open", "a", "b"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                browser.open_target(args)

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
        self.assertEqual(result["VIVALDI_FFMPEG_AUTO"], "0")

    def test_vivaldi_mode_compatibility(self):
        headless = browser.launch_options("vivaldi", ["open"])
        self.assertTrue(headless["headless"])
        self.assertIn("--disable-vivaldi", headless["args"])
        headed = browser.launch_options("vivaldi", ["open", "--headed"])
        self.assertFalse(headed["headless"])
        self.assertNotIn("args", headed)
        self.assertNotIn("--disable-vivaldi", headed.get("args", []))
        for args in (["open", "--headed", "false"], ["open", "--headed", "--no-headed"],
                     ["fill", "e1", "--", "--headed"]):
            self.assertFalse(browser.headed_requested(args))

    def test_temporary_cleanup_never_deletes_external_or_detached_profiles(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(browser, "runtime_root", return_value=Path(temp) / "runtime"):
            root = Path(temp)
            profile = root / "runtime" / "headed-owned"
            profile.mkdir(parents=True)
            state = {"pid": 123, "start": "original", "profile": str(profile), "temporary": True, "bound": True}
            (root / "vivaldi-process.json").write_text(json.dumps(state))
            with patch.object(browser, "process_start", return_value="reused"), patch.object(browser.os, "kill") as kill:
                browser.stop_managed(root)
                kill.assert_not_called()
            self.assertFalse(profile.exists())
            profile.mkdir()
            for changes in ({"bound": False}, {"temporary": False}):
                (root / "vivaldi-process.json").write_text(json.dumps({**state, **changes}))
                with patch.object(browser, "process_start", return_value=None):
                    browser.stop_managed(root)
                self.assertTrue(profile.exists())

    def test_profile_lock_checks_live_and_foreign_owners(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock = root / "SingletonLock"
            lock.symlink_to(os.uname().nodename + "-123")
            with patch.object(browser, "process_start", return_value="live"):
                self.assertTrue(browser.profile_locked(root))
            with patch.object(browser, "process_start", return_value=None):
                self.assertFalse(browser.profile_locked(root))
            lock.unlink()
            lock.symlink_to("another-host-123")
            with patch.object(browser, "process_start", return_value=None):
                self.assertTrue(browser.profile_locked(root))

    def test_native_profile_resolution_endpoint_and_owned_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            runtime.mkdir()
            process = unittest.mock.Mock(pid=123)
            process.poll.return_value = None
            def spawn(command, **_kwargs):
                profile = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--user-data-dir=")))
                self.assertEqual(profile, root / "relative-profile")
                self.assertEqual(command[-1], "about:blank")
                self.assertNotIn("data:text/html,<title>fixture</title>", command)
                (profile / "DevToolsActivePort").write_text("45678\n/devtools/browser/owned-id\n")
                return process
            opener = unittest.mock.Mock()
            opener.open.side_effect = [io.StringIO('{"id":"owned-target"}'),
                                       io.StringIO('[{"id":"owned-target","title":"fixture"}]'), io.StringIO('activated')]
            config = {"browser": {"userDataDir": "relative-profile", "launchOptions": {"executablePath": "vivaldi"}}}
            with patch.object(browser.subprocess, "Popen", side_effect=spawn), \
                    patch.object(browser, "process_start", return_value="start"), \
                    patch.object(browser.urllib.request, "build_opener", return_value=opener), \
                    patch.object(browser, "runtime_root", return_value=runtime):
                actual, target = browser.start_headed(root, config, ["open", "--headed", "data:text/html,<title>fixture</title>"], {})
            self.assertIs(actual, process)
            self.assertEqual(target, "owned-target")
            self.assertEqual(config["browser"]["cdpEndpoint"], "http://127.0.0.1:45678")
            state = json.loads((root / "vivaldi-process.json").read_text())
            self.assertFalse(state["temporary"])
            self.assertEqual(state["websocketPath"], "/devtools/browser/owned-id")

    def test_failed_native_launch_removes_only_its_temporary_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            runtime.mkdir()
            with patch.object(browser, "runtime_root", return_value=runtime), \
                    patch.object(browser.subprocess, "Popen", side_effect=OSError("fixture failure")):
                with self.assertRaises(OSError):
                    browser.start_headed(root, {"browser": {"launchOptions": {"executablePath": "vivaldi"}}},
                                         ["open", "--headed"], {})
            self.assertEqual(list(runtime.iterdir()), [])

    def test_native_file_url_uses_upstream_file_permission(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(browser.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError):
                browser.start_headed(Path(temp), {"browser": {"launchOptions": {"executablePath": "vivaldi"}}},
                                     ["open", "--headed", "file:///private/fixture"], {})
            spawn.assert_not_called()

    def test_native_rejects_unapplied_context_and_init_callbacks(self):
        base = {"launchOptions": {"executablePath": "vivaldi"}}
        for settings, args in (({**base, "contextOptions": {"locale": "fr-FR"}}, ["open", "--headed"]),
                               ({**base, "initPage": ["callback.js"]}, ["open", "--headed"]),
                               ({**base, "initScript": ["callback.js"]}, ["open", "--headed"]),
                               (base, ["open", "--headed", "--device=Pixel 10"]),
                               (base, ["open", "--headed", "--mobile"])):
            with self.subTest(settings=settings, args=args), self.assertRaises(ValueError):
                browser.validate_native_settings({"browser": settings}, args)

    def test_native_internal_selection_does_not_emit_extra_json(self):
        output = io.StringIO()
        ready = io.StringIO("Daemon listening on owned.sock\n")
        daemon = unittest.mock.Mock(stdout=ready)
        results = [subprocess.CompletedProcess([], 0, '{"result":"1"}', ""),
                   subprocess.CompletedProcess([], 0, '{"result":"internal-selection"}', ""),
                   subprocess.CompletedProcess([], 0)]
        with tempfile.TemporaryDirectory() as temp, patch.object(browser.subprocess, "Popen", return_value=daemon), \
                patch.object(browser.select, "select", return_value=([ready], [], [])), \
                patch.object(browser.subprocess, "run", side_effect=results) as run, patch("sys.stdout", output):
            result = browser.connect_headed("cli", Path(temp), Path(temp) / "config.json",
                                            ["open", "--headed", "--json", "https://example.com"], {}, "owned-id")
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(run.call_args_list[1].kwargs["capture_output"])
        self.assertNotIn("capture_output", run.call_args_list[2].kwargs)
        self.assertIn("goto", run.call_args_list[2].args[0])

    def test_placement_rule_is_exact_and_disabled_before_configuration(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(browser.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 0, "ok\n", "")) as call:
            root = Path(temp)
            context = {"PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME": "Agent · Target", "PROJECT_OBJECT_LAUNCH_ID": "a" * 32}
            state = browser.placement_rule(root, context)
            commands = [item.args[0] for item in call.call_args_list]
            self.assertEqual(commands[0][-2:], [state["rule"] + ":enable", "0"])
            self.assertIn(["@HYPRCTL@", "keyword", state["rule"] + ":match:class", "^pi-vivaldi-" + "a" * 32 + "$"], commands)
            self.assertEqual(commands[-1][-2:], [state["rule"] + ":enable", "1"])
            for bad in ({**context, "PROJECT_OBJECT_LAUNCH_ID": "bad"},
                        {**context, "PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME": "unsafe;workspace"}):
                with self.assertRaises(ValueError):
                    browser.placement_rule(root, bad)

    def test_explicit_ini_is_never_replaced_and_malformed_json_never_launches(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                "XDG_STATE_HOME": temp, "PI_SESSION_ID": "config-regression"}, clear=True), \
                patch.object(browser, "runtime_root", return_value=Path(temp) / "runtime" / "test"), \
                patch.object(browser.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                patch.object(browser, "start_headed") as native:
            config = Path(temp) / "explicit.ini"
            config.write_text("cdp-endpoint=http://127.0.0.1:9222\n")
            browser.run(["open", "--headed", "--config=" + str(config)], cli="cli", browser_executable="vivaldi")
            native.assert_not_called()
            self.assertEqual(sum(arg.startswith("--config=") for arg in run.call_args.args[0]), 1)
            self.assertIn("--config=" + str(config), run.call_args.args[0])
            run.reset_mock()
            config.write_text('{"browser": broken')
            with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                browser.run(["open", "--headed", "--config=" + str(config)], cli="cli", browser_executable="vivaldi")
            run.assert_not_called()
            native.assert_not_called()

    def test_launch_and_returncode(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "XDG_STATE_HOME": temp, "PI_SESSION_ID": "unit-test"}, clear=True), patch.object(
                browser.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as call, patch.object(
                    browser, "runtime_root", return_value=Path(temp) / "runtime" / "test"), patch.object(
                        browser, "start_headed", return_value=None):
            self.assertEqual(browser.run(["open", "--headed", "--persistent", "http://localhost", "--help"],
                                         cli="cli", browser_executable="/nix/store/test-vivaldi/bin/vivaldi"), 7)
            command = call.call_args.args[0]
            self.assertEqual(command[:2], ["cli", "-s=agent"])
            self.assertEqual(command[-5:], ["open", "--headed", "--persistent", "http://localhost", "--help"])
            config = json.loads((call.call_args.kwargs["cwd"] / "config.json").read_text())
            self.assertNotIn("isolated", config["browser"])
            self.assertTrue(config["browser"]["launchOptions"]["chromiumSandbox"])
            self.assertEqual(config["browser"]["launchOptions"]["executablePath"],
                             "/nix/store/test-vivaldi/bin/vivaldi")
            self.assertNotIn("--idle-timeout=900000", command)
            browser.run(["close"], cli="cli", browser_executable="vivaldi")
            self.assertNotIn("--config", " ".join(call.call_args.args[0]))
            custom = Path(temp) / "custom.json"
            custom.write_text(json.dumps({"browser": {"launchOptions": {"executablePath": "custom"}}}))
            browser.run(["open", "--config=" + str(custom)], cli="cli", browser_executable="vivaldi")
            self.assertEqual(sum(arg.startswith("--config=") for arg in call.call_args.args[0]), 1)
            browser.run(["attach", "--cdp=http://localhost:9222"], cli="cli", browser_executable="vivaldi")
            self.assertIn("--cdp=http://localhost:9222", call.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
