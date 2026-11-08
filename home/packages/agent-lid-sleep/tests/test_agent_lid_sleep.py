import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import agent_lid_sleep as agent


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.pid = os.getpid()
        self.record = dict(version=1, pid=self.pid,
                           processStartTime=agent.process_start_time(self.pid), state="working")
        self.path = self.directory / f"{self.pid}.json"

    def write(self, **changes):
        self.path.write_text(json.dumps(self.record | changes))

    def test_current_process_working_and_idle(self):
        self.write()
        self.assertTrue(agent.agents_working(self.directory))
        self.write(state="idle")
        self.assertFalse(agent.agents_working(self.directory))

    def test_mixed_agents_in_different_projects(self):
        self.write(state="idle", projectId="project-a", streamId=None)
        with subprocess.Popen(["sleep", "60"]) as child:
            try:
                path = self.directory / f"{child.pid}.json"
                path.write_text(json.dumps(self.record | dict(
                    pid=child.pid, processStartTime=agent.process_start_time(child.pid),
                    projectId="project-b", streamId="other-stream")))
                self.assertTrue(agent.agents_working(self.directory))
            finally:
                child.terminate()
                child.wait()
        self.assertFalse(agent.agents_working(self.directory))

    def test_old_timestamp_does_not_expire_a_live_tool_call(self):
        self.write(updatedAt="2000-01-01T00:00:00Z")
        self.assertTrue(agent.agents_working(self.directory))

    def test_stale_pid_birth_time_ignored(self):
        self.write(processStartTime="0")
        self.assertFalse(agent.agents_working(self.directory))

    def test_invalid_shapes_ignored(self):
        for change in (dict(version=2), dict(pid=True), dict(pid=-1), dict(pid=self.pid + 1),
                       dict(state="unknown"), dict(processStartTime=None), dict(processStartTime=1)):
            with self.subTest(change=change):
                self.write(**change)
                self.assertFalse(agent.agents_working(self.directory))
        for value in ([], "text", None, "{", "x" * 17000):
            self.path.write_text(value if isinstance(value, str) else json.dumps(value))
            self.assertFalse(agent.agents_working(self.directory))

    def test_symlink_and_fifo_records_ignored(self):
        self.write()
        other = self.directory / "payload"
        self.path.rename(other)
        self.path.symlink_to(other)
        self.assertFalse(agent.agents_working(self.directory))
        self.path.unlink()
        os.mkfifo(self.path)
        self.assertFalse(agent.agents_working(self.directory))

    def test_missing_directory_is_idle_and_symlink_directory_rejected(self):
        self.assertFalse(agent.agents_working(self.directory / "missing"))
        link = self.directory / "link"
        link.symlink_to(self.directory)
        with self.assertRaises(RuntimeError):
            agent.agents_working(link)

    def test_dead_process_and_zombie_do_not_hold_sleep(self):
        child = subprocess.Popen(["true"])
        try:
            import time
            deadline = time.monotonic() + 3
            while agent.process_start_time(child.pid) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertIsNone(agent.process_start_time(child.pid))
        finally:
            child.wait()
        self.assertIsNone(agent.process_start_time(child.pid))

    def test_process_name_containing_parentheses(self):
        fields = ["S"] + ["0"] * 18 + ["123"]
        with patch.object(Path, "read_text", return_value="99 (weird ) name) " + " ".join(fields)):
            self.assertEqual(agent.process_start_time(99), "123")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.acquired = []
        self.closed = []
        self.guard = agent.LidGuard(self.acquire, self.closed.append)

    def acquire(self):
        fd = 100 + len(self.acquired)
        self.acquired.append(fd)
        return fd

    def test_idle_without_inhibitor_does_nothing(self):
        self.guard.update(False, 0)
        self.guard.update(False, 20)
        self.assertEqual(self.acquired, [])

    def test_working_then_idle_grace_then_release(self):
        self.guard.update(True, 0)
        self.guard.update(True, 1000)
        self.assertEqual(self.acquired, [100])
        self.guard.update(False, 1001)
        self.guard.update(False, 1005.9)
        self.assertEqual(self.closed, [])
        self.guard.update(False, 1006)
        self.assertEqual(self.closed, [100])
        self.guard.update(False, 1007)
        self.assertEqual(self.closed, [100])

    def test_new_work_resets_settle_timer(self):
        for working, now in [(True, 0), (False, 1), (True, 5), (False, 6), (False, 10)]:
            self.guard.update(working, now)
        self.assertEqual(self.closed, [])
        self.guard.update(False, 11)
        self.assertEqual(self.closed, [100])
        self.guard.update(True, 12)
        self.assertEqual(self.acquired, [100, 101])

    def test_shutdown_releases_exact_fd_once(self):
        self.guard.update(True, 0)
        self.guard.release()
        self.guard.release()
        self.assertEqual(self.closed, [100])

    def test_acquisition_error_propagates_for_service_restart(self):
        def fail():
            raise RuntimeError("logind unavailable")
        guard = agent.LidGuard(fail)
        with self.assertRaises(RuntimeError):
            guard.update(True, 0)
        self.assertIsNone(guard.fd)


if __name__ == "__main__":
    unittest.main()
