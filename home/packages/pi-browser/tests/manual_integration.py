#!/usr/bin/env python3
"""Preauthorized/manual and opt-in native-consent tests on a private desktop.

Default connections and reconnects require no permission input. --wtype is used
only for opt-in synthetic native-consent or manual-popup controls; production
never writes the native consent preference or clicks a permission dialog.
"""
import http.server
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, str(Path(__file__).parent))
import headed_integration as headed

PAGE = b'''<!doctype html><title>Human-first fixture</title><p id="status">Signed in</p>
<button id="continue" onclick="document.querySelector('#status').textContent='Agent continued'">Continue</button>
<button id="popup" autofocus onclick="const w=window.open('','fixture-popup','width=500,height=400');
w.document.write('<title>Popup fixture</title><img src=/pixel><p>Confirmation fixture</p>');w.document.close()">Popup</button>
<script>const previous=localStorage.getItem('login');
fetch('/phase?webdriver='+navigator.webdriver+'&previous='+encodeURIComponent(previous||''));
localStorage.setItem('login','synthetic-user');</script>'''

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/pixel':
            self.server.pixels += 1
            self.send_response(200);self.send_header('Content-Type','image/gif');self.end_headers()
            self.wfile.write(bytes.fromhex('47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b'));return
        if self.path.startswith('/phase?'):
            self.server.phases.append(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query,keep_blank_values=True))
            self.send_response(204);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(PAGE)
    def log_message(self,*_args):
        pass


