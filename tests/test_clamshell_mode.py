"""Headless tests: no commands reach the live compositor or suspend policy."""
import copy
import fcntl
import os
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "home/scripts/display/clamshell-mode.py"
spec = importlib.util.spec_from_file_location("clamshell", SOURCE)
mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mode)


def output(name, x=0, mirror="none", workspace="1", focused=False):
    return dict(name=name, id={"eDP-1": 0, "DP-3": 1}.get(name, 2), x=x, y=0, width=1920, height=1200,
                refreshRate=60.001, scale=1.25, transform=0, disabled=False,
                mirrorOf=mirror, dpmsStatus=True, focused=focused, activeWorkspace={"name": workspace})


class ClamshellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.controller = mode.Clamshell(Path(self.temp.name), "instance-1")
        self.panel = output("eDP-1", workspace="notes", focused=True)
        self.external = output("DP-3", 1536, workspace="2")
        self.outputs = [self.panel, self.external]
        self.closed = True
        self.workspaces = [{"name": "notes", "monitor": "eDP-1"},
                           {"name": "3", "monitor": "eDP-1"},
                           {"name": "2", "monitor": "DP-3"}]
        self.commands = []
        self.fail = None
        self.addCleanup(patch.stopall)
        patch.object(mode, "monitors", side_effect=lambda: copy.deepcopy(self.outputs)).start()
        patch.object(mode, "lid_closed", side_effect=lambda: self.closed).start()
        self.busy = patch.object(mode, "headless_busy", return_value=False).start()
        patch.object(mode, "hypr", side_effect=self.hypr).start()

    def hypr(self, *args):
        self.commands.append(args)
        if self.fail and self.fail(args):
            raise subprocess.TimeoutExpired("hyprctl", 4)
        if args[:3] == ("output", "create", "headless"):
            self.outputs.append(output(args[3]))
        if args[:2] == ("output", "remove"):
            self.outputs.remove(next(m for m in self.outputs if m["name"] == args[2]))
        if args == ("workspaces", "-j"):
            return mode.json.dumps(self.workspaces)
        if args[:2] == ("dispatch", "moveworkspacetomonitor"):
            selector, monitor = args[2].rsplit(" ", 1)
            name = selector.removeprefix("name:")
            next(w for w in self.workspaces if w["name"] == name)["monitor"] = monitor
        if args[:2] == ("keyword", "monitor"):
            fields = args[2].split(",")
            monitor = next(m for m in self.outputs if m["name"] == fields[0])
            monitor["disabled"] = fields[1] == "disable"
            if fields[1] != "disable":
                monitor["mirrorOf"] = (str(next(m["id"] for m in self.outputs
                                                    if m["name"] == fields[-1]))
                                       if "mirror" in fields else "none")
        if args[:2] == ("dispatch", "dpms"):
            state, name = args[2].split()
            next(m for m in self.outputs if m["name"] == name)["dpmsStatus"] = state == "on"
        return "ok"

    def close(self):
        self.controller.handle("close")

    def test_close_and_reopen_restore_layout_and_named_workspace(self):
        self.close()
        self.assertTrue(self.panel["disabled"])
        self.assertTrue(self.controller.path.exists())
        self.assertEqual(self.commands[-1], ("keyword", "monitor", "eDP-1,disable"))
        self.closed = False
        self.controller.handle("open")
        self.assertFalse(self.panel["disabled"])
        self.assertFalse(self.controller.path.exists())
        self.assertIn(("keyword", "monitor", mode.rule(self.external)), self.commands)
        self.assertIn(("dispatch", "moveworkspacetomonitor", "name:notes eDP-1"), self.commands)
        self.assertEqual(self.commands[-1], ("dispatch", "focusmonitor", "eDP-1"))

    def test_no_external_blanks_without_disabling_and_reopen_wakes_panel(self):
        self.outputs = [self.panel]
        self.close()
        self.assertEqual(self.commands, [("dispatch", "dpms", "off eDP-1")])
        self.assertFalse(self.panel["disabled"])
        self.assertFalse(self.panel["dpmsStatus"])
        self.assertTrue(self.controller.load()["panelOnly"])
        self.controller.handle("check")
        self.assertEqual(len(self.commands), 1)
        self.closed = False
        self.controller.handle("open")
        self.assertTrue(self.panel["dpmsStatus"])
        self.assertFalse(self.controller.path.exists())

    def test_panel_blank_failure_keeps_recovery_journal(self):
        self.outputs = [self.panel]
        self.fail = lambda args: args == ("dispatch", "dpms", "off eDP-1")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.close()
        self.assertTrue(self.controller.path.exists())
        self.fail = None
        self.controller.handle("check")
        self.assertEqual(self.commands[-1], ("dispatch", "dpms", "off eDP-1"))
        self.assertFalse(self.panel["dpmsStatus"])
        self.assertTrue(self.controller.path.exists())
        self.closed = False
        self.controller.handle("check")
        self.assertEqual(self.commands[-1], ("dispatch", "dpms", "on eDP-1"))
        self.assertFalse(self.controller.path.exists())

    def test_folded_mode_all_states_are_untouched(self):
        self.busy.return_value = True
        for action in ("close", "open", "check"):
            self.controller.handle(action)
        self.assertEqual(self.commands, [])

    def test_stale_close_event_does_nothing_when_lid_open(self):
        self.closed = False
        self.close()
        self.assertEqual(self.commands, [])

    def test_mirror_is_detached_before_panel_and_restored_after(self):
        self.external["mirrorOf"] = "0"
        self.close()
        first_rule = next(args[2] for args in self.commands if args[:2] == ("keyword", "monitor"))
        self.assertNotIn("mirror", first_rule)
        self.assertTrue(self.panel["disabled"])
        self.closed = False
        self.controller.handle("open")
        self.assertEqual(self.external["mirrorOf"], "0")
        self.assertTrue(any(args[:2] == ("keyword", "monitor") and args[2].endswith(",mirror,eDP-1")
                            for args in self.commands))

    def test_hotplug_and_startup_checks_never_enter_mode(self):
        self.controller.handle("check")
        self.controller.handle("open")
        self.assertEqual(self.commands, [])

    def test_external_loss_restores_panel_at_origin(self):
        self.panel["x"] = 1536
        self.close()
        self.outputs = [self.panel]
        self.controller.handle("check")
        self.assertFalse(self.panel["disabled"])
        self.assertTrue(any(args[:2] == ("keyword", "monitor") and ",0x0," in args[2]
                            for args in self.commands[3:]))
        self.assertFalse(self.controller.path.exists())

    def test_interrupted_zero_output_recovery_cleans_up_exact_output_on_retry(self):
        self.close()
        self.outputs = [self.panel]
        self.fail = lambda args: args[:2] == ("keyword", "monitor")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.controller.handle("check")
        state = self.controller.load()
        recovery = state["recoveryOutput"]
        self.assertTrue(state["restoring"])
        self.assertTrue(any(m["name"] == recovery for m in self.outputs))
        self.fail = None
        self.controller.handle("check")
        self.assertFalse(self.panel["disabled"])
        self.assertFalse(any(m["name"] == recovery for m in self.outputs))
        self.assertEqual(sum(args[:3] == ("output", "create", "headless") for args in self.commands), 1)
        self.assertFalse(self.controller.path.exists())

    def test_partial_external_loss_keeps_clamshell(self):
        self.outputs.append(output("HDMI-A-1", 3072))
        self.close()
        self.outputs.remove(self.external)
        self.controller.handle("check")
        self.assertTrue(self.panel["disabled"])
        self.closed = False
        self.controller.handle("open")
        self.assertFalse(self.panel["disabled"])

    def test_inactive_workspace_assignments_are_restored(self):
        self.close()
        self.workspaces[1]["monitor"] = "DP-3"
        self.closed = False
        self.controller.handle("open")
        self.assertEqual(self.workspaces[1]["monitor"], "eDP-1")
        self.assertIn(("dispatch", "moveworkspacetomonitor", "3 eDP-1"), self.commands)

    def test_deleted_workspaces_are_not_recreated(self):
        self.close()
        self.workspaces.pop(1)
        self.closed = False
        self.controller.handle("open")
        self.assertNotIn(("dispatch", "moveworkspacetomonitor", "3 eDP-1"), self.commands)

    def test_close_failure_rolls_back_without_sensor_changes(self):
        self.fail = lambda args: args == ("keyword", "monitor", "eDP-1,disable")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.close()
        self.assertFalse(self.controller.path.exists())
        self.assertFalse(self.panel["disabled"])

    def test_restore_failure_keeps_journal_and_retries(self):
        self.close()
        self.closed = False
        self.fail = lambda args: args[:2] == ("keyword", "monitor")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.controller.handle("open")
        self.assertTrue(self.controller.path.exists())
        self.fail = None
        self.controller.handle("check")
        self.assertFalse(self.panel["disabled"])
        self.assertFalse(self.controller.path.exists())

    def test_old_instance_journal_is_not_replayed(self):
        self.close()
        self.commands.clear()
        mode.Clamshell(Path(self.temp.name), "new-instance").handle("check")
        self.assertEqual(self.commands, [])
        self.assertFalse(self.controller.path.exists())

    def test_duplicate_close_does_not_overwrite_snapshot(self):
        self.close()
        original = self.controller.path.read_text()
        count = len(self.commands)
        self.close()
        self.assertEqual(self.controller.path.read_text(), original)
        self.assertEqual(len(self.commands), count)

    def test_disabled_external_not_eligible(self):
        self.external["disabled"] = True
        self.close()
        self.assertEqual(self.commands, [("dispatch", "dpms", "off eDP-1")])
        self.assertFalse(self.panel["disabled"])

    def test_rules_preserve_scale_refresh_rotation_and_reject_unsafe_name(self):
        self.panel.update(width=1920, height=1200, transform=1, scale=1.5)
        self.assertEqual(mode.rule(self.panel), "eDP-1,1920x1200@60.001,0x0,1.5,transform,1")
        self.panel["name"] = "DP-1;dispatch exit"
        with self.assertRaises(ValueError):
            mode.rule(self.panel)

