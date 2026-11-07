import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch, call, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tablet_iterate", ROOT / "home/scripts/desktop/tablet-iterate.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name,
                                          "HYPRLAND_INSTANCE_SIGNATURE": "instance"}, clear=True)
        self.env.start()
        self.target = {"instance": "instance", "stream": "stream-id", "pid": 123,
                       "start": "45", "address": "0xabc", "workspace": "Machine · Tablet Mode"}
        self.client = {"address": "0xabc", "pid": 123, "class": "kitty", "title": "π - stream-id",
                       "workspace": {"name": self.target["workspace"]}}
        self.trial = ui.Trial(self.target)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_input_surface_cannot_take_keyboard_focus_or_auto_record(self):
        qml = (ROOT/"home/config/quickshell/tablet-home-preview/iteration.qml").read_text()
        self.assertEqual(qml.count("keyboardFocus: WlrKeyboardFocus.None"), 3)
        self.assertIn('onClicked: root.run("mic")', qml)
        self.assertNotIn('onActiveFocusChanged', qml)
        self.assertNotIn('triggeredOnStart: root.run("mic")', qml)

    def test_private_voice_namespace_ignores_interleaved_desktop_recording(self):
        private = self.trial.voice_runtime/"voxtype"
        private.mkdir(parents=True)
        (private/"pid").write_text("321")
        (private/"voxtype.lock").write_text("321")
        (private/"state").write_text("recording")
        desktop = Path(self.temp.name)/"voxtype"
        desktop.mkdir()
        (desktop/"state").write_text("recording")
        self.trial.voice_identity = {"pid": 321, "start": "45"}
        self.trial.recording = True
        def command(*args, **kwargs):
            self.assertEqual(kwargs["env"]["XDG_RUNTIME_DIR"], str(self.trial.voice_runtime))
            self.assertNotEqual(kwargs["env"]["XDG_RUNTIME_DIR"], self.temp.name)
            # An independent desktop recording starts between inspection and
            # command delivery. Only the private instance receives Cancel.
            (desktop/"state").write_text("another desktop recording")
            (private/"state").write_text("idle")
        with patch.object(ui, "start_time", return_value="45"), patch.object(ui, "run", side_effect=command):
            self.assertTrue(self.trial.owns_voice())
            self.trial.cancel()
        self.assertEqual((desktop/"state").read_text(), "another desktop recording")
        self.assertFalse(self.trial.voice_guard)
        self.assertEqual(self.trial.voice_env["PIPEWIRE_RUNTIME_DIR"], self.temp.name)

    def test_transcription_waiter_is_in_recovery_ledger(self):
        self.trial.transcriber = Mock(pid=321)
        self.trial.transcriber.poll.return_value = None
        with patch.object(ui, "start_time", return_value="45"):
            self.trial.journal()
        self.assertIn({"pid": 321, "start": "45"}, json.loads((ui.directory()/"recovery.json").read_text())["children"])

    def test_binding_requires_exact_session_compositor_pid_start_and_title(self):
        ui.save("binding.json", self.target)
        with patch.object(ui, "start_time", return_value="45"), patch.object(ui, "hypr", return_value=[self.client]):
            self.assertEqual(ui.binding()[0], self.target)
        with patch.object(ui, "start_time", return_value="46"):
            with self.assertRaises(RuntimeError): ui.binding()
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "other"}):
            with self.assertRaises(RuntimeError): ui.binding()
        with patch.object(ui, "start_time", return_value="45"), patch.object(ui, "hypr", return_value=[]):
            with self.assertRaises(RuntimeError): ui.binding()
        self.client["title"] = "shell, no Pi"
        with patch.object(ui, "start_time", return_value="45"), patch.object(ui, "hypr", return_value=[self.client]):
            with self.assertRaises(RuntimeError): ui.binding()

    def test_binding_rejects_dispatch_parameter_injection(self):
        for name in ("bad,name", "bad\nname", ""):
            with self.assertRaises(RuntimeError): ui.workspace_name(name)
        ui.save("binding.json", dict(self.target, address="0xabc,wrong"))
        with self.assertRaises(RuntimeError): ui.binding()

    def test_pi_reuses_exact_terminal_without_launching_new_agent(self):
        with patch.object(self.trial, "foreground", return_value=True), \
                patch.object(self.trial, "safe", return_value=True), \
                patch.object(ui, "binding", return_value=(self.target, self.client)), \
                patch.object(self.trial, "fit_pi"), \
                patch.object(ui, "dispatch") as dispatch, patch.object(ui.subprocess, "Popen") as spawn:
            self.trial.pi()
        self.assertEqual(dispatch.call_args_list, [
            call("movetoworkspacesilent", "name:tablet-trial,address:0xabc"),
            call("setfloating", "address:0xabc"),
            call("focuswindow", "address:0xabc"),
        ])
        spawn.assert_not_called()
        self.assertEqual(self.trial.view, "pi")
        self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["borrowed"])

    def test_pi_refuses_fullscreen_pinned_or_grouped_sessions_without_mutation(self):
        for state in ({"fullscreen": 2}, {"pinned": True}, {"grouped": ["0xdef"]}):
            client = dict(self.client, **state)
            with patch.object(self.trial, "foreground", return_value=True), \
                    patch.object(self.trial, "safe", return_value=True), \
                    patch.object(ui, "binding", return_value=(self.target, client)), \
                    patch.object(ui, "dispatch") as dispatch:
                with self.assertRaises(RuntimeError): self.trial.pi()
            dispatch.assert_not_called()
            self.assertFalse(self.trial.borrowed)

    def test_pi_layout_follows_keyboard_reservations_without_focus_changes(self):
        monitor = {"name": "eDP-1", "width": 1920, "height": 1200, "scale": 1.25,
                   "x": 0, "y": 0, "transform": 0, "reserved": [0, 120, 0, 300]}
        with patch.object(ui, "hypr", return_value=[monitor]), patch.object(ui, "dispatch") as dispatch:
            self.trial.fit_pi()
            first = dispatch.call_args_list[:]
            self.trial.fit_pi()
            self.assertEqual(dispatch.call_args_list, first)
            monitor["reserved"][-1] = 400
            self.trial.fit_pi()
        self.assertEqual(len(dispatch.call_args_list), 4)
        self.assertTrue(all(c.args[0] in ("resizewindowpixel", "movewindowpixel") for c in dispatch.call_args_list))
        self.assertTrue(all("address:0xabc" in c.args[1] for c in dispatch.call_args_list))
        h = int(dispatch.call_args_list[-2].args[1].split(",")[0].split()[-1])
        y = int(dispatch.call_args_list[-1].args[1].split(",")[0].split()[-1])
        self.assertLessEqual(y + h, 960 - 400)

    def test_pi_portrait_layout_stays_inside_rotated_monitor(self):
        monitor = {"name": "eDP-1", "width": 1920, "height": 1200, "scale": 1.25,
                   "x": 100, "y": 50, "transform": 1, "reserved": [0, 120, 0, 400]}
        with patch.object(ui, "hypr", return_value=[monitor]), patch.object(ui, "dispatch") as dispatch:
            self.trial.fit_pi()
        w, h = map(int, dispatch.call_args_list[0].args[1].split(",")[0].split()[1:])
        x, y = map(int, dispatch.call_args_list[1].args[1].split(",")[0].split()[1:])
        self.assertGreaterEqual(x, 100)
        self.assertGreaterEqual(y, 50 + 144)
        self.assertLessEqual(x + w, 100 + 960)
        self.assertLessEqual(y + h, 50 + 1536 - 400)

    def test_return_restores_original_floating_geometry(self):
        self.trial.borrowed = True
        self.trial.window_restore = {"floating": True, "at": [30, 40], "size": [600, 500]}
        self.client["workspace"]["name"] = ui.WORKSPACE
        with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                patch.object(ui, "dispatch") as dispatch:
            self.trial.return_terminal()
        self.assertEqual(dispatch.call_args_list, [
            call("movetoworkspacesilent", "name:Machine · Tablet Mode,address:0xabc"),
            call("setfloating", "address:0xabc"),
            call("resizewindowpixel", "exact 600 500,address:0xabc"),
            call("movewindowpixel", "exact 30 40,address:0xabc"),
        ])

    def test_return_restores_tiled_state_and_preserves_snapshot_on_partial_failure(self):
        self.trial.borrowed = True
        self.trial.window_restore = {"floating": False, "at": [30, 40], "size": [600, 500]}
        self.client["workspace"]["name"] = self.target["workspace"]
        with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                patch.object(ui, "dispatch", side_effect=RuntimeError("not restored")):
            with self.assertRaises(RuntimeError): self.trial.return_terminal()
        self.assertTrue(self.trial.borrowed)
        self.assertIsNotNone(self.trial.window_restore)
        with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                patch.object(ui, "dispatch") as dispatch:
            self.trial.return_terminal()
        dispatch.assert_called_once_with("settiled", "address:0xabc")

    def test_third_workspace_move_is_preserved_while_trial_window_state_is_restored(self):
        for floating in (False, True):
            self.trial.borrowed = True
            self.trial.window_restore = {"floating": floating, "at": [30, 40], "size": [600, 500]}
            self.client["workspace"]["name"] = "Other"
            with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                    patch.object(ui, "dispatch") as dispatch:
                self.trial.return_terminal()
            expected = [call("setfloating", "address:0xabc"), call("resizewindowpixel", "exact 600 500,address:0xabc")] if floating else [call("settiled", "address:0xabc")]
            self.assertEqual(dispatch.call_args_list, expected)
            self.assertFalse(self.trial.borrowed)
            self.assertIsNone(self.trial.window_restore)

    def test_third_workspace_cleanup_failure_retains_window_recovery(self):
        self.trial.borrowed = True
        self.trial.window_restore = {"floating": False, "at": [30, 40], "size": [600, 500]}
        self.trial.journal()
        self.client["workspace"]["name"] = "Other"
        with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                patch.object(ui, "dispatch", side_effect=RuntimeError("not restored")):
            with self.assertRaises(RuntimeError): self.trial.cleanup()
        ledger = json.loads((ui.directory()/"recovery.json").read_text())
        self.assertTrue(ledger["borrowed"])
        self.assertEqual(ledger["window"]["floating"], False)

    def test_pi_closure_returns_home_without_exiting_tablet_mode(self):
        self.trial.view = "pi"
        with patch.object(self.trial, "foreground", return_value=True), patch.object(self.trial, "safe", return_value=True), \
                patch.object(ui, "hypr", return_value=[]):
            self.trial.tick()
        self.assertEqual(self.trial.view, "home")
        self.assertFalse(self.trial.stopping)

    def test_pi_closure_with_voice_problem_stays_on_home_with_error(self):
        self.trial.view = "pi"
        with patch.object(self.trial, "foreground", return_value=True), patch.object(self.trial, "safe", return_value=True), \
                patch.object(self.trial, "cancel", side_effect=RuntimeError("voice needs attention")), \
                patch.object(ui, "hypr", return_value=[]):
            self.trial.tick()
        self.assertEqual(self.trial.view, "home")
        self.assertFalse(self.trial.stopping)
        self.assertEqual(self.trial.error, "voice needs attention")

    def test_layout_failure_does_not_exit_tablet_environment(self):
        self.trial.view = "pi"
        self.client["workspace"]["name"] = ui.WORKSPACE
        with patch.object(self.trial, "foreground", return_value=True), patch.object(self.trial, "safe", return_value=True), \
                patch.object(self.trial, "fit_pi", side_effect=RuntimeError("layout unavailable")), \
                patch.object(ui, "hypr", return_value=[self.client]):
            self.trial.tick()
        self.assertFalse(self.trial.stopping)
        self.assertEqual(self.trial.view, "pi")
        self.assertEqual(self.trial.error, "layout unavailable")

    def test_pi_does_not_steal_terminal_moved_elsewhere(self):
        self.client["workspace"]["name"] = "Other"
        with patch.object(self.trial, "foreground", return_value=True), \
                patch.object(self.trial, "safe", return_value=True), \
                patch.object(ui, "binding", return_value=(self.target, self.client)), \
                patch.object(ui, "dispatch") as dispatch:
            with self.assertRaises(RuntimeError): self.trial.pi()
        dispatch.assert_not_called()

    def test_home_returns_terminal_without_focusing_another_workspace(self):
        self.trial.borrowed = True
        self.client["workspace"]["name"] = ui.WORKSPACE
        with patch.object(ui, "hypr", return_value=[self.client]), \
                patch.object(self.trial, "foreground", return_value=True), \
                patch.object(ui, "start_time", return_value="45"), patch.object(ui, "dispatch") as dispatch:
            self.trial.action("home")
        dispatch.assert_called_once_with("movetoworkspacesilent", "name:Machine · Tablet Mode,address:0xabc")
        self.assertEqual(self.trial.view, "home")

    def test_return_does_not_hijack_terminal_user_moved(self):
        self.trial.borrowed = True
        self.client["workspace"]["name"] = "Other"
        with patch.object(ui, "hypr", return_value=[self.client]), patch.object(ui, "start_time", return_value="45"), \
                patch.object(ui, "dispatch") as dispatch:
            self.trial.return_terminal()
        dispatch.assert_not_called()

    def test_setting_journal_precedes_mutation_and_has_private_permissions(self):
        def command(*args, **kwargs):
            if args[1] == "set":
                saved = json.loads((ui.directory()/"recovery.json").read_text())
                self.assertEqual(saved["settings"], [["schema", "key", "false", "true"]])
            return SimpleNamespace(stdout="false\n")
        with patch.object(ui, "run", side_effect=command):
            self.trial.setting("schema", "key", "true")
        self.assertEqual((ui.directory()/"recovery.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(ui.directory().stat().st_mode & 0o777, 0o700)

    def test_failed_preflight_does_not_delete_an_existing_recovery_journal(self):
        ui.save("recovery.json", {"existing": True})
        self.trial.cleanup()
        self.assertTrue((ui.directory()/"recovery.json").exists())

    def voice_context(self):
        self.trial.view = "pi"
        return (patch.object(self.trial, "foreground", return_value=True),
                patch.object(self.trial, "safe", return_value=True),
                patch.object(ui, "binding", return_value=(self.target, self.client)))

    def test_explicit_mic_uses_file_output_no_autosubmit_no_live_paste(self):
        a,b,c = self.voice_context()
        with a,b,c, patch.object(self.trial, "start_voice"), patch.object(self.trial, "voice_snapshot", return_value=(1, 1, "idle")), \
                patch.object(self.trial, "await_voice", return_value=(1, 2, "recording")), \
                patch.object(ui, "run") as command:
            self.trial.mic()
        args = command.call_args.args
        self.assertIn("--file=" + str(self.trial.transcript), args)
        self.assertIn("--no-auto-submit", args)
        self.assertIn("--no-smart-auto-submit", args)
        self.assertNotIn("--paste", args)
        self.assertTrue(self.trial.recording)

    def test_mic_never_takes_over_existing_dictation(self):
        a,b,c = self.voice_context()
        with a,b,c, patch.object(self.trial, "start_voice"), patch.object(self.trial, "voice_snapshot", return_value=(1, 2, "recording")), patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.mic()
        command.assert_not_called()

    def test_mic_is_not_usable_on_home_or_without_foreground(self):
        with patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.mic()
        command.assert_not_called()

    def test_unconfirmed_private_owner_is_never_cancelled(self):
        self.trial.recording = True
        self.trial.voice_token = (1, 20, "recording")
        with patch.object(self.trial, "voice_snapshot", return_value=(1, 30, "recording")), \
                patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.cancel()
        self.assertTrue(self.trial.voice_pending)
        command.assert_not_called()

    def test_unconfirmed_private_owner_is_never_stopped(self):
        self.trial.recording = True
        self.trial.voice_token = (1, 20, "recording")
        with patch.object(self.trial, "voice_snapshot", return_value=(1, 30, "recording")), \
                patch.object(ui.subprocess, "Popen") as spawn:
            with self.assertRaises(RuntimeError): self.trial.stop_voice()
        spawn.assert_not_called()

    def test_cancel_idle_does_not_cancel_someone_elses_voxtype(self):
        with patch.object(ui, "run") as command:
            self.trial.cancel()
        command.assert_not_called()

    def test_cancel_own_recording_discards_transcript(self):
        self.trial.recording = True
        self.trial.transcript.write_text("private draft")
        with patch.object(self.trial, "owns_voice", return_value=True), \
                patch.object(self.trial, "voice_state", return_value="idle"), patch.object(ui, "run") as command:
            self.trial.cancel()
        command.assert_called_once_with("voxtype", "record", "cancel", env=self.trial.voice_env)
        self.assertFalse(self.trial.transcript.exists())

    def test_stop_is_async_and_never_auto_pastes(self):
        self.trial.recording = True
        process = Mock(pid=321)
        process.poll.return_value = None
        def waiting(*_):
            ledger = json.loads((ui.directory()/"recovery.json").read_text())
            self.assertIn({"pid": 321, "start": "45"}, ledger["children"])
            return (1, 3, "transcribing")
        with patch.object(self.trial, "owns_voice", return_value=True), \
                patch.object(self.trial, "await_voice", side_effect=waiting), \
                patch.object(ui.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(ui, "start_time", return_value="45"):
            self.trial.stop_voice()
        args = spawn.call_args.args[0]
        self.assertIn("--wait", args)
        self.assertNotIn("--paste", args)
        self.assertIs(self.trial.transcriber, process)
        self.assertFalse(self.trial.recording)

    def test_insert_verifies_focus_and_only_pastes_without_return(self):
        a,b,c = self.voice_context()
        self.trial.transcript.write_bytes(b"draft\nsecond line")
        clip = [SimpleNamespace(returncode=0, stdout=b"text/plain\n"),
                SimpleNamespace(returncode=0, stdout=b"previous"),
                SimpleNamespace(returncode=0, stdout=b"draft\nsecond line")]
        with a,b,c, patch.object(ui, "dispatch"), patch.object(ui, "hypr", return_value={"address": "0xabc"}), \
                patch.object(ui.subprocess, "run", side_effect=clip), patch.object(ui, "run") as command, \
                patch.object(ui.time, "sleep"):
            self.trial.insert()
        self.assertIn(call("wl-copy", input=b"previous"), command.call_args_list)
        key_calls = [x for x in command.call_args_list if x.args[0] == "wtype"]
        self.assertEqual(key_calls, [call("wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl")])
        self.assertFalse(self.trial.transcript.exists())

    def test_focus_mismatch_keeps_pending_transcript(self):
        a,b,c = self.voice_context()
        self.trial.transcript.write_text("draft")
        with a,b,c, patch.object(ui, "dispatch"), patch.object(ui, "hypr", return_value={"address": "0xdef"}), \
                patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.insert()
        command.assert_not_called()
        self.assertTrue(self.trial.transcript.exists())

    def test_nontext_clipboard_is_not_overwritten(self):
        a,b,c = self.voice_context()
        self.trial.transcript.write_text("draft")
        with a,b,c, patch.object(ui, "dispatch"), patch.object(ui, "hypr", return_value={"address": "0xabc"}), \
                patch.object(ui.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"image/png\n")), \
                patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.insert()
        command.assert_not_called()

    def test_restored_panel_does_not_inherit_trial_theme_or_command_path(self):
        self.trial.owns_journal = True
        self.trial.panel_commands = [{"argv": ["/store/quickshell", "-p", "/store/panel.qml"],
                                      "environment": {"PATH": "/original/bin", "QT_QUICK_CONTROLS_STYLE": "Original"}}]
        with patch.dict(os.environ, {"TABLET_TEST": "trial", "QT_QUICK_CONTROLS_STYLE": "Basic"}), \
                patch.object(ui.subprocess, "Popen") as spawn:
            self.trial.cleanup()
        environment = spawn.call_args.kwargs["env"]
        self.assertEqual(environment["PATH"], "/original/bin")
        self.assertEqual(environment["QT_QUICK_CONTROLS_STYLE"], "Original")
        self.assertNotIn("TABLET_TEST", environment)

    def test_existing_keyboard_is_not_terminated_during_preflight(self):
        with patch.object(self.trial, "safe", return_value=True), \
                patch.object(ui, "hypr", return_value={"monitor": "eDP-1"}), \
                patch.object(ui.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): self.trial.setup()
            self.trial.cleanup()
        command.assert_not_called()

    def test_failure_or_workspace_exit_stops_trial(self):
        with patch.object(self.trial, "foreground", return_value=False):
            self.trial.tick()
        self.assertTrue(self.trial.stopping)

    def test_cleanup_restores_only_unchanged_trial_settings(self):
        self.trial.owns_journal = True
        self.trial.settings = [["schema", "a", "false", "true"], ["schema", "b", "1.0", "1.45"]]
        def command(*args, **kwargs):
            return SimpleNamespace(stdout="2.0\n" if args[3] == "b" else "true\n")
        with patch.object(ui, "run", side_effect=command) as calls:
            self.trial.cleanup()
        self.assertIn(call("gsettings", "set", "schema", "a", "false"), calls.call_args_list)
        self.assertNotIn(call("gsettings", "set", "schema", "b", "1.0"), calls.call_args_list)

    def test_setup_packages_recovered_keyboard_without_automatic_recording(self):
        panel = Path(self.temp.name)/"panel.qml"
        panel.write_text("normal tablet panel")
        stage = Path(self.temp.name) / "stage.qml"
        stage.write_text("already running tablet stage")
        process = Path(self.temp.name) / "4242"
        process.mkdir()
        (process / "cmdline").write_bytes(b"/store/bin/quickshell\0--path\0" + os.fsencode(stage) + b"\0")
        original = Path.iterdir
        def entries(path):
            return iter([process]) if str(path) == "/proc" else original(path)
        child = Mock(pid=321)
        child.poll.return_value = None
        with patch.dict(os.environ, {"TABLET_NORMAL_PANEL": str(panel), "TABLET_ITERATION_QML": "/store/ui/iteration.qml"}), \
                patch.object(self.trial, "safe", return_value=True), \
                patch.object(ui, "hypr", return_value={"monitor": "eDP-1"}), \
                patch.object(ui.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
                patch.object(ui, "run", return_value=SimpleNamespace(stdout="false\n")) as command, \
                patch.object(ui.subprocess, "Popen", return_value=child) as spawn, \
                patch.object(ui, "start_time", return_value="45"), patch.object(Path, "iterdir", entries), \
                patch.object(self.trial, "start_stage"), patch.object(self.trial, "wait_stage"), \
                patch.object(self.trial, "verify_presentation_policy"):
            self.trial.setup()
        self.assertEqual([c.args[0] for c in spawn.call_args_list], [["squeekboard"], ["quickshell", "--path", "/store/ui/iteration.qml"]])
        self.assertTrue(self.trial.entered)
        self.assertFalse(self.trial.recording)
        self.assertIn(call("tablet-workspace", "enter-iteration"), command.call_args_list)
        self.assertFalse(any(c.args[0] == "voxtype" for c in command.call_args_list))

    def test_recovery_does_not_cancel_unconfirmed_private_daemon(self):
        ui.save("recovery.json", {"target": self.target, "settings": [], "borrowed": False,
                                  "entered": False, "panels": [], "children": [], "voice": True})
        with patch.object(ui.Trial, "voice_state", return_value="recording"), patch.object(ui, "run") as command:
            with self.assertRaises(RuntimeError): ui.recover()
        command.assert_not_called()
        self.assertTrue((ui.directory()/"recovery.json").exists())

    def test_recovery_removes_stale_socket_without_touching_system(self):
        (ui.directory()/"control.sock").touch()
        with patch.object(ui, "run") as command:
            ui.recover()
        command.assert_not_called()
        self.assertFalse((ui.directory()/"control.sock").exists())

    def test_recording_start_failure_is_journaled_as_uncertain_before_signal(self):
        a,b,c = self.voice_context()
        def fail(*args, **kwargs):
            self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])
            raise ui.subprocess.TimeoutExpired("voxtype", 5)
        with a,b,c, patch.object(self.trial, "start_voice"), patch.object(self.trial, "voice_snapshot", return_value=(1, 1, "idle")), \
                patch.object(ui, "run", side_effect=fail):
            with self.assertRaises(ui.subprocess.TimeoutExpired): self.trial.mic()
        self.assertTrue(self.trial.voice_pending)
        self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])
        with patch.object(self.trial, "voice_state", return_value="recording"):
            with self.assertRaises(RuntimeError): self.trial.cancel()
        self.assertTrue(self.trial.voice_pending)

    def test_ownership_inspection_failure_does_not_hide_possible_recording(self):
        a,b,c = self.voice_context()
        with a,b,c, patch.object(self.trial, "start_voice"), patch.object(self.trial, "voice_snapshot", return_value=(1, 1, "idle")), \
                patch.object(self.trial, "await_voice", side_effect=OSError("state inspection failed")), \
                patch.object(ui, "run"):
            with self.assertRaises(OSError): self.trial.mic()
        self.assertTrue(self.trial.voice_pending)
        self.assertFalse(self.trial.recording)
        self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])

    def test_tick_inspection_failure_keeps_voice_guard_through_cleanup(self):
        self.trial.recording = True
        with patch.object(self.trial, "owns_voice", return_value=False), \
                patch.object(self.trial, "voice_state", side_effect=OSError("inspection failed")), \
                patch.object(ui, "run"):
            with self.assertRaises(OSError): self.trial.tick()
            with self.assertRaises(RuntimeError): self.trial.cleanup()
        self.assertFalse(self.trial.recording)
        self.assertTrue(self.trial.voice_guard)
        self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])

    def test_stop_inspection_failure_keeps_voice_guard(self):
        self.trial.recording = True
        with patch.object(self.trial, "owns_voice", return_value=False), \
                patch.object(self.trial, "voice_state", side_effect=OSError("inspection failed")), \
                patch.object(ui.subprocess, "Popen") as spawn:
            with self.assertRaises(OSError): self.trial.stop_voice()
        spawn.assert_not_called()
        self.assertTrue(self.trial.voice_guard)
        self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])

    def test_failed_or_timed_out_waiter_cannot_erase_busy_voice_guard(self):
        for code, state in [(1, "recording"), (4, "transcribing")]:
            with self.subTest(code=code):
                trial = ui.Trial(self.target)
                trial.voice_guard = True
                trial.transcriber = Mock(returncode=code)
                trial.transcriber.poll.return_value = code
                with patch.object(trial, "foreground", return_value=True), \
                        patch.object(trial, "safe", return_value=True), \
                        patch.object(trial, "voice_state", return_value=state), \
                        patch.object(trial, "owns_voice", return_value=False), patch.object(ui, "run"):
                    trial.tick()
                    self.assertIsNone(trial.transcriber)
                    self.assertTrue(trial.voice_pending)
                    with self.assertRaises(RuntimeError): trial.cleanup()
                self.assertTrue(trial.voice_guard)
                self.assertTrue(json.loads((ui.directory()/"recovery.json").read_text())["voice"])

    def test_recovered_child_waits_until_it_really_stops(self):
        with patch.object(ui, "same_live_child", side_effect=[True, True, False]), \
                patch.object(ui.os, "kill") as kill, patch.object(ui.time, "sleep") as sleep:
            ui.stop_recovered_child({"pid": 321, "start": "45"})
        kill.assert_called_once_with(321, ui.signal.SIGTERM)
        sleep.assert_called_once()

    def test_recovery_keeps_journal_for_unstoppable_child_including_waiter(self):
        ui.save("recovery.json", {"target": self.target, "settings": [], "borrowed": False,
                                  "entered": False, "panels": [], "children": [{"pid": 321, "start": "45"}], "voice": False})
        with patch.object(ui, "same_live_child", return_value=True), \
                patch.object(ui.os, "kill"), patch.object(ui.time, "monotonic", side_effect=[0, 4]):
            with self.assertRaises(RuntimeError): ui.recover()
        self.assertEqual(json.loads((ui.directory()/"recovery.json").read_text())["children"], [{"pid": 321, "start": "45"}])

    def test_recovery_refuses_to_interfere_with_active_owner(self):
        # Exclusive-lock behavior is tested independently of any live daemon.
        with (ui.directory()/"owner.lock").open("w") as lock:
            ui.fcntl.flock(lock, ui.fcntl.LOCK_EX | ui.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError): ui.recover()


if __name__ == "__main__":
    unittest.main()
