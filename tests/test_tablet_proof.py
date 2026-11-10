import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch, call

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tablet_proof', ROOT / 'home/packages/tablet-proof/controller.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.tmp.name, 'HYPRLAND_INSTANCE_SIGNATURE': 'instance'}, clear=False)
        self.env.start()
        self.keyboard = Mock(process=None, settings=[])
        self.controls = Mock()
        self.proof = p.Proof(controls=self.controls, keyboard=self.keyboard)
        self.proof.record = {'instance':'instance','address':'0xab','pid':42,'start':'start','class':'vivaldi-stable',
                             'workspace':'work','origin':'work','focus':{'address':'0xab','pid':42,'class':'vivaldi-stable','stableId':'123'},'stableId':'123','tag':'proof-exact','internal':0,'client':0,
                             'sync':'true','applied':True,'tagged':True,'introduced_maximize':True,'config_changed':False}
        self.client = {'address':'0xab','pid':42,'class':'vivaldi-stable','mapped':True,'tags':['proof-exact'],
                       'workspace':{'name':'work'},'stableId':'123','monitor':0,'floating':False,'fullscreen':2,'fullscreenClient':1}

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_window_requires_tag_not_shared_browser_pid(self):
        replacement = dict(self.client, tags=[])
        with patch.object(p,'start_time',return_value='start'), patch.object(p,'hypr',return_value=[replacement]):
            with self.assertRaisesRegex(RuntimeError,'exact proof window'): self.proof.window()

    def test_same_process_recycled_address_does_not_reuse_window_lease(self):
        replacement=dict(self.client,stableId='456')
        with patch.object(p,'start_time',return_value='start'), patch.object(p,'hypr',return_value=[replacement]):
            with self.assertRaises(RuntimeError): self.proof.window()

    def test_stale_compositor_never_claims_window(self):
        self.proof.record['instance']='old'
        with patch.object(p,'hypr') as query:
            with self.assertRaises(RuntimeError): self.proof.window()
        query.assert_not_called()

    def test_same_workspace_focus_loss_ends_eligibility(self):
        monitor={'id':0,'name':'eDP-1','dpmsStatus':True}
        with patch.object(self.proof,'window',return_value=self.client), patch.object(p.Path,'read_text',return_value='off'), \
                patch.object(p,'hypr',side_effect=[[monitor],{'name':'work','monitor':'eDP-1'},{'address':'0xsibling'}]):
            with self.assertRaisesRegex(RuntimeError,'no longer foreground'): self.proof.guard()

    def test_floating_transition_ends_eligibility(self):
        self.client['floating']=True
        with patch.object(self.proof,'window',return_value=self.client), patch.object(p.Path,'read_text',return_value='off'), \
                patch.object(p,'hypr',side_effect=[[{'id':0,'name':'eDP-1'}],{'name':'work','monitor':'eDP-1'}]):
            with self.assertRaises(RuntimeError): self.proof.guard()

    def test_unmodified_initial_modes_do_not_bypass_focus_loss_recovery(self):
        self.proof.record.update(internal=2,client=2,introduced_maximize=False,applied=False)
        self.proof.journal()
        with patch.object(self.proof,'window',return_value=self.client), \
                patch.object(self.proof,'guard',side_effect=RuntimeError('focus lost')), patch.object(p,'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'recovery retained'): self.proof.cleanup()
        self.assertTrue((p.runtime()/'recovery.json').exists())
        dispatch.assert_not_called()
        self.keyboard.stop.assert_called_once()

    def test_native_state_is_idempotent_not_toggle(self):
        with patch.object(self.proof,'guard',return_value=(self.client,{})), \
                patch.object(p,'hypr',return_value={'address':'0xab'}), patch.object(p,'dispatch') as dispatch:
            self.proof.modes(2,1)
        dispatch.assert_not_called()

    def test_lost_focus_blocks_native_fullscreen(self):
        with patch.object(self.proof,'guard',return_value=(self.client,{})), \
                patch.object(p,'hypr',return_value={'address':'0xother'}), patch.object(p,'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'lost focus'): self.proof.modes(0,0)
        dispatch.assert_not_called()

    def test_native_state_change_never_resizes_or_floats(self):
        with patch.object(self.proof,'guard',return_value=(self.client,{})), \
                patch.object(p,'hypr',return_value={'address':'0xab'}), patch.object(p,'dispatch') as dispatch:
            self.proof.modes(0,0)
        dispatch.assert_called_once_with('fullscreenstate','0 0')

    def test_home_and_settings_do_not_change_video_fullscreen(self):
        with patch.object(self.proof,'guard'), patch.object(self.proof,'state',return_value={}), \
                patch.object(p,'dispatch') as dispatch:
            self.proof.action('home')
            self.proof.action('settings')
            self.proof.action('dismiss')
            self.proof.action('app')
        dispatch.assert_not_called()
        self.keyboard.hide.assert_called_once()
        self.controls.read.assert_called_once()
        self.assertFalse(self.proof.home)
        self.assertFalse(self.proof.drawer)

    def test_live_controls_only_change_while_drawer_open(self):
        with patch.object(self.proof,'guard'), patch.object(self.proof,'state',return_value={}):
            with self.assertRaises(RuntimeError): self.proof.action('brightness',30)
            self.proof.drawer=True
            self.proof.action('brightness',30)
        self.controls.change.assert_called_once_with('brightness',30)

    def test_controls_reject_invalid_values_without_side_effect(self):
        for value in (-1,101,'50',True,float('nan')):
            with patch.object(p,'run') as run:
                with self.assertRaises(RuntimeError): p.Controls().change('volume',value)
            run.assert_not_called()

    def test_controls_do_not_invent_unavailable_values(self):
        with patch.object(p,'run',side_effect=FileNotFoundError()):
            self.assertEqual(p.Controls().read(),{'volume':None,'muted':False,'brightness':None})

    def test_keyboard_cannot_address_replaced_bus_owner(self):
        keyboard=p.Keyboard(); keyboard.process=Mock(pid=42); keyboard.process.poll.return_value=None
        with patch.object(p,'run',side_effect=["(':1.4',)",'(uint32 99,)']) as run:
            with self.assertRaisesRegex(RuntimeError,'replaced'): keyboard.hide()
        self.assertEqual(run.call_count,2)
        self.assertFalse(any('SetVisible' in str(c) for c in run.call_args_list))

    def test_keyboard_restores_only_unchanged_settings(self):
        keyboard=p.Keyboard(); keyboard.settings=[['schema','first','false','true'],['schema','second','1','2']]
        with patch.object(p,'run',side_effect=['3','true','']) as run:
            keyboard.stop()
        self.assertEqual(run.call_args_list,[call('gsettings','get','schema','second'),
                         call('gsettings','get','schema','first'),call('gsettings','set','schema','first','false')])

    @patch.object(p.Proof,'guard')
    def test_cleanup_reverts_own_maximize_and_removes_only_own_tag(self, guard):
        self.proof.journal()
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes') as modes, \
                patch.object(p,'dispatch') as dispatch, patch.object(p,'hypr',side_effect=[{'name':'work'},[{'name':'work'}],[self.client]]):
            self.proof.cleanup()
        modes.assert_called_once_with(0,0)
        self.assertIn(call('tagwindow','-proof-exact address:0xab'),dispatch.call_args_list)
        self.assertFalse((p.runtime()/'recovery.json').exists())

    @patch.object(p.Proof,'guard')
    def test_cleanup_preserves_user_media_request(self, guard):
        self.client['fullscreenClient']=2
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes') as modes, \
                patch.object(p,'dispatch'), patch.object(p,'hypr',side_effect=[{'name':'work'},[],]):
            self.proof.cleanup()
        modes.assert_called_once_with(2,2)

    @patch.object(p.Proof,'guard')
    def test_preexisting_media_exit_is_not_resurrected(self, guard):
        self.proof.record.update(internal=2,client=2,introduced_maximize=False,applied=False)
        self.client.update(fullscreen=1,fullscreenClient=1)
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes') as modes, \
                patch.object(p,'dispatch') as dispatch, patch.object(p,'hypr',side_effect=[{'name':'work'},[]]):
            self.proof.cleanup()
        modes.assert_not_called()
        self.assertFalse(any(c.args[0]=='setprop' for c in dispatch.call_args_list))

    @patch.object(p.Proof,'guard')
    def test_internal_only_change_does_not_restore_exited_client_media(self, guard):
        self.proof.record.update(internal=1,client=2,introduced_maximize=False)
        self.client.update(fullscreen=2,fullscreenClient=1)
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes') as modes, \
                patch.object(p,'dispatch'), patch.object(p,'hypr',side_effect=[{'name':'work'},[]]):
            self.proof.cleanup()
        modes.assert_called_once_with(1,1)

    @patch.object(p.Proof,'guard')
    def test_config_reload_drops_own_override_not_replays_old_policy(self, guard):
        self.proof.record['config_changed']=True
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes'), \
                patch.object(p,'dispatch') as dispatch, patch.object(p,'hypr',side_effect=[{'name':'work'},[]]):
            self.proof.cleanup()
        self.assertIn(call('setprop','address:0xab sync_fullscreen unset'),dispatch.call_args_list)

    @patch.object(p.Proof,'guard')
    def test_cleanup_failure_retains_recovery_and_stops_keyboard(self, guard):
        self.proof.journal()
        with patch.object(self.proof,'window',return_value=self.client), patch.object(self.proof,'modes',side_effect=RuntimeError('focus lost')), \
                patch.object(p,'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'recovery retained'): self.proof.cleanup()
        self.keyboard.stop.assert_called_once()
        self.assertTrue((p.runtime()/'recovery.json').exists())
        dispatch.assert_not_called()

    def test_disappeared_window_not_recreated_or_replaced(self):
        self.proof.journal()
        with patch.object(self.proof,'window',side_effect=RuntimeError('closed')), patch.object(p,'dispatch') as dispatch:
            self.proof.cleanup()
        dispatch.assert_not_called()
        self.assertFalse((p.runtime()/'recovery.json').exists())

    def test_recover_does_not_replay_different_compositor(self):
        p.save({'window':dict(self.proof.record,instance='old'),'children':[],'settings':[]})
        with patch.object(p,'dispatch') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'original compositor'): p.recover()
        dispatch.assert_not_called()

    def test_supervisor_recovers_backend_failure(self):
        process=Mock();process.wait.return_value=-9
        with patch.dict(os.environ,{'TABLET_PROOF_BIN':'/store/proof'}), patch.object(p.subprocess,'Popen',return_value=process), \
                patch.object(p.signal,'signal'), patch.object(p,'recover') as recover:
            self.assertEqual(p.supervise('0xab'),-9)
        recover.assert_called_once_with()

    def test_proof_package_does_not_hook_folding_or_launch_browser(self):
        source=(ROOT/'home/packages/tablet-proof/controller.py').read_text()
        self.assertNotIn('tablet-workspace',source)
        self.assertNotIn("dispatch('exec'",source)
        self.assertNotIn("dispatch('setfloating'",source)
        self.assertNotIn("dispatch('resizewindowpixel'",source)
        self.assertNotIn("dispatch('movetoworkspace",source)


if __name__=='__main__':unittest.main()