def worker(arguments):
    root,helper,browser,strip=arguments;root=Path(root)
    headed.wait_for_file(root/'go')
    shared_runtime=os.environ.get('PI_BROWSER_TEST_SHARED_RUNTIME')=='1'
    port_file=root.parent/'runtime-fixture-port'
    port=int(port_file.read_text()) if shared_runtime and port_file.exists() else 0
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler);server.phases=[];server.pixels=0
    if shared_runtime:port_file.write_text(str(server.server_port))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    env={**os.environ,'PI_SESSION_ID':f'runtime-{root.parent.name}-{strip}',
         'XDG_STATE_HOME':str(root/'state'),'NIXOS_OZONE_WL':'1'}
    if os.environ.get('PI_BROWSER_TEST_TRACE') == '1':
        env['DEBUG'] = 'pw:protocol'  # Synthetic fixtures only; never real profiles.
    profile=(root.parent/'runtime-shared-profile') if shared_runtime else root/'synthetic-profile'
    profile.mkdir(exist_ok=shared_runtime)
    # Test fixture ONLY. Actual users enable the setting in Vivaldi themselves.
    settings_only=os.environ.get('PI_BROWSER_TEST_SETTINGS_ONLY')=='1'
    native_consent=(os.environ.get('PI_BROWSER_TEST_NATIVE_CONSENT')=='1' or settings_only
                    or os.environ.get('PI_BROWSER_TEST_DENY_FIRST')=='1')
    assert not (shared_runtime and native_consent),'shared-runtime control is preauthorized only'
    if native_consent and not settings_only:
        (profile/'Local State').write_text(json.dumps({'devtools':{'remote_debugging':{'user-enabled':True}}}))
    state=None
    classic_ui=False
    def fixture_alive():
        try:
            value=Path('/proc',str(state['pid']),'stat').read_text()
            return value[value.rfind(')')+2:].split()[19]==state['start']
        except (OSError,TypeError,KeyError,IndexError):
            return False
    def call(*args,success=True,error=None):
        result=subprocess.run([browser,*args],env=env,capture_output=True,text=True,timeout=25)
        if args[0]=='connect':assert 'synthetic-marker' not in result.stdout+result.stderr
        if success and (result.returncode!=0 or '### Error' in result.stdout) and os.environ.get('PI_BROWSER_TEST_CAPTURE_FAILURE')=='1':
            assert Path(env['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
            subprocess.run(['grim','-o','TEST',str(root/'failure.png')],env=env,check=True)
        if success:assert result.returncode==0 and '### Error' not in result.stdout,result.stderr+result.stdout
        else:assert result.returncode!=0,result.stdout
        if error:assert error in result.stderr,result.stderr
        return result.stdout
    def ctl(*args):
        # Absolute isolation assertion before every synthetic human input step.
        assert Path(env['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
        return subprocess.check_output(['hyprctl',*args],env=env,text=True).strip()
    def consent(allow):
        assert native_consent,'preauthorized connections must not require permission input'
        time.sleep(2)  # Native permission dialog; no page CDP exists yet.
        windows=json.loads(ctl('clients','-j'))
        window=next(c for c in windows if c.get('pid')==state['pid'])
        native_class=window['class']
        ctl('dispatch','event','pi-consent-begin:'+native_class)
        try:
            ctl('dispatch','focuswindow','address:'+window['address'])
            deadline=time.monotonic()+3
            while json.loads(ctl('activewindow','-j')).get('address') != window['address']:
                assert time.monotonic()<deadline,'private consent window did not receive focus'
                time.sleep(.05)
            # Chromium-interface dialog initially focuses Cancel; native
            # Vivaldi's dialog enters the focus order one step earlier.
            tabs=(1 if allow else 0) if classic_ui else (2 if allow else 1)
            keys=['-s','200']+['-k','Tab']*tabs+['-s','200','-k','Return']
            subprocess.run([os.environ['PI_BROWSER_TEST_WTYPE'],*keys],env=env,
                           capture_output=True,timeout=5,check=True)
        finally:
            ctl('dispatch','focusmonitor','TEST_FOCUS')
            ctl('dispatch','workspace','name:Focused elsewhere')
            ctl('dispatch','event','pi-consent-end:'+native_class)
    try:
        if os.environ.get('PI_BROWSER_TEST_DETACH_STAGE'):
            # Establish the stale upstream non-attached entry from the review.
            call('open','--persistent',f'http://127.0.0.1:{server.server_port}/')
            call('close')
            server.phases=[]
        command=[browser,'open','--headed','--manual','--profile='+str(profile),
                 f'http://127.0.0.1:{server.server_port}/?private=synthetic-marker']
        if native_consent:
            command.append('--native-consent')
        if os.environ.get('PI_BROWSER_TEST_NATIVE_UI') == '1':
            call('open','--headed','--help')
            private_session=Path(json.loads(call('paths'))['session'])
            config=json.loads((private_session/'config.json').read_text())
            config['browser']['launchOptions']['args']=[]
            config_path=root/'native-ui-config.json'
            config_path.write_text(json.dumps(config))
            command.append('--config='+str(config_path))
        direct = os.environ.get('PI_BROWSER_TEST_DIRECT') == '1'
        if direct:
            assert not native_consent,'direct control cannot request native manual consent'
            command.remove('--manual')
        launcher='import os,subprocess,time;'
        if strip=='yes':launcher+="os.environ.pop('HL_EXEC_RULE_TOKEN',None);os.environ.pop('HL_INITIAL_WORKSPACE_TOKEN',None);time.sleep(1.2);"
        launcher+='subprocess.run('+repr(command)+')'
        launched=subprocess.run([helper,sys.executable,'-c',launcher],env=env,capture_output=True,text=True,timeout=25)
        assert launched.returncode==0,launched.stderr
        if direct:
            session=Path(json.loads(call('paths'))['session'])
            state=json.loads((session/'vivaldi-process.json').read_text())
            call('run-code', '''async page => {
const popupPromise=page.waitForEvent('popup'); await page.locator('#popup').click();
const popup=await popupPromise; await popup.waitForFunction(()=>document.querySelector('img')?.naturalWidth>0,null,{timeout:5000});
await popup.close(); return {popup:true};}''')
            assert server.pixels == 1
            (root/'result.json').write_text(json.dumps({'status':0,'stdout':'direct native popup passed','stderr':''}))
            headed.wait_for_file(root/'done')
            return
        listing=json.loads(call('list'))
        assert listing['connected'] is False
        assert listing['debugging']==('native-consent' if native_consent else 'preauthorized')
        session=Path(json.loads(call('paths'))['session'])
        state=json.loads((session/'vivaldi-process.json').read_text())
        assert state['manual'] and state['preauthorized'] is (not native_consent)
        assert 'runtime_daemon' not in state
        if native_consent:
            assert 'endpoint' not in state
        else:
            assert urllib.parse.urlsplit(state['endpoint']).hostname=='127.0.0.1'
        flags=[x.decode() for x in (Path('/proc')/str(state['pid'])/'cmdline').read_bytes().split(b'\0') if x]
        if len(flags)==1:
            flags=shlex.split(flags[0])  # Vivaldi can replace argv with one display string.
        classic_ui='--disable-vivaldi' in flags
        assert classic_ui is (os.environ.get('PI_BROWSER_TEST_NATIVE_UI') != '1')
        if classic_ui:
            assert '--force-dark-mode' in flags
        assert not any(f.startswith(('--enable-automation','--headless','--no-sandbox')) for f in flags)
        if native_consent:
            assert not any(f.startswith('--remote-debugging') for f in flags)
        else:
            assert '--remote-debugging-address=127.0.0.1' in flags
            assert '--remote-debugging-port='+str(urllib.parse.urlsplit(state['endpoint']).port) in flags
            assert urllib.parse.urlsplit(state['endpoint']).port>0
        call('snapshot',success=False)
        deadline=time.monotonic()+10
        while not server.phases:
            assert time.monotonic()<deadline,'normal manual page did not load';time.sleep(.1)
        previous='synthetic-user' if shared_runtime and strip=='yes' else ''
        assert server.phases[0]=={'webdriver':['false'],'previous':[previous]},server.phases
        before_open=(session/'vivaldi-process.json').read_bytes()
        call('open','--headed','--manual',f'http://127.0.0.1:{server.server_port}/other',
             success=False,error='already open')
        assert (session/'vivaldi-process.json').read_bytes()==before_open
        assert fixture_alive(),'repeated open stopped the manual browser'
        if os.environ.get('PI_BROWSER_TEST_MANUAL_POPUP') == '1':
            own=next(c for c in json.loads(ctl('clients','-j')) if c.get('pid')==state['pid'])
            native_class=own['class']
            ctl('dispatch','event','pi-consent-begin:'+native_class)
            try:
                ctl('dispatch','focuswindow','address:'+own['address'])
                subprocess.run([os.environ['PI_BROWSER_TEST_WTYPE'],'-M','ctrl','-k','l','-m','ctrl',
                                "javascript:document.getElementById('popup').click()",'-k','Return'],
                               env=env,check=True,timeout=5)
            finally:
                ctl('dispatch','focusmonitor','TEST_FOCUS')
                ctl('dispatch','workspace','name:Focused elsewhere')
                ctl('dispatch','event','pi-consent-end:'+native_class)
            deadline=time.monotonic()+10
            while server.pixels != 1:
                assert time.monotonic()<deadline,'manual popup did not load'
                time.sleep(.1)
            deadline=time.monotonic()+10
            while True:
                popup=next((c for c in json.loads(ctl('clients','-j')) if c.get('class')==native_class and c['address']!=own['address']),None)
                if popup:break
                assert time.monotonic()<deadline,'manual popup window did not map'
                time.sleep(.1)
            ctl('dispatch','closewindow','address:'+popup['address'])
            (root/'result.json').write_text(json.dumps({'status':0,'stdout':'manual native popup passed without agent connection','stderr':''}))
            headed.wait_for_file(root/'done')
            return
        if settings_only:
            assert not (profile/'DevToolsActivePort').exists()
            assert json.loads(call('connect'))['status']=='enable-debugging'
            deadline=time.monotonic()+10
            while True:
                windows=json.loads(ctl('clients','-j'))
                own=next(c for c in windows if c.get('pid')==state['pid'])
                if 'Inspect' in own.get('title',''):break
                assert time.monotonic()<deadline,'native debugging settings did not open'
                time.sleep(.1)
            assert 'runtime_daemon' not in json.loads((session/'vivaldi-process.json').read_text())
            (root/'result.json').write_text(json.dumps({'status':0,'stdout':'native settings open without agent control','stderr':''}))
            headed.wait_for_file(root/'done')
            return
        if native_consent:
            while not (profile/'DevToolsActivePort').exists():
                assert time.monotonic()<deadline,'on-demand runtime server did not start';time.sleep(.1)
        assert json.loads(call('connect'))['status']==('approve-connection' if native_consent else 'connecting')
        call('snapshot',success=False)
        detach_stage=os.environ.get('PI_BROWSER_TEST_DETACH_STAGE')
        if detach_stage:
            if detach_stage=='approved':
                if native_consent:consent(True)
                deadline=time.monotonic()+10
                while b'Daemon listening on' not in (session/'runtime-daemon.log').read_bytes():
                    assert time.monotonic()<deadline,'daemon did not become ready';time.sleep(.1)
            assert json.loads(call('detach'))['status']=='detached'
            call('connect',success=False)
            call('close')
            assert fixture_alive(),'detach/close killed the handed-back browser'
            assert profile.exists()
            (root/'result.json').write_text(json.dumps({'status':0,'stdout':'manual/pending detach preserves live browser','stderr':''}))
            headed.wait_for_file(root/'done')
            return
        if os.environ.get('PI_BROWSER_TEST_DENY_FIRST')=='1':
            consent(False);time.sleep(.5)
            call('connect',success=False)
            assert profile.exists() and json.loads((session/'vivaldi-process.json').read_text())['pid']==state['pid']
            assert json.loads(call('connect'))['status']=='approve-connection'
        if native_consent:consent(True)
        deadline=time.monotonic()+10
        while True:
            output=json.loads(call('connect'))
            if output.get('connected'):break
            assert output['status']==('awaiting-approval' if native_consent else 'connecting') and time.monotonic()<deadline,output
            time.sleep(.1)
        assert output=={'connected':True,'origin':f'http://127.0.0.1:{server.server_port}'},output
        connected=json.loads((session/'vivaldi-process.json').read_text())
        assert connected['pid']==state['pid'] and connected['profile']==state['profile']
        assert not connected['manual'] and connected['runtime']
        assert 'synthetic-user' in call('localstorage-get','login')
        call('click','#continue')
        assert 'Agent continued' in call('eval',"document.querySelector('#status').textContent")
        assert 'false' in call('eval','navigator.webdriver')  # Unmodified native runtime behavior, not a JS override.
        assert not list((session/'artifacts').glob('page-*.yml')),'automatic page snapshot during consent'
        call('snapshot')  # Explicit authorized fixture snapshots remain supported.
        before_reuse=(session/'vivaldi-process.json').read_bytes()
        for _ in range(2):
            assert json.loads(call('connect'))=={'connected':True,'reused':True}
        call('open','--headed',f'http://127.0.0.1:{server.server_port}/other',
             success=False,error='already open')
        assert (session/'vivaldi-process.json').read_bytes()==before_reuse
        assert fixture_alive(),'reuse changed browser identity'
        assert 'Agent continued' in call('eval',"document.querySelector('#status').textContent")
        if os.environ.get('PI_BROWSER_TEST_POPUP') == '1':
            call('run-code', '''async page => {
const popupPromise=page.waitForEvent('popup'); await page.locator('#popup').click();
const popup=await popupPromise; await popup.waitForFunction(()=>document.querySelector('img')?.naturalWidth>0,null,{timeout:5000});
await popup.close(); return {popup:true};}''')
            assert server.pixels == 1, 'popup image request stalled'
            call('goto', f'http://127.0.0.1:{server.server_port}/ordinary')
            call('click', '#continue')
            assert 'Agent continued' in call('eval', "document.querySelector('#status').textContent")
        if os.environ.get('PI_BROWSER_TEST_RECONNECT') == '1':
            endpoint=connected['runtime_daemon']['endpoint']
            call('detach')
            with (root/'reconnect.log').open('w') as log:
                reconnect=subprocess.Popen([browser,'attach','--cdp='+endpoint],env=env,stdout=log,stderr=log)
                try:
                    if native_consent:
                        time.sleep(2)
                        assert reconnect.poll() is None,'reattach completed before renewed native approval'
                        # Public control must remain unavailable in opt-in
                        # native-consent mode until synthetic human approval.
                        with (root/'before-reapproval.log').open('w') as probe_log:
                            probe=subprocess.Popen([browser,'tab-list'],env=env,stdout=probe_log,stderr=probe_log)
                            try:
                                try:
                                    code=probe.wait(timeout=1)
                                    assert code!=0,'page control was available before renewed approval'
                                except subprocess.TimeoutExpired:
                                    pass
                            finally:
                                if probe.poll() is None:
                                    probe.terminate()
                                    probe.wait(timeout=5)
                        consent(True)
                    assert reconnect.wait(timeout=25)==0,'native reconnect failed; see private reconnect.log'
                finally:
                    if reconnect.poll() is None:
                        reconnect.terminate()
                        reconnect.wait(timeout=5)
            resumed=call('run-code', '''async page => {
const task=page.context().pages().find(p=>p.url().endsWith('/ordinary'));
if(!task)throw Error('Missing fixture after reconnect');
await task.locator('#continue').click();
return {login:await task.evaluate(()=>localStorage.getItem('login')),status:await task.locator('#status').textContent()};}''')
            assert 'synthetic-user' in resumed and 'Agent continued' in resumed
            assert fixture_alive(),'reconnect changed browser identity'
        mode='native runtime consent' if native_consent else 'preauthorized loopback (no permission input)'
        (root/'result.json').write_text(json.dumps({'status':0,'stdout':'same-process '+mode+' passed','stderr':''}))
        headed.wait_for_file(root/'done')
    except Exception as error:
        (root/'result.json').write_text(json.dumps({'status':1,'stdout':'','stderr':str(error)}));raise
    finally:
        call('close')
        if state:
            assert profile.exists()  # Explicit fixture profile, never implicitly deleted.
            if (os.environ.get('PI_BROWSER_TEST_DETACH_STAGE') or os.environ.get('PI_BROWSER_TEST_RECONNECT')) and fixture_alive():
                # Test controller still owns this isolated synthetic fixture,
                # even though the browser wrapper deliberately relinquished it.
                assert Path(env['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
                os.kill(state['pid'],15)
                deadline=time.monotonic()+10
                while fixture_alive():
                    assert time.monotonic()<deadline,'private detached browser did not exit'
                    time.sleep(.05)
        server.shutdown();server.server_close()


def main():
    if sys.argv[1:2]==['--worker']:worker(sys.argv[2:]);return
    if '--wtype' in sys.argv:
        index=sys.argv.index('--wtype');os.environ['PI_BROWSER_TEST_WTYPE']=sys.argv[index+1];del sys.argv[index:index+2]
    needs_input=any(os.environ.get(name)=='1' for name in ('PI_BROWSER_TEST_NATIVE_CONSENT','PI_BROWSER_TEST_DENY_FIRST','PI_BROWSER_TEST_MANUAL_POPUP'))
    if needs_input and not os.environ.get('PI_BROWSER_TEST_WTYPE'):raise SystemExit('--wtype is required for isolated test-human input')
    if needs_input and '--simulate-human-consent' not in sys.argv:sys.argv.append('--simulate-human-consent')
    headed.__file__=__file__;headed.main()

if __name__=='__main__':
    if '--harness' not in sys.argv and sys.argv[1:2]!=['--worker'] and os.environ.get('PI_BROWSER_TEST_HARNESS'):
        sys.argv+=['--harness',os.environ['PI_BROWSER_TEST_HARNESS']]
    main()
