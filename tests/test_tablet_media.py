import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
with patch.dict(os.environ, {'TABLET_PROOF_SOURCE': str(ROOT / 'home/packages/tablet-proof/controller.py')}):
    spec = importlib.util.spec_from_file_location('tablet_media_host', ROOT / 'home/packages/tablet-proof/media/host.py')
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.tmp.name, 'HYPRLAND_INSTANCE_SIGNATURE': 'instance'})
        self.env.start()
        self.source = {'instance': 'instance', 'address': '0xab', 'pid': 42, 'start': 'start',
                       'class': 'vivaldi-stable', 'stableId': 'abc'}
        self.record = dict(self.source, native=True, owner={'pid': 99, 'start': 'owner'},
                           tablet_session={'workspace': 'tablet-trial'})
        self.bridge = h.Bridge(io.BytesIO()); self.bridge.port = 1234
        self.client = dict(self.source, mapped=True, workspace={'name': 'tablet-trial'})

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_shared_pid_and_recycled_address_never_replace_native_window_identity(self):
        other = dict(self.client, stableId='other')
        with patch.object(h.core, 'start_time', return_value='start'), patch.object(h.core, 'hypr', return_value=[other]):
            self.assertIsNone(h.source_client(self.source))
        other['stableId'] = 'abc'; other['workspace']['name'] = 'laptop'
        with patch.object(h.core, 'start_time', return_value='start'), patch.object(h.core, 'hypr', return_value=[other]):
            self.assertIsNone(h.source_client(self.source))

    def test_pause_requires_exact_registered_source_not_shared_browser_process(self):
        with patch.object(h, 'current', return_value=self.record), patch.object(h.core, 'start_time', return_value='owner'), \
                patch.object(h, 'source_client', return_value=self.client):
            with self.assertRaisesRegex(RuntimeError, 'not paired'):
                self.bridge.native_request({'op': 'pause', 'source': self.source}, 99)
            self.bridge.bindings[h.key(self.source)] = {'source': self.source, 'windowId': 7}
            with patch.object(self.bridge, 'ask', return_value={'ok': True, 'playing': 0}) as ask:
                self.bridge.native_request({'op': 'pause', 'source': self.source}, 99)
            ask.assert_called_once_with('pause', windowId=7)
            wrong = dict(self.source, stableId='other')
            with self.assertRaisesRegex(RuntimeError, 'Wrong tablet source'):
                self.bridge.native_request({'op': 'pause', 'source': wrong}, 99)

    def test_unrelated_socket_peer_cannot_issue_pause(self):
        with patch.object(h, 'current', return_value=self.record):
            with self.assertRaisesRegex(RuntimeError, 'Not the tablet owner'):
                self.bridge.native_request({'op': 'pause', 'source': self.source}, 123)

    def test_registration_uses_nonce_title_plus_extension_tab_identity_not_focus(self):
        registration = self.bridge.prepare(self.source)
        registration['report'] = {'windowId': 7, 'tabId': 101}
        self.client['title'] = registration['marker'] + ' - Vivaldi'
        with patch.object(h, 'current', return_value=self.record), patch.object(h, 'source_client', return_value=self.client), \
                patch.object(self.bridge, 'ask', return_value={'ok': True}) as ask:
            self.bridge.finalize(registration, self.source)
        self.assertEqual(self.bridge.bindings[h.key(self.source)]['windowId'], 7)
        self.assertEqual([c.args[0] for c in ask.call_args_list], ['verify', 'verify', 'resume'])

    def test_registration_is_not_published_until_initial_state_acknowledgement(self):
        registration = self.bridge.prepare(self.source)
        registration['report'] = {'windowId': 7, 'tabId': 101}
        self.client['title'] = registration['marker']
        with patch.object(h, 'current', return_value=self.record), patch.object(h, 'source_client', return_value=self.client), \
                patch.object(self.bridge, 'ask', side_effect=[{'ok': True}, {'ok': True}, RuntimeError('no ack')]):
            with self.assertRaisesRegex(RuntimeError, 'no ack'): self.bridge.finalize(registration, self.source)
        self.assertFalse(self.bridge.bindings)

    def test_pairing_rechecks_exit_state_before_commit_instead_of_late_resume(self):
        registration = self.bridge.prepare(self.source)
        registration['report'] = {'windowId': 7, 'tabId': 101}
        self.client['title'] = registration['marker']
        with patch.object(h, 'current', side_effect=[self.record, dict(self.record, media_suspended=True)]), \
                patch.object(h, 'source_client', return_value=self.client), \
                patch.object(self.bridge, 'ask', return_value={'ok': True}) as ask:
            self.bridge.finalize(registration, self.source)
        self.assertEqual(ask.call_args.args[0], 'pause')

    def test_registration_move_during_confirmation_is_rejected(self):
        registration = self.bridge.prepare(self.source)
        registration['report'] = {'windowId': 7, 'tabId': 101}
        valid = dict(self.client, title=registration['marker'])
        with patch.object(h, 'current', return_value=self.record), \
                patch.object(h, 'source_client', side_effect=[valid, None]), \
                patch.object(self.bridge, 'ask', return_value={'ok': True}):
            with self.assertRaisesRegex(RuntimeError, 'moved'):
                self.bridge.finalize(registration, self.source)
        self.assertFalse(self.bridge.bindings)

    def test_wrong_lease_cannot_bind_even_with_valid_registration_page(self):
        registration = self.bridge.prepare(self.source)
        registration['report'] = {'windowId': 7, 'tabId': 101}
        self.client['title'] = registration['marker']
        with patch.object(h, 'current', return_value=dict(self.record, stableId='other')), \
                patch.object(h, 'source_client', return_value=self.client), \
                patch.object(self.bridge, 'ask', return_value={'ok': True}):
            with self.assertRaisesRegex(RuntimeError, 'lease changed'):
                self.bridge.finalize(registration, self.source)
        self.assertFalse(self.bridge.bindings)

    def test_source_closed_means_no_browser_request(self):
        with patch.object(h, 'current', return_value=self.record), patch.object(h.core, 'start_time', return_value='owner'), \
                patch.object(h, 'source_client', return_value=None), patch.object(self.bridge, 'ask') as ask:
            result = self.bridge.native_request({'op': 'pause', 'source': self.source}, 99)
        self.assertTrue(result['closed'])
        ask.assert_not_called()

    def test_native_framing_is_length_prefixed_and_bounded(self):
        self.bridge.send({'ok': True})
        output = self.bridge.output.getvalue()
        self.assertEqual(int.from_bytes(output[:4], byteorder=os.sys.byteorder), len(output)-4)
        self.assertEqual(json.loads(output[4:]), {'ok': True})


if __name__ == '__main__': unittest.main()
