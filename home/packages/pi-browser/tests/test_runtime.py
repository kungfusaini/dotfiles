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

spec = importlib.util.spec_from_file_location('runtime_browser', Path(__file__).resolve().parents[1] / 'browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class RuntimeTests(unittest.TestCase):
    def test_native_consent_start_never_enables_debugger_or_starts_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process = Mock(pid=123)
            process.poll.return_value = None
            config = {'browser': {'userDataDir':str(root/'profile'), 'launchOptions':{'executablePath':'vivaldi'}}}
            with patch.object(browser,'profile_locked',side_effect=[False,True]), \
                    patch.object(browser,'process_start',return_value='start'), \
                    patch.object(browser,'provision_bitwarden_host'), \
                    patch.object(browser,'open_manual_tab') as handoff, \
                    patch.object(browser.subprocess,'Popen',return_value=process) as spawn:
                actual,target = browser.start_headed(root,config,['open','--headed','--manual','--native-consent','https://example.com'],{})
            self.assertIs(actual,process)
            self.assertIsNone(target)
            self.assertFalse(any(a.startswith(('--remote-debugging','--enable-automation','--no-sandbox')) for a in spawn.call_args.args[0]))
            self.assertEqual(handoff.call_args.args[3],'https://example.com')
            self.assertNotIn('cdpEndpoint',config['browser'])
            self.assertTrue(browser.read_state(root)['manual'])

    def test_marker_is_owned_regular_small_and_direct_websocket_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); marker=root/'DevToolsActivePort'
            self.assertIsNone(browser.runtime_endpoint(root))
            marker.write_text('9222\n/devtools/browser/'+'a'*36+'\n')
            self.assertEqual(browser.runtime_endpoint(root),'ws://127.0.0.1:9222/devtools/browser/'+'a'*36)
            for value in ('0\n/devtools/browser/'+'a'*36, '9222\nhttps://other.example/', '9222\n/devtools/browser/secret?token=private', 'x'*300):
                marker.write_text(value)
                with self.assertRaises(ValueError):browser.runtime_endpoint(root)
            marker.unlink(); marker.symlink_to(root/'outside')
            with self.assertRaises(OSError):browser.runtime_endpoint(root)

    def test_private_results_never_forward_auth_urls_or_stderr(self):
        secret='synthetic-private-token'
        for bad in (False,True):
            payload={'result':{'origin':'https://example.com'},'code':secret,'page':{'url':'https://example.com/?token='+secret}}
            if bad:payload={'isError':True,'error':secret}
            out,err=io.StringIO(),io.StringIO()
            with patch.object(browser.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),secret)), \
                    patch('sys.stdout',out),patch('sys.stderr',err):
                if bad:
                    with self.assertRaisesRegex(ValueError,'private output was suppressed') as caught:
                        browser.private_cli_result('cli',Path('/fixture'),{},'run-code','async()=>{}')
                    self.assertNotIn(secret,str(caught.exception))
                else:
                    self.assertEqual(browser.private_cli_result('cli',Path('/fixture'),{},'run-code','async()=>{}'),{'origin':'https://example.com'})
            self.assertEqual(out.getvalue()+err.getvalue(),'')

    def test_final_connection_keeps_browser_pid_profile_and_existing_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); profile=root/'profile'; profile.mkdir()
            (profile/'SingletonLock').symlink_to(os.uname().nodename+'-123')
            endpoint='ws://127.0.0.1:9222/devtools/browser/'+'a'*36
            state={'pid':123,'start':'browser','manual':True,'bound':True,'temporary':False,
                   'profile':str(profile),'url':'https://example.com/?private=synthetic',
                   'runtime_daemon':{'pid':456,'start':'daemon','endpoint':endpoint,'offset':0}}
            config={'browser':{'launchOptions':{'executablePath':'vivaldi'}}}
            browser.write_json(root/'config.json',config)
            (root/'runtime-daemon.log').write_text('Daemon listening on private socket\n')
            output=io.StringIO()
            with patch.object(browser,'managed_state',return_value=state), \
                    patch.object(browser,'runtime_endpoint',return_value=endpoint), \
                    patch.object(browser,'process_start',return_value='daemon'), \
                    patch.object(browser,'private_cli_result',side_effect=[0,None,{'origin':'https://example.com'}]) as command, \
                    patch.object(browser,'stop_managed') as stop, \
                    patch.object(browser.subprocess,'Popen') as spawn,patch('sys.stdout',output):
                self.assertEqual(browser.connect_manual('cli',root,{},'vivaldi'),0)
                stop.assert_not_called(); spawn.assert_not_called()
            self.assertEqual(json.loads(output.getvalue()),{'connected':True,'origin':'https://example.com'})
            self.assertNotIn('synthetic',output.getvalue())
            current=browser.read_state(root)
            self.assertEqual(current['pid'],123)
            self.assertEqual(current['profile'],str(profile))
            self.assertFalse(current['manual'])
            self.assertEqual(command.call_args_list[1].args[-2:],('tab-select','0'))

    def test_repeated_connect_reuses_only_owned_approved_daemon_without_page_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); profile=root/'profile'; profile.mkdir()
            (profile/'SingletonLock').symlink_to(os.uname().nodename+'-123')
            endpoint='ws://127.0.0.1:9222/devtools/browser/'+'a'*36
            state={'pid':123,'start':'browser','manual':False,'runtime':True,'bound':True,
                   'profile':str(profile),'url':'https://example.com/?token=synthetic-private',
                   'runtime_daemon':{'pid':456,'start':'daemon','endpoint':endpoint}}
            browser.write_json(root/'vivaldi-process.json',state)
            before=(root/'vivaldi-process.json').read_bytes()
            output=io.StringIO()
            with patch.object(browser,'managed_state',return_value=state), \
                    patch.object(browser,'runtime_endpoint',return_value=endpoint), \
                    patch.object(browser,'process_start',return_value='daemon'), \
                    patch.object(browser,'private_cli_result') as command, \
                    patch.object(browser.subprocess,'Popen') as spawn, \
                    patch.object(browser.subprocess,'run') as run, \
                    patch.object(browser,'stop_managed') as stop,patch('sys.stdout',output):
                for _ in range(2):
                    self.assertEqual(browser.connect_manual('cli',root,{},'vivaldi'),0)
                command.assert_not_called();spawn.assert_not_called();run.assert_not_called();stop.assert_not_called()
            self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()],
                             [{'connected':True,'reused':True}]*2)
            self.assertNotIn('synthetic-private',output.getvalue())
            self.assertEqual((root/'vivaldi-process.json').read_bytes(),before)
            self.assertFalse((root/'config.json').exists())  # No mutable config dependency.

    def test_reuse_fails_closed_for_missing_changed_or_foreign_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); profile=root/'profile'; profile.mkdir()
            lock=profile/'SingletonLock';lock.symlink_to(os.uname().nodename+'-123')
            endpoint='ws://127.0.0.1:9222/devtools/browser/'+'a'*36
            base={'pid':123,'start':'browser','manual':False,'runtime':True,'bound':True,'profile':str(profile),
                  'runtime_daemon':{'pid':456,'start':'daemon','endpoint':endpoint}}
            cases=[({'runtime_daemon':None},endpoint,'daemon'),
                   ({'runtime_daemon':['invalid']},endpoint,'daemon'),
                   ({'runtime_daemon':{'pid':123,'start':'daemon','endpoint':endpoint}},endpoint,'daemon'),
                   ({'runtime_daemon':{'pid':456,'start':'daemon'}},endpoint,'daemon'),
                   ({'runtime_daemon':{'pid':456,'endpoint':endpoint}},endpoint,'daemon'),
                   ({'runtime_daemon':{'pid':True,'start':'daemon','endpoint':endpoint}},endpoint,'daemon'),
                   ({},None,'daemon'),({},endpoint+'changed','daemon'),({},endpoint,None),({},endpoint,'reused-pid'),
                   ({'bound':False},endpoint,'daemon'),({'runtime':False},endpoint,'daemon')]
            for changes,marker,start in cases:
                with self.subTest(changes=changes,marker=marker,start=start), \
                        patch.object(browser,'managed_state',return_value={**base,**changes}), \
                        patch.object(browser,'runtime_endpoint',return_value=marker), \
                        patch.object(browser,'process_start',return_value=start), \
                        patch.object(browser,'private_cli_result') as command, \
                        patch.object(browser.subprocess,'Popen') as spawn:
                    with self.assertRaises(ValueError):browser.connect_manual('cli',root,{},'vivaldi')
                    command.assert_not_called();spawn.assert_not_called()
            for owner in (os.uname().nodename+'-999','foreign-host-123'):
                lock.unlink();lock.symlink_to(owner)
                with patch.object(browser,'managed_state',return_value=base), \
                        patch.object(browser.subprocess,'Popen') as spawn:
                    with self.assertRaisesRegex(ValueError,'profile is not owned'):
                        browser.connect_manual('cli',root,{},'vivaldi')
                    spawn.assert_not_called()

    def test_open_refuses_to_restart_owned_manual_or_connected_browser(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'PI_SESSION_ID':'open-guard','XDG_STATE_HOME':temp},clear=True), \
                patch.object(browser,'runtime_root',return_value=Path(temp)/'runtime'/'test'):
            root=browser.session_root(os.environ)
            config=root/'config.json';config.write_text('{"keep":"original"}')
            for manual in (True,False):
                state={'pid':123,'start':'browser','manual':manual,'runtime':not manual,'bound':True}
                browser.write_json(root/'vivaldi-process.json',state)
                before=(root/'vivaldi-process.json').read_bytes()
                with patch.object(browser,'managed_state',return_value=state), \
                        patch.object(browser,'stop_managed') as stop, \
                        patch.object(browser,'start_headed') as start, \
                        patch.object(browser.subprocess,'run') as upstream:
                    for args in (['open'],['open','--headed'],['open','--headed','--manual','https://example.com']):
                        with self.subTest(manual=manual,args=args),self.assertRaisesRegex(ValueError,'already open'):
                            browser.run(args,cli='cli',browser_executable='vivaldi')
                    stop.assert_not_called();start.assert_not_called();upstream.assert_not_called()
                self.assertEqual(config.read_text(),'{"keep":"original"}')
                self.assertEqual((root/'vivaldi-process.json').read_bytes(),before)
            with patch.object(browser,'managed_state',return_value={'manual':True}), \
                    patch.object(browser.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as upstream, \
                    patch.object(browser,'stop_managed') as stop:
                self.assertEqual(browser.run(['open','--headed','--help'],cli='cli',browser_executable='vivaldi'),0)
                upstream.assert_called_once();stop.assert_not_called()

    def test_pending_connection_preserves_manual_browser_and_has_no_auto_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); profile=root/'profile'; profile.mkdir()
            (profile/'SingletonLock').symlink_to(os.uname().nodename+'-123')
            endpoint='ws://127.0.0.1:9222/devtools/browser/'+'a'*36
            state={'pid':123,'start':'browser','manual':True,'bound':True,'temporary':False,
                   'profile':str(profile),'url':'https://example.com',
                   'runtime_daemon':{'pid':456,'start':'daemon','endpoint':endpoint,'offset':0}}
            browser.write_json(root/'config.json',{'browser':{'launchOptions':{'executablePath':'vivaldi'}}})
            with patch.object(browser,'managed_state',return_value=state), \
                    patch.object(browser,'runtime_endpoint',return_value=endpoint), \
                    patch.object(browser,'process_start',return_value=None), \
                    patch.object(browser.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'declined'):
                    browser.connect_manual('cli',root,{},'vivaldi')
                spawn.assert_not_called()
            self.assertTrue(profile.exists())
            self.assertTrue(browser.read_state(root)['manual'])
            self.assertNotIn('runtime_daemon',browser.read_state(root))

    def test_manual_detach_is_independent_of_stale_upstream_session(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'PI_SESSION_ID':'detach','XDG_STATE_HOME':temp},clear=True), \
                patch.object(browser,'runtime_root',return_value=Path(temp)/'runtime'/'test'):
            root=browser.session_root(os.environ);profile=root/'profile';profile.mkdir()
            state={'pid':123,'start':'browser','manual':True,'bound':True,'temporary':False,
                   'profile':str(profile),'runtime_daemon':{'pid':456,'start':'daemon'}}
            browser.write_json(root/'vivaldi-process.json',state)
            with patch.object(browser,'managed_state',return_value=state), \
                    patch.object(browser,'stop_runtime_daemon') as stop, \
                    patch.object(browser.subprocess,'run',return_value=subprocess.CompletedProcess([],1)) as upstream:
                self.assertEqual(browser.run(['detach'],cli='cli',browser_executable='vivaldi'),0)
                upstream.assert_not_called();stop.assert_called_once()
                self.assertFalse(browser.read_state(root)['bound'])
                with self.assertRaisesRegex(ValueError,'No owned'):
                    browser.connect_manual('cli',root,{},'vivaldi')
            with patch.object(browser.subprocess,'run',return_value=subprocess.CompletedProcess([],0)), \
                    patch.object(browser.os,'kill') as kill:
                self.assertEqual(browser.run(['close'],cli='cli',browser_executable='vivaldi'),0)
                kill.assert_not_called()
            self.assertTrue(profile.exists())

    def test_only_exact_owned_daemon_can_be_terminated(self):
        state={'pid':123,'runtime_daemon':{'pid':456,'start':'owned'}}
        with patch.object(browser,'process_start',return_value='other'),patch.object(browser.os,'kill') as kill:
            browser.stop_runtime_daemon(state);kill.assert_not_called()
        with patch.object(browser,'process_start',return_value='owned'),patch.object(browser.os,'kill') as kill:
            browser.stop_runtime_daemon(state);kill.assert_called_once_with(456,signal.SIGTERM)
        state['runtime_daemon']['pid']=123
        with patch.object(browser,'process_start',return_value='owned'),patch.object(browser.os,'kill') as kill:
            browser.stop_runtime_daemon(state);kill.assert_not_called()

    def test_wrapper_flag_and_manual_guard_preserve_literal_data_and_config(self):
        self.assertEqual(browser.without_manual_option(['open','--manual','false','--native-consent','--','--manual']),['open','--','--manual'])
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'PI_SESSION_ID':'manual','XDG_STATE_HOME':temp},clear=True), \
                patch.object(browser,'runtime_root',return_value=Path(temp)/'runtime'/'test'), \
                patch.object(browser,'managed_state',return_value={'manual':True}):
            root=browser.session_root(os.environ);config=root/'config.json';config.write_text('{"keep":"manual"}')
            for command in (['snapshot'],['run-code','async()=>{}'],['state-save','auth.json']):
                with self.assertRaisesRegex(ValueError,'no agent connection'):
                    browser.run(command,cli='cli',browser_executable='vivaldi')
            self.assertEqual(config.read_text(),'{"keep":"manual"}')
