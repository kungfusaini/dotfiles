#!/usr/bin/env python3
"""Real isolated compositor test with a fake Steam client; no account/game access."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

from workspace_exec_integration import wait_for

FAKE_CLIENT = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
static int has(const char *root, const char *name) {
    char p[4096]; snprintf(p,sizeof(p),"%s/%s",root,name); return access(p,F_OK)==0;
}
static void touch(const char *root,const char *name) {
    char p[4096]; snprintf(p,sizeof(p),"%s/%s",root,name); FILE *f=fopen(p,"w"); if(f)fclose(f);
}
static void window(const char *klass,int game) {
    if(fork()==0) {
        if(game) {setenv("SteamAppId","1687950",1); setenv("SteamGameId","1687950",1);}
        execl(getenv("STEAM_TEST_KITTY"),"kitty","--class",klass,"--title",klass,
              "sh","-c","sleep 120",(char*)0); _exit(1);
    }
}
int main(int argc,char **argv) {
    const char *root=getenv("STEAM_TEST_ROOT"); if(!root)return 2;
    if(argc==2 && strcmp(argv[1],"steam://rungameid/1687950")==0) {touch(root,"show-game");return 0;}
    if(argc!=2 || strcmp(argv[1],"-silent")!=0)return 3;
    int ui=0,game=0; touch(root,"backend-running");
    while(!has(root,"stop")) {
        if(!ui && has(root,"show-client")){window("steam",0);ui=1;}
        if(!game && has(root,"show-game")){window("steam-fake-game",1);game=1;}
        usleep(50000);
    }
    return 0;
}
'''


def worker(root, helper, client):
    root = Path(root)
    for label, argument in [('background', '-silent'), ('game', 'steam://rungameid/1687950')]:
        wait_for(lambda: (root / ('go-' + label)).exists(), timeout=90)
        result = subprocess.run([helper, client, argument], capture_output=True, text=True)
        (root / (label + '-result.json')).write_text(json.dumps(dict(code=result.returncode,
                                                       stdout=result.stdout, stderr=result.stderr)))
    wait_for(lambda: (root / 'done').exists(), timeout=90)


def run(args):
    root = Path(tempfile.mkdtemp(prefix='steam-wex.'))
    runtime = root / 'r'
    runtime.mkdir(mode=0o700)
    (root / 'home').mkdir()
    (root / 'labwc').mkdir()
    binary = root / 'ubuntu12_32/steam'
    binary.parent.mkdir()
    (root / 'client.c').write_text(FAKE_CLIENT)
    subprocess.run([args.cc, '-O2', str(root / 'client.c'), '-o', str(binary)], check=True)
    env = {**os.environ, 'HOME': str(root / 'home'), 'XDG_RUNTIME_DIR': str(runtime),
           'XDG_CONFIG_HOME': str(root / 'home/.config'), 'XDG_CONFIG_DIRS': str(root / 'empty'),
           'WLR_BACKENDS': 'headless', 'WLR_HEADLESS_OUTPUTS': '1', 'WLR_RENDERER': 'gles2',
           'WLR_RENDER_DRM_DEVICE': args.render_node, 'WLR_LIBINPUT_NO_DEVICES': '1',
           'XDG_SESSION_TYPE': 'wayland', 'XDG_CURRENT_DESKTOP': 'Hyprland',
           'STEAM_TEST_ROOT': str(root), 'STEAM_TEST_KITTY': args.kitty,
           'PROJECT_PICKER_HYPRCTL': args.hyprctl}
    for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'HYPRLAND_INSTANCE_SIGNATURE',
                'PROJECT_OBJECT_WORKSPACE_NAME', 'PROJECT_OBJECT_LAUNCH_ID',
                'HL_INITIAL_WORKSPACE_TOKEN', 'HL_EXEC_RULE_TOKEN']:
        env.pop(key, None)
    processes, events = [], []
    event_ready = threading.Event()

    def record(path):
        with socket.socket(socket.AF_UNIX) as connection, (root / 'events.log').open('w', buffering=1) as log:
            connection.connect(str(path))
            event_ready.set()
            with connection.makefile() as source:
                for line in source:
                    events.append(line.rstrip())
                    log.write(line)

    def start(command, name):
        with (root / (name + '.log')).open('w') as log:
            p = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(p)

    def ctl(*cmd):
        return subprocess.check_output([args.hyprctl, *cmd], env=env, text=True, timeout=5)

    def clients():
        return json.loads(ctl('clients', '-j'))

    try:
        start([args.labwc, '-C', str(root / 'labwc')], 'labwc')
        outer = wait_for(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None))
        env['WAYLAND_DISPLAY'] = outer.name
        config = root / 'config.conf'
        config.write_text('monitor=,960x640@60,auto,1\nxwayland {\n enabled=false\n}\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\n'
                          'windowrule = match:class ^([Ss]team)$, workspace special:steam-hidden silent\n'
                          'windowrule = match:class ^([Ss]team)$, no_initial_focus on\n'
                          'windowrule = match:class ^([Ss]team)$, suppress_event activate activatefocus\n')
        start([args.hyprland, '-c', str(config)], 'hyprland')
        ipc = wait_for(lambda: next((runtime / 'hypr').glob('*/.socket.sock'), None))
        env['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        errors = json.loads(ctl('configerrors', '-j'))
        assert all(not error.strip() for error in errors), errors
        threading.Thread(target=record, args=(ipc.parent / '.socket2.sock',), daemon=True).start()
        assert event_ready.wait(5)
        assert ctl('output', 'create', 'headless', 'TEST').strip() == 'ok'
        env['WAYLAND_DISPLAY'] = wait_for(lambda: next((p for p in runtime.glob('wayland-*')
                                                       if p.is_socket() and p != outer), None)).name
        assert ctl('dispatch', 'workspace', 'name:Invoking library').strip() == 'ok'
        # The helper forwards only identity context, so test fixture variables are
        # supplied in the fake executable's parent compositor environment above.
        command = [args.kitty, '--class', 'steam-invoker', sys.executable, str(Path(__file__).resolve()),
                   '--worker', str(root), str(Path(args.helper).resolve()), str(binary)]
        assert ctl('dispatch', 'exec', shlex.join(command)).strip() == 'ok'
        wait_for(lambda: any(c['class'] == 'steam-invoker' for c in clients()))
        assert ctl('dispatch', 'workspace', 'name:Unrelated active workspace').strip() == 'ok'
        (root / 'go-background').touch()
        wait_for(lambda: (root / 'background-result.json').exists())
        result = json.loads((root / 'background-result.json').read_text())
        assert result['code'] == 0, result
        assert (root / 'backend-running').exists()
        assert not any(c['class'] == 'steam' for c in clients()), 'tray-only startup unexpectedly mapped a window'
        print('PASS: marked tray-only process verified without a mapped window', flush=True)
        (root / 'show-client').touch()
        client = wait_for(lambda: next((c for c in clients() if c['class'] == 'steam'), None))
        assert client['workspace']['name'] == 'special:steam-hidden', client
        assert json.loads(ctl('activeworkspace', '-j'))['name'] == 'Unrelated active workspace'
        print('PASS: delayed Steam UI starts hidden without stealing focus', flush=True)
        (root / 'go-game').touch()
        wait_for(lambda: (root / 'game-result.json').exists(), timeout=30)
        result = json.loads((root / 'game-result.json').read_text())
        assert result['code'] == 0, result
        game = wait_for(lambda: next((c for c in clients() if c['class'] == 'steam-fake-game'), None))
        assert game['workspace']['name'] == 'Invoking library', game
        assert json.loads(ctl('activeworkspace', '-j'))['name'] == 'Unrelated active workspace'
        assert json.loads(ctl('activewindow', '-j')) == {}, 'game routing stole focus'
        assert next(c for c in clients() if c['address'] == client['address'])['workspace']['name'] == 'special:steam-hidden'
        opened = [e.split('>>', 1)[1].split(',', 3) for e in events if e.startswith('openwindow>>')]
        assert all(e[1] == 'special:steam-hidden' for e in opened if len(e) == 4 and e[2] == 'steam')
        assert not any(e.startswith('activewindow>>steam,') for e in events)
        print('PASS: exact app-ID game window routed to invoking library; Steam UI remains hidden', flush=True)
        (root / 'done').touch()
    finally:
        (root / 'stop').touch()
        # Only synthetic processes in this private compositor/runtime can be touched.
        marker = ('XDG_RUNTIME_DIR=' + str(runtime)).encode()
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                if marker in (proc / 'environ').read_bytes().split(b'\0'):
                    os.kill(int(proc.name), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        for p in reversed(processes):
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print('Isolated test process needs attention: ' + str(p.pid), file=sys.stderr)
        print('Private logs retained at ' + str(root), flush=True)


def main():
    if sys.argv[1:2] == ['--worker']:
        worker(*sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['hyprland', 'hyprctl', 'labwc', 'kitty', 'cc']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--render-node', default='/dev/dri/renderD128')
    parser.add_argument('--helper', default=str(Path(__file__).resolve().parents[1] / 'bin/project-workspace-exec'))
    args = parser.parse_args()
    if os.environ.get('STEAM_WORKSPACE_PRIVATE_BUS') != '1':
        env = dict(os.environ, STEAM_WORKSPACE_PRIVATE_BUS='1')
        env.pop('DBUS_SESSION_BUS_ADDRESS', None)
        root = Path(tempfile.mkdtemp(prefix='steam-wex-bus.'))
        cfg = root / 'bus.conf'
        cfg.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
        result = subprocess.run(['dbus-run-session', '--config-file=' + str(cfg), '--',
                                 sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
        raise SystemExit(result.returncode)
    run(args)


if __name__ == '__main__':
    main()
