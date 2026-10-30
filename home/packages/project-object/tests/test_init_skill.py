import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / "integrations" / "pi" / "skills" / "init" / "scripts" / "mark.py"


class InitSkillTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.project_id = str(uuid.uuid4())
        self.stream_id = str(uuid.uuid4())
        self.project_home = self.data / "projects" / self.project_id
        self.home = self.project_home / "streams" / self.stream_id
        self.home.mkdir(parents=True)
        (self.home / "plans").mkdir()
        (self.home / "worklogs").mkdir()
        (self.home / "AGENTS.md").write_text("# Stream guide\n\n## Scope\n\nExisting guidance.\n")
        (self.home / "NOTES.md").write_text("# Notes\n\nExisting notes.\n")
        (self.home / "TODO.md").write_text("# Todo\n\n## Now\n\n- Existing task\n\n## Next\n\n## Waiting\n")
        (self.home / "worklogs" / "events.jsonl").write_text('{"type":"start"}\n')

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return {
            **os.environ,
            "PROJECT_OBJECT_DATA_DIR": str(self.data),
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_HOME": str(self.project_home),
            "PROJECT_OBJECT_STREAM_ID": self.stream_id,
            "PROJECT_OBJECT_STREAM_HOME": str(self.home),
        }

    def run_marker(self, environment=None):
        return subprocess.run(
            ["python3", str(MARKER)],
            env=environment or self.environment(),
            text=True,
            capture_output=True,
        )

    def test_stream_with_existing_material_can_be_marked_once(self):
        marked = self.run_marker()
        self.assertEqual(marked.returncode, 0, marked.stderr)
        marker = self.home / ".project-object-initialized.json"
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        value = json.loads(marker.read_text())
        self.assertEqual(value["streamId"], self.stream_id)
        self.assertEqual(value["scope"], "stream")

        repeated = self.run_marker()
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("already been initialized", repeated.stderr)

    def test_project_with_existing_material_can_be_marked(self):
        self.project_home.mkdir(exist_ok=True)
        environment = self.environment()
        environment.pop("PROJECT_OBJECT_STREAM_ID")
        environment.pop("PROJECT_OBJECT_STREAM_HOME")

        marked = self.run_marker(environment)
        self.assertEqual(marked.returncode, 0, marked.stderr)
        marker = json.loads((self.project_home / ".project-object-initialized.json").read_text())
        self.assertEqual(marker["scope"], "project")
        self.assertNotIn("streamId", marker)

    def test_requires_canonical_attached_stream_home(self):
        environment = self.environment()
        environment["PROJECT_OBJECT_STREAM_HOME"] = str(self.root / "wrong")
        result = self.run_marker(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical UUID path", result.stderr)
        self.assertFalse((self.home / ".project-object-initialized.json").exists())

    def test_refuses_unsafe_existing_marker(self):
        target = self.root / "marker-target"
        target.write_text("keep\n")
        (self.home / ".project-object-initialized.json").symlink_to(target)
        result = self.run_marker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("marker is unsafe", result.stderr)
        self.assertEqual(target.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main()
