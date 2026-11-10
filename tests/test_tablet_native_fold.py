import copy
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
                patch.object(self.native, 'start_stage', side_effect=lambda **kw: self.events.append(('stage', 'covered'))))

    def enter(self, address=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.runtime(): stack.enter_context(patcher)
            self.native.setup(address)

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
        self.assertTrue(argument.startswith('[workspace name:tablet-trial silent] vivaldi --new-window '))
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


if __name__ == '__main__': unittest.main()
