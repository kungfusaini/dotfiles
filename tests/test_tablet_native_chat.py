import importlib.util
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_chat_backend", ROOT / "home/scripts/desktop/tablet-iterate.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class NativeChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "worktree"
        self.project.mkdir()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name, "XDG_STATE_HOME": self.temp.name + "/state",
                                          "HOME": self.temp.name, "TABLET_NATIVE_CHAT": "1",
                                          "HYPRLAND_INSTANCE_SIGNATURE": "instance"}, clear=True)
        self.env.start()
        self.config = Path(self.temp.name) / ".config/hypr/hyprland.conf"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("layerrule=match:namespace ^tablet-rotation-fade$, no_anim on\n")
        with patch.object(Path, "cwd", return_value=self.project): ui.bind()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_active_external_close_is_immediate_and_never_deferred_to_later_open(self):
        trial = ui.Trial()
        trial.shell = self.process(42)
        trial.view = "external"
        trial.external_ready = True
        apps = Mock(active="browser", pending=None, registry={"browser": {}})
        apps.owned.return_value = {"address":"0xab"}
        with patch.object(trial,"foreground",return_value=True), patch.object(trial,"safe",return_value=True), \
                patch.object(trial,"agent_state",return_value={}), patch.object(trial,"apps",return_value=apps), \
                patch.object(trial,"status",return_value={}), patch.object(trial,"cover_view") as cover:
            trial.app_action("app-close","browser",42)
        apps.focus.assert_called_once_with("browser")
        apps.close.assert_called_once_with("browser")
        cover.assert_not_called()
        self.assertIsNone(trial.close_after_reveal)

    def test_external_actions_reject_retired_frontend_background_voice_and_question(self):
        trial = ui.Trial()
        trial.shell = self.process(42)
        with patch.object(trial,"foreground",return_value=True), patch.object(trial,"safe",return_value=True), \
                patch.object(trial,"agent_state",return_value={}), patch.object(trial,"apps") as apps:
            with self.assertRaises(RuntimeError): trial.app_action("app-open","browser",41)
            trial.recording = True
            with self.assertRaises(RuntimeError): trial.app_action("app-open","browser",42)
            trial.recording = False
            with patch.object(trial,"agent_state",return_value={"question":{"id":"pending"}}):
                with self.assertRaises(RuntimeError): trial.app_action("app-open","browser",42)
            apps.assert_not_called()

    def test_app_tick_failure_falls_back_home_without_stopping_trial(self):
        trial = ui.Trial()
        trial.view = "external"
        trial.window_apps = Mock(active="browser",ownership_escape=False)
        trial.window_apps.tick.side_effect = RuntimeError("window disappeared")
        trial.window_apps.unmanaged_clients.return_value=[]
        trial.close_after_reveal = "browser"
        def home(view): trial.view = view
        with patch.object(trial,"foreground",return_value=True), patch.object(trial,"safe",return_value=True), \
                patch.object(trial,"cover_view",side_effect=home), patch.object(trial,"reveal_entry"), patch.object(trial,"ui_tick"):
            trial.tick()
        self.assertEqual(trial.view,"home")
        self.assertFalse(trial.stopping)
        self.assertIsNone(trial.close_after_reveal)
        self.assertEqual(trial.error,"window disappeared")
        trial.window_apps.park.assert_called_once_with("browser")

    def test_refused_placement_falls_back_home_without_killing_browser_or_trial(self):
        trial = ui.Trial()
        trial.view = "external"
        trial.window_apps = Mock(active="browser",ownership_escape=False)
        trial.window_apps.owned.return_value={"address":"0xab"}
        trial.window_apps.fit.side_effect=RuntimeError("placement refused")
        trial.window_apps.unmanaged_clients.return_value=[]
        def home(view): trial.view=view
        with patch.object(trial,"foreground",return_value=True), patch.object(trial,"safe",return_value=True), \
                patch.object(ui,"hypr",return_value=[{"name":"eDP-1"}]), patch.object(trial,"cover_view",side_effect=home), \
                patch.object(trial,"reveal_entry"), patch.object(trial,"ui_tick"):
            trial.tick()
        self.assertEqual(trial.view,"home")
        self.assertFalse(trial.stopping)
        trial.window_apps.close.assert_not_called()
        trial.window_apps.park.assert_called_once_with("browser")

    def test_parking_failure_never_reveals_home_over_focused_surviving_browser(self):
        trial=ui.Trial()
        trial.view="external"
        trial.window_apps=Mock(active="browser")
        trial.window_apps.owned.return_value={"address":"0xab"}
        trial.window_apps.park.side_effect=RuntimeError("parking refused")
        trial.window_apps.unmanaged_clients.return_value=[]
        with patch.object(trial,"cover_view") as cover:
            with self.assertRaisesRegex(RuntimeError,"Home was not revealed"):
                trial.fail_external("placement refused")
        cover.assert_not_called()
        trial.window_apps.fail.assert_not_called()
        trial.window_apps.close.assert_not_called()

    def test_unmanaged_native_focus_never_gets_hidden_under_failure_home(self):
        trial=ui.Trial()
        trial.view="external"
        trial.window_apps=Mock()
        trial.window_apps.unmanaged_clients.return_value=[{"address":"0xother"}]
        with patch.object(trial,"cover_view") as cover:
            trial.fail_external("app closed")
        self.assertTrue(trial.stopping)
        cover.assert_not_called()
        trial.window_apps.park.assert_not_called()
        trial.window_apps.close.assert_not_called()

    def test_home_parking_failure_keeps_native_view_not_hidden_focus(self):
        trial=ui.Trial()
        trial.view="external"
        trial.window_apps=Mock(active="browser")
        trial.window_apps.park.side_effect=RuntimeError("parking refused")
        def cover(view):trial.view=view
        with patch.object(trial,"cover_view",side_effect=cover),patch.object(trial,"cancel"):
            with self.assertRaisesRegex(RuntimeError,"parking refused"):trial.action("home")
        self.assertEqual(trial.view,"external")
        self.assertFalse(trial.stopping)

    def test_pinned_grouped_app_exits_to_desktop_instead_of_hiding_unowned_focus(self):
        trial=ui.Trial()
        trial.view="external"
        trial.window_apps=Mock(ownership_escape=True)
        with patch.object(trial,"foreground",return_value=True),patch.object(trial,"safe",return_value=True), \
                patch.object(trial,"reveal_entry") as reveal:
            trial.tick()
        self.assertTrue(trial.stopping)
        reveal.assert_not_called()
        trial.window_apps.fit.assert_not_called()
        trial.window_apps.close.assert_not_called()

    def test_incompatible_existing_browser_never_launches_or_changes_view(self):
        trial=ui.Trial()
        trial.shell=self.process(42)
        apps=Mock(registry={"browser":{}},pending=None)
        apps.require_compatible.side_effect=RuntimeError("unverified IME")
        with patch.object(trial,"foreground",return_value=True),patch.object(trial,"safe",return_value=True), \
                patch.object(trial,"agent_state",return_value={}),patch.object(trial,"apps",return_value=apps), \
                patch.object(trial,"cover_view") as cover:
            with self.assertRaisesRegex(RuntimeError,"unverified IME"):trial.app_action("app-open","browser",42)
        cover.assert_not_called()
        apps.open.assert_not_called()
        self.assertEqual(trial.view,"home")

    def test_external_timeout_parks_surviving_focus_before_home(self):
        trial=ui.Trial()
        trial.view="external";trial.entry_pending=True;trial.entry_deadline=0
        trial.window_apps=Mock(active="browser")
        trial.window_apps.unmanaged_clients.return_value=[]
        events=[]
        trial.window_apps.park.side_effect=lambda app:events.append("park")
        with patch.object(trial,"cover_view",side_effect=lambda view:events.append("cover-"+view)):
            trial.reveal_entry()
        self.assertEqual(events,["park","cover-home"])
        trial.window_apps.close.assert_not_called()

    def test_external_timeout_refuses_home_when_surviving_focus_cannot_be_parked(self):
        trial=ui.Trial()
        trial.view="external";trial.entry_pending=True;trial.entry_deadline=0
        trial.window_apps=Mock(active="browser")
        trial.window_apps.unmanaged_clients.return_value=[]
        trial.window_apps.park.side_effect=RuntimeError("parking refused")
        with patch.object(trial,"cover_view") as cover:
            with self.assertRaisesRegex(RuntimeError,"Home was not revealed"):trial.reveal_entry()
        cover.assert_not_called()
        self.assertEqual(trial.view,"external")

    def test_entry_parks_prior_owned_windows_before_entering_home(self):
        trial=ui.Trial()
        apps=Mock(windows={"browser":{}})
        apps.unmanaged_clients.return_value=[]
        with patch.object(trial,"apps",return_value=apps):trial.prepare_app_workspace()
        apps.tick.assert_called_once()
        apps.park.assert_called_once_with("browser")

    def test_entry_refuses_unmanaged_windows_without_moving_them(self):
        trial=ui.Trial()
        apps=Mock(windows={"browser":{}})
        apps.unmanaged_clients.return_value=[{"address":"0xother"}]
        with patch.object(trial,"apps",return_value=apps):
            with self.assertRaisesRegex(RuntimeError,"unowned windows"):trial.prepare_app_workspace()
        apps.park.assert_not_called()
        apps.close.assert_not_called()

    def test_home_cancels_deferred_external_close(self):
        trial = ui.Trial()
        trial.close_after_reveal = "browser"
        with patch.object(trial,"cancel"), patch.object(trial,"cover_view"), patch.object(trial,"return_terminal"), \
                patch.object(trial,"status",return_value={}):
            trial.action("home")
        self.assertIsNone(trial.close_after_reveal)

    def test_unfold_close_refuses_to_discard_unsaved_frontend_draft(self):
        trial = ui.Trial()
        trial.shell = self.process(42)
        with patch.object(trial, "ipc", return_value='{"saved":false}') as ipc, \
                patch.object(trial, "cancel") as cancel:
            with self.assertRaisesRegex(RuntimeError, "draft"):
                trial.action("close")
        ipc.assert_called_once_with(trial.shell, "tabletUi", "persistDraft")
        cancel.assert_not_called()
        self.assertFalse(trial.stopping)

    def test_unfold_close_flushes_draft_before_stopping(self):
        trial = ui.Trial()
        trial.shell = self.process(42)
        events = []
        def persist(*args):
            events.append("persist")
            return '{"saved":true}'
        with patch.object(trial, "ipc", side_effect=persist), \
                patch.object(trial, "cancel", side_effect=lambda: events.append("cancel")), \
                patch.object(trial, "status", return_value={}):
            trial.action("close")
        self.assertEqual(events, ["persist", "cancel"])
        self.assertTrue(trial.stopping)

    def test_recovery_releases_identity_verified_parked_browser(self):
        trial = ui.Trial()
        trial.journal()
        parking = "special:tablet-app-abcdef123456"
        record = {"id": "browser", "address": "0xab", "pid": 42, "start": "start", "tag": "tablet-owned", "parking": parking}
        ui.save("app-windows.json", {"instance": "instance", "windows": {"browser": record}})
        client = {"address": "0xab", "pid": 42, "class": "vivaldi-stable", "tags": ["tablet-owned"], "workspace": {"name": parking}}
        with patch.dict(os.environ, {"TABLET_APPS_MODULE": str(ROOT / "home/scripts/desktop/tablet_apps.py"),
                                     "TABLET_APPS_REGISTRY": str(ROOT / "home/config/quickshell/tablet-home-preview/apps.json")}), \
                patch.object(ui, "hypr", return_value=[client]), patch.object(ui, "start_time", return_value="start"), \
                patch.object(ui.Trial, "cancel"), patch.object(ui.Trial, "return_terminal"), \
                patch.object(ui.Trial, "app_dispatch") as dispatch:
            ui.recover()
        dispatch.assert_called_once_with("movetoworkspacesilent", "name:tablet-trial,address:0xab")
        self.assertFalse((ui.directory() / "recovery.json").exists())

    def test_native_context_has_no_terminal_or_session_identity_requirement(self):
        with patch.object(ui, "start_time", side_effect=AssertionError("must not bind terminal")), \
                patch.object(ui, "hypr", side_effect=AssertionError("must not inspect terminal")):
            target, client = ui.binding()
        self.assertEqual(client, {})
        self.assertEqual(target["pid"], 0)
        self.assertEqual(os.environ["TABLET_CHAT_CWD"], str(self.project))
        self.assertIn("tablet-chat", os.environ["TABLET_CHAT_SESSIONS"])
        context = ui.directory()/"context.json"
        self.assertEqual(context.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("KITTY_PID", json.loads(context.read_text())["project"])

    def test_opening_native_chat_never_moves_a_terminal(self):
        trial = ui.Trial()
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(ui, "dispatch") as dispatch:
            trial.pi()
        dispatch.assert_not_called()
        self.assertFalse(trial.borrowed)
        self.assertEqual(trial.view, "pi")

    def test_home_entry_attaches_without_rebinding_or_navigating(self):
        existing = {"running": True, "view": "pi"}
        with patch.object(ui, "request", return_value=existing) as request, \
                patch.object(ui, "bind") as bind, patch.object(ui.subprocess, "Popen") as spawn:
            self.assertEqual(ui.start_trial("home"), existing)
        request.assert_called_once_with("status")
        bind.assert_not_called()
        spawn.assert_not_called()

    def test_fresh_home_entry_binds_once_and_starts_home_not_pi(self):
        process = self.process(42)
        with patch.dict(os.environ, {"TABLET_ITERATE_BIN": "/store/tablet-chat"}), \
                patch.object(ui, "request", side_effect=[FileNotFoundError(), {"running": True, "view": "home"}]) as request, \
                patch.object(ui, "bind") as bind, patch.object(ui.subprocess, "Popen", return_value=process) as spawn:
            self.assertEqual(ui.start_trial("home")["view"], "home")
        self.assertEqual([call.args[0] for call in request.call_args_list], ["status", "status"])
        bind.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs["env"]["TABLET_START_VIEW"], "home")

    def test_fold_entry_preserves_registered_context_and_marks_automatic(self):
        before = (ui.directory() / "context.json").read_text()
        with patch.dict(os.environ, {"TABLET_ITERATE_BIN": "/store/tablet-chat"}), \
                patch.object(ui, "request", side_effect=[FileNotFoundError(), {"running": True}]), \
                patch.object(ui, "bind") as bind, \
                patch.object(ui.subprocess, "Popen", return_value=self.process(42)) as spawn:
            ui.start_trial("home", automatic=True)
        bind.assert_not_called()
        self.assertEqual((ui.directory() / "context.json").read_text(), before)
        self.assertEqual(spawn.call_args.kwargs["env"]["TABLET_AUTOMATIC"], "1")
        self.assertEqual(spawn.call_args.kwargs["env"]["TABLET_START_VIEW"], "home")

    def test_fold_adopts_existing_manual_home_without_respawning(self):
        with patch.object(ui, "request", return_value={"running": True, "automatic": True}) as request, \
                patch.object(ui, "bind") as bind, patch.object(ui.subprocess, "Popen") as spawn:
            ui.start_trial("home", automatic=True)
        request.assert_called_once_with("adopt-fold")
        bind.assert_not_called()
        spawn.assert_not_called()

    def test_adoption_marks_supervisor_and_workspace_ownership_without_navigation(self):
        trial = ui.Trial()
        trial.view = "pi"
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(trial, "journal") as journal, patch.object(trial, "status", return_value={}), \
                patch.object(ui, "run") as run, patch.object(ui.subprocess, "Popen") as spawn:
            trial.action("adopt-fold")
        run.assert_called_once_with("tablet-workspace", "adopt-fold")
        journal.assert_called_once()
        spawn.assert_not_called()
        self.assertTrue(trial.automatic)
        self.assertTrue(trial.entered)
        self.assertEqual(trial.view, "pi")

    def test_first_fold_uses_home_without_inheriting_project_context(self):
        (ui.directory() / "context.json").unlink()
        with patch.dict(os.environ, {"TABLET_ITERATE_BIN": "/store/tablet-chat", "PROJECT_OBJECT_ID": "not-the-fold-context"}), \
                patch.object(ui, "request", side_effect=[FileNotFoundError(), {"running": True}]), \
                patch.object(ui.subprocess, "Popen", return_value=self.process(42)):
            ui.start_trial("home", automatic=True)
        self.assertEqual(json.loads((ui.directory() / "context.json").read_text()),
                         {"cwd": str(Path.home()), "project": {}})

    def test_manual_home_uses_registered_context_without_automatic_exit(self):
        with patch.dict(os.environ, {"TABLET_ITERATE_BIN": "/store/tablet-chat"}), \
                patch.object(ui, "request", side_effect=[FileNotFoundError(), {"running": True}]), \
                patch.object(ui, "bind") as bind, \
                patch.object(ui.subprocess, "Popen", return_value=self.process(42)) as spawn:
            ui.start_trial("home", registered=True)
        bind.assert_not_called()
        self.assertEqual(spawn.call_args.kwargs["env"]["TABLET_AUTOMATIC"], "0")

    def test_home_entry_does_not_rebind_or_spawn_over_pending_recovery(self):
        ui.save("recovery.json", {"pending": True})
        with patch.object(ui, "request", side_effect=FileNotFoundError()), \
                patch.object(ui, "bind") as bind, patch.object(ui.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "cleanup is pending"):
                ui.start_trial("home")
        bind.assert_not_called()
        spawn.assert_not_called()

    def test_pi_from_home_only_starts_rpc_once_without_another_frontend(self):
        with patch.dict(os.environ, {"TABLET_START_VIEW": "home"}): trial = ui.Trial()
        trial.agent = self.process(42)
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(trial, "ipc", return_value="") as ipc, \
                patch.object(ui, "dispatch") as dispatch, patch.object(ui.subprocess, "Popen") as spawn:
            trial.pi()
            trial.pi()
        ipc.assert_called_once_with(trial.agent, "tabletAgent", "launchPi")
        dispatch.assert_not_called()
        spawn.assert_not_called()
        self.assertTrue(trial.pi_started)
        self.assertEqual(trial.view, "pi")

    def test_preview_wrapper_has_no_standalone_shell_launch_path(self):
        module = (ROOT / "home/modules/tablet-workspace.nix").read_text()
        preview = module.split('name = "tablet-home-preview";', 1)[1].split("voxtype =", 1)[0]
        self.assertIn("tablet-chat start", preview)
        self.assertNotIn("exec quickshell", preview)
        self.assertFalse((ROOT / "home/config/quickshell/tablet-home-preview/shell.qml").exists())

    def test_native_dictation_returns_text_without_paste_or_enter(self):
        trial = ui.Trial()
        trial.view = "pi"
        trial.transcript.write_text("Unsent native draft")
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(ui, "hypr", return_value=[]), patch.object(ui, "dispatch") as dispatch, \
                patch.object(ui, "run") as command:
            result = trial.action("insert")
        self.assertEqual(result["insertText"], "Unsent native draft")
        command.assert_not_called()
        dispatch.assert_not_called()
        self.assertFalse(trial.transcript.exists())

    def test_native_chat_does_not_return_home_when_no_terminal_client_exists(self):
        trial = ui.Trial()
        trial.view = "pi"
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(ui, "hypr", side_effect=AssertionError("no terminal client lookup")):
            trial.tick()
        self.assertEqual(trial.view, "pi")
        self.assertFalse(trial.stopping)

    def process(self, pid):
        process = Mock(pid=pid)
        process.poll.return_value = None
        return process

    def replacement(self, trial, process=None):
        value = {"bundle": "/nix/store/test-ui", "root": str(ui.chat_state() / "ui-roots" / ("a" * 32)),
                 "source": "/nix/store/test-ui/share/tablet-ui/iteration.qml", "token": "token"}
        if process:
            value.update(process=process, deadline=ui.time.monotonic() + 12,
                         handoff={"focused": True, "cursor": 7})
        trial.replacement = value
        trial.ui_update = {"phase": "loading" if process else "queued", "token": "token"}
        return value

    def test_ui_handoff_waits_for_dictation_without_touching_backend(self):
        trial = ui.Trial()
        self.replacement(trial)
        trial.transcript.write_text("Pending dictation")
        with patch.object(trial, "agent_state") as agent, patch.object(ui.subprocess, "Popen") as launch:
            trial.ui_tick()
        agent.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(trial.ui_update["phase"], "queued")
        self.assertEqual(trial.transcript.read_text(), "Pending dictation")

    def test_ui_handoff_waits_for_pending_frontend_actions(self):
        trial = ui.Trial()
        self.replacement(trial)
        with patch.object(trial, "agent_state", return_value={"resetting": False, "awaitingPrompt": False}), \
                patch.object(trial, "ipc", return_value='{"ready":false}'), patch.object(ui.subprocess, "Popen") as launch:
            trial.ui_tick()
        launch.assert_not_called()
        self.assertEqual(trial.ui_update["phase"], "queued")

    def test_handoff_flushes_exact_draft_before_starting_new_ui(self):
        trial = ui.Trial()
        trial.shell, trial.agent = self.process(101), self.process(102)
        self.replacement(trial)
        candidate = self.process(103)
        prepared = {"ready": True, "focused": True, "cursor": 7, "draft": "Draft 🌿 without sending"}
        with patch.object(trial, "agent_state", return_value={"resetting": False, "awaitingPrompt": False}), \
                patch.object(trial, "ipc", return_value=json.dumps(prepared)), patch.object(trial, "journal"), \
                patch.object(ui.subprocess, "Popen", return_value=candidate):
            trial.ui_tick()
        self.assertEqual((ui.chat_state() / "draft.txt").read_text(), prepared["draft"])
        self.assertEqual((ui.chat_state() / "draft.txt").stat().st_mode & 0o777, 0o600)
        self.assertIsNot(trial.shell, candidate)
        self.assertIs(trial.replacement["process"], candidate)
        trial.shell.terminate.assert_not_called()
        trial.agent.terminate.assert_not_called()
        self.assertEqual(trial.ui_update["phase"], "loading")

    def test_ready_handoff_retires_only_old_ui_and_keeps_agent_keyboard(self):
        trial = ui.Trial()
        old, new = self.process(101), self.process(103)
        trial.shell, trial.agent, trial.keyboard = old, self.process(102), self.process(104)
        self.replacement(trial, new)
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(trial, "ipc", return_value=json.dumps({"mapped": True, "rendered": True, "connected": True, "draftRestored": True, "updating": True})), patch.object(trial, "journal"):
            result = trial.ui_ready("token")
        self.assertEqual(result["phase"], "applied")
        self.assertIs(trial.shell, new)
        self.assertEqual(json.loads((ui.chat_state() / "current-ui.json").read_text())["bundle"], "/nix/store/test-ui")
        old.terminate.assert_called_once()
        new.terminate.assert_not_called()
        trial.agent.terminate.assert_not_called()
        trial.keyboard.terminate.assert_not_called()

    def test_failed_candidate_restores_old_interface_and_never_stops_pi(self):
        trial = ui.Trial()
        old, failed = self.process(101), self.process(103)
        trial.shell, trial.agent = old, self.process(102)
        self.replacement(trial, failed)
        failed.poll.return_value = 1
        with patch.object(trial, "ipc") as ipc, patch.object(trial, "journal"):
            trial.ui_tick()
        self.assertEqual(trial.ui_update["phase"], "failed")
        self.assertIs(trial.shell, old)
        old.terminate.assert_not_called()
        trial.agent.terminate.assert_not_called()
        ipc.assert_called_once_with(old, "tabletUi", "activate", "true", "7")
        self.assertFalse((ui.chat_state() / "current-ui.json").exists())

    def test_stale_ui_ack_does_not_retire_the_screen(self):
        trial = ui.Trial()
        trial.shell = self.process(101)
        self.replacement(trial, self.process(103))
        with self.assertRaises(RuntimeError): trial.ui_ready("stale")
        trial.shell.terminate.assert_not_called()

    def test_recovery_journal_owns_both_uis_and_stable_agent(self):
        trial = ui.Trial()
        trial.shell, trial.agent = self.process(101), self.process(102)
        self.replacement(trial, self.process(103))
        trial.stage = self.process(104)
        with patch.object(ui, "start_time", return_value="identity"):
            trial.journal()
        children = json.loads((ui.directory() / "recovery.json").read_text())["children"]
        self.assertEqual({p["pid"] for p in children}, {101, 102, 103, 104})

    def test_new_chat_cannot_clear_pending_dictation(self):
        trial = ui.Trial()
        trial.transcript.write_text("Keep voice")
        requests = ui.directory() / "requests"
        requests.mkdir()
        path = requests / "new"
        path.write_text(json.dumps({"action": "new_chat"}))
        with patch.object(trial, "ipc") as ipc, self.assertRaises(RuntimeError):
            trial.action("agent-command", path=str(path))
        ipc.assert_not_called()
        self.assertEqual(trial.transcript.read_text(), "Keep voice")

    def test_ui_bundle_rejects_backend_changes_and_checkout_sources(self):
        ui.binding()
        store = Path(self.temp.name) / "store"
        bundle = store / "hash-ui"
        source = bundle / "share/tablet-ui"
        source.mkdir(parents=True)
        (source / "iteration.qml").write_text("scene")
        manifest = source / "ui-manifest.json"
        manifest.write_text(json.dumps({"protocol": 1, "backend": "same"}))
        roots = ui.chat_state() / "ui-roots"
        roots.mkdir()
        root = roots / ("a" * 32)
        root.symlink_to(bundle)
        with patch.object(ui, "NIX_STORE", store), patch.dict(os.environ, TABLET_UI_BACKEND="same"):
            self.assertEqual(ui.ui_bundle(str(bundle), str(root)), source)
            manifest.write_text(json.dumps({"protocol": 1, "backend": "changed"}))
            with self.assertRaisesRegex(RuntimeError, "backend"): ui.ui_bundle(str(bundle), str(root))
            with self.assertRaisesRegex(RuntimeError, "immutable"): ui.ui_bundle(str(self.project), str(root))
            root.unlink()
            root.symlink_to(self.project)
            with self.assertRaisesRegex(RuntimeError, "GC root"): ui.ui_bundle(str(bundle), str(root))

    def test_update_builder_selects_bundle_by_manifest_not_output_order(self):
        ui.binding()
        module = self.project / "home/modules/tablet-workspace.nix"
        module.parent.mkdir(parents=True)
        module.touch()
        bundle = Path(self.temp.name) / "bundle"
        source = bundle / "share/tablet-ui"
        source.mkdir(parents=True)
        (source / "ui-manifest.json").write_text("{}")
        outputs = Mock(stdout=f"/unrelated-first-test\n{bundle}\n/unrelated-last-test\n")
        with patch.object(ui.subprocess, "run", return_value=outputs) as build, \
                patch.object(ui, "ui_bundle", return_value=source), \
                patch.object(ui, "request", side_effect=[{"running": True}, {"phase": "queued"}]) as request:
            result = ui.update_ui()
        self.assertEqual(result["phase"], "queued")
        self.assertEqual(request.call_args.kwargs["bundle"], str(bundle))
        commands = [call.args[0] for call in build.call_args_list]
        self.assertEqual(commands[0][:2], ["nix", "build"])
        self.assertIn("--no-link", commands[0])
        self.assertIn("tablet-home-preview.nix", commands[0][-1])
        self.assertIn("tablet-iteration-shell.nix", commands[0][-1])
        self.assertEqual(commands[1][:2], ["nix-store", "--realise"])
        self.assertIn("--add-root", commands[1])
        self.assertFalse(any("deploy-kirax1" in str(c) or "switch" in c for c in commands))

    def test_second_update_cannot_overwrite_still_live_retired_ui_owner(self):
        trial = ui.Trial()
        retired = self.process(100)
        trial.retired_ui = retired
        trial.retired_deadline = ui.time.monotonic() + 3
        self.replacement(trial)
        with patch.object(trial, "agent_state") as agent:
            trial.ui_tick()
        agent.assert_not_called()
        self.assertIs(trial.retired_ui, retired)
        self.assertEqual(trial.ui_update["phase"], "queued")
        retired.kill.assert_not_called()

    def test_ui_handoff_defers_unfinished_dialogs_and_unacknowledged_recovery(self):
        for pending in ([{"question": {"id": "q", "method": method}} for method in ("input", "editor", "select")]
                        + [{"editorVersion": 1, "editorAck": 0}, {"rejectedVersion": 1, "rejectedAck": 0}, {"selectionPending": True}]):
            with self.subTest(pending=pending):
                trial = ui.Trial()
                self.replacement(trial)
                state = dict(pending, resetting=False, awaitingPrompt=False)
                with patch.object(trial, "agent_state", return_value=state), patch.object(trial, "ipc") as ipc:
                    trial.ui_tick()
                ipc.assert_not_called()
                self.assertEqual(trial.ui_update["phase"], "queued")

    def test_new_chat_selection_stays_fresh_until_pi_persists_its_file(self):
        ui.binding()
        (ui.chat_state() / "old.jsonl").write_text("saved old conversation")
        selected = ui.chat_state() / "new.jsonl"
        ui.private_write(ui.chat_state() / "selection.json", json.dumps({"sessionFile": str(selected)}))
        environment = ui.session_environment()
        self.assertEqual(environment["TABLET_CHAT_FORCE_FRESH"], "1")
        self.assertEqual(environment["TABLET_CHAT_RESUME_FILE"], "")
        selected.write_text("saved new conversation")
        environment = ui.session_environment()
        self.assertEqual(environment["TABLET_CHAT_RESUME_FILE"], str(selected))
        self.assertEqual((ui.chat_state() / "old.jsonl").read_text(), "saved old conversation")

    def test_chat_selection_cannot_resume_other_workspace_or_symlink(self):
        ui.binding()
        foreign = self.project / "foreign.jsonl"
        foreign.touch()
        selection = ui.chat_state() / "selection.json"
        ui.private_write(selection, json.dumps({"sessionFile": str(foreign)}))
        with self.assertRaises(RuntimeError): ui.session_environment()
        link = ui.chat_state() / "linked.jsonl"
        link.symlink_to(foreign)
        ui.private_write(selection, json.dumps({"sessionFile": str(link)}))
        with self.assertRaises(RuntimeError): ui.session_environment()

    def test_compositor_transparency_or_wrong_geometry_is_not_coverage(self):
        trial = ui.Trial()
        process = self.process(103)
        layer = {"pid": 103, "namespace": ui.GUARDED_NAMESPACE, "alpha": .5, "w": 1536, "h": 960}
        def hypr(command):
            if command == "monitors": return [{"name": "eDP-1", "width": 1920, "height": 1200, "scale": 1.25}]
            return {"eDP-1": {"levels": {"3": [layer]}}}
        with patch.object(ui, "hypr", side_effect=hypr):
            self.assertFalse(trial.layer_opaque(process, "tablet-stage-cover"))
            layer["alpha"] = 1
            self.assertTrue(trial.layer_opaque(process, "tablet-stage-cover"))
            layer["w"] = 100
            self.assertFalse(trial.layer_opaque(process, "tablet-stage-cover"))
            layer["w"], layer["pid"] = 1536, 999
            self.assertFalse(trial.layer_opaque(process, "tablet-stage-cover"))

    def test_mapping_without_queued_app_frames_cannot_reveal_entry_cover(self):
        trial = ui.Trial()
        trial.shell, trial.stage = self.process(101), self.process(102)
        trial.entry_pending = True
        trial.entry_deadline = ui.time.monotonic() + 20
        with patch.object(trial, "ipc", return_value=json.dumps({"mapped": True, "rendered": False, "connected": True, "draftRestored": True})) as ipc:
            trial.reveal_entry()
        self.assertTrue(trial.entry_pending)
        ipc.assert_called_once_with(trial.shell, "tabletUi", "status")

    def test_replacement_must_be_compositor_opaque_before_retiring_old_ui(self):
        trial = ui.Trial()
        trial.shell, trial.stage = self.process(101), self.process(102)
        self.replacement(trial, self.process(103))
        state = {"mapped": True, "rendered": True, "connected": True, "draftRestored": True, "updating": True}
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(trial, "ipc", return_value=json.dumps(state)), patch.object(trial, "layer_opaque", return_value=False), \
                self.assertRaisesRegex(RuntimeError, "transparent"):
            trial.ui_ready("token")
        trial.shell.terminate.assert_not_called()
        self.assertFalse((ui.chat_state() / "current-ui.json").exists())

    def test_failed_cover_preflight_never_switches_workspace(self):
        trial = ui.Trial()
        with patch.object(trial, "safe", return_value=True), patch.object(ui, "hypr", return_value={"monitor": "eDP-1"}), \
                patch.object(ui.subprocess, "run", return_value=Mock(returncode=1)), \
                patch.object(trial, "selected_ui", return_value="/store/ui/iteration.qml"), \
                patch.object(trial, "start_stage", side_effect=RuntimeError("not opaque")), patch.object(ui, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "opaque"): trial.setup()
        command.assert_not_called()

    def test_stage_is_owned_and_removed_after_workspace_return(self):
        trial = ui.Trial()
        trial.owns_journal = trial.entered = True
        trial.stage, trial.shell = self.process(103), self.process(104)
        (Path(self.temp.name) / "tablet-workspace.json").write_text('{"enabled":true}')
        events = []
        trial.stage.terminate.side_effect = lambda: events.append("stage removed")
        trial.shell.terminate.side_effect = lambda: events.append("UI removed")
        with patch.object(ui, "run", side_effect=lambda *a, **k: events.append(a[1]) if a[0] == "tablet-workspace" else None):
            trial.cleanup()
        self.assertLess(events.index("UI removed"), events.index("leave-automatic"))
        self.assertLess(events.index("leave-automatic"), events.index("stage removed"))

    def test_home_cancels_voice_then_covers_before_releasing_the_app(self):
        trial = ui.Trial()
        trial.stage = self.process(103)
        trial.view = "pi"
        events = []
        with patch.object(trial, "cancel", side_effect=lambda: events.append("voice resolved")), \
                patch.object(trial, "ipc", side_effect=lambda *a: events.append("cover requested")), \
                patch.object(trial, "wait_stage", side_effect=lambda: events.append("opaque")), \
                patch.object(trial, "return_terminal", side_effect=lambda: events.append("old app released")), \
                patch.object(trial, "status", return_value={}):
            trial.action("home")
        self.assertEqual(events, ["voice resolved", "cover requested", "opaque", "old app released"])
        self.assertEqual(trial.view, "home")
        self.assertTrue(trial.entry_pending)

    def test_duplicate_layer_cannot_substitute_for_a_new_opaque_surface(self):
        trial = ui.Trial()
        process = self.process(103)
        layers = [{"pid": 103, "namespace": ui.GUARDED_NAMESPACE, "alpha": 1, "w": 800, "h": 600},
                  {"pid": 103, "namespace": ui.GUARDED_NAMESPACE, "alpha": .1, "w": 800, "h": 600}]
        def hypr(command):
            if command == "monitors": return [{"name": "eDP-1", "width": 800, "height": 600}]
            return {"eDP-1": {"levels": {"3": layers}}}
        with patch.object(ui, "hypr", side_effect=hypr):
            self.assertFalse(trial.layer_opaque(process, "tablet-stage-cover"))

    def test_guarded_namespace_requires_deployed_no_animation_policy(self):
        trial = ui.Trial()
        trial.verify_presentation_policy()
        self.config.write_text("# alpha.goal() cannot prove current opacity during animations\n")
        with self.assertRaisesRegex(RuntimeError, "no_anim"):
            trial.verify_presentation_policy()
        self.config.unlink()
        with self.assertRaisesRegex(RuntimeError, "refusing workspace entry"):
            trial.verify_presentation_policy()

    def test_input_panel_targets_only_verified_owned_unique_bus_peer(self):
        trial = ui.Trial()
        trial.shell, trial.keyboard = self.process(101), self.process(102)
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(ui, "run", side_effect=[Mock(stdout="(':1.24',)"), Mock(stdout="(uint32 102,)"), Mock(stdout="()")]) as run:
            self.assertEqual(trial.input_panel(False, 101), {"accepted": True, "visible": False})
        command = run.call_args_list[-1].args
        self.assertEqual(command[command.index("--dest") + 1], ":1.24")
        self.assertEqual(command[-1], "false")

    def test_input_panel_refuses_foreign_keyboard_owner(self):
        trial = ui.Trial()
        trial.shell, trial.keyboard = self.process(101), self.process(102)
        with patch.object(trial, "foreground", return_value=True), patch.object(trial, "safe", return_value=True), \
                patch.object(ui, "run", side_effect=[Mock(stdout="(':1.24',)"), Mock(stdout="(uint32 999,)")]) as run:
            with self.assertRaisesRegex(RuntimeError, "not owned"):
                trial.input_panel(False, 101)
        self.assertEqual(run.call_count, 2)

    def test_retired_frontend_cannot_hide_new_frontends_keyboard(self):
        trial = ui.Trial()
        trial.shell, trial.keyboard = self.process(101), self.process(102)
        with patch.object(ui, "run") as run:
            self.assertEqual(trial.input_panel(False, 99), {"accepted": False})
        run.assert_not_called()

    def test_delayed_input_panel_request_cannot_show_over_home(self):
        trial = ui.Trial()
        trial.shell, trial.keyboard = self.process(101), self.process(102)
        trial.view = "home"
        with patch.object(ui, "run") as run:
            self.assertEqual(trial.input_panel(True, 101), {"accepted": False})
        run.assert_not_called()

    def test_background_tablet_cannot_change_keyboard_visibility(self):
        trial = ui.Trial()
        trial.shell, trial.keyboard = self.process(101), self.process(102)
        with patch.object(trial, "foreground", return_value=False), patch.object(ui, "run") as run:
            self.assertEqual(trial.input_panel(False, 101), {"accepted": False})
        run.assert_not_called()

    def test_native_home_refuses_to_discard_pending_dictation(self):
        trial = ui.Trial()
        trial.native_chat = True
        trial.view = "pi"
        trial.voice_pending = True
        with patch.object(trial, "cancel") as cancel:
            with self.assertRaisesRegex(RuntimeError, "Finish or cancel dictation"):
                trial.action("home")
            cancel.assert_not_called()
        self.assertEqual(trial.view, "pi")

    def test_retired_polling_client_cannot_tear_down_the_supervisor(self):
        trial = ui.Trial()
        connection = Mock()
        connection.recv.return_value = b'{"command":"status"}'
        connection.sendall.side_effect = BrokenPipeError()
        with patch.object(trial, "status", return_value={"running": True}):
            ui.respond(trial, connection)
        self.assertFalse(trial.stopping)
        self.assertEqual(trial.error, "")

    def test_retired_client_eof_or_reset_is_not_a_trial_failure(self):
        trial = ui.Trial()
        connection = Mock()
        connection.recv.return_value = b""
        ui.respond(trial, connection)
        connection.sendall.assert_not_called()
        connection.recv.side_effect = ConnectionResetError()
        ui.respond(trial, connection)
        self.assertFalse(trial.stopping)
        self.assertEqual(trial.error, "")

    def test_nonreading_large_poll_reply_timeout_is_not_a_trial_exit(self):
        trial = ui.Trial()
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
            receiver.sendall(b'{"command":"status"}')
            with patch.object(trial, "status", return_value={"running": True, "fixture": "x" * 1048576}):
                ui.respond(trial, sender)
        self.assertFalse(trial.stopping)
        self.assertEqual(trial.error, "")

    def test_deleted_worktree_refuses_context_instead_of_silently_switching(self):
        self.project.rmdir()
        with self.assertRaises(RuntimeError): ui.binding()


if __name__ == "__main__":
    unittest.main()
