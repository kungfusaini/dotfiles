import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from update_check import check, fetch_release, version


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "longshot_version.txt").write_text("version=v3.2.0\nsource=example\n")
        self.state = self.root / "state"
        self.requests = 0
        self.notifications = []

    def run_check(self, tag="v3.3.0", now=100000, fetch=None, send=None):
        def request():
            self.requests += 1
            return tag
        check(self.game, self.state, now=now, fetch=fetch or request,
              send=send or self.notifications.append)

    def test_fetch_is_bounded_ipv4_and_validates_release(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"tag_name": "v3.3.0", "prerelease": False}))
        with patch("update_check.subprocess.run", return_value=result) as run:
            self.assertEqual(fetch_release(), "v3.3.0")
            args, options = run.call_args
            self.assertIn("--ipv4", args[0])
            self.assertIn("--max-time", args[0])
            self.assertEqual(options["timeout"], 10)
        result.stdout = json.dumps({"tag_name": "v3.3.0", "prerelease": True})
        with patch("update_check.subprocess.run", return_value=result), self.assertRaises(ValueError):
            fetch_release()

    def test_current_and_older_do_not_notify(self):
        self.run_check("v3.2.0")
        self.run_check("v3.1.9", now=200000)
        self.assertEqual(self.notifications, [])

    def test_numeric_versions_and_once_per_release(self):
        self.run_check("v3.10.0")
        self.run_check("v3.10.0", now=100001)
        self.assertEqual(self.requests, 1)
        self.run_check("v3.10.0", now=200000)
        self.assertEqual(self.notifications, ["v3.10.0"])
        self.run_check("v3.11.0", now=300000)
        self.assertEqual(self.notifications, ["v3.10.0", "v3.11.0"])
        self.assertEqual((self.state / "state.json").stat().st_mode & 0o777, 0o600)

    def test_release_withdrawal_does_not_repeat_notification(self):
        self.run_check("v3.3.0")
        self.run_check("v3.4.0", now=200000)
        self.run_check("v3.3.0", now=300000)
        self.assertEqual(self.notifications, ["v3.3.0", "v3.4.0"])

    def test_offline_attempt_is_throttled(self):
        def offline():
            raise subprocess.CalledProcessError(6, "curl")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_check(fetch=offline)
        self.run_check(now=100001)
        self.assertEqual(self.requests, 0)
        self.assertEqual(self.notifications, [])

    def test_bad_and_nonstable_tags_are_rejected(self):
        for tag in ["v3.3.0-rc.1", "nightly-1", "v3.3.0\nmessage", "v3.3.0; touch /tmp/bad"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                version(tag)

    def test_corrupt_state_and_clock_rollback(self):
        self.state.mkdir()
        (self.state / "state.json").write_text("broken")
        self.run_check()
        self.run_check(now=90000)
        self.assertEqual(self.requests, 2)
        self.assertEqual(self.notifications, ["v3.3.0"])

    def test_notification_failure_is_not_marked_delivered(self):
        def failure(tag):
            raise subprocess.CalledProcessError(1, "notify-send")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_check(send=failure)
        state = json.loads((self.state / "state.json").read_text())
        self.assertNotIn("last_notified", state)
        self.run_check(now=200000)
        self.assertEqual(self.notifications, ["v3.3.0"])

    def test_missing_game_never_fetches(self):
        (self.game / "longshot_version.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_check()
        self.assertEqual(self.requests, 0)

    def test_concurrent_checker_does_not_fetch(self):
        self.state.mkdir()
        with (self.state / "check.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_check()
        self.assertEqual(self.requests, 0)


if __name__ == "__main__":
    unittest.main()
