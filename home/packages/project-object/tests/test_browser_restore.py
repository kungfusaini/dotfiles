import copy
import io
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from browser_protocol import MAX_MESSAGE, receive, send
import browser_restore
from browser_restore import RecoveryCancelled, Restoration, fingerprint, private_file
from project_object import write_json_atomic


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        stream = io.BytesIO()
        send(stream, {'ok': True, 'value': 'λ'})
        stream.seek(0)
        self.assertEqual(receive(stream), {'ok': True, 'value': 'λ'})

    def test_reject_bad_frames(self):
        for data in [b'', b'\x01', struct.pack('<I', MAX_MESSAGE + 1), struct.pack('<I', 2) + b'[]']:
            with self.subTest(data=data), self.assertRaises((EOFError, ValueError)):
                receive(io.BytesIO(data))

    def test_reject_nonfinite_and_oversized(self):
        for value in [{'number': float('nan')}, {'text': 'x' * MAX_MESSAGE}]:
            with self.assertRaises(ValueError):
                send(io.BytesIO(), value)


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = {'id': str(uuid.uuid4()), 'name': 'Alpha'}
        self.api = SimpleNamespace(DATA_ROOT=self.root / 'data', RUNTIME_ROOT=self.root / 'runtime',
            validate_browser_role=mock.Mock(return_value='Alpha · Browser'),
            load_registry=lambda: {'projects': [self.project]}, browser_clients=mock.Mock(return_value=[]),
            clients=mock.Mock(return_value=[]), client_address=lambda c: c['address'],
            client_workspace=lambda c: c['workspace']['name'], dispatch=mock.Mock(),
            live_address=mock.Mock(return_value='0x123'), launch_urls=mock.Mock())
        self.manager = Restoration(self.api)
        self.manager.bridge = mock.Mock()
        self.identity = {'pid': 42, 'startTime': '123', 'instance': str(uuid.uuid4()),
                         'profile': str(self.root / 'profile'), 'protocol': 1, 'ready': True, 'ok': True}
        self.manager.bridge.identity.return_value = self.identity
        self.window = {'id': 7, 'projectId': self.project['id'], 'windowKey': str(uuid.uuid4()),
                       'type': 'normal', 'incognito': False, 'provenance': [self.project['id']],
                       'tabs': [{'id': 8, 'url': 'https://example.com', 'pinned': True, 'group': '',
                                 'groupTitle': '', 'fixedTitle': '', 'workspace': 0}]}
        self.record = {'key': self.window['windowKey'], 'name': 'native-session', 'window': self.window,
                       'backup': 'checkpoints/' + str(uuid.uuid4()) + '/0.bin', 'sha256': 'hash'}
        self.checkpoint = {'version': 1, 'projectId': self.project['id'], 'identity': self.identity,
                           'generation': self.record['backup'].split('/')[1], 'windows': [self.record]}

    def save(self):
        write_json_atomic(self.manager.home(self.project) / 'checkpoint.json', self.checkpoint)

    def test_checkpoint_absent_does_not_start_browser(self):
        self.assertEqual(self.manager.restore(self.project), [])
        self.manager.bridge.request.assert_not_called()
        self.api.launch_urls.assert_not_called()

    def test_private_checkpoint_is_atomic_and_private(self):
        self.save()
        self.assertEqual(self.manager.checkpoint(self.project), self.checkpoint)
        path = self.manager.home(self.project) / 'checkpoint.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_symlink_is_rejected(self):
        target = self.root / 'target'
        target.write_text('{}')
        link = self.root / 'link'
        link.symlink_to(target)
        with self.assertRaises(OSError):
            private_file(link)

    def test_wrong_project_id_is_rejected(self):
        with self.assertRaises((ValueError, RuntimeError)):
            self.manager.home({'id': '../../escape'})

    def test_fingerprint_preserves_stack_relationships_not_generated_ids(self):
        other = copy.deepcopy(self.window)
        other['tabs'][0]['id'] = 900
        self.assertEqual(fingerprint(other), fingerprint(self.window))
        other['tabs'][0]['pinned'] = False
        self.assertNotEqual(fingerprint(other), fingerprint(self.window))

    def test_recovered_window_is_reused_without_native_replay(self):
        self.save()
        self.manager.ready = mock.Mock(return_value=self.identity)
        self.manager.address = mock.Mock(return_value='0x123')
        self.manager.bridge.request.return_value = [self.window]
        self.assertEqual(self.manager.restore(self.project), ['0x123'])
        self.manager.bridge.request.assert_called_once_with('inventory')
        self.api.dispatch.assert_called_once_with('movetoworkspacesilent', 'name:Alpha · Browser,address:0x123')

    def test_wrong_profile_or_duplicate_recovery_is_refused(self):
        self.save()
        self.manager.ready = mock.Mock(return_value={**self.identity, 'profile': '/elsewhere'})
        with self.assertRaisesRegex(RuntimeError, 'different browser profile'):
            self.manager.restore(self.project)
        self.manager.ready.return_value = self.identity
        self.manager.bridge.request.return_value = [self.window, self.window]
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous recovered'):
            self.manager.restore(self.project)
        self.api.dispatch.assert_not_called()

    def test_mixed_tab_provenance_is_not_replayed(self):
        self.save()
        self.manager.ready = mock.Mock(return_value=self.identity)
        mixed = copy.deepcopy(self.window)
        del mixed['projectId']
        self.manager.bridge.request.return_value = [mixed]
        with self.assertRaisesRegex(RuntimeError, 'Mixed recovered'):
            self.manager.restore(self.project)

    def test_bad_backup_fails_before_native_restore(self):
        self.save()
        self.manager.ready = mock.Mock(return_value=self.identity)
        self.manager.bridge.request.return_value = []
        backup = self.manager.home(self.project) / self.record['backup']
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'integrity verification'):
            self.manager.restore(self.project)
        self.manager.bridge.request.assert_called_once_with('inventory')

    def test_backup_failure_prevents_any_close(self):
        client = {'address': '0x123', 'workspace': {'name': 'Alpha · Browser'}}
        self.api.browser_clients.return_value = [client]
        self.api.clients.return_value = [client]
        self.manager.bindings = mock.Mock(return_value={7: '0x123'})
        self.manager.backup = mock.Mock(side_effect=RuntimeError('disk full'))
        def request(op, **kwargs):
            return {'inventory': [self.window], 'tag': self.window, 'save': {'window': self.window}}[op]
        self.manager.bridge.request.side_effect = request
        with self.assertRaisesRegex(RuntimeError, 'disk full'):
            self.manager.close(self.project)
        self.assertFalse(any(call.args[0] == 'close' for call in self.manager.bridge.request.call_args_list))
        self.assertIsNone(self.manager.checkpoint(self.project))

    def test_interrupted_pin_removal_is_not_adopted_as_user_edit(self):
        self.checkpoint['phase'] = 'closing'
        self.save()
        self.manager.ready = mock.Mock(return_value=self.identity)
        partial = copy.deepcopy(self.window)
        partial['tabs'] = []
        self.manager.bridge.request.return_value = [partial]
        with self.assertRaisesRegex(RuntimeError, 'Interrupted browser closure'):
            self.manager.restore(self.project)
        self.manager.bridge.request.assert_called_once_with('inventory')
        self.api.dispatch.assert_not_called()

    def test_restart_missing_window_requires_proven_startup_completion(self):
        self.save()
        self.manager.ready = mock.Mock(return_value={**self.identity, 'instance': str(uuid.uuid4())})
        self.manager.bridge.request.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'Startup recovery completion'):
            self.manager.restore(self.project)
        self.manager.bridge.request.assert_called_once_with('inventory')

    def prepare_restart(self):
        content = b'native saved session'
        self.record['sha256'] = hashlib.sha256(content).hexdigest()
        self.save()
        backup = self.manager.home(self.project) / self.record['backup']
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(content)
        self.manager.native_file = mock.Mock(return_value=backup)
        identity = {**self.identity, 'instance': str(uuid.uuid4())}
        self.manager.ready = mock.Mock(return_value=identity)
        self.manager.bridge.identity.return_value = identity
        self.manager.address = mock.Mock(return_value='0x123')
        self.live = []
        def request(op, **kwargs):
            if op == 'inventory':
                return copy.deepcopy(self.live)
            if op == 'restore':
                self.assertEqual(kwargs['projectId'], self.project['id'])
                self.assertEqual(kwargs['windowKey'], self.window['windowKey'])
                self.live.append(copy.deepcopy(self.window))
                return copy.deepcopy(self.window)
            self.fail(op)
        self.manager.bridge.request.side_effect = request

    def replay_calls(self):
        return [c for c in self.manager.bridge.request.call_args_list if c.args[0] == 'restore']

    def test_cancel_restart_recovery_has_no_replay_placement_or_journal_change(self):
        self.prepare_restart()
        path = self.manager.home(self.project) / 'checkpoint.json'
        before = path.read_bytes()
        confirm = mock.Mock(return_value=False)
        with self.assertRaises(RecoveryCancelled):
            self.manager.restore(self.project, confirm_recovery=confirm)
        confirm.assert_called_once_with(self.project, 1)
        self.assertFalse(self.replay_calls())
        self.api.dispatch.assert_not_called()
        self.assertEqual(path.read_bytes(), before)

    def test_confirmed_restart_restores_once_and_preserves_backup(self):
        self.prepare_restart()
        confirm = mock.Mock(return_value=True)
        self.assertEqual(self.manager.restore(self.project, confirm_recovery=confirm), ['0x123'])
        self.assertEqual(self.manager.restore(self.project, confirm_recovery=confirm), ['0x123'])
        confirm.assert_called_once_with(self.project, 1)
        self.assertEqual(len(self.replay_calls()), 1)
        self.assertTrue((self.manager.home(self.project) / self.record['backup']).is_file())

    def test_late_recovery_during_confirmation_is_adopted_with_live_edits(self):
        self.prepare_restart()
        edited = copy.deepcopy(self.window)
        edited['tabs'][0]['url'] = 'https://example.com/live-edit'
        def confirm(*_args):
            self.live.append(edited)
            return True
        self.assertEqual(self.manager.restore(self.project, confirm_recovery=confirm), ['0x123'])
        self.assertFalse(self.replay_calls())
        self.assertEqual(self.live[0], edited)

    def test_confirmation_does_not_authorize_a_changed_adapter(self):
        self.prepare_restart()
        def confirm(*_args):
            self.manager.bridge.identity.return_value = {**self.identity, 'instance': 'changed'}
            return True
        with self.assertRaisesRegex(RuntimeError, 'Browser changed'):
            self.manager.restore(self.project, confirm_recovery=confirm)
        self.assertFalse(self.replay_calls())
        self.api.dispatch.assert_not_called()

    def test_restart_between_inventory_and_replay_is_rejected_at_boundary(self):
        from test_browser_host import host
        self.prepare_restart()
        original = self.manager.bridge.request.side_effect
        expected = self.manager.bridge.identity.return_value
        def request(op, **kwargs):
            if op == 'restore':
                receiving = {key: expected[key] for key in ('pid', 'startTime', 'profile')}
                try:
                    host.validate_restore_identity({'op': op, **kwargs}, receiving, 'replacement-adapter')
                except ValueError as error:
                    raise RuntimeError(str(error)) from error
                self.fail('Replacement host must reject stale consent')
            return original(op, **kwargs)
        self.manager.bridge.request.side_effect = request
        with self.assertRaisesRegex(RuntimeError, 'Browser changed before replay'):
            self.manager.restore(self.project, confirm_recovery=lambda *_: True)
        self.assertEqual(self.live, [])
        self.api.dispatch.assert_not_called()

    def test_ambiguous_or_mixed_late_recovery_is_not_replayed(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                self.prepare_restart()
                def confirm(*_args):
                    if mixed:
                        window = copy.deepcopy(self.window)
                        window['provenance'].append(str(uuid.uuid4()))
                        self.live.append(window)
                    else:
                        self.live.extend([self.window, self.window])
                    return True
                with self.assertRaisesRegex(RuntimeError, 'Mixed recovered|Ambiguous recovered'):
                    self.manager.restore(self.project, confirm_recovery=confirm)
                self.assertFalse(self.replay_calls())
                self.api.dispatch.assert_not_called()
                self.manager.bridge.request.reset_mock()

    def test_consent_does_not_bypass_backup_integrity(self):
        self.prepare_restart()
        (self.manager.home(self.project) / self.record['backup']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'integrity verification'):
            self.manager.restore(self.project, confirm_recovery=lambda *_: True)
        self.assertFalse(self.replay_calls())

    def test_late_duplicate_after_replay_is_reported_not_closed(self):
        self.prepare_restart()
        original = self.manager.bridge.request.side_effect
        def request(op, **kwargs):
            result = original(op, **kwargs)
            if op == 'restore':
                self.live.append(copy.deepcopy(self.window))
            return result
        self.manager.bridge.request.side_effect = request
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous recovered'):
            self.manager.restore(self.project, confirm_recovery=lambda *_: True)
        self.assertEqual(len(self.live), 2)
        self.api.dispatch.assert_not_called()

    def test_confirmation_is_not_reused_on_a_later_open(self):
        self.prepare_restart()
        self.manager.restore(self.project, confirm_recovery=lambda *_: True)
        self.live.clear()
        with self.assertRaisesRegex(RuntimeError, 'Startup recovery completion'):
            self.manager.restore(self.project)
        self.assertEqual(len(self.replay_calls()), 1)

    def test_retry_partial_close_retains_complete_manifest(self):
        self.checkpoint['phase'] = 'closing'
        self.save()
        client = {'address': '0x123', 'workspace': {'name': 'Alpha · Browser'}}
        self.api.browser_clients.return_value = [client]
        before = (self.manager.home(self.project) / 'checkpoint.json').read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'Previous browser closure is unresolved'):
            self.manager.close(self.project)
        self.assertEqual((self.manager.home(self.project) / 'checkpoint.json').read_bytes(), before)
        self.manager.bridge.request.assert_not_called()

    def test_split_window_key_is_rejected_before_mutation(self):
        clients = [{'address': address, 'workspace': {'name': 'Alpha · Browser'}} for address in ['0x123', '0x456']]
        self.api.browser_clients.return_value = clients
        self.api.clients.return_value = clients
        duplicate = {**self.window, 'id': 9}
        self.manager.bridge.request.return_value = [self.window, duplicate]
        self.manager.bindings = mock.Mock(return_value={7: '0x123', 9: '0x456'})
        with self.assertRaisesRegex(RuntimeError, 'share a recovery key'):
            self.manager.close(self.project)
        self.manager.bridge.request.assert_called_once_with('inventory')
        self.assertIsNone(self.manager.checkpoint(self.project))

    def test_partial_restart_close_does_not_replace_unrecovered_records(self):
        missing = copy.deepcopy(self.record)
        missing['key'] = str(uuid.uuid4())
        missing['window']['windowKey'] = missing['key']
        self.checkpoint['phase'] = 'closed'
        self.checkpoint['windows'].append(missing)
        self.save()
        before = (self.manager.home(self.project) / 'checkpoint.json').read_bytes()
        client = {'address': '0x123', 'workspace': {'name': 'Alpha · Browser'}}
        self.api.browser_clients.return_value = [client]
        self.api.clients.return_value = [client]
        self.manager.bridge.request.return_value = [self.window]
        self.manager.bindings = mock.Mock(return_value={7: '0x123'})
        with self.assertRaisesRegex(RuntimeError, 'unrecovered windows'):
            self.manager.close(self.project)
        self.assertEqual((self.manager.home(self.project) / 'checkpoint.json').read_bytes(), before)
        self.manager.bridge.request.assert_called_once_with('inventory')

    def test_new_directory_entries_are_synced_before_backup_creation(self):
        native = self.root / 'native.bin'
        native.write_bytes(b'native-session')
        destination = self.root / 'checkpoints/generation/0.bin'
        self.manager.native_file = mock.Mock(return_value=native)
        events = []
        real_sync = browser_restore.fsync_directory
        real_open = os.open
        def sync(path):
            events.append(('sync', path))
            return real_sync(path)
        def opened(path, flags, *args, **kwargs):
            if flags & os.O_WRONLY:
                events.append(('create', path))
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(browser_restore, 'fsync_directory', side_effect=sync), \
                mock.patch.object(browser_restore.os, 'open', side_effect=opened), \
                mock.patch.object(browser_restore.time, 'sleep'):
            self.manager.backup(self.identity, 'native-name', destination)
        expected_prefix = [('sync', self.root / 'checkpoints'), ('sync', self.root),
                           ('sync', destination.parent), ('sync', destination.parent.parent)]
        self.assertEqual(events[:4], expected_prefix)
        self.assertGreater(events.index(('create', destination)), 3)
        self.assertEqual(events[-1], ('sync', destination.parent))
        self.assertEqual(destination.read_bytes(), b'native-session')

    def test_ancestor_fsync_failure_is_fatal_and_retried_on_next_attempt(self):
        native = self.root / 'native.bin'
        native.write_bytes(b'native-session')
        destination = self.root / 'checkpoints/generation/0.bin'
        self.manager.native_file = mock.Mock(return_value=native)
        real_sync = browser_restore.fsync_directory
        calls = []
        failed = False
        def sync(path):
            nonlocal failed
            calls.append(path)
            if path == self.root and not failed:
                failed = True
                raise OSError('injected parent fsync failure')
            return real_sync(path)
        with mock.patch.object(browser_restore, 'fsync_directory', side_effect=sync), \
                mock.patch.object(browser_restore.time, 'sleep'):
            with self.assertRaisesRegex(OSError, 'injected parent fsync failure'):
                self.manager.backup(self.identity, 'native-name', destination)
            self.assertFalse(destination.exists())
            self.assertEqual(calls.count(self.root), 1)
            self.manager.backup(self.identity, 'native-name', destination)
        self.assertGreaterEqual(calls.count(self.root), 2)
        self.assertEqual(destination.read_bytes(), b'native-session')

    def test_explicit_verified_recovery_resolves_closing_journal(self):
        self.checkpoint['phase'] = 'closing'
        self.save()
        self.manager.ready = mock.Mock(return_value=self.identity)
        self.manager.address = mock.Mock(return_value='0x123')
        self.manager.bridge.request.return_value = [self.window]
        self.assertEqual(self.manager.restore(self.project), ['0x123'])
        self.assertEqual(self.manager.checkpoint(self.project)['phase'], 'recovered')

    def test_startup_does_not_adopt_partial_close(self):
        self.checkpoint['phase'] = 'closing'
        self.save()
        partial = copy.deepcopy(self.window)
        partial['tabs'] = []
        self.manager.bridge.request.return_value = [partial]
        with self.assertRaisesRegex(RuntimeError, 'partial startup windows were not adopted'):
            self.manager.reconcile_startup()
        self.api.dispatch.assert_not_called()

    def test_startup_only_moves_owned_windows_and_never_restores(self):
        self.save()
        self.manager.bridge.request.return_value = [self.window]
        self.manager.address = mock.Mock(return_value='0x123')
        self.manager.reconcile_startup()
        self.manager.bridge.request.assert_called_once_with('inventory')
        self.api.dispatch.assert_called_once_with('movetoworkspacesilent', 'name:Alpha · Browser,address:0x123')


if __name__ == '__main__':
    unittest.main()
