"""Manual/automated ownership contracts; no real client or compositor access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import manual
import steamctl as s


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for key, value in {'STATE_DIR': root, 'MANUAL_SESSION': root / 'manual.json',
                           'VISIBILITY_LOCK': root / 'visibility.lock',
                           'HIDE_WATCH_PID': root / 'watch.pid'}.items():
            p = patch.object(s, key, value)
            p.start()
            self.addCleanup(p.stop)

    def lease(self):
        s.record_manual_session([os.getpid()])

    def test_lease_is_valid_only_for_exact_process_lifetime(self):
        self.lease()
        self.assertEqual(s.manual_session_pids(), [os.getpid()])
        record = json.loads(s.MANUAL_SESSION.read_text())
        record[0]['start_ticks'] += 1
        s.MANUAL_SESSION.write_text(json.dumps(record))
        self.assertEqual(s.manual_session_pids(), [])

    def test_missing_dead_and_malformed_leases_do_not_affect_next_client(self):
        for text in ['null', '{}', '[{"pid": 999999999, "start_ticks": 42}]', 'not json']:
            s.MANUAL_SESSION.write_text(text)
            self.assertEqual(s.manual_session_pids(), [])

    def test_manual_lease_disables_all_hiding_even_if_called_explicitly(self):
        self.lease()
        with patch.object(s, '_hide_windows') as hide, patch.object(s.subprocess, 'Popen') as spawn:
            self.assertEqual(s.hide_windows(), 0)
            s.start_hide_watch()
            hide.assert_not_called()
            spawn.assert_not_called()

    def test_manual_client_is_a_shutdown_blocker_and_never_receives_shutdown(self):
        self.lease()
        with patch.object(s, 'steam_running', return_value=True), \
             patch.object(s, 'running_game_appids', return_value=[]), \
             patch.object(s, 'active_download_appids', return_value=[]), \
             patch.object(s, 'active_cloud_appids', return_value=[]), \
             patch.object(s.subprocess, 'run') as run:
            with self.assertRaisesRegex(s.SteamError, 'manual_client'):
                s.stop_steam(10, False, False, False)
            run.assert_not_called()

    def test_rule_installation_respects_manual_lease(self):
        self.lease()
        with patch.object(s.subprocess, 'run') as run:
            self.assertEqual(s.configure_hidden_rule(), {'manual': True})
            run.assert_not_called()

    def test_automated_rule_is_class_scoped_and_enabled_only_when_complete(self):
        with patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')) as run:
            self.assertEqual(s.configure_hidden_rule(), {'manual': False})
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-2:], ['windowrule[project-object-steam-hidden]:enable', '0'])
        self.assertIn('^([Ss]team)$', commands[1])
        self.assertIn('special:steam-hidden silent', commands[2])
        self.assertEqual(commands[-1][-1], '1')

    def test_rule_install_failure_never_enables_partial_rule(self):
        with patch.object(s.subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, 'ok'), subprocess.CompletedProcess([], 1, 'error')]) as run:
            with self.assertRaises(s.SteamError):
                s.configure_hidden_rule()
        self.assertEqual(run.call_count, 2)

    def test_background_hiding_still_runs_without_valid_manual_lease(self):
        with patch.object(s, '_hide_windows', return_value=3) as hide:
            self.assertEqual(s.hide_windows(), 3)
            hide.assert_called_once()

    def test_agent_context_never_falls_back_to_active_workspace(self):
        with patch.dict(os.environ, {'PROJECT_OBJECT_WORKSPACE_NAME': 'Agent workspace'}), \
             patch.object(manual.session, 'invoking_workspace', return_value='Agent workspace'), \
             patch.object(manual, 'hypr') as hypr:
            self.assertEqual(manual.workspace(desktop=True), 'Agent workspace')
            hypr.assert_not_called()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(manual.session, 'invoking_workspace', side_effect=s.SteamError('missing')), \
             patch.object(manual, 'hypr') as hypr:
            with self.assertRaises(s.SteamError):
                manual.workspace()
            hypr.assert_not_called()

    def test_workspace_launcher_identity_wins_over_desktop_and_ancestor_context(self):
        with patch.dict(os.environ, {'PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME': 'Verified invoking workspace',
                                     'PROJECT_OBJECT_WORKSPACE_NAME': 'Older worker workspace'}), \
             patch.object(manual.session, 'invoking_workspace') as ancestor, \
             patch.object(manual, 'hypr') as hypr:
            self.assertEqual(manual.workspace(desktop=True), 'Verified invoking workspace')
            ancestor.assert_not_called()
            hypr.assert_not_called()

    def test_human_desktop_entry_can_use_current_workspace(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(manual, 'hypr', return_value='{"name": "Human workspace"}'):
            self.assertEqual(manual.workspace(desktop=True), 'Human workspace')

    def test_existing_client_takeover_precedes_open_and_does_not_stop_work(self):
        events = []
        def hypr(*args):
            events.append(args)
            self.assertTrue(s.manual_session_pids())
            return 'ok'
        with patch.object(s, 'steam_main_pids', return_value=[os.getpid()]), \
             patch.object(manual.shutil, 'which', return_value='/bin/steam'), \
             patch.object(manual, 'hypr', side_effect=hypr), \
             patch.object(manual, 'place_windows', return_value=True), \
             patch.object(s, 'stop_hide_watch') as watch, \
             patch.object(manual.time, 'monotonic', side_effect=[0, 0, 0, 20]), \
             patch.object(s, 'stop_steam') as stop:
            manual.open_manual('Invoking workspace', [])
            self.assertEqual(events[0], ('keyword', 'windowrule[project-object-steam-hidden]:enable', '0'))
            self.assertIn('workspace name:Invoking workspace silent', events[1][-1])
            watch.assert_called_once()
            stop.assert_not_called()
            self.assertEqual(s.manual_session_pids(), [os.getpid()])

    def test_placement_requires_exact_address_and_live_client_ancestry(self):
        window = dict(address='0xab', mapped=True, pid=123, workspace={'name': 'hidden'})
        moved = dict(window, workspace={'name': 'Target'})
        with patch.object(s, 'steam_windows', side_effect=[[window], [moved]]), \
             patch.object(manual, 'owns_window', return_value=True), \
             patch.object(manual, 'hypr', return_value='ok') as hypr:
            self.assertTrue(manual.place_windows('Target'))
            hypr.assert_called_once_with('dispatch', 'movetoworkspacesilent', 'name:Target,address:0xab')
        with patch.object(s, 'steam_windows', return_value=[window]), \
             patch.object(manual, 'owns_window', return_value=False), \
             patch.object(manual, 'hypr') as hypr:
            self.assertFalse(manual.place_windows('Target'))
            hypr.assert_not_called()

    def test_already_routed_windows_are_not_moved_back_after_human_moves_them(self):
        window = dict(address='0xab', mapped=True, pid=123, workspace={'name': 'Human choice'})
        with patch.object(s, 'steam_windows', return_value=[window]), \
             patch.object(manual, 'owns_window', return_value=True), \
             patch.object(manual, 'hypr') as hypr:
            self.assertFalse(manual.place_windows('Target', {'0xab'}))
            hypr.assert_not_called()

    def test_startup_timeout_cannot_bypass_manual_shutdown_guard(self):
        self.lease()
        with patch.object(s, 'steam_running', side_effect=[False, True]), \
             patch.object(s, 'start_hide_watch'), \
             patch.object(s.shutil, 'which', side_effect=['steam', 'project-workspace-exec']), \
             patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(s, 'running_game_appids', return_value=[]), \
             patch.object(s, 'active_download_appids', return_value=[]), \
             patch.object(s, 'active_cloud_appids', return_value=[]), \
             patch.object(s.time, 'monotonic', side_effect=[0, 20]):
            with self.assertRaisesRegex(s.SteamError, 'guarded cleanup'):
                s.start_steam(10)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], ['project-workspace-exec', 'steam', '-silent'])

    def test_failed_takeover_does_not_close_client_or_cancel_download(self):
        with patch.object(s, 'steam_main_pids', return_value=[os.getpid()]), \
             patch.object(manual.shutil, 'which', return_value='/bin/steam'), \
             patch.object(manual, 'hypr', return_value='error'), \
             patch.object(s, 'stop_steam') as stop:
            with self.assertRaises(s.SteamError):
                manual.open_manual('Target', [])
            stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
