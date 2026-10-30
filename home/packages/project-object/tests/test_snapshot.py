import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "bin" / "project-snapshot"


def workspace(name="Alpha"):
    return {
        "id": 7,
        "name": name,
        "monitor": "HEADLESS-1",
        "monitorID": 0,
        "windows": 1,
        "hasfullscreen": False,
        "lastwindow": "0xabc",
        "lastwindowtitle": "Project terminal",
    }


def client(name="Alpha", address="0xabc"):
    return {
        "address": address,
        "class": "kitty",
        "initialClass": "kitty",
        "title": "Project terminal",
        "initialTitle": "kitty",
        "pid": 1234,
        "workspace": {"id": 7, "name": name},
        "monitor": 0,
        "at": [100, 200],
        "size": [1200, 800],
        "floating": False,
        "pseudo": None,
        "pinned": False,
        "fullscreen": 0,
        "grouped": [],
        "swallowing": None,
        "focusHistoryID": 0,
        "xwayland": False,
    }


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.fixtures = self.root / "fixtures"
        self.runtime = self.root / "runtime"
        self.fixtures.mkdir()
        self.project_id = str(uuid.uuid4())
        self.project_home = self.data / "projects" / self.project_id
        self.project_home.mkdir(parents=True)
        self.registry = {
            "version": 1,
            "projects": [{
                "id": self.project_id,
                "name": "Alpha",
                "mainDirectory": str(self.root),
                "archivedAt": None,
            }],
        }
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        self.log = self.root / "hyprctl.log"
        self.hyprctl = self.root / "hyprctl"
        self.hyprctl.write_text("""#!/usr/bin/env python3
import os, sys
from pathlib import Path
subject = sys.argv[1]
with Path(os.environ['HYPRCTL_LOG']).open('a') as stream:
    stream.write(' '.join(sys.argv[1:]) + '\\n')
fixture = Path(os.environ['HYPRCTL_FIXTURES']) / f'{subject}.json'
if not fixture.exists():
    print(f'missing fixture: {subject}', file=sys.stderr)
    raise SystemExit(2)
print(fixture.read_text())
""")
        self.hyprctl.chmod(0o755)
        self.write_fixtures()

    def tearDown(self):
        self.temporary.cleanup()

    def write_fixtures(self, *, workspaces=None, clients=None):
        values = {
            "workspaces": workspaces if workspaces is not None else [workspace("Alpha"), workspace("Other")],
            "clients": clients if clients is not None else [client("Alpha", "0xabc"), client("Other", "0xdef")],
            "activeworkspace": {"id": 7, "name": "Alpha"},
            "activewindow": {"address": "0xabc"},
        }
        for subject, value in values.items():
            (self.fixtures / f"{subject}.json").write_text(json.dumps(value))

    def environment(self):
        environment = {
            **os.environ,
            "PROJECT_OBJECT_DATA_DIR": str(self.data),
            "PROJECT_PICKER_HYPRCTL": str(self.hyprctl),
            "PROJECT_OBJECT_RUNTIME_DIR": str(self.runtime),
            "HYPRCTL_FIXTURES": str(self.fixtures),
            "HYPRCTL_LOG": str(self.log),
            "HYPRLAND_INSTANCE_SIGNATURE": "isolated-test-instance",
        }
        environment.pop("PROJECT_OBJECT_ID", None)
        environment.pop("PROJECT_OBJECT_STREAM_ID", None)
        return environment

    def write_activity(self, state="idle", session_id="restore-session-123"):
        directory = self.runtime / "pi-activity"
        directory.mkdir(parents=True, mode=0o700)
        pid = os.getpid()
        kitty_pid = os.getppid()
        stat_fields = (Path("/proc") / str(pid) / "stat").read_text().split(")", 1)[1].split()
        kitty_stat_fields = (Path("/proc") / str(kitty_pid) / "stat").read_text().split(")", 1)[1].split()
        clients = json.loads((self.fixtures / "clients.json").read_text())
        clients[0]["pid"] = kitty_pid
        (self.fixtures / "clients.json").write_text(json.dumps(clients))
        (directory / f"{pid}.json").write_text(json.dumps({
            "version": 1,
            "pid": pid,
            "processStartTime": stat_fields[19],
            "projectId": self.project_id,
            "streamId": None,
            "state": state,
            "sessionId": session_id,
            "kittyPid": kitty_pid,
            "kittyStartTime": kitty_stat_fields[19],
            "kittyWindowId": 17,
        }))

    def run_snapshot(self):
        return subprocess.run(
            [str(SNAPSHOT), "--project-id", self.project_id],
            env=self.environment(),
            text=True,
            capture_output=True,
        )

    def test_captures_only_project_workspace_without_dispatch(self):
        result = self.run_snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.project_home / "snapshots" / "workspace.json"
        self.assertEqual(result.stdout.strip(), str(target))
        snapshot = json.loads(target.read_text())
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["projectId"], self.project_id)
        self.assertEqual(snapshot["hyprlandInstance"], "isolated-test-instance")
        self.assertEqual(snapshot["workspace"]["name"], "Alpha")
        self.assertEqual(snapshot["activeWindowAddress"], "0xabc")
        self.assertEqual([window["address"] for window in snapshot["windows"]], ["0xabc"])
        self.assertEqual(snapshot["windows"][0]["position"], [100, 200])
        self.assertIsNone(snapshot["windows"][0]["pseudo"])
        commands = self.log.read_text().splitlines()
        self.assertEqual(commands, ["workspaces -j", "clients -j", "activeworkspace -j", "activewindow -j"])
        self.assertFalse(any("dispatch" in command for command in commands))
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_captures_exact_idle_pi_session_for_managed_kitty_window(self):
        self.write_activity()
        result = self.run_snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads((self.project_home / "snapshots" / "workspace.json").read_text())
        self.assertEqual(snapshot["windows"][0]["piSessionId"], "restore-session-123")
        self.assertEqual(snapshot["windows"][0]["piSessions"], [{
            "sessionId": "restore-session-123",
            "pid": os.getpid(),
            "startTime": snapshot["windows"][0]["piProcesses"][0]["startTime"],
            "kittyWindowId": 17,
        }])

    def test_refuses_to_close_while_attached_pi_is_working(self):
        self.write_activity(state="working")
        result = self.run_snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pi is still working", result.stderr)
        self.assertFalse((self.project_home / "snapshots" / "workspace.json").exists())

    def test_shared_kitty_process_is_protected_but_not_misattributed_to_os_windows(self):
        self.write_activity()
        clients = json.loads((self.fixtures / "clients.json").read_text())
        duplicate = {**clients[0], "address": "0xabd", "title": "Second Kitty OS window"}
        self.write_fixtures(workspaces=[workspace("Alpha")], clients=[clients[0], duplicate])
        result = self.run_snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads((self.project_home / "snapshots" / "workspace.json").read_text())
        self.assertEqual(len(snapshot["piProcesses"]), 1)
        self.assertEqual(len(snapshot["windows"]), 2)
        self.assertTrue(all("piSessions" not in window for window in snapshot["windows"]))

    def test_shared_kitty_process_across_workspaces_is_not_misattributed(self):
        self.write_activity()
        clients = json.loads((self.fixtures / "clients.json").read_text())
        duplicate = {
            **clients[0],
            "address": "0xabd",
            "title": "Kitty OS window elsewhere",
            "workspace": {"id": 8, "name": "Other"},
        }
        self.write_fixtures(
            workspaces=[workspace("Alpha"), workspace("Other")],
            clients=[clients[0], duplicate],
        )
        result = self.run_snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads((self.project_home / "snapshots" / "workspace.json").read_text())
        self.assertEqual(len(snapshot["windows"]), 1)
        self.assertNotIn("piSessions", snapshot["windows"][0])

    def test_malformed_session_id_still_protects_working_pi(self):
        self.write_activity(state="working", session_id="not a valid session id")
        result = self.run_snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pi is still working", result.stderr)

    def test_ignores_activity_from_a_reused_pid(self):
        self.write_activity()
        target = self.runtime / "pi-activity" / f"{os.getpid()}.json"
        activity = json.loads(target.read_text())
        activity["processStartTime"] = str(int(activity["processStartTime"]) + 1)
        target.write_text(json.dumps(activity))
        result = self.run_snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads((self.project_home / "snapshots" / "workspace.json").read_text())
        self.assertNotIn("piSessionId", snapshot["windows"][0])
        self.assertNotIn("piProcesses", snapshot["windows"][0])

    def test_captures_stream_workspace_into_stream_home(self):
        stream_id = str(uuid.uuid4())
        stream_home = self.project_home / "streams" / stream_id
        stream_home.mkdir(parents=True)
        (self.project_home / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused Work", "mainDirectory": None, "archivedAt": None}],
        }))
        name = "Alpha · Focused Work"
        self.write_fixtures(workspaces=[workspace(name)], clients=[client(name)])
        result = subprocess.run(
            [str(SNAPSHOT), "--project-id", self.project_id, "--stream-id", stream_id],
            env=self.environment(), text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        target = stream_home / "snapshots" / "workspace.json"
        snapshot = json.loads(target.read_text())
        self.assertEqual(snapshot["scope"], "stream")
        self.assertEqual(snapshot["streamId"], stream_id)
        self.assertEqual(snapshot["workspace"]["name"], name)

    def test_missing_live_workspace_does_not_replace_snapshot(self):
        snapshots = self.project_home / "snapshots"
        snapshots.mkdir()
        target = snapshots / "workspace.json"
        target.write_text("previous snapshot\n")
        self.write_fixtures(workspaces=[workspace("Other")], clients=[])
        result = self.run_snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected one live workspace", result.stderr)
        self.assertEqual(target.read_text(), "previous snapshot\n")

    def test_invalid_client_data_does_not_write_snapshot(self):
        invalid = client()
        invalid["size"] = "not-a-pair"
        self.write_fixtures(clients=[invalid])
        result = self.run_snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("client.size", result.stderr)
        self.assertFalse((self.project_home / "snapshots" / "workspace.json").exists())

    def test_symlinked_snapshot_directory_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project_home / "snapshots").symlink_to(outside, target_is_directory=True)
        result = self.run_snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsafe directory", result.stderr)
        self.assertFalse((outside / "workspace.json").exists())


if __name__ == "__main__":
    unittest.main()
