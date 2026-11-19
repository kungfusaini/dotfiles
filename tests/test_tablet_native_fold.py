import copy
from contextlib import contextmanager, ExitStack
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch, call

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tablet_native', ROOT / 'home/packages/tablet-proof/native.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
p = n.p


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.tmp.name, 'XDG_STATE_HOME': self.tmp.name + '/state',
            'HYPRLAND_INSTANCE_SIGNATURE': 'instance', 'TABLET_NATIVE_ORIENTATION_BIN': '/native/orientation'})
        self.env.start()
        read_text = Path.read_text
        self.headless = patch.object(Path, 'read_text', lambda path, *args, **kwargs:
            'off' if str(path) == '/run/headless-mode/state' else read_text(path, *args, **kwargs))
        self.headless.start()
        self.addCleanup(self.headless.stop)
        self.keyboard = Mock(process=None, settings=[])
        self.controls = Mock()
        self.controls.read.return_value = {'volume': 30, 'brightness': 40}
        self.media = Mock()
        self.media.prepare.return_value = {'marker': 'tablet-media-fixture', 'nonce': 'fixture',
                                           'url': 'http://tablet.localhost:123/register/fixture'}
        self.native = n.Native(media=self.media, controls=self.controls, keyboard=self.keyboard)
        self.workspace = {'name': 'laptop', 'monitor': 'eDP-1'}
        self.panel = {'name': 'eDP-1', 'id': 0, 'reserved': [0, 0, 0, 0], 'width': 960, 'height': 640}
        self.laptop = self.client('0xab', 'abc', 'laptop')
        self.clients = [self.laptop]
        self.focus = self.laptop
        self.workspaces = [{'name': 'laptop', 'monitor': 'eDP-1'}]
        self.events = []

    def client(self, address, stable, workspace):
        return {'address': address, 'stableId': stable, 'pid': 42, 'class': 'vivaldi-stable',
                'workspace': {'name': workspace}, 'monitor': 0, 'mapped': True,
                'floating': False, 'tags': [], 'fullscreen': 0, 'fullscreenClient': 0}

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def queries(self, command):
        return {'activeworkspace': self.workspace, 'activewindow': self.focus,
                'monitors': [self.panel], 'clients': self.clients, 'workspaces': self.workspaces}[command]

    def dispatch(self, command, argument):
        self.events.append((command, argument))
        if command == 'workspace':
            self.workspace = {'name': argument.removeprefix('name:'), 'monitor': 'eDP-1'}
            if not any(w['name'] == self.workspace['name'] for w in self.workspaces):
                self.workspaces.append(dict(self.workspace))
            self.focus = next((c for c in self.clients if c['workspace']['name'] == self.workspace['name']), {})
        elif command == 'focuswindow':
            self.focus = next(c for c in self.clients if c['address'] == argument.removeprefix('address:'))
        elif command == 'fullscreenstate':
            self.focus['fullscreen'], self.focus['fullscreenClient'] = map(int, argument.split())
        elif command == 'tagwindow':
            tag, address = argument.split(' address:')
            c = next(c for c in self.clients if c['address'] == address)
            if tag[0] == '+': c['tags'].append(tag[1:])
            else: c['tags'].remove(tag[1:])

    def runtime(self):
        process = Mock(pid=77); process.poll.return_value = 0
        return (patch.object(p, 'hypr', side_effect=self.queries),
                patch.object(p, 'dispatch', side_effect=self.dispatch),
                patch.object(p, 'start_time', return_value='process'),
                patch.object(p, 'run', side_effect=lambda *a, **kw: 'true' if 'getprop' in a else ''),
                patch.object(p.subprocess, 'Popen', return_value=process),
                patch.object(self.native, 'cover'),
                patch.object(self.native, 'start_stage', side_effect=lambda **kw: self.events.append(('stage', 'covered'))),
                patch.object(self.native, 'acquire_posture'))

    def enter(self, address=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            self.native.setup(address)

    def test_native_stage_is_presentation_only_including_recovery(self):
        config = Path(self.tmp.name) / 'config/hypr'
        config.mkdir(parents=True)
        (config / 'hyprland.conf').write_text('layerrule=match:namespace ^tablet-rotation-fade$, no_anim on\n')
        self.native.owner = {'start': 'owner-start'}
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config.parent),
                'TABLET_STAGE_QML': '/nix/store/fixture/stage.qml',
                'TABLET_PROOF_QML': '/nix/store/fixture/shell.qml'}), \
                patch.object(n.subprocess, 'Popen') as launch, \
                patch.object(self.native, 'journal'), patch.object(self.native, 'cover') as cover:
            for recovering in (False, True):
                self.native.start_stage(allow_stopping=recovering)
                environment = launch.call_args.kwargs['env']
                self.assertEqual(environment['TABLET_STAGE_PRESENTATION_ONLY'], '1')
                self.assertEqual(environment['TABLET_STAGE_ASSETS'], '/nix/store/fixture')
                cover.assert_called_with(allow_stopping=recovering)

    def test_real_headless_posture_is_rejected_before_tablet_entry(self):
        with patch.object(Path, 'read_text', return_value='on'):
            with self.assertRaisesRegex(RuntimeError, 'awake internal display'):
                self.enter()
        self.assertEqual(self.events, [])

    def test_fold_from_laptop_browser_enters_empty_tablet_home_without_borrowing(self):
        before = copy.deepcopy(self.laptop)
        self.enter()
        self.assertEqual(self.workspace['name'], n.WORKSPACE)
        self.assertEqual(self.native.session['origin'], 'laptop')
        self.assertTrue(self.native.record['home_only'])
        self.assertIsNone(self.native.source)
        self.assertEqual(before, self.laptop)
        self.assertEqual(self.events, [('stage', 'covered'), ('workspace', 'name:tablet-trial')])
        self.keyboard.start.assert_called_once()

    def test_explicit_laptop_address_is_rejected_before_workspace_or_stage_change(self):
        with self.assertRaisesRegex(RuntimeError, 'never borrowed'):
            self.enter('0xab')
        self.assertEqual(self.events, [])

    def test_tablet_browser_resumes_in_place_and_returns_exact_laptop_focus(self):
        browser = self.client('0xcd', 'def', n.WORKSPACE)
        self.clients.append(browser)
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'eDP-1'})
        before_laptop = copy.deepcopy(self.laptop)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            self.native.setup(None)
            self.native.action('app')
            saved = n.memory()
            self.assertFalse(saved['home'])
            self.assertEqual(saved['source']['address'], '0xcd')
            self.native.cleanup()
        self.assertEqual(self.workspace['name'], 'laptop')
        self.assertEqual(self.focus['stableId'], 'abc')
        self.assertEqual(browser['workspace']['name'], n.WORKSPACE)
        self.assertEqual(before_laptop, self.laptop)
        self.assertFalse(any(command.startswith(('move', 'resize')) for command, _ in self.events))
        self.assertFalse((p.runtime() / 'recovery.json').exists())
        # A fresh backend must resume the same view/window, not whichever
        # browser is focused on the laptop at the next fold.
        self.native = n.Native(media=self.media, controls=self.controls, keyboard=self.keyboard)
        self.enter()
        self.assertFalse(self.native.home)
        self.assertEqual(self.native.source['stableId'], 'def')

    def test_media_pause_is_attempted_before_native_release_and_laptop_return(self):
        self.clients.append(self.client('0xcd', 'def', n.WORKSPACE))
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'eDP-1'})
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            self.native.setup(None)
            self.media.pause.side_effect = lambda record: self.events.append(('media', 'pause'))
            self.native.cleanup()
        self.assertLess(self.events.index(('media', 'pause')), self.events.index(('fullscreenstate', '0 0')))
        self.assertEqual(self.workspace['name'], 'laptop')
        self.assertEqual(self.media.pause.call_count, 1)

    def test_unverified_media_pause_warns_and_retains_recovery_without_trapping_laptop(self):
        self.clients.append(self.client('0xcd', 'def', n.WORKSPACE))
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'eDP-1'})
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            self.native.setup(None)
            self.media.pause.side_effect = RuntimeError('not paired')
            with self.assertRaisesRegex(RuntimeError, 'pause could not be verified'): self.native.cleanup()
        self.assertEqual(self.workspace['name'], 'laptop')
        record = json.loads((p.runtime() / 'recovery.json').read_text())['window']
        self.assertTrue(record['media_pause_pending'])
        self.assertTrue(record['lease_released'])
        self.assertTrue(record['media_pause_notice_sent'])

    def test_native_ui_has_no_visible_desktop_exit_buttons(self):
        source = (ROOT / 'home/packages/tablet-proof/native.qml').read_text()
        self.assertNotIn('objectName: "returnDesktop"', source)
        self.assertIn('showExit: false', source)

    def test_closed_or_moved_saved_browser_is_not_substituted_from_laptop(self):
        saved = {'instance': 'instance', 'source': {**{k: self.laptop[k] for k in ('address', 'pid', 'class', 'stableId')}, 'start': 'process'}}
        with patch.object(p, 'start_time', return_value='process'):
            self.assertIsNone(n.saved_browser(saved, [self.laptop]))
            other = self.client('0xcd', 'def', n.WORKSPACE)
            self.assertIsNone(n.saved_browser(saved, [self.laptop, other]))

    def test_tablet_workspace_on_other_monitor_is_not_moved(self):
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'DP-1'})
        with self.assertRaisesRegex(RuntimeError, 'another display'):
            self.enter()
        self.assertEqual(self.events, [])

    def test_failed_cover_never_switches_workspace(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime()[:-1]: stack.enter_context(patcher)
            stack.enter_context(patch.object(self.native, 'start_stage', side_effect=RuntimeError('no cover')))
            with self.assertRaisesRegex(RuntimeError, 'no cover'): self.native.setup(None)
        self.assertEqual(self.events, [])
        self.assertFalse(self.native.session['entered'])

    def test_pending_legacy_exit_and_recovery_block_entry(self):
        path = Path(self.tmp.name) / 'tablet-workspace.json'
        path.write_text(json.dumps({'enabled': False, 'exit_pending': True}))
        with self.assertRaisesRegex(RuntimeError, 'old tablet'): self.enter()
        self.assertEqual(self.events, [])

    def test_launch_targets_new_tablet_window_not_laptop_browser(self):
        caps = Mock()
        caps.require_compatible.return_value = {'processes': {42: 'process'}}
        caps.registry = {'browser': {'command': ['vivaldi'], 'openArguments': ['--new-window']}}
        with patch.object(self.native, 'browser_policy', return_value=caps), \
                patch.object(n, 'normal_profile_processes', return_value={42: 'process'}), \
                patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'dispatch') as dispatch:
            self.native.launch_browser()
        caps.verify_launch.assert_called_once()
        command, argument = dispatch.call_args.args
        self.assertEqual(command, 'exec')
        self.assertTrue(argument['command'].startswith('vivaldi --new-window '))
        self.assertEqual(argument['rules'], {'workspace':'name:tablet-trial silent'})
        self.assertIn(self.laptop['address'], self.native.pending['previous'])

    def test_custom_profile_cannot_authorize_cold_normal_browser_launch(self):
        with patch.object(Path, 'read_bytes', return_value=b'vivaldi\0--user-data-dir=/temporary-profile\0--enable-wayland-ime\0'), \
                patch.object(p, 'start_time', return_value='process'):
            self.assertEqual(n.normal_profile_processes({42: 'process'}), {})
        with patch.object(Path, 'read_bytes', return_value=b'vivaldi\0--enable-wayland-ime\0'), \
                patch.object(p, 'start_time', return_value='process'):
            self.assertEqual(n.normal_profile_processes({42: 'process'}), {42: 'process'})

    def test_launch_wrong_workspace_never_moves_or_adopts_window(self):
        self.laptop['title'] = 'tablet-launch-private-marker'
        self.native.pending = {'marker': self.laptop['title'], 'previous': [], 'authorities': {}}
        self.native.capabilities = Mock()
        with patch.object(p, 'hypr', return_value=self.clients), patch.object(self.native, 'attach') as attach:
            self.native.poll_launch()
        attach.assert_not_called()
        self.assertIn('no existing window was moved', self.native.error)

    def test_cleanup_journal_failure_still_releases_resources(self):
        self.native.record = {'native': True, 'home_only': True}
        self.native.journal()
        with patch.object(self.native, 'journal', side_effect=OSError('read-only journal')), patch.object(p, 'run') as restore, \
                patch.object(p, 'hypr', return_value={'name': 'laptop'}):
            with self.assertRaisesRegex(RuntimeError, 'read-only journal'): self.native.cleanup()
        self.keyboard.stop.assert_called_once()
        restore.assert_called_once_with('/native/orientation', 'restore')
        self.assertTrue((p.runtime() / 'recovery.json').exists())

    def test_rotation_failure_records_released_lease_and_does_not_repeat_it(self):
        self.native.record = {'native': True}
        with patch.object(p, 'run', side_effect=RuntimeError('panel unavailable')), patch.object(p.Proof, 'cleanup') as release, \
                patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), patch.object(self.native, 'start_stage'), \
                patch.object(self.native, 'cover'):
            with self.assertRaises(RuntimeError): self.native.cleanup()
        release.assert_called_once_with(False, retain_journal=True)
        self.assertTrue(json.loads((p.runtime() / 'recovery.json').read_text())['window']['lease_released'])
        with patch.object(p, 'run'), patch.object(p.Proof, 'cleanup') as release, \
                patch.object(p, 'hypr', return_value={'name': 'laptop'}): self.native.cleanup(activate=True)
        release.assert_not_called()

    def test_failed_exit_cover_stops_input_but_never_changes_client_or_workspace(self):
        self.native.record = {'native': True}
        with patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), \
                patch.object(self.native, 'start_stage', side_effect=RuntimeError('cover timeout')), \
                patch.object(p, 'run'), patch.object(p.Proof, 'cleanup') as release, \
                patch.object(p, 'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError, 'cover timeout'): self.native.cleanup(activate=True)
        release.assert_not_called()
        dispatch.assert_not_called()
        self.keyboard.stop.assert_called_once()
        self.assertTrue((p.runtime() / 'recovery.json').exists())

    def test_dead_stage_is_reestablished_before_client_release_and_return(self):
        self.native.record = {'native': True, 'home_only': True}
        self.native.stage = Mock(); self.native.stage.poll.return_value = 0
        events = []
        with patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), patch.object(p, 'run'), \
                patch.object(self.native, 'start_stage', side_effect=lambda **kw: events.append('cover')), \
                patch.object(self.native, 'cover'), \
                patch.object(self.native, 'release_presentation', side_effect=lambda _: events.append('release')), \
                patch.object(self.native, 'return_desktop', side_effect=lambda: events.append('return')):
            self.native.cleanup()
        self.assertEqual(events, ['cover', 'release', 'return'])

    def test_cover_lost_during_rotation_defers_window_and_workspace_mutations(self):
        self.native.record = {'native': True}
        with patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), \
                patch.object(self.native, 'start_stage'), \
                patch.object(self.native, 'cover', side_effect=RuntimeError('cover lost')), \
                patch.object(p, 'run'), patch.object(p.Proof, 'cleanup') as release, \
                patch.object(p, 'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError, 'cover lost'): self.native.cleanup()
        release.assert_not_called()
        dispatch.assert_not_called()
        self.keyboard.stop.assert_called_once()

    def test_recovery_covers_before_stopping_old_children(self):
        p.save({'window': {'instance': 'instance', 'home_only': True, 'tablet_session': {'origin': 'laptop'}},
                'settings': [], 'children': [{'pid': 33, 'start': 'start'}]})
        recovered = Mock(); recovered.stage = None
        events = []
        def cover(**kwargs):
            events.append('cover')
            recovered.stage = Mock(pid=77); recovered.stage.poll.return_value = None
        recovered.start_stage.side_effect = cover
        recovered.cleanup.side_effect = lambda _: events.append('cleanup')
        with patch.object(n, 'Native', return_value=recovered), \
                patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), \
                patch.object(p, 'start_time', return_value='start'), \
                patch.object(os, 'pidfd_open', return_value=88), patch.object(os, 'close'), \
                patch('signal.pidfd_send_signal', side_effect=lambda *args: events.append('stop-old')), \
                patch('select.select', return_value=([88], [], [])):
            n.recover()
        self.assertEqual(events, ['cover', 'stop-old', 'cleanup'])
        self.assertIn({'pid': 77, 'start': 'start', 'role': 'stage'}, json.loads((p.runtime() / 'recovery.json').read_text())['children'])

    def test_recovery_failed_replacement_keeps_old_ui_and_cover_alive(self):
        children = [{'pid': 33, 'start': 'start', 'role': 'ui'},
                    {'pid': 34, 'start': 'start', 'role': 'stage'},
                    {'pid': 35, 'start': 'start', 'role': 'keyboard'}]
        p.save({'window': {'instance': 'instance', 'home_only': True, 'tablet_session': {'origin': 'laptop'}},
                'settings': [], 'children': children})
        recovered = Mock(); recovered.stage = None
        recovered.start_stage.side_effect = RuntimeError('replacement not opaque')
        with patch.object(n, 'Native', return_value=recovered), \
                patch.object(p, 'hypr', return_value={'name': n.WORKSPACE}), \
                patch.object(p, 'run'), patch.object(p, 'start_time', return_value='start'), \
                patch.object(os, 'pidfd_open', side_effect=lambda pid: pid + 100) as descriptors, \
                patch.object(os, 'close'), patch('signal.pidfd_send_signal') as stop, \
                patch('select.select', return_value=([135], [], [])):
            with self.assertRaisesRegex(RuntimeError, 'replacement not opaque'): n.recover()
        descriptors.assert_called_once_with(35)
        stop.assert_called_once()
        recovered.cleanup.assert_not_called()
        recovered.keyboard.stop.assert_called_once()
        self.assertEqual(json.loads((p.runtime() / 'recovery.json').read_text())['children'], children)

    def test_user_workspace_escape_is_not_followed_by_desktop_return(self):
        self.native.record = {'home_only': True}
        self.native.session = {'entered': True, 'origin': 'laptop'}
        self.workspace = {'name': 'other', 'monitor': 'eDP-1'}
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'dispatch') as dispatch:
            self.native.return_desktop()
        dispatch.assert_not_called()

    def test_known_empty_laptop_workspace_can_be_recreated_without_adopting_apps(self):
        self.native.record = {'home_only': True}
        self.native.session = {'entered': True, 'origin': 'empty-laptop', 'origin_empty': True, 'focus': {}}
        self.workspace = {'name': n.WORKSPACE, 'monitor': 'eDP-1'}
        self.workspaces = []
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'dispatch') as dispatch:
            self.native.return_desktop()
        dispatch.assert_called_once_with('workspace', 'name:empty-laptop')

    def test_disappearing_child_does_not_break_journal(self):
        self.native.record = {'native': True}
        self.native.orientation = Mock(pid=42); self.native.orientation.poll.return_value = None
        with patch.object(p, 'start_time', side_effect=FileNotFoundError()): self.native.journal()
        self.assertEqual(json.loads((p.runtime() / 'recovery.json').read_text())['children'], [])

    def test_pegasus_switch_parks_browser_behind_cover_without_stopping_ui(self):
        tablet = self.client('0xcd', 'def', n.WORKSPACE)
        self.clients.append(tablet); self.enter()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            stack.enter_context(patch.object(self.native, 'ipc'))
            launch = stack.enter_context(patch.object(self.native.games, 'launch'))
            self.native.select_games()
        launch.assert_called_once()
        self.assertTrue(self.native.record['home_only'])
        self.assertEqual(self.native.active_app, 'games')
        self.assertEqual(self.native.source['address'], tablet['address'])
        self.media.pause.assert_called_once()
        self.keyboard.stop.assert_not_called()
        self.assertFalse(tablet['tags'])
        self.assertEqual(tablet['fullscreen'], 0)

    def test_game_handoff_and_library_return_use_verified_identities(self):
        self.enter()
        self.native.active_app = 'games'
        game = dict(self.client('0xcd', 'def', n.WORKSPACE), **{'class': 'game', 'xwayland': True})
        library = dict(self.client('0xce', 'fed', n.WORKSPACE), **{'class': 'pegasus-fe'})
        self.clients += [game, library]
        self.focus = game
        status = dict(gameLaunching=False, gameRunning=True, gamesLaunching=False)
        game.update(floating=True, size=[960, 640])
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(n.gaming, 'start', return_value='process'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch), \
                patch.object(self.native.games, 'status', return_value=status), \
                patch.object(self.native.games, 'game', return_value=game) as playing, \
                patch.object(self.native.games, 'launcher', return_value=library):
            self.native.poll_games()
            self.assertEqual(self.native.games_target['address'], game['address'])
            self.assertEqual((game['fullscreen'], game['fullscreenClient']), (2, 2))
            self.assertEqual(self.native.record['game_presentation']['internal'], 0)
            self.native.release_game_presentation()
            self.assertEqual((game['fullscreen'], game['fullscreenClient']), (0, 0))
            status['gameRunning'] = False
            self.clients.remove(game); self.focus = library; playing.return_value = None
            self.native.poll_games()
            self.assertEqual(self.native.games_target['address'], library['address'])
        self.assertNotIn(('workspace', 'name:laptop'), self.events)

    def test_live_ineligible_game_keeps_presentation_recovery_evidence(self):
        self.enter(); self.native.active_app = 'games'
        game = dict(self.client('0xcd', 'def', n.WORKSPACE), floating=True, size=[960, 640])
        self.clients.append(game); self.focus = game
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(n.gaming, 'start', return_value='process'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch):
            self.assertTrue(self.native.present_game(game))
            for change in ({'workspace': {'name': 'elsewhere'}}, {'pinned': True}, {'mapped': False}):
                original = copy.deepcopy(game)
                game.update(change)
                with self.assertRaisesRegex(RuntimeError, 'ineligible live'):
                    self.native.release_game_presentation()
                self.assertIn('game_presentation', self.native.record)
                game.clear(); game.update(original)

    def test_explicit_game_recovery_covers_before_workspace_activation(self):
        self.enter(); self.native.active_app = 'games'
        game = dict(self.client('0xcd', 'def', n.WORKSPACE), floating=True, size=[960, 640])
        self.clients.append(game); self.focus = game
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(n.gaming, 'start', return_value='process'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch), \
                patch.object(self.native, 'cover', side_effect=lambda **kw:self.events.append(('cover', 'ready'))):
            self.native.present_game(game)
            self.workspace = {'name': 'laptop', 'monitor': 'eDP-1'}; self.focus = self.laptop
            self.events.clear()
            self.native.release_game_presentation(activate=True)
            self.assertEqual(self.events[:2], [('cover', 'ready'), ('workspace', 'name:' + n.WORKSPACE)])
            self.assertNotIn('game_presentation', self.native.record)
            self.assertEqual(game['fullscreen'], 0)

    def test_game_handoff_never_follows_user_workspace_escape(self):
        self.enter(); self.native.active_app = 'games'
        self.workspace = {'name': 'other', 'monitor': 'eDP-1'}
        game = self.client('0xcd', 'def', n.WORKSPACE)
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch') as dispatch, \
                patch.object(self.native.games, 'status', return_value=dict(gameLaunching=False, gameRunning=True)), \
                patch.object(self.native.games, 'game', return_value=game):
            with self.assertRaisesRegex(RuntimeError, 'no longer foreground'):
                self.native.poll_games()
        dispatch.assert_not_called()

    def test_launch_gap_keeps_real_pegasus_instead_of_tablet_home(self):
        self.enter(); self.native.active_app = 'games'; self.native.games_requested = True
        library = dict(self.client('0xce', 'fed', n.WORKSPACE), **{'class': 'pegasus-fe'})
        self.clients.append(library); self.focus = library
        status = dict(gameLaunching=True, gameRunning=False)
        with patch.object(p, 'hypr', side_effect=self.queries), \
                patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch), \
                patch.object(self.native.games, 'status', return_value=status), \
                patch.object(self.native.games, 'game', return_value=None), \
                patch.object(self.native.games, 'launcher', return_value=library):
            self.assertEqual(self.native.poll_games(), status)
        self.assertFalse(self.native.home)
        self.assertEqual(self.native.games_target['address'], library['address'])

    def test_foreign_same_workspace_focus_does_not_destroy_navigation_or_get_reclaimed(self):
        self.enter(); self.native.active_app = 'games'; self.native.games_requested = True; self.native.home = False
        game = self.client('0xcd', 'def', n.WORKSPACE)
        foreign = self.client('0xef', 'fed', n.WORKSPACE)
        self.clients += [game, foreign]; self.focus = foreign
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch') as dispatch, patch.object(n.time, 'monotonic', return_value=10), \
                patch.object(self.native.games, 'status', return_value=dict(gameLaunching=False, gameRunning=True)), \
                patch.object(self.native.games, 'game', return_value=game):
            self.native.games_target = n.identity(game)
            self.native.games_focus_lost_at = 0
            self.native.poll_games()
        dispatch.assert_not_called()
        self.assertFalse(self.native.stopping)
        self.assertFalse(self.native.home)
        self.assertIn('swipe up for Home', self.native.error)

    def test_empty_focus_can_repair_only_verified_foreground_tablet_target(self):
        self.enter(); self.native.active_app = 'games'; self.native.games_requested = True; self.native.home = False
        game = self.client('0xcd', 'def', n.WORKSPACE)
        self.clients.append(game); self.focus = {}
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch), patch.object(n.time, 'monotonic', return_value=10), \
                patch.object(self.native.games, 'status', return_value=dict(gameLaunching=False, gameRunning=True)), \
                patch.object(self.native.games, 'game', return_value=game):
            self.native.games_target = n.identity(game)
            self.native.games_focus_lost_at = 0
            self.native.poll_games()
        self.assertEqual(self.focus, game)
        self.assertFalse(self.native.stopping)
        self.assertNotIn(('workspace', 'name:laptop'), self.events)

    def test_empty_focus_does_not_take_focus_from_drawer_or_visible_ime(self):
        self.enter(); self.native.active_app = 'games'; self.native.games_requested = True; self.native.home = False
        game = self.client('0xcd', 'def', n.WORKSPACE)
        self.clients.append(game); self.focus = {}
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch') as dispatch, patch.object(n.time, 'monotonic', return_value=10), \
                patch.object(self.native.games, 'status', return_value=dict(gameLaunching=False, gameRunning=True)), \
                patch.object(self.native.games, 'game', return_value=game):
            self.native.games_target = n.identity(game)
            self.native.games_focus_lost_at = 0
            self.native.drawer = True
            self.native.poll_games()
            self.native.drawer = False
            self.panel['reserved'][3] = 200
            self.native.poll_games()
        dispatch.assert_not_called()
        self.assertFalse(self.native.stopping)

    def test_changed_game_or_library_target_does_not_take_drawer_or_ime_focus(self):
        self.enter(); self.native.active_app = 'games'; self.native.games_requested = True; self.native.home = False
        game = self.client('0xcd', 'def', n.WORKSPACE)
        library = dict(self.client('0xef', 'fed', n.WORKSPACE), **{'class': 'pegasus-fe'})
        self.clients += [game, library]; self.focus = {}
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'start_time', return_value='process'), \
                patch.object(p, 'dispatch') as dispatch, \
                patch.object(self.native.games, 'status') as state, \
                patch.object(self.native.games, 'game') as playing, \
                patch.object(self.native.games, 'launcher', return_value=library):
            for target in (game, None):
                playing.return_value = target
                state.return_value = dict(gameLaunching=False, gameRunning=target is not None)
                for drawer, inset in ((True, 0), (False, 200)):
                    self.native.drawer = drawer; self.panel['reserved'][3] = inset
                    self.native.games_target = {'address': '0xold'}
                    self.native.poll_games()
                    self.assertEqual(self.native.games_target, {'address': '0xold'})
        dispatch.assert_not_called()
        self.assertFalse(self.native.stopping)

    def test_failed_media_pause_during_switch_reveals_original_browser(self):
        self.enter()
        self.native.record['home_only'] = False
        with patch.object(self.native, 'cover'), patch.object(self.native, 'pause_media', side_effect=RuntimeError('unpaired')), \
                patch.object(self.native, 'ipc') as ipc, patch.object(self.native, 'release_window') as release:
            with self.assertRaisesRegex(RuntimeError, 'unpaired'):
                self.native.select_games()
        ipc.assert_called_once_with(self.native.stage, 'tabletStage', 'reveal')
        release.assert_not_called()
        self.assertEqual(self.native.active_app, 'vivaldi')

    def test_unfold_gaming_does_not_pause_close_or_signal_game(self):
        self.enter(); self.native.active_app = 'games'
        with patch.object(p, 'hypr', side_effect=self.queries), patch.object(p, 'run'), \
                patch.object(self.native, 'cover'), patch.object(self.native, 'start_stage'), \
                patch.object(p, 'dispatch', side_effect=self.dispatch):
            self.native.cleanup()
        self.media.pause.assert_not_called()
        self.assertEqual(self.workspace['name'], 'laptop')
        self.assertFalse((p.runtime() / 'recovery.json').exists())

    def test_stremio_tile_leaves_laptop_windows_and_unfold_keeps_app(self):
        self.enter()
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            stack.enter_context(patch.object(self.native, 'ipc'))
            stack.enter_context(patch.object(self.native.stremio, 'launch'))
            stack.enter_context(patch.object(self.native, 'stop_orientation'))
            self.native.select_stremio()
            self.assertEqual(self.native.active_app, 'stremio')
            self.assertEqual(self.laptop['workspace']['name'], 'laptop')
            self.native.cleanup()
        self.media.pause.assert_not_called()
        self.assertEqual(self.workspace['name'], 'laptop')
        self.assertFalse(any(event[0] in ('closewindow', 'movetoworkspace') for event in self.events))

    def test_stremio_poll_never_reclaims_foreign_focus(self):
        self.enter(); self.native.active_app = 'stremio'
        target = dict(self.client('0xac', 'def', n.WORKSPACE), **{'class': 'com.stremio.Stremio'})
        with patch.object(p, 'hypr', side_effect=self.queries), \
                patch.object(self.native.stremio, 'status', return_value={'stremioLaunching': False}), \
                patch.object(self.native.stremio, 'window', return_value=target), \
                patch.object(self.native, 'present_game') as present:
            self.native.poll_stremio()
        present.assert_not_called()
        self.assertFalse(any(event[0] == 'focuswindow' for event in self.events))

    def test_home_cancels_pending_stremio_reveal(self):
        self.enter(); self.native.active_app = 'stremio'; self.native.stremio_waiting = True
        with patch.object(p, 'hypr', side_effect=self.queries): self.native.action('home')
        self.assertFalse(self.native.stremio_waiting)
        self.assertTrue(self.native.home)

    def test_stremio_card_has_separate_lifetime_and_eligibility(self):
        self.enter()
        target = dict(self.client('0xac', 'def', n.WORKSPACE), **{'class': 'com.stremio.Stremio'})
        self.clients.append(target)
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            stack.enter_context(patch.object(self.native.stremio, 'registered', return_value=target))
            window = stack.enter_context(patch.object(self.native.stremio, 'window', return_value=target))
            selected = self.native.card_sources()['stremio']
            target['workspace'] = {'name': 'laptop'}; window.return_value = None
            lifetimes, sources = self.native.card_state()
            self.assertIn('stremio', lifetimes); self.assertNotIn('stremio', sources)
            stack.enter_context(patch.object(n, 'uses_lua', return_value=True))
            with self.assertRaisesRegex(RuntimeError, 'unavailable or changed'):
                self.native.resume_app({'app': 'stremio', 'window': selected})
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                self.native.action('stremio')
        self.assertFalse(any(event[0] == 'focuswindow' for event in self.events))

    def test_stremio_close_releases_presentation_then_requests_only_exact_window(self):
        self.enter()
        target = dict(self.client('0xac', 'def', n.WORKSPACE), **{'class': 'com.stremio.Stremio'})
        self.clients.append(target); events = []
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            stack.enter_context(patch.object(n, 'uses_lua', return_value=True))
            stack.enter_context(patch.object(self.native.stremio, 'registered', return_value=target))
            stack.enter_context(patch.object(self.native.stremio, 'window', return_value=target))
            stack.enter_context(patch.object(self.native, 'release_game_presentation', side_effect=lambda: events.append('release')))
            stack.enter_context(patch.object(self.native, 'owned_window_action', side_effect=lambda record, action: events.append((record['stableId'], action))))
            selected = self.native.card_sources()['stremio']
            with self.assertRaisesRegex(RuntimeError, 'unavailable or changed'):
                self.native.dismiss_app({'app': 'stremio', 'window': dict(selected, stableId='old')})
            self.assertEqual(events, [])
            self.native.dismiss_app({'app': 'stremio', 'window': selected})
        self.assertEqual(events, ['release', ('def', 'focus'), ('def', 'close')])
        self.assertEqual(self.laptop['workspace']['name'], 'laptop')

    def tick(self, edges, posture, state, headless='off'):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path).endswith('hotkey_tablet_mode'): return posture
            if str(path) == '/run/headless-mode/state': return headless
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read), patch.object(n, 'call', return_value=state) as command, \
                patch.object(p, 'hypr', side_effect=self.queries): edges.tick()
        return [c.args[0] for c in command.call_args_list]

    def test_fold_consumes_edge_and_does_not_reopen_after_manual_exit(self):
        edges = n.FoldEdges()
        self.assertEqual(self.tick(edges, '1', {}), ['status', 'start-fold'])
        self.assertEqual(self.tick(edges, '1', {}), [])

    def test_fold_adopts_existing_tablet_session_without_resetting_its_view(self):
        self.assertEqual(self.tick(n.FoldEdges(), '1', {'running': True, 'native': True}), ['status', 'adopt-fold'])

    def test_headless_fold_is_consumed_without_wake_takeover(self):
        edges = n.FoldEdges()
        self.assertEqual(self.tick(edges, '1', {}, 'on'), [])
        self.assertEqual(self.tick(edges, '1', {}), [])

    def test_unfold_closes_automatic_but_not_unfolded_manual_session(self):
        self.assertEqual(self.tick(n.FoldEdges(), '0', {'running': True, 'native': True, 'automatic': True}), ['status', 'close'])
        self.assertEqual(self.tick(n.FoldEdges(), '0', {'running': True, 'native': True, 'automatic': False}), ['status'])

    def test_unknown_posture_is_not_an_unfold(self):
        with self.assertRaisesRegex(RuntimeError, 'Unknown'): self.tick(n.FoldEdges(), '?', {})

    def test_pending_recovery_and_external_destination_block_fold_start(self):
        self.assertEqual(self.tick(n.FoldEdges(), '1', {'recovery': True}), ['status'])
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'DP-1'})
        self.assertEqual(self.tick(n.FoldEdges(), '1', {}), [])

    @contextmanager
    def switcher_fixture(self):
        browser = self.client('0xcd', 'def', n.WORKSPACE)
        self.clients.append(browser)
        self.workspaces.append({'name': n.WORKSPACE, 'monitor': 'eDP-1'})
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            stack.enter_context(patch.object(n, 'uses_lua', return_value=True))
            stack.enter_context(patch.object(n.gaming, 'start', return_value='process'))
            self.native.setup(None)
            yield browser

    def test_switcher_sources_are_exact_registered_windows_not_shared_pid(self):
        with self.switcher_fixture() as browser:
            foreign = self.client('0xef', 'aaa', n.WORKSPACE)
            self.clients.append(foreign)
            sources = self.native.card_sources()
            self.assertEqual(set(sources), {'vivaldi'})
            self.assertEqual(sources['vivaldi']['address'], browser['address'])
            self.assertEqual(sources['vivaldi']['stableId'], browser['stableId'])
            self.assertEqual(sources['vivaldi']['start'], 'process')
            self.assertEqual(sources['vivaldi']['instance'], 'instance')
            self.assertEqual(sources['vivaldi']['tag'], self.native.record['tag'])

    def test_switcher_moved_or_untagged_window_is_not_captured_or_closed(self):
        with self.switcher_fixture() as browser, patch.object(self.native, 'owned_window_action') as operation:
            target = self.native.card_sources()['vivaldi']
            browser['workspace']['name'] = 'laptop'
            self.assertEqual(self.native.card_sources(), {})
            self.assertEqual(self.native.card_state()[0]['vivaldi']['stableId'], browser['stableId'])
            with self.assertRaisesRegex(RuntimeError, 'unavailable or changed'):
                self.native.dismiss_app({'app': 'vivaldi', 'window': target})
            operation.assert_not_called()
            browser['workspace']['name'] = n.WORKSPACE
            browser['tags'] = []
            self.assertEqual(self.native.card_sources(), {})

    def test_switcher_ineligible_live_browser_retains_card_without_capture_permission(self):
        with self.switcher_fixture() as browser:
            for change in ({'mapped': False}, {'pinned': True}, {'grouped': ['0xcd']},
                           {'floating': True}, {'workspace': {'name': 'laptop'}}):
                original = copy.deepcopy(browser)
                browser.update(change)
                state = self.native.state()
                self.assertIn('vivaldi', state['cardLifetimes'])
                self.assertNotIn('vivaldi', state['cardSources'])
                self.assertIsNotNone(self.native.source)
                self.assertFalse(self.native.record.get('home_only'))  # Still owns its attached browser lease.
                self.assertTrue(self.native.action('home')['running'])
                with self.assertRaises(RuntimeError): self.native.modes(0, 0)
                browser.clear(); browser.update(original)

    def test_switcher_stale_resume_never_launches_or_replaces_registered_browser(self):
        with self.switcher_fixture() as browser, patch.object(self.native, 'owned_window_action') as operation, \
                patch.object(self.native, 'launch_browser') as launch, patch.object(self.native, 'select_browser') as select:
            target = self.native.card_sources()['vivaldi']
            source = copy.deepcopy(self.native.source)
            self.native.record = self.native.home_record()
            self.native.active_app = 'games'
            browser['workspace']['name'] = 'laptop'
            with self.assertRaisesRegex(RuntimeError, 'no replacement'):
                self.native.resume_app({'app': 'vivaldi', 'window': target})
            with self.assertRaisesRegex(RuntimeError, 'no replacement'):
                self.native.action('app')
            self.assertEqual(self.native.source, source)
            operation.assert_not_called(); launch.assert_not_called(); select.assert_not_called()

    def test_switcher_exact_active_resume_is_addressed_and_does_not_launch(self):
        with self.switcher_fixture(), patch.object(self.native, 'owned_window_action') as operation, \
                patch.object(self.native, 'launch_browser') as launch:
            target = self.native.card_sources()['vivaldi']; self.native.home = True
            state = self.native.resume_app({'app': 'vivaldi', 'window': target})
            operation.assert_called_once_with(target, 'focus')
            self.assertFalse(state['home'])
            launch.assert_not_called()

    def test_switcher_expected_browser_vanishing_during_resume_cannot_fall_back_to_launch(self):
        with self.switcher_fixture(), patch.object(self.native, 'launch_browser') as launch, \
                patch.object(self.native, 'ipc', return_value='ok'):
            target = self.native.card_sources()['vivaldi']
            source = copy.deepcopy(self.native.source)
            self.native.record = self.native.home_record()
            with patch.object(self.native, 'card_sources', return_value={'vivaldi': target}), \
                    patch.object(n.gaming, 'find', return_value=None):
                with self.assertRaisesRegex(RuntimeError, 'no replacement'): self.native.select_browser(expected=target)
            self.assertEqual(self.native.source, source)
            launch.assert_not_called()

    def test_switcher_stale_game_resume_never_selects_library_or_launches(self):
        with self.switcher_fixture(), patch.object(self.native, 'owned_window_action') as operation, \
                patch.object(self.native, 'select_games') as select, patch.object(self.native.games, 'launch') as launch:
            game = self.client('0xef', 'aaa', n.WORKSPACE)
            game.update(floating=True, **{'class': 'org.quickshell'})
            library = self.client('0xfa', 'bbb', n.WORKSPACE); library['class'] = 'pegasus-fe'
            self.clients.extend([game, library])
            with patch.object(self.native.games, 'game', return_value=game) as playing, \
                    patch.object(self.native.games, 'launcher', return_value=library):
                target = self.native.card_sources()['games']
                game['mapped'] = False; playing.return_value = None
                with self.assertRaisesRegex(RuntimeError, 'no replacement'):
                    self.native.resume_app({'app': 'games', 'window': target})
                with self.assertRaisesRegex(RuntimeError, 'no replacement'): self.native.action('games')
            operation.assert_not_called(); select.assert_not_called(); launch.assert_not_called()

    def test_switcher_live_ineligible_game_is_not_replaced_by_its_library(self):
        with self.switcher_fixture():
            game = self.client('0xef', 'aaa', n.WORKSPACE)
            game.update(floating=True, **{'class': 'org.quickshell'})
            library = self.client('0xfa', 'bbb', n.WORKSPACE)
            library['class'] = 'pegasus-fe'
            self.clients.extend([game, library])
            with patch.object(self.native.games, 'game', return_value=game) as playing, \
                    patch.object(self.native.games, 'launcher', return_value=library):
                self.assertEqual(self.native.card_state()[0]['games']['stableId'], 'aaa')
                game['mapped'] = False; playing.return_value = None
                lives, sources = self.native.card_state()
                self.assertEqual(lives['games']['stableId'], 'aaa')
                self.assertNotIn('games', sources)
                self.clients.remove(game)
                lives, sources = self.native.card_state()
                self.assertEqual(lives['games']['stableId'], 'bbb')
                self.assertIn('games', sources)

    def test_switcher_process_exit_with_lingering_client_does_not_end_session(self):
        with self.switcher_fixture() as browser:
            def start(pid):
                if pid == browser['pid']: raise FileNotFoundError('process exited before compositor unmap')
                return 'process'
            with patch.object(p, 'start_time', side_effect=start):
                state = self.native.state()
            self.assertTrue(state['running'])
            self.assertTrue(state['home'])
            self.assertFalse(state['browserRunning'])
            self.assertEqual(state['cardLifetimes'], {})
            self.assertTrue(self.native.record['home_only'])
            self.assertIn(browser, self.clients)  # Lingering snapshot is not re-adopted.

    def test_switcher_process_lookup_race_is_exact_disappearance(self):
        with self.switcher_fixture():
            with patch.object(p, 'start_time', side_effect=ProcessLookupError('exited')):
                self.assertIsNone(self.native.refresh_browser())
            self.assertIsNone(self.native.source)
            self.assertTrue(self.native.record['home_only'])

    def test_switcher_recycled_window_never_replaces_snapshot_close_target(self):
        with self.switcher_fixture() as browser, patch.object(self.native, 'owned_window_action') as operation:
            target = self.native.card_sources()['vivaldi']
            browser['stableId'] = 'bad'
            with self.assertRaisesRegex(RuntimeError, 'unavailable or changed'):
                self.native.dismiss_app({'app': 'vivaldi', 'window': target})
            operation.assert_not_called()
            self.assertIsNone(self.native.source)
            self.assertTrue(self.native.record['home_only'])
            self.assertIn(browser, self.clients)

    def test_switcher_unreadable_lifetime_is_not_disappearance(self):
        with self.switcher_fixture():
            source = copy.deepcopy(self.native.source)
            with patch.object(p, 'start_time', side_effect=PermissionError('unreadable')):
                with self.assertRaises(PermissionError): self.native.refresh_browser()
            self.assertEqual(self.native.source, source)
            self.assertFalse(self.native.record.get('home_only'))

    def test_switcher_normal_close_keeps_card_and_reveals_confirmation(self):
        with self.switcher_fixture() as browser, patch.object(self.native, 'owned_window_action') as operation:
            target = self.native.card_sources()['vivaldi']
            self.native.home = True
            self.native.resume_overview = True
            state = self.native.dismiss_app({'app': 'vivaldi', 'window': target})
            self.assertEqual(operation.call_args_list, [call(target, 'focus'), call(target, 'close')])
            self.assertFalse(state['home'])
            self.assertFalse(state['resumeOverview'])
            self.assertEqual(state['cardSources']['vivaldi'], target)
            self.assertEqual(state['closePending'], 'vivaldi')
            self.assertIn(browser, self.clients)
            self.keyboard.hide.assert_called()

    def test_switcher_actual_close_prunes_only_dead_window_and_keeps_posture(self):
        with self.switcher_fixture() as browser:
            target = self.native.card_sources()['vivaldi']
            laptop = copy.deepcopy(self.laptop)
            posture = {'owned': 'fixture'}
            self.native.posture = posture
            self.native.record['posture'] = posture
            def operation(record, action):
                self.assertEqual(record, target)
                if action == 'close': self.clients.remove(browser); self.focus = {}
            with patch.object(self.native, 'owned_window_action', side_effect=operation):
                state = self.native.dismiss_app({'app': 'vivaldi', 'window': target})
            self.assertTrue(state['running'])
            self.assertTrue(state['home'])
            self.assertFalse(state['browserRunning'])
            self.assertEqual(state['cardSources'], {})
            self.assertEqual(state['closePending'], '')
            self.assertEqual(self.clients, [laptop])
            self.assertEqual(self.native.record['posture'], posture)
            self.assertIsNone(n.memory()['source'])

    def test_switcher_confirmation_focus_can_be_observed_without_lease_mutation(self):
        with self.switcher_fixture() as browser:
            dialog = self.client('0xef', 'bbb', n.WORKSPACE)
            dialog.update(floating=True, **{'class': 'confirmation'})
            self.clients.append(dialog); self.focus = dialog
            self.assertTrue(self.native.state()['running'])
            self.assertEqual(self.native.card_sources()['vivaldi']['address'], browser['address'])
            with self.assertRaises(RuntimeError): self.native.modes(0, 0)
            self.assertEqual(self.focus, dialog)

    def test_switcher_close_rejects_external_workspace_or_invalid_app(self):
        with self.switcher_fixture(), patch.object(self.native, 'owned_window_action') as operation:
            target = self.native.card_sources()['vivaldi']
            with self.assertRaises(RuntimeError): self.native.dismiss_app({'app': 'laptop', 'window': target})
            self.workspace['name'] = 'laptop'
            with self.assertRaisesRegex(RuntimeError, 'no longer foreground'):
                self.native.dismiss_app({'app': 'vivaldi', 'window': target})
            operation.assert_not_called()

    def test_switcher_atomic_close_checks_lifetime_and_scope_in_one_callback(self):
        with self.switcher_fixture(), patch.object(p, 'run', return_value='ok') as ipc:
            target = self.native.card_sources()['vivaldi']
            self.native.owned_window_action(target, 'close')
            args = ipc.call_args.args
            self.assertEqual(args[:2], ('hyprctl', 'eval'))
            code = args[2]
            for guard in ('hl.get_window', 'w.pid==42', 'w.stable_id', 'w.workspace.name',
                          'w.tags', 'not w.pinned', 'not w.group', 'w.floating==false', 'hl.get_active_workspace', 'hl.get_active_monitor'):
                self.assertIn(guard, code)
            self.assertIn('hl.dsp.window.close({window=w})', code)
            self.assertNotIn('kill', code)
            self.assertLess(code.index('assert(w'), code.index('hl.dsp.window.close'))
            with patch.object(n, 'uses_lua', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'native Lua'): self.native.owned_window_action(target, 'close')


if __name__ == '__main__': unittest.main()
