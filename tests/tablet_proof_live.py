"""Real native-window proof on private Labwc → Hyprland, never the host seat."""
import importlib.util
import io
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
from unittest.mock import patch


def until(check, reason, timeout=25):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        try:
            value=check()
            if value:return value
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:last=error
        time.sleep(.05)
    raise AssertionError(reason+(': '+str(last) if last else ''))


def outer(script=None):
    root=Path(tempfile.mkdtemp(prefix='twa.proof.'))
    (root/'r').mkdir(mode=0o700);(root/'home').mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith(('PI_','PROJECT_OBJECT_','HL_'))}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','HYPRLAND_INSTANCE_SIGNATURE','DBUS_SESSION_BUS_ADDRESS','QT_PLUGIN_PATH','QML_IMPORT_PATH'):
        env.pop(key,None)
    env.update(TABLET_WINDOW_TEST_ROOT=str(root),HOME=str(root/'home'),XDG_RUNTIME_DIR=str(root/'r'),
               XDG_CONFIG_HOME=str(root/'config'),XDG_CONFIG_DIRS=str(root/'empty'),XDG_DATA_HOME=str(root/'data'),
               XDG_STATE_HOME=str(root/'state'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',
               WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='1',WLR_RENDERER='gles2',
               WLR_RENDER_DRM_DEVICE='/dev/dri/renderD128',WLR_LIBINPUT_NO_DEVICES='1',
               QT_QPA_PLATFORM='wayland',QT_QUICK_CONTROLS_STYLE='Basic',QT_FORCE_STDERR_LOGGING='1',
               DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(root/'no-system-bus'),VIVALDI_FFMPEG_AUTO='0',PYTHONDONTWRITEBYTECODE='1')
    print('Private proof artifacts:',root,flush=True)
    headless=root/'headless-state';headless.write_text('off')
    # The host may deliberately be in external-display/headless posture. Mask
    # only this file in a mount namespace; never change host display state or
    # weaken the production awake-internal-panel guard for the private proof.
    return subprocess.call(['bwrap','--bind','/','/','--dev-bind','/dev','/dev','--tmpfs','/tmp/.X11-unix','--tmpfs','/run/headless-mode',
                            '--ro-bind',str(headless),'/run/headless-mode/state',
                            'dbus-run-session','--',sys.executable,script or __file__],env=env)


def inner():
    root=Path(os.environ['TABLET_WINDOW_TEST_ROOT']);runtime=root/'r'
    native = os.environ.get('TABLET_TEST_NATIVE_FOLD') == '1'
    orientation_file = root/'orientation'
    orientation_file.write_text('normal')
    os.environ['TABLET_TEST_ORIENTATION'] = str(orientation_file)
    assert str(root).startswith('/tmp/twa.proof.') and runtime==Path(os.environ['XDG_RUNTIME_DIR'])
    processes=[]
    requests=[]
    playback = {}
    attempts = {'tablet': False}
    server=None
    def start(command,name):
        p=subprocess.Popen(command,stdout=(root/(name+'.log')).open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        processes.append(p);return p
    def ctl(*args):return subprocess.check_output([os.environ['TABLET_TEST_HYPRCTL'],*args],text=True,timeout=5).strip()
    def clients():return json.loads(ctl('clients','-j'))
    def meta(client):return {k:client.get(k) for k in ('address','pid','workspace','monitor','floating','at','size','fullscreen','fullscreenClient','tags')}
    def proof(command,*args):
        result=subprocess.run([os.environ['TABLET_PROOF_BIN'],command,*args],capture_output=True,text=True,timeout=30)
        if result.returncode:raise RuntimeError(result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    def status():return proof('status')
    def scene():return json.loads(subprocess.check_output(['quickshell','ipc','--path',os.environ['TABLET_TEST_PROOF_QML'],'call','tabletNativeScene' if native else 'tabletProofScene','status'],text=True,timeout=5))
    def snapshot(name):
        assert str(ipc).startswith(str(runtime)+'/hypr/')
        image=Image.open(io.BytesIO(subprocess.check_output(['grim','-o','eDP-1','-']))).convert('RGB')
        image.save(root/(name+'.png'));return image
    def color_center(image,color):
        points=[(x,y) for y in range(0,image.height,3) for x in range(0,image.width,3) if max(abs(a-b) for a,b in zip(image.getpixel((x,y)),color))<5]
        if len(points)<10:return None
        return ((min(x for x,y in points)+max(x for x,y in points))//2,(min(y for x,y in points)+max(y for x,y in points))//2)
    def assert_single_indicator(image, inset=0):
        # Count rendered light horizontal bars, not declared/enabled handlers.
        # The retired edge component drew another line 5px from the bottom.
        rows=[]
        bottom=image.height-round(inset)
        for y in range(max(0,bottom-60), bottom):
            pixels=[image.getpixel((x,y)) for x in range(image.width//2-40,image.width//2+40)]
            # Browser media progress tracks span most of the output; shell
            # indicators are only 100px wide. Do not count the app's controls.
            outside=[image.getpixel((image.width//2+dx,y)) for dx in (-65,65)]
            center=image.getpixel((image.width//2,y))
            if sum(min(color)>=160 and max(abs(a-b) for a,b in zip(color,center))<=3 for color in pixels)>=72 and all(max(abs(a-b) for a,b in zip(color,center))>=8 for color in outside):
                rows.append(y)
        bands=[]
        for y in rows:
            if not bands or y>bands[-1][-1]+1: bands.append([])
            bands[-1].append(y)
        assert len(bands)==1, ('expected exactly one rendered swipe indicator',bands,inset)
        return (image.width//2, (bands[0][0]+bands[0][-1])//2)
    def handle_center(name, inset=0):
        point=assert_single_indicator(snapshot(name),inset)
        rect=scene()['navigationInput']
        assert rect['width']==180 and rect['height']==52, ('unexpected navigation capture area',rect)
        assert rect['x']<=point[0]<rect['x']+rect['width'] and rect['y']<=point[1]<rect['y']+rect['height'], (point,rect)
        return point
    def stage_call(process, method, *args):
        return subprocess.check_output(['quickshell','ipc','--pid',str(getattr(process,'pid',process)),'call','tabletStage',method,*args],text=True,timeout=5)
    def check_native_stage():
        # Exercise the exact packaged stage before any native Home exists,
        # including its persistent floor after the transition cover fades.
        # The client's busy cursor can be software-composited even without
        # grim -c. Park it outside the content/indicator sample regions.
        move(900,550)
        environment=dict(os.environ, TABLET_STAGE_PRESENTATION_ONLY='1',
            TABLET_STAGE_OWNER_PID=str(os.getpid()),
            TABLET_STAGE_OWNER_START=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
            TABLET_STAGE_ASSETS=str(Path(os.environ['TABLET_TEST_PROOF_QML']).parent))
        with (root/'stage-presentation.log').open('w') as log:
            process=subprocess.Popen(['quickshell','--path',str(Path(os.environ['TABLET_TEST_PROOF_QML']).with_name('stage.qml'))],env=environment,stdout=log,stderr=log)
            processes.append(process)
            try:
                until(lambda:(lambda s:s['cover'] and s['backdrop'] and s['presentationOnly'])(json.loads(stage_call(process,'status'))),'neutral stage frames')
                image=snapshot('native-entry-cover')
                # Ignore delayed transition notice/cancel; neither launcher
                # content nor swipe indicators may occur in the cover.
                for area in ((0,0,960,480),(0,610,960,640)):
                    assert image.crop(area).getextrema()==((23,23),(43,43),(60,60)), ('non-neutral native cover',area)
                origin=json.loads(ctl('activeworkspace','-j'))['name']
                ctl('dispatch','workspace','name:stage-only-fixture')
                stage_call(process,'reveal')
                until(lambda:not json.loads(stage_call(process,'status'))['covering'],'stage cover faded')
                time.sleep(.6)  # Let the private compositor's workspace animation settle.
                image=snapshot('native-persistent-floor')
                for area in ((0,0,850,640),(850,0,960,480),(850,610,960,640)):
                    assert image.crop(area).getextrema()==((23,23),(43,43),(60,60)), ('persistent stage rendered another Home/navigation',area)
            finally:
                if 'origin' in locals():
                    ctl('dispatch','workspace','name:'+origin)
                    time.sleep(.6)
                process.terminate();process.wait(timeout=5)
    pointer=None;ipc=None
    def pointer_command(line):
        assert ipc and str(ipc).startswith(str(runtime)+'/hypr/')
        assert os.environ['WAYLAND_DISPLAY']!='wayland-0' or (runtime/'wayland-0').exists()
        pointer.stdin.write(line+'\n');pointer.stdin.flush()
        assert select.select([pointer.stdout],[],[],5)[0]
        assert pointer.stdout.readline().strip()=='OK'
    def move(x,y):pointer_command(f'move {x} {y} 960 640')
    def click(x,y):move(x,y);pointer_command('down');time.sleep(.06);pointer_command('up')
    def swipe(x,y,end_y):
        move(x,y);pointer_command('down')
        for i in range(1,9):move(x,round(y+(end_y-y)*i/8));time.sleep(.035)
        pointer_command('up')
    def keys(*args):
        assert str(ipc).startswith(str(runtime)+'/hypr/')
        subprocess.run(['wtype',*args],check=True,timeout=10)
    try:
        class Page(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path.startswith('/state/'):
                    _, _, role, state = self.path.split('/')
                    playback[role] = state == 'playing'
                    self.send_response(204); self.end_headers(); return
                if self.path.startswith('/attempt/'):
                    role = self.path.split('/')[-1]
                    self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
                    self.wfile.write(json.dumps({'attempt': attempts.get(role, False)}).encode()); return
                self.send_response(200)
                self.send_header('Content-Type','video/webm' if self.path=='/video.webm' else 'text/html')
                self.end_headers()
                if self.path=='/video.webm':self.wfile.write(Path(os.environ['TABLET_TEST_VIDEO']).read_bytes());return
                self.wfile.write(b'''<!doctype html><title>Native proof fixture</title>
<style>body{margin:0;background:#c5314c;color:white}input{position:fixed;left:20px;top:20px;width:80%;height:60px;background:#e8f0fa;border:0;font-size:28px}button{position:fixed;left:30%;top:40%;width:40%;height:20%;background:#ffd42a;border:0}video{width:100vw;height:100vh;object-fit:fill}video:not(:fullscreen){display:none}</style>
<input id=text placeholder="Private input"><button id=full>Fullscreen video</button><video id=video src=/video.webm muted loop></video>
<script>
const role=location.pathname==='/'?'tablet':location.pathname.slice(1);
function report(element,name){let attempted=false;setInterval(()=>{
  fetch('/state/'+name+'/'+(element.paused?'paused':'playing'));
  fetch('/attempt/'+name).then(r=>r.json()).then(s=>{if(s.attempt&&!attempted){
    attempted=true;element.play();fetch('/attempted-'+name)}})},200)}
if(role!=='tablet'){document.title='Media '+role+' fixture';video.style.display='block';video.play();full.remove();text.remove()}
if(__NATIVE__&&role==='tablet'){
  const cross=document.createElement('iframe');cross.src=location.origin.replace('127.0.0.1','localhost')+'/frame';
  cross.style='position:fixed;right:0;bottom:0;width:100px;height:60px';document.body.append(cross);
  const blank=document.createElement('iframe');blank.src='about:blank';blank.style='position:fixed;left:0;bottom:0;width:100px;height:60px';
  blank.onload=()=>{const media=blank.contentDocument.createElement('video');media.src=location.origin+'/video.webm';
    media.muted=true;media.loop=true;blank.contentDocument.body.append(media);media.play();report(media,'blank')};document.body.append(blank);
}
if(role==='frame'){
  const host=document.createElement('div');document.body.append(host);const shadow=host.attachShadow({mode:'open'});
  const media=document.createElement('video');media.src='/video.webm';media.muted=true;media.loop=true;shadow.append(media);
  media.play();report(media,'frame-shadow');
}
document.onclick=e=>{fetch('/clicked-'+e.target.tagName);if(e.target.id==='full'){video.play();video.requestFullscreen()}};
if(role==='tablet'){text.onfocus=()=>fetch('/focused');text.oninput=()=>fetch('/typed-'+encodeURIComponent(text.value))}
document.onfullscreenchange=()=>fetch('/media-'+!!document.fullscreenElement);report(video,role);
</script>'''.replace(b'__NATIVE__',b'true' if native else b'false'))
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Page)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}/'
        fake=root/'fake-bin';fake.mkdir()
        # System controls are private stubs; never touch host audio/backlight.
        for name in ('wpctl','brightnessctl'):
            path=fake/name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(root/name)+'.calls"\n'+
                            ('case "$1" in get-volume) echo "Volume: 0.40";; esac\n' if name=='wpctl' else
                             'case "$2" in max) echo 100;; get) echo 60;; esac\n'))
            path.chmod(0o700)
        os.environ['TABLET_TEST_FAKE_BIN']=str(fake)
        (root/'labwc').mkdir();start(['labwc','-C',str(root/'labwc')],'labwc')
        outer_socket=until(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None),'outer socket')
        os.environ['WAYLAND_DISPLAY']=outer_socket.name
        config=root/'hyprland.conf'
        config.write_text('monitor=,960x640@60,auto,1\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\nxwayland {\n enabled=false\n}\nlayerrule=match:namespace ^tablet-native-proof$, no_anim on\n')
        if native:
            with config.open('a') as output:
                output.write('layerrule=match:namespace ^tablet-native$, no_anim on\nlayerrule=match:namespace ^tablet-rotation-fade$, no_anim on\n')
            directory = Path(os.environ['XDG_CONFIG_HOME'])/'hypr'
            directory.mkdir(parents=True)
            (directory/'hyprland.conf').symlink_to(config)
        start([os.environ['TABLET_TEST_HYPRLAND'],'-c',str(config)],'hyprland')
        ipc=until(lambda:next((runtime/'hypr').glob('*/.socket.sock'),None),'nested IPC')
        os.environ['HYPRLAND_INSTANCE_SIGNATURE']=ipc.parent.name
        os.environ['WAYLAND_DISPLAY']=until(lambda:next((p.name for p in runtime.glob('wayland-*') if p.is_socket() and p!=outer_socket),None),'nested Wayland')
        ctl('output','create','headless','eDP-1');ctl('keyword','monitor','eDP-1,960x640@60,0x0,1')
        for monitor in json.loads(ctl('monitors','-j')):
            if monitor['name']!='eDP-1':ctl('keyword','monitor',monitor['name']+',disable')
        ctl('dismissnotify','-1');ctl('dispatch','focusmonitor','eDP-1');ctl('dispatch','workspace','name:proof-fixture')
        pointer=subprocess.Popen([os.environ['TABLET_TEST_POINTER']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,start_new_session=True)
        processes.append(pointer)
        assert select.select([pointer.stdout],[],[],5)[0] and pointer.stdout.readline().strip()=='READY'
        start(['wtype','-s','600000','-k','Shift_L'],'seat-keyboard')
        if native:
            manifests = root/'config/vivaldi/NativeMessagingHosts'
            manifests.mkdir(parents=True, exist_ok=True)
            (manifests/'org.machine.tablet_media.json').write_text(Path(os.environ['TABLET_TEST_MEDIA_MANIFEST']).read_text())
        flags=['--user-data-dir='+str(root/'config/vivaldi' if native else root/'browser-profile'),'--ozone-platform=wayland','--enable-wayland-ime','--wayland-text-input-version=3','--no-first-run','--no-default-browser-check','--password-store=basic',
               '--disable-background-networking','--disable-component-update','--disable-sync','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost, EXCLUDE tablet.localhost']
        if native:
            flags += ['--load-extension='+os.environ['TABLET_TEST_MEDIA_EXTENSION'], '--disable-extensions-except='+os.environ['TABLET_TEST_MEDIA_EXTENSION']]
        start([os.environ['TABLET_TEST_VIVALDI'],*flags,'--new-window','about:blank'],'browser')
        first=until(lambda:next((c for c in clients() if c.get('class')=='vivaldi-stable' and c.get('title')),None),'browser window')
        time.sleep(1)
        # First-run onboarding belongs to this disposable browser only. Keep
        # that window as the sibling and request a normal second native window,
        # as the already-warm real browser will be used in the live proof.
        start([os.environ['TABLET_TEST_VIVALDI'],*flags,'--new-window',url],'fixture-launch')
        second=until(lambda:next((c for c in clients() if c.get('class')=='vivaldi-stable' and c['address']!=first['address']),None),'second private window')
        # Vivaldi can open its Start Page instead of the requested URL during
        # first-run initialization. Navigate only this disposable test window.
        until(lambda:any(c['address']==second['address'] and c.get('title') not in ('', 'Vivaldi - Vivaldi') for c in clients()),'private browser UI initialized')
        time.sleep(2)
        ctl('dispatch','focuswindow','address:'+second['address'])
        keys('-M','ctrl','-k','l','-m','ctrl','-s','300','-d','20',url,'-s','300','-k','Return')
        browser=until(lambda:next((c for c in clients() if c['address']==second['address'] and 'Native proof fixture' in c.get('title','')),None),'private fixture window')
        address=browser['address']
        until(lambda:len([c for c in clients() if c.get('class')=='vivaldi-stable'])==2,'sibling window')
        time.sleep(1)
        laptop_window = first
        if native:
            previous = {c['address'] for c in clients()}
            start([os.environ['TABLET_TEST_VIVALDI'],*flags,'--new-window',url+'desktop'],'desktop-media-launch')
            desktop = until(lambda:next((c for c in clients() if c.get('class')=='vivaldi-stable' and c['address'] not in previous),None),'second private media window')
            ctl('dispatch','focuswindow','address:'+desktop['address'])
            time.sleep(1)
            keys('-M','ctrl','-k','l','-m','ctrl','-s','300','-d','20',url+'desktop','-s','300','-k','Return')
            until(lambda:playback.get('desktop'),'other browser window playing')
            ctl('dispatch','movetoworkspacesilent','name:tablet-trial,address:'+address)
            laptop = start(['quickshell','--path',os.environ['TABLET_TEST_LAPTOP_QML']],'laptop-app')
            laptop_window = until(lambda:next((c for c in clients() if c['pid']==laptop.pid),None),'unrelated laptop app')
            ctl('dispatch','focuswindow','address:'+laptop_window['address'])
            time.sleep(.7)
        before={c['address']:meta(c) for c in clients()}
        browser_pid=browser['pid']
        if native: check_native_stage()
        proof('start','--address',address)
        until(lambda:status().get('ready'),'frontend frames')
        if native:
            assert status()['home'] and status()['browserRunning']
            assert json.loads(ctl('activeworkspace','-j'))['name']=='tablet-trial'
            assert next(c for c in clients() if c['address']==laptop_window['address'])['workspace']['name']=='proof-fixture'
            until(lambda:scene()['rendered'] and not scene()['transitioning'],'stable native Home')
            handle_center('original-design-home')
            proof('app')
            until(lambda:not scene()['home'] and not scene().get('transitioning') and scene()['rendered'],'native Home dismissal rendered')
            # Use the companion's actual Options UI in this disposable
            # browser, not an injected event, debugging port or test backdoor.
            pair_url='chrome-extension://'+os.environ['TABLET_TEST_MEDIA_EXTENSION_ID']+'/pair.html'
            start([os.environ['TABLET_TEST_VIVALDI'],*flags,pair_url],'pair-options-launch')
            until(lambda:any(c['address']==address and 'Pair tablet media' in c.get('title','') for c in clients()),'companion pairing page')
            pair_button=until(lambda:color_center(snapshot('pairing-page'),(38,207,135)),'pairing button')
            click(*pair_button)
            until(lambda:status().get('mediaPaired'),'window-scoped companion pairing',timeout=30)
            until(lambda:any(c['address']==address and 'Pair tablet media' in c.get('title','') for c in clients()),'registration tab removed')
            keys('-M','ctrl','-k','w','-m','ctrl')
            until(lambda:any(c['address']==address and 'Native proof fixture' in c.get('title','') for c in clients()),'own pairing page closed')
            other_url=url.replace('127.0.0.1','localhost')+'other-site'
            start([os.environ['TABLET_TEST_VIVALDI'],*flags,other_url],'other-site-tab-launch')
            until(lambda:any(c['address']==address and 'Media other-site fixture' in c.get('title','') for c in clients()),'different-site tablet tab')
            until(lambda:playback.get('other-site'),'second tablet site playing')
            keys('-M','ctrl','-M','shift','-k','Tab','-m','shift','-m','ctrl')
            until(lambda:any(c['address']==address and 'Native proof fixture' in c.get('title','') for c in clients()),'original media tab restored')
        active=next(c for c in clients() if c['address']==address)
        assert not active['floating'] and active['fullscreen']==2 and active['fullscreenClient']==1,active
        assert active['workspace']==before[address]['workspace']
        target=lambda:next(c for c in clients() if c['address']==address)
        until(lambda:target()['size']==[960,640],'native app fills output')
        button=until(lambda:color_center(snapshot('app'),(255,212,42)),
                     'original fixture rendered after tab switch')
        previous=len(requests);click(*button)
        until(lambda:'/media-true' in requests,'browser client fullscreen request')
        if native:
            # The second site was verified playing while foreground above.
            # Vivaldi may itself pause that muted background tab on tab switch;
            # do not mistake its delayed report for a tablet pause regression.
            # Its explicit background replay attempts are still tested below.
            until(lambda:all(playback.get(role) for role in ('tablet','desktop','frame','frame-shadow','blank')),
                  'cross-origin/inherited frames, shadow media and separate window playing')
        until(lambda:target()['fullscreen']==2 and target()['fullscreenClient']==2,'true native media fullscreen')
        move(500,300)
        time.sleep(3.5)  # Let the browser's own video controls/bubble fade.
        media=snapshot('media')
        # The browser may retain its own native video controls at the bottom;
        # those are not shell margins. Check video across both top corners and
        # near the lower content edge, plus the native output-sized geometry.
        assert target()['at']==[0,0] and target()['size']==[960,640]
        for x,y in [(20,20),(940,20),(20,530),(940,530)]:
            r,g,b=media.getpixel((x,y));assert g>r+50 and g>b+50,(x,y,(r,g,b))
        # The edge overlay must not swallow application touches elsewhere.
        count=len([r for r in requests if r.startswith('/clicked-')]);click(320,220)
        until(lambda:len([r for r in requests if r.startswith('/clicked-')])>count,'touch/click passthrough')
        swipe(930,8,150)
        until(lambda:status()['drawer'],'global settings over video')
        assert target()['fullscreenClient']==2
        snapshot('settings-over-media')
        proof('volume','--value','35');proof('brightness','--value','55')
        assert 'set-volume @DEFAULT_AUDIO_SINK@ 0.35' in (root/'wpctl.calls').read_text()
        assert '--device=intel_backlight set 55%' in (root/'brightnessctl.calls').read_text()
        proof('dismiss')
        until(lambda:not scene()['drawer'] and not scene().get('transitioning') and scene()['rendered'],'settings dismissal rendered/input mask committed')
        if native:
            # Original swipe-and-pause navigation must be available over the
            # real video too, without capturing a browser texture or changing
            # its fullscreen state. Initial edge contact expands the mask.
            x,y=handle_center('single-indicator-over-media')
            move(x,y); pointer_command('down')
            for i in range(1,9): move(x,round(y-150*i/8)); time.sleep(.035)
            time.sleep(.4)
            pointer_command('up')
            until(lambda:scene()['overview'],'original app switcher gesture over media')
            assert target()['fullscreenClient']==2
            snapshot('original-design-switcher')
            click(480,320)
            until(lambda:not scene()['overview'],'resume existing browser from switcher')
        x,y=handle_center('visible-handle-home') if native else (480,634)
        swipe(x,y,y-130)
        until(lambda:status()['home'],'global Home gesture over video')
        snapshot('home-over-media')
        assert target()['fullscreenClient']==2
        proof('app');assert target()['fullscreenClient']==2
        until(lambda:not scene()['home'] and not scene().get('transitioning') and scene()['rendered'],'browser resume rendered/input mask committed')
        keys('-k','Escape')
        until(lambda:'/media-false' in requests,'leave media fullscreen')
        until(lambda:target()['fullscreenClient']==1,'client returns to native maximized state')
        assert target()['fullscreen']==2,'app must remain screen filling without resize enforcement'
        time.sleep(.4)
        image=snapshot('app-after-media')
        field=color_center(image,(232,240,250));assert field,'native input fixture missing'
        if native:
            # Test DOM passthrough outside media fullscreen: Chromium's own
            # fullscreen controls consume bottom clicks before DOM handlers.
            handle_center('bottom-passthrough-geometry')
            # Stay inside the handle's vertical band but above Vivaldi's own
            # status bar so the fixture can authoritatively report delivery.
            handle_y=round(scene()['navigationInput']['y']+8)
            for side in (220,740):
                count=len([r for r in requests if r.startswith('/clicked-')])
                click(side,handle_y)
                until(lambda:len([r for r in requests if r.startswith('/clicked-')])>count,'bottom app touch beside handle')
                assert not status()['home'], 'bottom app touch incorrectly opened Home'
        click(*field)
        until(lambda:'/focused' in requests,'native input touch focus')
        until(lambda:json.loads(ctl('monitors','-j'))[0].get('reserved',[0,0,0,0])[3]>0,'native IME panel')
        keys('touch-proof')
        until(lambda:any(r.startswith('/typed-touch-proof') for r in requests),'private native text input')
        if native:
            for side in (220,740):
                inset=status()['keyboardInset']
                assert inset > 0
                handle_center('ime-passthrough-'+str(side),inset)
                handle_y=round(scene()['navigationInput']['y']+8)
                count=len([r for r in requests if r.startswith('/clicked-')])
                click(side,handle_y)
                until(lambda:len([r for r in requests if r.startswith('/clicked-')])>count,'app touch beside handle above IME')
                assert not status()['home'], 'app touch above IME incorrectly opened Home'
                click(*field)
                until(lambda:status()['keyboardInset']>0,'refocus text after IME passthrough')
            inset=status()['keyboardInset']
            x,y=handle_center('single-indicator-above-ime',inset)
            swipe(x,y,y-110)
            until(lambda:status()['home'],'original Home gesture above open IME')
            until(lambda:status()['keyboardInset']==0,'Home hides IME without losing navigation')
            proof('app')
            until(lambda:not scene()['home'] and not scene().get('transitioning'),'resume after IME Home')
        proof('hide-keyboard')
        if native:
            # Validate the actual session's return cover too, not merely the
            # standalone stage fixture. Close must keep this neutral cover
            # while retiring the single Home and restoring laptop focus.
            journal=json.loads((runtime/'tablet-proof/recovery.json').read_text())
            stage_pid=next(child['pid'] for child in journal['children'] if child['role']=='stage')
            stage_call(stage_pid,'cover','Returning to laptop…')
            until(lambda:json.loads(stage_call(stage_pid,'status'))['cover'],'native return cover frames')
            move(900,550)
            image=snapshot('native-return-cover')
            for area in ((0,0,960,480),(0,610,960,640)):
                assert image.crop(area).getextrema()==((23,23),(43,43),(60,60)), ('return cover rendered another Home/navigation',area)
        proof('close')
        until(lambda:not status().get('running'),'clean proof exit')
        time.sleep(.7)
        after={c['address']:meta(c) for c in clients()}
        assert set(before)==set(after),'no windows launched/closed by proof'
        for key in before:
            assert after[key]==before[key],(key,before[key],after[key])
        assert target()['pid']==browser_pid
        assert not (runtime/'tablet-proof/recovery.json').exists()
        if native:
            assert 'recovery retained' not in (runtime/'tablet-proof/supervisor.log').read_text(), 'normal close silently fell back to supervisor recovery'
            tablet_roles=('tablet','frame','frame-shadow','blank','other-site')
            until(lambda:all(playback.get(role) is False for role in tablet_roles) and playback.get('desktop') is True,
                  'all tablet sites/frames paused while other window keeps playing')
            for role in tablet_roles:attempts[role]=True
            until(lambda:all('/attempted-'+role in requests for role in tablet_roles),'background replay attempted across sites/frames')
            time.sleep(1)
            assert all(playback.get(role) is False for role in tablet_roles) and playback.get('desktop') is True,'background replay escaped tablet-only pause'
            for role in tablet_roles:attempts[role]=False
        if native:
            # Losing the stage must establish a fresh verified cover before a
            # normal release/return, not silently fall through to recovery.
            proof('start','--address',address)
            time.sleep(.5)
            assert all(playback.get(role) is False for role in tablet_roles) and playback.get('desktop') is True,'return unexpectedly resumed playback'
            journal=json.loads((runtime/'tablet-proof/recovery.json').read_text())
            stage=next(child for child in journal['children']
                       if any(arg.endswith(b'/stage.qml') for arg in (Path('/proc')/str(child['pid'])/'cmdline').read_bytes().split(b'\0')))
            assert (Path('/proc')/str(stage['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==stage['start']
            descriptor=os.pidfd_open(stage['pid'])
            try:signal.pidfd_send_signal(descriptor,signal.SIGKILL)
            finally:os.close(descriptor)
            time.sleep(.15)
            proof('close')
            assert json.loads(ctl('activewindow','-j'))['address']==laptop_window['address']
            assert 'recovery retained' not in (runtime/'tablet-proof/supervisor.log').read_text()
        # Kill only the verified private backend, proving the independent
        # supervisor restores presentation/settings without a running frontend.
        proof('start','--address',address)
        identity=status()['backend'];proc=Path('/proc')/str(identity['pid'])
        assert (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==identity['start']
        assert (b'XDG_RUNTIME_DIR='+os.fsencode(runtime)) in (proc/'environ').read_bytes().split(b'\0')
        descriptor=os.pidfd_open(identity['pid'])
        try:signal.pidfd_send_signal(descriptor,signal.SIGKILL)
        finally:os.close(descriptor)
        until(lambda:not status().get('running') and not (runtime/'tablet-proof/recovery.json').exists(),'automatic backend-crash recovery')
        time.sleep(.6)
        assert {c['address']:meta(c) for c in clients()}==before
        # A sibling taking focus in the same workspace must end eligibility;
        # no overlay or keyboard may remain attached over the wrong app.
        proof('start','--address',address)
        ctl('dispatch','focuswindow','address:'+first['address'])
        until(lambda:not status().get('running') and not json.loads(ctl('layers','-j'))['eDP-1']['levels']['3'],'same-workspace focus-loss stops overlay')
        assert (runtime/'tablet-proof/recovery.json').exists()
        until(lambda:proof('recover','--activate') or not (runtime/'tablet-proof/recovery.json').exists(),'explicit safe recovery after focus loss')
        time.sleep(.6)
        assert {c['address']:meta(c) for c in clients()}==before
        assert not (runtime/'tablet-proof/recovery.json').exists()
        # Regression: no presentation mutation was introduced for a source
        # acquired at2/2. That must NOT bypass automatic focus-loss safety.
        ctl('dispatch','focuswindow','address:'+address)
        ctl('dispatch','fullscreenstate','2 2')
        proof('start','--address',address)
        assert not json.loads((runtime/'tablet-proof/recovery.json').read_text())['window']['applied']
        ctl('dispatch','focuswindow','address:'+first['address'])
        until(lambda:not status().get('running') and not json.loads(ctl('layers','-j'))['eDP-1']['levels']['3'],'unchanged-mode focus-loss stop')
        assert json.loads(ctl('activewindow','-j'))['address']==first['address'],'automatic cleanup stole focus'
        assert (runtime/'tablet-proof/recovery.json').exists()
        until(lambda:proof('recover','--activate') or not (runtime/'tablet-proof/recovery.json').exists(),'unchanged-mode explicit recovery')
        ctl('dispatch','focuswindow','address:'+address)
        ctl('dispatch','fullscreenstate','0 0')
        time.sleep(.6)
        assert {c['address']:meta(c) for c in clients()}==before
        if native:
            # Exercise the actual shared rotation controller on a private fake
            # sensor, with no system bus or physical input devices available.
            proof('start','--address',address)
            orientation_file.write_text('left-up')
            until(lambda:next(m for m in json.loads(ctl('monitors','-j')) if m['name']=='eDP-1')['transform']==1,
                  'native session rotates in original app workspace')
            snapshot('original-design-portrait')
            proof('close')
            until(lambda:next(m for m in json.loads(ctl('monitors','-j')) if m['name']=='eDP-1')['transform']==0,
                  'native exit restores orientation')
            orientation_file.write_text('normal')
            spec=importlib.util.spec_from_file_location('private_fold_edges',os.environ['TABLET_TEST_NATIVE_SOURCE'])
            fold=importlib.util.module_from_spec(spec);spec.loader.exec_module(fold)
            edges=fold.FoldEdges()
            read=Path.read_text
            def tick(posture):
                def private_posture(path,*args,**kwargs):
                    if str(path)=='/sys/devices/platform/thinkpad_acpi/hotkey_tablet_mode':return posture
                    return read(path,*args,**kwargs)
                with patch.object(Path,'read_text',private_posture):edges.tick()
            ctl('dispatch','focuswindow','address:'+laptop_window['address'])
            tick('1')
            assert status()['native'] and status()['automatic'] and not status()['home'],'last app view was not resumed'
            assert status()['source']['address']==address
            assert json.loads(ctl('activeworkspace','-j'))['name']=='tablet-trial'
            tick('0')
            assert not status()['running'] and not status()['recovery']
            assert json.loads(ctl('activewindow','-j'))['address']==laptop_window['address']
            assert {c['address']:meta(c) for c in clients()}==before
            tick('1');proof('home');proof('close');tick('1')
            assert not status()['running'],'manual exit was reopened while still folded'
            tick('0');tick('1')
            assert status()['home'],'last Home view was not resumed'
            tick('0')
            proof('start')
            tick('0')
            assert status()['running'] and not status()['automatic'],'unfold without a fold closed a manual session'
            tick('1')
            assert status()['automatic'] and status()['home'],'fold adoption reset the existing tablet view'
            tick('0')
            assert not status()['running']
            # Simulate the user closing ONLY the disposable tablet browser.
            # A later Home launch creates its own new tablet-local window,
            # never borrows the still-running laptop Vivaldi or laptop app.
            ctl('dispatch','closewindow','address:'+address)
            until(lambda:not any(c['address']==address for c in clients()),'private tablet window closed')
            ctl('dispatch','focuswindow','address:'+laptop_window['address'])
            before_home = {c['address']:meta(c) for c in clients()}
            proof('start')
            assert status()['home'] and not status()['browserRunning']
            assert status()['browserAvailable']
            proof('settings');proof('dismiss');proof('app')
            until(lambda:status()['browserRunning'] and not status()['home'],'new tablet-only browser launch from Home')
            new_source = status()['source']['address']
            assert new_source not in before_home and new_source!=address
            assert next(c for c in clients() if c['address']==new_source)['workspace']['name']=='tablet-trial'
            proof('home');proof('close')
            assert json.loads(ctl('activewindow','-j'))['address']==laptop_window['address']
            after_home = {c['address']:meta(c) for c in clients()}
            for key in before_home: assert after_home[key]==before_home[key]
            proof('start')
            assert status()['home'] and status()['source']['address']==new_source
            proof('app');proof('close')
            assert len(clients())==len(before_home)+1,'resume duplicated a tablet application'
            # Actual Pegasus in the private HOME, with one disposable native
            # game. No real library, Steam, account, saves or host seat exists.
            import shlex
            games = root/'fixture-games'; games.mkdir()
            (games/'dummy.rom').touch()
            game_ui = root/'dummy-game.qml'
            game_ui.write_text('''import Quickshell
import QtQuick
ShellRoot { FloatingWindow { visible: true; width: 480; height: 320; title: "Tablet fixture game"; color: "#15b94d"; onClosed: Qt.quit() } }
''')
            delayed = 'sleep 3; exec ' + shlex.join(['quickshell', '--path', str(game_ui)])
            launch = [sys.executable, os.environ['TABLET_GAMING_SOURCE'], '--', 'sh', '-c', delayed]
            failure = [sys.executable, os.environ['TABLET_GAMING_SOURCE'], '--', '/definitely-missing-tablet-test-game']
            (games/'failed.rom').touch()
            (games/'metadata.pegasus.txt').write_text('collection: Tablet fixture\n\ngame: 01 Disposable tablet test\nfile: dummy.rom\nlaunch: '+shlex.join(launch)+'\n\ngame: 02 Confirmed failure\nfile: failed.rom\nlaunch: '+shlex.join(failure)+'\n')
            ctl('keyword', 'windowrule', 'match:title ^Tablet fixture game$, float on')
            pegasus_config = root/'config/pegasus-frontend'; pegasus_config.mkdir(parents=True, exist_ok=True)
            (pegasus_config/'game_dirs.txt').write_text(str(games)+'\n')
            theme = pegasus_config/'themes/tablet-fixture'; theme.mkdir(parents=True)
            (theme/'theme.cfg').write_text('name: Tablet fixture\nauthor: Private test\nversion: 1\n')
            (theme/'theme.qml').write_text('''import QtQuick 2.15
FocusScope {
    Rectangle { anchors.fill: parent; color: tabletLaunchActive ? "#245ac7" : "#253b68" }
    Text { anchors.centerIn: parent; color: "white"; text: tabletLaunchActive ? "Launching fixture game…" : "Tablet library: 1 play, 2 fail" }
    Keys.onPressed: event => {
        if (tabletLaunchActive) { event.accepted = true; return }
        if (event.key === Qt.Key_1 || event.key === Qt.Key_2) {
            event.accepted = true
            api.allGames.get(event.key === Qt.Key_1 ? 0 : 1).launch()
        }
    }
}
''')
            (pegasus_config/'settings.txt').write_text('general.fullscreen: true\nproviders.steam.enabled: false\ngeneral.theme: themes/tablet-fixture/\n')
            proof('start'); proof('games')
            until(lambda:status()['pegasusRunning'] and not status()['home'], 'real tablet-local Pegasus launch')
            time.sleep(1)
            snapshot('pegasus-library')
            assert status()['activeApp']=='games'
            library = next(c for c in clients() if c['class'].startswith(('pegasus-fe','org.pegasus-frontend')))
            assert library['workspace']['name']=='tablet-trial'
            # Input is sent only to the private compositor, never the host seat.
            keys('1')
            until(lambda:status()['gameLaunching'], 'real Pegasus owns the delayed launch')
            for sample in range(2):
                assert status()['pegasusRunning'] and not status()['home'], 'launch fell back to Tablet Home'
                assert any(c['address']==library['address'] and c['mapped'] for c in clients()), 'Pegasus loading window was torn down'
                image=snapshot('pegasus-owned-loading-'+str(sample))
                pixel=image.getpixel((40,40))
                assert pixel==(36,90,199) or (pixel==(21,185,77) and status()['gameRunning']), 'neither Pegasus loading nor verified game is visible'
                time.sleep(.35)
            until(lambda:status()['gameRunning'] and not status()['home'] and json.loads(ctl('activewindow','-j')).get('title')=='Tablet fixture game', 'verified floating game visible above retained Pegasus', timeout=45)
            game = next(c for c in clients() if c.get('title')=='Tablet fixture game')
            assert game['workspace']['name']=='tablet-trial' and game['floating']
            until(lambda:next(c for c in clients() if c['address']==game['address'])['size']==[960,640], 'floating game gets true screen-filling presentation')
            assert snapshot('visible-floating-game').getpixel((40,40))==(21,185,77)
            proof('close')
            restored=next(c for c in clients() if c['address']==game['address'])
            assert restored['floating'] and restored['fullscreen']==0 and restored['fullscreenClient']==0, 'unfold did not release game presentation'
            assert restored['size']==[480,320], restored
            assert any(c['address']==game['address'] for c in clients()), 'unfold closed a game'
            assert json.loads(ctl('activewindow','-j'))['address']==laptop_window['address']
            proof('start')
            assert status()['activeApp']=='games' and status()['gameRunning']
            assert json.loads(ctl('activewindow','-j'))['address']==game['address']
            ctl('dispatch','closewindow','address:'+game['address'])
            until(lambda:status()['pegasusRunning'] and not status()['gameRunning'], 'return to Pegasus after dummy game exit')
            until(lambda:json.loads(ctl('activewindow','-j')).get('pid')==library['pid'], 'library focus restored')
            assert any(c['address']==library['address'] for c in clients()), 'Pegasus did not retain the same window'
            keys('2')
            until(lambda:(lambda r:r.get('phase')=='done' and r.get('code')==1)(json.loads((runtime/'tablet-games/launch.json').read_text())), 'confirmed failed child releases its launch receipt', timeout=35)
            until(lambda:status()['pegasusRunning'] and not status()['gameLaunching'] and not status()['home'], 'failure returns to Pegasus rather than Home')
            caller=json.loads((runtime/'tablet-games/launch.json').read_text())['caller']['pid']
            until(lambda:not (Path('/proc')/str(caller)).exists(), 'Pegasus launch wrapper returned after failed attempt', timeout=30)
            time.sleep(.3)
            keys('-k','Return')  # Dismiss the real Pegasus launch-error dialog.
            keys('1')
            until(lambda:status()['gameRunning'] and json.loads(ctl('activewindow','-j')).get('title')=='Tablet fixture game', 'retry after failed launch is not permanently locked', timeout=45)
            retry=next(c for c in clients() if c.get('title')=='Tablet fixture game')
            ctl('dispatch','closewindow','address:'+retry['address'])
            until(lambda:status()['pegasusRunning'] and not status()['gameRunning'], 'retry returns to retained Pegasus')
            proof('app')
            assert status()['activeApp']=='vivaldi' and status()['browserRunning']
            proof('games')
            assert status()['pegasusRunning'] and not status()['home']
            proof('close')
            assert json.loads(ctl('activewindow','-j'))['address']==laptop_window['address']
            assert not (runtime/'tablet-proof/recovery.json').exists()
            assert not (runtime/'tablet-native-orientation.json').exists()
        print('PASS: native app/media fullscreen, global edge gestures, passthrough, real IME, exact layout return, backend crash recovery and focus-loss safety including unchanged2/2 acquisition'
              + ('; original Home/control visuals, persistent tablet-workspace app/Home resume, unrelated laptop app/focus return, tablet-only browser launch, rotation/restore, repeated fold ownership and real two-window isolated media pause/autoplay gate/no auto-resume; real Pegasus/dummy-game launch, unfold survival, resume, game exit/library return and browser switching; neutral entry/floor/return stage, single rendered indicator, visible-handle gestures and both-side bottom/IME passthrough' if native else ''),flush=True)
        return 0
    finally:
        if ipc:
            try:
                (root/'last-clients.json').write_text(json.dumps(clients(),indent=2))
                (root/'requests.json').write_text(json.dumps(requests))
                (root/'last-status.json').write_text(json.dumps(status(),indent=2))
                (root/'last-layers.json').write_text(ctl('layers','-j'))
                snapshot('last-frame')
            except (OSError,subprocess.SubprocessError):
                pass
        try:
            if ipc and (runtime/'tablet-proof/control.sock').exists():proof('close')
        except Exception as error:print('proof cleanup:',error,file=sys.stderr)
        if server:server.shutdown()
        for process in reversed(processes):
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for process in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        spec=importlib.util.spec_from_file_location('private_cleanup',os.environ['TABLET_TEST_CLEANUP'])
        cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)
        cleanup.cleanup_runtime(runtime)


if __name__=='__main__':
    raise SystemExit(inner() if os.environ.get('TABLET_WINDOW_TEST_ROOT') else outer())
