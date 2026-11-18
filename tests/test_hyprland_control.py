import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'home/packages/hyprland-control'))
import hyprland_control as control


class ControlTests(unittest.TestCase):
    def test_string_literals_preserve_unicode_and_escape_all_controls(self):
        value = 'κítty 🐈 "\\\n\r\t\0\x01\x7f'
        encoded = control.literal(value)
        self.assertIn('κítty 🐈', encoded)
        self.assertNotIn('\n', encoded)
        self.assertIn('\\000', encoded)
        self.assertIn('\\127', encoded)
        lua = os.environ.get('LUA')
        if lua:
            result = subprocess.check_output([lua, '-e', 'io.write(' + encoded + ')'])
            self.assertEqual(result, value.encode())

    def test_names_cannot_inject_lua(self):
        for name in ('monitor);os.execute("x")','dsp..focus','get_config:foo',''):
            with self.assertRaises(ValueError): control.call(name, {})

    def test_silent_moves_use_follow_false_not_ignored_silent_field(self):
        request = control.dispatch_args('movetoworkspacesilent','name:α,address:0x123')
        self.assertIn('["follow"]=false', request[1])
        self.assertIn('["window"]="address:0x123"', request[1])
        self.assertNotIn('["silent"]', request[1])

    def test_group_move_is_into_group_not_reorder_within_group(self):
        self.assertIn('hl.dsp.window.move', control.dispatch_args('moveintogroup','r')[1])
        self.assertIn('["into_group"]="right"', control.dispatch_args('moveintogroup','r')[1])

    def test_setprop_uses_native_prop_key(self):
        self.assertIn('["prop"]="sync_fullscreen"',control.dispatch_args('setprop','address:0x1 sync_fullscreen unset')[1])

    def test_pixel_coordinates_and_tags_are_data(self):
        self.assertIn('["relative"]=false',control.dispatch_args('movewindowpixel','exact -10 20,address:0x1')[1])
        self.assertIn('["tag"]="-old"',control.dispatch_args('tagwindow','-old address:0x1')[1])
        with self.assertRaises(ValueError): control.dispatch_args('resizewindowpixel','exact 1;os.exit() 2,address:0x1')

    def test_unknown_operations_and_exec_prefixes_are_not_interpreted(self):
        for name,arg in [('unknown',''),('exec','[workspace other] program')]:
            with self.assertRaises(ValueError): control.dispatch_args(name,arg)

    def test_rule_replacement_disables_and_clears_before_enabling(self):
        request=control.rule_args('test',{'match':{'class':'^app$'},'workspace':'name:target silent'})
        code=request[1]
        self.assertLess(code.index('["enabled"]=false'),code.index('r:clear_effects()'))
        self.assertLess(code.index('r:clear_effects()'),code.index('["enabled"]=true'))
        self.assertNotIn('clear_effects',control.rule_args('test')[1])

    def test_actual_backend_negotiation_is_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            for output,expected in [('ok',True),('eval is only supported with the lua config manager',False)]:
                with patch.object(control.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')):
                    self.assertEqual(control.uses_lua('exact-cli'),expected)
            with patch.object(control.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'unknown','')):
                with self.assertRaises(RuntimeError): control.uses_lua()

    def test_legacy_path_uses_no_native_mutations(self):
        with patch.dict(os.environ,{'HYPRLAND_CONTROL_TEST_BACKEND':'legacy'}):
            args=['dispatch','tagwindow','--','-tag address:0x1']
            self.assertEqual(control.desktop_args('ctl',args),args)
            self.assertEqual(control.desktop_exec_args('ctl','kitty',{'workspace':'name:target silent'}),['dispatch','exec','[workspace name:target silent] kitty'])

    def test_native_exec_rules_are_structured(self):
        with patch.dict(os.environ,{'HYPRLAND_CONTROL_TEST_BACKEND':'lua'}):
            args=control.desktop_exec_args('ctl','env TOKEN=x kitty',{'workspace':'name:target silent'})
            self.assertEqual(args[0],'dispatch')
            self.assertIn('hl.dsp.exec_cmd("env TOKEN=x kitty",{',args[1])
            self.assertNotIn('[workspace',args[1])

    def test_posture_setting_types_and_allowlist(self):
        with patch.dict(os.environ,{'HYPRLAND_CONTROL_TEST_BACKEND':'lua'}):
            self.assertIn('["workspace_swipe_touch"]=false',control.setting_args('gestures:workspace_swipe_touch',0)[1])
            self.assertIn('["follow_mouse"]=3',control.setting_args('input:follow_mouse',3)[1])
            with self.assertRaises(ValueError): control.setting_args('anything',1)

    def test_config_identity_tracks_lua_not_stale_legacy_copy(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'XDG_CONFIG_HOME':temp}):
            root=Path(temp)/'hypr';root.mkdir()
            (root/'hyprland.conf').write_text('old')
            (root/'hyprland.lua').write_text('new')
            with patch.object(control,'uses_lua',return_value=False):
                self.assertEqual(control.config_path().suffix,'.conf')
            with patch.object(control,'uses_lua',return_value=True):
                self.assertEqual(control.config_path().suffix,'.lua')


if __name__=='__main__': unittest.main()
