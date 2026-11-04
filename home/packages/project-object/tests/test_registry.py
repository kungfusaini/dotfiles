import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from project_object import (
    AtomicWriteCommittedError,
    RegistryError,
    ensure_private_directory,
    fuzzy_directory_matches,
    fuzzy_directory_score,
    project_home,
    project_session_directory,
    read_registry,
    read_stream_registry,
    read_stream_registry_view,
    stream_home,
    stream_session_directory,
    stream_workspace_name,
    validate_registry,
    validate_stream_registry,
    verify_worktree_checkout,
    write_json_atomic,
)


class DirectoryMatchingTests(unittest.TestCase):
    def setUp(self):
        self.home = Path("/home/test")
        self.candidates = [
            "/home/test/matrix/projects/elijah",
            "/home/test/.config/nixos",
            "/home/test/matrix/projects/project-object",
            "/home/test/Documents/objects",
        ]

    def test_path_fragments_rank_the_intended_directory_first(self):
        matches = fuzzy_directory_matches("mat proj obj", self.candidates, home=self.home)
        self.assertEqual(matches[0], "/home/test/matrix/projects/project-object")

    def test_tilde_queries_and_exact_paths_are_supported(self):
        self.assertEqual(
            fuzzy_directory_matches("~/.config/nixos", self.candidates, home=self.home)[0],
            "/home/test/.config/nixos",
        )
        self.assertLess(
            fuzzy_directory_score("/home/test/.config/nixos", "/home/test/.config/nixos", home=self.home),
            fuzzy_directory_score("nixos", "/home/test/.config/nixos", home=self.home),
        )

    def test_non_matches_are_removed_and_duplicates_are_collapsed(self):
        matches = fuzzy_directory_matches("elijah", self.candidates + [self.candidates[0]], limit=2, home=self.home)
        self.assertEqual(matches, ["/home/test/matrix/projects/elijah"])
        self.assertEqual(fuzzy_directory_matches("not-present", self.candidates, home=self.home), [])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.project_id = str(uuid.uuid4())
        self.base = {
            "version": 1,
            "projects": [{
                "id": self.project_id,
                "name": "Alpha",
                "mainDirectory": str(self.root.resolve()),
                "archivedAt": None,
            }],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_valid_registry_and_legacy_canonical_home_migration(self):
        self.base["projects"][0]["projectHome"] = str(self.data / "projects" / self.project_id)
        registry, changed = validate_registry(self.base, self.data)
        self.assertTrue(changed)
        self.assertNotIn("projectHome", registry["projects"][0])

    def test_rejects_invalid_uuid_duplicate_id_and_duplicate_normalized_name(self):
        invalid = json.loads(json.dumps(self.base))
        invalid["projects"][0]["id"] = "../../escape"
        with self.assertRaises(RegistryError):
            validate_registry(invalid, self.data)

        duplicate_id = json.loads(json.dumps(self.base))
        duplicate_id["projects"].append({**duplicate_id["projects"][0], "name": "Beta"})
        with self.assertRaisesRegex(RegistryError, "Duplicate project ID"):
            validate_registry(duplicate_id, self.data)

        duplicate_name = json.loads(json.dumps(self.base))
        duplicate_name["projects"].append({**duplicate_name["projects"][0], "id": str(uuid.uuid4()), "name": "ALPHA"})
        with self.assertRaisesRegex(RegistryError, "Duplicate normalized project name"):
            validate_registry(duplicate_name, self.data)

        unicode_duplicate = json.loads(json.dumps(self.base))
        unicode_duplicate["projects"][0]["name"] = "Kelvin"
        unicode_duplicate["projects"].append({**unicode_duplicate["projects"][0], "id": str(uuid.uuid4()), "name": "kelvin"})
        with self.assertRaisesRegex(RegistryError, "Duplicate normalized project name"):
            validate_registry(unicode_duplicate, self.data)

    def test_rejects_noncanonical_project_home(self):
        self.base["projects"][0]["projectHome"] = str(self.root / "outside")
        with self.assertRaisesRegex(RegistryError, "unsafe non-canonical projectHome"):
            validate_registry(self.base, self.data)

    def test_symlink_escape_is_rejected_for_derived_paths(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.data / "projects").mkdir(parents=True)
        (self.data / "projects" / self.project_id).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RegistryError):
            project_home(self.data, self.project_id)

    def test_symlink_alias_to_another_project_is_rejected(self):
        other_id = str(uuid.uuid4())
        (self.data / "projects" / other_id).mkdir(parents=True)
        (self.data / "projects" / self.project_id).symlink_to(self.data / "projects" / other_id, target_is_directory=True)
        with self.assertRaisesRegex(RegistryError, "symlinked managed component"):
            project_home(self.data, self.project_id)

        state_projects = self.root / "state" / "projects"
        (state_projects / other_id).mkdir(parents=True)
        (state_projects / self.project_id).symlink_to(state_projects / other_id, target_is_directory=True)
        with self.assertRaisesRegex(RegistryError, "symlinked managed component"):
            project_session_directory(self.root / "state", self.project_id)

    def test_archived_explicit_projects_are_not_resolved(self):
        from project_object import find_project
        self.base["projects"][0]["archivedAt"] = "2026-01-01T00:00:00Z"
        registry, _ = validate_registry(self.base, self.data)
        self.assertIsNone(find_project(registry, project_id=self.project_id))

    def test_atomic_json_and_directories_are_private(self):
        directory = self.root / "private"
        ensure_private_directory(directory)
        target = directory / "state.json"
        write_json_atomic(target, {"ok": True})
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(target.read_text()), {"ok": True})

    def test_session_path_is_uuid_scoped(self):
        expected = self.root / "state" / "projects" / self.project_id / "pi-sessions"
        self.assertEqual(project_session_directory(self.root / "state", self.project_id), expected)

    def test_stream_registry_and_derived_paths(self):
        project = self.base["projects"][0]
        stream_id = str(uuid.uuid4())
        streams = {
            "version": 1,
            "streams": [{
                "id": stream_id,
                "name": "Focused Work",
                "mainDirectory": None,
                "archivedAt": None,
            }],
        }
        validated = validate_stream_registry(streams, self.data, project)
        self.assertEqual(validated["streams"][0]["id"], stream_id)
        self.assertEqual(stream_home(self.data, self.project_id, stream_id), self.data / "projects" / self.project_id / "streams" / stream_id)
        self.assertEqual(stream_session_directory(self.root / "state", self.project_id, stream_id), self.root / "state" / "projects" / self.project_id / "streams" / stream_id / "pi-sessions")
        self.assertEqual(stream_workspace_name("Alpha", "Focused Work"), "Alpha · Focused Work")

    def test_stream_registry_validates_managed_worktree_identity(self):
        project = self.base["projects"][0]
        stream_id = str(uuid.uuid4())
        directory = str((self.data / "worktrees" / self.project_id / stream_id).resolve())
        stream = {
            "id": stream_id,
            "name": "Focused Work",
            "mainDirectory": directory,
            "worktree": {
                "repository": str(self.root.resolve()),
                "directory": directory,
                "branch": f"project-object/{stream_id}",
                "baseCommit": "a" * 40,
            },
            "archivedAt": None,
        }
        validated = validate_stream_registry({"version": 1, "streams": [stream]}, self.data, project)
        self.assertEqual(validated["streams"][0]["worktree"]["directory"], directory)
        stream["worktree"]["directory"] = str(self.root / "elsewhere")
        with self.assertRaisesRegex(RegistryError, "invalid worktree directory"):
            validate_stream_registry({"version": 1, "streams": [stream]}, self.data, project)

    def test_prepared_worktree_allows_branch_changes_but_rejects_unsafe_identity(self):
        repository = self.root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        (repository / "README.md").write_text("initial\n")
        subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "initial"], check=True)
        branch = f"project-object/{uuid.uuid4()}"
        directory = self.root / "worktree"
        subprocess.run(["git", "-C", str(repository), "worktree", "add", "-qb", branch, str(directory), "HEAD"], check=True)
        worktree = {"repository": str(repository), "directory": str(directory), "branch": branch, "baseCommit": "a" * 40}
        verify_worktree_checkout(worktree)

        subprocess.run(["git", "-C", str(directory), "switch", "-qc", "feature/work"], check=True)
        (directory / "README.md").write_text("uncommitted work\n")
        (directory / "untracked.txt").write_text("keep me\n")
        before = subprocess.check_output(["git", "-C", str(directory), "status", "--porcelain"])
        verify_worktree_checkout(worktree)
        subprocess.run(["git", "-C", str(directory), "branch", "-m", "feature/renamed"], check=True)
        verify_worktree_checkout(worktree)
        subprocess.run(["git", "-C", str(directory), "switch", "-q", "--detach"], check=True)
        verify_worktree_checkout(worktree)
        self.assertEqual(subprocess.check_output(["git", "-C", str(directory), "status", "--porcelain"]), before)
        self.assertEqual((directory / "README.md").read_text(), "uncommitted work\n")
        self.assertEqual((directory / "untracked.txt").read_text(), "keep me\n")
        (directory / "subdirectory").mkdir()
        with self.assertRaisesRegex(RegistryError, "unexpected checkout"):
            verify_worktree_checkout({**worktree, "directory": str(directory / "subdirectory")})
        subprocess.run(["git", "-C", str(directory), "switch", "-q", branch], check=True)

        other = self.root / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        with self.assertRaisesRegex(RegistryError, "different Git repository"):
            verify_worktree_checkout({**worktree, "repository": str(other)})

        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(RegistryError):
            verify_worktree_checkout({**worktree, "directory": str(empty)})
        symlink = self.root / "symlink"
        symlink.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(RegistryError, "not a safe prepared directory"):
            verify_worktree_checkout({**worktree, "directory": str(symlink)})

    def test_stream_registry_rejects_duplicates_and_symlink_escape(self):
        project = self.base["projects"][0]
        stream_id = str(uuid.uuid4())
        duplicate = {
            "version": 1,
            "streams": [
                {"id": stream_id, "name": "Work"},
                {"id": str(uuid.uuid4()), "name": "WORK"},
            ],
        }
        with self.assertRaisesRegex(RegistryError, "Duplicate normalized stream name"):
            validate_stream_registry(duplicate, self.data, project)

        outside = self.root / "outside-stream"
        outside.mkdir()
        streams_root = self.data / "projects" / self.project_id / "streams"
        streams_root.mkdir(parents=True)
        (streams_root / stream_id).symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RegistryError, "symlinked managed component"):
            stream_home(self.data, self.project_id, stream_id)

    def test_stream_discovery_quarantines_invalid_records_without_writing(self):
        project = self.base["projects"][0]
        home = project_home(self.data, self.project_id)
        home.mkdir(parents=True)
        path = home / "streams.json"
        healthy = {"id": str(uuid.uuid4()), "name": "Healthy"}
        broken = {"id": str(uuid.uuid4()), "name": "UI Development", "worktree": {}}
        value = {"version": 1, "streams": [healthy, broken]}
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        view = read_stream_registry_view(self.data, project)
        self.assertEqual(view["streams"], [healthy])
        self.assertEqual(len(view["errors"]), 1)
        self.assertIn("UI Development", view["errors"][0])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(RegistryError):
            read_stream_registry(self.data, project)

        value["streams"].append({"id": healthy["id"], "name": "Duplicate"})
        path.write_text(json.dumps(value))
        view = read_stream_registry_view(self.data, project)
        self.assertEqual(view["streams"], [])
        self.assertEqual(len(view["errors"]), 3)

        value = {"version": 1, "streams": [healthy, {"id": str(uuid.uuid4()), "name": "NUL path", "mainDirectory": "/tmp/bad\u0000path"}]}
        path.write_text(json.dumps(value))
        view = read_stream_registry_view(self.data, project)
        self.assertEqual(view["streams"], [healthy])
        self.assertIn("NUL path", view["errors"][0])
        value["streams"] = [healthy, {"id": str(uuid.uuid4()), "name": "Broken\ud800"}]
        path.write_text(json.dumps(value))
        view = read_stream_registry_view(self.data, project)
        self.assertEqual(view["streams"], [healthy])
        self.assertIn(r"Broken\ud800", view["errors"][0])
        view["errors"][0].encode("utf-8")  # Safe to pass to GTK labels/tooltips.
        path.write_bytes(b"\xff\xfe")
        view = read_stream_registry_view(self.data, project)
        self.assertEqual(view["streams"], [])
        self.assertIn("Cannot read", view["errors"][0])

        path.write_text("{broken json")
        self.assertEqual(read_stream_registry_view(self.data, project)["streams"], [])
        self.assertIn("Cannot read", read_stream_registry_view(self.data, project)["errors"][0])
        outside = self.root / "outside.json"
        outside.write_text(json.dumps({"version": 1, "streams": [healthy]}))
        path.unlink()
        path.symlink_to(outside)
        self.assertEqual(read_stream_registry_view(self.data, project)["streams"], [])
        self.assertIn("Unsafe stream registry", read_stream_registry_view(self.data, project)["errors"][0])

    def test_missing_stream_registry_is_empty(self):
        project = self.base["projects"][0]
        self.assertEqual(read_stream_registry(self.data, project), {"version": 1, "streams": []})

    def test_post_commit_fsync_failure_is_explicit_and_does_not_remove_file(self):
        target = self.root / "state.json"
        real_fsync = __import__("os").fsync
        calls = 0
        def fail_parent_fsync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated parent fsync failure")
            return real_fsync(descriptor)
        with mock.patch("project_object.os.fsync", side_effect=fail_parent_fsync):
            with self.assertRaises(AtomicWriteCommittedError):
                write_json_atomic(target, {"committed": True})
        self.assertEqual(json.loads(target.read_text()), {"committed": True})

    def test_malformed_json_is_reported(self):
        self.data.mkdir()
        registry = self.data / "projects.json"
        registry.write_text("{")
        with self.assertRaisesRegex(RegistryError, "Cannot read"):
            read_registry(registry, self.data)


if __name__ == "__main__":
    unittest.main()
