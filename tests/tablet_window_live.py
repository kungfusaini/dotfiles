"""Real Vivaldi + Quickshell capture in a private nested Hyprland.

No host sockets, profile, model, audio or physical input. Requires a render node.
Run the packaged tests/tablet-window-apps.nix tool, not against a live compositor.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import signal
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image


def until(check, message, timeout=25):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            result = check()
            if result: return result
        except (RuntimeError, subprocess.SubprocessError, ValueError, OSError) as error:
            last = error
        time.sleep(.05)
    raise AssertionError(message + (': ' + str(last) if last else ''))


def cleanup_runtime(runtime):
    """Reap daemonized compositor children too, never any live-session process."""
    runtime=Path(runtime)
    assert str(runtime).startswith(("/tmp/twa.","/tmp/tablet-window-test.")) and runtime.name=="r"
    protected={os.getpid()};parent=os.getppid()
    while parent>1 and parent not in protected:
        protected.add(parent)
        try:parent=int(Path(f"/proc/{parent}/stat").read_text().rsplit(")",1)[1].split()[1])
        except OSError:break
    marker=b"XDG_RUNTIME_DIR="+os.fsencode(runtime)
    descriptors=[]
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) in protected:continue
        fd=None
        try:
            if proc.stat().st_uid!=os.getuid() or (proc/"comm").read_text().strip()=="dbus-daemon":continue
            if marker not in (proc/"environ").read_bytes().split(b"\0"):continue
            fd=os.pidfd_open(int(proc.name))
            # Re-check after pinning identity; a recycled PID must not qualify.
            if marker not in (proc/"environ").read_bytes().split(b"\0"):os.close(fd);continue
            signal.pidfd_send_signal(fd,signal.SIGTERM)
            descriptors.append(fd)
        except (OSError,ProcessLookupError):
            if fd is not None:os.close(fd)
    end=time.monotonic()+3
    pending=set(descriptors)
    while pending and time.monotonic()<end:
        ready,_,_=select.select(list(pending),[],[],.1)
        pending.difference_update(ready)
    for fd in pending:
        try:signal.pidfd_send_signal(fd,signal.SIGKILL)
        except ProcessLookupError:pass
    for fd in descriptors:os.close(fd)


def outer():
    root = Path(tempfile.mkdtemp(prefix="twa."))
    runtime = root / "r"
    runtime.mkdir(mode=0o700)
    (root / "home").mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PI_", "PROJECT_OBJECT_", "HL_"))}
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS", "QT_PLUGIN_PATH", "QML_IMPORT_PATH", "QT_QUICK_BACKEND"):
        env.pop(key, None)
    env.update(TABLET_WINDOW_TEST_ROOT=str(root), HOME=str(root / "home"), XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(root / "config"), XDG_CONFIG_DIRS=str(root / "empty"), XDG_DATA_HOME=str(root / "data"),
               XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"), GSETTINGS_BACKEND="keyfile",
               WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="gles2",
               WLR_RENDER_DRM_DEVICE="/dev/dri/renderD128", WLR_LIBINPUT_NO_DEVICES="1", VIVALDI_FFMPEG_AUTO="0",
               QT_QPA_PLATFORM="wayland", QT_QUICK_CONTROLS_STYLE="Basic", PYTHONDONTWRITEBYTECODE="1")
    print("Private test artifacts: " + str(root), flush=True)
    return subprocess.call(["dbus-run-session", "--", sys.executable, __file__], env=env)


def inner():
    root = Path(os.environ["TABLET_WINDOW_TEST_ROOT"])
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    assert root.is_relative_to(Path(tempfile.gettempdir())) and runtime == root / "r"
    assert not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    processes = []
    stop = threading.Event()
    errors = []
    requests = []
    guard = {"enabled":False}
    log = (root / "surfaces.log").open("w")

    def start(command, name):
        p = subprocess.Popen(command, stdout=(root / (name + ".log")).open("w"), stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(p)
        return p

    def ctl(*args):
        return subprocess.run([os.environ["TABLET_TEST_HYPRCTL"], *args], check=True, capture_output=True, text=True, timeout=5).stdout

    def clients(): return json.loads(ctl("clients", "-j"))

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if self.path.startswith("/app") else "application/json")
            self.end_headers()
            if self.path.startswith("/app"):
                self.wfile.write(b'''<!doctype html><title>Private tablet app test</title>
<style>body{margin:0;background:#a5314c;color:white}input{position:fixed;top:0;left:0;width:90%;height:90px;font-size:32px}p{margin-top:160px}</style>
<input placeholder="Private input"><p>Native Vivaldi content</p>
<script>document.onclick=e=>{fetch('/clicked-'+e.target.tagName);if(e.target.tagName!='INPUT')document.querySelector('input').blur()};
setInterval(()=>fetch('/guard').then(r=>r.json()).then(v=>{window.onbeforeunload=v.enabled?(e=>{e.preventDefault();e.returnValue='';}):null}),100)</script>''')
            else:
                self.wfile.write(json.dumps(guard).encode())
        def log_message(self,*args): pass

    server = ThreadingHTTPServer(("127.0.0.1",0),Page)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/app"
    trial = None
    worker = None
    recorder = None
    normal = None
    pointer = None
    try:
        (root / "labwc").mkdir()
        start(["labwc", "-C", str(root / "labwc")], "labwc")
        outer_socket = until(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket()),None), "outer compositor")
        os.environ["WAYLAND_DISPLAY"] = outer_socket.name
        config = Path(os.environ["XDG_CONFIG_HOME"]) / "hypr/hyprland.conf"
        config.parent.mkdir(parents=True)
        config.write_text("monitor=,960x640@60,auto,1\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\nxwayland {\n enabled=false\n}\nlayerrule=match:namespace ^tablet-rotation-fade$, no_anim on\n")
        start([os.environ["TABLET_TEST_HYPRLAND"], "-c",str(config)],"hyprland")
        ipc = until(lambda:next((runtime / "hypr").glob("*/.socket.sock"),None),"nested Hyprland")
        os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = ipc.parent.name
        assert str(ipc).startswith(str(runtime) + "/hypr/")
        ctl("output","create","headless","eDP-1")
        until(lambda:any(m["name"]=="eDP-1" for m in json.loads(ctl("monitors","-j"))),"private output")
        os.environ["WAYLAND_DISPLAY"] = until(lambda:next((p for p in runtime.glob("wayland-*") if p.is_socket() and p != outer_socket),None),"nested Wayland socket").name
        ctl("keyword","monitor","eDP-1,960x640@60,0x0,1")
        for monitor in json.loads(ctl("monitors","-j")):
            if monitor["name"] != "eDP-1": ctl("keyword","monitor",monitor["name"]+",disable")
        ctl("dismissnotify","-1")
        ctl("dispatch","focusmonitor","eDP-1")
        ctl("dispatch","workspace","name:normal-browser")
        # Establish seat capabilities BEFORE browser/Qt startup, like real
        # hardware. Neither fixture emits a key or button at registration.
        pointer=subprocess.Popen([os.environ["TABLET_TEST_POINTER"]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,start_new_session=True)
        processes.append(pointer)
        assert until(lambda:select.select([pointer.stdout],[],[],.1)[0],"pointer readiness")
        assert pointer.stdout.readline().strip()=="READY"
        start(["wtype","-s","600000","-k","Shift_L"],"seat-keyboard")
        time.sleep(.2)
        wrapper = root / "test-vivaldi"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(os.environ["TABLET_TEST_VIVALDI_UNCONFIGURED"] if os.environ.get("TABLET_TEST_UNCONFIGURED") else os.environ["TABLET_TEST_VIVALDI"])
                          + " --user-data-dir=" + shlex.quote(str(root / "browser-profile"))
                          # The ordinary configured binary must provide its
                          # own native/IME flags; the fixture must not fake them.
                          + (' --ozone-platform=wayland' if os.environ.get('TABLET_TEST_UNCONFIGURED') else '')
                          + ' --no-first-run --no-default-browser-check --password-store=basic --disable-background-networking --disable-component-update --disable-sync'
                          + ' --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" "$@"\n')
        wrapper.chmod(0o700)
        normal_process=start([str(wrapper),"--new-window",url+"?normal"],"normal-browser")
        normal = until(lambda:next((c for c in clients() if c.get("class")=="vivaldi-stable"),None),"ordinary browser")
        normal_address = normal["address"]
        ctl("dispatch","workspace","name:tablet-trial")
        registry = json.loads(Path(os.environ["TABLET_TEST_REGISTRY"]).read_text())
        for app in registry:
            if app["kind"] == "window": app["command"]=[str(wrapper),*app["command"][1:]]
        (root / "apps.json").write_text(json.dumps(registry))
        ui_path = Path(os.environ["TABLET_TEST_UI"])
        sessions = root / "sessions"
        sessions.mkdir()
        (sessions / "draft.txt").write_text("Preserved fake draft")
        os.environ.update(TABLET_NATIVE_CHAT="1", TABLET_START_VIEW="home", TABLET_APPS_REGISTRY=str(root / "apps.json"),
                          TABLET_CHAT_SESSIONS=str(sessions), TABLET_CHAT_CWD=str(root), TABLET_CHAT_PROVIDER="fake", TABLET_CHAT_MODEL="fake",
                          TABLET_STAGE_SCREEN="eDP-1", TABLET_STAGE_QML=str(ui_path / "stage.qml"),
                          TABLET_ITERATION_QML=str(ui_path / "iteration.qml"), TABLET_UI_BACKEND="fixture", TABLET_FAKE_RPC_LOG=str(root / "fake-rpc.jsonl"))
        spec=importlib.util.spec_from_file_location("controller",os.environ["TABLET_TEST_CONTROLLER"])
        ui=importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)
        ui.binding=lambda: (trial.target,{})
        trial=ui.Trial(target={"instance":ipc.parent.name,"workspace":"tablet-trial"})
        # Limit /proc enumeration to this test-owned browser. The production
        # scanner is unit-tested separately; never probe host browser processes.
        trial.apps().browser_pids=lambda policy: {normal["pid"]} if normal_process.poll() is None else set()
        if os.environ.get("TABLET_TEST_UNCONFIGURED"):
            # Prove refusal also works without compositor-window discovery,
            # as for a warm background-only browser process.
            real_hypr=trial.apps().hypr
            trial.apps().hypr=lambda *args: [] if args == ("clients",) else real_hypr(*args)
        start([os.environ["TABLET_TEST_QS"],"--path",os.environ["TABLET_TEST_WALLPAPER"]],"desktop-fixture")
        time.sleep(.3)
        negative=start(["wf-recorder","--no-dmabuf","-D","-o","eDP-1","-r","30","-c","rawvideo","-x","rgb24","-m","nut","-f",str(root / "negative.nut")],"negative-recorder")
        time.sleep(.3);negative.send_signal(signal.SIGINT);assert negative.wait(timeout=15)==0
        detector=subprocess.run([sys.executable,os.environ["TABLET_FRAME_CHECKER"],str(root / "negative.nut"),str(root / "negative")],capture_output=True,text=True,cwd=root)
        (root / "negative-control.log").write_text(detector.stdout+detector.stderr)
        assert detector.returncode!=0 and "Work desktop visible" in detector.stderr,"desktop detector negative control failed"
        trial.start_stage(str(ui_path / "iteration.qml"))
        trial.wait_stage()
        recorder=start(["wf-recorder","--no-dmabuf","-D","-o","eDP-1","-r","30","-c","rawvideo","-x","rgb24","-m","nut","-f",str(root / "transitions.nut")],"recorder")
        subprocess.run(["gsettings","set","org.gnome.desktop.a11y.applications","screen-keyboard-enabled","true"],check=True)
        trial.keyboard=start(["squeekboard"],"keyboard")
        trial.agent=subprocess.Popen([os.environ["TABLET_TEST_QS"],"--path",str(ui_path / "agent.qml")],env=dict(os.environ,TABLET_DEFER_PI="1"),stdout=log,stderr=log)
        trial.shell=subprocess.Popen([os.environ["TABLET_TEST_QS"],"--path",str(ui_path / "iteration.qml")],stdout=log,stderr=log)
        trial.entry_pending=True; trial.entry_deadline=time.monotonic()+25; trial.journal()
        control=socket.socket(socket.AF_UNIX)
        control.bind(str(ui.directory()/"control.sock"));control.listen(8);control.settimeout(.05)
        def serve():
            try:
                while not stop.is_set():
                    try:
                        conn,_=control.accept()
                        with conn: ui.respond(trial,conn)
                    except socket.timeout: pass
                    trial.tick()
            except Exception as e: errors.append(e)
        worker=threading.Thread(target=serve,daemon=True);worker.start()
        def check(checker,message):
            def test():
                if errors: raise AssertionError(str(errors))
                return checker()
            return until(test,message)
        def settled():
            return not trial.entry_pending and not json.loads(trial.ipc(trial.stage,"tabletStage","status"))["covering"]
        def nav(method,*args):
            return trial.ipc(trial.shell,"testNavigation",method,*args).strip()
        def snapshot(name):
            assert str(ipc).startswith(str(runtime)+"/hypr/")
            image=Image.open(io.BytesIO(subprocess.check_output(["grim","-o","eDP-1","-"]))).convert("RGB")
            image.save(root / (name+".png"));return image
        def keys(*args):
            assert str(ipc).startswith(str(runtime)+"/hypr/")
            subprocess.run(["wtype","-d","15",*args],check=True,timeout=10)
        def pointer_command(command):
            nonlocal pointer
            assert str(ipc).startswith(str(runtime)+"/hypr/")
            monitors=json.loads(ctl("monitors","-j"))
            assert len(monitors)==1 and monitors[0]["name"]=="eDP-1"
            if pointer is None:
                pointer=subprocess.Popen([os.environ["TABLET_TEST_POINTER"]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,start_new_session=True)
                processes.append(pointer)
                assert until(lambda:select.select([pointer.stdout],[],[],.1)[0],"pointer readiness")
                assert pointer.stdout.readline().strip()=="READY"
            pointer.stdin.write(command+"\n");pointer.stdin.flush()
            assert until(lambda:select.select([pointer.stdout],[],[],.1)[0],"pointer command")
            assert pointer.stdout.readline().strip()=="OK"
        def move(x,y):
            monitor=json.loads(ctl("monitors","-j"))[0]
            pointer_command(f'move {x} {y} {monitor["width"]} {monitor["height"]}')
        def click(x,y):
            move(x,y);time.sleep(.1)
            move(x+1,y+1);time.sleep(.1)
            pointer_command("down");time.sleep(.1);pointer_command("up")
        def swipe(x,y,distance,hold=0):
            move(x,y);time.sleep(.1);move(x+1,y);time.sleep(.1)
            pointer_command("down")
            for offset in range(0,distance,-20):
                move(x,y+offset);time.sleep(.015)
            move(x,y+distance)
            time.sleep(hold)
            pointer_command("up")
        def keyboard_visible():
            result=subprocess.run(["gdbus","call","--session","--dest","sm.puri.OSK0","--object-path","/sm/puri/OSK0","--method","org.freedesktop.DBus.Properties.Get","sm.puri.OSK0","Visible"],check=True,capture_output=True,text=True,timeout=3).stdout
            return "<true>" in result
        check(lambda:not trial.entry_pending,"Home did not become ready")
        snapshot("home")
        nav("choose","browser")
        if os.environ.get("TABLET_TEST_UNCONFIGURED"):
            check(lambda:"Cannot verify native keyboard" in trial.error,"unverified browser was not refused")
            assert trial.view=="home" and not trial.entry_pending
            assert {c["address"] for c in clients()}=={normal_address},"unverified browser launch changed windows"
            assert next(c for c in clients() if c["address"]==normal_address)["workspace"]["name"]=="normal-browser"
            snapshot("refused-unconfigured-browser")
            print("PASS: ordinarily launched browser without verified IME flags is left untouched; no restart, new window, view switch or false keyboard-support claim",flush=True)
            return 0
        check(lambda:trial.view=="external" and not trial.entry_pending,"Vivaldi launch/real capture did not become ready")
        owned=trial.apps().owned("browser")
        assert owned and owned["address"]!=normal_address and owned["pid"]==normal["pid"],"not a new shared-process window"
        identity=(owned["address"],owned["pid"])
        original_tag=trial.apps().windows["browser"]["tag"]
        old_shell,old_agent=trial.shell.pid,trial.agent.pid
        assert next(c for c in clients() if c["address"]==normal_address)["workspace"]["name"]=="normal-browser"
        check(settled,"initial cover fade did not finish")
        snapshot("browser-start")
        keys("-M","ctrl","-k","l","-m","ctrl",url,"-k","Return")
        check(lambda:any(p=="/app" for p in requests),"browser URL navigation failed")
        check(lambda:"/guard" in requests,"test page script did not initialize")
        time.sleep(.4)
        check(settled,"URL/IME cover did not finish")
        # First acquire pointer focus with the newly registered virtual device,
        # then click again: neither bypasses hit testing or the native window.
        click(300,300);time.sleep(.2)
        click(300,300)
        snapshot("after-click")
        (root / "pointer.json").write_text(ctl("cursorpos","-j"))
        (root / "layers.json").write_text(ctl("layers","-j"))
        try:
            until(lambda:any(p.startswith("/clicked-") for p in requests),"overlay intercepted browser content click",timeout=3)
        except AssertionError:
            click(20,52);time.sleep(.2);snapshot("menu-click")
            raise
        click(300,160)
        check(lambda:"/clicked-INPUT" in requests,"native input field click failed")
        check(keyboard_visible,"native Vivaldi input did not show Squeekboard")
        check(lambda:settled() and trial.external_ready and json.loads(nav("external"))["inset"]>0
              and trial.apps().owned("browser")["size"]==[960,400],"keyboard resize did not settle at the native minimum")
        snapshot("browser-keyboard")
        inset=json.loads(nav("external"))["inset"]
        swipe(480,610-inset,-90)
        check(lambda:trial.view=="home" and settled(),"Home from native text input failed")
        check(lambda:not keyboard_visible(),"keyboard remained visible over Home")
        parked=trial.apps().owned("browser")
        assert parked and parked["workspace"]["name"].startswith("special:tablet-app-"),"hidden browser retained workspace/input focus"
        nav("choose","browser")
        check(lambda:trial.view=="external" and settled(),"focused native app did not resume")
        assert trial.apps().owned("browser")["address"]==identity[0]
        click(300,240)
        check(lambda:not keyboard_visible(),"native input blur did not hide Squeekboard")
        check(lambda:settled() and trial.external_ready and json.loads(nav("external"))["inset"]==0,"keyboard geometry did not settle")
        time.sleep(.1)
        swipe(480,610,-150,.4)
        check(lambda:json.loads(nav("external"))["overview"],"native bottom-handle hold did not open switcher")
        check(lambda:not json.loads(nav("previews"))["capturing"],"native preview capture stuck")
        check(lambda:"browser" in json.loads(nav("previews"))["images"],"real window preview missing")
        snapshot("browser-switcher")
        nav("home")
        check(lambda:trial.view=="home" and not trial.entry_pending,"Home failed")
        nav("choose","browser")
        check(lambda:trial.view=="external" and not trial.entry_pending,"resume failed")
        check(settled,"resume cover did not finish")
        assert (trial.apps().owned("browser")["address"],trial.apps().owned("browser")["pid"])==identity
        assert trial.shell.pid==old_shell and trial.agent.pid==old_agent
        assert (sessions / "draft.txt").read_text()=="Preserved fake draft"
        # Browser close confirmation must remain usable, not be hidden by cards.
        guard["enabled"]=True; time.sleep(.3)
        click(300,300)
        nav("openOverview");check(lambda:not json.loads(nav("previews"))["capturing"],"preview stuck")
        swipe(480,350,-200)
        time.sleep(.8)
        assert trial.apps().owned("browser"),"beforeunload was bypassed"
        assert not json.loads(nav("external"))["overview"],"confirmation hidden behind switcher"
        snapshot("browser-close-confirmation")
        keys("-k","Escape")
        guard["enabled"]=False;time.sleep(.4)
        nav("dismiss","browser")
        check(lambda:trial.view=="home" and not trial.entry_pending,"close did not return Home")
        check(lambda:"browser" not in json.loads(nav("state"))["opened"],"closed card remained")
        assert any(c["address"]==normal_address and c["workspace"]["name"]=="normal-browser" for c in clients()),"ordinary browser was moved/closed"
        nav("choose","browser")
        check(lambda:trial.view=="external" and not trial.entry_pending,"reopen failed")
        assert trial.apps().windows["browser"]["tag"]!=original_tag  # Compositor addresses can legitimately be reused.
        assert trial.apps().owned("browser")["pid"]==normal["pid"]
        # Separate cold/first-window refusal case. Experiments proved normal
        # Vivaldi startup can restore extra session windows; this preview must
        # refuse it before launching anything or changing the user's profile.
        # Closing the ordinary window here is explicit private test setup.
        nav("dismiss","browser")
        check(lambda:trial.view=="home" and settled(),"pre-cold Home failed")
        ctl("dispatch","closewindow","address:"+normal_address)
        time.sleep(.3)
        if normal_process.poll() is None:
            # An initial-profile exit prompt may keep the fixture alive. This
            # process group was spawned here with disposable local-only data;
            # this is test setup, never an operation of the product controller.
            os.killpg(normal_process.pid,signal.SIGTERM);normal_process.wait(timeout=10)
        check(lambda:not any(str(c.get("class","")).lower().startswith("vivaldi") for c in clients()),"test browser windows did not close")
        nav("choose","browser")
        check(lambda:"cold startup" in trial.error,"cold process was not refused")
        assert trial.view=="home" and settled()
        assert not any(str(c.get("class","")).lower().startswith("vivaldi") for c in clients()),"cold refusal still started a browser"
        snapshot("browser-cold-refused")
        recorder.send_signal(signal.SIGINT);assert recorder.wait(timeout=15)==0
        subprocess.run([sys.executable,os.environ["TABLET_FRAME_CHECKER"],str(root / "transitions.nut"),str(root)],check=True,cwd=root)
        print("PASS: real shared-profile Vivaldi, exact ownership, native click-through/capture, real OSK show/hide, bottom/card gestures, retained preview, Home/resume, confirmation-aware close, unrelated browser preservation/reopen and safe cold-start refusal",flush=True)
        return 0
    finally:
        try:
            snapshot("final")
            (root / "requests.json").write_text(json.dumps(requests))
            (root / "final-clients.json").write_text(json.dumps(clients(),indent=2))
        except Exception: pass
        if trial:
            try:
                (root / "final-state.json").write_text(json.dumps({"status":trial.status(),"errors":[str(e) for e in errors],
                    "external":nav("external"),"ui":trial.ipc(trial.shell,"tabletUi","status")},indent=2))
            except Exception: pass
        stop.set()
        if recorder and recorder.poll() is None:
            recorder.send_signal(signal.SIGINT)
            try:recorder.wait(timeout=15)
            except subprocess.TimeoutExpired:recorder.kill();recorder.wait()
        if worker: worker.join(timeout=10)
        if trial:
            try: trial.cleanup()
            except Exception as e: print("cleanup:",e,file=sys.stderr)
            if trial.window_apps:
                # Test-owned cold browser processes only. Product cleanup never
                # signals these potentially shared application processes.
                for p in trial.window_apps.launchers:
                    if p.poll() is None:
                        p.terminate()
                        try:p.wait(timeout=5)
                        except subprocess.TimeoutExpired:p.kill();p.wait()
        server.shutdown()
        for p in reversed(processes):
            if p.poll() is None:
                try: os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError: pass
        for p in processes:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        log.close()
        cleanup_runtime(runtime)


if __name__=="__main__":
    raise SystemExit(inner() if os.environ.get("TABLET_WINDOW_TEST_ROOT") else outer())
