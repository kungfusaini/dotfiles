import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('preauthorized_browser', Path(__file__).resolve().parents[1] / 'browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
WS_PATH = '/devtools/browser/' + 'a' * 36
HTTP = 'http://127.0.0.1:45678'
WS = 'ws://127.0.0.1:45678' + WS_PATH


class PreauthorizedTests(unittest.TestCase):
    def test_port_reservation_uses_only_ipv4_loopback(self):
        listener = Mock()
        listener.getsockname.return_value = ('127.0.0.1', 45678)
        with patch.object(browser.socket, 'socket') as factory:
            factory.return_value.__enter__.return_value = listener
            self.assertEqual(browser.unused_loopback_port(), 45678)
            listener.bind.assert_called_once_with(('127.0.0.1', 0))

    def test_listener_verification_checks_pid_socket_inode_and_loopback(self):
        for address, inode, expected in [('0100007F', '42', True), ('0100007F', '99', False), ('00000000', '42', 'reject')]:
            line = f'0: {address}:B26E 00000000:0000 0A 0:0 00:0 0 1000 0 {inode}'
            def table(path):
                return 'header\n' if str(path).endswith('tcp6') else 'header\n' + line
            with self.subTest(address=address, inode=inode), \
                    patch.object(Path, 'iterdir', return_value=[Path('/proc/123/fd/1')]), \
                    patch.object(Path, 'readlink', return_value=Path('socket:[42]')), \
                    patch.object(Path, 'read_text', autospec=True, side_effect=table):
                if expected == 'reject':
                    with self.assertRaisesRegex(ValueError, 'loopback'):
                        browser.loopback_listener_owned(123, 45678)
                else:
                    self.assertIs(browser.loopback_listener_owned(123, 45678), expected)
        with patch.object(Path, 'iterdir', side_effect=PermissionError):
            self.assertFalse(browser.loopback_listener_owned(123, 45678))

    def test_owned_version_endpoint_is_validated_without_proxy(self):
        state = {'pid': 123, 'start': 'browser', 'endpoint': HTTP, 'websocketPath': WS_PATH}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps({'webSocketDebuggerUrl': WS}).encode())
        with patch.object(browser, 'process_start', return_value='browser'), \
                patch.object(browser, 'loopback_listener_owned', return_value=True) as owned, \
                patch.object(browser.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(browser.preauthorized_endpoint(state), WS)
            owned.assert_called_once_with(123, 45678)
            opener.open.assert_called_once_with(HTTP + '/json/version', timeout=2)
            self.assertEqual(build.call_args.args[0].proxies, {})

    def test_foreign_or_reused_listener_is_never_probed(self):
        state = {'pid': 123, 'start': 'browser', 'endpoint': HTTP}
        for start, owned in [('other-pid', True), ('browser', False)]:
            with self.subTest(start=start, owned=owned), \
                    patch.object(browser, 'process_start', return_value=start), \
                    patch.object(browser, 'loopback_listener_owned', return_value=owned), \
                    patch.object(browser.urllib.request, 'build_opener') as build:
                self.assertIsNone(browser.preauthorized_endpoint(state))
                build.assert_not_called()

    def test_invalid_endpoint_and_changed_websocket_fail_closed(self):
        state = {'pid': 123, 'start': 'browser', 'endpoint': HTTP, 'websocketPath': WS_PATH}
        for endpoint in [None, {}, 'http://localhost:45678', 'http://0.0.0.0:45678', HTTP + '/other',
                         HTTP + '?private=token', 'http://user:secret@127.0.0.1:45678', 'http://127.0.0.1:invalid']:
            with self.subTest(endpoint=endpoint), patch.object(browser.urllib.request, 'build_opener') as build:
                with self.assertRaises(ValueError):
                    browser.preauthorized_endpoint({**state, 'endpoint': endpoint})
                build.assert_not_called()
        for payload in [{'webSocketDebuggerUrl': WS.replace('45678', '45679')},
                        {'webSocketDebuggerUrl': WS + '?token=private'},
                        {'webSocketDebuggerUrl': WS.replace('a' * 36, 'b' * 36)}, {}, [], 'x' * 65537]:
            opener = Mock()
            body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
            opener.open.return_value = io.BytesIO(body)
            with self.subTest(payload_type=type(payload)), \
                    patch.object(browser, 'process_start', return_value='browser'), \
                    patch.object(browser, 'loopback_listener_owned', return_value=True), \
                    patch.object(browser.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaises(ValueError):
                    browser.preauthorized_endpoint(state)

    def test_manual_default_starts_debugging_but_not_an_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); profile = root / 'profile'
            process = Mock(pid=123); process.poll.return_value = None
            config = {'browser': {'userDataDir': str(profile), 'launchOptions': {'executablePath': 'vivaldi'}}}
            with patch.object(browser, 'profile_locked', side_effect=[False, True]), \
                    patch.object(browser, 'process_start', return_value='browser'), \
                    patch.object(browser, 'unused_loopback_port', return_value=45678), \
                    patch.object(browser, 'preauthorized_endpoint', return_value=WS), \
                    patch.object(browser, 'provision_bitwarden_host'), \
                    patch.object(browser, 'open_manual_tab') as handoff, \
                    patch.object(browser.subprocess, 'Popen', return_value=process) as spawn:
                actual, target = browser.start_headed(root, config, ['open', '--headed', '--manual', 'https://example.com'], {})
            self.assertIs(actual, process); self.assertIsNone(target)
            self.assertIn('--remote-debugging-address=127.0.0.1', spawn.call_args.args[0])
            self.assertIn('--remote-debugging-port=45678', spawn.call_args.args[0])
            spawn.assert_called_once(); handoff.assert_called_once()
            state = browser.read_state(root)
            self.assertTrue(state['manual']); self.assertTrue(state['preauthorized'])
            self.assertEqual(state['websocketPath'], WS_PATH)
            self.assertNotIn('runtime_daemon', state)
            self.assertNotIn('cdpEndpoint', config['browser'])

    def test_preauthorized_connect_has_no_permission_stage_or_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); profile = root / 'profile'; profile.mkdir()
            (profile / 'SingletonLock').symlink_to(os.uname().nodename + '-123')
            state = {'pid': 123, 'start': 'browser', 'manual': True, 'bound': True, 'preauthorized': True,
                     'profile': str(profile), 'url': 'https://example.com/?private=synthetic', 'endpoint': HTTP,
                     'websocketPath': WS_PATH}
            browser.write_json(root / 'config.json', {'browser': {'launchOptions': {'executablePath': 'vivaldi'}}})
            process = Mock(pid=456)
            output = io.StringIO()
            with patch.object(browser, 'managed_state', return_value=state), \
                    patch.object(browser, 'preauthorized_endpoint', return_value=WS), \
                    patch.object(browser, 'process_start', return_value='daemon'), \
                    patch.object(browser.subprocess, 'Popen', return_value=process) as spawn, \
                    patch.object(browser.subprocess, 'run') as external, patch('sys.stdout', output):
                self.assertEqual(browser.connect_manual('cli', root, {}, 'vivaldi'), 0)
                self.assertEqual(json.loads(output.getvalue()), {'status': 'connecting', 'connected': False})
                output.seek(0); output.truncate()
                self.assertEqual(browser.connect_manual('cli', root, {}, 'vivaldi'), 0)
                self.assertEqual(json.loads(output.getvalue()), {'status': 'connecting', 'connected': False})
                spawn.assert_called_once(); external.assert_not_called()
                self.assertEqual(spawn.call_args.kwargs['env']['PI_BROWSER_OWNED_DOWNLOADS'], '1')
                self.assertEqual(spawn.call_args.kwargs['env']['PI_BROWSER_METADATA_ONLY'], '1')
            with patch.object(browser, 'managed_state', return_value=state), \
                    patch.object(browser, 'preauthorized_endpoint', return_value=None), \
                    patch.object(browser.subprocess, 'run') as external, \
                    patch.object(browser.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'no consent mode fallback'):
                    browser.connect_manual('cli', root, {}, 'vivaldi')
                external.assert_not_called(); spawn.assert_not_called()

    def test_final_preauthorized_connection_activates_only_validated_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);profile=root/'profile';profile.mkdir()
            (profile/'SingletonLock').symlink_to(os.uname().nodename+'-123')
            state={'pid':123,'start':'browser','manual':True,'bound':True,'preauthorized':True,
                   'profile':str(profile),'url':'https://example.com/?token=synthetic-private',
                   'endpoint':HTTP,'websocketPath':WS_PATH,
                   'runtime_daemon':{'pid':456,'start':'daemon','endpoint':WS,'offset':0}}
            browser.write_json(root/'config.json',{'browser':{'launchOptions':{'executablePath':'vivaldi'}}})
            (root/'runtime-daemon.log').write_text('Daemon listening on private socket\n')
            for selected, second_endpoint, valid in [({'index':0,'targetId':'B'*32},WS,True),
                    ({'index':True,'targetId':'B'*32},WS,False),
                    ({'index':0,'targetId':'not-a-target'},WS,False),
                    ({'index':0,'targetId':'B'*32},None,False)]:
                opener=Mock();opener.open.return_value=io.BytesIO(b'activated')
                output=io.StringIO()
                current={**state}
                with self.subTest(selected=selected,endpoint=second_endpoint), \
                        patch.object(browser,'managed_state',return_value=current), \
                        patch.object(browser,'preauthorized_endpoint',side_effect=[WS,second_endpoint]), \
                        patch.object(browser,'process_start',return_value='daemon'), \
                        patch.object(browser,'private_cli_result',side_effect=[selected,None,{'origin':'https://example.com'}]) as command, \
                        patch.object(browser.urllib.request,'build_opener',return_value=opener) as build, \
                        patch.object(browser.subprocess,'Popen') as spawn,patch('sys.stdout',output):
                    if valid:
                        self.assertEqual(browser.connect_manual('cli',root,{},'vivaldi'),0)
                        opener.open.assert_called_once_with(HTTP+'/json/activate/'+'B'*32,timeout=5)
                        self.assertEqual(json.loads(output.getvalue()),{'connected':True,'origin':'https://example.com'})
                        self.assertNotIn('synthetic-private',output.getvalue())
                        self.assertEqual(command.call_args_list[1].args[-2:],('tab-select','0'))
                    else:
                        with self.assertRaises(ValueError):browser.connect_manual('cli',root,{},'vivaldi')
                        build.assert_not_called()
                        self.assertEqual(command.call_count,1)
                    spawn.assert_not_called()

    def test_failed_start_cleanup_does_not_probe_foreign_endpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); profile = root / 'profile'; profile.mkdir()
            state = {'pid': 123, 'start': 'browser', 'bound': True, 'preauthorized': True,
                     'profile': str(profile), 'endpoint': HTTP, 'temporary': False}
            with patch.object(browser, 'read_state', return_value=state), \
                    patch.object(browser, 'process_start', return_value='browser'), \
                    patch.object(Path, 'read_text', return_value='123 (fixture) Z 0'), \
                    patch.object(browser.urllib.request, 'build_opener') as build, \
                    patch.object(browser.os, 'kill') as kill:
                browser.stop_managed(root)
                build.assert_not_called()
                kill.assert_called_once_with(123, signal.SIGTERM)

    def test_native_consent_flag_requires_manual_mode(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'PI_SESSION_ID': 'native-consent-flag', 'XDG_STATE_HOME': temp}, clear=True), \
                patch.object(browser, 'runtime_root', return_value=Path(temp) / 'runtime' / 'test'), \
                patch.object(browser, 'start_headed') as start, \
                patch.object(browser.subprocess, 'run') as upstream:
            with self.assertRaisesRegex(ValueError, 'requires --headed --manual'):
                browser.run(['open', '--headed', '--native-consent'], cli='cli', browser_executable='vivaldi')
            start.assert_not_called(); upstream.assert_not_called()
