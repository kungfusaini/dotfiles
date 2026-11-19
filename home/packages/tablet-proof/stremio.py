"""Exact, tablet-created Stremio window ownership; no desktop singleton adoption."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

APP_ID = 'com.stremio.Stremio'
WORKSPACE = 'tablet-trial'


def start(pid):
    return Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[19]


def token(pid):
    return next((item.split(b'=', 1)[1].decode() for item in
                 Path(f'/proc/{int(pid)}/environ').read_bytes().split(b'\0')
                 if item.startswith(b'TABLET_STREMIO_TOKEN=')), None)


def busy():
    # GApplication is single-instance, including hidden/tray-only instances.
    # Query registration, not window presence; never activate a desktop owner.
    result = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
                             '--object-path', '/org/freedesktop/DBus', '--method',
                             'org.freedesktop.DBus.NameHasOwner', APP_ID],
                            check=True, capture_output=True, text=True, timeout=5)
    if result.stdout.strip() not in ('(true,)', '(false,)'):
        raise RuntimeError('Could not verify Stremio singleton availability')
    if result.stdout.strip() == '(true,)':
        return True
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid == os.getuid() and (path / 'exe').resolve(strict=True).name in (
                    'stremio', 'stremio-linux-shell', '.stremio-wrapped', '.stremio-linux-shell-wrapped'):
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass  # Unrelated nondumpable processes are not singleton evidence.
    return False


def activate_owned(record, verify):
    """Resolve and activate on ONE bus connection; never a well-known-name race."""
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def query(method, value):
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                             'org.freedesktop.DBus', method, GLib.Variant('(s)', (value,)),
                             None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    destination = query('GetNameOwner', APP_ID)
    pid = query('GetConnectionUnixProcessID', destination)
    owner = record['owner']
    if (pid != owner['pid'] or start(pid) != owner['start'] or token(pid) != record['token']):
        raise RuntimeError('Stremio singleton ownership changed; no instance was activated')
    verify()  # Fresh workspace/window eligibility immediately before the request.
    bus.call_sync(destination, '/com/stremio/Stremio', 'org.freedesktop.Application',
                  'Activate', GLib.Variant('(a{sv})', ({},)), None,
                  Gio.DBusCallFlags.NONE, 5000, None)


def token_processes(value):
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            executable = (path / 'exe').resolve(strict=True).name
            helper = executable.startswith('python') and os.fsencode(str(Path(__file__).resolve())) in (path / 'cmdline').read_bytes().split(b'\0')
            if (executable in ('stremio', 'stremio-linux-shell', '.stremio-wrapped', '.stremio-linux-shell-wrapped') or helper) and token(int(path.name)) == value:
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass  # The exact recorded owner is checked separately before retry.
    return False


class Stremio:
    def __init__(self, hypr, dispatch):
        self.hypr, self.dispatch = hypr, dispatch
        self.error = ''

    def path(self):
        root = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-stremio'
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            raise RuntimeError('Unsafe Stremio runtime')
        root.chmod(0o700)
        return root / 'window.json'

    @contextmanager
    def lock(self):
        with self.path().with_suffix('.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def read(self):
        try:
            value = json.loads(self.path().read_text())
            return value if value.get('instance') == os.environ['HYPRLAND_INSTANCE_SIGNATURE'] else {}
        except FileNotFoundError:
            return {}

    def write(self, value):
        path = self.path()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(value, instance=os.environ['HYPRLAND_INSTANCE_SIGNATURE'])))
        temporary.chmod(0o600)
        temporary.replace(path)

    def candidate(self, client, record):
        return (client.get('mapped') and client.get('class') == APP_ID
                and not any(client.get(k) for k in ('xwayland', 'floating', 'pinned', 'grouped'))
                and client.get('workspace', {}).get('name') == WORKSPACE
                and bool(re.fullmatch('[0-9a-f]+', client.get('stableId', '')))
                and client['address'] not in record['previous']
                and client['pid'] == record.get('owner', {}).get('pid')
                and start(client['pid']) == record['owner']['start']
                and token(client['pid']) == record['token'])

    def registered(self):
        record = self.read()
        if not record.get('window'):
            return None
        for client in self.hypr('clients'):
            try:
                identity = {k: client[k] for k in ('address', 'pid', 'class', 'stableId')}
                if (identity == record['window'] and start(client['pid']) == record['start']
                        and token(client['pid']) == record['token']):
                    return client
            except (FileNotFoundError, ProcessLookupError):
                pass
        return None

    def window(self):
        client = self.registered()
        return client if client and self.candidate(client, self.read()) else None

    def hidden(self):
        client = self.registered()
        return bool(client and not client.get('mapped')
                    and client.get('workspace', {}).get('name') == WORKSPACE
                    and not any(client.get(k) for k in ('xwayland', 'floating', 'pinned', 'grouped')))

    def restore(self, old):
        owner = old['owner']
        def verify():
            workspace = self.hypr('activeworkspace')
            if (workspace.get('name') != WORKSPACE or workspace.get('monitor') != 'eDP-1'
                    or any(c.get('pid') == owner['pid'] and (c.get('mapped')
                           or c.get('workspace', {}).get('name') != WORKSPACE
                           or any(c.get(k) for k in ('xwayland', 'floating', 'pinned', 'grouped')))
                           for c in self.hypr('clients'))):
                raise RuntimeError('Quit desktop Stremio before reopening the tablet instance; no window was activated')
        verify()
        clients = self.hypr('clients')
        value = {'token': old['token'], 'owner': owner, 'deadline': time.monotonic() + 30,
                 'previous': [c['address'] for c in clients if {k: c[k] for k in ('address', 'pid', 'class', 'stableId')} != old['window']]}
        self.write(value)  # Journal intent before sending the owned activation.
        try:
            activate_owned(value, verify)
        except Exception:
            # Keep uncertainty: a delivered activation may still map later.
            self.error = 'Stremio reopen was not verified; no other instance was activated'
            raise
        self.error = ''

    def launch(self):
        with self.lock():
            return self._launch()

    def _launch(self):
        self._tick()
        client = self.window()
        if client:
            self.error = ''
            return client  # The native caller performs lifetime-guarded focus.
        old = self.read()
        if old.get('window') and old.get('owner'):
            try:
                owned = start(old['owner']['pid']) == old['owner']['start'] and token(old['owner']['pid']) == old['token']
            except (FileNotFoundError, ProcessLookupError):
                owned = False
            if owned:
                self.restore(old)
                return
        if old and not old.get('window'):
            owner = old.get('owner', {})
            try:
                alive = start(owner['pid']) == owner['start']
            except (FileNotFoundError, ProcessLookupError, KeyError):
                alive = False
            if time.monotonic() < old['deadline'] or alive or token_processes(old['token']):
                raise RuntimeError('Previous Stremio launch is unresolved; no duplicate started')
            # Under the same lock as the spawn helper: replacing this token
            # invalidates any delayed compositor exec before it can start.

        if busy() or any(c.get('class') == APP_ID for c in self.hypr('clients')):
            raise RuntimeError('Quit desktop Stremio (including its tray) before opening the tablet tile; no laptop window was moved')
        value = {'token': uuid.uuid4().hex, 'previous': [c['address'] for c in self.hypr('clients')],
                 'deadline': time.monotonic() + 30}
        self.write(value)  # Survives controller interruption before first map.
        command = [sys.executable, str(Path(__file__).resolve()), '--spawn', value['token']]
        try:
            self.dispatch('exec', {'command': 'env GDK_BACKEND=wayland TABLET_STREMIO_TOKEN='
                          + value['token'] + ' ' + shlex.join(command),
                          'rules': {'workspace': 'name:' + WORKSPACE + ' silent'}})
        except Exception:
            value['deadline'] = 0
            self.write(value)
            raise RuntimeError('Tablet Stremio launch request failed') from None
        self.error = ''

    def tick(self):
        with self.lock():
            self._tick()

    def _tick(self):
        record = self.read()
        if not record or record.get('window'):
            return
        if record.get('ambiguous'):
            self.error = 'Stremio opened multiple windows; quit Stremio before retrying. No window was adopted.'
            return
        matches = []
        for client in self.hypr('clients'):
            try:
                if self.candidate(client, record):
                    matches.append(client)
            except (FileNotFoundError, ProcessLookupError):
                pass
        if len(matches) == 1:
            client = matches[0]
            record.update(window={k: client[k] for k in ('address', 'pid', 'class', 'stableId')},
                          start=start(client['pid']))
            self.write(record)
            self.error = ''
        elif len(matches) > 1:
            record.update(ambiguous=True, deadline=0)
            self.write(record)
            self.error = 'Stremio launch was not uniquely verified; no existing window was adopted. Launch receipt retained.'
        elif time.monotonic() >= record['deadline']:
            self.error = 'Stremio launch was not uniquely verified; no existing window was adopted. Launch receipt retained.'

    def status(self):
        self.tick()
        record = self.read()
        return {'stremioRunning': bool(self.window()),
                'stremioLaunching': bool(record and not record.get('window') and time.monotonic() < record['deadline']),
                'stremioError': self.error}


def spawn(value):
    app = Stremio(None, None)
    with app.lock():
        record = app.read()
        if (record.get('token') != value or record.get('owner') or record.get('window')
                or time.monotonic() >= record['deadline']):
            return 1
        record['owner'] = {'pid': os.getpid(), 'start': start(os.getpid())}
        app.write(record)
    # The packaged GApplication guard refuses remote activation atomically.
    os.execv(os.environ['TABLET_STREMIO_BIN'], [os.environ['TABLET_STREMIO_BIN']])


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--spawn':
        raise SystemExit('Only the tablet spawn helper is supported')
    raise SystemExit(spawn(sys.argv[2]))
