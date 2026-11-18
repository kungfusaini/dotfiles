import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_screen_sleep import SleepRequest, main


class RequestTests(unittest.TestCase):
    def test_unarmed_cannot_sleep(self):
        self.assertFalse(SleepRequest().ready(False, 100))

    def test_five_seconds_and_busy_reset(self):
        request = SleepRequest()
        request.activity("idle")
        self.assertFalse(request.ready(False, 0))
        self.assertFalse(request.ready(False, 4.99))
        self.assertFalse(request.ready(True, 5))
        self.assertFalse(request.ready(False, 6))
        self.assertFalse(request.ready(False, 10.99))
        self.assertTrue(request.ready(False, 11))
        request.submitted = True
        self.assertFalse(request.ready(False, 12))

    def test_active_or_invalid_event_permanently_cancels(self):
        for event in ("active", "garbage", ""):
            request = SleepRequest()
            request.activity("idle")
            request.ready(False, 0)
            request.activity(event)
            request.activity("idle")
            self.assertFalse(request.ready(False, 100))


class RunnerTests(unittest.TestCase):
    """Real GLib/pipe handling, fake Wayland monitor and power/display commands."""
    def run_request(self, body, *, working=False, external_sleep=False, fail_off=False,
                    owner_lost=False, bus_lost=False, input_during_scan=False, reject_off=False):
        import dbus
        from gi.repository import GLib

        calls = []
        receivers = {}
        class Bus:
            def get_name_owner(self, *args):
                return ":1.42"
            def get_is_connected(self):
                return True
            def add_signal_receiver(self, callback, **kwargs):
                name = kwargs["signal_name"]
                receivers[name] = callback
                if external_sleep and name == "PrepareForSleep":
                    GLib.timeout_add(100, lambda: (callback(True), False)[1])
                if owner_lost and name == "NameOwnerChanged":
                    GLib.timeout_add(100, lambda: (callback("org.freedesktop.login1", ":1.42", ""), False)[1])
                if bus_lost and name == "Disconnected":
                    GLib.timeout_add(100, lambda: (callback(), False)[1])
            def remove_signal_receiver(self, *args, **kwargs):
                pass
            def close(self):
                pass

        def run(args, **kwargs):
            calls.append(args)
            if args == ["systemctl", "suspend"]:
                # CLI completion means enqueued, not resumed. The display must
                # remain off until the real logind resume signal arrives.
                callback = receivers["PrepareForSleep"]
                GLib.timeout_add(20, lambda: (callback(True), False)[1])
                def resume():
                    self.assertEqual(calls[-1], ["systemctl", "suspend"])
                    callback(False)
                    return False
                GLib.timeout_add(100, resume)
            if fail_off and args[-1] == "off":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, stdout='refused' if reject_off and args[-1]=='off' else 'ok', stderr='')

        clock = iter(range(0, 1000, 3))
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "helper"
            scan_count = 0
            def scan(_):
                nonlocal scan_count
                scan_count += 1
                if input_during_scan and scan_count == 3:
                    (Path(directory) / "activate").touch()
                    time.sleep(.1)  # Activity arrives while the scan is running.
                return working
            if input_during_scan:
                body = ("import os\nprint('idle', flush=True)\n"
                        f"while not os.path.exists({str(Path(directory) / 'activate')!r}): time.sleep(.005)\n"
                        "print('active', flush=True)\ntime.sleep(10)")
            helper.write_text(f"#!{sys.executable}\nimport time\n{body}\n")
            helper.chmod(0o700)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}), \
                    patch.object(sys, "argv", ["agent-screen-sleep", str(helper)]), \
                    patch.object(dbus, "SystemBus", return_value=Bus()), \
                    patch("agent_screen_sleep.subprocess.run", side_effect=run), \
                    patch("agent_screen_sleep.agents_working", side_effect=scan), \
                    patch("agent_screen_sleep.time.monotonic", side_effect=lambda: next(clock)):
                try:
                    main()
                except SystemExit as error:
                    self.assertEqual(error.code, 1)
        return calls

    def test_input_restores_without_suspending(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(.05)\nprint('active', flush=True)\ntime.sleep(10)")
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_settled_agents_suspend_once_then_restore(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)")
        self.assertEqual([c[-1] for c in calls], ["off", "suspend", "on"])

    def test_busy_agents_wait_until_cancelled(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(.8)\nprint('active', flush=True)\ntime.sleep(10)", working=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_monitor_loss_never_suspends(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(.05)")
        self.assertNotIn(["systemctl", "suspend"], calls)
        if calls:
            self.assertEqual(calls[-1][-1], "on")

    def test_input_during_final_scan_cancels_before_submission(self):
        calls = self.run_request("", input_during_scan=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_external_sleep_cancels_request(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)", external_sleep=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_logind_loss_cancels_request(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)", owner_lost=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_bus_loss_cancels_request(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)", bus_lost=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])

    def test_zero_exit_with_rejected_blanking_never_suspends(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)", reject_off=True)
        self.assertEqual([c[-1] for c in calls], ['off','on'])
        self.assertNotIn(['systemctl','suspend'], calls)

    def test_failed_blanking_never_suspends(self):
        calls = self.run_request("print('idle', flush=True)\ntime.sleep(10)", fail_off=True)
        self.assertEqual([c[-1] for c in calls], ["off", "on"])


if __name__ == "__main__":
    unittest.main()
