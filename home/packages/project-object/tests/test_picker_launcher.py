import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_launcher(runtime_root: Path):
    with mock.patch.dict(os.environ, {"PROJECT_OBJECT_RUNTIME_DIR": str(runtime_root)}):
        loader = SourceFileLoader("project_picker_launcher_test", str(ROOT / "bin" / "project-picker"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module


class PickerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.launcher = load_launcher(Path(self.temporary.name) / "runtime")

    def tearDown(self):
        self.temporary.cleanup()

    def test_generation_is_checked_before_existing_window_is_dismissed(self):
        events = []
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", side_effect=lambda: events.append("generation") or 42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker", side_effect=lambda pid: events.append(("dismiss", pid)) or True), \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        self.assertEqual(events, ["generation", ("dismiss", 42)])
        start.assert_not_called()

    def test_only_current_daemon_picker_is_closed_through_hyprland(self):
        clients = mock.Mock(
            returncode=0,
            stdout=(
                '[{"class":"dev.project_object.Picker","address":"0xstale","pid":41},'
                '{"class":"dev.project_object.Picker","address":"0xcurrent","pid":42}]'
            ),
        )
        dismissed = mock.Mock(returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=[clients, dismissed]) as run:
            self.assertTrue(self.launcher.dismiss_existing_picker(42))
        self.assertEqual(
            run.call_args_list[1].args[0],
            [self.launcher.HYPRCTL, "dispatch", "closewindow", "address:0xcurrent"],
        )

    def test_close_active_workspace_signals_running_daemon_without_toggling_picker(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--close-active-workspace"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker") as dismiss, \
             mock.patch.object(self.launcher.os, "kill") as kill:
            self.launcher.main()
        dismiss.assert_not_called()
        kill.assert_called_once_with(42, self.launcher.signal.SIGUSR2)

    def test_close_active_workspace_starts_hidden_daemon_with_action_when_missing(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--close-active-workspace"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        start.assert_called_once_with(show=False, close_active_workspace=True)

    def test_next_attention_signals_without_toggling_picker(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--next-attention"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker") as dismiss, \
             mock.patch.object(self.launcher.os, "kill") as kill:
            self.launcher.main()
        dismiss.assert_not_called()
        kill.assert_called_once_with(42, signal.SIGHUP)

    def test_next_attention_starts_hidden_daemon_with_action(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--next-attention"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        start.assert_called_once_with(show=False, next_attention=True)
        with mock.patch.object(self.launcher.subprocess, "Popen") as popen, \
             mock.patch.object(self.launcher, "wait_for_daemon"):
            self.launcher.start_daemon(show=False, next_attention=True)
        self.assertEqual(popen.call_args.args[0], [str(self.launcher.GUI), "--daemon", "--next-attention"])
        module = (ROOT / "nix" / "home-manager-module.nix").read_text()
        self.assertIn('$mod, n, exec, ${package}/bin/project-picker --next-attention', module)
        gui = (ROOT / "bin" / "project-picker-gui").read_text()
        self.assertIn('signal.SIGHUP, application.jump_next_attention', gui)
        self.assertIn('GLib.idle_add(jump_once)', gui)

    def test_previous_attention_signals_without_toggling_picker(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--previous-attention"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker") as dismiss, \
             mock.patch.object(self.launcher.os, "kill") as kill:
            self.launcher.main()
        dismiss.assert_not_called()
        kill.assert_called_once_with(42, signal.SIGINT)

    def test_previous_attention_starts_hidden_daemon_with_action(self):
        with mock.patch.object(sys, "argv", ["project-picker", "--previous-attention"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        start.assert_called_once_with(show=False, previous_attention=True)
        with mock.patch.object(self.launcher.subprocess, "Popen") as popen, \
             mock.patch.object(self.launcher, "wait_for_daemon"):
            self.launcher.start_daemon(show=False, previous_attention=True)
        self.assertEqual(popen.call_args.args[0], [str(self.launcher.GUI), "--daemon", "--previous-attention"])
        module = (ROOT / "nix" / "home-manager-module.nix").read_text()
        self.assertIn('$mod SHIFT, n, exec, ${package}/bin/project-picker --previous-attention', module)
        gui = (ROOT / "bin" / "project-picker-gui").read_text()
        self.assertIn('signal.SIGINT, application.jump_previous_attention', gui)

    def test_hidden_picker_is_woken_when_no_window_can_be_dismissed(self):
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker", return_value=False), \
             mock.patch.object(self.launcher.os, "kill") as kill:
            self.launcher.main()
        kill.assert_called_once_with(42, self.launcher.signal.SIGUSR1)

    def test_concurrent_cold_close_requests_wait_for_one_ready_daemon(self):
        root = Path(self.temporary.name)
        launcher = root / "project-picker"
        gui = root / "project-picker-gui"
        marker = root / "starts"
        launcher.write_bytes((ROOT / "bin" / "project-picker").read_bytes())
        launcher.chmod(0o755)
        gui.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, signal, sys, time\n"
            "with open(os.environ['PICKER_START_MARKER'], 'a') as stream:\n"
            "    stream.write(f'{os.getpid()}\\n')\n"
            "def stop(*_args):\n"
            "    raise SystemExit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "signal.signal(signal.SIGUSR2, lambda *_args: None)\n"
            "time.sleep(0.15)\n"
            "runtime = pathlib.Path(os.environ['PROJECT_OBJECT_RUNTIME_DIR'])\n"
            "runtime.mkdir(parents=True, exist_ok=True)\n"
            "record = {'pid': os.getpid(), 'command': str(pathlib.Path(sys.argv[0]).resolve())}\n"
            "(runtime / 'picker-gui.json').write_text(json.dumps(record) + '\\n')\n"
            "while True:\n"
            "    time.sleep(1)\n"
        )
        gui.chmod(0o755)
        environment = {
            **os.environ,
            "PROJECT_OBJECT_RUNTIME_DIR": str(root / "runtime"),
            "PICKER_START_MARKER": str(marker),
        }
        daemon_pid = None
        try:
            processes = [
                subprocess.Popen([str(launcher), "--close-active-workspace"], env=environment)
                for _ in range(2)
            ]
            for process in processes:
                self.assertEqual(process.wait(timeout=5), 0)
            record = json.loads((root / "runtime" / "picker-gui.json").read_text())
            daemon_pid = record["pid"]
            deadline = time.monotonic() + 2
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            starts = marker.read_text().splitlines()
            self.assertEqual(starts, [str(daemon_pid)])
        finally:
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_missing_current_daemon_starts_new_generation_without_dismissing_stale_window(self):
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "dismiss_existing_picker") as dismiss, \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        dismiss.assert_not_called()
        start.assert_called_once_with(show=True, close_active_workspace=False)


if __name__ == "__main__":
    unittest.main()
