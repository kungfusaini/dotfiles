import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "integrations" / "pi" / "skills" / "init" / "scripts" / "guard.py"


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
        (self.home / "AGENTS.md").write_text("# Stream guide\n\n## Scope\n\n<!-- project-object:init-scope -->\n")
        (self.home / "NOTES.md").write_text("# Notes\n")
        (self.home / "TODO.md").write_text("# Todo\n\n## Now\n\n## Next\n\n## Waiting\n")

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

    def run_guard(self, action):
        return subprocess.run(["python3", str(GUARD), action], env=self.environment(), text=True, capture_output=True)

    def test_pristine_stream_can_be_marked_once_after_minimal_artifacts(self):
        checked = self.run_guard("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["state"], "pristine")

        incomplete = self.run_guard("mark")
        self.assertNotEqual(incomplete.returncode, 0)
        self.assertIn("incomplete initialization", incomplete.stderr)

        (self.home / "AGENTS.md").write_text("# Stream guide\n\n## Scope\n\nInspect the current system without changing external services.\n")
        (self.home / "TODO.md").write_text("# Todo\n\n## Now\n\n- [ ] Inspect the current system\n\n## Next\n\n## Waiting\n")
        marked = self.run_guard("mark")
        self.assertEqual(marked.returncode, 0, marked.stderr)
        marker = self.home / ".project-object-initialized.json"
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(marker.read_text())["streamId"], self.stream_id)

        repeated = self.run_guard("check")
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("already been initialized", repeated.stderr)

    def test_pristine_project_can_be_initialized(self):
        for directory in ("plans", "worklogs"):
            (self.project_home / directory).mkdir(exist_ok=True)
        (self.project_home / "AGENTS.md").write_text("# Project guide\n\n## Scope\n\n<!-- project-object:init-scope -->\n")
        (self.project_home / "NOTES.md").write_text("# Notes\n")
        (self.project_home / "TODO.md").write_text("# Todo\n\n## Now\n\n## Next\n\n## Waiting\n")
        environment = self.environment()
        environment.pop("PROJECT_OBJECT_STREAM_ID")
        environment.pop("PROJECT_OBJECT_STREAM_HOME")

        checked = subprocess.run(["python3", str(GUARD), "check"], env=environment, text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["scope"], "project")

        (self.project_home / "AGENTS.md").write_text("# Project guide\n\n## Scope\n\nCoordinate the system.\n")
        (self.project_home / "TODO.md").write_text("# Todo\n\n## Now\n\n- [ ] Inspect the system\n\n## Next\n\n## Waiting\n")
        marked = subprocess.run(["python3", str(GUARD), "mark"], env=environment, text=True, capture_output=True)
        self.assertEqual(marked.returncode, 0, marked.stderr)
        marker = json.loads((self.project_home / ".project-object-initialized.json").read_text())
        self.assertEqual(marker["scope"], "project")
        self.assertNotIn("streamId", marker)

    def test_populated_stream_without_marker_is_not_overwritten(self):
        (self.home / "AGENTS.md").write_text("# Stream guide\n\n## Scope\n\nExisting work.\n")
        result = self.run_guard("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already contains initialized stream scope", result.stderr)
        self.assertFalse((self.home / ".project-object-initialized.json").exists())

    def test_requires_canonical_attached_stream_home(self):
        environment = self.environment()
        environment["PROJECT_OBJECT_STREAM_HOME"] = str(self.root / "wrong")
        result = subprocess.run(["python3", str(GUARD), "check"], env=environment, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical UUID path", result.stderr)


if __name__ == "__main__":
    unittest.main()
