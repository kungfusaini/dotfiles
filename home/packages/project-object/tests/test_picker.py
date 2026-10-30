import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]


def load_picker(root: Path):
    environment = {
        "PROJECT_OBJECT_DATA_DIR": str(root / "data"),
        "PROJECT_OBJECT_RUNTIME_DIR": str(root / "runtime"),
        "HYPRLAND_INSTANCE_SIGNATURE": "test-instance",
    }
    with mock.patch.dict(os.environ, environment):
        loader = SourceFileLoader("project_picker_test", str(ROOT / "bin" / "project-picker-tui"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.picker = load_picker(self.root)
        self.project = {"id": str(uuid.uuid4()), "name": "Alpha", "mainDirectory": str(self.root)}
        self.session = {"version": 2, "hyprlandInstance": "test-instance", "openWorkspaces": []}

    def tearDown(self):
        self.temporary.cleanup()

    def test_picker_items_keep_registry_order_when_runtime_state_changes(self):
        second_project = {"id": str(uuid.uuid4()), "name": "Beta", "mainDirectory": str(self.root)}
        registry = {"version": 1, "projects": [self.project, second_project]}
        self.session["openWorkspaces"] = [self.picker.project_scope(self.project)]
        projects = self.picker.project_picker_items(registry, self.session, second_project["name"])
        self.assertEqual([(item["name"], state) for item, state in projects], [
            ("Alpha", "open"),
            ("Beta", "current"),
        ])

        first_stream = {"id": str(uuid.uuid4()), "name": "First"}
        second_stream = {"id": str(uuid.uuid4()), "name": "Second"}
        stream_registry = {"version": 1, "streams": [first_stream, second_stream]}
        streams = self.picker.stream_picker_items(
            self.project,
            stream_registry,
            self.session,
            self.picker.stream_workspace_name(self.project, second_stream),
        )
        self.assertEqual([(item["name"], state) for item, state in streams], [
            ("First", "closed"),
            ("Second", "current"),
        ])

    def test_dispatch_failure_rolls_back_session(self):
        failed = mock.Mock(returncode=1)
        with mock.patch.object(self.picker, "active_workspace_name", return_value="before"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "run", return_value=failed), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            with self.assertRaisesRegex(RuntimeError, "Could not enter"):
                self.picker.enter_project(self.project, self.session, True)
        self.assertEqual(self.session["openWorkspaces"], [])
        self.assertEqual(write.call_count, 2)

    def test_terminal_launch_failure_restores_workspace_and_session(self):
        success = mock.Mock(returncode=0)
        commands = []
        def run(command):
            commands.append(command)
            return success
        with mock.patch.object(self.picker, "active_workspace_name", return_value="before"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "run", side_effect=run), \
             mock.patch.object(self.picker, "write_json_atomic"), \
             mock.patch.object(self.picker.subprocess, "Popen", side_effect=OSError("missing")):
            with self.assertRaises(OSError):
                self.picker.enter_project(self.project, self.session, True)
        self.assertEqual(self.session["openWorkspaces"], [])
        self.assertIn([self.picker.HYPRCTL, "dispatch", "workspace", "name:before"], commands)

    def test_project_creation_scaffolds_one_time_init_placeholder(self):
        registry = {"version": 1, "projects": []}
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            project = self.picker.create_project(registry, "New Project", str(self.root))
        agents = self.picker.project_home(project) / "AGENTS.md"
        self.assertIn("<!-- project-object:init-scope -->", agents.read_text())

    def test_registry_write_failure_removes_new_project_home(self):
        ui = self.picker.PickerUI.__new__(self.picker.PickerUI)
        ui.create_name = "New Project"
        ui.create_directory = str(self.root)
        ui.registry = {"version": 1, "projects": []}
        ui.message = ""
        ui.result = None
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "write_json_atomic", side_effect=OSError("disk full")):
            ui.submit_create()
        self.assertEqual(ui.registry["projects"], [])
        self.assertIsNone(ui.result)
        self.assertIn("disk full", ui.message)
        projects_root = self.picker.DATA_ROOT / "projects"
        self.assertEqual(list(projects_root.iterdir()), [])

    def test_instance_change_resets_runtime_session(self):
        self.picker.ensure_directory(self.picker.RUNTIME_ROOT)
        self.picker.write_json_atomic(self.picker.SESSION_PATH, {
            "version": 1,
            "hyprlandInstance": "old-instance",
            "openProjectIds": [self.project["id"]],
        })
        self.assertEqual(self.picker.load_session()["openWorkspaces"], [])

    def test_current_instance_migrates_project_runtime_state(self):
        self.picker.ensure_directory(self.picker.RUNTIME_ROOT)
        self.picker.write_json_atomic(self.picker.SESSION_PATH, {
            "version": 1,
            "hyprlandInstance": "test-instance",
            "openProjectIds": [self.project["id"]],
        })
        self.assertEqual(self.picker.load_session()["openWorkspaces"], [
            {"kind": "project", "projectId": self.project["id"]},
        ])

    def test_create_stream_scaffolds_boundary_artifacts(self):
        self.picker.initialize_project_home(self.project)
        registry = {"version": 1, "streams": []}
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            stream = self.picker.create_stream(self.project, registry, "Focused Work")
        home = self.picker.stream_home(self.project, stream)
        self.assertEqual(self.picker.stream_workspace_name(self.project, stream), "Alpha · Focused Work")
        for name in ("AGENTS.md", "NOTES.md", "TODO.md"):
            self.assertTrue((home / name).is_file())
            self.assertEqual((home / name).stat().st_mode & 0o777, 0o600)
        self.assertFalse((home / "CONTEXT.md").exists())
        self.assertFalse((home / "STATUS.md").exists())
        instructions = (home / "AGENTS.md").read_text()
        self.assertIn("# Focused Work", instructions)
        self.assertIn("<!-- project-object:init-scope -->", instructions)
        self.assertNotIn(".creating-", instructions)
        self.assertIn("## Now", (home / "TODO.md").read_text())
        for name in ("plans", "worklogs", "snapshots"):
            self.assertTrue((home / name).is_dir())
            self.assertEqual((home / name).stat().st_mode & 0o777, 0o700)
        saved = __import__("json").loads((self.picker.project_home(self.project) / "streams.json").read_text())
        self.assertEqual(saved["streams"][0]["id"], stream["id"])

    def test_stream_creation_rejects_registered_workspace_ambiguity(self):
        colliding_project = {
            "id": str(uuid.uuid4()),
            "name": "Alpha · Focused Work",
            "mainDirectory": str(self.root),
            "archivedAt": None,
        }
        self.picker.ensure_directory(self.picker.DATA_ROOT)
        self.picker.write_json_atomic(self.picker.REGISTRY_PATH, {"version": 1, "projects": [self.project, colliding_project]})
        self.picker.initialize_project_home(self.project)
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "already represented"):
                self.picker.create_stream(self.project, {"version": 1, "streams": []}, "Focused Work")

    def test_post_commit_stream_registry_failure_keeps_registered_home(self):
        import json
        self.picker.initialize_project_home(self.project)
        registry = {"version": 1, "streams": []}

        def committed_then_failed(file, value):
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(value))
            raise self.picker.AtomicWriteCommittedError("simulated parent fsync failure")

        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "durable_write_json_atomic", side_effect=committed_then_failed):
            stream = self.picker.create_stream(self.project, registry, "Committed Stream")
        home = self.picker.stream_home(self.project, stream)
        self.assertTrue(home.is_dir())
        saved = json.loads((self.picker.project_home(self.project) / "streams.json").read_text())
        self.assertEqual(saved["streams"][0]["id"], stream["id"])

    def test_project_creation_rejects_registered_stream_workspace(self):
        self.picker.initialize_project_home(self.project)
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work", "mainDirectory": None, "archivedAt": None}
        self.picker.write_json_atomic(self.picker.project_home(self.project) / "streams.json", {"version": 1, "streams": [stream]})
        registry = {"version": 1, "projects": [self.project]}
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "already represented"):
                self.picker.create_project(registry, "Alpha · Focused Work", str(self.root))

    def test_reconcile_removes_stale_project_scope_without_closing_stream(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work", "mainDirectory": None, "archivedAt": None}
        self.picker.initialize_project_home(self.project)
        self.picker.write_json_atomic(self.picker.project_home(self.project) / "streams.json", {"version": 1, "streams": [stream]})
        project_scope = self.picker.project_scope(self.project)
        stream_scope = self.picker.stream_scope(self.project, stream)
        session = {"version": 2, "hyprlandInstance": "test-instance", "openWorkspaces": [project_scope, stream_scope]}
        registry = {"version": 1, "projects": [self.project]}
        with mock.patch.object(self.picker, "hypr_json", return_value=[{"name": "Alpha · Focused Work"}]), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            self.picker.reconcile_session(registry, session)
        self.assertEqual(session["openWorkspaces"], [stream_scope])
        write.assert_called_once()

    def test_close_project_snapshots_only_project_and_retains_stream_scope(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work"}
        project_scope = self.picker.project_scope(self.project)
        stream_scope = self.picker.stream_scope(self.project, stream)
        session = {"version": 2, "hyprlandInstance": "test-instance", "openWorkspaces": [project_scope, stream_scope]}
        success = mock.Mock(returncode=0, stdout="", stderr="")
        commands = []
        def run(command):
            commands.append(command)
            return success
        with mock.patch.object(self.picker, "run", side_effect=run), \
             mock.patch.object(self.picker, "active_workspace_name", return_value="Elsewhere"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=True), \
             mock.patch.object(self.picker, "workspace_clients", side_effect=[[], []]), \
             mock.patch.object(self.picker, "write_json_atomic"):
            self.picker.close_project(self.project, session)
        self.assertEqual(session["openWorkspaces"], [stream_scope])
        self.assertIn([self.picker.PROJECT_SNAPSHOT, "--project-id", self.project["id"]], commands)
        self.assertFalse(any("--stream-id" in command for command in commands))

    def test_close_stream_snapshots_closes_windows_and_updates_state(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work"}
        scope = self.picker.stream_scope(self.project, stream)
        session = {"version": 2, "hyprlandInstance": "test-instance", "openWorkspaces": [scope]}
        success = mock.Mock(returncode=0, stdout="", stderr="")
        client = {"address": "0xabc", "workspace": {"name": "Alpha · Focused Work"}}
        browser_client = {"address": "0xdef", "workspace": {"name": "Alpha · Browser"}}
        commands = []
        def run(command):
            commands.append(command)
            return success
        with mock.patch.object(self.picker, "run", side_effect=run), \
             mock.patch.object(self.picker, "active_workspace_name", return_value="Elsewhere"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=True), \
             mock.patch.object(self.picker, "workspace_clients", side_effect=[[browser_client], [], [], [client], [], []]), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            self.picker.close_stream(self.project, stream, session)
        self.assertEqual(session["openWorkspaces"], [])
        self.assertIn([self.picker.PROJECT_SNAPSHOT, "--project-id", self.project["id"], "--stream-id", stream["id"]], commands)
        self.assertIn([self.picker.HYPRCTL, "dispatch", "closewindow", "address:0xabc"], commands)
        self.assertIn([self.picker.HYPRCTL, "dispatch", "closewindow", "address:0xdef"], commands)
        write.assert_called_once()

    def test_archive_stream_closes_workspace_before_registry_update(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work", "archivedAt": None, "updatedAt": "before"}
        stream_registry = {"version": 1, "streams": [stream]}
        calls = []

        def close(_project, _stream, _session):
            calls.append("close")
            self.assertIsNone(stream["archivedAt"])

        def write(path, value):
            calls.append("write")
            self.assertEqual(path, self.picker.project_home(self.project) / "streams.json")
            self.assertIs(value, stream_registry)
            self.assertIsNotNone(stream["archivedAt"])

        with mock.patch.object(self.picker, "close_stream", side_effect=close), \
             mock.patch.object(self.picker, "write_json_atomic", side_effect=write):
            self.picker.archive_stream(self.project, stream, stream_registry, self.session)

        self.assertEqual(calls, ["close", "write"])
        self.assertNotEqual(stream["updatedAt"], "before")

    def test_archive_stream_close_failure_leaves_stream_active(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work", "archivedAt": None, "updatedAt": "before"}
        stream_registry = {"version": 1, "streams": [stream]}
        with mock.patch.object(self.picker, "close_stream", side_effect=RuntimeError("window refused")), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            with self.assertRaisesRegex(RuntimeError, "window refused"):
                self.picker.archive_stream(self.project, stream, stream_registry, self.session)
        self.assertIsNone(stream["archivedAt"])
        self.assertEqual(stream["updatedAt"], "before")
        write.assert_not_called()

    def test_archive_project_closes_streams_and_project_before_registry_update(self):
        stream_one = {"id": str(uuid.uuid4()), "name": "One", "archivedAt": None}
        stream_two = {"id": str(uuid.uuid4()), "name": "Two", "archivedAt": None}
        project = {**self.project, "archivedAt": None, "updatedAt": "before"}
        registry = {"version": 1, "projects": [project]}
        calls = []
        with mock.patch.object(self.picker, "load_stream_registry", return_value={"version": 1, "streams": [stream_one, stream_two]}), \
             mock.patch.object(self.picker, "close_stream", side_effect=lambda _project, stream, _session: calls.append(("stream", stream["id"]))), \
             mock.patch.object(self.picker, "close_project", side_effect=lambda _project, _session: calls.append(("project", project["id"]))), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            self.picker.archive_project(project, registry, self.session)
        self.assertEqual(calls, [("stream", stream_one["id"]), ("stream", stream_two["id"]), ("project", project["id"])])
        self.assertIsNotNone(project["archivedAt"])
        self.assertNotEqual(project["updatedAt"], "before")
        write.assert_called_once_with(self.picker.REGISTRY_PATH, registry)

    def test_archive_project_retains_project_and_stream_homes(self):
        stream = {"id": str(uuid.uuid4()), "name": "One", "mainDirectory": None, "archivedAt": None}
        project = {**self.project, "archivedAt": None, "updatedAt": "before"}
        registry = {"version": 1, "projects": [project]}
        self.picker.initialize_project_home(project)
        self.picker.initialize_stream_home(project, stream)
        project_marker = self.picker.project_home(project) / "NOTES.md"
        stream_marker = self.picker.stream_home(project, stream) / "NOTES.md"
        project_marker.write_text("project retained\n")
        stream_marker.write_text("stream retained\n")
        self.picker.write_json_atomic(self.picker.project_home(project) / "streams.json", {"version": 1, "streams": [stream]})
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            self.picker.archive_project(project, registry, self.session)
        saved = __import__("json").loads(self.picker.REGISTRY_PATH.read_text())
        self.assertIsNotNone(saved["projects"][0]["archivedAt"])
        self.assertEqual(project_marker.read_text(), "project retained\n")
        self.assertEqual(stream_marker.read_text(), "stream retained\n")

    def test_archive_project_close_failure_does_not_mark_registry_archived(self):
        stream = {"id": str(uuid.uuid4()), "name": "One", "archivedAt": None}
        project = {**self.project, "archivedAt": None, "updatedAt": "before"}
        registry = {"version": 1, "projects": [project]}
        with mock.patch.object(self.picker, "load_stream_registry", return_value={"version": 1, "streams": [stream]}), \
             mock.patch.object(self.picker, "close_stream", side_effect=RuntimeError("window refused")), \
             mock.patch.object(self.picker, "close_project"), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            with self.assertRaisesRegex(RuntimeError, "window refused"):
                self.picker.archive_project(project, registry, self.session)
        self.assertIsNone(project["archivedAt"])
        self.assertEqual(project["updatedAt"], "before")
        write.assert_not_called()

    def test_stale_lock_is_reclaimed(self):
        self.picker.ensure_directory(self.picker.LOCK_PATH)
        (self.picker.LOCK_PATH / "pid").write_text("not-a-pid")
        self.assertTrue(self.picker.acquire_lock())
        self.picker.release_lock()


if __name__ == "__main__":
    unittest.main()
