import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import codex_usage as tracker
import codex_oneshot as one

SESSION = "a" * 32
QUOTA = ("account", "pro", 200000, 604800, 60, 1, 0)


class OneShotTests(unittest.TestCase):
    def test_timer_is_absolute_at_reset_not_before_and_kills_entire_unit(self):
        command = one.timer_command(SESSION, 200000)
        self.assertIn("--on-calendar=@200000", command)
        self.assertIn("--timer-property=AccuracySec=1us", command)
        self.assertIn("--timer-property=WakeSystem=false", command)
        self.assertIn("--signal=SIGKILL", command)
        self.assertIn("--kill-whom=all", command)
        self.assertEqual(command[-1], one.unit_names(SESSION)[0])

    @patch.object(one.time, "time", return_value=100000)
    def test_fresh_quota_rejects_failure_expired_restricted(self, _clock):
        for quota, status in [(None, "network_error"),
                              ((*QUOTA[:2], 99999, *QUOTA[3:]), "ok"),
                              ((*QUOTA[:4], 100, 1, 0), "ok"),
                              ((*QUOTA[:5], 0, 0), "ok"),
                              ((*QUOTA[:6], 1), "ok")]:
            with self.subTest(status=status, quota=quota), patch.object(one, "fetch_quota", return_value=(quota, status)):
                with self.assertRaises(ValueError):
                    one.fresh_quota()
        with patch.object(one, "fetch_quota", return_value=(QUOTA, "ok")):
            self.assertEqual(one.fresh_quota(), ("account", 200000, 60))

    @patch.object(one.time, "time", return_value=100000)
    def test_session_preserves_attachment_without_forwarding_secrets(self, _clock):
        with patch.dict(os.environ, {"PROJECT_OBJECT_STREAM_ID": "stream", "API_KEY": "SECRET",
                                     "PI_CODING_AGENT_SESSION_DIR": "/private/sessions"}, clear=True):
            command = one.session_command(SESSION, "account", 200000, Path("/tmp"))
        self.assertIn("--setenv=PROJECT_OBJECT_STREAM_ID=stream", command)
        self.assertIn("--setenv=PI_CODING_AGENT_SESSION_DIR=/private/sessions", command)
        self.assertNotIn("SECRET", repr(command))
        self.assertIn("--property=Restart=no", command)
        self.assertIn("--property=KillMode=control-group", command)
        self.assertIn("--pty", command)

    @patch.object(one, "cleanup")
    @patch.object(one.subprocess, "run")
    @patch.object(one, "fresh_quota", return_value=("account", 200000, 60))
    def test_timer_armed_before_session_and_cleaned_on_failure(self, _quota, run, cleanup):
        run.side_effect = [Mock(returncode=0), OSError("failed")]
        with patch.object(one.sys.stdin, "isatty", return_value=True), patch.object(one.sys.stdout, "isatty", return_value=True):
            with self.assertRaises(OSError):
                one.launch()
        self.assertTrue(any(c.startswith("--on-calendar=") for c in run.call_args_list[0].args[0]))
        self.assertIn("--pty", run.call_args_list[1].args[0])
        cleanup.assert_called_once()

    @patch.object(one, "cleanup")
    @patch.object(one.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "timer"))
    @patch.object(one, "fresh_quota", return_value=("account", 200000, 60))
    def test_failed_timer_never_starts_pi(self, _quota, run, cleanup):
        with patch.object(one.sys.stdin, "isatty", return_value=True), patch.object(one.sys.stdout, "isatty", return_value=True):
            with self.assertRaises(subprocess.CalledProcessError):
                one.launch()
        self.assertEqual(run.call_count, 1)

    @patch.object(one.subprocess, "run")
    def test_failed_stop_retains_deadline(self, run):
        run.side_effect = [Mock(returncode=1), Mock(returncode=1, stdout="")]
        with self.assertRaises(ValueError):
            one.cleanup(SESSION)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn(".timer", repr(run.call_args_list))

    @patch.object(one.subprocess, "run", return_value=Mock(returncode=0))
    def test_cleanup_stops_session_before_deadline(self, run):
        one.cleanup(SESSION)
        self.assertEqual(run.call_args_list[0].args[0][-1], one.unit_names(SESSION)[0])
        self.assertTrue(run.call_args_list[1].args[0][-2].endswith(".timer"))

    @patch.object(one.os, "execv")
    @patch.object(one.subprocess, "run", return_value=Mock(returncode=0))
    @patch.object(one.time, "time", return_value=100000)
    def test_worker_rechecks_window_account_and_deadline(self, _clock, _run, execute):
        args = argparse.Namespace(session=SESSION, account="account", reset=200000)
        for quota in [("other", 200000, 60), ("account", 200010, 60), ("account", 99999, 60)]:
            with patch.object(one, "fresh_quota", return_value=quota):
                with self.assertRaises(ValueError):
                    one.execute(args)
        execute.assert_not_called()

    @patch.object(one.os, "execv")
    @patch.object(one.subprocess, "run", return_value=Mock(returncode=0))
    @patch.object(one.time, "time", return_value=100000)
    @patch.object(one, "fresh_quota", return_value=("account", 200001, 60))
    def test_worker_accepts_jitter_without_extending_deadline(self, _quota, _clock, _run, execute):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"piBin":"/nix/store/test/bin/pi","model":"gpt-test","thinking":"high"}')
            with patch.object(one, "config_path", return_value=config):
                one.execute(argparse.Namespace(session=SESSION, account="account", reset=200000))
        args = execute.call_args.args[1]
        self.assertIn("--session-id", args)
        self.assertIn(SESSION, args)
        self.assertIn("openai-codex", args)
        self.assertEqual(args[args.index("--model") + 1], "gpt-test")
        self.assertEqual(args[args.index("--thinking") + 1], "high")

    def test_noninteractive_launch_rejected_without_quota_fetch(self):
        with patch.object(one.sys.stdin, "isatty", return_value=False), patch.object(one, "fresh_quota") as quota:
            with self.assertRaises(ValueError):
                one.launch()
            quota.assert_not_called()


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.context = tracker.database(Path(self.tmp.name))
        self.db = self.context.__enter__()
        self.notify = patch.object(tracker.subprocess, "run", return_value=Mock(returncode=0))
        self.run = self.notify.start()

    def tearDown(self):
        self.notify.stop()
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_24h_then_4h_once_with_jitter(self):
        self.assertTrue(tracker.remind(self.db, QUOTA, now=200000-80000))
        self.assertFalse(tracker.remind(self.db, QUOTA, now=200000-70000))
        self.assertTrue(tracker.remind(self.db, QUOTA, now=200000-10000))
        jitter = (*QUOTA[:2], 200001, *QUOTA[3:])
        self.assertFalse(tracker.remind(self.db, jitter, now=200000-9000))
        self.assertFalse(tracker.remind(self.db, QUOTA, now=200000-80000))
        self.assertEqual(self.run.call_count, 2)

    def test_late_first_sample_sends_only_4h(self):
        tracker.remind(self.db, QUOTA, now=199000)
        self.assertIn("Codex reset within 4 hours", self.run.call_args.args[0])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0], 1)

    def test_no_reminder_outside_window_exhausted_or_expired(self):
        for now, used in [(0, 60), (200000, 60), (200001, 60), (199000, 91), (199000, 100)]:
            self.assertFalse(tracker.remind(self.db, (*QUOTA[:4], used, *QUOTA[5:]), now=now))
        self.run.assert_not_called()

    def test_delivery_failure_retried_not_recorded(self):
        self.run.side_effect = subprocess.CalledProcessError(1, "notify-send")
        self.assertFalse(tracker.remind(self.db, QUOTA, now=199000))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0], 0)
        self.run.side_effect = None
        self.assertTrue(tracker.remind(self.db, QUOTA, now=199000))

    def test_other_accounts_and_windows_independent(self):
        self.assertTrue(tracker.remind(self.db, QUOTA, now=199000))
        self.assertTrue(tracker.remind(self.db, ("other", *QUOTA[1:]), now=199000))
        self.assertTrue(tracker.remind(self.db, (*QUOTA[:2], 300000, *QUOTA[3:]), now=299000))


if __name__ == "__main__":
    unittest.main()
