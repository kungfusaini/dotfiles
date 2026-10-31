from concurrent.futures import ThreadPoolExecutor
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]


def load_picker(root: Path):
    environment = {
        "PROJECT_OBJECT_DATA_DIR": str(root / "data"),
        "PROJECT_OBJECT_RUNTIME_DIR": str(root / "runtime"),
        "PROJECT_OBJECT_STATE_DIR": str(root / "state"),
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

    def make_git_repository(self, name="repository"):
        repository = self.root / name
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        (repository / "README.md").write_text("initial\n")
        subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
        subprocess.run([
            "git", "-C", str(repository), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "initial",
        ], check=True)
        return repository.resolve()

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

    def test_opening_closed_stream_restores_exact_snapshotted_pi_session(self):
        import json
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work"}
        self.picker.initialize_stream_home(self.project, stream)
        session_id = "restore-session-123"
        session_directory = self.picker.stream_session_directory(
            self.picker.STATE_ROOT, self.project["id"], stream["id"]
        )
        session_directory.mkdir(parents=True)
        (session_directory / f"2026-01-01T00-00-00_{session_id}.jsonl").write_text(json.dumps({
            "type": "session", "version": 3, "id": session_id, "cwd": str(self.root)
        }) + "\n")
        snapshot = {
            "version": 1,
            "projectId": self.project["id"],
            "scope": "stream",
            "streamId": stream["id"],
            "windows": [{"class": "kitty", "initialClass": "kitty", "piSessionId": session_id}],
        }
        self.picker.write_json_atomic(self.picker.stream_home(self.project, stream) / "snapshots" / "workspace.json", snapshot)
        success = mock.Mock(returncode=0)
        with mock.patch.object(self.picker, "active_workspace_name", return_value="before"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "run", return_value=success), \
             mock.patch.object(self.picker, "write_json_atomic"), \
             mock.patch.object(self.picker.subprocess, "Popen") as launch:
            self.picker.enter_stream(self.project, stream, self.session)
        command = launch.call_args.args[0]
        self.assertEqual(command[-4:], ["-e", "pi", "--session", session_id])

    def test_opening_closed_stream_restores_every_ordered_pi_session(self):
        import json
        stream = {"id": str(uuid.uuid4()), "name": "Many Agents"}
        self.picker.initialize_stream_home(self.project, stream)
        session_directory = self.picker.stream_session_directory(
            self.picker.STATE_ROOT, self.project["id"], stream["id"]
        )
        session_directory.mkdir(parents=True)
        session_ids = ["restore-session-one", "restore-session-two"]
        for index, session_id in enumerate(session_ids):
            (session_directory / f"2026-01-01T00-00-0{index}_{session_id}.jsonl").write_text(json.dumps({
                "type": "session", "version": 3, "id": session_id, "cwd": str(self.root)
            }) + "\n")
        snapshot = {
            "version": 1,
            "projectId": self.project["id"],
            "scope": "stream",
            "streamId": stream["id"],
            "windows": [
                {"order": 1, "class": "kitty", "initialClass": "kitty", "piSessions": [{"sessionId": session_ids[1]}]},
                {"order": 0, "class": "kitty", "initialClass": "kitty", "piSessions": [{"sessionId": session_ids[0]}]},
                {"order": 2, "class": "code", "initialClass": "code"},
            ],
        }
        self.picker.write_json_atomic(self.picker.stream_home(self.project, stream) / "snapshots" / "workspace.json", snapshot)
        success = mock.Mock(returncode=0)
        with mock.patch.object(self.picker, "active_workspace_name", return_value="before"), \
             mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             mock.patch.object(self.picker, "run", return_value=success), \
             mock.patch.object(self.picker, "write_json_atomic"), \
             mock.patch.object(self.picker, "notify_warning") as warning, \
             mock.patch.object(self.picker.subprocess, "Popen") as launch:
            self.picker.enter_stream(self.project, stream, self.session)
        commands = [call.args[0] for call in launch.call_args_list]
        self.assertEqual([command[-1] for command in commands], session_ids)
        self.assertTrue(all(command[-3:-1] == ["pi", "--session"] for command in commands))
        warning.assert_called_once()
        self.assertIn("Restored 2 Pi session", warning.call_args.args[0])
        self.assertIn("1 captured item", warning.call_args.args[0])

    def test_restore_plan_skips_session_that_is_already_live(self):
        import json
        stream = {"id": str(uuid.uuid4()), "name": "Live Elsewhere"}
        self.picker.initialize_stream_home(self.project, stream)
        session_id = "already-live-session"
        session_directory = self.picker.stream_session_directory(
            self.picker.STATE_ROOT, self.project["id"], stream["id"]
        )
        session_directory.mkdir(parents=True)
        (session_directory / f"2026-01-01T00-00-00_{session_id}.jsonl").write_text(json.dumps({
            "type": "session", "version": 3, "id": session_id, "cwd": str(self.root)
        }) + "\n")
        self.picker.write_json_atomic(self.picker.stream_home(self.project, stream) / "snapshots" / "workspace.json", {
            "version": 1,
            "projectId": self.project["id"],
            "scope": "stream",
            "streamId": stream["id"],
            "windows": [{"class": "kitty", "initialClass": "kitty", "piSessions": [{"sessionId": session_id}]}],
        })
        activity = self.picker.RUNTIME_ROOT / "pi-activity"
        activity.mkdir(parents=True)
        pid = os.getpid()
        (activity / f"{pid}.json").write_text(json.dumps({
            "version": 1,
            "pid": pid,
            "processStartTime": self.picker.process_start_time(pid),
            "projectId": self.project["id"],
            "streamId": stream["id"],
            "sessionId": session_id,
        }))
        self.assertEqual(self.picker.restored_pi_plan(self.project, stream), {
            "sessionIds": [],
            "unsupported": 1,
        })

    def test_project_creation_scaffolds_one_time_init_placeholder(self):
        registry = {"version": 1, "projects": []}
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            project = self.picker.create_project(registry, "New Project", str(self.root))
        home = self.picker.project_home(project)
        agents = home / "AGENTS.md"
        self.assertIn("<!-- project-object:init-scope -->", agents.read_text())
        self.assertTrue((home / "skills").is_dir())
        self.assertEqual((home / "skills").stat().st_mode & 0o777, 0o700)

    def test_scope_context_composes_recent_worklog_fields(self):
        self.picker.initialize_project_home(self.project)
        worklog = self.picker.project_home(self.project) / "worklogs" / "events.jsonl"
        events = [
            {
                "v": 1,
                "time": "2026-10-30T12:00:00Z",
                "type": "start",
                "summary": "Starting restoration work",
                "task": "Restore every safely captured Pi session",
                "project": self.project["id"],
                "scope": "project",
            },
            {
                "v": 1,
                "time": "2026-10-30T13:00:00Z",
                "type": "finish",
                "summary": "Restoration implementation finished",
                "brief": {
                    "current": "The restoration implementation is ready.",
                    "next": "Deploy it and run a live restoration test.",
                    "attention": "action",
                },
                "result": "Implementation committed and validated",
                "next": "Deploy and run a live restoration test",
                "project": self.project["id"],
                "scope": "project",
            },
        ]
        worklog.write_text("".join(json.dumps(event) + "\n" for event in events))

        self.assertEqual(self.picker.load_scope_context(self.project), {
            "briefCurrent": "The restoration implementation is ready.",
            "briefNext": "Deploy it and run a live restoration test.",
            "briefAttention": "action",
            "latestType": "finish",
            "detail": "Restoration implementation finished\n\nImplementation committed and validated",
            "happening": "Restore every safely captured Pi session",
            "stopped": "Implementation committed and validated",
            "next": "Deploy and run a live restoration test",
            "nextSource": "worklog",
            "updatedAt": "2026-10-30T13:00:00Z",
            "hasWorklog": True,
        })

    def test_scope_context_keeps_in_progress_preview_compact_without_duplicating_it(self):
        self.picker.initialize_project_home(self.project)
        worklog = self.picker.project_home(self.project) / "worklogs" / "events.jsonl"
        worklog.write_text(json.dumps({
            "v": 1,
            "time": "2026-10-30T13:00:00Z",
            "type": "progress",
            "summary": "word " * 100,
            "brief": {"current": "x" * 161, "attention": "urgent"},
            "project": self.project["id"],
            "scope": "project",
        }) + "\n")
        context = self.picker.load_scope_context(self.project)
        self.assertIsNone(context["briefCurrent"])
        self.assertIsNone(context["briefAttention"])
        self.assertLessEqual(len(context["happening"]), self.picker.MAX_CONTEXT_TEXT_LENGTH)
        self.assertTrue(context["happening"].endswith("…"))
        self.assertEqual(context["stopped"], "Work remains in progress; no separate stopping point is recorded.")

    def test_scope_context_uses_first_unfinished_todo_when_worklog_has_no_next(self):
        self.picker.initialize_project_home(self.project)
        (self.picker.project_home(self.project) / "TODO.md").write_text(
            "# Todo\n\n## Now\n\n- [x] Already done\n- Run the live test\n\n## Next\n\n- Later task\n"
        )
        self.assertEqual(self.picker.load_scope_context(self.project)["next"], "Run the live test")
        self.assertEqual(self.picker.load_scope_context(self.project)["nextSource"], "TODO")

    def test_scope_context_rejects_cross_scope_worklog_and_unsafe_todo(self):
        self.picker.initialize_project_home(self.project)
        home = self.picker.project_home(self.project)
        (home / "worklogs" / "events.jsonl").write_text(json.dumps({
            "v": 1,
            "time": "2026-10-30T13:00:00Z",
            "type": "progress",
            "summary": "Another project's event",
            "project": str(uuid.uuid4()),
            "scope": "project",
        }) + "\n")
        todo = home / "TODO.md"
        todo.unlink()
        external = self.root / "external-todo.md"
        external.write_text("## Now\n- Must not be read\n")
        todo.symlink_to(external)

        self.assertEqual(self.picker.load_scope_context(self.project), {
            "briefCurrent": None,
            "briefNext": None,
            "briefAttention": None,
            "latestType": None,
            "detail": None,
            "happening": None,
            "stopped": None,
            "next": None,
            "nextSource": None,
            "updatedAt": None,
            "hasWorklog": False,
        })

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
            stream = self.picker.create_stream(self.project, registry, "Focused Work", use_worktree=False)
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
        self.assertEqual((home / "TODO.md").read_text(), "# Todo\n\n## Now\n\n## Next\n\n## Waiting\n")
        for name in ("plans", "skills", "worklogs", "snapshots"):
            self.assertTrue((home / name).is_dir())
            self.assertEqual((home / name).stat().st_mode & 0o777, 0o700)
        saved = __import__("json").loads((self.picker.project_home(self.project) / "streams.json").read_text())
        self.assertEqual(saved["streams"][0]["id"], stream["id"])

    def test_git_stream_records_worktree_immediately_and_prepares_it_lazily(self):
        repository = self.make_git_repository()
        project = {**self.project, "mainDirectory": str(repository)}
        self.picker.initialize_project_home(project)
        registry = {"version": 1, "streams": []}
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            stream = self.picker.create_stream(project, registry, "Focused Work")

        directory = Path(stream["worktree"]["directory"])
        self.assertEqual(stream["mainDirectory"], str(directory))
        self.assertFalse(directory.exists())
        branch = stream["worktree"]["branch"]
        self.assertNotEqual(subprocess.run(["git", "-C", str(repository), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode, 0)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: self.picker.prepare_stream_worktree(project, stream), range(2)))
        self.assertEqual(results, [None, None])
        self.assertTrue(directory.is_dir())
        self.assertEqual(subprocess.check_output(["git", "-C", str(directory), "branch", "--show-current"], text=True).strip(), branch)
        self.picker.prepare_stream_worktree(project, stream)

    def test_multi_repository_project_requires_choice_or_explicit_non_code_opt_out(self):
        first = self.make_git_repository("first")
        self.make_git_repository("second")
        project = {**self.project, "mainDirectory": str(self.root)}
        self.picker.initialize_project_home(project)
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "multiple Git repositories"):
                self.picker.create_stream(project, {"version": 1, "streams": []}, "Ambiguous")
            selected = self.picker.create_stream(project, {"version": 1, "streams": []}, "Selected", repository=str(first))
            non_code = self.picker.create_stream(project, {"version": 1, "streams": []}, "Writing", use_worktree=False)
        self.assertEqual(selected["worktree"]["repository"], str(first))
        self.assertNotIn("worktree", non_code)
        self.assertIsNone(non_code["mainDirectory"])

    def test_missing_or_out_of_bounds_repository_requires_explicit_non_code_opt_out(self):
        deep = self.root / "one" / "two" / "three" / "four" / "repository"
        deep.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(deep)], check=True)
        project = {**self.project, "mainDirectory": str(self.root)}
        self.picker.initialize_project_home(project)
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "No Git repository was detected"):
                self.picker.create_stream(project, {"version": 1, "streams": []}, "Unbound")
            non_code = self.picker.create_stream(project, {"version": 1, "streams": []}, "Writing", use_worktree=False)
        self.assertNotIn("worktree", non_code)

    def test_root_repository_with_nested_repository_is_not_treated_as_unambiguous(self):
        root_repository = self.make_git_repository("root-repository")
        nested_parent = root_repository / "components"
        nested_parent.mkdir()
        nested = nested_parent / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        (nested / "README.md").write_text("nested\n")
        subprocess.run(["git", "-C", str(nested), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(nested), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "nested"], check=True)
        project = {**self.project, "mainDirectory": str(root_repository)}
        self.picker.initialize_project_home(project)
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "multiple Git repositories"):
                self.picker.create_stream(project, {"version": 1, "streams": []}, "Ambiguous")

    def test_concurrent_stream_registration_serializes_registry_updates(self):
        self.picker.initialize_project_home(self.project)
        self.picker.ensure_directory(self.picker.DATA_ROOT)
        self.picker.write_json_atomic(self.picker.REGISTRY_PATH, {"version": 1, "projects": [self.project]})

        def create(name):
            registry = {"version": 1, "streams": []}
            return self.picker.create_stream(self.project, registry, name, use_worktree=False)

        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False), \
             ThreadPoolExecutor(max_workers=2) as executor:
            streams = list(executor.map(create, ["First", "Second"]))
        saved = __import__("json").loads((self.picker.project_home(self.project) / "streams.json").read_text())
        self.assertEqual({stream["name"] for stream in saved["streams"]}, {"First", "Second"})
        self.assertEqual({stream["id"] for stream in streams}, {stream["id"] for stream in saved["streams"]})

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
            stream = self.picker.create_stream(self.project, registry, "Committed Stream", use_worktree=False)
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
             mock.patch.object(self.picker, "workspace_clients", side_effect=[[client], [], [], [browser_client], [], []]), \
             mock.patch.object(self.picker, "write_json_atomic") as write:
            self.picker.close_stream(self.project, stream, session)
        self.assertEqual(session["openWorkspaces"], [])
        self.assertIn([self.picker.PROJECT_SNAPSHOT, "--project-id", self.project["id"], "--stream-id", stream["id"]], commands)
        self.assertIn([self.picker.HYPRCTL, "dispatch", "closewindow", "address:0xabc"], commands)
        self.assertIn([self.picker.HYPRCTL, "dispatch", "closewindow", "address:0xdef"], commands)
        write.assert_called_once()

    def test_close_pauses_captured_pi_and_resumes_it_when_revalidation_refuses(self):
        stream = {"id": str(uuid.uuid4()), "name": "Focused Work"}
        scope = self.picker.stream_scope(self.project, stream)
        session = {"version": 2, "hyprlandInstance": "test-instance", "openWorkspaces": [scope]}
        success = mock.Mock(returncode=0, stdout="snapshot\n", stderr="")
        refused = mock.Mock(returncode=1, stdout="", stderr="Pi is still working")
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=True), \
             mock.patch.object(self.picker, "run", side_effect=[success, refused]), \
             mock.patch.object(self.picker, "captured_pi_processes", return_value=[{"pid": 4242, "startTime": "123"}]), \
             mock.patch.object(self.picker, "process_start_time", return_value="123"), \
             mock.patch.object(self.picker, "request_pi_quiescence", return_value=[]), \
             mock.patch.object(self.picker.os, "pidfd_open", return_value=99) as pidfd_open, \
             mock.patch.object(self.picker.signal, "pidfd_send_signal") as send_signal, \
             mock.patch.object(self.picker.os, "close") as close_fd, \
             mock.patch.object(self.picker, "workspace_clients") as clients:
            with self.assertRaisesRegex(RuntimeError, "Pi is still working"):
                self.picker.close_workspace(self.project, session, stream)
        pidfd_open.assert_called_once_with(4242)
        self.assertEqual(send_signal.call_args_list, [
            mock.call(99, self.picker.signal.SIGSTOP),
            mock.call(99, self.picker.signal.SIGCONT),
        ])
        close_fd.assert_called_once_with(99)
        clients.assert_not_called()
        self.assertEqual(session["openWorkspaces"], [scope])

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

    def test_archive_stream_retains_managed_worktree_branch_and_uncommitted_files(self):
        repository = self.make_git_repository()
        project = {**self.project, "mainDirectory": str(repository)}
        self.picker.initialize_project_home(project)
        with mock.patch.object(self.picker, "live_workspace_exists", return_value=False):
            stream = self.picker.create_stream(project, {"version": 1, "streams": []}, "Focused Work")
        self.picker.prepare_stream_worktree(project, stream)
        directory = Path(stream["mainDirectory"])
        (directory / "uncommitted.txt").write_text("keep me\n")
        stream_registry = {"version": 1, "streams": [stream]}
        with mock.patch.object(self.picker, "close_stream"), \
             mock.patch.object(self.picker, "write_json_atomic"):
            self.picker.archive_stream(project, stream, stream_registry, self.session)
        self.assertTrue(directory.is_dir())
        self.assertEqual((directory / "uncommitted.txt").read_text(), "keep me\n")
        branch = stream["worktree"]["branch"]
        self.assertEqual(subprocess.run(["git", "-C", str(repository), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode, 0)
        self.assertIsNotNone(stream["archivedAt"])

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
