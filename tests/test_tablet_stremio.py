import copy
import importlib.util
import os
import sys
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tablet_stremio', ROOT / 'home/packages/tablet-proof/stremio.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
scan_busy = s.busy
scan_tokens = s.token_processes


class StremioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, XDG_RUNTIME_DIR=self.tmp.name, HYPRLAND_INSTANCE_SIGNATURE='private',
                              TABLET_STREMIO_BIN='/nix/store/private-client/bin/stremio')
        self.env.start(); self.addCleanup(self.env.stop)
        self.clients = []
        self.events = []
        self.app = s.Stremio(lambda name: {'name': s.WORKSPACE, 'monitor': 'eDP-1'} if name == 'activeworkspace' else self.clients,
                             lambda *a: self.events.append(a))
        for name, value in [('busy', False), ('start', 'start'), ('token', 'token'), ('token_processes', False)]:
            patcher = patch.object(s, name, return_value=value)
            setattr(self, name, patcher.start()); self.addCleanup(patcher.stop)
        self.client = {'address': '0xab', 'pid': 42, 'class': s.APP_ID, 'stableId': 'abc',
                       'mapped': True, 'workspace': {'name': s.WORKSPACE}}

    def launch(self):
        self.app.launch()
        record = self.app.read()
        self.token.return_value = record['token']
        record['owner'] = {'pid': 42, 'start': 'start'}
        self.app.write(record)

    def test_proc_scans_skip_unrelated_nondumpable_and_vanished_processes(self):
        entry = Path(self.tmp.name) / '42'; entry.mkdir()
        for error in (PermissionError(), FileNotFoundError(), ProcessLookupError()):
            with self.subTest(error=type(error).__name__), \
                    patch.object(s.Path, 'iterdir', return_value=[entry]), \
                    patch.object(s.Path, 'resolve', side_effect=error), \
                    patch.object(s.subprocess, 'run', return_value=Mock(stdout='(false,)')):
                self.assertFalse(scan_busy())
            with patch.object(s.Path, 'iterdir', return_value=[entry]), \
                    patch.object(s, 'token', side_effect=error):
                self.assertFalse(scan_tokens('private-token'))

    def test_unreadable_exact_owner_blocks_retry(self):
        self.launch()
        record = self.app.read(); record['deadline'] = 0; self.app.write(record)
        self.start.side_effect = PermissionError('owner identity unavailable')
        with self.assertRaises(PermissionError): self.app.launch()
        self.assertEqual(len(self.events), 1)

    def test_launch_targets_tablet_and_journals_before_exec(self):
        self.launch()
        self.assertEqual(self.events[0][1]['rules'], {'workspace': 'name:tablet-trial silent'})
        self.assertIn('env GDK_BACKEND=wayland TABLET_STREMIO_TOKEN=', self.events[0][1]['command'])
        self.assertIn('TABLET_STREMIO_BIN=/nix/store/private-client/bin/stremio', self.events[0][1]['command'])
        self.assertEqual(self.app.path().stat().st_mode & 0o777, 0o600)

    def test_desktop_singleton_refused_before_exec(self):
        self.busy.return_value = True
        with self.assertRaisesRegex(RuntimeError, 'Quit desktop'): self.app.launch()
        self.assertEqual(self.events, [])
        self.assertFalse(self.app.read())

    def test_existing_window_refused_even_without_bus_owner(self):
        self.clients.append(self.client)
        with self.assertRaisesRegex(RuntimeError, 'Quit desktop'): self.app.launch()
        self.assertEqual(self.events, [])

    def test_exact_new_window_resumes_after_controller_restart(self):
        self.launch(); self.clients.append(self.client)
        self.app.tick()
        other = s.Stremio(lambda _: self.clients, lambda *a: self.events.append(a))
        self.assertEqual(other.window(), self.client)
        self.assertEqual(other.launch(), self.client)
        self.assertEqual(len(self.events), 1)  # Native caller performs addressed, lifetime-guarded focus.

    def test_wrong_token_not_claimed(self):
        self.launch(); self.clients.append(self.client)
        self.token.return_value = 'foreign'
        self.app.tick()
        self.assertIsNone(self.app.window())

    def test_unrelated_placements_and_classes_not_claimed(self):
        self.launch()
        for change in [{'workspace': {'name': 'laptop'}}, {'class': 'foreign'}, {'floating': True},
                       {'pinned': True}, {'grouped': [1]}, {'xwayland': True}, {'mapped': False}]:
            with self.subTest(change=change):
                self.clients[:] = [dict(self.client, **change)]
                self.app.tick()
                self.assertIsNone(self.app.window())

    def test_address_pid_and_lifetime_replacement_not_claimed(self):
        self.launch(); self.clients.append(copy.deepcopy(self.client)); self.app.tick()
        for key, value in [('address', '0xac'), ('pid', 43), ('stableId', 'abd')]:
            self.clients[:] = [dict(self.client, **{key: value})]
            self.assertIsNone(self.app.window())
        self.clients[:] = [self.client]; self.start.return_value = 'new'
        self.assertIsNone(self.app.window())

    def test_ambiguous_windows_not_adopted(self):
        self.launch()
        self.clients[:] = [self.client, dict(self.client, address='0xac', stableId='abd')]
        self.app.tick()
        self.assertIsNone(self.app.window())
        self.assertIn('not uniquely verified', self.app.error)
        self.clients[:] = [self.client]
        self.app.tick()
        self.assertIsNone(self.app.window())

    def test_timeout_retains_receipt_and_blocks_duplicate(self):
        self.launch()
        record = self.app.read(); record['deadline'] = 0; self.app.write(record)
        self.assertFalse(self.app.status()['stremioLaunching'])
        with self.assertRaisesRegex(RuntimeError, 'unresolved'): self.app.launch()
        self.assertEqual(len(self.events), 1)

    def test_failed_dead_launch_can_retry(self):
        self.launch()
        record = self.app.read(); record['deadline'] = 0; record.pop('owner'); self.app.write(record)
        old = record['token']
        self.app.launch()
        self.assertNotEqual(self.app.read()['token'], old)
        with patch.object(s.os, 'execv') as execute:
            self.assertEqual(s.spawn(old), 1)
        execute.assert_not_called()

    def test_live_token_process_blocks_retry_even_without_window(self):
        self.launch()
        record = self.app.read(); record['deadline'] = 0; record.pop('owner'); self.app.write(record)
        self.token_processes.return_value = True
        with self.assertRaisesRegex(RuntimeError, 'unresolved'): self.app.launch()

    def test_dispatch_failure_allows_safe_retry(self):
        with patch.object(self.app, 'dispatch', side_effect=RuntimeError('IPC refused')):
            with self.assertRaisesRegex(RuntimeError, 'launch request failed'): self.app.launch()
        self.assertEqual(self.app.read()['deadline'], 0)
        self.app.launch()
        self.assertEqual(len(self.events), 1)

    def test_other_compositor_cannot_resume(self):
        self.launch(); self.clients.append(self.client); self.app.tick()
        with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='other'):
            self.assertIsNone(self.app.window())

    def test_normal_close_reopens_only_the_owned_tray_without_new_process(self):
        self.launch(); self.clients.append(self.client); self.app.tick()
        self.clients.clear()
        def activate(record, verify):
            verify()
            self.clients.append(dict(self.client, address='0xac', stableId='abd'))
        with patch.object(s, 'activate_owned', side_effect=activate) as restore:
            self.app.launch()
        restore.assert_called_once()
        self.app.tick()
        self.assertEqual(self.app.window()['address'], '0xac')
        self.assertEqual([event[0] for event in self.events], ['exec'])

    def test_live_ineligible_identity_keeps_registration_but_no_source(self):
        self.launch(); self.clients.append(copy.deepcopy(self.client)); self.app.tick()
        self.clients[0]['mapped'] = False
        self.assertIsNotNone(self.app.registered())
        self.assertIsNone(self.app.window())
        self.assertTrue(self.app.hidden())
        self.clients[0]['workspace'] = {'name': 'laptop'}
        self.assertFalse(self.app.hidden())
        with patch.object(s, 'activate_owned') as activate:
            with self.assertRaisesRegex(RuntimeError, 'Quit desktop'): self.app.launch()
        activate.assert_not_called()

    def test_permission_failure_does_not_erase_registered_lifetime(self):
        self.launch(); self.clients.append(self.client); self.app.tick()
        self.start.side_effect = PermissionError('unavailable')
        with self.assertRaises(PermissionError): self.app.registered()
        self.assertIn('window', self.app.read())

    def bus(self, pid=42):
        variant = lambda signature, value: SimpleNamespace(unpack=lambda: value)
        bus = Mock()
        bus.call_sync.side_effect = [variant('', (':1.7',)), variant('', (pid,)), variant('', ())]
        gio = SimpleNamespace(bus_get_sync=Mock(return_value=bus), BusType=SimpleNamespace(SESSION=0),
                              DBusCallFlags=SimpleNamespace(NONE=0))
        gi = SimpleNamespace(require_version=Mock())
        repository = SimpleNamespace(Gio=gio, GLib=SimpleNamespace(Variant=variant))
        return bus, gio, {'gi': gi, 'gi.repository': repository}

    def test_restore_uses_one_connection_and_exact_unique_destination(self):
        self.launch(); bus, gio, modules = self.bus()
        verify = Mock()
        with patch.dict(sys.modules, modules): s.activate_owned(self.app.read(), verify)
        gio.bus_get_sync.assert_called_once(); verify.assert_called_once()
        self.assertEqual(bus.call_sync.call_args.args[0], ':1.7')
        self.assertEqual(bus.call_sync.call_args.args[3], 'Activate')

    def test_restore_refuses_different_bus_owner_or_token(self):
        self.launch()
        for pid, value in [(43, self.app.read()['token']), (42, 'foreign')]:
            bus, gio, modules = self.bus(pid)
            self.token.return_value = value
            with patch.dict(sys.modules, modules), self.assertRaisesRegex(RuntimeError, 'ownership changed'):
                s.activate_owned(self.app.read(), Mock())
            self.assertEqual(bus.call_sync.call_count, 2)

    def test_restore_rechecks_window_workspace_before_activation(self):
        self.launch(); bus, gio, modules = self.bus()
        with patch.dict(sys.modules, modules), self.assertRaisesRegex(RuntimeError, 'left tablet'):
            s.activate_owned(self.app.read(), Mock(side_effect=RuntimeError('left tablet')))
        self.assertEqual(bus.call_sync.call_count, 2)


if __name__ == '__main__': unittest.main()
