import copy
import fcntl
import importlib.util
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, call, patch

SOURCE = Path(__file__).resolve().parents[1] / 'home/scripts/desktop/tablet-orientation.py'
spec = importlib.util.spec_from_file_location('tablet_orientation', SOURCE)
rotation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotation)


class FakeSensor:
    def __init__(self):
        self.value = 'left-up'
        self.closed = False
        self.failure = False
        self.waits = []

    def read(self):
        if self.failure:
            raise RuntimeError('sensor lost')
        return self.value

    def wait(self, timeout):
        self.waits.append(timeout)

    def close(self):
        self.closed = True


class FakeBackend:
    instance = 'test'
    monitor = 'eDP-1'

    def __init__(self):
        self.visible = False
        self.headless_value = False
        self.available = True
        self.token = ['config', 1]
        self.transform = 0
        self.saved = None
        self.calls = []
        self.fail_apply = False
        self.fail_restore = False
        self.baseline = {'instance': self.instance, 'monitor': self.monitor,
                         'config': self.token, 'transform': 0,
                         'inputs': [{'name': 'built-in-touch', 'output': '[[Auto]]', 'transform': 0},
                                    {'name': 'built-in-pen', 'output': '[[EMPTY]]', 'transform': 0}]}

    def active(self): return self.visible and not self.headless_value and self.available
    def headless(self): return self.headless_value
    def panel(self): return {'transform': self.transform} if self.available else None
    def config_token(self): return copy.deepcopy(self.token)
    def load(self): return copy.deepcopy(self.saved)
    def clear(self): self.saved = None
    def save(self, value):
        self.calls.append(('save',))
        self.saved = copy.deepcopy(value)
    def snapshot(self): return copy.deepcopy(self.baseline)

    def apply(self, snapshot, delta):
        self.calls.append(('apply', delta))
        if delta is None and self.fail_restore:
            raise RuntimeError('restore failed')
        self.transform = snapshot['transform'] if delta is None else (snapshot['transform'] + delta) % 4
        if delta is not None and self.fail_apply:
            raise RuntimeError('partial transaction')


class OrientationTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.sensor = FakeSensor()
        self.factory = []
        def start():
            self.factory.append('claim')
            return self.sensor
        self.controller = rotation.Controller(self.backend, start)

    def activate(self):
        self.backend.visible = True
        self.controller.tick(0)
        self.controller.tick(1)

    def test_no_sensor_or_mutation_while_inactive(self):
        self.controller.tick(0)
        self.assertEqual(self.factory, [])
        self.assertEqual(self.backend.calls, [])

    def test_debounce_and_journal_before_apply(self):
        self.backend.visible = True
        self.controller.tick(0)
        self.controller.tick(.14)
        self.assertEqual(self.backend.calls, [])
        self.controller.tick(.16)
        self.assertEqual(self.backend.calls, [('save',), ('apply', 1)])

    def test_unstable_orientation_restarts_debounce(self):
        self.backend.visible = True
        self.controller.tick(0)
        self.sensor.value = 'right-up'
        self.controller.tick(.08)
        self.controller.tick(.20)
        self.assertEqual(self.backend.calls, [])
        self.controller.tick(.24)
        self.assertEqual(self.backend.transform, 3)

    def test_first_stable_reading_does_not_wait_old_800ms(self):
        self.backend.visible = True
        self.controller.tick(10)
        self.controller.tick(10.151)
        self.assertEqual(self.backend.transform, 1)

    def test_pending_stability_deadline_wakes_before_poll_interval(self):
        self.backend.visible = True
        self.controller.tick(10)
        self.assertAlmostEqual(self.controller.next_wait(10.05), .1)
        self.assertEqual(self.controller.next_wait(10.16), 0)
        self.controller.wait_for_work(10.05)
        self.assertAlmostEqual(self.sensor.waits[-1], .1)

    def test_stable_and_inactive_modes_keep_original_gate_cadence(self):
        self.assertEqual(self.controller.next_wait(0), .2)
        with patch.object(rotation.time, 'sleep') as sleep:
            self.controller.wait_for_work(0)
        sleep.assert_called_once_with(.2)
        self.activate()
        self.assertEqual(self.controller.next_wait(2), .2)
        self.controller.wait_for_work(2)
        self.assertEqual(self.sensor.waits[-1], .2)

    def test_new_orientation_restarts_short_stability_deadline(self):
        self.backend.visible = True
        self.controller.tick(10)
        self.sensor.value = 'right-up'
        self.controller.tick(10.10)
        self.assertAlmostEqual(self.controller.next_wait(10.20), .05)
        self.controller.tick(10.24)
        self.assertEqual(self.backend.calls, [])
        self.controller.tick(10.251)
        self.assertEqual(self.backend.transform, 3)

    def test_sensor_wait_uses_readable_fd_instead_of_sleep(self):
        sensor = rotation.Sensor.__new__(rotation.Sensor)
        sensor.process = MagicMock()
        with patch.object(rotation.select, 'select', return_value=([sensor.process.stdout], [], [])) as select_call, \
                patch.object(rotation.time, 'sleep') as sleep:
            sensor.wait(.15)
        select_call.assert_called_once_with([sensor.process.stdout], [], [], .15)
        sleep.assert_not_called()

    def test_unknown_or_flat_reading_holds_last_rotation(self):
        self.activate()
        self.sensor.value = None
        self.controller.tick(2)
        self.assertEqual(self.backend.transform, 1)
        self.assertEqual(len([c for c in self.backend.calls if c[0] == 'apply']), 1)

    def test_duplicate_orientation_does_not_reconfigure(self):
        self.activate()
        self.controller.tick(2)
        self.controller.tick(3)
        self.assertEqual(self.backend.calls, [('save',), ('apply', 1)])

    def test_existing_rotation_is_composed_and_restored(self):
        self.backend.baseline['transform'] = 2
        self.backend.transform = 2
        self.activate()
        self.assertEqual(self.backend.transform, 3)
        self.backend.visible = False
        self.controller.tick(2)
        self.assertEqual(self.backend.transform, 2)

    def test_workspace_exit_releases_sensor_and_restores(self):
        self.activate()
        self.backend.visible = False
        self.controller.tick(2)
        self.assertTrue(self.sensor.closed)
        self.assertEqual(self.backend.transform, 0)
        self.assertIsNone(self.backend.saved)

    def test_sensor_loss_restores_then_backs_off(self):
        self.activate()
        self.sensor.failure = True
        self.controller.tick(2)
        self.assertTrue(self.sensor.closed)
        self.assertEqual(self.backend.transform, 0)
        self.controller.tick(3)
        self.assertEqual(len(self.factory), 1)

    def test_headless_releases_and_defers_restore(self):
        self.activate()
        self.backend.headless_value = True
        self.controller.tick(2)
        self.assertTrue(self.sensor.closed)
        self.assertIsNotNone(self.backend.saved)
        self.assertEqual(self.backend.transform, 1)
        self.backend.headless_value = False
        self.backend.visible = False
        self.controller.tick(3)
        self.assertEqual(self.backend.transform, 0)

    def test_disconnected_panel_defers_restore(self):
        self.activate()
        self.backend.available = False
        self.controller.tick(2)
        self.assertIsNotNone(self.backend.saved)
        self.backend.available = True
        self.backend.visible = False
        self.controller.tick(3)
        self.assertIsNone(self.backend.saved)

    def test_partial_apply_is_rolled_back(self):
        self.backend.fail_apply = True
        self.backend.visible = True
        self.controller.tick(0)
        with self.assertRaises(RuntimeError):
            self.controller.tick(1)
        self.assertEqual(self.backend.transform, 0)
        self.assertIsNone(self.backend.saved)

    def test_failed_rollback_retains_recovery_journal(self):
        self.backend.fail_apply = self.backend.fail_restore = True
        self.backend.visible = True
        self.controller.tick(0)
        with self.assertRaises(RuntimeError):
            self.controller.tick(1)
        self.assertIsNotNone(self.backend.saved)

    def test_recovery_restores_before_taking_new_baseline(self):
        self.backend.saved = copy.deepcopy(self.backend.baseline)
        self.backend.transform = 3
        controller = rotation.Controller(self.backend, lambda: self.sensor)
        self.backend.visible = True
        controller.tick(0)
        self.assertEqual(self.backend.calls, [('apply', None)])
        self.assertEqual(self.backend.transform, 0)

    def test_configuration_change_is_not_overwritten(self):
        self.activate()
        self.backend.token = ['new-config', 2]
        with self.assertRaises(RuntimeError):
            self.controller.tick(2)
        self.assertTrue(self.sensor.closed)
        self.assertIsNone(self.backend.saved)
        self.assertEqual(self.backend.calls, [('save',), ('apply', 1)])

    def test_config_change_while_idle_does_not_reuse_old_policy(self):
        self.controller.tick(0)
        self.backend.token = ['new-config', 2]
        self.backend.visible = True
        with self.assertRaises(RuntimeError):
            self.controller.tick(1)
        self.assertEqual(self.factory, [])
        self.assertEqual(self.backend.calls, [])

    def test_config_reload_reset_is_reapplied_while_active(self):
        self.activate()
        self.backend.transform = 0
        self.controller.tick(2)
        self.assertEqual(self.backend.transform, 1)

    def test_resume_releases_cached_sensor_and_debounces_fresh_reading(self):
        self.activate()
        self.controller.tick(10)
        self.assertEqual(len(self.factory), 2)
        self.assertEqual(self.backend.transform, 0)
        self.controller.tick(11)
        self.assertEqual(self.backend.transform, 1)

    def test_sensor_event_parser_and_flat_state(self):
        sensor = rotation.Sensor.__new__(rotation.Sensor)
        sensor.available = True
        sensor.orientation = None
        sensor.tilt = 'undefined'
        sensor.consume('=== Has accelerometer (orientation: normal, tilt: vertical)')
        self.assertEqual((sensor.orientation, sensor.tilt), ('normal', 'vertical'))
        sensor.consume('    Accelerometer orientation changed: right-up')
        self.assertEqual(sensor.orientation, 'right-up')
        sensor.consume('    Tilt changed: face-up')
        self.assertIn(sensor.tilt, rotation.FLAT)
        sensor.consume('=== No accelerometer')
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.orientation)

    def test_transaction_targets_only_named_monitor_and_built_in_inputs(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        snapshot = self.backend.baseline
        with patch.object(backend, 'hypr', return_value='ok\n\nok\n\nok\n\nok\n\nok') as ipc, \
                patch.object(backend, 'panel', return_value={'transform': 1}):
            backend.apply(snapshot, 1)
        args = ipc.call_args.args
        self.assertEqual(args[0], '--batch')
        self.assertIn('keyword monitor eDP-1,transform,1', args[1])
        self.assertIn('device[built-in-touch]:transform 1', args[1])
        self.assertIn('device[built-in-pen]:transform 1', args[1])
        self.assertNotIn('input:touchdevice', args[1])
        self.assertNotIn('preferred', args[1])
        self.assertNotIn('dispatch', args[1])

    def test_restore_uses_saved_input_outputs_and_transforms(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        snapshot = copy.deepcopy(self.backend.baseline)
        snapshot['inputs'][0]['transform'] = 2
        with patch.object(backend, 'hypr', return_value='ok\nok\nok\nok\nok') as ipc, \
                patch.object(backend, 'panel', return_value={'transform': 0}):
            backend.apply(snapshot, None)
        command = ipc.call_args.args[1]
        self.assertIn('device[built-in-touch]:output [[Auto]]', command)
        self.assertIn('device[built-in-touch]:transform 2', command)
        self.assertIn('device[built-in-pen]:output [[EMPTY]]', command)

    def test_ipc_text_error_is_not_mistaken_for_success(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        with patch.object(backend, 'hypr', return_value='ok\ninvalid config field'), \
                patch.object(backend, 'panel', return_value={'transform': 1}):
            with self.assertRaises(RuntimeError):
                backend.apply(self.backend.baseline, 1)

    def test_stale_instance_journal_is_discarded_without_ipc(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = rotation.Backend.__new__(rotation.Backend)
            backend.instance = 'new'
            backend.journal = Path(tmp)/'journal.json'
            backend.journal.write_text(json.dumps({'instance': 'old'}))
            self.assertIsNone(backend.load())
            self.assertFalse(backend.journal.exists())


class RotationFadeTests(unittest.TestCase):
    def test_handshake_and_cleanup_are_ordered(self):
        fade = rotation.RotationFade('eDP-1')
        process = MagicMock(pid=1234)
        process.poll.return_value = None
        with patch.dict(os.environ, {'TABLET_ROTATION_FADE_QML': '/immutable/fade.qml'}), \
                patch.object(rotation.subprocess, 'Popen', return_value=process) as launch, \
                patch.object(fade, 'wait_for') as wait, patch.object(fade, 'call') as ipc:
            with fade:
                pass
        self.assertEqual(wait.call_args_list, [call('ready', 1.5), call('covered', 1), call('done', .7)])
        self.assertEqual(ipc.call_args_list, [call('cover'), call('reveal')])
        self.assertEqual(launch.call_args.kwargs['env']['TABLET_FADE_MONITOR'], 'eDP-1')
        process.terminate.assert_called_once()

    def test_missing_cover_ack_cancels_without_rotation(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        snapshot = FakeBackend().baseline
        with patch.object(backend, 'panel', return_value={'transform':0}), \
                patch.object(backend, 'headless', return_value=False), \
                patch.object(backend, 'active', return_value=True), \
                patch.object(backend, 'settle_delay', return_value=0), \
                patch.object(backend, 'hypr') as ipc, \
                patch.object(rotation, 'RotationFade') as fade:
            fade.return_value.__enter__.side_effect = RuntimeError('no cover ack')
            with self.assertRaises(RuntimeError):
                backend.apply(snapshot, 1)
        ipc.assert_not_called()

    def test_rotation_is_covered_until_after_layout_settles(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        events = []
        class Cover:
            def __enter__(self):
                events.append('covered')
                return self
            def __exit__(self, *_): events.append('revealed')
            def timeout(self, *args, **kwargs): return .2
            def ensure_covered(self, reserve): events.append('cover-rechecked')
        def ipc(*args, **kwargs):
            events.append('rotate')
            return chr(10).join(['ok'] * 5)
        with patch.object(backend, 'panel', side_effect=[{'transform':0}, {'transform':0}, {'transform':1}]), \
                patch.object(backend, 'headless', return_value=False), \
                patch.object(backend, 'active', return_value=True), \
                patch.object(backend, 'settle_delay', return_value=.53), \
                patch.object(backend, 'hypr', side_effect=ipc), \
                patch.object(rotation, 'RotationFade', return_value=Cover()), \
                patch.object(rotation.time, 'sleep', side_effect=lambda _:events.append('settled')):
            backend.apply(FakeBackend().baseline, 1)
        self.assertEqual(events, ['covered', 'cover-rechecked', 'rotate', 'settled', 'revealed'])

    def test_cover_expiring_during_gate_queries_prevents_mutation(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        with patch.object(backend, 'panel', return_value={'transform':0}), \
                patch.object(backend, 'headless', return_value=False), \
                patch.object(backend, 'active', return_value=True), \
                patch.object(backend, 'settle_delay', return_value=0), \
                patch.object(backend, 'hypr') as ipc, patch.object(rotation, 'RotationFade') as fade:
            active_mock = backend.active
            covered = fade.return_value.__enter__.return_value
            covered.timeout.return_value = .1
            covered.ensure_covered.side_effect = RuntimeError('watchdog expired during gate check')
            with self.assertRaises(RuntimeError):
                backend.apply(FakeBackend().baseline, 1)
        ipc.assert_not_called()
        active_mock.assert_any_call(timeout=.025)
        covered.ensure_covered.assert_called_once()

    def test_cover_deadline_reserves_hold_time_and_rechecks_status(self):
        fade = rotation.RotationFade('eDP-1')
        fade.deadline = 10
        with patch.object(rotation.time, 'monotonic', return_value=9.9):
            with self.assertRaises(RuntimeError): fade.timeout(reserve=.3)
        with patch.object(rotation.time, 'monotonic', return_value=9), \
                patch.object(fade, 'call', return_value='done'):
            with self.assertRaises(RuntimeError): fade.ensure_covered(.3)
        with patch.object(rotation.time, 'monotonic', return_value=9), \
                patch.object(fade, 'call', return_value='covered') as ipc:
            fade.ensure_covered(.3)
        ipc.assert_called_once_with('status', timeout=.2)

    def test_gate_closing_during_cover_prevents_rotation(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        with patch.object(backend, 'panel', return_value={'transform':0}), \
                patch.object(backend, 'headless', return_value=False), \
                patch.object(backend, 'active', side_effect=[True, False]), \
                patch.object(backend, 'settle_delay', return_value=0), \
                patch.object(backend, 'hypr') as ipc, patch.object(rotation, 'RotationFade') as fade:
            fade.return_value.__enter__.return_value.timeout.return_value = .8
            with self.assertRaises(RuntimeError):
                backend.apply(FakeBackend().baseline, 1)
        ipc.assert_not_called()

    def test_unchanged_orientation_does_not_flash(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        backend.monitor = 'eDP-1'
        with patch.object(backend, 'panel', return_value={'transform':1}), \
                patch.object(backend, 'hypr', return_value=chr(10).join(['ok'] * 5)), \
                patch.object(rotation, 'RotationFade') as fade:
            backend.apply(FakeBackend().baseline, 1)
        fade.assert_not_called()

    def test_reveal_failure_clears_cover_without_undoing_valid_rotation(self):
        fade = rotation.RotationFade('eDP-1')
        with patch.object(fade, 'call', side_effect=RuntimeError('lost IPC')), \
                patch.object(fade, 'close') as close, patch('builtins.print'):
            fade.__exit__(None, None, None)
        close.assert_called_once()

    def test_startup_failure_closes_owned_overlay(self):
        fade = rotation.RotationFade('eDP-1')
        with patch.dict(os.environ, {'TABLET_ROTATION_FADE_QML': '/immutable/fade.qml'}), \
                patch.object(rotation.subprocess, 'Popen'), \
                patch.object(fade, 'wait_for', side_effect=RuntimeError('bad QML')), \
                patch.object(fade, 'close') as close:
            with self.assertRaises(RuntimeError): fade.__enter__()
        close.assert_called_once()

    def test_ipc_targets_only_owned_pid(self):
        fade = rotation.RotationFade('eDP-1')
        fade.process = MagicMock(pid=1234)
        fade.process.poll.return_value = None
        with patch.object(rotation.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,'covered','')) as run:
            self.assertEqual(fade.call('status'), 'covered')
        self.assertEqual(run.call_args.args[0], ['quickshell','ipc','--pid','1234','call','rotationFade','status'])

    def test_hold_uses_inherited_resize_animation_without_changing_settings(self):
        backend = rotation.Backend.__new__(rotation.Backend)
        groups = [[{'name':'windowsMove','overridden':False},
                   {'name':'windows','overridden':True,'enabled':True,'speed':4.79}]]
        with patch.object(backend, 'hypr', return_value=groups) as ipc:
            self.assertAlmostEqual(backend.settle_delay(), .529)
        ipc.assert_called_once_with('animations', '-j', json_output=True)
        with patch.object(backend, 'hypr', return_value=[]):
            self.assertEqual(backend.settle_delay(), .55)

    def test_qml_is_monitor_scoped_with_independent_timeout(self):
        root = SOURCE.parents[2]
        qml = (root/'config/quickshell/tablet-rotation-fade/shell.qml').read_text()
        self.assertIn('s.name === Quickshell.env("TABLET_FADE_MONITOR")', qml)
        state = (root/'config/quickshell/tablet-rotation-fade/FadeState.qml').read_text()
        self.assertIn('hardTimeout: 3000', state)
        self.assertNotIn('Behavior on', state)
        self.assertIn('onFinished: rendered.restart()', state)
        self.assertIn('exclusionMode: ExclusionMode.Ignore', qml)
        self.assertIn('keyboardFocus: WlrKeyboardFocus.None', qml)
        self.assertIn('window.backingWindowVisible', qml)
        self.assertIn('root.phase = "covered"', state)
        self.assertIn('onResourcesLost: Qt.quit()', qml)
        self.assertNotIn('grabToImage', qml)


class BackendGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.backend = rotation.Backend.__new__(rotation.Backend)
        self.backend.runtime = Path(self.tmp.name)
        self.backend.instance = 'test'
        self.backend.monitor = 'eDP-1'
        self.mode = {'enabled': True, 'instance': 'test'}
        self.mode_path = self.backend.runtime/'tablet-workspace.json'
        self.mode_path.write_text(json.dumps(self.mode))
        self.workspace = {'name': 'tablet-trial', 'monitor': 'eDP-1'}

    def tearDown(self): self.tmp.cleanup()

    def active(self, panel=None, process_code=1, headless=False):
        panel = {'transform': 0} if panel is None else panel
        with patch.object(self.backend, 'hypr', return_value=self.workspace), \
                patch.object(self.backend, 'panel', return_value=panel), \
                patch.object(self.backend, 'headless', return_value=headless), \
                patch.object(rotation.subprocess, 'run') as pgrep:
            pgrep.return_value.returncode = process_code
            return self.backend.active()

    def test_foreground_gate_accepts_only_explicit_same_instance_mode(self):
        self.assertTrue(self.active())
        for state in ({'enabled': False, 'instance': 'test'}, {'enabled': True, 'instance': 'old'}):
            self.mode_path.write_text(json.dumps(state))
            self.assertFalse(self.active())

    def test_invalid_workspace_state_cannot_claim_sensor(self):
        for value in ([], None, {'enabled': 'false', 'instance': 'test'}):
            self.mode_path.write_text(json.dumps(value))
            self.assertFalse(self.active())

    def test_other_workspace_and_external_monitor_are_not_tablet_mode(self):
        self.workspace['name'] = 'work'
        self.assertFalse(self.active())
        self.workspace = {'name': 'tablet-trial', 'monitor': 'DP-2'}
        self.assertFalse(self.active())

    def test_headless_special_workspace_and_sensor_conflict_block_rotation(self):
        self.assertFalse(self.active(headless=True))
        self.assertFalse(self.active(panel={'specialWorkspace': {'id': -1}}))
        self.assertFalse(self.active(process_code=0))
        self.assertFalse(self.active(process_code=2))

    def test_packaged_and_unwrapped_mewtion_names_block_sensor_claim(self):
        for comm in ('Mewtion', '.Mewtion-wrappe'):
            def pgrep(args, **kwargs):
                return subprocess.CompletedProcess(args, 0 if re.fullmatch(args[2], comm, re.I) else 1)
            with self.subTest(comm=comm), \
                    patch.object(self.backend, 'hypr', return_value=self.workspace), \
                    patch.object(self.backend, 'panel', return_value={'transform': 0}), \
                    patch.object(self.backend, 'headless', return_value=False), \
                    patch.object(rotation.subprocess, 'run', side_effect=pgrep):
                self.assertFalse(self.backend.active())

    def test_native_session_rotates_in_place_only_with_live_owner_and_lease(self):
        self.backend.native = True
        self.workspace = {'name': 'Machine · Browser', 'monitor': 'eDP-1'}
        start = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
        state = {'native': True, 'instance': 'test', 'rotation_enabled': True,
                 'workspace': 'Machine · Browser', 'home_only': True,
                 'owner': {'pid': os.getpid(), 'start': start}}
        directory = self.backend.runtime / 'tablet-proof'
        directory.mkdir()
        path = directory / 'recovery.json'
        path.write_text(json.dumps({'window': state}))
        self.assertTrue(self.active())
        state['owner']['start'] = 'recycled'
        path.write_text(json.dumps({'window': state}))
        self.assertFalse(self.active())
        state['owner']['start'] = start
        state['rotation_enabled'] = False
        path.write_text(json.dumps({'window': state}))
        self.assertFalse(self.active())
        state.update(rotation_enabled=True, home_only=False, address='0xab', stableId='abc')
        path.write_text(json.dumps({'window': state}))
        self.assertFalse(self.active())  # foreground query lacks leased stableId
        with patch.object(self.backend, 'hypr', side_effect=[self.workspace, {'address': '0xab', 'stableId': 'abc'}]), \
                patch.object(self.backend, 'panel', return_value={'transform': 0}), \
                patch.object(self.backend, 'headless', return_value=False), \
                patch.object(rotation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertTrue(self.backend.active())

    def test_disabled_or_dpms_off_panel_is_not_selected(self):
        with patch.object(self.backend, 'hypr', return_value=[{'name': 'eDP-1', 'disabled': True}]):
            self.assertIsNone(self.backend.panel())
        with patch.object(self.backend, 'hypr', return_value=[{'name': 'eDP-1', 'dpmsStatus': False}]):
            self.assertIsNone(self.backend.panel())

    def test_bad_recovery_names_fail_closed(self):
        self.backend.policy = {'devices': [{'name': 'internal'}]}
        self.backend.journal = self.backend.runtime/'tablet-orientation.json'
        self.backend.journal.write_text(json.dumps({'instance': 'test', 'monitor': 'eDP-1', 'transform': 0,
                                                    'inputs': [{'name': 'external; dispatch exit', 'transform': 0, 'output': ''}]}))
        with self.assertRaises(RuntimeError):
            self.backend.load()


class DaemonSchedulingTests(unittest.TestCase):
    def test_main_waits_for_sensor_or_deadline_without_fixed_sleep(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            backend.runtime = Path(directory)
            controller = MagicMock()
            def stop_after_wait(now):
                rotation.STOP = True
            controller.wait_for_work.side_effect = stop_after_wait
            with patch.object(rotation, 'Backend', return_value=backend), \
                    patch.object(rotation, 'Controller', return_value=controller), \
                    patch.object(rotation, 'STOP', False), \
                    patch.object(rotation.signal, 'signal'), \
                    patch.object(rotation.time, 'sleep') as sleep, \
                    patch.object(sys, 'argv', ['tablet-orientation', 'daemon']):
                self.assertEqual(rotation.main(), 0)
            controller.tick.assert_called_once()
            controller.wait_for_work.assert_called_once()
            sleep.assert_not_called()


class DaemonOwnershipTests(unittest.TestCase):
    def test_healthy_singleton_does_not_start_another_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            backend.runtime = Path(directory)
            owner = backend.runtime/'tablet-orientation-owner.json'
            owner.write_text(json.dumps({'instance': 'test', 'config': backend.token}))
            with (backend.runtime/'lock').open('w') as lock, \
                    patch.object(rotation.fcntl, 'flock', side_effect=BlockingIOError), \
                    patch.object(rotation.time, 'sleep') as sleep:
                self.assertFalse(rotation.claim_daemon(backend, lock))
            sleep.assert_not_called()

    def test_stale_singleton_waits_then_acquires_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            backend.runtime = Path(directory)
            owner = backend.runtime/'tablet-orientation-owner.json'
            owner.write_text(json.dumps({'instance': 'test', 'config': ['old']}))
            with (backend.runtime/'lock').open('w') as lock, \
                    patch.object(rotation.fcntl, 'flock', side_effect=[BlockingIOError, None]), \
                    patch.object(rotation.time, 'sleep') as sleep:
                self.assertTrue(rotation.claim_daemon(backend, lock))
            sleep.assert_called_once()
            self.assertEqual(json.loads(owner.read_text())['config'], backend.token)


class SimulatedDaemonTest(unittest.TestCase):
    def test_daemon_rotates_and_restores_using_only_fake_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'bin').mkdir()
            (root/'hypr').mkdir()
            (root/'hypr/hyprland.conf').write_text('simulated configuration')
            fixture = root/'fixture.json'
            fixture.write_text(json.dumps({'workspace': 'tablet-trial', 'transform': 0}))
            (root/'tablet-workspace.json').write_text(json.dumps({'enabled': True, 'instance': 'test'}))
            policy = {'monitor': 'eDP-1', 'devices': [
                {'name': 'built-in-touch', 'kind': 'touch'}, {'name': 'built-in-pen', 'kind': 'pen'}]}
            (root/'policy.json').write_text(json.dumps(policy))
            hypr = root/'bin/hyprctl'
            hypr.write_text(f'#!{sys.executable}\n' + '''import json,os,sys
from pathlib import Path
p=Path(os.environ['FIXTURE']); value=json.loads(p.read_text());args=sys.argv[1:]
if args[0]=='activeworkspace':print(json.dumps({'name':value['workspace'],'monitor':'eDP-1'}))
elif args[0]=='monitors':print(json.dumps([{'name':'eDP-1','transform':value['transform']}]))
elif args[0]=='devices':print(json.dumps({'touch':[{'name':'built-in-touch'}],'tablets':[{'name':'built-in-pen'}]}))
elif args[0]=='animations':print(json.dumps([[{'name':'windowsMove','overridden':True,'enabled':False,'speed':0}]]))
elif args[0]=='getoption':print(json.dumps({'int':0,'str':'[[Auto]]' if 'touchdevice' in args[1] else '[[EMPTY]]'}))
elif args[0]=='--batch':
 commands=args[1].split('; ')
 for command in commands:
  with p.with_suffix('.commands').open('a') as f:f.write(command+'\\n')
  if command.startswith('keyword monitor '):value['transform']=int(command.rsplit(',',1)[1])
 temporary=p.with_suffix('.tmp');temporary.write_text(json.dumps(value));temporary.replace(p);print('\\n'.join(['ok']*len(commands)))
else:raise SystemExit(1)
''')
            sensor = root/'bin/monitor-sensor'
            sensor.write_text(f'#!{sys.executable}\n' + '''import os,signal,sys,time
from pathlib import Path
marker=Path(os.environ['FIXTURE']).with_suffix('.claimed');marker.touch()
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
try:
 print('=== Has accelerometer (orientation: left-up, tilt: vertical)',flush=True)
 while True:time.sleep(.1)
finally:marker.unlink(missing_ok=True)
''')
            quickshell = root/'bin/quickshell'
            quickshell.write_text(f'#!{sys.executable}\n' + '''import os,signal,sys,time
from pathlib import Path
phase=Path(os.environ['FIXTURE']).with_suffix('.fade')
if sys.argv[1]=='ipc':
 method=sys.argv[-1]
 if method=='cover':phase.write_text('covered')
 elif method=='reveal':phase.write_text('done')
 elif method=='status':print(phase.read_text() if phase.exists() else 'starting')
else:
 phase.write_text('ready')
 signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
 while True:time.sleep(.1)
''')
            pgrep = root/'bin/pgrep'
            pgrep.write_text('#!/bin/sh\nexit 1\n')
            for file in (hypr, sensor, pgrep, quickshell): file.chmod(0o700)
            env = dict(os.environ, PATH=str(root/'bin')+':'+os.environ['PATH'], XDG_RUNTIME_DIR=str(root),
                       XDG_CONFIG_HOME=str(root), HYPRLAND_INSTANCE_SIGNATURE='test',
                       TABLET_ORIENTATION_POLICY=str(root/'policy.json'), FIXTURE=str(fixture),
                       TABLET_ROTATION_FADE_QML=str(root/'fake-fade.qml'))
            driver = ('import runpy,sys; ns=runpy.run_path(' + repr(str(SOURCE)) + '); '
                      'ns["Backend"].headless=lambda self:False; '
                      'sys.argv=["tablet-orientation","daemon"]; sys.exit(ns["main"]())')
            process = subprocess.Popen([sys.executable, '-B', '-c', driver], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes = [process]
            try:
                def wait_for(predicate):
                    deadline = time.monotonic()+8
                    while time.monotonic()<deadline:
                        if predicate(): return
                        if process.poll() is not None:
                            self.fail(process.communicate()[1].decode())
                        time.sleep(.05)
                    self.fail('Simulated controller did not reach expected state')
                wait_for(lambda: json.loads(fixture.read_text())['transform']==1)
                # Change only the fake mode gate, never the real compositor.
                (root/'tablet-workspace.json').write_text(json.dumps({'enabled': False, 'instance':'test'}))
                wait_for(lambda: json.loads(fixture.read_text())['transform']==0)
                wait_for(lambda: not fixture.with_suffix('.claimed').exists())
                wait_for(lambda: not (root/'tablet-orientation.json').exists())
                # Re-enter, then force the config-change/startup interleaving:
                # old daemon cannot observe the new token until workspace.lock
                # is released, so the replacement must wait rather than exit.
                (root/'tablet-workspace.json').write_text(json.dumps({'enabled': True, 'instance':'test'}))
                wait_for(lambda: json.loads(fixture.read_text())['transform']==1)
                old_process = process
                with (root/'tablet-workspace.lock').open('w') as workspace_lock:
                    fcntl.flock(workspace_lock, fcntl.LOCK_EX)
                    (root/'hypr/hyprland.conf').write_text('new simulated configuration after deployment')
                    fixture.write_text(json.dumps({'workspace':'tablet-trial', 'transform':0}))
                    process = subprocess.Popen([sys.executable, '-B', '-c', driver], env=env,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    processes.append(process)
                    time.sleep(.2)
                    self.assertIsNone(process.poll(), 'Replacement exited instead of waiting for stale owner')
                wait_for(lambda: json.loads(fixture.read_text())['transform']==1)
                old_process.wait(timeout=5)
                self.assertNotEqual(old_process.returncode, 0)
                (root/'tablet-workspace.json').write_text(json.dumps({'enabled': False, 'instance':'test'}))
                wait_for(lambda: json.loads(fixture.read_text())['transform']==0)
                wait_for(lambda: not fixture.with_suffix('.claimed').exists())
                wait_for(lambda: not (root/'tablet-orientation.json').exists())
                commands=fixture.with_suffix('.commands').read_text()
                self.assertNotIn('dispatch', commands)
                self.assertNotIn('DP-2', commands)
            finally:
                for child in processes:
                    if child.poll() is None:
                        child.send_signal(signal.SIGTERM)
                    out, err = child.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, err.decode())
            self.assertFalse((root/'tablet-orientation-owner.json').exists())


if __name__ == '__main__':
    unittest.main()
