import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import sys
import tempfile
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

    def test_hidden_picker_is_woken_when_no_window_can_be_dismissed(self):
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=42), \
             mock.patch.object(self.launcher, "dismiss_existing_picker", return_value=False), \
             mock.patch.object(self.launcher.os, "kill") as kill:
            self.launcher.main()
        kill.assert_called_once_with(42, self.launcher.signal.SIGUSR1)

    def test_missing_current_daemon_starts_new_generation_without_dismissing_stale_window(self):
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "dismiss_existing_picker") as dismiss, \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        dismiss.assert_not_called()
        start.assert_called_once_with(show=True)


if __name__ == "__main__":
    unittest.main()
