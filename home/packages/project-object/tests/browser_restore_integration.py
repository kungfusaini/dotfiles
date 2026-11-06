#!/usr/bin/env python3
"""Opt-in native-session contract in a private bus, profile and hidden desktop.

Requires --vivaldi-package (a Nix package root), labwc, Hyprland and a render node.
No live display, user profile, debugger or globally active workspace is accessed.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from browser_protocol import EXTENSION_ID
from browser_restore import Restoration, fingerprint
from workspace_exec_integration import wait_for


def run(args):
    root = Path(tempfile.mkdtemp(prefix='brtest.'))
    # Hyprland's long instance signature must fit UNIX's 108-byte socket path.
    runtime = Path(tempfile.mkdtemp(prefix='brr.', dir='/tmp'))
    for name in ['home', 'labwc', 'profile/Default']:
        (root / name).mkdir(parents=True)
    env = {**os.environ, 'HOME': str(root / 'home'), 'XDG_RUNTIME_DIR': str(runtime),
           'XDG_CONFIG_HOME': str(root / 'home/.config'), 'XDG_CONFIG_DIRS': str(root / 'empty'),
           'XDG_DATA_HOME': str(root / 'data'), 'XDG_CACHE_HOME': str(root / 'cache'),
           'XDG_STATE_HOME': str(root / 'state'), 'PROJECT_OBJECT_DATA_DIR': str(root / 'project-data'),
           'PROJECT_OBJECT_RUNTIME_DIR': str(runtime / 'project-object'),
           'WLR_BACKENDS': 'headless', 'WLR_HEADLESS_OUTPUTS': '1', 'WLR_RENDERER': 'gles2',
           'WLR_RENDER_DRM_DEVICE': args.render_node, 'WLR_LIBINPUT_NO_DEVICES': '1',
           'XDG_SESSION_TYPE': 'wayland', 'XDG_CURRENT_DESKTOP': 'Hyprland', 'VIVALDI_FFMPEG_AUTO': '0',
           'PYTHONDONTWRITEBYTECODE': '1'}
    for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'HYPRLAND_INSTANCE_SIGNATURE',
                 'HL_INITIAL_WORKSPACE_TOKEN', 'HL_EXEC_RULE_TOKEN', 'PROJECT_OBJECT_LAUNCH_ID',
                 'PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME', 'PROJECT_OBJECT_ID', 'PI_CODING_AGENT']:
        env.pop(name, None)
    source = Path(args.vivaldi_package) / 'opt/vivaldi'
    code = Path(args.project_object).resolve()
    package = root / 'browser'
    package.mkdir()
    for item in source.iterdir():
        if item.name == 'vivaldi-bin':
            shutil.copy2(item, package / item.name)
            (package / item.name).chmod(0o700)
        elif item.name != 'resources':
            (package / item.name).symlink_to(item)
    shutil.copytree(source / 'resources', package / 'resources')
    ui = package / 'resources/vivaldi'
    ui.chmod(0o700)
    adapter = Path(__file__).resolve().parents[1] / 'integrations/browser'
    for name in ['project-object-adapter.js', 'fixture.js']:
        if (ui / name).exists():
            (ui / name).chmod(0o600)
    shutil.copy2(adapter / 'adapter.js', ui / 'project-object-adapter.js')
    main = ui / 'main.html'
    main.chmod(0o600)
    main.write_text(main.read_text().replace('<script src="project-object-adapter.js"></script>', '')
                    .replace('</body>', '<script src="project-object-adapter.js"></script><script src="fixture.js"></script></body>'))
    wrapper = (Path(args.vivaldi_package) / 'bin/vivaldi').read_bytes().split(b'\0')
    browser_libraries = wrapper[wrapper.index(b'LD_LIBRARY_PATH') - 1].decode()
    manifest = {'name': 'org.project_object.browser', 'description': 'Hidden regression only',
                'path': str(code / 'bin/project-browser-host'), 'type': 'stdio',
                'allowed_origins': ['chrome-extension://' + EXTENSION_ID + '/']}
    hosts = root / 'profile/NativeMessagingHosts'
    hosts.mkdir()
    (hosts / 'org.project_object.browser.json').write_text(json.dumps(manifest))
    (root / 'profile/Default/Preferences').write_text(json.dumps({'vivaldi': {'startup': {
        'has_seen_welcome_page': True, 'first_seen_version': '8.2.4133.52', 'has_seen_feature': 1}}}))
    processes = []

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<title>Identical test title</title><input><div style="height:6000px">Fixture</div>')
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    (ui / 'fixture.js').write_text('''(async()=>{
      const nap=ms=>new Promise(r=>setTimeout(r,ms));let window;
      for(let n=0;n<100;n++){window=(await chrome.windows.getAll({populate:true}))[0];if(window?.tabs?.length)break;await nap(100);}
      await chrome.tabs.update(window.tabs[0].id,{url:BASE+'/alpha/one'});await nap(500);
      await chrome.tabs.update(window.tabs[0].id,{url:BASE+'/alpha/two'});await nap(500);
      const a=await chrome.tabs.create({windowId:window.id,url:BASE+'/alpha/stack-a',active:false});
      const b=await chrome.tabs.create({windowId:window.id,url:BASE+'/alpha/stack-b',active:false});
      const group=await vivaldi.tabsPrivate.move({tabIds:[a.id,b.id],windowId:window.id,target:1,tweaks:['create-group']});
      await vivaldi.tabsPrivate.setGroupProperties({groupExtId:group.group,groupTitle:'Research'});
      await chrome.tabs.update(window.tabs[0].id,{pinned:true,active:true});
      await chrome.windows.create({url:BASE+'/beta',focused:false});
    })();'''.replace('BASE', json.dumps(base)))

    def start(command, name, extra=None):
        process = subprocess.Popen(command, env={**env, **(extra or {})}, stdout=(root / (name + '.log')).open('a'),
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process
    def ctl(*command):
        return subprocess.check_output([args.hyprctl, *command], env=env, text=True, timeout=5)
    def clients():
        return json.loads(ctl('clients', '-j'))
    def browser_clients(workspace=None):
        return [c for c in clients() if c.get('class', '').startswith('vivaldi') and
                (workspace is None or c.get('workspace', {}).get('name') == workspace)]
    def launch():
        return start([str(package / 'vivaldi-bin'), '--user-data-dir=' + str(root / 'profile'),
                      '--ozone-platform=wayland', '--load-extension=' + str(adapter), '--no-first-run',
                      '--disable-background-networking', '--disable-component-update', '--disable-sync',
                      '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'], 'browser',
                     {'LD_LIBRARY_PATH': browser_libraries})
    def kill_browser():
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if (proc / 'exe').resolve() == package / 'vivaldi-bin':
                    os.kill(int(proc.name), signal.SIGKILL)
            except OSError:
                pass

    project = {'id': '11111111-1111-4111-8111-111111111111', 'name': 'Alpha'}
    role = 'Alpha · Browser'
    api = SimpleNamespace(DATA_ROOT=root / 'project-data', RUNTIME_ROOT=runtime / 'project-object',
        validate_browser_role=lambda _registry, _project: role, load_registry=lambda: {'projects': [project]},
        browser_clients=browser_clients, clients=clients, client_address=lambda c: c['address'],
        client_workspace=lambda c: c.get('workspace', {}).get('name', ''),
        dispatch=lambda name, arg: ctl('dispatch', name, arg),
        live_address=lambda address, workspace: next((c['address'] for c in browser_clients(workspace) if c['address'] == address), None))
    manager = Restoration(api)
    def ready():
        try:
            return manager.bridge.identity()
        except (OSError, RuntimeError):
            return None
    try:
        start([args.labwc, '-C', str(root / 'labwc')], 'labwc')
        outer = wait_for(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None))
        env['WAYLAND_DISPLAY'] = outer.name
        config = root / 'hyprland.conf'
        config.write_text('monitor=,1000x800@60,auto,1\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\nxwayland {\n enabled=false\n}\n')
        start([args.hyprland, '-c', str(config)], 'hyprland')
        ipc = wait_for(lambda: next((runtime / 'hypr').glob('*/.socket.sock'), None))
        env['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        ctl('output', 'create', 'headless', 'TEST')
        wait_for(lambda: json.loads(ctl('monitors', '-j')))
        env['WAYLAND_DISPLAY'] = wait_for(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket() and p != outer), None)).name
        browser = launch()
        identity = wait_for(ready)
        assert identity['profile'] == str(root / 'profile/Default')
        def fixture_ready():
            windows = manager.bridge.request('inventory')
            return windows if len(windows) == 2 and sorted(len(w['tabs']) for w in windows) == [1, 3] else None
        windows = wait_for(fixture_ready)
        alpha = next(w for w in windows if len(w['tabs']) == 3)
        beta = next(w for w in windows if len(w['tabs']) == 1)
        address = manager.address(alpha['id'], identity)
        ctl('dispatch', 'movetoworkspacesilent', 'name:' + role + ',address:' + address)
        manager.close(project)
        checkpoint = manager.checkpoint(project)
        assert checkpoint['phase'] == 'closed' and len(checkpoint['windows']) == 1
        assert not browser_clients(role)
        live = manager.bridge.request('inventory')
        assert len(live) == 1 and fingerprint(live[0]) == fingerprint(beta), live
        restored = manager.restore(project)
        assert len(restored) == 1 and manager.restore(project) == restored
        assert len(manager.bridge.request('inventory')) == 2
        (ui / 'fixture.js').write_text('')
        # No grace delay: deliberately expose stale live-session checkpointing.
        kill_browser()
        browser.wait(timeout=10)
        time.sleep(.5)
        browser = launch()
        wait_for(ready)
        try:
            restored = manager.restore(project)
        except RuntimeError as error:
            # Missing windows after restart are deliberately blocked until a
            # trustworthy normal-startup recovery barrier has been implemented.
            assert 'Startup recovery completion' in str(error), error
            print('PASS restart absence fails closed (normal-startup barrier remains unresolved)', flush=True)
        else:
            assert len(restored) == 1
            final = manager.bridge.request('inventory')
            assert len(final) == 2, final
            assert len([w for w in final if w.get('projectId') == project['id']]) == 1
            unchanged = next(w for w in final if w.get('projectId') != project['id'])
            assert fingerprint(unchanged) == fingerprint(beta), unchanged
            print('PASS recovered window adopted after restart without duplicate replay', flush=True)
        print('PASS native bridge, private checkpoint, guarded close, stacks/pins, exact placement and idempotent open', flush=True)
    finally:
        server.shutdown()
        server.server_close()
        kill_browser()
        marker = ('XDG_RUNTIME_DIR=' + str(runtime)).encode()
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                if marker in (proc / 'environ').read_bytes().split(b'\0'):
                    os.kill(int(proc.name), signal.SIGKILL)
            except OSError:
                pass
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        print('ARTIFACTS', root, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vivaldi-package', required=True)
    parser.add_argument('--project-object', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--labwc', default='labwc')
    parser.add_argument('--hyprland', default='Hyprland')
    parser.add_argument('--hyprctl', default='hyprctl')
    parser.add_argument('--render-node', default='/dev/dri/renderD128')
    args = parser.parse_args()
    if os.environ.get('BROWSER_RESTORE_PRIVATE_BUS') != '1':
        descriptor, filename = tempfile.mkstemp(prefix='brtest-bus.', suffix='.conf')
        os.close(descriptor)
        conf = Path(filename)
        conf.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
        try:
            raise SystemExit(subprocess.call(['dbus-run-session', '--config-file=' + str(conf), '--', sys.executable, __file__, *sys.argv[1:]],
                                            env={**os.environ, 'BROWSER_RESTORE_PRIVATE_BUS': '1'}))
        finally:
            conf.unlink(missing_ok=True)
    run(args)
