import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / f'home/scripts/desktop/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fold = load('tablet-fold-watch')
workspace = load('tablet-workspace')


class FoldHomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.tmp.name,
                                          'HYPRLAND_INSTANCE_SIGNATURE': 'test'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def tick(self, watcher, folded='1', headless='off', monitor='eDP-1'):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path).endswith('hotkey_tablet_mode'):
                return folded
            if str(path) == '/run/headless-mode/state':
                return headless
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read), \
                patch.object(workspace, 'hypr', side_effect=[
                    [{'name': 'eDP-1'}], {'name': 'tablet-trial', 'monitor': monitor}, []]):
            watcher.tick()

    def test_fold_replaces_legacy_foreground_panel_once(self):
        workspace.save_state({'instance': 'test', 'return': 'work', 'enabled': True})
        enter, leave = Mock(), Mock()
        watcher = workspace.FoldWatcher(enter, leave, mode_active=lambda: False)
        self.tick(watcher)
        self.tick(watcher)
        enter.assert_called_once_with()
        with patch.object(workspace, 'enter', side_effect=AssertionError('legacy entry')):
            self.tick(watcher, folded='0')
        leave.assert_called_once_with()

    def test_fold_attaches_existing_home_and_unfold_closes_it(self):
        workspace.save_state({'instance': 'test', 'return': 'work', 'enabled': True})
        enter, leave = Mock(), Mock()
        watcher = workspace.FoldWatcher(enter, leave, mode_active=lambda: True)
        self.tick(watcher)
        enter.assert_not_called()
        self.tick(watcher, folded='0')
        leave.assert_called_once_with()

    def test_manual_home_is_adopted_then_restart_unfold_closes_it(self):
        workspace.save_state({'instance': 'test', 'return': 'work', 'enabled': True, 'automatic': False})
        def adopt():
            state = workspace.load_state()
            state['automatic'] = True
            workspace.save_state(state)
        watcher = workspace.FoldWatcher(adopt, Mock(), mode_active=lambda: False)
        self.tick(watcher)
        self.assertTrue(workspace.load_state()['automatic'])
        leave = Mock()
        restarted = workspace.FoldWatcher(Mock(), leave, mode_active=lambda: True)
        self.tick(restarted, folded='0')
        leave.assert_called_once_with()

    def test_failed_home_start_does_not_consume_fold_edge(self):
        enter = Mock(side_effect=RuntimeError('not ready'))
        watcher = workspace.FoldWatcher(enter, Mock(), mode_active=lambda: False)
        with self.assertRaises(RuntimeError):
            self.tick(watcher)
        self.assertIsNone(watcher.folded)
        enter.side_effect = None
        self.tick(watcher)
        self.assertTrue(watcher.folded)

    def test_external_focus_and_headless_never_launch_home(self):
        enter = Mock()
        watcher = workspace.FoldWatcher(enter, Mock(), mode_active=lambda: False)
        self.tick(watcher, monitor='HDMI-A-1')
        with patch.object(workspace.subprocess, 'run'):
            self.tick(watcher, headless='active')
        self.tick(watcher)
        enter.assert_not_called()

    def test_close_waits_for_home_cleanup_before_legacy_fallback(self):
        state = {'enabled': False}
        with patch.object(fold, 'chat', side_effect=[{'running': True}, {}, {'running': True}, {'running': False}]) as chat, \
                patch.object(fold.time, 'sleep'), patch.object(fold.subprocess, 'run') as run:
            fold.leave_home({'load_state': lambda: state})
        self.assertEqual(chat.call_args_list, [call('status'), call('close'), call('status'), call('status')])
        run.assert_not_called()

    def test_close_old_panel_after_migration_without_home(self):
        with patch.object(fold, 'chat', return_value={'running': False}), \
                patch.object(fold.subprocess, 'run') as run:
            fold.leave_home({'load_state': lambda: {'enabled': True}})
        run.assert_called_once_with(['tablet-workspace', 'leave-automatic'], check=True, timeout=15)

    def test_failed_close_does_not_run_legacy_leave_under_home(self):
        with patch.object(fold, 'chat', side_effect=[{'running': True}, RuntimeError('voice needs recovery')]), \
                patch.object(fold.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                fold.leave_home({'load_state': lambda: {'enabled': True}})
        run.assert_not_called()

    def test_pending_recovery_never_falls_back_to_legacy_leave(self):
        runtime = Path(self.tmp.name) / 'tablet-chat'
        runtime.mkdir()
        (runtime / 'recovery.json').write_text('{}')
        with patch.object(fold, 'chat', return_value={'running': False}), \
                patch.object(fold.time, 'monotonic', side_effect=[0, 36]), \
                patch.object(fold.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'journal retained'):
                fold.leave_home({'load_state': lambda: {'enabled': True}})
        run.assert_not_called()

    def test_chat_command_is_bounded_and_checked(self):
        with patch.object(fold.subprocess, 'run', return_value=Mock(stdout='{"running": true}')) as run:
            self.assertTrue(fold.chat('start-fold')['running'])
        run.assert_called_once_with(['tablet-chat', 'start-fold'], check=True, capture_output=True,
                                    text=True, timeout=40)


if __name__ == '__main__':
    unittest.main()
