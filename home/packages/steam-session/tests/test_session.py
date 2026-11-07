"""No Steam, GUI, account API or real saves are touched by these tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in [('STATE_DIR', self.root), ('LOGS', self.root)]:
            m = patch.object(session.steam, name, value)
            m.start()
            self.addCleanup(m.stop)
        m = patch.object(session, 'STATE', self.root / 'session.json')
        m.start()
        self.addCleanup(m.stop)
        self.game = dict(appid=1687950, state_flags=6)

    def test_dispatch_independent_service_retains_workspace_and_waits(self):
        with patch.object(session, 'invoking_workspace', return_value='Machine · Games'), \
             patch.object(session.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(session.dispatch(1687950), 0)
        args = run.call_args.args[0]
        self.assertIn('--wait', args)
        self.assertIn('--collect', args)
        self.assertNotIn('--pipe', args)
        self.assertIn('--setenv=PROJECT_OBJECT_WORKSPACE_NAME=Machine · Games', args)
        self.assertEqual(args[-2:], ['--worker', '1687950'])
        self.assertFalse(any('TOKEN' in arg or 'SECRET' in arg for arg in args))

    def test_full_launch_exit_cleanup_order_and_pending_installed_update(self):
        events = []
        with patch.object(session.steam, 'manifests', return_value=[self.game]), \
             patch.object(session.steam, 'running_game_appids', return_value=[]), \
             patch.object(session.steam, 'start_steam', side_effect=lambda *_: events.append('start')), \
             patch.object(session.steam, 'wait_steam_ready', side_effect=lambda *_: events.append('ready')), \
             patch.object(session.steam, 'request_url', side_effect=lambda *a, **kw: events.append(('request', a, kw))), \
             patch.object(session.steam, 'wait_game', side_effect=lambda *a, **kw: events.append(('wait', a, kw))), \
             patch.object(session, 'cleanup', side_effect=lambda *_: events.append('cleanup')):
            self.assertEqual(session.worker(1687950), 0)
        self.assertEqual(events[0:2], ['start', 'ready'])
        self.assertEqual(events[2], ('request', ('steam://rungameid/1687950',), {'approved': True}))
        self.assertEqual(events[3], ('wait', (1687950, 86400), {'startup_timeout': 180}))
        self.assertEqual(events[-1], 'cleanup')
        self.assertEqual(json.loads(session.STATE.read_text())['phase'], 'finished-steam-closed')

    def test_failed_launch_still_attempts_guarded_cleanup(self):
        events = []
        with patch.object(session.steam, 'manifests', return_value=[self.game]), \
             patch.object(session.steam, 'running_game_appids', return_value=[]), \
             patch.object(session.steam, 'start_steam', side_effect=session.steam.SteamError('startup failed')), \
             patch.object(session, 'cleanup', side_effect=lambda *_: events.append('cleanup')) as cleanup, \
             patch.object(session, 'notify', side_effect=lambda *_: events.append('notify')) as notify:
            self.assertEqual(session.worker(1687950), 1)
            cleanup.assert_called_once_with(1687950)
            notify.assert_called_once()
            self.assertEqual(events, ['notify', 'cleanup'])
        self.assertEqual(json.loads(session.STATE.read_text())['phase'], 'needs-attention')

    def test_uninstalled_or_already_running_game_never_takes_cleanup_ownership(self):
        for games, running in [([], []), ([self.game], [1687950])]:
            with self.subTest(games=games), patch.object(session.steam, 'manifests', return_value=games), \
                 patch.object(session.steam, 'running_game_appids', return_value=running), \
                 patch.object(session, 'cleanup') as cleanup, patch.object(session.steam, 'start_steam') as start:
                with self.assertRaises(session.steam.SteamError):
                    session.worker(1687950)
                cleanup.assert_not_called()
                start.assert_not_called()

    def test_duplicate_worker_never_launches_or_stops_existing_session(self):
        with (self.root / 'session.lock').open('w') as lock:
            session.fcntl.flock(lock, session.fcntl.LOCK_EX | session.fcntl.LOCK_NB)
            with patch.object(session.steam, 'manifests', return_value=[self.game]), \
                 patch.object(session, 'cleanup') as cleanup, patch.object(session.steam, 'start_steam') as start:
                with self.assertRaisesRegex(session.steam.SteamError, 'already owns'):
                    session.worker(1687950)
                start.assert_not_called()
                cleanup.assert_not_called()

    def test_cleanup_waits_for_real_work_and_stops_without_override(self):
        with patch.object(session.steam, 'steam_running', side_effect=[True, True, False]), \
             patch.object(session.steam, 'shutdown_blockers', side_effect=[{'games': [1]}, {'games': []}]), \
             patch.object(session.steam, 'settle') as settle, patch.object(session.steam, 'stop_steam') as stop, \
             patch.object(session.time, 'sleep'):
            session.cleanup(1687950)
            settle.assert_called_once_with(20, 60)
            stop.assert_called_once_with(90, force=False, approved=False, override_active=False)

    def test_cleanup_rechecks_activity_after_settling(self):
        with patch.object(session.steam, 'steam_running', side_effect=[True, True, False]), \
             patch.object(session.steam, 'shutdown_blockers', side_effect=[{'games': []}, {'games': [1]}, {'games': []}]), \
             patch.object(session.steam, 'settle'), \
             patch.object(session.steam, 'stop_steam', side_effect=[session.steam.SteamError('activity'), {}]) as stop:
            session.cleanup(1687950)
            self.assertEqual(stop.call_count, 2)

    def test_cleanup_off_client_does_not_wait_for_history(self):
        with patch.object(session.steam, 'steam_running', return_value=False), \
             patch.object(session.steam, 'shutdown_blockers') as blockers, \
             patch.object(session.steam, 'stop_hide_watch') as watcher:
            session.cleanup(1687950)
            blockers.assert_not_called()
            watcher.assert_called_once()

    def test_workspace_comes_from_invoking_ancestor_not_active_workspace(self):
        clients = [dict(pid=200, workspace=dict(name='Invoking game library')),
                   dict(pid=300, workspace=dict(name='Unrelated active workspace'))]
        with patch.object(session.os, 'getpid', return_value=100), \
             patch.object(session, 'parent_pid', side_effect=lambda pid: {100: 200, 200: 1}[pid]), \
             patch.object(session.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(clients))):
            self.assertEqual(session.invoking_workspace(), 'Invoking game library')

    def test_no_workspace_is_fail_closed(self):
        with patch.dict(session.os.environ, {}, clear=True), \
             patch.object(session.os, 'getpid', return_value=100), \
             patch.object(session, 'parent_pid', return_value=1), \
             patch.object(session.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[]')):
            with self.assertRaises(session.steam.SteamError):
                session.invoking_workspace()

    def test_game_start_failure_bounded_and_marker_removed(self):
        marker = session.steam.launch_marker_path(1687950)
        marker.write_text(json.dumps(dict(inode=0, offset=0)))
        with patch.object(session.steam, 'running_game_appids', return_value=[]), \
             patch.object(session.steam, 'steam_running', return_value=True), \
             patch.object(session.steam.time, 'monotonic', side_effect=[0, 0, 0, 2]), \
             patch.object(session.steam.time, 'sleep'):
            with self.assertRaisesRegex(session.steam.SteamError, 'not observed starting'):
                session.steam.wait_game(1687950, 60, startup_timeout=1)
        self.assertFalse(marker.exists())

    def test_very_short_game_is_detected_from_fresh_start_and_exit_records(self):
        log = self.root / 'gameprocess_log.txt'
        log.write_text('AppID 1687950 adding PID 100 as a tracked process\n'
                       'AppID 1687950 no longer tracking PID 100, exit code 0\n')
        marker = session.steam.launch_marker_path(1687950)
        marker.write_text(json.dumps(dict(inode=log.stat().st_ino, offset=0)))
        with patch.object(session.steam, 'running_game_appids', return_value=[]):
            result = session.steam.wait_game(1687950, 60, startup_timeout=1)
        self.assertTrue(result['started'] and result['exited'])
        self.assertFalse(marker.exists())

    def test_game_request_requires_verified_workspace_helper(self):
        s = session.steam
        with patch.object(s, 'steam_running', return_value=True), \
             patch.object(s.shutil, 'which', side_effect=['steam', 'project-workspace-exec']), \
             patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(s.subprocess, 'Popen') as popen, patch.object(s, 'hide_windows', return_value=0), \
             patch.object(s.time, 'sleep'):
            s.request_url('steam://rungameid/1687950', approved=True)
            self.assertEqual(run.call_args.args[0], ['project-workspace-exec', 'steam', 'steam://rungameid/1687950'])
            popen.assert_not_called()

    def test_game_placement_failure_never_falls_back_to_unrouted_launch(self):
        s = session.steam
        with patch.object(s, 'steam_running', return_value=True), \
             patch.object(s.shutil, 'which', side_effect=['steam', 'project-workspace-exec']), \
             patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)), \
             patch.object(s.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(s.SteamError, 'placement'):
                s.request_url('steam://rungameid/1687950', approved=True)
            popen.assert_not_called()

    def test_background_start_placement_error_is_not_ignored(self):
        s = session.steam
        with patch.object(s, 'steam_running', return_value=False), \
             patch.object(s, 'start_hide_watch'), \
             patch.object(s.shutil, 'which', side_effect=['steam', 'project-workspace-exec']), \
             patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)), \
             patch.object(s.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(s.SteamError, 'placement'):
                s.start_steam(120)
            popen.assert_not_called()

    def test_long_protected_activity_notifies_without_forcing_or_expiring_it(self):
        with patch.object(session.time, 'monotonic', side_effect=[0, 1, 301, 302, 303]), \
             patch.object(session.time, 'sleep'), patch.object(session, 'notify') as notify, \
             patch.object(session.steam, 'steam_running', side_effect=[True, True, False]), \
             patch.object(session.steam, 'shutdown_blockers', return_value={'games': [400]}), \
             patch.object(session.steam, 'stop_steam') as stop, patch.object(session.steam, 'stop_hide_watch'):
            session.cleanup(1687950, timeout=1000)
            notify.assert_called_once()
            stop.assert_not_called()

    def test_ready_check_cannot_reuse_previous_session_login(self):
        with patch.object(session.steam, 'current_session_lines', return_value=[]), \
             patch.object(session.steam, 'steam_running', return_value=False), \
             patch.object(session.steam, 'hide_windows'):
            with self.assertRaisesRegex(session.steam.SteamError, 'before login'):
                session.steam.wait_steam_ready(10)


if __name__ == '__main__':
    unittest.main()
