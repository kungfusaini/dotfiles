import importlib.machinery
import importlib.util
import json
import os
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / "bin" / "project-browser"


def load_browser(root: Path):
    name = f"project_browser_test_{uuid.uuid4().hex}"
    loader = importlib.machinery.SourceFileLoader(name, str(BROWSER))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    environment = {
        "PROJECT_OBJECT_DATA_DIR": str(root / "data"),
        "PROJECT_OBJECT_RUNTIME_DIR": str(root / "runtime"),
    }
    with mock.patch.dict(os.environ, environment, clear=False):
        loader.exec_module(module)
    return module


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.main = self.root / "main"
        self.main.mkdir()
        self.project_id = str(uuid.uuid4())
        self.project = {
            "id": self.project_id,
            "name": "Alpha",
            "mainDirectory": str(self.main),
            "archivedAt": None,
        }
        self.registry = {"version": 1, "projects": [self.project]}
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        self.browser = load_browser(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_workspace_resolution_includes_stream_and_browser_role(self):
        stream_id = str(uuid.uuid4())
        home = self.data / "projects" / self.project_id
        home.mkdir(parents=True)
        (home / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused", "mainDirectory": None, "archivedAt": None}],
        }))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECT_OBJECT_ID", None)
            browser_match = self.browser.resolve_project(self.registry, "Alpha · Browser")
            stream_match = self.browser.resolve_project(self.registry, "Alpha · Focused")
        self.assertEqual(browser_match["id"], self.project_id)
        self.assertEqual(stream_match["id"], self.project_id)

    def test_plain_open_uses_companion_and_project_mode_uses_primary(self):
        state = self.browser.empty_state()
        patches = (
            mock.patch.object(self.browser, "active_workspace_name", return_value="Alpha"),
            mock.patch.object(self.browser, "load_registry", return_value=self.registry),
            mock.patch.object(self.browser, "browser_lock", return_value=nullcontext()),
            mock.patch.object(self.browser, "load_state", return_value=state),
            mock.patch.object(self.browser, "ensure_companion_browser"),
            mock.patch.object(self.browser, "ensure_project_browser"),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4] as companion, patches[5] as primary, \
                mock.patch.dict(os.environ, {"PROJECT_OBJECT_ID": self.project_id}):
            self.browser.open_urls("adjacent", ["https://example.com/quick"])
            companion.assert_called_once()
            primary.assert_not_called()
            companion.reset_mock()
            self.browser.open_urls("project", ["https://example.com/reference"])
            primary.assert_called_once()
            companion.assert_not_called()

    def test_super_b_returns_from_project_browser_to_last_live_stream(self):
        state = self.browser.empty_state()
        state["returns"][self.project_id] = "Alpha · Focused"
        with mock.patch.object(self.browser, "live_workspace_names", return_value={"Alpha · Browser", "Alpha · Focused"}), \
                mock.patch.object(self.browser, "workspace_belongs_to_project", return_value=True), \
                mock.patch.object(self.browser, "dispatch") as dispatch:
            returned = self.browser.return_from_project_browser(self.registry, self.project, state)
        self.assertTrue(returned)
        dispatch.assert_called_once_with("workspace", "name:Alpha · Focused")

    def test_project_browser_records_the_origin_workspace(self):
        state = self.browser.empty_state()
        with mock.patch.object(self.browser, "validate_browser_role", return_value="Alpha · Browser"), \
                mock.patch.object(self.browser, "workspace_belongs_to_project", return_value=True), \
                mock.patch.object(self.browser, "save_state"), \
                mock.patch.object(self.browser, "dispatch"), \
                mock.patch.object(self.browser, "discover_address", return_value="0xabc"), \
                mock.patch.object(self.browser, "open_in_window"):
            self.browser.ensure_project_browser(
                self.registry,
                self.project,
                [],
                state,
                focus_only=True,
                origin_workspace="Alpha · Focused",
            )
        self.assertEqual(state["returns"][self.project_id], "Alpha · Focused")

    def test_shift_click_marker_is_one_shot_and_scoped_to_kitty_window(self):
        with mock.patch.dict(os.environ, {"KITTY_WINDOW_ID": "42"}):
            self.browser.mark_project_click()
            self.assertEqual(self.browser.consume_click_mode("adjacent"), "project")
            self.assertEqual(self.browser.consume_click_mode("adjacent"), "adjacent")

    def test_shift_click_marker_falls_back_to_shared_parent_pid(self):
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(self.browser.os, "getppid", return_value=1234):
            os.environ.pop("KITTY_WINDOW_ID", None)
            self.browser.mark_project_click()
            self.assertEqual(self.browser.consume_click_mode("adjacent"), "project")

    def test_non_project_open_uses_global_browser(self):
        with mock.patch.object(self.browser, "active_workspace_name", return_value="comms"), \
                mock.patch.object(self.browser, "load_registry", return_value=self.registry), \
                mock.patch.object(self.browser, "ensure_global_browser") as global_browser, \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECT_OBJECT_ID", None)
            self.browser.open_urls("adjacent", ["https://example.com"])
        global_browser.assert_called_once_with(["https://example.com"])

    def test_rejects_non_web_urls(self):
        with self.assertRaises(ValueError):
            self.browser.validate_urls(["file:///tmp/private"])


if __name__ == "__main__":
    unittest.main()
