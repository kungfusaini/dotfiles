import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch, call

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tablet_session_trial', ROOT / 'hosts/kirax1/scripts/desktop/tablet-session-trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class SessionTrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'source.json'
        self.state = patch.object(trial, 'STATE', self.path)
        self.state.start()

    def tearDown(self):
        self.state.stop()
        self.tmp.cleanup()

    def test_source_must_be_active_owner_wayland_session(self):
        for value in ({'Name':'tablet-trial'}, {'Name':'sumeet','Type':'tty','Seat':'seat0'},
                      {'Name':'sumeet','Type':'wayland','Seat':'seat0','LockedHint':'yes'}):
            with patch.object(trial, 'active', return_value='3'), patch.object(trial, 'properties', return_value=value):
                with self.assertRaises(RuntimeError): trial.save_source()
        self.assertFalse(self.path.exists())

    def test_source_saved_privately_without_caller_supplied_id(self):
        with patch.object(trial, 'active', return_value='3'), patch.object(trial, 'properties',
                return_value={'Name':'sumeet','Type':'wayland','Seat':'seat0','VTNr':'1'}):
            trial.save_source()
        self.assertEqual(json.loads(self.path.read_text()), {'session':'3','user':'sumeet','vt':'1'})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_first_entry_starts_service_even_when_inactive(self):
        with patch.object(trial, 'save_source'), patch.object(trial.subprocess, 'run', return_value=Mock(returncode=3,stdout='inactive')), \
                patch.object(trial, 'trial_session', return_value='8'), patch.object(trial, 'check_vt') as check, \
                patch.object(trial, 'run') as run:
            result = trial.enter()
        check.assert_called_once()
        run.assert_called_once_with('systemctl','start',trial.UNIT)
        self.assertTrue(result['cold'])

    def test_warm_entry_activates_without_restart(self):
        with patch.object(trial, 'save_source'), patch.object(trial.subprocess, 'run', return_value=Mock(returncode=0,stdout='active')), \
                patch.object(trial, 'trial_session', return_value='8'), patch.object(trial, 'run') as run:
            result = trial.enter()
        run.assert_called_once_with('loginctl','activate','8')
        self.assertFalse(result['cold'])

    def test_active_service_without_session_refuses_activation(self):
        with patch.object(trial, 'save_source'), patch.object(trial.subprocess, 'run', return_value=Mock(returncode=0,stdout='active')), \
                patch.object(trial, 'trial_session', return_value=''), patch.object(trial, 'run') as run:
            with self.assertRaises(RuntimeError): trial.enter()
        run.assert_not_called()

    def test_occupied_vt_is_not_claimed(self):
        idle='LoadState=loaded\nActiveState=inactive'
        with patch.object(trial, 'run', side_effect=[idle,idle,'other 1001 someone']), \
                patch.object(trial, 'properties', return_value={'VTNr':'8'}):
            with self.assertRaisesRegex(RuntimeError, 'already belongs'): trial.check_vt()

    def test_busy_getty_states_are_refused_without_stopping_it(self):
        for state in ('active','activating','deactivating','reloading','unknown',''):
            with patch.object(trial,'run',return_value='LoadState=loaded\nActiveState='+state) as run:
                with self.assertRaisesRegex(RuntimeError,'busy or unqueryable getty'): trial.check_vt()
            run.assert_called_once_with('systemctl','show','getty@tty8.service','--property=LoadState','--property=ActiveState')

    def test_failed_getty_query_does_not_mean_unoccupied(self):
        with patch.object(trial,'run',side_effect=subprocess.CalledProcessError(1,'show')) as run:
            with self.assertRaises(subprocess.CalledProcessError): trial.check_vt()
        self.assertEqual(run.call_count,1)

    def test_return_never_guesses_missing_source(self):
        with patch.object(trial, 'run') as run:
            trial.return_to_laptop()
        run.assert_not_called()

    def test_return_validates_source_identity(self):
        self.path.write_text(json.dumps({'session':'3','vt':'1'}))
        with patch.object(trial, 'properties', return_value={'Name':'other','Seat':'seat0','VTNr':'1'}), \
                patch.object(trial, 'run') as run:
            with self.assertRaises(RuntimeError): trial.return_to_laptop()
        run.assert_not_called()

    def test_return_does_not_steal_focus_from_other_session(self):
        self.path.write_text(json.dumps({'session':'3','vt':'1'}))
        with patch.object(trial, 'properties', side_effect=[{'Name':'sumeet','Seat':'seat0','VTNr':'1'},{'Name':'someone'}]), \
                patch.object(trial, 'active', return_value='9'), patch.object(Path, 'read_text', autospec=True) as read, \
                patch.object(trial, 'run') as run:
            read.side_effect = lambda path: json.dumps({'session':'3','vt':'1'}) if path == self.path else 'tty9'
            with self.assertRaises(RuntimeError): trial.return_to_laptop()
        run.assert_not_called()

    def test_return_only_activates_saved_session_without_unlocking(self):
        self.path.write_text(json.dumps({'session':'3','vt':'1'}))
        with patch.object(trial, 'properties', side_effect=[{'Name':'sumeet','Seat':'seat0','VTNr':'1'},{'Name':'tablet-trial'}]), \
                patch.object(trial, 'active', return_value='8'), patch.object(Path, 'read_text', autospec=True) as read, \
                patch.object(trial, 'run') as run:
            read.side_effect = lambda path: json.dumps({'session':'3','vt':'1'}) if path == self.path else 'tty8'
            trial.return_to_laptop()
        run.assert_called_once_with('loginctl','activate','3')

    def test_stop_still_cleans_up_when_return_is_unsafe(self):
        for reason in ('saved source ended', 'another session is foreground'):
            with patch.object(trial,'return_to_laptop',side_effect=RuntimeError(reason)), \
                    patch.object(trial,'run') as run:
                with self.assertRaisesRegex(RuntimeError,reason): trial.stop_trial()
            self.assertEqual(run.call_args_list,[call('systemctl','stop',trial.UNIT),call('loginctl','terminate-user',trial.USER)])

    def test_corrupt_source_does_not_block_cleanup(self):
        for content in ('{broken', '{}', '[]'):
            self.path.write_text(content)
            with patch.object(trial,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'return:'): trial.stop_trial()
            self.assertEqual(run.call_args_list,[call('systemctl','stop',trial.UNIT),call('loginctl','terminate-user',trial.USER)])

    def test_failed_service_stop_still_terminates_only_trial_user(self):
        with patch.object(trial,'return_to_laptop'), \
                patch.object(trial,'run',side_effect=[subprocess.CalledProcessError(1,'stop'),'']) as run:
            with self.assertRaisesRegex(RuntimeError,'service stop'): trial.stop_trial()
        self.assertEqual(run.call_args_list[-1],call('loginctl','terminate-user','tablet-trial'))

    def test_measurement_on_ac_is_not_a_battery_comparison(self):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == 'status': return 'Charging'
            if path.name in ('energy_now','power_now'): return '10000000'
            if path.name == 'cpu.stat': return 'usage_usec 1000'
            if path.name == 'memory.current': return '1024'
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read), patch.object(trial,'active',return_value='3'), \
                patch.object(trial.time,'sleep'), patch.object(trial.time,'monotonic',side_effect=[0,1]):
            result = trial.sample(1)
        self.assertFalse(result['batteryDataUsable'])

    def test_module_is_opt_in_no_freeze_or_default_desktop_change(self):
        module=(ROOT/'hosts/kirax1/modules/desktop/tablet-session-trial.nix').read_text()
        self.assertNotIn('wantedBy',module)
        self.assertNotIn('defaultSession',module)
        self.assertNotIn('freeze',module)
        self.assertIn('subject.active',module)
        self.assertIn('tablet-session-trial-return.service',module)


if __name__ == '__main__': unittest.main()
