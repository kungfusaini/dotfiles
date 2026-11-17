"""Scoped Pegasus identities and launch receipts without host games or compositor."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gaming', ROOT / 'home/packages/tablet-proof/gaming.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GamingTests(unittest.TestCase):
    def setUp(self):
        original_umask = os.umask(0o022)
        os.umask(original_umask)
        self.addCleanup(os.umask, original_umask)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, XDG_RUNTIME_DIR=self.tmp.name, HYPRLAND_INSTANCE_SIGNATURE='test')
        env.start(); self.addCleanup(env.stop)
        self.start = patch.object(g, 'start', return_value='lifetime')
        self.start.start(); self.addCleanup(self.start.stop)
        self.window = dict(address='0xab', pid=42, stableId='abc', **{'class': 'pegasus-fe'},
                           mapped=True, workspace={'name': g.WORKSPACE})
        self.clients = [self.window]
        self.hypr = Mock(side_effect=lambda command: self.clients)
        self.dispatch = Mock()
        self.games = g.Games(self.hypr, self.dispatch)
        self.pegasus = dict(pid=42, start='lifetime', token='token')

    def register(self):
        g.write('pegasus.json', self.pegasus)

    def test_receipts_are_compositor_bound_and_private(self):
        self.register()
        self.assertEqual((g.root() / 'pegasus.json').stat().st_mode & 0o777, 0o600)
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='other'):
            self.assertEqual(g.read('pegasus.json'), {})

    def test_same_pid_cannot_substitute_recycled_window_or_other_workspace(self):
        record = g.identity(self.window)
        self.assertIs(g.find(record, self.clients), self.window)
        self.window['stableId'] = 'def'
        self.assertIsNone(g.find(record, self.clients))
        self.window['stableId'] = 'abc'
        self.window['workspace']['name'] = 'laptop'
        self.assertIsNone(g.find(record, self.clients))

    def test_xwayland_game_allowed_but_floating_pinned_grouped_refused(self):
        self.window['xwayland'] = True
        self.assertTrue(g.local(self.window))
        for key in ['floating', 'pinned', 'grouped']:
            self.window[key] = True
            self.assertFalse(g.local(self.window))
            self.window[key] = False

    def test_pegasus_requires_exact_executable_token_and_lifetime(self):
        with patch.object(g, 'executable', return_value='pegasus-fe'), \
                patch.object(g, 'environment', return_value={'TABLET_PEGASUS_TOKEN': 'token'}):
            self.assertIs(g.pegasus_client(self.pegasus, self.clients), self.window)
            self.assertIsNone(g.pegasus_client(dict(self.pegasus, token='other'), self.clients))
            self.assertIsNone(g.pegasus_client(dict(self.pegasus, start='old'), self.clients))
        with patch.object(g, 'executable', return_value='unrelated'):
            self.assertIsNone(g.pegasus_client(self.pegasus, self.clients))

    def test_desktop_pegasus_is_not_adopted_or_relaunched(self):
        self.window['workspace']['name'] = 'laptop'
        with self.assertRaisesRegex(RuntimeError, 'desktop Pegasus'):
            self.games.launch()
        self.dispatch.assert_not_called()

    def test_launch_uses_creation_workspace_and_new_token(self):
        self.clients.clear()
        self.games.launch()
        self.assertIn('[workspace name:tablet-trial silent] env TABLET_PEGASUS_TOKEN=', self.dispatch.call_args.args[1])
        self.dispatch.assert_called_once()
        self.games.launch()
        self.dispatch.assert_called_once()

    def test_ambiguous_new_pegasus_is_never_registered(self):
        self.clients.clear(); self.games.launch()
        self.clients.extend([self.window, dict(self.window, address='0xac', stableId='def')])
        with patch.object(g, 'executable', return_value='pegasus-fe'), \
                patch.object(g, 'environment', return_value={'TABLET_PEGASUS_TOKEN': self.games.pending['token']}):
            self.games.tick()
        self.assertEqual(g.read('pegasus.json'), {})
        self.assertIn('uniquely verified', self.games.error)

    def test_receipt_game_is_never_adopted_from_another_pegasus_session(self):
        self.register()
        g.write('launch.json', dict(token='other', game=g.identity(self.window)))
        self.assertIsNone(self.games.game())
        g.write('launch.json', dict(token='token', game=g.identity(self.window)))
        self.assertIs(self.games.game(), self.window)

    def test_steam_handoff_requires_exact_appid_and_new_tablet_window(self):
        with patch.object(g, 'environment', return_value={'SteamAppId': '123'}):
            self.assertTrue(g.authorized_game(self.window, ['steam-session', '123'], {}, []))
            self.assertFalse(g.authorized_game(self.window, ['steam-session', '124'], {}, []))
            self.assertFalse(g.authorized_game(self.window, ['steam-session', '123'], {}, ['0xab']))
            self.window['workspace']['name'] = 'laptop'
            self.assertFalse(g.authorized_game(self.window, ['steam-session', '123'], {}, []))

    def test_floating_game_requires_exact_steam_identity_and_workspace(self):
        self.window['floating'] = True
        self.assertFalse(g.local(self.window))  # Still not a Pegasus candidate.
        with patch.object(g, 'environment', return_value={'SteamAppId': '123'}):
            self.assertTrue(g.authorized_game(self.window, ['steam-session', '123'], {}, []))
            self.assertFalse(g.authorized_game(self.window, ['steam-session', '124'], {}, []))
            self.window['pinned'] = True
            self.assertFalse(g.authorized_game(self.window, ['steam-session', '123'], {}, []))

    def test_native_handoff_requires_launch_descendant(self):
        with patch.object(g, 'descendant', return_value=False):
            self.assertFalse(g.authorized_game(self.window, ['pcsx2-qt'], {}, []))
        with patch.object(g, 'descendant', return_value=True):
            self.assertTrue(g.authorized_game(self.window, ['pcsx2-qt'], {}, []))

    def test_desktop_launch_is_exact_exec_passthrough(self):
        with patch.object(g.os, 'execvp', side_effect=SystemExit) as execute:
            with self.assertRaises(SystemExit):
                g.launch(['steam-session', '123'])
        execute.assert_called_once_with('steam-session', ['steam-session', '123'])
        self.assertFalse((g.root() / 'launch.json').exists())

    def test_worker_crash_before_verification_blocks_relaunch_without_guessing_exit(self):
        self.register()
        g.write('launch.json', dict(token='token', phase='launching', game=None,
                                  owner={'pid': 99, 'start': 'dead'},
                                  child={'pid': 100, 'start': 'possibly-running'}))
        with patch.object(g, 'descendant', return_value=True), \
                patch.object(g, 'executable', return_value='pegasus-fe'), \
                patch.object(g, 'environment', return_value={'TABLET_PEGASUS_TOKEN': 'token'}), \
                patch.object(g.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'unresolved'):
                g.launch(['test-game'])
        launch.assert_not_called()
        self.assertEqual(g.read('launch.json')['child']['pid'], 100)

    def test_desktop_passthrough_preserves_umask_and_works_without_hyprland(self):
        self.register()
        with patch.dict(os.environ):
            del os.environ['HYPRLAND_INSTANCE_SIGNATURE']
            with patch.object(g.os, 'umask') as mask, patch.object(g.os, 'execvp', side_effect=SystemExit) as execute:
                with self.assertRaises(SystemExit):
                    g.launch(['test-game', '--fullscreen'])
            mask.assert_not_called()
            execute.assert_called_once_with('test-game', ['test-game', '--fullscreen'])

    def test_worker_invalid_request_never_starts_game(self):
        g.write('launch.json', dict(request='nonce', command=g.command_hash(['test-game'])))
        with patch.object(g.subprocess, 'Popen') as launch:
            for request, command in [('wrong', ['test-game']), ('nonce', ['other'])]:
                with self.assertRaisesRegex(RuntimeError, 'Invalid tablet game'):
                    g.worker(command, request)
        launch.assert_not_called()

    def test_worker_waits_for_game_and_cleanup_without_kill(self):
        self.register()
        command = ['steam-session', '123']
        record = dict(request='nonce', token='token', command=g.command_hash(command), phase='launching',
                      game=None, caller={'pid': 10, 'start': 'lifetime'})
        g.write('launch.json', record)
        child = Mock(pid=20); child.poll.return_value = None; child.wait.return_value = 0
        with patch.object(g.subprocess, 'Popen', return_value=child), \
                patch.object(g, 'clients', side_effect=[[], [self.window], []]), \
                patch.object(g, 'authorized_game', return_value=True), patch.object(g.time, 'sleep'):
            self.assertEqual(g.worker(command, 'nonce'), 0)
        receipt = g.read('launch.json')
        self.assertEqual(receipt['phase'], 'done')
        child.wait.assert_called_once()
        child.terminate.assert_not_called(); child.kill.assert_not_called()

    def test_ambiguous_game_keeps_worker_alive_and_reports_without_kill(self):
        command = ['test-game']
        g.write('launch.json', dict(request='nonce', token='token', command=g.command_hash(command),
                                  phase='launching', game=None, caller={'pid': 10, 'start': 'lifetime'}))
        child = Mock(pid=20); child.wait.return_value = 0
        with patch.object(g.subprocess, 'Popen', return_value=child), \
                patch.object(g.subprocess, 'run') as notify, \
                patch.object(g, 'clients', side_effect=[[], [self.window, dict(self.window, address='0xac')]]), \
                patch.object(g, 'authorized_game', return_value=True):
            g.worker(command, 'nonce')
        self.assertIn('Multiple game windows', g.read('launch.json')['error'])
        notify.assert_called_once(); child.wait.assert_called_once()
        child.terminate.assert_not_called(); child.kill.assert_not_called()

    def test_notification_failure_cannot_strand_a_confirmed_failed_child(self):
        command = ['test-game']
        g.write('launch.json', dict(request='nonce', token='token', command=g.command_hash(command),
                                  phase='launching', game=None, caller={'pid': 10, 'start': 'lifetime'}))
        child = Mock(pid=20); child.poll.return_value = 7; child.wait.return_value = 7
        with patch.object(g.subprocess, 'Popen', return_value=child), \
                patch.object(g.subprocess, 'run', side_effect=FileNotFoundError('notify-send')), \
                patch.object(g, 'clients', return_value=[]):
            self.assertEqual(g.worker(command, 'nonce'), 7)
        self.assertEqual(g.read('launch.json')['phase'], 'done')
        self.assertEqual(g.read('launch.json')['code'], 7)
        self.assertIn('could not be verified', g.read('launch.json')['error'])
        child.terminate.assert_not_called(); child.kill.assert_not_called()

    def test_explicit_recovery_archives_only_dead_idle_exact_failed_request(self):
        with patch.dict(os.environ, XDG_STATE_HOME=self.tmp.name + '/state'):
            record = dict(phase='unavailable', game=None, command=g.command_hash(['steam-session', '123']),
                          caller={'pid': 10, 'start': 'dead'}, owner={'pid': 11, 'start': 'dead'},
                          child={'pid': 12, 'start': 'dead'})
            g.write('launch.json', record)
            with patch.object(g.subprocess, 'check_output', return_value=json.dumps({'running': False, 'shutdown_blockers': {}})), \
                    patch.object(g, 'environment', return_value={}), \
                    patch.object(g, 'sync_directory', wraps=g.sync_directory) as sync:
                with self.assertRaisesRegex(RuntimeError, 'exact failed'):
                    g.recover_failed('124')
                archive = g.recover_failed('123')
                state = Path(self.tmp.name) / 'state'
                self.assertEqual([c.args[0] for c in sync.call_args_list], [
                    Path(self.tmp.name), state, state / 'tablet-native',
                    state / 'tablet-native/recovered-launch-receipts'])
            self.assertFalse((g.root() / 'launch.json').exists())
            self.assertEqual(json.loads(Path(archive).read_text())['phase'], 'unavailable')
            self.assertEqual(Path(archive).stat().st_mode & 0o777, 0o600)

    def test_gone_or_zombie_process_has_no_environment_to_inspect(self):
        for error in (FileNotFoundError('gone'), ProcessLookupError('zombie environ')):
            with patch.object(g, 'environment', side_effect=error):
                self.assertEqual(g.recovery_environment(42, '200'), {})

    def test_unreadable_preexisting_service_is_not_a_launch_descendant(self):
        with patch.object(g, 'environment', side_effect=PermissionError('protected service')), \
                patch.object(g, 'start', return_value='10'):
            self.assertEqual(g.recovery_environment(3795, '200'), {})
        for born in ('200', '300'):
            with patch.object(g, 'environment', side_effect=PermissionError('protected child')), \
                    patch.object(g, 'start', return_value=born):
                with self.assertRaisesRegex(RuntimeError, 'possible launch descendant'):
                    g.recovery_environment(42, '200')

    def test_failed_recovery_archives_across_filesystems_without_rename(self):
        if not Path('/dev/shm').is_dir():
            self.skipTest('No private tmpfs fixture available')
        with tempfile.TemporaryDirectory(prefix='tablet-receipt-test.', dir='/dev/shm') as memory:
            if Path(memory).stat().st_dev == Path(self.tmp.name).stat().st_dev:
                self.skipTest('Fixture directories are on the same filesystem')
            with patch.dict(os.environ, XDG_RUNTIME_DIR=memory, XDG_STATE_HOME=self.tmp.name + '/state'):
                g.write('launch.json', dict(phase='unavailable', game=None, command=g.command_hash(['steam-session', '123']),
                    caller={'pid': 10, 'start': 'dead'}, owner={'pid': 11, 'start': 'dead'}, child={'pid': 12, 'start': 'dead'}))
                raw = (g.root() / 'launch.json').read_bytes()
                with patch.object(g.subprocess, 'check_output', return_value=json.dumps({'running': False, 'shutdown_blockers': {}})), \
                        patch.object(g, 'environment', return_value={}):
                    archive = Path(g.recover_failed('123'))
                self.assertEqual(archive.read_bytes(), raw)
                self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
                self.assertFalse((g.root() / 'launch.json').exists())

    def test_recovery_refuses_alive_worker_or_running_steam(self):
        record = dict(phase='unavailable', game=None, command=g.command_hash(['steam-session', '123']),
                      caller={'pid': 10, 'start': 'lifetime'}, owner={'pid': 11, 'start': 'dead'},
                      child={'pid': 12, 'start': 'dead'})
        g.write('launch.json', record)
        with self.assertRaisesRegex(RuntimeError, 'still alive'):
            g.recover_failed('123')
        record['caller']['start'] = 'dead'; g.write('launch.json', record)
        with patch.object(g.subprocess, 'check_output', return_value=json.dumps({'running': True, 'shutdown_blockers': {}})):
            with self.assertRaisesRegex(RuntimeError, 'protected activity'):
                g.recover_failed('123')
        self.assertTrue((g.root() / 'launch.json').exists())

    def test_curated_launches_use_wrapper_but_existing_steam_worker_is_unchanged(self):
        for path in (ROOT / 'home/config/pegasus').glob('*.pegasus.txt'):
            for line in path.read_text().splitlines():
                if line.startswith('launch:'):
                    self.assertTrue(line.startswith('launch: tablet-game-launch -- '), line)
        source = (ROOT / 'home/packages/steam-session/scripts/session.py').read_text()
        self.assertIn('steam.wait_game', source)
        self.assertIn('force=False', source)


if __name__ == '__main__':
    unittest.main()
