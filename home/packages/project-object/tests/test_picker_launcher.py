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

    def test_generation_is_checked_before_existing_window_is_focused(self):
        events = []
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", side_effect=lambda: events.append("generation") or 42), \
             mock.patch.object(self.launcher, "focus_existing_picker", side_effect=lambda: events.append("focus") or True), \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        self.assertEqual(events, ["generation", "focus"])
        start.assert_not_called()

    def test_missing_current_daemon_starts_new_generation_without_focusing_stale_window(self):
        with mock.patch.object(sys, "argv", ["project-picker"]), \
             mock.patch.object(self.launcher, "running_daemon", return_value=None), \
             mock.patch.object(self.launcher, "focus_existing_picker") as focus, \
             mock.patch.object(self.launcher, "start_daemon") as start:
            self.launcher.main()
        focus.assert_not_called()
        start.assert_called_once_with(show=True)


if __name__ == "__main__":
    unittest.main()
