#!/usr/bin/env python3
"""Opt-in real Pegasus launch test inside private, headless compositors.

No Steam, accounts, saves, live desktop input, or visible windows are used.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def wait_for(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError("Timed out waiting for isolated test")


def probe(package, output):
    # Give Pegasus time to perform its normal immediate teardown. Nothing is
    # launched: exercise only the installed session's read-only workspace lookup.
    time.sleep(.3)
    sys.path.insert(0, str(Path(package) / 'libexec/steam-session'))
    import session
    try:
        result = {'workspace': session.invoking_workspace()}
    except Exception as exc:
        result = {'error': str(exc)}
    Path(output).write_text(json.dumps(result))
    time.sleep(1)


def run(args):
    root = Path(tempfile.mkdtemp(prefix='pgl.'))
    runtime = root / 'r'
    runtime.mkdir(mode=0o700)
    (root / 'labwc').mkdir()
    env = dict(os.environ, HOME=str(root / 'home'), XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(root / 'home/.config'), XDG_DATA_HOME=str(root / 'home/.local/share'),
               XDG_CACHE_HOME=str(root / 'home/.cache'), XDG_STATE_HOME=str(root / 'home/.local/state'),
               XDG_CONFIG_DIRS=str(root / 'empty'), WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
               WLR_RENDERER='gles2', WLR_LIBINPUT_NO_DEVICES='1', XDG_SESSION_TYPE='wayland',
               QT_QPA_PLATFORM='wayland', QT_QUICK_BACKEND='software')
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'HYPRLAND_INSTANCE_SIGNATURE',
                'PROJECT_OBJECT_WORKSPACE_NAME', 'PROJECT_OBJECT_LAUNCH_ID',
                'HL_INITIAL_WORKSPACE_TOKEN', 'HL_EXEC_RULE_TOKEN'):
        env.pop(key, None)
    processes = []

    def start(command, name):
        with (root / (name + '.log')).open('w') as log:
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        processes.append(process)
        return process

    def ctl(*command):
        return subprocess.check_output([args.hyprctl, *command], env=env, text=True, timeout=5)

    try:
        start([args.labwc, '-C', str(root / 'labwc')], 'labwc')
        outer = wait_for(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None))
        env['WAYLAND_DISPLAY'] = outer.name
        config = root / 'hyprland.conf'
        config.write_text('monitor=,960x640@60,auto,1\nxwayland {\n enabled=false\n}\n'
                          'misc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\n')
        start([args.hyprland, '-c', str(config)], 'hyprland')
        ipc = wait_for(lambda: next((runtime / 'hypr').glob('*/.socket.sock'), None))
        env['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        assert ctl('output', 'create', 'headless', 'TEST').strip() == 'ok'
        env['WAYLAND_DISPLAY'] = wait_for(lambda: next((p for p in runtime.glob('wayland-*')
                                                       if p.is_socket() and p != outer), None)).name
        assert ctl('dispatch', 'workspace', 'name:Isolated game library').strip() == 'ok'
        config_home = Path(env['XDG_CONFIG_HOME']) / 'pegasus-frontend'
        theme = config_home / 'themes/probe'
        theme.mkdir(parents=True)
        (theme / 'theme.cfg').write_text('name: Launch probe\nauthor: Test\n')
        (theme / 'theme.qml').write_text('import QtQuick 2.15\nFocusScope {\n'
            ' Timer { interval: 1000; running: true; onTriggered: api.allGames.get(0).launch() }\n}\n')
        metadata = config_home / 'metafiles'
        metadata.mkdir()
        game = root / 'dummy-game'
        game.touch()
        for label in ('default', 'pre-launch-hook'):
            result_path = root / (label + '.json')
            (config_home / 'settings.txt').write_text(
                'general.theme: themes/probe/\nproviders.steam.enabled: false\n')
            if label == 'pre-launch-hook':
                hook = config_home / 'scripts/game-start/steam-workspace'
                hook.parent.mkdir(parents=True)
                hook.write_text('#!/bin/sh\nexec "' + str(Path(args.package) / 'bin/steam-session') +
                                '" --capture-workspace\n')
                hook.chmod(0o700)
            (metadata / 'probe.metadata.pegasus.txt').write_text(
                'collection: Probe\ngame: Probe\nfile: ' + str(game) + '\nlaunch: ' +
                ' '.join('"' + str(p) + '"' for p in [sys.executable, Path(__file__).resolve(),
                         '--probe', args.package, result_path]) + '\n')
            process = start([args.pegasus], label)
            wait_for(result_path.exists)
            result = json.loads(result_path.read_text())
            if label == 'default':
                assert 'Cannot safely identify the invoking workspace' in result.get('error', ''), result
            else:
                assert result == {'workspace': 'Isolated game library'}, result
            print(f'PASS {label}: {result}', flush=True)
            process.terminate()
            process.wait(timeout=10)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
        print('Private logs retained at ' + str(root), flush=True)


def main():
    if sys.argv[1:2] == ['--probe']:
        probe(*sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('hyprland', 'hyprctl', 'labwc', 'pegasus', 'package'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    if os.environ.get('PEGASUS_TEST_PRIVATE_BUS') != '1':
        env = dict(os.environ, PEGASUS_TEST_PRIVATE_BUS='1')
        env.pop('DBUS_SESSION_BUS_ADDRESS', None)
        bus_root = Path(tempfile.mkdtemp(prefix='pgl-bus.'))
        bus_config = bus_root / 'bus.conf'
        # No service auto-activation: portals must not touch shared user mounts.
        bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                              '<auth>EXTERNAL</auth><policy context="default">'
                              '<allow send_destination="*"/><allow receive_sender="*"/>'
                              '<allow own="*"/></policy></busconfig>')
        raise SystemExit(subprocess.call(['dbus-run-session', '--config-file=' + str(bus_config),
                                          '--', sys.executable, str(Path(__file__).resolve()),
                                          *sys.argv[1:]], env=env))
    run(args)


if __name__ == '__main__':
    main()
