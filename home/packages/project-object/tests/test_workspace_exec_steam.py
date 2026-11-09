"""Steam-only workspace routing contracts; no compositor/client is launched."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/project-workspace-exec'
loader = importlib.machinery.SourceFileLoader('workspace_exec_steam', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
h = importlib.util.module_from_spec(spec)
loader.exec_module(h)


def window(address='0xab', workspace='special:steam-hidden', cls='game', pid=123):
    return dict(address=address, mapped=True, workspace=dict(name=workspace), **{'class': cls}, pid=pid)


class SteamWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)
        def path(value):
            text = str(value)
            return self.proc / text.removeprefix('/proc').lstrip('/') if text.startswith('/proc') else Path(value)
        m = patch.object(h, 'Path', side_effect=path)
        m.start()
        self.addCleanup(m.stop)

    def process(self, pid=123, marker='launch', child=False, appid=None):
        p = self.proc / str(pid)
        p.mkdir(exist_ok=True)
        args = [b'/home/user/.local/share/Steam/ubuntu12_32/steam', b'-silent']
        if child:
            args.append(b'-child-update-ui')
        (p / 'cmdline').write_bytes(b'\0'.join(args) + b'\0')
        env = [f'{h.LAUNCH_ID_ENV}={marker}'.encode()]
        if appid:
            env.append(f'SteamGameId={appid}'.encode())
        (p / 'environ').write_bytes(b'\0'.join(env) + b'\0')
        return p

    def test_real_marked_tray_process_is_enough_without_window(self):
        self.process()
        self.assertEqual(h.steam_backend_pids('launch'), [123])
        with patch.object(h, 'hypr_clients', return_value=[]):
            h.verify_steam_backend('launch')

    def test_updater_or_previous_client_cannot_confirm_new_startup(self):
        self.process(pid=123, child=True)
        self.process(pid=124, marker='old')
        self.assertEqual(h.steam_backend_pids('launch'), [])
        with patch.object(h, 'hypr_clients', return_value=[]), \
             patch.object(h.time, 'monotonic', side_effect=[0, 0, 16]), patch.object(h.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'no newly launched'):
                h.verify_steam_backend('launch')

    def test_mapped_steam_client_must_be_hidden_not_moved_to_frontend(self):
        self.process()
        with patch.object(h, 'hypr_clients', return_value=[window(cls='steam')]):
            h.verify_steam_backend('launch')
        with patch.object(h, 'hypr_clients', return_value=[window(cls='steam', workspace='Other')]), \
             patch.object(h.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'outside its hidden'):
                h.verify_steam_backend('launch')
            run.assert_not_called()

    def test_hidden_policy_delegates_to_serialized_visibility_owner(self):
        with patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"manual": false}')) as run:
            h.steam_hide_rule()
        self.assertEqual(run.call_args.args[0], ['steam-library', 'configure-hidden-rule'])
        self.assertEqual(run.call_args.kwargs['env']['STEAM_VISIBILITY_HYPRCTL'], h.HYPRCTL)

    def test_manual_client_is_not_hidden_again_by_automated_game_launch(self):
        with patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"manual": true}')) as run:
            h.steam_hide_rule()
        self.assertEqual(run.call_count, 1)

    def test_manual_launcher_uses_invoking_context_and_its_own_ui_verification(self):
        with patch.object(sys, 'argv', ['project-workspace-exec', 'steam-manual']), \
             patch.object(h, 'hypr_clients', return_value=[]), \
             patch.object(h, 'invoking_workspace', return_value='Invoking workspace'), \
             patch.object(h, 'verify_window') as regular, \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            h.main()
            self.assertEqual(run.call_args.kwargs['env'][h.LAUNCH_WORKSPACE_ENV], 'Invoking workspace')
            regular.assert_not_called()

    def test_hidden_policy_failure_is_not_ignored(self):
        with patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'error')):
            with self.assertRaises(RuntimeError):
                h.steam_hide_rule()

    def test_game_identity_uses_exact_live_appid_not_window_title(self):
        self.process(appid=1687950)
        self.assertTrue(h.steam_game_process(123, 1687950))
        with patch.object(h, 'parent_pid', return_value=1):
            self.assertFalse(h.steam_game_process(123, 168795))
        self.assertFalse(h.steam_game_process(True, 1687950))

    def test_route_exact_game_silently_and_reverify_same_address(self):
        self.process(appid=1687950)
        with patch.object(h, 'hypr_clients', side_effect=[[window()], [window(workspace='Library')]]), \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')) as run, \
             patch.object(h.time, 'sleep'):
            h.verify_steam_game('Library', 1687950, set())
        self.assertEqual(run.call_args.args[0][-2:], ['movetoworkspacesilent', 'name:Library,address:0xab'])

    def test_disappearing_splash_is_replaced_only_by_verified_game_window(self):
        self.process(appid=1687950)
        frames = [[window(address='0xab')], [window(address='0xcd')],
                  [window(address='0xcd', workspace='Library')]]
        with patch.object(h, 'hypr_clients', side_effect=frames), \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')) as run, \
             patch.object(h.time, 'sleep'):
            h.verify_steam_game('Library', 1687950, set())
        self.assertEqual([c.args[0][-1] for c in run.call_args_list],
                         ['name:Library,address:0xab', 'name:Library,address:0xcd'])

    def test_existing_and_unrelated_windows_are_never_routing_guesses(self):
        self.process(appid=400)
        with patch.object(h, 'hypr_clients', return_value=[window(), window(address='0xcd', cls='steam')]), \
             patch.object(h, 'parent_pid', return_value=1), \
             patch.object(h.time, 'monotonic', side_effect=[0, 0, 181]), \
             patch.object(h.time, 'sleep'), patch.object(h.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'requested Steam game'):
                h.verify_steam_game('Library', 1687950, {'0xab'})
            run.assert_not_called()

    def test_main_steam_silent_uses_hidden_exec_and_process_verifier(self):
        with patch.object(sys, 'argv', ['project-workspace-exec', 'steam', '-silent']), \
             patch.object(h, 'hypr_clients', return_value=[]), \
             patch.object(h, 'invoking_workspace', return_value='Library'), \
             patch.object(h.secrets, 'token_hex', return_value='launch'), \
             patch.object(h, 'steam_hide_rule') as hide, patch.object(h, 'verify_steam_backend') as verify, \
             patch.object(h, 'verify_window') as regular, \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')) as run:
            h.main()
            hide.assert_called_once()
            verify.assert_called_once_with('launch')
            regular.assert_not_called()
            self.assertTrue(run.call_args.args[0][-1].startswith('[workspace special:steam-hidden silent]'))

    def test_main_steam_game_uses_exact_app_verifier(self):
        with patch.object(sys, 'argv', ['project-workspace-exec', 'steam', 'steam://rungameid/1687950']), \
             patch.object(h, 'hypr_clients', return_value=[]), \
             patch.object(h, 'invoking_workspace', return_value='Library'), \
             patch.object(h, 'steam_hide_rule'), patch.object(h, 'verify_steam_game') as verify, \
             patch.object(h, 'verify_window') as regular, \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')):
            h.main()
            verify.assert_called_once_with('Library', 1687950, set())
            regular.assert_not_called()

    def test_other_apps_still_require_mapped_window_verification(self):
        with patch.object(sys, 'argv', ['project-workspace-exec', 'kitty']), \
             patch.object(h, 'hypr_clients', return_value=[]), \
             patch.object(h, 'invoking_workspace', return_value='Library'), \
             patch.object(h, 'steam_hide_rule') as hide, patch.object(h, 'verify_steam_backend') as steam, \
             patch.object(h, 'verify_window') as regular, \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')):
            h.main()
            hide.assert_not_called()
            steam.assert_not_called()
            regular.assert_called_once()


if __name__ == '__main__':
    unittest.main()
