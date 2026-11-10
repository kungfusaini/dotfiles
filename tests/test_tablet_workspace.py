import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

SOURCE = Path(__file__).resolve().parents[1] / "home/scripts/desktop/tablet-workspace.py"
spec = importlib.util.spec_from_file_location("tablet_workspace", SOURCE)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class TabletWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "XDG_RUNTIME_DIR": self.tmp.name,
            "HYPRLAND_INSTANCE_SIGNATURE": "test-instance",
            "TABLET_PANEL_QML": "/deployed/shell.qml",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def state(self, origin="work"):
        trial.save_state({"instance": "test-instance", "return": origin, "enabled": True})

    def test_native_session_blocks_legacy_workspace_entry(self):
        path = Path(self.tmp.name) / 'tablet-proof'
        path.mkdir()
        (path / 'recovery.json').write_text('{}')
        with patch.object(trial, 'dispatch') as dispatch, patch.object(trial, 'hypr') as query:
            with self.assertRaisesRegex(RuntimeError, 'native tablet session'):
                trial.enter()
        dispatch.assert_not_called()
        query.assert_not_called()

    def test_enter_only_switches_workspace_and_remembers_origin(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, []]), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "Popen"):
            trial.enter()
        dispatch.assert_called_once_with("workspace", "name:tablet-trial")
        self.assertEqual(trial.load_state()["return"], "work")

    def test_repeated_enter_keeps_original_return(self):
        self.state()
        with patch.object(trial, "hypr", return_value={"name": "tablet-trial"}), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "Popen"):
            trial.enter()
        dispatch.assert_not_called()
        self.assertEqual(trial.load_state()["return"], "work")

    def test_reentry_from_another_workspace_records_that_workspace(self):
        self.state()
        with patch.object(trial, "hypr", return_value={"name": "other"}), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "Popen"):
            trial.enter()
        self.assertEqual(trial.load_state()["return"], "other")

    def test_unowned_workspace_is_not_claimed(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, [{"name": "tablet-trial"}]]), \
                patch.object(trial, "dispatch") as dispatch:
            with self.assertRaises(RuntimeError):
                trial.enter()
        dispatch.assert_not_called()
        self.assertFalse(trial.state_path().exists())

    def test_unowned_current_workspace_is_not_claimed(self):
        with patch.object(trial, "hypr", return_value={"name": "tablet-trial"}), \
                patch.object(trial, "dispatch") as dispatch:
            with self.assertRaises(RuntimeError):
                trial.enter()
        dispatch.assert_not_called()

    def test_failed_switch_cleans_state(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, []]), \
                patch.object(trial, "dispatch", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                trial.enter()
        self.assertFalse(trial.state_path().exists())

    def test_failed_reentry_preserves_ownership_and_parked_apps(self):
        self.state()
        state = trial.load_state()
        state["enabled"] = False
        trial.save_state(state)
        with patch.object(trial, "hypr", return_value={"name": "other"}), \
                patch.object(trial, "dispatch", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                trial.enter()
        self.assertEqual(trial.load_state(), state)

    def test_leave_and_immediate_reentry_reuses_a_hidden_panel(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}]), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "run"):
            trial.leave()
        with patch.object(trial, "hypr", return_value={"name": "work"}), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "Popen") as launch:
            trial.enter()
        self.assertIn("--no-duplicate", launch.call_args.args[0])
        qml = SOURCE.parents[2] / "config/quickshell/tablet-workspace/shell.qml"
        self.assertNotIn("Qt.quit()", qml.read_text())
        self.assertTrue(trial.load_state()["enabled"])

    def test_leave_preserves_apps_and_does_not_send_escape(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}]), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "run") as run:
            trial.leave()
        dispatch.assert_called_once_with("workspace", "name:work")
        self.assertEqual(run.call_args_list, [
            call(["tablet-orientation", "restore"], check=True),
            call(["tablet-osk", "dismiss"], check=True),
        ])
        self.assertFalse(trial.load_state()["enabled"])

    def test_reentry_after_leave_with_parked_apps(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}, {"name": "tablet-trial"}]), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "run"):
            trial.leave()
        self.assertFalse(trial.load_state()["enabled"])
        with patch.object(trial, "hypr", return_value={"name": "work"}), \
                patch.object(trial, "dispatch") as dispatch, patch.object(trial.subprocess, "Popen"):
            trial.enter()
        dispatch.assert_called_once_with("workspace", "name:tablet-trial")
        self.assertTrue(trial.load_state()["enabled"])
        self.assertEqual(trial.load_state()["return"], "work")

    def test_disabled_trial_cannot_launch_apps(self):
        self.state()
        state = trial.load_state()
        state["enabled"] = False
        trial.save_state(state)
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "dispatch") as dispatch:
            with self.assertRaises(RuntimeError):
                trial.action("browser")
        dispatch.assert_not_called()

    def test_failed_orientation_restore_blocks_return_and_disables_rotation(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}]), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "restore")):
            with self.assertRaises(subprocess.CalledProcessError):
                trial.leave()
        dispatch.assert_not_called()
        self.assertFalse(trial.load_state()["enabled"])

    def test_failed_restore_can_retry_leave_without_reentering(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}]), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "run") as run:
            run.side_effect = subprocess.CalledProcessError(1, "restore")
            with self.assertRaises(subprocess.CalledProcessError):
                trial.leave()
            self.assertTrue(trial.load_state()["exit_pending"])
            self.assertFalse(trial.load_state()["enabled"])
            run.side_effect = None
            trial.leave()
        dispatch.assert_called_once_with("workspace", "name:work")
        self.assertFalse(trial.load_state()["exit_pending"])
        self.assertFalse(trial.load_state()["enabled"])

    def test_pending_exit_does_not_start_a_new_controller(self):
        self.state()
        state = trial.load_state()
        state.update(enabled=False, exit_pending=True)
        trial.save_state(state)
        with patch.object(trial, "dispatch") as dispatch, patch.object(trial.subprocess, "Popen") as launch:
            with self.assertRaises(RuntimeError):
                trial.enter()
        dispatch.assert_not_called()
        launch.assert_not_called()

    def test_pending_exit_keeps_back_button_visible(self):
        self.state()
        state = trial.load_state()
        state.update(enabled=False, exit_pending=True)
        trial.save_state(state)
        with patch.object(trial, "hypr", return_value={"name": "tablet-trial", "monitor": "eDP-1"}), \
                patch("builtins.print") as output:
            trial.status()
        self.assertTrue(json.loads(output.call_args.args[0])["visible"])

    def test_iteration_entry_never_starts_the_normal_panel(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, []]), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "Popen") as launch:
            trial.enter(panel=False)
        self.assertEqual(len(launch.call_args_list), 1)
        self.assertEqual(launch.call_args.args[0], ["tablet-orientation", "daemon"])
        self.assertTrue(trial.load_state()["enabled"])

    def test_explicit_entry_starts_rotation_daemon_without_rotation_commands(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, []]), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "Popen") as launch:
            trial.enter()
        self.assertEqual(launch.call_args_list[0].args[0], ["tablet-orientation", "daemon"])

    def test_missing_return_does_not_switch_or_remove_state(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[]), patch.object(trial, "dispatch") as dispatch:
            with self.assertRaises(RuntimeError):
                trial.leave()
        dispatch.assert_not_called()
        self.assertIsNotNone(trial.load_state())

    def test_state_from_old_compositor_is_ignored(self):
        self.state()
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "new-instance"}):
            self.assertIsNone(trial.load_state())

    def test_actions_outside_trial_are_refused(self):
        self.state()
        with patch.object(trial, "foreground", return_value=False), \
                patch.object(trial, "dispatch") as dispatch:
            for action in ("browser", "keyboard", "next"):
                with self.assertRaises(RuntimeError):
                    trial.action(action)
        dispatch.assert_not_called()

    def test_browser_opens_a_new_window_in_trial_only(self):
        self.state()
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "dispatch") as dispatch:
            trial.action("browser")
        dispatch.assert_called_once_with("exec", "[workspace name:tablet-trial silent] vivaldi --new-window about:blank")

    def test_status_hides_panel_outside_trial(self):
        self.state()
        with patch.object(trial, "hypr", return_value={"name": "work", "monitor": "eDP-1"}), \
                patch("builtins.print") as output:
            trial.status()
        state = json.loads(output.call_args.args[0])
        self.assertTrue(state["enabled"])
        self.assertFalse(state["visible"])

    def test_status_shows_panel_on_active_tablet_monitor(self):
        self.state()
        with patch.object(trial, "hypr", return_value={"name": "tablet-trial", "monitor": "eDP-1"}), \
                patch("builtins.print") as output:
            trial.status()
        self.assertEqual(json.loads(output.call_args.args[0]), {
            "enabled": True, "visible": True, "monitor": "eDP-1",
        })

    def test_keyboard_has_no_legacy_fold_daemon(self):
        script = Path(__file__).resolve().parents[1] / "hosts/kirax1/scripts/desktop/tablet-osk"
        self.assertNotIn("daemon()", script.read_text())
        self.assertNotIn("hotkey_tablet_mode", script.read_text())
        self.assertIn('dismiss) touch "$DISABLED_FILE"; stop_osk ;;', script.read_text())

    def posture(self, watcher, folded="1", headless="off", monitors=None, current=None, workspaces=None):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path).endswith("hotkey_tablet_mode"):
                if isinstance(folded, Exception):
                    raise folded
                return folded
            if str(path) == "/run/headless-mode/state":
                return headless
            return original(path, *args, **kwargs)
        if monitors is None:
            monitors = [{"name": "eDP-1", "dpmsStatus": True}]
        if current is None:
            current = {"name": "work", "monitor": "eDP-1"}
        with patch.object(Path, "read_text", read), \
                patch.object(trial, "hypr", side_effect=[monitors, current, workspaces or []]), \
                patch.object(trial, "enter") as enter, patch.object(trial, "leave") as leave:
            watcher.tick()
        return enter, leave

    def test_fold_enters_once_and_manual_exit_is_respected(self):
        watcher = trial.FoldWatcher()
        enter, leave = self.posture(watcher)
        enter.assert_called_once_with(automatic=True)
        leave.assert_not_called()
        enter, _ = self.posture(watcher)
        enter.assert_not_called()
        self.posture(watcher, folded="0")
        enter, _ = self.posture(watcher)
        enter.assert_called_once_with(automatic=True)

    def test_unfold_leaves_enabled_mode_once(self):
        watcher = trial.FoldWatcher()
        self.posture(watcher)
        self.state()
        _, leave = self.posture(watcher, folded="0")
        leave.assert_called_once_with(automatic=True)
        # A real leave marks this disabled; repeated laptop ticks are inert.
        state = trial.load_state()
        state["enabled"] = False
        trial.save_state(state)
        _, leave = self.posture(watcher, folded="0")
        leave.assert_not_called()

    def test_login_unfolded_preserves_explicit_manual_mode(self):
        self.state()
        enter, leave = self.posture(trial.FoldWatcher(), folded="0")
        enter.assert_not_called()
        leave.assert_not_called()

    def test_restart_unfolded_restores_automatically_owned_mode(self):
        self.state()
        state = trial.load_state()
        state["automatic"] = True
        trial.save_state(state)
        _, leave = self.posture(trial.FoldWatcher(), folded="0")
        leave.assert_called_once_with(automatic=True)

    def test_headless_fold_is_consumed_without_entry_after_headless_exit(self):
        for mode in ("primed", "active", "unexpected"):
            watcher = trial.FoldWatcher()
            with patch.object(trial.subprocess, "run") as run:
                enter, leave = self.posture(watcher, headless=mode)
                self.posture(watcher, headless=mode)
            run.assert_called_once_with(["tablet-osk", "dismiss"], check=True)
            enter.assert_not_called()
            leave.assert_not_called()
            enter, _ = self.posture(watcher)
            enter.assert_not_called()
            self.posture(watcher, folded="0")
            enter, _ = self.posture(watcher)
            enter.assert_called_once_with(automatic=True)

    def test_headless_dismissal_survives_missing_or_unknown_posture(self):
        for value in (FileNotFoundError("missing"), "2"):
            with patch.object(trial.subprocess, "run") as run:
                with self.assertRaises((OSError, ValueError)):
                    self.posture(trial.FoldWatcher(), folded=value, headless="active")
            run.assert_called_once_with(["tablet-osk", "dismiss"], check=True)

    def test_restart_unfolded_retries_pending_exit_of_manual_mode(self):
        self.state()
        state = trial.load_state()
        state.update(enabled=False, automatic=False, exit_pending=True)
        trial.save_state(state)
        _, leave = self.posture(trial.FoldWatcher(), folded="0")
        leave.assert_called_once_with(automatic=True)

    def test_missing_or_unknown_posture_never_infers_unfold(self):
        watcher = trial.FoldWatcher()
        watcher.folded = True
        for value in (FileNotFoundError("missing"), "", "2"):
            with self.assertRaises((OSError, ValueError)):
                self.posture(watcher, folded=value)
            self.assertIs(watcher.folded, True)

    def test_fold_waits_for_internal_display_and_focus(self):
        for monitors, current in [
            ([], None),
            ([{"name": "eDP-1", "dpmsStatus": False}], None),
            ([{"name": "eDP-1", "disabled": True}], None),
            ([{"name": "eDP-1", "specialWorkspace": {"id": -99}}], None),
            (None, {"name": "work", "monitor": "HDMI-A-1"}),
        ]:
            watcher = trial.FoldWatcher()
            enter, _ = self.posture(watcher, monitors=monitors, current=current)
            enter.assert_not_called()
            enter, _ = self.posture(watcher)
            enter.assert_called_once_with(automatic=True)

    def test_fold_does_not_reenter_existing_manual_mode(self):
        self.state()
        enter, _ = self.posture(trial.FoldWatcher(), current={"name": "tablet-trial", "monitor": "eDP-1"})
        enter.assert_not_called()

    def test_fold_reenters_enabled_but_background_manual_mode(self):
        self.state()
        enter, _ = self.posture(trial.FoldWatcher())
        enter.assert_called_once_with(automatic=True)

    def test_fold_never_focuses_retained_external_tablet_workspace(self):
        watcher = trial.FoldWatcher()
        enter, _ = self.posture(watcher, workspaces=[{"name": "tablet-trial", "monitor": "HDMI-A-1"}])
        enter.assert_not_called()
        self.assertIsNone(watcher.folded)
        enter, _ = self.posture(watcher, workspaces=[{"name": "tablet-trial", "monitor": "eDP-1"}])
        enter.assert_called_once_with(automatic=True)

    def test_automatic_leave_does_not_steal_focus(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[{"name": "work"}]), \
                patch.object(trial, "foreground", return_value=False), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "run") as run:
            trial.leave(automatic=True)
        dispatch.assert_not_called()
        self.assertEqual(run.call_args_list[0], call(["tablet-orientation", "restore"], check=True))
        self.assertFalse(trial.load_state()["enabled"])

    def test_unfold_with_missing_return_still_restores_and_dismisses_keyboard(self):
        self.state()
        with patch.object(trial, "hypr", return_value=[]), \
                patch.object(trial, "dispatch") as dispatch, \
                patch.object(trial.subprocess, "run") as run:
            trial.leave(automatic=True)
        dispatch.assert_not_called()
        self.assertEqual(run.call_args_list, [
            call(["tablet-orientation", "restore"], check=True),
            call(["tablet-osk", "dismiss"], check=True),
        ])
        self.assertFalse(trial.load_state()["enabled"])

    def test_automatic_entry_is_recorded_for_watcher_restart(self):
        with patch.object(trial, "hypr", side_effect=[{"name": "work"}, []]), \
                patch.object(trial, "dispatch"), patch.object(trial.subprocess, "Popen"):
            trial.enter(automatic=True)
        self.assertTrue(trial.load_state()["automatic"])

    def test_watcher_failure_retries_without_consuming_edge(self):
        watcher = trial.FoldWatcher()
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path).endswith("hotkey_tablet_mode"):
                return "1"
            if str(path) == "/run/headless-mode/state":
                return "off"
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", read), \
                patch.object(trial, "hypr", side_effect=[[{"name": "eDP-1"}], {"monitor": "eDP-1"}, []]), \
                patch.object(trial, "enter", side_effect=RuntimeError("restore pending")):
            with self.assertRaises(RuntimeError):
                watcher.tick()
        self.assertIsNone(watcher.folded)
        enter, _ = self.posture(watcher)
        enter.assert_called_once_with(automatic=True)


if __name__ == "__main__":
    unittest.main()
