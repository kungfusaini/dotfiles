#!/usr/bin/env python3
"""One-window Hyprland tablet proof. No app launch, workspace move or fold hook."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import subprocess
import sys
import time
import uuid


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=5, **kwargs).stdout.strip()


def hypr(*args):
    return json.loads(run('hyprctl', *args, '-j'))


def dispatch(command, argument):
    # Stop hyprctl's flag parser before negative tag-removal arguments.
    result = run('hyprctl', 'dispatch', command, '--', argument)
    if result != 'ok':
        raise RuntimeError('Compositor refused ' + command + ': ' + result)


def start_time(pid):
    return Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[19]


def runtime():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-proof'
    if path.is_symlink():
        raise RuntimeError('Unsafe proof runtime directory')
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError('Proof runtime is not owned by this user')
    path.chmod(0o700)
    return path


def save(value):
    path = runtime() / 'recovery.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value))
    temp.chmod(0o600)
    temp.replace(path)


def safe_workspace(name):
    if not name or any(c in name for c in ',;\n\r'):
        raise RuntimeError('Workspace name cannot be safely dispatched')
    return name


class Controls:
    """Read/write existing system backends, never simulated values in the UI."""
    def read(self):
        value = {'volume': None, 'muted': False, 'brightness': None}
        try:
            text = run('wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@')
            value.update(volume=min(100, round(float(text.split()[1]) * 100)), muted='MUTED' in text)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        try:
            maximum = int(run('brightnessctl', '--device=intel_backlight', 'max'))
            value['brightness'] = round(int(run('brightnessctl', '--device=intel_backlight', 'get')) * 100 / maximum)
        except (OSError, ValueError, ZeroDivisionError, subprocess.SubprocessError):
            pass
        return value

    def change(self, command, value=None):
        if command in ('volume', 'brightness'):
            if type(value) not in (int, float) or not 0 <= value <= 100:
                raise RuntimeError('Invalid control value')
            if command == 'volume':
                run('wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', str(value / 100))
            else:
                run('brightnessctl', '--device=intel_backlight', 'set', f'{max(5, round(value))}%')
        elif command == 'mute':
            run('wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle')
        else:
            raise RuntimeError('Unsupported control')


class Keyboard:
    def __init__(self):
        self.process = None
        self.settings = []

    def start(self):
        # Another bus/compositor's keyboard is not ours to replace. Refuse any
        # keyboard already attached to this exact runtime/display.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if proc.stat().st_uid != os.getuid() or (proc / 'comm').read_text().strip() not in ('squeekboard', 'wvkbd', 'wvkbd-mobintl'):
                    continue
                env = dict(os.fsdecode(v).split('=', 1) for v in (proc / 'environ').read_bytes().split(b'\0') if b'=' in v)
                if env.get('XDG_RUNTIME_DIR') == os.environ['XDG_RUNTIME_DIR'] and env.get('WAYLAND_DISPLAY') == os.environ.get('WAYLAND_DISPLAY'):
                    raise RuntimeError('An existing keyboard owns this display; proof will not replace it')
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        for schema, key, applied in [
            ('org.gnome.desktop.a11y.applications', 'screen-keyboard-enabled', 'true'),
            ('sm.puri.Squeekboard', 'scale-in-horizontal-screen-orientation', '1.45'),
            ('sm.puri.Squeekboard', 'layout-shape-changes-to-fit-panel', 'true'),
        ]:
            old = run('gsettings', 'get', schema, key)
            self.settings.append([schema, key, old, applied])
            # Journal before changing settings, including partial startup.
            self.journal_callback()
            run('gsettings', 'set', schema, key, applied)
        with (runtime() / 'keyboard.log').open('a') as log:
            self.process = subprocess.Popen(['squeekboard'], stdout=log, stderr=log)
        self.journal_callback()

    def hide(self):
        if not self.process or self.process.poll() is not None:
            return
        owner = run('gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus',
                    '--method', 'org.freedesktop.DBus.GetNameOwner', 'sm.puri.OSK0')
        match = re.fullmatch(r"\('(:[A-Za-z0-9_.-]+)',\)", owner)
        if not match:
            raise RuntimeError('Cannot verify proof keyboard bus owner')
        peer = match[1]
        identity = run('gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus',
                       '--method', 'org.freedesktop.DBus.GetConnectionUnixProcessID', peer)
        if identity != f'(uint32 {self.process.pid},)':
            raise RuntimeError('Keyboard bus owner was replaced; no action sent')
        run('gdbus', 'call', '--session', '--dest', peer, '--object-path', '/sm/puri/OSK0',
            '--method', 'sm.puri.OSK0.SetVisible', 'false')

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        for schema, key, old, applied in reversed(self.settings):
            if run('gsettings', 'get', schema, key) == applied:
                run('gsettings', 'set', schema, key, old)


class Proof:
    def __init__(self, controls=None, keyboard=None):
        self.controls = controls or Controls()
        self.keyboard = keyboard or Keyboard()
        self.keyboard.journal_callback = self.journal
        self.record = None
        self.ui = None
        self.home = False
        self.drawer = False
        self.ready = False
        self.stopping = False
        self.error = ''
        self.values = {}

    def window(self, require_tag=True):
        r = self.record
        if r['instance'] != os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            raise RuntimeError('Proof belongs to a different compositor')
        if start_time(r['pid']) != r['start']:
            raise RuntimeError('Selected browser process was replaced')
        for client in hypr('clients'):
            if (client['address'] == r['address'] and client['pid'] == r['pid']
                    and client.get('class') == r['class'] and client.get('stableId') == r['stableId'] and client.get('mapped')
                    and (not require_tag or r['tag'] in [t.rstrip('*') for t in client.get('tags', [])])):
                return client
        raise RuntimeError('The exact proof window no longer exists; no replacement claimed')

    def owned_processes(self):
        return (self.ui, self.keyboard.process)

    def child_role(self, process):
        return 'keyboard' if process is self.keyboard.process else 'ui'

    def journal(self):
        if not self.record:
            return
        children = []
        for process in self.owned_processes():
            if process and process.poll() is None:
                try:
                    children.append({'pid': process.pid, 'start': start_time(process.pid), 'role': self.child_role(process)})
                except (FileNotFoundError, ProcessLookupError):
                    pass  # A child may exit between poll and lifetime lookup.
        save({'window': self.record, 'children': children, 'settings': self.keyboard.settings})

    def guard(self):
        window = self.window()
        monitors = hypr('monitors')
        current = hypr('activeworkspace')
        monitor = next((m for m in monitors if m['name'] == 'eDP-1'), None)
        try:
            headless = Path('/run/headless-mode/state').read_text().strip() != 'off'
        except FileNotFoundError:
            headless = False
        if (headless or not monitor or monitor.get('disabled') or not monitor.get('dpmsStatus', True)
                or monitor.get('specialWorkspace', {}).get('id', 0)
                or current['name'] != self.record['workspace'] or current.get('monitor') != 'eDP-1'
                or window.get('workspace', {}).get('name') != self.record['workspace'] or window.get('monitor') != monitor['id']
                or window.get('pinned') or window.get('grouped') or window.get('floating')
                or hypr('activewindow').get('address') != self.record['address']):
            raise RuntimeError('Selected internal-display window/workspace is no longer foreground and eligible')
        return window, monitor

    def modes(self, internal, client):
        window, _ = self.guard()
        # The pinned hyprlang dispatcher operates on the active window. Never
        # issue it on focus guessed from a shared process or a stale address.
        if hypr('activewindow').get('address') != window['address']:
            raise RuntimeError('Browser lost focus; native presentation change refused')
        if (window.get('fullscreen', 0), window.get('fullscreenClient', 0)) == (internal, client):
            return  # fullscreenstate TOGGLES if called with identical modes.
        dispatch('fullscreenstate', f'{internal} {client}')
        if hypr('activewindow').get('address') != window['address']:
            raise RuntimeError('Focus changed during presentation transition; recovery retained')

    def setup(self, address):
        if (runtime() / 'recovery.json').exists():
            raise RuntimeError('Previous proof needs recover first')
        self.lease(address)
        self.keyboard.start()
        self.values = self.controls.read()

    def lease(self, address):
        """Acquire native presentation; the caller already owns the journal."""
        if not re.fullmatch(r'0x[0-9a-f]+', address):
            raise RuntimeError('Explicit browser address required')
        clients = hypr('clients')
        client = next((c for c in clients if c['address'] == address), None)
        if not client or client.get('class') != 'vivaldi-stable' or client.get('xwayland') or not client.get('mapped'):
            raise RuntimeError('Proof needs one existing native Vivaldi window; no app will be launched')
        if client.get('pinned') or client.get('grouped') or client.get('floating'):
            raise RuntimeError('This first proof requires a regular tiled browser, not a floating/pinned/grouped window')
        if not re.fullmatch(r'[0-9a-f]+', client.get('stableId', '')):
            raise RuntimeError('Pinned compositor window lifetime ID is unavailable')
        workspace = next((w for w in hypr('workspaces') if w['name'] == client['workspace']['name']), None)
        if not workspace or workspace.get('monitor') != 'eDP-1':
            raise RuntimeError('Selected window must already be on the internal display')
        if any(c['address'] != address and c['workspace']['name'] == workspace['name'] and c.get('fullscreen') for c in clients):
            raise RuntimeError('Another fullscreen window owns this workspace')
        origin = hypr('activeworkspace')
        if origin.get('monitor') != 'eDP-1':
            raise RuntimeError('Start proof from the awake internal display')
        focus = hypr('activewindow')
        sync = run('hyprctl', 'getprop', 'address:' + address, 'sync_fullscreen')
        if sync not in ('true', 'false'):
            raise RuntimeError('Cannot snapshot fullscreen synchronization')
        self.record = {'instance': os.environ['HYPRLAND_INSTANCE_SIGNATURE'], 'address': address,
                       'pid': client['pid'], 'start': start_time(client['pid']), 'class': client['class'], 'stableId': client['stableId'],
                       'workspace': safe_workspace(workspace['name']), 'origin': safe_workspace(origin['name']),
                       'focus': {key: focus.get(key) for key in ('address', 'pid', 'class', 'stableId')},
                       'tag': 'tablet-proof-' + uuid.uuid4().hex,
                       'internal': client.get('fullscreen', 0), 'client': client.get('fullscreenClient', 0),
                       'sync': sync, 'applied': False, 'tagged': False,
                       'introduced_maximize': client.get('fullscreenClient', 0) == 0,
                       'config_changed': False}
        self.journal()
        self.record['tagged'] = True
        self.journal()
        dispatch('tagwindow', '+' + self.record['tag'] + ' address:' + address)
        dispatch('workspace', 'name:' + self.record['workspace'])
        dispatch('focuswindow', 'address:' + address)
        self.guard()
        client_mode = 2 if client.get('fullscreenClient') == 2 else 1
        self.record['applied'] = (client.get('fullscreen', 0), client.get('fullscreenClient', 0)) != (2, client_mode)
        self.journal()
        # Internal full display + client maximized is a native fullscreen-state
        # pair, not a fake floating rectangle. Client requests for media remain
        # free to become fullscreen; no geometry enforcement runs afterwards.
        self.modes(2, client_mode)

    def state(self):
        window, monitor = self.guard()
        return {'running': True, 'ready': self.ready, 'home': self.home, 'drawer': self.drawer,
                'backend': {'pid': os.getpid(), 'start': start_time(os.getpid())},
                'media': window.get('fullscreenClient') == 2,
                'keyboardInset': monitor.get('reserved', [0, 0, 0, 0])[3],
                'source': {'address': self.record['address'], 'pid': self.record['pid']},
                'error': self.error, **self.values}

    def action(self, command, value=None):
        self.guard()
        if command != 'status':
            self.error = ''
        if command == 'ui-ready':
            self.ready = True
        elif command == 'home':
            self.keyboard.hide()
            self.home = True
            self.drawer = False
        elif command == 'app':
            self.home = False
            self.drawer = False
        elif command == 'settings':
            self.values = self.controls.read()
            self.drawer = True
        elif command == 'dismiss':
            self.drawer = False
        elif command == 'hide-keyboard':
            self.keyboard.hide()
        elif command in ('volume', 'brightness', 'mute'):
            if not self.drawer:
                raise RuntimeError('Open settings before using a live control')
            self.controls.change(command, value)
            self.values = self.controls.read()
        elif command == 'close':
            self.stopping = True
        elif command != 'status':
            raise RuntimeError('Unknown proof action')
        return self.state()

    def cleanup(self, activate=False, retain_journal=False):
        if not self.record:
            return
        errors = []
        for fn in (self.keyboard.stop,):
            try:
                fn()
            except Exception as error:
                errors.append(str(error))
        r = self.record
        try:
            window = self.window(require_tag=r['tagged'])
        except (OSError, RuntimeError):
            window = None  # Never adopt/recreate a disappeared or untagged app.
        if window:
            try:
                if activate:
                    dispatch('workspace', 'name:' + r['workspace'])
                    dispatch('focuswindow', 'address:' + r['address'])
                # Even an unchanged initial pair owns an overlay/return path.
                # Never use that path to steal focus after eligibility is lost.
                self.guard()
                if r['applied']:
                    current_client = window.get('fullscreenClient', 0)
                    # Revert our initial client-maximize request, but preserve
                    # a user's later real media fullscreen/exit request.
                    desired_client = r['client'] if current_client == 1 and r['introduced_maximize'] else current_client
                    desired_internal = 2 if desired_client == 2 else r['internal']
                    self.modes(desired_internal, desired_client)
                    dispatch('setprop', 'address:' + r['address'] + ' sync_fullscreen ' + ('unset' if r['config_changed'] else r['sync']))
                if r['tagged']:
                    dispatch('tagwindow', '-' + r['tag'] + ' address:' + r['address'])
                current = hypr('activeworkspace')
                # Never steal focus after a deliberate workspace switch.
                if current['name'] == r['workspace']:
                    if any(w['name'] == r['origin'] for w in hypr('workspaces')):
                        dispatch('workspace', 'name:' + r['origin'])
                        focus = next((c for c in hypr('clients') if all(c.get(key) == value for key, value in r['focus'].items())
                                      and c.get('stableId') and c['workspace']['name'] == r['origin']), None)
                        if focus:
                            dispatch('focuswindow', 'address:' + focus['address'])
            except Exception as error:
                errors.append(str(error))
        if self.ui and self.ui.poll() is None:
            self.ui.terminate()
            try:
                self.ui.wait(timeout=5)
            except subprocess.TimeoutExpired:
                errors.append('Proof frontend did not stop')
        if errors:
            raise RuntimeError('Proof recovery retained: ' + '; '.join(errors))
        if not retain_journal:
            (runtime() / 'recovery.json').unlink(missing_ok=True)


def request(command, value=None):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(8)
        conn.connect(str(runtime() / 'control.sock'))
        conn.sendall(json.dumps({'command': command, 'value': value}).encode() + b'\n')
        line = conn.makefile('rb').readline(65536)
        result = json.loads(line)
        if result.get('failed'):
            raise RuntimeError(result['error'])
        return result


def daemon(address):
    with (runtime() / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        selector = selectors.DefaultSelector()
        subscribers = set()
        proof = Proof()
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, lambda *_: setattr(proof, 'stopping', True))
        path = runtime() / 'control.sock'
        server = socket.socket(socket.AF_UNIX)
        ipc = socket.socket(socket.AF_UNIX)
        previous = None
        deferred = None
        event_buffer = b''
        try:
            path.unlink(missing_ok=True)
            server.bind(str(path)); server.listen(8)
            selector.register(server, selectors.EVENT_READ, 'server')
            ipc.connect(str(Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr' / os.environ['HYPRLAND_INSTANCE_SIGNATURE'] / '.socket2.sock'))
            selector.register(ipc, selectors.EVENT_READ, 'compositor')
            proof.setup(address)
            with (runtime() / 'frontend.log').open('a') as log:
                proof.ui = subprocess.Popen(['quickshell', '--path', os.environ['TABLET_PROOF_QML']], stdout=log, stderr=log)
            proof.journal()
            deadline = time.monotonic() + 15
            while not proof.stopping:
                if proof.ui.poll() is not None or proof.keyboard.process.poll() is not None:
                    raise RuntimeError('Proof frontend or keyboard exited')
                if not proof.ready and time.monotonic() > deadline:
                    raise RuntimeError('Proof frontend did not render/connect; inspect frontend.log')
                events = selector.select(.1 if deferred else 2)
                for key, _ in events:
                    if key.data == 'compositor':
                        data = ipc.recv(65536)
                        if not data:
                            raise RuntimeError('Compositor disconnected')
                        event_buffer += data
                        lines = event_buffer.split(b'\n')
                        event_buffer = lines.pop()
                        if any(line.startswith(b'configreloaded>>') for line in lines):
                            proof.record['config_changed'] = True
                            proof.journal()
                            proof.stopping = True
                        deferred = time.monotonic() + .15
                    elif key.data == 'server':
                        conn, _ = server.accept(); conn.settimeout(2)
                        try:
                            try:
                                message = json.loads(conn.makefile('rb').readline(65536))
                                if message['command'] == 'watch':
                                    conn.sendall(json.dumps(proof.state()).encode() + b'\n')
                                    subscribers.add(conn); continue
                                state = proof.action(message['command'], message.get('value'))
                            except Exception as error:
                                proof.error = str(error)
                                state = {'failed': True, 'error': str(error)}
                            conn.sendall(json.dumps(state).encode() + b'\n')
                        finally:
                            if conn not in subscribers:
                                conn.close()
                state = proof.state()  # Event-driven, plus a 2s safety gate.
                if state != previous or (deferred and time.monotonic() >= deferred):
                    payload = json.dumps(state).encode() + b'\n'
                    for conn in list(subscribers):
                        try:
                            conn.settimeout(.1); conn.sendall(payload)
                        except OSError:
                            conn.close(); subscribers.remove(conn)
                    previous = state
                    if deferred and time.monotonic() >= deferred:
                        deferred = None
        finally:
            server.close(); ipc.close(); selector.close()
            for conn in subscribers:
                conn.close()
            try:
                proof.cleanup()
            finally:
                path.unlink(missing_ok=True)


def recover(activate=False):
    with (runtime() / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = runtime() / 'recovery.json'
        if not path.exists():
            return
        value = json.loads(path.read_text())
        if value['window']['instance'] != os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            raise RuntimeError('Recover in the original compositor; no stale state replayed')
        for child in value['children']:
            try:
                if start_time(child['pid']) != child['start']:
                    continue
                fd = os.pidfd_open(child['pid'])
                try:
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                    import select
                    if not select.select([fd], [], [], 5)[0]:
                        raise RuntimeError('Proof child did not exit; no force used')
                finally:
                    os.close(fd)
            except (FileNotFoundError, ProcessLookupError):
                pass
        proof = Proof()
        proof.record = value['window']
        proof.keyboard.settings = value['settings']
        proof.cleanup(activate=activate)


def supervise(address):
    child = subprocess.Popen([os.environ['TABLET_PROOF_BIN'], 'daemon', '--address', address])
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: child.terminate() if child.poll() is None else None)
    code = child.wait()
    # An independently sleeping supervisor recovers after a backend crash. It
    # never invents an active target or steals another workspace's focus.
    recover()
    return code


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'supervise', 'daemon', 'status', 'watch', 'home', 'app', 'settings', 'dismiss', 'hide-keyboard', 'volume', 'brightness', 'mute', 'ui-ready', 'close', 'recover'] + globals().get('EXTRA_COMMANDS', []))
    parser.add_argument('--address')
    parser.add_argument('--value', type=float)
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if args.command == 'daemon':
        daemon(args.address)
    elif args.command == 'supervise':
        sys.exit(supervise(args.address))
    elif args.command == 'start':
        with (runtime() / 'launch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = request('status')
                if args.address and state.get('source', {}).get('address') != args.address:
                    raise RuntimeError('Another proof is already active; no target replaced')
                print(json.dumps(state)); return
            except (FileNotFoundError, ConnectionRefusedError):
                pass
            if (runtime() / 'recovery.json').exists():
                raise RuntimeError('Previous proof needs recover first')
            with (runtime() / 'supervisor.log').open('a') as log:
                process = subprocess.Popen([os.environ['TABLET_PROOF_BIN'], 'supervise', '--address', args.address or ''], stdout=log, stderr=log, start_new_session=True)
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Proof failed; inspect private supervisor.log')
                try:
                    state = request('status')
                    if state.get('ready'):
                        print(json.dumps(state)); return
                except (FileNotFoundError, ConnectionRefusedError):
                    pass
                time.sleep(.1)
            raise RuntimeError('Proof startup timed out; inspect supervisor.log')
    elif args.command == 'watch':
        with socket.socket(socket.AF_UNIX) as conn:
            conn.connect(str(runtime() / 'control.sock'))
            conn.sendall(b'{"command":"watch"}\n')
            for line in conn.makefile():
                print(line.rstrip(), flush=True)
    elif args.command == 'recover':
        recover(args.activate)
    else:
        try:
            result = request(args.command, args.value)
            if args.command == 'close':
                for _ in range(150):
                    if not (runtime() / 'control.sock').exists() and not (runtime() / 'recovery.json').exists():
                        break
                    time.sleep(.1)
                if (runtime() / 'recovery.json').exists():
                    raise RuntimeError('Proof closed with pending recovery; use recover')
            print(json.dumps(result))
        except (FileNotFoundError, ConnectionRefusedError):
            if args.command != 'status':
                raise
            print(json.dumps({'running': False, 'recovery': (runtime() / 'recovery.json').exists()}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
