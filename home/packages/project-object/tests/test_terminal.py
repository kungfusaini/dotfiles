import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ROOT / "bin" / "project-terminal"


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.main = self.root / "working directory"
        self.main.mkdir()
        self.project_id = str(uuid.uuid4())
        self.registry = {
            "version": 1,
            "projects": [{
                "id": self.project_id,
                "name": "Project With Spaces",
                "mainDirectory": str(self.main),
                "archivedAt": None,
            }],
        }
        self.data.mkdir()
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        self.capture = self.root / "capture.json"
        self.fake_kitty = self.root / "kitty"
        self.fake_kitty.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
keys = ('PROJECT_OBJECT_ID','PROJECT_OBJECT_NAME','PROJECT_OBJECT_HOME','PROJECT_OBJECT_MAIN_DIRECTORY','PROJECT_OBJECT_STREAM_ID','PROJECT_OBJECT_STREAM_NAME','PROJECT_OBJECT_STREAM_HOME','PI_CODING_AGENT_SESSION_DIR')
Path(os.environ['CAPTURE']).write_text(json.dumps({'argv': sys.argv[1:], 'env': {key: os.environ.get(key) for key in keys}}))
""")
        self.fake_kitty.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return {
            **os.environ,
            "PROJECT_OBJECT_DATA_DIR": str(self.data),
            "PROJECT_OBJECT_STATE_DIR": str(self.state),
            "PROJECT_PICKER_KITTY": str(self.fake_kitty),
            "CAPTURE": str(self.capture),
        }

    def test_project_environment_and_private_session_tree(self):
        subprocess.run([str(TERMINAL), "--project-id", self.project_id, "-e", "pi"], env=self.environment(), check=True)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured["env"]["PROJECT_OBJECT_ID"], self.project_id)
        self.assertEqual(captured["env"]["PROJECT_OBJECT_NAME"], "Project With Spaces")
        self.assertEqual(captured["env"]["PROJECT_OBJECT_MAIN_DIRECTORY"], str(self.main))
        self.assertEqual(captured["argv"][:2], ["--directory", str(self.main)])
        self.assertIn(["--override", "confirm_os_window_close=0"], [captured["argv"][index:index + 2] for index in range(len(captured["argv"]) - 1)])
        session = Path(captured["env"]["PI_CODING_AGENT_SESSION_DIR"])
        self.assertTrue(session.is_dir())
        for directory in (self.state, self.state / "projects", self.state / "projects" / self.project_id, session):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_stream_environment_and_session_isolation(self):
        stream_id = str(uuid.uuid4())
        stream_home = self.data / "projects" / self.project_id / "streams"
        stream_home.mkdir(parents=True)
        (self.data / "projects" / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused Work", "mainDirectory": None, "archivedAt": None}],
        }))
        subprocess.run([str(TERMINAL), "--project-id", self.project_id, "--stream-id", stream_id, "-e", "pi"], env=self.environment(), check=True)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured["env"]["PROJECT_OBJECT_STREAM_ID"], stream_id)
        self.assertEqual(captured["env"]["PROJECT_OBJECT_STREAM_NAME"], "Focused Work")
        self.assertEqual(captured["argv"][:2], ["--directory", str(self.main)])
        self.assertIn(f"/streams/{stream_id}/pi-sessions", captured["env"]["PI_CODING_AGENT_SESSION_DIR"])
        self.assertNotEqual(captured["env"]["PI_CODING_AGENT_SESSION_DIR"], str(self.state / "projects" / self.project_id / "pi-sessions"))

    def test_two_projects_sharing_directory_get_distinct_sessions(self):
        second_id = str(uuid.uuid4())
        self.registry["projects"].append({**self.registry["projects"][0], "id": second_id, "name": "Second"})
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        subprocess.run([str(TERMINAL), "--project-id", self.project_id], env=self.environment(), check=True)
        first = json.loads(self.capture.read_text())["env"]["PI_CODING_AGENT_SESSION_DIR"]
        subprocess.run([str(TERMINAL), "--project-id", second_id], env=self.environment(), check=True)
        second = json.loads(self.capture.read_text())["env"]["PI_CODING_AGENT_SESSION_DIR"]
        self.assertNotEqual(first, second)

    def test_ambiguous_workspace_falls_back_without_attaching_context(self):
        stream_id = str(uuid.uuid4())
        colliding_id = str(uuid.uuid4())
        self.registry["projects"].append({
            "id": colliding_id,
            "name": "Project With Spaces · Focused Work",
            "mainDirectory": str(self.main),
            "archivedAt": None,
        })
        project_home = self.data / "projects" / self.project_id
        project_home.mkdir(parents=True)
        (project_home / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused Work", "mainDirectory": None, "archivedAt": None}],
        }))
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        hyprctl = self.root / "hyprctl"
        hyprctl.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({'name':'Project With Spaces · Focused Work'}))
""")
        hyprctl.chmod(0o755)
        environment = self.environment()
        environment["PROJECT_PICKER_HYPRCTL"] = str(hyprctl)
        result = subprocess.run([str(TERMINAL)], env=environment, text=True, capture_output=True, check=True)
        captured = json.loads(self.capture.read_text())
        self.assertIn("Ambiguous project or stream workspace name", result.stderr)
        self.assertIsNone(captured["env"]["PROJECT_OBJECT_ID"])
        self.assertIsNone(captured["env"]["PROJECT_OBJECT_STREAM_ID"])
        self.assertNotIn("confirm_os_window_close=0", captured["argv"])

    def test_project_browser_workspace_inherits_project_context(self):
        hyprctl = self.root / "hyprctl"
        hyprctl.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({'name':'Project With Spaces · Browser'}))
""")
        hyprctl.chmod(0o755)
        environment = self.environment()
        environment["PROJECT_PICKER_HYPRCTL"] = str(hyprctl)
        subprocess.run([str(TERMINAL)], env=environment, check=True)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured["env"]["PROJECT_OBJECT_ID"], self.project_id)
        self.assertIsNone(captured["env"]["PROJECT_OBJECT_STREAM_ID"])

    def test_archived_explicit_id_is_rejected(self):
        self.registry["projects"][0]["archivedAt"] = "2026-01-01T00:00:00Z"
        (self.data / "projects.json").write_text(json.dumps(self.registry))
        result = subprocess.run([str(TERMINAL), "--project-id", self.project_id], env=self.environment(), text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_malformed_registry_falls_back_to_generic_terminal(self):
        (self.data / "projects.json").write_text("{")
        environment = self.environment()
        for variable in (
            "PROJECT_OBJECT_ID",
            "PROJECT_OBJECT_NAME",
            "PROJECT_OBJECT_HOME",
            "PROJECT_OBJECT_MAIN_DIRECTORY",
            "PROJECT_OBJECT_STREAM_ID",
            "PROJECT_OBJECT_STREAM_NAME",
            "PROJECT_OBJECT_STREAM_HOME",
            "PI_CODING_AGENT_SESSION_DIR",
        ):
            environment[variable] = "inherited-project-value"
        subprocess.run([str(TERMINAL), "--title", "generic"], env=environment, check=True)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured["argv"], ["--title", "generic"])
        self.assertTrue(all(value is None for value in captured["env"].values()))


if __name__ == "__main__":
    unittest.main()
