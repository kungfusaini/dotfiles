"""Focused real-Pegasus lifecycle proof on private Labwc → Hyprland only."""
import importlib.util
import io
import json
import os
import select
from pathlib import Path
import signal
import subprocess
import sys
import time
from PIL import Image

spec = importlib.util.spec_from_file_location('proof_driver', os.environ['TABLET_TEST_PROOF_DRIVER'])
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
until = driver.until


def inner():
    root = Path(os.environ['TABLET_WINDOW_TEST_ROOT'])
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    assert str(root).startswith('/tmp/twa.proof.') and runtime == root / 'r'
    processes = []
    ipc = None
    pointer = None
    os.environ['TABLET_TEST_ORIENTATION'] = str(root / 'orientation')
    (root / 'orientation').write_text('normal')
    fake = root / 'fake-bin'; fake.mkdir()
    for name, result in [('wpctl', 'Volume: 0.4'), ('brightnessctl', '100')]:
        path = fake / name; path.write_text('#!/bin/sh\necho "' + result + '"\n'); path.chmod(0o755)
    os.environ['TABLET_TEST_FAKE_BIN'] = str(fake)

    def start(command, name):
        with (root / (name + '.log')).open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        processes.append(process)
        return process

    def ctl(*args):
        return subprocess.check_output([os.environ['TABLET_TEST_HYPRCTL'], *args], text=True, timeout=5).strip()

    def clients():
        return json.loads(ctl('clients', '-j'))

    def proof(command):
        output = subprocess.check_output([os.environ['TABLET_PROOF_BIN'], command], text=True, timeout=40)
        return json.loads(output) if output.strip() else {}

    def status():
        return proof('status')

    def receipt():
        return json.loads((runtime / 'tablet-games/launch.json').read_text())

    def keys(key):
        assert ipc and str(ipc).startswith(str(runtime) + '/hypr/')
        subprocess.run(['wtype', '-k', key], check=True, timeout=5)

    def posture():
        return {key: json.loads(ctl('getoption', key, '-j'))['int'] for key in
                ('gestures:workspace_swipe_touch', 'input:follow_mouse')}

    def pointer_command(command):
        assert ipc and str(ipc).startswith(str(runtime) + '/hypr/')
        pointer.stdin.write(command + '\n'); pointer.stdin.flush()
        assert select.select([pointer.stdout], [], [], 5)[0]
        assert pointer.stdout.readline().strip() == 'OK'

    def swipe_home():
        pointer_command('move 480 610 960 640'); pointer_command('down')
        time.sleep(.04)
        for step in range(1, 9):
            pointer_command('move 480 ' + str(610 - step * 16) + ' 960 640')
            time.sleep(.018)
        pointer_command('up')

    def snapshot(name):
        assert ipc and str(ipc).startswith(str(runtime) + '/hypr/')
        image = Image.open(io.BytesIO(subprocess.check_output(['grim', '-o', 'eDP-1', '-']))).convert('RGB')
        image.save(root / (name + '.png'))
        return image

    try:
        (root / 'labwc').mkdir()
        start(['labwc', '-C', str(root / 'labwc')], 'labwc')
        outer = until(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None), 'private outer socket')
        os.environ['WAYLAND_DISPLAY'] = outer.name
        config = root / 'hyprland.conf'
        config.write_text('monitor=,960x640@60,auto,1\nxwayland {\n enabled=false\n}\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\ngestures {\n workspace_swipe_touch=true\n}\ninput {\n follow_mouse=1\n}\nlayerrule=match:namespace ^tablet-rotation-fade$, no_anim on\n')
        install = Path(os.environ['XDG_CONFIG_HOME']) / 'hypr'; install.mkdir(parents=True)
        (install / 'hyprland.conf').symlink_to(config)
        start([os.environ['TABLET_TEST_HYPRLAND'], '-c', str(config)], 'hyprland')
        ipc = until(lambda: next((runtime / 'hypr').glob('*/.socket.sock'), None), 'private inner socket')
        os.environ['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        os.environ['WAYLAND_DISPLAY'] = until(lambda: next((p.name for p in runtime.glob('wayland-*') if p.is_socket() and p != outer), None), 'private inner display')
        ctl('output', 'create', 'headless', 'eDP-1')
        ctl('keyword', 'monitor', 'eDP-1,960x640@60,0x0,1')
        for monitor in json.loads(ctl('monitors', '-j')):
            if monitor['name'] != 'eDP-1': ctl('keyword', 'monitor', monitor['name'] + ',disable')
        pointer = subprocess.Popen([os.environ['TABLET_TEST_POINTER']], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        processes.append(pointer)
        assert select.select([pointer.stdout], [], [], 5)[0]
        assert pointer.stdout.readline().strip() == 'READY'
        baseline = posture()
        assert all(value == 1 for value in baseline.values())
        ctl('dispatch', 'workspace', 'name:laptop-fixture')
        laptop = start(['quickshell', '--path', os.environ['TABLET_TEST_LAPTOP_QML']], 'laptop')
        laptop_window = until(lambda: next((c for c in clients() if c['pid'] == laptop.pid), None), 'private laptop window')
        ctl('dispatch', 'focuswindow', 'address:' + laptop_window['address'])
        games = root / 'games'; games.mkdir()
        game_ui = root / 'game.qml'
        game_ui.write_text('import Quickshell\nimport QtQuick\nShellRoot { FloatingWindow { visible: true; width: 480; height: 320; title: "Tablet fixture game"; color: "#15b94d"; onClosed: Qt.quit() } }\n')
        import shlex
        launch = [sys.executable, os.environ['TABLET_GAMING_SOURCE'], '--', 'sh', '-c', 'sleep 3; exec ' + shlex.join(['quickshell', '--path', str(game_ui)])]
        fail = [sys.executable, os.environ['TABLET_GAMING_SOURCE'], '--', '/definitely-missing-tablet-test-game']
        for name in ('play', 'fail'): (games / (name + '.rom')).touch()
        (games / 'metadata.pegasus.txt').write_text('collection: Tablet fixture\n\ngame: 01 Play\nfile: play.rom\nlaunch: ' + shlex.join(launch) + '\n\ngame: 02 Fail\nfile: fail.rom\nlaunch: ' + shlex.join(fail) + '\n')
        config_dir = Path(os.environ['XDG_CONFIG_HOME']) / 'pegasus-frontend'
        theme = config_dir / 'themes/tablet-fixture'; theme.mkdir(parents=True)
        (theme / 'theme.cfg').write_text('name: Tablet fixture\nauthor: Private test\nversion: 1\n')
        (theme / 'theme.qml').write_text('''import QtQuick 2.15
FocusScope {
    Rectangle { anchors.fill: parent; color: tabletLaunchActive ? "#245ac7" : "#253b68" }
    Text { anchors.centerIn: parent; color: "white"; text: tabletLaunchActive ? "Launching game…" : "Tablet library" }
    Keys.onPressed: event => {
        if (tabletLaunchActive) { event.accepted = true; return }
        if (event.key === Qt.Key_1 || event.key === Qt.Key_2) {
            event.accepted = true
            api.allGames.get(event.key === Qt.Key_1 ? 0 : 1).launch()
        }
    }
}
''')
        (config_dir / 'game_dirs.txt').write_text(str(games) + '\n')
        (config_dir / 'settings.txt').write_text('general.fullscreen: true\nproviders.steam.enabled: false\ngeneral.theme: themes/tablet-fixture/\n')
        ctl('keyword', 'windowrule', 'match:title ^Tablet fixture game$, float on')
        proof('start'); proof('games')
        until(lambda: status()['pegasusRunning'] and not status()['home'], 'tablet Pegasus view')
        assert all(value == 0 for value in posture().values()), 'tablet interaction lease missing'
        first_backend = status()['backend']['pid']
        library = next(c for c in clients() if c['class'].startswith(('pegasus-fe', 'org.pegasus-frontend')))
        time.sleep(.5)
        assert snapshot('library').getpixel((40, 40)) == (37, 59, 104)
        keys('1')
        until(lambda: status()['gameLaunching'], 'Pegasus owns delayed launch')
        for sample in range(2):
            assert status()['pegasusRunning'] and not status()['home']
            assert any(c['address'] == library['address'] and c['mapped'] for c in clients())
            pixel = snapshot('loading-' + str(sample)).getpixel((40, 40))
            assert pixel == (36, 90, 199) or (pixel == (21, 185, 77) and status()['gameRunning']), 'neither Pegasus loading nor the verified game'
            time.sleep(.35)
        until(lambda: status()['gameRunning'] and not status()['home'] and json.loads(ctl('activewindow', '-j')).get('title') == 'Tablet fixture game', 'verified floating game handoff')
        game = next(c for c in clients() if c.get('title') == 'Tablet fixture game')
        until(lambda: next(c for c in clients() if c['address'] == game['address'])['size'] == [960, 640], 'screen-filling floating game')
        assert snapshot('game').getpixel((40, 40)) == (21, 185, 77)
        intruder_ui = root / 'foreign-focus.qml'
        intruder_ui.write_text('import Quickshell\nimport QtQuick\nShellRoot { FloatingWindow { visible: true; width: 200; height: 150; title: "Foreign focus fixture"; color: "#555555"; onClosed: Qt.quit() } }\n')
        ctl('keyword', 'windowrule', 'match:title ^Foreign focus fixture$, float on')
        intruder_process = start(['quickshell', '--path', str(intruder_ui)], 'foreign-focus')
        intruder = until(lambda: next((c for c in clients() if c['pid'] == intruder_process.pid), None), 'foreign same-workspace focus fixture')
        ctl('dispatch', 'focuswindow', 'address:' + intruder['address'])
        time.sleep(6)  # Cross the former fatal focus-loss timeout.
        assert status()['running'] and status()['backend']['pid'] == first_backend
        assert json.loads(ctl('activewindow', '-j'))['pid'] == intruder_process.pid, 'unrelated focus reclaimed'
        assert all(value == 0 for value in posture().values())
        ctl('dispatch', 'closewindow', 'address:' + intruder['address'])
        until(lambda: json.loads(ctl('activewindow', '-j')).get('address') == game['address'], 'verified game focus resumes')
        proof('close')
        assert posture() == baseline, 'desktop gesture/focus baseline not restored on unfold'
        restored = next(c for c in clients() if c['address'] == game['address'])
        assert restored['floating'] and restored['fullscreen'] == 0 and restored['size'] == [480, 320], restored
        assert json.loads(ctl('activewindow', '-j'))['address'] == laptop_window['address']
        proof('start')
        returned_backend = status()['backend']['pid']
        assert all(value == 0 for value in posture().values())
        until(lambda: status()['gameRunning'] and json.loads(ctl('activewindow', '-j')).get('address') == game['address'], 'game resumes on fold')
        ctl('dispatch', 'closewindow', 'address:' + game['address'])
        until(lambda: status()['pegasusRunning'] and not status()['gameRunning'] and json.loads(ctl('activewindow', '-j')).get('pid') == library['pid'], 'same library returns after game')
        assert status()['backend']['pid'] == returned_backend, 'game exit destroyed tablet navigation'
        swipe_home()
        until(lambda: status()['home'], 'bottom swipe works after returning from game to Pegasus')
        assert status()['backend']['pid'] == returned_backend
        proof('games')
        until(lambda: status()['pegasusRunning'] and not status()['home'], 'Pegasus resumes from tablet Home')
        keys('2')
        until(lambda: receipt().get('phase') == 'done' and receipt().get('code') == 1, 'failed child receipt completes', timeout=35)
        caller = receipt()['caller']['pid']
        until(lambda: not (Path('/proc') / str(caller)).exists(), 'failed wrapper returned to Pegasus', timeout=30)
        time.sleep(.3)
        keys('Return')
        assert status()['pegasusRunning'] and not status()['home']
        keys('1')
        until(lambda: status()['gameRunning'] and json.loads(ctl('activewindow', '-j')).get('title') == 'Tablet fixture game', 'failed launch does not lock retry', timeout=40)
        retry = next(c for c in clients() if c.get('title') == 'Tablet fixture game')
        ctl('dispatch', 'closewindow', 'address:' + retry['address'])
        until(lambda: status()['pegasusRunning'] and not status()['gameRunning'], 'retry returns to Pegasus')
        proof('close')
        assert posture() == baseline, 'desktop input settings changed after final exit'
        assert not (runtime / 'tablet-proof/recovery.json').exists()
        assert json.loads(ctl('activewindow', '-j'))['address'] == laptop_window['address']
        proof('start')
        assert all(value == 0 for value in posture().values())
        backend = status()['backend']['pid']
        descriptor = os.pidfd_open(backend)
        try: signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        finally: os.close(descriptor)
        until(lambda: not status().get('running') and not status().get('recovery'), 'crashed controller recovers interaction ownership', timeout=35)
        assert posture() == baseline, 'crash recovery did not restore desktop input policy'
        assert json.loads(ctl('activewindow', '-j'))['address'] == laptop_window['address']
        print('PASS: retained Pegasus loading, no Home fallback, floating fullscreen/release, unfold survival/resume, library return, failed launch and retry; reversible interaction isolation, no foreign-focus reclaim, bottom swipe after game return, crash restoration', flush=True)
    finally:
        if ipc:
            try:
                (root / 'last-clients.json').write_text(json.dumps(clients(), indent=2))
                (root / 'last-status.json').write_text(json.dumps(status(), indent=2))
                snapshot('last-frame')
                if status().get('running'): proof('close')
            except Exception as error: print('Private cleanup:', error, file=sys.stderr)
        for process in reversed(processes):
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
        for process in processes:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
        spec = importlib.util.spec_from_file_location('cleanup', os.environ['TABLET_TEST_CLEANUP'])
        cleanup = importlib.util.module_from_spec(spec); spec.loader.exec_module(cleanup)
        cleanup.cleanup_runtime(runtime)


if __name__ == '__main__':
    raise SystemExit(inner() if os.environ.get('TABLET_WINDOW_TEST_ROOT') else driver.outer(__file__))
