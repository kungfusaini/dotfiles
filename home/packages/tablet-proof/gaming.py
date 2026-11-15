#!/usr/bin/env python3
"""Tablet-local Pegasus/game identities; never borrow or terminate applications."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

WORKSPACE = 'tablet-trial'
PEGASUS = {'pegasus-fe', '.pegasus-fe-wrapped'}


def start(pid):
    return Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[19]


def executable(pid):
    return Path(f'/proc/{int(pid)}/exe').resolve(strict=True).name


def environment(pid):
    # Read only launch identity, never retain unrelated browser/account state.
    names = {b'TABLET_PEGASUS_TOKEN', b'SteamAppId', b'SteamGameId'}
    return {k.decode(): v.decode() for item in Path(f'/proc/{int(pid)}/environ').read_bytes().split(b'\0')
            if b'=' in item for k, v in [item.split(b'=', 1)] if k in names}


def descendant(pid, authority):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        try:
            if pid == authority['pid']:
                return start(pid) == authority['start']
            pid = int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def root():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-games'
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError('Unsafe tablet game runtime')
    return path


def read(name):
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return {}
    try:
        value = json.loads((root() / name).read_text())
        return value if value.get('instance') == os.environ['HYPRLAND_INSTANCE_SIGNATURE'] else {}
    except FileNotFoundError:
        return {}


def write(name, value):
    path = root() / name
    temporary = path.with_name(name + '.' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(dict(value, instance=os.environ['HYPRLAND_INSTANCE_SIGNATURE'])))
    temporary.chmod(0o600)
    temporary.replace(path)


def identity(client):
    return {**{k: client[k] for k in ('address', 'pid', 'class', 'stableId')}, 'start': start(client['pid'])}


def local(client):
    return (client.get('mapped') and client.get('workspace', {}).get('name') == WORKSPACE
            and not any(client.get(k) for k in ('pinned', 'grouped', 'floating'))
            and bool(re.fullmatch('[0-9a-f]+', client.get('stableId', ''))))


def find(record, clients):
    for client in clients:
        try:
            if local(client) and identity(client) == record:
                return client
        except OSError:
            pass
    return None


def pegasus_client(record, clients):
    matches = []
    for client in clients:
        try:
            if (local(client) and client['pid'] == record['pid']
                    and start(client['pid']) == record['start']
                    and executable(client['pid']) in PEGASUS
                    and environment(client['pid']).get('TABLET_PEGASUS_TOKEN') == record['token']):
                matches.append(client)
        except (OSError, KeyError):
            pass
    return matches[0] if len(matches) == 1 else None


class Games:
    def __init__(self, hypr, dispatch):
        self.hypr, self.dispatch = hypr, dispatch
        self.pending = None
        self.error = ''

    def launcher(self):
        return pegasus_client(read('pegasus.json'), self.hypr('clients'))

    def game(self):
        record = read('launch.json')
        pegasus = read('pegasus.json')
        if record.get('token') != pegasus.get('token') or not record.get('game'):
            return None
        return find(record['game'], self.hypr('clients'))

    def launch(self):
        if self.pending:
            return
        target = self.game() or self.launcher()
        if target:
            self.dispatch('focuswindow', 'address:' + target['address'])
            return
        old = read('pegasus.json')
        if old:
            try:
                if start(old['pid']) == old['start']:
                    raise RuntimeError('Tablet Pegasus is still busy or unmapped; no duplicate started')
            except (OSError, KeyError):
                pass
        # Pegasus can be single-instance. Never redirect an existing desktop UI.
        if any(c.get('class', '').startswith(('pegasus-fe', 'org.pegasus-frontend')) for c in self.hypr('clients')):
            raise RuntimeError('Close desktop Pegasus before opening its tablet instance')
        token = uuid.uuid4().hex
        self.pending = {'token': token, 'previous': [c['address'] for c in self.hypr('clients')],
                        'deadline': time.monotonic() + 20}
        self.dispatch('exec', '[workspace name:' + WORKSPACE + ' silent] env TABLET_PEGASUS_TOKEN=' + token + ' pegasus-fe')

    def tick(self):
        if not self.pending:
            return
        matches = []
        for client in self.hypr('clients'):
            try:
                if (local(client) and client['address'] not in self.pending['previous']
                        and executable(client['pid']) in PEGASUS
                        and environment(client['pid']).get('TABLET_PEGASUS_TOKEN') == self.pending['token']):
                    matches.append(client)
            except OSError:
                pass
        if len(matches) == 1:
            client = matches[0]
            write('pegasus.json', dict(pid=client['pid'], start=start(client['pid']), token=self.pending['token']))
            self.pending = None
        elif len(matches) > 1 or time.monotonic() >= self.pending['deadline']:
            self.pending = None
            self.error = 'Tablet Pegasus launch was not uniquely verified; no existing window was moved'

    def status(self):
        self.tick()
        record = read('launch.json')
        current = read('pegasus.json')
        valid = record.get('token') == current.get('token') and bool(current)
        owner = record.get('owner', record.get('caller', {}))
        try:
            alive = start(owner['pid']) == owner['start']
        except (OSError, KeyError):
            alive = False
        error = record.get('error', '') if valid else ''
        if valid and not alive and record.get('phase') != 'done':
            error = error or 'Game worker exited before completion; the game may still be running. Launch receipt retained.'
        return {'pegasusRunning': bool(self.launcher()), 'gameRunning': bool(self.game()),
                'gameLaunching': valid and alive and record.get('phase') in ('launching', 'returning'),
                'gamesLaunching': bool(self.pending), 'gamesError': self.error or error}


def clients():
    result = subprocess.run(['hyprctl', 'clients', '-j'], check=True, capture_output=True, text=True, timeout=5)
    return json.loads(result.stdout)


def authorized_game(client, command, owner, previous):
    if not local(client) or client['address'] in previous:
        return False
    if command[0] == 'steam-session':
        if len(command) != 2 or not command[1].isdigit():
            return False
        values = environment(client['pid'])
        return command[1] in (values.get('SteamAppId'), values.get('SteamGameId'))
    return descendant(client['pid'], owner)


def command_hash(command):
    return hashlib.sha256(json.dumps(command).encode()).hexdigest()


def launch(command):
    """Metadata wrapper: desktop launches are exact passthrough, tablet launches keep a receipt."""
    pegasus = read('pegasus.json')
    try:
        authorized = (pegasus and descendant(os.getpid(), pegasus)
                      and executable(pegasus['pid']) in PEGASUS
                      and environment(pegasus['pid']).get('TABLET_PEGASUS_TOKEN') == pegasus['token'])
    except (OSError, KeyError):
        authorized = False
    if not authorized:
        os.execvp(command[0], command)
    os.umask(0o077)
    previous = read('launch.json')
    # A dead worker is not proof that its child/game stopped. Keep unresolved
    # receipts as an explicit recovery barrier, even before window verification.
    if previous and previous.get('phase') != 'done':
        raise RuntimeError('Previous tablet game launch is unresolved; inspect its receipt before another launch')
    owner = previous.get('owner', {})
    try:
        busy = start(owner['pid']) == owner['start']
    except (OSError, KeyError):
        busy = False
    if busy or (previous.get('game') and find(previous['game'], clients())):
        raise RuntimeError('A tablet game session is already running')
    # Prevent a second wrapper from overwriting a game's identity.
    import fcntl
    with (root() / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        request = uuid.uuid4().hex
        record = dict(token=pegasus['token'], request=request, command=command_hash(command),
                      phase='launching', game=None,
                      caller={'pid': os.getpid(), 'start': start(os.getpid())})
        write('launch.json', record)
        # The routed worker is independent of Pegasus's lifetime. The graphical
        # launcher verifies its descendant window, not a guessed active window.
        result = subprocess.run(['project-workspace-exec', 'env',
                                 'PROJECT_OBJECT_WORKSPACE_NAME=' + WORKSPACE,
                                 sys.executable, str(Path(__file__).resolve()),
                                 '--worker', request, '--', *command],
                                env=dict(os.environ, PROJECT_OBJECT_WORKSPACE_NAME=WORKSPACE), check=False)
        while True:
            current = read('launch.json')
            if current.get('request') != request:
                raise RuntimeError('Game launch receipt was replaced')
            if current.get('phase') == 'done':
                return current.get('code', 1)
            owner = current.get('owner', current['caller'])
            try:
                alive = start(owner['pid']) == owner['start']
            except OSError:
                alive = False
            if not alive or (result.returncode and 'owner' not in current):
                raise RuntimeError('Game worker unavailable; no application was closed')
            time.sleep(.25)


def worker(command, request):
    record = read('launch.json')
    if (record.get('request') != request or record.get('command') != command_hash(command)
            or record.get('phase') != 'launching' or record.get('owner')):
        raise RuntimeError('Invalid tablet game worker request')
    caller = record['caller']
    if start(caller['pid']) != caller['start']:
        raise RuntimeError('Tablet game caller was replaced')
    os.umask(0o077)
    record['owner'] = {'pid': os.getpid(), 'start': start(os.getpid())}
    write('launch.json', record)
    previous = [c['address'] for c in clients()]
    child = None
    try:
        child = subprocess.Popen(command)
        owner = {'pid': child.pid, 'start': start(child.pid)}
        record['child'] = owner
        write('launch.json', record)
        deadline = time.monotonic() + 195
        while True:
            current = clients()
            if not record['game']:
                matches = []
                for client in current:
                    try:
                        if authorized_game(client, command, owner, previous):
                            matches.append(client)
                    except OSError:
                        pass
                if len(matches) == 1:
                    record.update(game=identity(matches[0]), phase='playing')
                    write('launch.json', record)
                elif len(matches) > 1:
                    raise RuntimeError('Multiple game windows; tablet handoff refused')
                elif child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Game window could not be verified; no app was closed')
            elif not find(record['game'], current):
                record.update(phase='returning', game=None)
                write('launch.json', record)
                break
            time.sleep(.25)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(phase='unavailable', error=str(error))
        write('launch.json', record)
        subprocess.run(['notify-send', 'Tablet game handoff unavailable', str(error)], check=False)
    # Never terminate a game/Steam cleanup worker. Returning from this command
    # (not just a launcher exit) is what lets Pegasus restore its frontend.
    code = child.wait() if child else 1
    record.update(phase='done', game=None, code=code)
    write('launch.json', record)
    return code


if __name__ == '__main__':
    command = sys.argv[1:]
    request = None
    if command[:1] == ['--worker'] and len(command) >= 3:
        request, command = command[1], command[2:]
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        raise SystemExit('Usage: tablet-game-launch -- COMMAND [ARG ...]')
    try:
        raise SystemExit(worker(command, request) if request else launch(command))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
