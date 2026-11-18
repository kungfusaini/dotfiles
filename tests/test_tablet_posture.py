"""Reversible tablet interaction ownership without a host compositor or input."""
import copy
import importlib.util
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tablet_posture_native', ROOT / 'home/packages/tablet-proof/native.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)


class PostureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'runtime').mkdir(mode=0o700)
        self.config = root / 'config/hypr/hyprland.conf'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('# private fixture\n')
        env = patch.dict(os.environ, XDG_RUNTIME_DIR=str(root / 'runtime'),
                         XDG_CONFIG_HOME=str(root / 'config'), HYPRLAND_INSTANCE_SIGNATURE='private')
        env.start(); self.addCleanup(env.stop)
        self.native = n.Native(media=Mock(), keyboard=Mock(process=None, settings=[]), controls=Mock())
        self.native.record = {'home_only': True}
        self.values = {key: 1 for key in self.native.POSTURE_OPTIONS}
        self.writes = []
        self.fail = None
        run = patch.object(n.p, 'run', side_effect=self.fake_run)
        run.start(); self.addCleanup(run.stop)

    def fake_run(self, *args, **kwargs):
        self.assertEqual(args[0], 'hyprctl')
        if args[1] == 'getoption':
            return json.dumps({'int': self.values[args[2]]})
        self.assertEqual(args[1], 'keyword')
        key, value = args[2], int(args[3])
        # Acquisition and restoration must already have durable intent.
        saved = json.loads((n.p.runtime() / 'recovery.json').read_text())['window']['posture']
        self.assertIn(key, saved['applied'])
        self.writes.append((key, value))
        if self.fail == key:
            raise OSError('private IPC failure')
        self.values[key] = value
        return 'ok'

    def test_queued_setup_reload_aborts_before_acquiring_post_reload_baseline(self):
        for data in (b'configreloaded>>\n', b'configreload'):
            with self.subTest(data=data):
                left, right = socket.socketpair()
                try:
                    right.sendall(data)
                    self.native.before_interaction_acquire = lambda: n.p.reject_pending_interaction_reload(self.native, left)
                    with self.assertRaisesRegex(RuntimeError, 'before tablet interaction acquisition'):
                        self.native.acquire_posture()
                    self.assertEqual(left.recv(65536), data, 'barrier consumed main-loop events')
                    self.assertEqual(self.values, {key: 1 for key in self.values})
                    self.assertEqual(self.writes, [])
                    self.assertNotIn('posture', self.native.record)
                finally:
                    left.close(); right.close()

    def test_reload_queued_during_snapshot_aborts_before_first_write(self):
        left, right = socket.socketpair()
        checks = []
        def barrier():
            checks.append(True)
            if len(checks) == 2:
                right.sendall(b'configreloaded>>\n')
            n.p.reject_pending_interaction_reload(self.native, left)
        try:
            self.native.before_interaction_acquire = barrier
            with self.assertRaisesRegex(RuntimeError, 'before tablet interaction acquisition'):
                self.native.acquire_posture()
            self.assertEqual(self.native.record['posture']['applied'], [])
            self.native.restore_posture()
            self.assertEqual(self.writes, [])
            self.assertTrue(all(value == 1 for value in self.values.values()))
            self.assertNotIn('posture', self.native.record)
        finally:
            left.close(); right.close()

    def test_non_reload_setup_events_are_preserved_for_main_loop(self):
        left, right = socket.socketpair()
        try:
            data = b'activewindow>>fixture,Fixture\n'
            right.sendall(data)
            self.native.before_interaction_acquire = lambda: n.p.reject_pending_interaction_reload(self.native, left)
            self.native.acquire_posture()
            self.assertEqual(left.recv(65536), data)
            self.native.restore_posture()
            self.assertTrue(all(value == 1 for value in self.values.values()))
        finally:
            left.close(); right.close()

    def test_native_boolean_option_reply_preserves_integer_lease_contract(self):
        with patch.object(n.p,'run',return_value=json.dumps({'bool':True})):
            self.assertEqual(self.native.posture_value('gestures:workspace_swipe_touch'),1)
        with patch.object(n.p,'run',return_value=json.dumps({'bool':False})):
            self.assertEqual(self.native.posture_value('gestures:workspace_swipe_touch'),0)

    def test_snapshot_precedes_mutation_and_exact_baseline_is_restored(self):
        self.values['input:follow_mouse'] = 3
        self.native.acquire_posture()
        self.assertEqual(self.values, {key: 0 for key in self.values})
        self.assertEqual(self.native.record['posture']['baseline']['input:follow_mouse'], 3)
        self.native.restore_posture()
        self.assertEqual(self.values, {'gestures:workspace_swipe_touch': 1, 'input:follow_mouse': 3})
        self.assertNotIn('posture', self.native.record)
        self.assertIsNone(self.native.posture)

    def test_adapter_record_replacement_does_not_drop_interaction_lease(self):
        self.native.acquire_posture()
        lease = self.native.posture
        self.native.record = {'home_only': True, 'replacement': True}
        self.native.journal()
        self.assertIs(self.native.record['posture'], lease)
        self.native.restore_posture()
        self.assertTrue(all(value == 1 for value in self.values.values()))

    def test_new_recovery_controller_can_restore_saved_lease(self):
        self.native.acquire_posture()
        saved = copy.deepcopy(self.native.record)
        recovered = n.Native(media=Mock(), keyboard=Mock(process=None, settings=[]), controls=Mock())
        recovered.record = saved
        recovered.restore_posture()
        self.assertTrue(all(value == 1 for value in self.values.values()))
        self.assertNotIn('posture', recovered.record)

    def test_partial_acquisition_failure_is_recoverable(self):
        self.fail = 'input:follow_mouse'
        with self.assertRaises(OSError): self.native.acquire_posture()
        self.assertEqual(self.values, {'gestures:workspace_swipe_touch': 0, 'input:follow_mouse': 1})
        self.fail = None
        self.native.restore_posture()
        self.assertTrue(all(value == 1 for value in self.values.values()))

    def test_failed_restoration_retains_evidence_for_retry(self):
        self.native.acquire_posture()
        self.fail = 'input:follow_mouse'
        with self.assertRaises(OSError): self.native.restore_posture()
        self.assertIn('posture', self.native.record)
        self.fail = None
        self.native.restore_posture()
        self.assertTrue(all(value == 1 for value in self.values.values()))

    def test_external_nonmatching_live_change_is_not_overwritten(self):
        self.native.acquire_posture()
        self.values['input:follow_mouse'] = 2
        self.native.restore_posture()
        self.assertEqual(self.values, {'gestures:workspace_swipe_touch': 1, 'input:follow_mouse': 2})

    def test_config_generation_change_owns_its_new_baseline(self):
        self.native.acquire_posture()
        count = len(self.writes)
        self.config.write_text('# replaced config generation\n')
        self.values.update({'gestures:workspace_swipe_touch': 1, 'input:follow_mouse': 2})
        self.native.restore_posture()
        self.assertEqual(len(self.writes), count)
        self.assertEqual(self.values['input:follow_mouse'], 2)
        self.assertNotIn('posture', self.native.record)

    def test_config_reload_does_not_replay_old_runtime_baseline(self):
        self.native.acquire_posture()
        count = len(self.writes)
        self.native.record['config_changed'] = True
        self.values.update({'gestures:workspace_swipe_touch': 1, 'input:follow_mouse': 1})
        self.native.restore_posture()
        self.assertEqual(len(self.writes), count)

    def test_already_isolated_baseline_needs_no_runtime_writes(self):
        self.values = {key: 0 for key in self.values}
        self.native.acquire_posture(); self.native.restore_posture()
        self.assertEqual(self.writes, [])
        self.assertTrue(all(value == 0 for value in self.values.values()))

    def test_malformed_or_foreign_option_cannot_be_replayed(self):
        self.native.acquire_posture()
        self.native.record['posture']['applied'].append('bind')
        with self.assertRaisesRegex(RuntimeError, 'Invalid tablet interaction'):
            self.native.restore_posture()
        self.assertIn('posture', self.native.record)

    def test_absent_visual_cover_recovery_can_release_only_its_settings(self):
        self.native.acquire_posture()
        record = copy.deepcopy(self.native.record)
        recovered = n.Native(media=Mock(), keyboard=Mock(process=None, settings=[]), controls=Mock())
        recovered.restore_posture(record)
        self.assertNotIn('posture', record)
        self.assertTrue(all(value == 1 for value in self.values.values()))


if __name__ == '__main__': unittest.main()