class ShellSerializationTests(unittest.TestCase):
    def test_layout_helpers_recheck_ownership_after_waiting_for_lock(self):
        root = SOURCE.parents[3]
        for name in ("display-mode-toggle", "display-layout-apply"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                runtime = Path(directory)
                (runtime / "headless-mode").mkdir()
                binary = runtime / "hyprctl"
                binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MARKER"\n')
                binary.chmod(0o755)
                marker = runtime / "calls"
                env = {**os.environ, "XDG_RUNTIME_DIR": directory, "MARKER": str(marker),
                       "PATH": directory + ":" + os.environ["PATH"]}
                env.pop("DISPLAY_TRANSITION_LOCKED", None)
                with (runtime / "headless-mode/lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    process = subprocess.Popen(["bash", str(root / "home/scripts/display" / name)], env=env,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            process.wait(timeout=.15)
                        self.assertFalse(marker.exists())
                        (runtime / "clamshell-mode").mkdir()
                        (runtime / "clamshell-mode/state.json").write_text("{}")
                        fcntl.flock(lock, fcntl.LOCK_UN)
                        stdout, stderr = process.communicate(timeout=5)
                        self.assertEqual(process.returncode, 0, stderr)
                        self.assertTrue(marker.read_text().startswith("notify "))
                        self.assertNotIn("monitors", marker.read_text())
                        # Nested synchronous calls skip a lock already owned by
                        # their folded/mirror caller; they still honor ownership.
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        nested = subprocess.run(["bash", str(root / "home/scripts/display" / name)],
                                                env=dict(env, DISPLAY_TRANSITION_LOCKED="1"),
                                                capture_output=True, timeout=5)
                        self.assertEqual(nested.returncode, 0, nested.stderr)
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.communicate(timeout=5)


class WiringTests(unittest.TestCase):
    def test_shared_lock_and_lid_bindings(self):
        root = SOURCE.parents[3]
        script = SOURCE.read_text()
        self.assertIn('runtime / "headless-mode" / "lock"', script)
        config = (root / "home/modules/hypr.nix").read_text()
        self.assertIn('switch:on:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode close', config)
        self.assertIn('switch:off:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode open', config)
        watcher = (root / "home/scripts/display/headless-monitor-watch").read_text()
        self.assertIn('clamshell-mode check', watcher)
        self.assertIn('[[ ! -e "$runtime/clamshell-mode/state.json" ]] || return 0', watcher)

    def test_ipc_has_timeout_and_no_shell(self):
        with patch.object(subprocess, "run") as run:
            run.return_value.stdout = "[]"
            self.assertEqual(mode.hypr("monitors", "all", "-j"), "[]")
            run.assert_called_once_with(["hyprctl", "monitors", "all", "-j"], check=True,
                                        capture_output=True, text=True, timeout=4)

    def test_lid_policy_is_independent_of_power(self):
        policy = (SOURCE.parents[3] / "hosts/kirax1/modules/hardware/clamshell-mode.nix").read_text()
        self.assertIn('HandleLidSwitch = "suspend";', policy)
        self.assertIn('HandleLidSwitchExternalPower = "suspend";', policy)
        self.assertIn('HandleLidSwitchDocked = "ignore";', policy)


if __name__ == "__main__":
    unittest.main()
