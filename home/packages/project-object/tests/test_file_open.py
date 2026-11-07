import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "bin/project-file-open"
loader = importlib.machinery.SourceFileLoader("file_open", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
opener = importlib.util.module_from_spec(spec)
loader.exec_module(opener)


class FileOpenTests(unittest.TestCase):
    def test_local_paths_unicode_spaces_hash_and_percent(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "photo é #100% ; $(echo nope).html"
            path.touch()
            self.assertEqual(opener.local_file(path.as_uri() + "#section"), (path, "section"))
            self.assertEqual(opener.local_file(path.as_uri().replace("file:///", "file://localhost/"))[0], path)
            self.assertEqual(opener.local_file(Path(root).as_uri())[0], Path(root))

    def test_reject_unsafe_urls(self):
        for value in ("https://example.com", "file://server/etc/passwd", "file:relative",
                      "file:///tmp/%00", "file:///tmp/%0a", "file:///tmp/line\n",
                      "file:///tmp/%xx", "file:///tmp/test?x=1", "/etc/passwd"):
            with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                opener.local_file(value)

    def test_missing_and_special_files(self):
        with self.assertRaises(FileNotFoundError):
            opener.local_file("file:///nonexistent-file-open-test")
        with self.assertRaises(ValueError):
            opener.local_file("file:///dev/null")

    def test_reject_redirected_runtime_directory(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"XDG_RUNTIME_DIR": root}):
            target = Path(root) / "target"
            target.mkdir(mode=0o700)
            (Path(root) / "project-object-file-opens").symlink_to(target)
            with self.assertRaises(ValueError):
                opener.runtime_root()

    def workspace_api(self, workspace="source"):
        return {"hypr_clients": Mock(return_value=[{"address": "0x1"}]),
                "invoking_workspace": Mock(return_value=workspace), "validate_workspace_rule": Mock(),
                "verify_window": Mock()}

    def test_vivaldi_has_dedicated_local_route(self):
        app = Mock()
        app.get_boolean.return_value = False
        app.get_commandline.return_value = "/nix/store/test/bin/vivaldi %U"
        with patch.object(opener, "local_file", return_value=(Path("/tmp/a.html"), "part")), \
             patch.object(opener, "desktop_app", return_value=app), \
             patch.object(opener.runpy, "run_path", return_value=self.workspace_api()), \
             patch.object(opener, "open_vivaldi") as browser:
            opener.open_file("file:///tmp/a.html#part")
            browser.assert_called_once_with(Path("/tmp/a.html"), "part", "source", {"0x1"})

    def test_no_workspace_no_launch(self):
        with patch.object(opener, "local_file", return_value=(Path("/tmp/a"), "")), \
             patch.object(opener, "desktop_app"), \
             patch.object(opener, "validate_app", return_value="desktop"), \
             patch.object(opener.runpy, "run_path", return_value=self.workspace_api(None)), \
             patch.object(opener.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "workspace"):
                opener.open_file("file:///tmp/a")
            run.assert_not_called()

    def test_default_app_uses_verifier_and_quoted_arguments(self):
        app = Mock()
        app.get_boolean.return_value = False
        app.get_commandline.return_value = "zathura %U"
        path = Path("/tmp/a ; $(echo x).pdf")
        api = self.workspace_api()
        with patch.object(opener, "local_file", return_value=(path, "")), \
             patch.object(opener, "desktop_app", return_value=app), \
             patch.object(opener.runpy, "run_path", return_value=api), \
             patch.object(opener, "command", return_value="ok") as command:
            opener.open_file(path.as_uri())
            payload = command.call_args.args[-1]
            rules, child = payload.split("] ", 1)
            self.assertIn("no_initial_focus on", rules)
            self.assertIn("suppress_event activate activatefocus", rules)
            import shlex
            args = shlex.split(child)
            self.assertEqual(args[-2:], ["--desktop-launch", path.as_uri()])
            api["verify_window"].assert_called_once()
            api["verify_window"].side_effect = RuntimeError("verification failed")
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                opener.open_file(path.as_uri())

    def test_unsupported_singleton_and_dbus_are_rejected_before_launch(self):
        app = Mock()
        app.get_name.return_value = "Unsupported viewer"
        for dbus, command in ((True, "zathura %U"), (False, "unknown-viewer %U"),
                              (False, "nvim --remote %F"), (False, "kitty +open %U")):
            app.get_boolean.return_value = dbus
            app.get_commandline.return_value = command
            with self.subTest(command=command, dbus=dbus), \
                 patch.object(opener, "local_file", return_value=(Path("/tmp/a.pdf"), "")), \
                 patch.object(opener, "desktop_app", return_value=app), \
                 patch.object(opener.runpy, "run_path") as api, \
                 self.assertRaises(ValueError):
                opener.open_file("file:///tmp/a.pdf")
            api.assert_not_called()

    def test_terminal_fallback_rejected_before_dispatch(self):
        app = Mock()
        app.get_boolean.side_effect = lambda key: key == "Terminal"
        app.get_commandline.return_value = "zathura %U"
        with patch.object(opener, "local_file", return_value=(Path("/tmp/a.pdf"), "")), \
             patch.object(opener, "desktop_app", return_value=app), \
             patch.object(opener.runpy, "run_path") as api:
            with self.assertRaisesRegex(ValueError, "terminal fallback"):
                opener.open_file("file:///tmp/a.pdf")
            api.assert_not_called()

    def test_changed_child_route_cannot_launch_vivaldi_directly(self):
        app = Mock()
        with patch.object(opener.sys, "argv", [str(SOURCE), "--desktop-launch", "file:///tmp/a"]), \
             patch.object(opener, "local_file", return_value=(Path("/tmp/a"), "")), \
             patch.object(opener, "desktop_app", return_value=app), \
             patch.object(opener, "validate_app", return_value="vivaldi"), \
             patch.object(opener.subprocess, "run") as run:
            self.assertEqual(opener.main(), 1)
            app.launch.assert_not_called()
            self.assertEqual(run.call_args.args[0][0], "notify-send")

    def test_supported_directory_and_editor_routes(self):
        app = Mock()
        app.get_boolean.return_value = False
        app.get_commandline.return_value = "nvim %F"
        self.assertEqual(opener.validate_app(app, Path("/tmp/a.txt")), "editor")
        app.get_commandline.return_value = "kitty +open %U"
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(opener.validate_app(app, Path(root)), "desktop")

    def test_errors_are_not_silent(self):
        with patch.object(opener.sys, "argv", [str(SOURCE), "file:///missing"]), \
             patch.object(opener, "open_file", side_effect=RuntimeError("missing file")), \
             patch.object(opener.subprocess, "run") as notify:
            self.assertEqual(opener.main(), 1)
            self.assertEqual(notify.call_args.args[0][:2], ["notify-send", "File opening failed"])

    def test_browser_rule_and_bootstrap_are_private_and_exact(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"XDG_RUNTIME_DIR": root}), \
             patch.object(opener.subprocess, "Popen") as launch:
            def command(_ctl, *args):
                if args[0] == "keyword":
                    return "ok"
                uri = launch.call_args.args[0][-1].removeprefix("--app=")
                from urllib.parse import urlsplit
                path = urlsplit(uri).path
                return __import__("json").dumps([{"mapped": True, "address": "0x2",
                    "workspace": {"name": "source"}, "class": "vivaldi-_" + path.replace("/", "_") + "-Default"}])
            with patch.object(opener, "command", side_effect=command) as ctl:
                opener.open_vivaldi(Path('/tmp/private " file.html'), "part", "source", {"0x1"})
            files = list(Path(root).glob("project-object-file-opens/open-*/open.html"))
            self.assertEqual(len(files), 1)
            self.assertIn("file:///tmp/private%20%22%20file.html#part", files[0].read_text())
            self.assertEqual(files[0].parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(ctl.call_args.args[1:], ("keyword", opener.RULE + ":enable", "0"))


if __name__ == "__main__":
    unittest.main()
