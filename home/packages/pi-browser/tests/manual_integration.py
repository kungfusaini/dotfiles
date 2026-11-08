#!/usr/bin/env python3
"""Runtime-consent handoff in a hidden desktop. No real accounts or host input.

--wtype is used ONLY for bounded test-human native permission input on the
private compositor. A synthetic Local State seed models enabling the checkbox;
production never writes that preference or approves its own connection.
"""
import http.server
import json
import os
from pathlib import Path
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
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);server.phases=[];server.pixels=0
    threading.Thread(target=server.serve_forever,daemon=True).start()
    env={**os.environ,'PI_SESSION_ID':f'runtime-{root.parent.name}-{strip}',
         'XDG_STATE_HOME':str(root/'state'),'NIXOS_OZONE_WL':'1'}
    if os.environ.get('PI_BROWSER_TEST_TRACE') == '1':
        env['DEBUG'] = 'pw:protocol'  # Synthetic fixtures only; never real profiles.
    profile=root/'synthetic-profile';profile.mkdir()
    # Test fixture ONLY. Actual users enable the setting in Vivaldi themselves.
    settings_only=os.environ.get('PI_BROWSER_TEST_SETTINGS_ONLY')=='1'
    if not settings_only:
        (profile/'Local State').write_text(json.dumps({'devtools':{'remote_debugging':{'user-enabled':True}}}))
    state=None
    def fixture_alive():
        try:
            value=Path('/proc',str(state['pid']),'stat').read_text()
            return value[value.rfind(')')+2:].split()[19]==state['start']
        except (OSError,TypeError,KeyError,IndexError):
            return False
    def call(*args,success=True):
        result=subprocess.run([browser,*args],env=env,capture_output=True,text=True,timeout=25)
        if args[0]=='connect':assert 'synthetic-marker' not in result.stdout+result.stderr
        if success:assert result.returncode==0 and '### Error' not in result.stdout,result.stderr+result.stdout
        else:assert result.returncode!=0,result.stdout
        return result.stdout
    def ctl(*args):
        # Absolute isolation assertion before every synthetic human input step.
        assert Path(env['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
        return subprocess.check_output(['hyprctl',*args],env=env,text=True).strip()
    def consent(allow):
        time.sleep(2)  # Native permission dialog; no page CDP exists yet.
        windows=json.loads(ctl('clients','-j'))
        window=next(c for c in windows if c.get('pid')==state['pid'])
        native_class=window['class']
        ctl('dispatch','event','pi-consent-begin:'+native_class)
        try:
            ctl('dispatch','focuswindow','address:'+window['address'])
            keys=['-k','Tab']*(2 if allow else 1)+['-s','200','-k','Return']
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
        direct = os.environ.get('PI_BROWSER_TEST_DIRECT') == '1'
        if direct:
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
        assert json.loads(call('list'))['connected'] is False
        session=Path(json.loads(call('paths'))['session'])
        state=json.loads((session/'vivaldi-process.json').read_text())
        assert state['manual'] and 'endpoint' not in state
        flags=(Path('/proc')/str(state['pid'])/'cmdline').read_bytes().split(b'\0')
        assert not any(f.startswith((b'--remote-debugging',b'--enable-automation',b'--headless',b'--no-sandbox')) for f in flags)
        call('snapshot',success=False)
        deadline=time.monotonic()+10
        while not server.phases:
            assert time.monotonic()<deadline,'normal manual page did not load';time.sleep(.1)
        assert server.phases[0]=={'webdriver':['false'],'previous':['']},server.phases
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
        while not (profile/'DevToolsActivePort').exists():
            assert time.monotonic()<deadline,'on-demand runtime server did not start';time.sleep(.1)
        assert json.loads(call('connect'))['status']=='approve-connection'
        call('snapshot',success=False)
        detach_stage=os.environ.get('PI_BROWSER_TEST_DETACH_STAGE')
        if detach_stage:
            if detach_stage=='approved':
                consent(True)
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
        consent(True)
        deadline=time.monotonic()+10
        while True:
            output=json.loads(call('connect'))
            if output.get('connected'):break
            assert output['status']=='awaiting-approval' and time.monotonic()<deadline,output
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
        call('connect',success=False)
        if os.environ.get('PI_BROWSER_TEST_POPUP') == '1':
            call('run-code', '''async page => {
const popupPromise=page.waitForEvent('popup'); await page.locator('#popup').click();
const popup=await popupPromise; await popup.waitForFunction(()=>document.querySelector('img')?.naturalWidth>0,null,{timeout:5000});
await popup.close(); return {popup:true};}''')
            assert server.pixels == 1, 'popup image request stalled'
            call('goto', f'http://127.0.0.1:{server.server_port}/ordinary')
            call('click', '#continue')
            assert 'Agent continued' in call('eval', "document.querySelector('#status').textContent")
        (root/'result.json').write_text(json.dumps({'status':0,'stdout':'same-process native runtime consent passed','stderr':''}))
        headed.wait_for_file(root/'done')
    except Exception as error:
        (root/'result.json').write_text(json.dumps({'status':1,'stdout':'','stderr':str(error)}));raise
    finally:
        call('close')
        if state:
            assert profile.exists()  # Explicit fixture profile, never implicitly deleted.
            if os.environ.get('PI_BROWSER_TEST_DETACH_STAGE') and fixture_alive():
                # Test controller still owns this isolated synthetic fixture,
                # even though the browser wrapper deliberately relinquished it.
                assert Path(env['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
                os.kill(state['pid'],15)
        server.shutdown();server.server_close()


def main():
    if sys.argv[1:2]==['--worker']:worker(sys.argv[2:]);return
    if '--wtype' in sys.argv:
        index=sys.argv.index('--wtype');os.environ['PI_BROWSER_TEST_WTYPE']=sys.argv[index+1];del sys.argv[index:index+2]
    if not os.environ.get('PI_BROWSER_TEST_WTYPE'):raise SystemExit('--wtype is required for isolated test-human input')
    if '--simulate-human-consent' not in sys.argv:sys.argv.append('--simulate-human-consent')
    headed.__file__=__file__;headed.main()

if __name__=='__main__':
    if '--harness' not in sys.argv and sys.argv[1:2]!=['--worker'] and os.environ.get('PI_BROWSER_TEST_HARNESS'):
        sys.argv+=['--harness',os.environ['PI_BROWSER_TEST_HARNESS']]
    main()
