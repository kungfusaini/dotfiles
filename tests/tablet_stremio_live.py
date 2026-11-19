"""Real Stremio + bottom navigation, on a private seat/profile/network only."""
import importlib.util
import io
import json
import os
from pathlib import Path
import select
import shlex
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
    assert Path(os.environ['HOME']) == root / 'home'
    processes = []
    ipc = None
    os.environ['TABLET_TEST_ORIENTATION'] = str(root / 'orientation')
    (root / 'orientation').write_text('normal')
    fake = root / 'fake-bin'; fake.mkdir()
    for name, result in [('wpctl', 'Volume: 0.4'), ('brightnessctl', '100')]:
        path = fake / name; path.write_text('#!/bin/sh\necho "' + result + '"\n'); path.chmod(0o755)
    os.environ['TABLET_TEST_FAKE_BIN'] = str(fake)
    page = root / 'stremio.html'
    page.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body style="background:#253b68;color:white"><h1>Private Stremio fixture</h1><input placeholder="Touch keyboard test"></body></html>')
    binary = root / 'stremio-fixture'
    binary.write_text('#!/bin/sh\nexec ' + shlex.join([os.environ['TABLET_TEST_STREMIO'], '--url', page.as_uri()]) + ' "$@" > ' + shlex.quote(str(root / 'stremio.log')) + ' 2>&1\n')
    binary.chmod(0o755)
    # The real compositor does not inherit the native wrapper's executable.
    # Keep that boundary clean: only the controller gets this fixture override.
    os.environ.pop('TABLET_STREMIO_BIN', None)

    def start(command, name):
        with (root / (name + '.log')).open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        processes.append(process)
        return process

    def ctl(*args):
        from hyprland_control import desktop_args, call
        executable = os.environ['TABLET_TEST_HYPRCTL']
        if args[:2] == ('keyword', 'monitor'):
            output, spec = args[2].split(',', 1)
            monitor = {'output': output}
            if spec == 'disable': monitor['disabled'] = True
            else:
                mode, position, scale = spec.split(',')
                monitor.update(mode=mode, position=position, scale=float(scale))
            args = ['eval', call('monitor', monitor) + ';hl.exec_scheduled_prop_refresh_immediately()']
        else: args = desktop_args(executable, args)
        result = subprocess.check_output([executable, *args], text=True, timeout=5).strip()
        if result.startswith('error:'): raise RuntimeError(result)
        return result

    def clients():
        return json.loads(ctl('clients', '-j'))

    def mark(name):
        with (root / 'interaction-timeline.jsonl').open('a') as log:
            log.write(json.dumps({'time': time.monotonic(), 'name': name}) + '\n')

    def proof(command, *args):
        output = subprocess.check_output([os.environ['TABLET_PROOF_BIN'], command, *args], text=True, timeout=40)
        return json.loads(output) if output.strip() else {}

    def status():
        return proof('status')

    def posture():
        values = {}
        for key in ('gestures:workspace_swipe_touch', 'input:follow_mouse'):
            reply = json.loads(ctl('getoption', key, '-j'))
            value = reply.get('int', reply.get('bool'))
            assert type(value) in (int, bool), reply
            values[key] = int(value)
        return values

    def pointer_command(command):
        assert ipc and str(ipc).startswith(str(runtime) + '/hypr/')
        pointer.stdin.write(command + '\n'); pointer.stdin.flush()
        assert select.select([pointer.stdout], [], [], 5)[0]
        assert pointer.stdout.readline().strip() == 'OK'

    def scene():
        return json.loads(subprocess.check_output(['quickshell', 'ipc', '--path', os.environ['TABLET_TEST_PROOF_QML'],
                           'call', 'tabletNativeScene', 'status'], text=True, timeout=5))

    def target(name):
        return json.loads(subprocess.check_output(['quickshell', 'ipc', '--path', os.environ['TABLET_TEST_PROOF_QML'],
                           'call', 'tabletNativeScene', 'targetRect', name], text=True, timeout=5))

    def tap(name):
        rect = until(lambda: target(name), name + ' available')
        pointer_command(f'move {rect["x"]+rect["width"]/2} {rect["y"]+rect["height"]/2} 960 640')
        pointer_command('down'); time.sleep(.08); pointer_command('up')
        mark('touch:' + name)

    def snapshot(name):
        image = Image.open(io.BytesIO(subprocess.check_output(['grim', '-o', 'eDP-1', '-']))).convert('RGB')
        image.save(root / (name + '.png')); return image

    def switcher():
        mark('stremio-preview:begin')
        pointer_command('move 480 639 960 640'); pointer_command('down')
        for step in range(1, 13):
            pointer_command(f'move 480 {639-step*12} 960 640'); time.sleep(.035)
        time.sleep(.7); pointer_command('up')
        until(lambda: scene()['overview'] and 'stremio' in scene()['previewImages'] and not scene()['capturing'], 'real Stremio preview')
        image = snapshot('stremio-switcher-preview')
        rect = target('appPreview-stremio'); assert rect
        crop = image.crop((int(rect['x']), int(rect['y']), int(rect['x']+rect['width']), int(rect['y']+rect['height'])))
        assert sum(max(abs(a-b) for a,b in zip(pixel, (37,59,104)))<6 for pixel in crop.get_flattened_data()) > 10000, 'Preview did not contain real WebKit fixture pixels'
        mark('stremio-preview:ready')

    def swipe_card_close():
        mark('stremio-normal-close:begin')
        rect = target('appCard-stremio'); assert rect
        x=rect['x']+rect['width']/2; y=rect['y']+rect['height']/2
        pointer_command(f'move {x} {y} 960 640'); pointer_command('down')
        for step in range(1,9):
            pointer_command(f'move {x} {max(0,y-step*28)} 960 640'); time.sleep(.035)
        pointer_command('up')
        until(lambda: status()['home'] and not status()['stremioRunning'], 'Stremio normal close/hide')
        snapshot('stremio-normal-close-home'); mark('stremio-normal-close:hidden')

    def swipe_home():
        pointer_command('move 480 639 960 640'); pointer_command('down')
        time.sleep(.04)
        for step in range(1, 9):
            pointer_command('move 480 ' + str(639 - step * 16) + ' 960 640')
            time.sleep(.018)
        pointer_command('up')

    try:
        (root / 'labwc').mkdir()
        start(['labwc', '-C', str(root / 'labwc')], 'labwc')
        outer = until(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None), 'private outer socket')
        os.environ['WAYLAND_DISPLAY'] = outer.name
        config = root / 'hyprland.lua'
        config.write_text('''hl.monitor({output="",mode="960x640@60",position="auto",scale=1})
hl.monitor({output="eDP-1",mode="960x640@60",position="0x0",scale=1})
hl.config({misc={disable_hyprland_logo=true,disable_splash_rendering=true},xwayland={enabled=false},gestures={workspace_swipe_touch=true},input={follow_mouse=1}})
hl.layer_rule({match={namespace="^tablet-native$"},no_anim=true})
hl.layer_rule({match={namespace="^tablet-rotation-fade$"},no_anim=true})
desktop_policy={no_animation={["tablet-rotation-fade"]=true}}
''')
        install = Path(os.environ['XDG_CONFIG_HOME']) / 'hypr'; install.mkdir(parents=True)
        (install / 'hyprland.lua').symlink_to(config)
        start([os.environ['TABLET_TEST_HYPRLAND'], '-c', str(config)], 'hyprland')
        ipc = until(lambda: next((runtime / 'hypr').glob('*/.socket.sock'), None), 'private inner socket')
        os.environ['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        os.environ['WAYLAND_DISPLAY'] = until(lambda: next((p.name for p in runtime.glob('wayland-*') if p.is_socket() and p != outer), None), 'private inner display')
        probe = root / 'compositor-stremio-bin.txt'
        ctl('dispatch', 'exec', 'printf "%s" "${TABLET_STREMIO_BIN:-}" > ' + shlex.quote(str(probe)))
        until(probe.exists, 'clean compositor environment probe')
        assert probe.read_text() == '', 'Fixture must not mask launcher environment handoff'
        os.environ['TABLET_STREMIO_BIN'] = str(binary)
        ctl('output', 'create', 'headless', 'eDP-1')
        ctl('keyword', 'monitor', 'eDP-1,960x640@60,0x0,1')
        for monitor in json.loads(ctl('monitors', '-j')):
            if monitor['name'] != 'eDP-1': ctl('keyword', 'monitor', monitor['name'] + ',disable')
        pointer = subprocess.Popen([os.environ['TABLET_TEST_POINTER']], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        processes.append(pointer)
        assert select.select([pointer.stdout], [], [], 5)[0] and pointer.stdout.readline().strip() == 'READY'
        baseline = posture()
        ctl('dispatch', 'workspace', 'name:laptop-fixture')
        laptop = start(['quickshell', '--path', os.environ['TABLET_TEST_LAPTOP_QML']], 'laptop')
        laptop_window = until(lambda: next((c for c in clients() if c['pid'] == laptop.pid), None), 'laptop fixture')
        ctl('dispatch', 'focuswindow', 'address:' + laptop_window['address'])
        proof('start'); tap('app-stremio')
        until(lambda: status()['stremioRunning'] and not status()['home'], 'real Stremio tablet launch', timeout=50)
        window = next(c for c in clients() if c['class'] == 'com.stremio.Stremio')
        original = {k: window[k] for k in ('address', 'pid', 'stableId')}
        backend = status()['backend']['pid']
        until(lambda: next(c for c in clients() if c['address'] == window['address'])['size'] == [960, 640], 'Stremio fills tablet')
        assert not window['xwayland']
        def fixture_rendered():
            assert str(ipc).startswith(str(runtime) + '/hypr/')
            image = Image.open(io.BytesIO(subprocess.check_output(['grim', '-o', 'eDP-1', '-']))).convert('RGB')
            return image.getpixel((500, 400)) == (37, 59, 104)
        until(fixture_rendered, 'offline HTML fixture actually rendered')
        snapshot('stremio-fullscreen'); mark('stremio-fullscreen:ready')
        time.sleep(.5); swipe_home()
        until(lambda: status()['home'], 'real bottom swipe from Stremio')
        tap('app-stremio')
        until(lambda: not status()['home'], 'resume Stremio')
        switcher()
        old_source = status()['cardSources']['stremio']
        swipe_card_close()
        assert Path(f'/proc/{original["pid"]}').exists(), 'Normal close must respect the app tray policy, not kill it'
        mark('owned-tray-reopen:begin'); tap('app-stremio')
        until(lambda: status()['stremioRunning'] and not status()['home'], 'reopen exact owned tray')
        window = next(c for c in clients() if c['class'] == 'com.stremio.Stremio' and c['mapped'])
        assert window['pid'] == original['pid'], 'Reopen created another process'
        if window['stableId'] != original['stableId']:
            for command in ['dismiss-app', 'resume-app']:
                refused = subprocess.run([os.environ['TABLET_PROOF_BIN'], command, '--target', json.dumps({'app':'stremio','window':old_source})], capture_output=True, text=True, timeout=40)
                assert refused.returncode and 'unavailable or changed' in refused.stderr
                mark('stale-card:' + command + '-refused')
        original = {k: window[k] for k in ('address', 'pid', 'stableId')}
        snapshot('stremio-owned-tray-reopened'); mark('owned-tray-reopen:ready')
        assert status()['backend']['pid'] == backend
        assert len([c for c in clients() if c['class'] == 'com.stremio.Stremio']) == 1
        proof('close')
        assert posture() == baseline
        assert json.loads(ctl('activewindow', '-j'))['address'] == laptop_window['address']
        kept = next(c for c in clients() if c['address'] == window['address'])
        assert all(kept[k] == v for k, v in original.items()) and kept['fullscreen'] == 0
        proof('start')
        until(lambda: status()['stremioRunning'] and not status()['home'], 'refold resumes exact Stremio')
        assert next(c for c in clients() if c['class'] == 'com.stremio.Stremio')['stableId'] == original['stableId']
        # SIGKILL recovery must restore the desktop without closing Stremio.
        descriptor = os.pidfd_open(status()['backend']['pid'])
        try: signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        finally: os.close(descriptor)
        until(lambda: not status().get('running') and not status().get('recovery'), 'Stremio crash recovery', timeout=40)
        assert posture() == baseline
        assert any(c['stableId'] == original['stableId'] for c in clients())
        # Move only this disposable test window to simulate a desktop singleton.
        ctl('dispatch', 'movetoworkspacesilent', 'name:laptop-fixture,address:' + window['address'])
        proof('start')
        attempt = subprocess.run([os.environ['TABLET_PROOF_BIN'], 'stremio'], capture_output=True, text=True, timeout=40)
        assert attempt.returncode and ('Quit desktop Stremio' in attempt.stderr or 'unavailable' in attempt.stderr), attempt
        # Exercise the registration race guard directly, bypassing the advisory
        # Python busy check while a real singleton already owns the bus name.
        focus_before = json.loads(ctl('activewindow', '-j'))
        refused = subprocess.run([str(binary)], env=dict(os.environ, TABLET_STREMIO_TOKEN='race-fixture'),
                                 capture_output=True, text=True, timeout=15)
        assert refused.returncode == 1, refused
        assert json.loads(ctl('activewindow', '-j')) == focus_before, 'remote singleton activated'
        assert len([c for c in clients() if c['class'] == 'com.stremio.Stremio']) == 1
        assert next(c for c in clients() if c['stableId'] == original['stableId'])['workspace']['name'] == 'laptop-fixture'
        proof('close')
        print('PASS: actual native Stremio tile launch, fullscreen, bottom swipe, real WebKit preview, normal close/hide, exact owned-tray reopen, stale card rejection, unfold/crash restoration; desktop singleton and laptop window untouched; offline disposable profile', flush=True)
    finally:
        if ipc:
            try:
                (root / 'last-frame.png').write_bytes(subprocess.check_output(['grim', '-o', 'eDP-1', '-']))
                (root / 'last-clients.json').write_text(json.dumps(clients(), indent=2))
                (root / 'last-status.json').write_text(json.dumps(status(), indent=2))
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
    raise SystemExit(inner() if os.environ.get('TABLET_WINDOW_TEST_ROOT') else driver.outer(__file__, isolated_network=True, isolated_processes=True))
