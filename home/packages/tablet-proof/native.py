#!/usr/bin/env python3
"""Resume a dedicated tablet workspace without borrowing laptop applications."""
import fcntl
from hyprland_control import config_path, guarded_layer, setting_args, literal, uses_lua
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('tablet_proof', os.environ.get('TABLET_PROOF_SOURCE', str(Path(__file__).with_name('controller.py'))))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
WORKSPACE = 'tablet-trial'
media_spec = importlib.util.spec_from_file_location('tablet_media_client', os.environ.get(
    'TABLET_MEDIA_CLIENT_SOURCE', str(Path(__file__).with_name('media') / 'client.py')))
media_module = importlib.util.module_from_spec(media_spec)
media_spec.loader.exec_module(media_module)
games_spec = importlib.util.spec_from_file_location('tablet_gaming', os.environ.get(
    'TABLET_GAMING_SOURCE', str(Path(__file__).with_name('gaming.py'))))
gaming = importlib.util.module_from_spec(games_spec)
games_spec.loader.exec_module(gaming)
stremio_spec = importlib.util.spec_from_file_location('tablet_stremio', os.environ.get(
    'TABLET_STREMIO_SOURCE', str(Path(__file__).with_name('stremio.py'))))
stremio_module = importlib.util.module_from_spec(stremio_spec)
stremio_spec.loader.exec_module(stremio_module)


def state_file():
    root = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'tablet-native'
    if root.is_symlink():
        raise RuntimeError('Unsafe tablet state directory')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.getuid():
        raise RuntimeError('Tablet state belongs to another user')
    root.chmod(0o700)
    return root / 'session.json'


def memory():
    try:
        value = json.loads(state_file().read_text())
        if not isinstance(value, dict):
            raise ValueError('Invalid tablet resume state')
        return value
    except FileNotFoundError:
        return {}


def store(value):
    path = state_file()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def identity(client):
    return {**{k: client[k] for k in ('address', 'pid', 'class', 'stableId')},
            'start': p.start_time(client['pid'])}


def eligible(client):
    return (client.get('class') == 'vivaldi-stable' and client.get('mapped')
            and client.get('workspace', {}).get('name') == WORKSPACE
            and not any(client.get(k) for k in ('xwayland', 'floating', 'pinned', 'grouped'))
            and bool(re.fullmatch(r'[0-9a-f]+', client.get('stableId', ''))))


def saved_browser(saved, clients):
    """Resume only tablet-local identities; never search laptop workspaces."""
    source = saved.get('source')
    if source:
        if saved.get('instance') != os.environ['HYPRLAND_INSTANCE_SIGNATURE']:
            return None
        for c in clients:
            try:
                if eligible(c) and identity(c) == source:
                    return c
            except OSError:
                pass
        return None  # A moved/closed/recycled source is not substituted.
    candidates = [c for c in clients if eligible(c)]
    return candidates[0] if len(candidates) == 1 else None


def normal_profile_processes(processes):
    """Do not mistake a custom-profile window for a warm normal profile."""
    default = (Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'vivaldi').resolve()
    result = {}
    for pid, start in processes.items():
        args = [os.fsdecode(v) for v in (Path(f'/proc/{int(pid)}/cmdline')).read_bytes().split(b'\0') if v]
        if len(args) == 1:
            args = shlex.split(args[0])  # Vivaldi's rewritten process title.
        directory = None
        for index, arg in enumerate(args[1:], 1):
            if re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', arg):
                break  # Never inspect/retain page arguments.
            if arg.startswith('--user-data-dir='):
                directory = arg.split('=', 1)[1]
            elif arg == '--user-data-dir':
                directory = args[index + 1] if index + 1 < len(args) else ''
        if directory is None or (directory and Path(directory).resolve() == default):
            if p.start_time(pid) == start:
                result[pid] = start
    return result


class Native(p.Proof):
    def __init__(self, media=None, **kwargs):
        super().__init__(**kwargs)
        self.media = media if media is not None else media_module.Media()
        self.media_paired = False
        self.media_status_at = 0
        self.orientation = None
        self.stage = None
        self.session = None
        self.owner = None
        self.automatic = os.environ.get('TABLET_NATIVE_AUTOMATIC') == '1'
        self.rotation_enabled = False
        self.source = None
        self.pending = None
        self.capabilities = None
        self.saved = {}
        self.resume_overview = False
        self.games = gaming.Games(lambda *args: p.hypr(*args), lambda *args: p.dispatch(*args))
        self.stremio = stremio_module.Stremio(lambda *args: p.hypr(*args), lambda *args: p.dispatch(*args))
        self.stremio_waiting = False
        self.active_app = 'vivaldi'
        self.games_target = None
        self.games_requested = False
        self.games_focus_lost_at = None
        self.posture = None
        self.close_requested = None
        self.game_card = None
        self.game_card_role = None

    def panel(self):
        panel = next((m for m in p.hypr('monitors') if m['name'] == 'eDP-1'), None)
        try:
            headless = Path('/run/headless-mode/state').read_text().strip() != 'off'
        except FileNotFoundError:
            headless = False
        if (headless or not panel or panel.get('disabled') or not panel.get('dpmsStatus', True)
                or panel.get('specialWorkspace', {}).get('id', 0)):
            raise RuntimeError('Use the awake internal display without a special workspace')
        return panel

    POSTURE_OPTIONS = {'gestures:workspace_swipe_touch': (0, (0, 1)),
                       'input:follow_mouse': (0, (0, 1, 2, 3))}

    def config_token(self):
        config = config_path()
        stat = config.stat()
        return [str(config.resolve()), stat.st_mtime_ns, stat.st_size]

    def posture_value(self, option):
        reply = json.loads(p.run('hyprctl', 'getoption', option, '-j'))
        value = reply.get('int')
        if value is None and type(reply.get('bool')) is bool:
            value = int(reply['bool'])
        if type(value) is not int or value not in self.POSTURE_OPTIONS[option][1]:
            raise RuntimeError('Unsupported tablet interaction baseline: ' + option)
        return value

    def acquire_posture(self):
        barrier = getattr(self, 'before_interaction_acquire', None)
        if barrier:
            barrier()
        baseline = {key: self.posture_value(key) for key in self.POSTURE_OPTIONS}
        lease = {'config': self.config_token(), 'baseline': baseline, 'applied': []}
        self.posture = lease
        self.record['posture'] = lease
        self.journal()
        if barrier:
            barrier()  # Recheck after the synchronous baseline reads/journal, before writes.
        for key, (desired, _) in self.POSTURE_OPTIONS.items():
            if baseline[key] == desired:
                continue
            lease['applied'].append(key)  # Journal intent before a potentially interrupted IPC.
            self.journal()
            if p.run('hyprctl', *setting_args(key, desired)) != 'ok' or self.posture_value(key) != desired:
                raise RuntimeError('Could not acquire tablet interaction setting: ' + key)

    def restore_posture(self, record=None):
        record = self.record if record is None else record
        lease = record.get('posture') if record else None
        if not lease:
            return
        baseline, applied, token = lease.get('baseline'), lease.get('applied'), lease.get('config')
        if (not isinstance(token, list) or len(token) != 3 or not isinstance(token[0], str)
                or any(type(value) is not int for value in token[1:])
                or not isinstance(baseline, dict) or set(baseline) != set(self.POSTURE_OPTIONS)
                or not isinstance(applied, list) or any(not isinstance(key, str) for key in applied)
                or len(set(applied)) != len(applied)
                or any(key not in self.POSTURE_OPTIONS for key in applied)
                or any(type(baseline[key]) is not int or baseline[key] not in bounds
                       for key, (_, bounds) in self.POSTURE_OPTIONS.items())):
            raise RuntimeError('Invalid tablet interaction recovery record; retained')
        # A reload/deployment owns its new baseline. Never replay old settings
        # into that generation or override a nonmatching live external change.
        if not record.get('config_changed') and lease.get('config') == self.config_token():
            for key in list(reversed(applied)):
                if self.posture_value(key) == self.POSTURE_OPTIONS[key][0]:
                    if p.run('hyprctl', *setting_args(key, baseline[key])) != 'ok':
                        raise RuntimeError('Tablet interaction restoration deferred: ' + key)
                    if self.posture_value(key) != baseline[key]:
                        raise RuntimeError('Tablet interaction restoration not verified: ' + key)
                applied.remove(key)
                if record is self.record:
                    self.journal()
        record.pop('posture', None)
        if record is self.record:
            self.posture = None
            self.journal()

    def journal(self):
        if self.record and self.posture is not None:
            self.record['posture'] = self.posture
        if self.record and self.session is not None:
            self.record.update(native=True, automatic=self.automatic,
                               rotation_enabled=self.rotation_enabled, owner=self.owner,
                               tablet_session=self.session)
        super().journal()

    def owned_processes(self):
        return (*super().owned_processes(), self.orientation, self.stage)

    def child_role(self, process):
        if process is self.orientation:
            return 'orientation'
        if process is self.stage:
            return 'stage'
        return super().child_role(process)

    def ipc(self, process, target, method, *args):
        if not process or process.poll() is not None:
            raise RuntimeError('Tablet presentation process is unavailable')
        return p.run('quickshell', 'ipc', '--pid', str(process.pid), 'call', target, method, *args)

    def layer_opaque(self, process, level):
        panel = self.panel()
        width, height = panel['width'], panel['height']
        if panel.get('transform', 0) % 2:
            width, height = height, width
        matching = [layer for layer in p.hypr('layers').get('eDP-1', {}).get('levels', {}).get(level, [])
                    if layer.get('pid') == process.pid and layer.get('namespace') == 'tablet-rotation-fade']
        return (len(matching) == 1 and matching[0].get('alpha', 0) >= .999
                and matching[0].get('w', 0) >= int(width / panel.get('scale', 1))
                and matching[0].get('h', 0) >= int(height / panel.get('scale', 1)))

    def cover(self, label=None, allow_stopping=False):
        if label is not None:
            self.ipc(self.stage, 'tabletStage', 'cover', label)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and (allow_stopping or not self.stopping):
            try:
                state = json.loads(self.ipc(self.stage, 'tabletStage', 'status'))
                if state.get('cover') and state.get('backdrop') and self.layer_opaque(self.stage, '3') and self.layer_opaque(self.stage, '1'):
                    return
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                pass
            time.sleep(.025)
        raise RuntimeError('Tablet Home cover did not render; no uncovered workspace transition allowed')

    def start_stage(self, allow_stopping=False):
        if not guarded_layer('tablet-rotation-fade'):
            raise RuntimeError('Tablet entry requires the installed guarded no-animation policy')
        environment = dict(os.environ, TABLET_STAGE_PRESENTATION_ONLY='1',
                           TABLET_STAGE_OWNER_PID=str(os.getpid()),
                           TABLET_STAGE_OWNER_START=self.owner['start'],
                           TABLET_STAGE_ASSETS=str(Path(os.environ['TABLET_PROOF_QML']).parent))
        with (p.runtime() / 'stage.log').open('a') as log:
            self.stage = subprocess.Popen(['quickshell', '--path', os.environ['TABLET_STAGE_QML']],
                                          env=environment, stdout=log, stderr=log)
        self.journal()
        self.cover(allow_stopping=allow_stopping)

    def setup(self, address):
        root = Path(os.environ['XDG_RUNTIME_DIR'])
        legacy = any((root / name / 'recovery.json').exists() for name in ('tablet-chat', 'tablet-iterate'))
        workspace = root / 'tablet-workspace.json'
        old = json.loads(workspace.read_text()) if workspace.exists() else {}
        if not isinstance(old, dict) or legacy or old.get('enabled') or old.get('exit_pending'):
            raise RuntimeError('Close/recover the old tablet session first')
        if (p.runtime() / 'recovery.json').exists():
            raise RuntimeError('Previous tablet session needs recovery')
        current = p.hypr('activeworkspace')
        self.panel()
        if current.get('monitor') != 'eDP-1':
            raise RuntimeError('Tablet entry cannot take focus from an external display')
        destination = next((w for w in p.hypr('workspaces') if w['name'] == WORKSPACE), None)
        if destination and destination.get('monitor') != 'eDP-1':
            raise RuntimeError('Tablet workspace is on another display; no apps/workspace were moved')
        self.saved = memory()
        focus = p.hypr('activewindow')
        self.owner = {'pid': os.getpid(), 'start': p.start_time(os.getpid())}
        self.session = {'workspace': WORKSPACE, 'origin': p.safe_workspace(current['name']),
                        'focus': {k: focus.get(k) for k in ('address', 'pid', 'class', 'stableId')},
                        'entered': False, 'origin_empty': current.get('windows') == 0}
        # Starting while already in the tablet workspace retains its last
        # verified laptop return point, never inventing a desktop destination.
        previous = self.saved.get('return', {})
        if current['name'] == WORKSPACE and self.saved.get('instance') == os.environ['HYPRLAND_INSTANCE_SIGNATURE'] and previous:
            self.session.update(origin=p.safe_workspace(previous['origin']), focus=previous['focus'],
                                origin_empty=bool(previous.get('origin_empty', False)))
        clients = p.hypr('clients')
        source = saved_browser(self.saved, clients)
        if address:
            source = next((c for c in clients if eligible(c) and c['address'] == address), None)
            if not source:
                raise RuntimeError('Explicit browser must already live in the tablet workspace; laptop apps are never borrowed')
        self.record = {'home_only': True, 'instance': os.environ['HYPRLAND_INSTANCE_SIGNATURE'],
                       'workspace': WORKSPACE, 'origin': WORKSPACE, 'focus': {}}
        self.journal()
        self.start_stage()  # Rendered opaque Home BEFORE switching workspace.
        self.acquire_posture()
        self.session['entered'] = True
        self.journal()
        p.dispatch('workspace', 'name:' + WORKSPACE)
        self.guard()
        resume_games = self.saved.get('activeApp') == 'games'
        resume_stremio = self.saved.get('activeApp') == 'stremio'
        if source and not resume_games and not resume_stremio:
            self.attach(source)
        elif source:
            self.source = identity(source)
        if resume_games:
            self.active_app = 'games'
            self.games_requested = not self.saved.get('home', True)
            target = self.games.game() or self.games.launcher()
            if target:
                p.dispatch('focuswindow', 'address:' + target['address'])
                self.games_target = identity(target)
        if resume_stremio:
            self.active_app = 'stremio'
            target = self.stremio.window()
            if target and not self.saved.get('home', True):
                self.owned_window_action(self.card_sources()['stremio'], 'focus')
        self.keyboard.start()
        self.values = self.controls.read()
        available = bool(self.source or self.games_target or self.stremio.window())
        self.home = bool(self.saved.get('home', True)) if available else True
        self.drawer = bool(self.saved.get('drawer', False))
        self.resume_overview = bool(self.saved.get('overview', False)) and available
        self.rotation_enabled = True
        self.record['media_suspended'] = False
        self.journal()
        if self.source and self.active_app == 'vivaldi':
            try:
                self.media.resume(self.record)  # Unblock only; never auto-play.
            except (OSError, ValueError, RuntimeError):
                self.error = 'Pair the tablet media companion to pause web media on exit.'
        self.remember()
        with (p.runtime() / 'orientation.log').open('a') as log:
            self.orientation = subprocess.Popen([os.environ['TABLET_NATIVE_ORIENTATION_BIN'], 'daemon'], stdout=log, stderr=log)
        self.journal()

    def fullscreen_peer_allowed(self, client):
        return any(target and identity(client) == identity(target)
                   for target in (self.games.game(), self.games.launcher(), self.stremio.window()))

    def attach(self, client):
        if not eligible(client):
            raise RuntimeError('Only tablet-local native browser windows may be presented')
        p.dispatch('focuswindow', 'address:' + client['address'])
        self.lease(client['address'])
        self.source = identity(client)
        self.journal()

    def home_record(self):
        # A disappeared client no longer needs a fullscreen lease, but the
        # independent posture/game leases and session recovery still do.
        keep = {key: self.record[key] for key in ('posture', 'game_presentation', 'config_changed')
                if self.record and key in self.record}
        return dict(keep, home_only=True, instance=os.environ['HYPRLAND_INSTANCE_SIGNATURE'],
                    workspace=WORKSPACE, origin=WORKSPACE, focus={})

    def registered_window(self, record, clients):
        if not record:
            return None
        match = next((c for c in clients if all(c.get(k) == record[k]
                     for k in ('address', 'pid', 'class', 'stableId'))), None)
        if not match:
            return None
        try:
            return match if p.start_time(match['pid']) == record['start'] else None
        except (FileNotFoundError, ProcessLookupError):
            # /proc confirms the old process vanished even if the compositor
            # still has its final client snapshot. Permission/read errors must
            # propagate instead: they are not proof of disappearance.
            return None

    def refresh_browser(self):
        if not self.source:
            return None
        match = self.registered_window(self.source, p.hypr('clients'))
        # Moved/unmapped/ineligible is not disappeared: retain ownership/lease.
        if match:
            return match
        self.source = None
        if not self.record.get('home_only'):
            self.record = self.home_record()
        if self.active_app == 'vivaldi':
            self.home = True
            self.drawer = False
            self.resume_overview = False
        self.journal()
        self.remember()
        return None

    def workspace_guard(self):
        current = p.hypr('activeworkspace')
        panel = self.panel()
        if (self.record['instance'] != os.environ['HYPRLAND_INSTANCE_SIGNATURE']
                or current.get('monitor') != 'eDP-1' or current.get('name') != WORKSPACE):
            raise RuntimeError('Tablet workspace is no longer foreground')
        return None, panel

    def guard(self):
        self.refresh_browser()
        if not self.record.get('home_only'):
            return super().guard()
        return self.workspace_guard()

    def card_state(self):
        """Existence retains cards; eligibility separately permits capture/close."""
        clients = p.hypr('clients')
        browser = self.registered_window(self.source, clients)
        game = self.games.game()
        previous = self.registered_window(self.game_card, clients)
        if not game and self.game_card_role == 'game' and previous:
            target, role = previous, 'game'  # Never replace a live ineligible game with its library.
        else:
            target = game or self.games.launcher() or previous
            role = 'game' if game else ('library' if target and target is not previous else self.game_card_role)
        if target:
            try:
                self.game_card, self.game_card_role = identity(target), role
            except (FileNotFoundError, ProcessLookupError):
                self.game_card = self.game_card_role = None
                target = None
        else:
            self.game_card = self.game_card_role = None
        stremio = self.stremio.registered()
        stremio_identity = None
        if stremio:
            try:
                stremio_identity = identity(stremio)
            except (FileNotFoundError, ProcessLookupError):
                stremio = None
        lifetimes, sources = {}, {}
        for app, client, registered in (('vivaldi', browser, self.source), ('games', target, self.game_card),
                                        ('stremio', stremio, stremio_identity)):
            if not client or not registered:
                continue
            descriptor = dict(registered, instance=os.environ['HYPRLAND_INSTANCE_SIGNATURE'], workspace=WORKSPACE,
                              floating=bool(client.get('floating')))
            lifetimes[app] = descriptor
            allowed = (eligible(client) if app == 'vivaldi' else bool(self.stremio.window())
                       if app == 'stremio' else gaming.local(client, allow_floating=True))
            if app == 'vivaldi' and not self.record.get('home_only'):
                descriptor = dict(descriptor, tag=self.record['tag'])
                allowed = allowed and self.record['tag'] in [tag.rstrip('*') for tag in client.get('tags', [])]
            if allowed:
                sources[app] = descriptor
        return lifetimes, sources

    def card_sources(self):
        return self.card_state()[1]

    def owned_window_action(self, record, action):
        """Resolve lifetime + workspace and operate in one native IPC callback."""
        if action not in ('focus', 'close') or not uses_lua():
            raise RuntimeError('Switcher window operations require the native Lua session')
        self.workspace_guard()
        if (record.get('instance') != os.environ['HYPRLAND_INSTANCE_SIGNATURE']
                or record.get('workspace') != WORKSPACE
                or not re.fullmatch('0x[0-9a-f]+', str(record.get('address', '')))
                or not re.fullmatch('[0-9a-f]+', str(record.get('stableId', '')))
                or type(record.get('pid')) is not int or type(record.get('floating')) is not bool):
            raise RuntimeError('Invalid switcher window identity')
        code = ('local w=hl.get_window(' + literal('address:' + record['address']) + ');'
                'assert(w and w.mapped and w.pid==' + literal(record['pid'])
                + ' and w.class==' + literal(record['class'])
                + ' and string.format("%x",w.stable_id)==' + literal(record['stableId'])
                + ' and w.workspace and w.workspace.name==' + literal(WORKSPACE)
                + ' and not w.pinned and not w.group and w.floating==' + literal(record['floating'])
                + ',"Tablet window changed");'
                + ('local tagged=false;for _,tag in ipairs(w.tags) do if tag:gsub("%*$", "")== '
                   + literal(record['tag']) + ' then tagged=true end end;assert(tagged,"Tablet ownership changed");'
                   if record.get('tag') else '')
                + 'assert(hl.get_active_workspace().name==' + literal(WORKSPACE)
                + ' and hl.get_active_monitor().name=="eDP-1","Tablet focus changed");'
                'local result=hl.dispatch(' + ('hl.dsp.focus({window=w})' if action == 'focus'
                                             else 'hl.dsp.window.close({window=w})')
                + ');assert(result.ok,"Tablet window request rejected")')
        if p.run('hyprctl', 'eval', code) != 'ok':
            raise RuntimeError('Tablet window operation rejected')

    def switcher_target(self, value):
        if not uses_lua():
            raise RuntimeError('Switcher operations require the native Lua session')
        self.refresh_browser()
        self.workspace_guard()
        if not isinstance(value, dict) or set(value) != {'app', 'window'}:
            raise RuntimeError('Explicit switcher card identity required')
        app, target = value['app'], value['window']
        if app not in ('vivaldi', 'games', 'stremio') or self.card_sources().get(app) != target or not target:
            raise RuntimeError('Exact tablet window is unavailable or changed; no replacement opened or closed')
        return app, target

    def resume_app(self, value):
        app, target = self.switcher_target(value)
        self.error = ''
        if app == 'stremio':
            self.select_stremio(expected=target)
        elif app == 'games' and self.active_app == 'games':
            self.owned_window_action(target, 'focus')
            lease = self.record.get('game_presentation')
            if lease and lease['window'] == identity(target):
                lease['presented'] = False
            self.games_target = None
            self.games_requested = True
            self.home = self.drawer = self.resume_overview = False
            self.remember()
        elif app == 'games':
            self.select_games(expected=target)
        elif self.record.get('home_only') or self.active_app != 'vivaldi':
            self.select_browser(expected=target)
        else:
            self.owned_window_action(target, 'focus')
            self.home = self.drawer = self.resume_overview = False
            self.remember()
        return self.state()

    def dismiss_app(self, value):
        app, target = self.switcher_target(value)
        self.error = ''
        if app != 'vivaldi' and not self.record.get('home_only'):
            self.pause_media()
            self.release_window()
            self.record = self.home_record()
            self.journal()
        if app != 'games':
            self.release_game_presentation()
        # Reveal the selected original before a normal close request, so a
        # beforeunload/modal confirmation is usable, never hidden by Home/cards.
        # No launch, PID kill or force-close path exists here.
        self.owned_window_action(target, 'focus')
        self.active_app = app
        self.games_requested = False
        self.games_target = {k: target[k] for k in ('address', 'pid', 'class', 'stableId', 'start')} if app == 'games' else None
        self.home = self.drawer = self.resume_overview = False
        self.keyboard.hide()
        self.close_requested = {'app': app, 'window': target, 'until': time.monotonic() + 5}
        self.remember()
        self.owned_window_action(target, 'close')
        return self.state()

    def remember(self):
        if self.session is None:
            return
        store({'instance': os.environ['HYPRLAND_INSTANCE_SIGNATURE'], 'source': self.source,
               'activeApp': self.active_app,
               'home': False if self.active_app == 'games' and self.games_requested else self.home,
               'drawer': self.drawer, 'overview': self.resume_overview,
               'return': {key: self.session[key] for key in ('origin', 'focus', 'origin_empty')}})

    def browser_policy(self):
        spec = importlib.util.spec_from_file_location('tablet_window_apps', os.environ['TABLET_WINDOW_APPS_SOURCE'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        registry = json.loads(Path(os.environ['TABLET_APPS_REGISTRY']).read_text())
        capabilities = module.WindowApps(p.runtime(), registry, p.hypr, p.dispatch, p.start_time)
        # Native tablet launch is warm-only: require mapped compatible windows
        # on THIS compositor. No cold launch and no probing other sessions'
        # background browsers to infer that a launch is safe.
        capabilities.browser_pids = lambda policy: set()
        return capabilities

    def launch_browser(self):
        if self.pending:
            return
        capabilities = self.browser_policy()
        verification = capabilities.require_compatible('browser')
        verification['processes'] = normal_profile_processes(verification['processes'])
        if not verification['processes']:
            raise RuntimeError('Open normal Vivaldi once before using its tablet launcher; custom profiles are not adopted or restarted')
        registration = self.media.prepare()
        marker = registration['marker']
        previous = [c['address'] for c in p.hypr('clients')]
        capabilities.verify_launch('browser', verification)
        policy = capabilities.registry['browser']
        command = [*policy['command'], *policy.get('openArguments', []), registration['url']]
        # Target the persistent tablet workspace at creation. The nonce can
        # confirm only the NEW window; no laptop window is moved to fit it.
        try:
            p.dispatch('exec', {'command': shlex.join(command), 'rules': {'workspace': 'name:' + WORKSPACE + ' silent'}})
        except (OSError, RuntimeError, subprocess.SubprocessError):
            raise RuntimeError('Tablet browser launch failed') from None  # Do not log registration URLs.
        self.capabilities = capabilities
        self.pending = {'marker': marker, 'nonce': registration['nonce'], 'previous': previous,
                        'authorities': verification['processes'], 'deadline': time.monotonic() + 15}

    def poll_launch(self):
        if not self.pending:
            return
        pending = self.pending
        matches = [c for c in p.hypr('clients') if c['address'] not in pending['previous']
                   and pending['marker'] in c.get('title', '') and c.get('class') == 'vivaldi-stable' and c.get('mapped')]
        if len(matches) > 1:
            self.pending = None
            self.error = 'Ambiguous tablet launch; no browser was adopted'
        elif matches:
            client = matches[0]
            self.pending = None
            if not eligible(client) or not self.capabilities.from_authorized_process(client['pid'], pending['authorities']):
                self.error = 'New browser did not arrive safely in the tablet workspace; no existing window was moved'
                return
            self.attach(client)
            try:
                self.media.bind(self.record, pending['nonce'])
            except (OSError, ValueError, RuntimeError):
                self.error = 'Tablet browser opened, but its media companion could not be paired.'
                return
            self.home = False
            self.remember()
        elif time.monotonic() >= pending['deadline']:
            self.pending = None
            self.error = 'Tablet browser launch could not be verified; no existing window was adopted'

    def select_stremio(self, expected=None):
        if expected is not None and self.card_sources().get('stremio') != expected:
            raise RuntimeError('Exact tablet Stremio is unavailable; no replacement opened')
        self.cover('Opening Stremio…')
        try:
            self.release_game_presentation()
            if not self.record.get('home_only'):
                self.pause_media()
                self.release_window()
                self.record = self.home_record()
                self.journal()
            if expected is not None:
                self.owned_window_action(expected, 'focus')
            else:
                self.stremio.launch()
                target = self.card_sources().get('stremio')
                if target:
                    self.owned_window_action(target, 'focus')
            status = self.stremio.status()
            self.stremio_waiting = status['stremioLaunching']
            self.active_app = 'stremio'
            self.games_requested = False
            self.games_target = None
            self.home = not bool(self.stremio.window())
            self.drawer = False
            self.remember()
        finally:
            self.ipc(self.stage, 'tabletStage', 'reveal')

    def poll_stremio(self):
        status = self.stremio.status()
        if self.active_app != 'stremio':
            return status
        target = self.stremio.window()
        if target:
            # Preserve foreign/modal focus. Only an already-focused exact root
            # can acquire its reversible presentation, never a background app.
            if p.hypr('activewindow').get('address') == target['address'] and not self.drawer:
                if not self.present_game(target):
                    return status
                if self.stremio_waiting:
                    self.home = False
                    self.stremio_waiting = False
                    self.remember()
        elif not status['stremioLaunching']:
            self.home = True
        return status

    def select_games(self, expected=None):
        if expected is not None and self.card_sources().get('games') != expected:
            raise RuntimeError('Exact tablet game/library is unavailable; no replacement opened')
        self.cover('Opening Pegasus…')
        try:
            lease = self.record.get('game_presentation')
            target = (self.games.game() or self.games.launcher()) if lease else None
            # Returning to the SAME lifetime must not demand its focus before
            # the explicit selection can restore focus. Keep its valid lease;
            # switching to another app/window still uses strict restoration.
            if target and lease and lease['window'] == identity(target):
                # Explicit return may re-present fullscreen if the compositor
                # exited it during foreign focus, without replacing originals.
                lease['presented'] = False
            else:
                self.release_game_presentation()
            if not self.record.get('home_only'):
                self.pause_media()
                self.release_window()
                self.record = {'home_only': True, 'instance': os.environ['HYPRLAND_INSTANCE_SIGNATURE'],
                               'workspace': WORKSPACE, 'origin': WORKSPACE, 'focus': {}}
                self.journal()
            self.active_app = 'games'
            self.games_target = None
            self.games_requested = True
            if expected is None:
                self.games.launch()
            else:
                self.owned_window_action(expected, 'focus')  # A card resume never launches a replacement.
            self.home = not bool(self.games.game() or self.games.launcher())
            self.drawer = False
            self.remember()
        finally:
            self.ipc(self.stage, 'tabletStage', 'reveal')

    def select_browser(self, expected=None):
        if expected is not None and self.card_sources().get('vivaldi') != expected:
            raise RuntimeError('Exact tablet browser is unavailable; no replacement opened')
        self.cover('Opening Vivaldi…')
        try:
            self.release_game_presentation()
            self.active_app = 'vivaldi'
            self.games_target = None
            self.games_requested = False
            if self.record.get('home_only') and self.source:
                client = gaming.find(self.source, p.hypr('clients'))
                if client and eligible(client):
                    if expected is not None:
                        self.owned_window_action(expected, 'focus')
                    self.attach(client)
                    self.media.resume(self.record)  # Ungate, never play.
                else:
                    if expected is not None:
                        raise RuntimeError('Exact browser changed during resume; no replacement opened')
                    self.source = None
            if not self.source:
                if expected is not None:
                    raise RuntimeError('Exact browser disappeared; no replacement opened')
                self.launch_browser()
            else:
                p.dispatch('focuswindow', 'address:' + self.source['address'])
                self.home = False
                self.drawer = False
            self.remember()
        finally:
            self.ipc(self.stage, 'tabletStage', 'reveal')

    def present_game(self, client):
        """Fullscreen only the exact verified tablet game; keep a reversible lease."""
        self.guard()
        if not gaming.find(gaming.identity(client), p.hypr('clients')):
            raise RuntimeError('Tablet game identity changed before presentation')
        if p.hypr('activewindow').get('address') != client['address']:
            raise RuntimeError('Tablet game lost focus before presentation')
        lease = self.record.get('game_presentation')
        if lease and lease['window'] != gaming.identity(client):
            self.release_game_presentation()
            lease = None
        if lease and lease.get('presented'):
            return True  # No repeated enforcement after the verified first handoff.
        if not lease:
            lease = {'window': gaming.identity(client), 'internal': client.get('fullscreen', 0),
                     'client': client.get('fullscreenClient', 0)}
            self.record['game_presentation'] = lease
            self.journal()  # Recovery evidence precedes the first mutation.
        if (client.get('fullscreen', 0), client.get('fullscreenClient', 0)) != (2, 2):
            p.dispatch('fullscreenstate', '2 2')
            if p.hypr('activewindow').get('address') != client['address']:
                raise RuntimeError('Game focus changed during fullscreen transition')
        current = gaming.find(lease['window'], p.hypr('clients'))
        panel = self.panel()
        width, height = panel['width'], panel['height']
        if panel.get('transform', 0) % 2:
            width, height = height, width
        scale = panel.get('scale', 1)
        presented = bool(current and current.get('fullscreen') == 2
                         and current.get('size') == [round(width / scale), round(height / scale)])
        if presented:
            lease['presented'] = True
            self.journal()
        return presented

    def release_game_presentation(self, activate=False):
        lease = self.record.get('game_presentation') if self.record else None
        if not lease:
            return
        # Ineligible is not destroyed: a moved, pinned or temporarily unmapped
        # exact window still owns this lease. Never erase its recovery evidence.
        client = next((c for c in p.hypr('clients') if identity(c) == lease['window']), None)
        if client:
            if not gaming.local(client, allow_floating=True):
                raise RuntimeError('Game presentation restore deferred for ineligible live window')
            if activate and p.hypr('activeworkspace').get('name') != WORKSPACE:
                if p.hypr('activeworkspace').get('monitor') != 'eDP-1':
                    raise RuntimeError('Explicit game recovery cannot take focus from another display')
                self.panel()
                self.cover(allow_stopping=True)
                p.dispatch('workspace', 'name:' + WORKSPACE)
            self.guard()
            if p.hypr('activewindow').get('address') != client['address']:
                if not activate:
                    raise RuntimeError('Game presentation restore needs its verified foreground window')
                p.dispatch('focuswindow', 'address:' + client['address'])
            if p.hypr('activewindow').get('address') != client['address']:
                raise RuntimeError('Game restore focus could not be verified')
            modes = (lease['internal'], lease['client'])
            if (client.get('fullscreen', 0), client.get('fullscreenClient', 0)) != modes:
                p.dispatch('fullscreenstate', f'{modes[0]} {modes[1]}')
                if p.hypr('activewindow').get('address') != client['address']:
                    raise RuntimeError('Game focus changed during restore')
        self.record.pop('game_presentation', None)
        self.journal()

    def poll_games(self):
        status = self.games.status()
        if self.active_app != 'games':
            return status
        # Tablet Pegasus keeps its real, game-specific loading window mapped.
        # Never substitute Home while its wrapper waits for the verified game.
        game = self.games.game()
        if not game and self.game_card_role == 'game' and self.registered_window(self.game_card, p.hypr('clients')):
            self.error = 'Tablet game is unavailable here; no library was substituted.'
            return status
        target = game or self.games.launcher()
        if target:
            if self.games_requested:
                self.home = False
            current = identity(target)
            if (status['gameRunning'] and current == self.games_target
                    and p.hypr('activewindow').get('address') == target['address']):
                if not self.present_game(target):
                    return status
            if current != self.games_target:
                # Handoff only while our workspace remains foreground. Never
                # follow a game or user to a different output/workspace.
                _, panel = self.guard()
                focus = p.hypr('activewindow')
                if (focus.get('address') != target['address']
                        and (self.drawer or panel.get('reserved', [0, 0, 0, 0])[3])):
                    return status  # A drawer/IME may own even an empty focus during handoff.
                known = [self.source, self.games_target]
                if focus and focus.get('address') != target['address'] and not any(
                        item and all(focus.get(k) == v for k, v in item.items() if k != 'start') for item in known):
                    self.error = 'Tablet game/library is not focused; swipe up for Home.'
                    return status  # Keep navigation; never reclaim unrelated focus.
                if focus.get('address') != target['address']:
                    p.dispatch('focuswindow', 'address:' + target['address'])
                if status['gameRunning'] and not self.present_game(target):
                    return status  # Renderer/compositor geometry may settle asynchronously.
                if not status['gameRunning']:
                    self.release_game_presentation()
                self.games_target = current
                self.journal()
                self.remember()
            if not self.home and p.hypr('activewindow').get('address') != target['address']:
                latest = self.games.status()
                if latest['gameLaunching'] or latest['gameRunning'] != status['gameRunning']:
                    return latest
                # Keep navigation through modal/owned focus transitions. Only
                # an empty focus may be repaired to the verified current target;
                # a nonempty foreign window is never reclaimed.
                if self.games_focus_lost_at is None:
                    self.games_focus_lost_at = time.monotonic()
                if (not self.drawer and not p.hypr('activewindow')
                        and time.monotonic() - self.games_focus_lost_at >= .25):
                    _, panel = self.guard()
                    verified = self.games.game() or self.games.launcher()
                    if (not panel.get('reserved', [0, 0, 0, 0])[3]
                            and verified and identity(verified) == current and not p.hypr('activewindow')):
                        p.dispatch('focuswindow', 'address:' + target['address'])
                self.error = 'Tablet game/library is not focused; swipe up for Home.'
                return latest
            self.games_focus_lost_at = None
            if self.error == 'Tablet game/library is not focused; swipe up for Home.':
                self.error = ''
        elif not status['gameLaunching'] and not status['gamesLaunching']:
            self.home = True
            self.games_target = None
        return status

    def state(self):
        browser = self.refresh_browser()
        _, panel = self.workspace_guard()
        games = self.poll_games() if not self.stopping else self.games.status()
        stremio = self.poll_stremio() if not self.stopping else self.stremio.status()
        if not self.stopping:
            self.poll_launch()
        leased = browser if not self.record.get('home_only') else None
        window = leased if leased and eligible(leased) and leased.get('monitor') == panel['id'] else None
        # State/confirmation observation must not require the root browser to
        # hold keyboard focus. Mutation/lease guards remain focus-checked.
        state = {'running': True, 'ready': self.ready, 'home': self.home, 'drawer': self.drawer,
                 'backend': {'pid': os.getpid(), 'start': p.start_time(os.getpid())},
                 'media': bool(window and window.get('fullscreenClient') == 2),
                 'keyboardInset': panel.get('reserved', [0, 0, 0, 0])[3],
                 'error': self.error, **self.values}
        if leased:
            state['source'] = {'address': leased['address'], 'pid': leased['pid']}
        lifetimes, sources = self.card_state()
        if self.close_requested and (sources.get(self.close_requested['app']) != self.close_requested['window']
                                     or time.monotonic() >= self.close_requested['until']):
            self.close_requested = None
        if self.source and self.active_app == 'vivaldi' and time.monotonic() >= self.media_status_at:
            self.media_status_at = time.monotonic() + 1
            try:
                self.media_paired = bool(self.media.status(self.record).get('registered'))
            except (OSError, ValueError, RuntimeError):
                self.media_paired = False
        return dict(state, native=True, automatic=self.automatic, workspace=WORKSPACE,
                    mediaPaired=self.media_paired,
                    browserAvailable=True, browserRunning=bool(self.source),
                    activeApp=self.active_app, **games, **stremio, stremioHidden=self.stremio.hidden(),
                    launching=bool(self.pending) or games['gamesLaunching'] or games['gameLaunching'] or stremio['stremioLaunching'],
                    resumeOverview=self.resume_overview, cardSources=sources, cardLifetimes=lifetimes,
                    closePending=self.close_requested['app'] if self.close_requested else '')

    def action_guard(self):
        # View/control actions do not mutate the client lease. Keep them usable
        # while a registered window is temporarily unavailable or showing a modal.
        return self.workspace_guard()

    def action(self, command, value=None):
        if command == 'dismiss-app':
            return self.dismiss_app(value)
        if command == 'resume-app':
            return self.resume_app(value)
        self.refresh_browser()
        self.workspace_guard()
        if command in ('app', 'games', 'stremio'):
            app = 'vivaldi' if command == 'app' else command
            lifetimes, sources = self.card_state()
            hidden_stremio = app == 'stremio' and self.stremio.hidden()
            if app in lifetimes and app not in sources and not hidden_stremio:
                raise RuntimeError('Registered tablet window is unavailable; no replacement opened')
        if command == 'adopt-fold':
            self.automatic = True
            self.journal()
            return self.state()
        if command == 'home':
            self.games_requested = False
            self.stremio_waiting = False
        if command == 'stremio':
            self.error = ''
            self.select_stremio()
            return self.state()
        if command == 'games':
            self.error = ''
            self.select_games()
            return self.state()
        if command == 'app' and (self.record.get('home_only') or self.active_app != 'vivaldi'):
            self.error = ''
            self.select_browser()
            return self.state()
        if command == 'ui-ready':
            if not self.layer_opaque(self.ui, '3'):
                raise RuntimeError('Native tablet frontend is not fully mapped')
            if self.home:
                self.keyboard.hide()
            self.ipc(self.stage, 'tabletStage', 'reveal')
            return super().action(command, value)
        if command == 'close' and self.ui and self.ui.poll() is None:
            scene = json.loads(self.ipc(self.ui, 'tabletNativeScene', 'status'))
            self.resume_overview = bool(scene.get('overview'))
        state = super().action(command, value)
        if command in ('home', 'app', 'settings', 'dismiss', 'close'):
            self.remember()
        return state

    def return_desktop(self):
        if not self.record.get('home_only') and not self.record.get('lease_released'):
            return  # A failed focus-checked release must not steal focus.
        session = self.session or self.record.get('tablet_session')
        if not session or not session.get('entered'):
            return
        current = p.hypr('activeworkspace')
        # Never follow the user to another workspace, nor recreate a vanished
        # laptop workspace. Returning changes focus, never application placement.
        if current.get('name') != WORKSPACE or session['origin'] == WORKSPACE:
            return
        if not session.get('origin_empty') and not any(w['name'] == session['origin'] for w in p.hypr('workspaces')):
            raise RuntimeError('Laptop return workspace disappeared; choose a destination explicitly')
        p.dispatch('workspace', 'name:' + session['origin'])
        focus = next((c for c in p.hypr('clients') if c.get('workspace', {}).get('name') == session['origin']
                      and c.get('stableId') and all(c.get(k) == v for k, v in session['focus'].items())), None)
        if focus:
            p.dispatch('focuswindow', 'address:' + focus['address'])

    def pause_media(self):
        if self.record.get('home_only') or not self.record.get('address'):
            return
        client = next((c for c in p.hypr('clients') if c.get('address') == self.record['address']
                       and c.get('stableId') == self.record['stableId'] and c.get('pid') == self.record['pid']
                       and c.get('workspace', {}).get('name') == WORKSPACE), None)
        if not client:
            return  # Closed/moved windows are not reclaimed as media targets.
        self.record['media_suspended'] = True
        self.record['media_pause_pending'] = True
        self.journal()
        try:
            self.media.pause(self.record)
        except (OSError, ValueError, RuntimeError):
            if not self.record.get('media_pause_notice_sent'):
                self.record['media_pause_notice_sent'] = True
                self.journal()
                try:
                    p.run('notify-send', '--app-name=Tablet playback', 'Tablet playback was not paused',
                          'Check companion pairing and website access. No other browser window was paused.')
                except (OSError, subprocess.SubprocessError):
                    pass
            raise RuntimeError('Tablet-only media pause could not be verified; recovery retained') from None
        self.record['media_pause_pending'] = False
        self.journal()

    def cleanup(self, activate=False):
        if not self.record:
            return
        errors = []
        covered = False
        pending_lease = (not self.record.get('home_only') and not self.record.get('lease_released')) or bool(self.record.get('game_presentation'))
        try:
            foreground = p.hypr('activeworkspace').get('name') == WORKSPACE
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            foreground = False
            errors.append(str(error))
        # A verified cover is a hard prerequisite for foreground window-state
        # changes or workspace return, including explicit crash recovery.
        needs_cover = foreground or (activate and pending_lease)
        if needs_cover:
            try:
                if not self.stage or self.stage.poll() is not None:
                    self.owner = {'pid': os.getpid(), 'start': p.start_time(os.getpid())}
                    self.start_stage(allow_stopping=True)
                else:
                    self.cover('Returning to laptop…', allow_stopping=True)
                covered = True
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(str(error))
        self.rotation_enabled = False
        self.record['rotation_enabled'] = False
        for fn in (self.journal, self.pause_media, self.stop_orientation,
                   lambda: p.run(os.environ['TABLET_NATIVE_ORIENTATION_BIN'], 'restore')):
            try:
                fn()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(str(error))
        if covered:
            try:
                # Rotation/child shutdown can resize or outlive a surface.
                # Revalidate queued frames and compositor coverage immediately
                # before touching native window state or returning workspace.
                self.cover(allow_stopping=True)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                covered = False
                errors.append(str(error))
        try:
            if covered or (not needs_cover and not pending_lease):
                self.release_presentation(activate)
            else:
                self.stop_surfaces()
                if pending_lease:
                    errors.append('Client restoration deferred until a covered tablet workspace is eligible')
            if covered:
                self.return_desktop()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
        # Even a deferred client restore must release the interaction lease.
        # Do this after client/workspace work so follow-mouse cannot disrupt it.
        try:
            self.restore_posture()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
        # Stage last: window/IME teardown and workspace return happen behind it.
        try:
            if self.stage and self.stage.poll() is None:
                self.stage.terminate()
                self.stage.wait(timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(str(error))
        if errors:
            try:
                self.journal()
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(str(error))
            raise RuntimeError('Native tablet recovery retained: ' + '; '.join(errors))
        (p.runtime() / 'recovery.json').unlink(missing_ok=True)

    def stop_orientation(self):
        if self.orientation and self.orientation.poll() is None:
            self.orientation.terminate()
            self.orientation.wait(timeout=10)

    def release_presentation(self, activate):
        self.release_game_presentation(activate)
        if not self.record.get('home_only') and not self.record.get('lease_released'):
            super().cleanup(activate, retain_journal=True)
            self.record['lease_released'] = True
            return
        self.stop_surfaces()

    def stop_surfaces(self):
        errors = []
        try:
            self.keyboard.stop()
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
        try:
            if self.ui and self.ui.poll() is None:
                self.ui.terminate()
                self.ui.wait(timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(str(error))
        if errors:
            raise RuntimeError('; '.join(errors))


BASE_RECOVER = p.recover


def recover(activate=False):
    path = p.runtime() / 'recovery.json'
    if not path.exists():
        return
    value = json.loads(path.read_text())
    if not value.get('window', {}).get('tablet_session'):
        return BASE_RECOVER(activate)
    with (p.runtime() / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = json.loads(path.read_text())
        record = value['window']
        if record['instance'] != os.environ['HYPRLAND_INSTANCE_SIGNATURE']:
            raise RuntimeError('Recover in the original compositor; no stale state replayed')
        record['media_recovery_owner'] = {'pid': os.getpid(), 'start': p.start_time(os.getpid())}
        p.save(value)
        proof = Native()
        # Establish a new, owned cover BEFORE stopping any surviving old cover
        # or mutating client/workspace state. Until registered in the journal,
        # its exact-parent watchdog handles interruption of this recovery.
        pending = (not record.get('home_only') and not record.get('lease_released')) or bool(record.get('game_presentation'))
        foreground = p.hypr('activeworkspace').get('name') == WORKSPACE
        covered = False
        cover_error = None
        waiting_presentation = False
        try:
            if foreground or (activate and pending):
                proof.owner = {'pid': os.getpid(), 'start': p.start_time(os.getpid())}
                try:
                    proof.start_stage(allow_stopping=True)
                    covered = True
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    cover_error = error
                if proof.stage and proof.stage.poll() is None:
                    value['children'].append({'pid': proof.stage.pid, 'start': p.start_time(proof.stage.pid), 'role': 'stage'})
                    p.save(value)
            for child in value['children']:
                if proof.stage and child['pid'] == proof.stage.pid:
                    continue
                try:
                    if p.start_time(child['pid']) != child['start']:
                        continue
                    if not covered and child.get('role') not in ('keyboard', 'orientation'):
                        waiting_presentation = True
                        continue  # Never retire an old cover/UI without a verified replacement.
                    descriptor = os.pidfd_open(child['pid'])
                    try:
                        import select
                        import signal
                        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                        if not select.select([descriptor], [], [], 5)[0]:
                            raise RuntimeError('Owned tablet child did not exit; recovery retained')
                    finally:
                        os.close(descriptor)
                except (FileNotFoundError, ProcessLookupError):
                    pass
            proof.keyboard.settings = value['settings']
            if not covered and (cover_error or pending or waiting_presentation):
                # Preserve every original presentation identity. Safe IME and
                # sensor cleanup must not erase evidence or mutate client state.
                record['rotation_enabled'] = False
                p.save(value)
                errors = []
                for fn in (proof.keyboard.stop, lambda: p.run(os.environ['TABLET_NATIVE_ORIENTATION_BIN'], 'restore'),
                           lambda: proof.restore_posture(record)):
                    try:
                        fn()
                    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                        errors.append(str(error))
                p.save(value)
                detail = str(cover_error) if cover_error else 'Covered tablet foreground is required'
                raise RuntimeError('Native tablet recovery retained: ' + '; '.join([detail, *errors]))
            proof.record = record
            proof.cleanup(activate)
        finally:
            if proof.stage and proof.stage.poll() is None:
                proof.stage.terminate()
                proof.stage.wait(timeout=5)


def call(command):
    result = subprocess.run([os.environ['TABLET_PROOF_BIN'], command], check=True,
                            capture_output=True, text=True, timeout=40)
    return json.loads(result.stdout)


class FoldEdges:
    def __init__(self):
        self.folded = None

    def tick(self):
        value = Path('/sys/devices/platform/thinkpad_acpi/hotkey_tablet_mode').read_text().strip()
        if value not in ('0', '1'):
            raise RuntimeError('Unknown tablet posture; no transition inferred')
        folded = value == '1'
        try:
            headless = Path('/run/headless-mode/state').read_text().strip() != 'off'
        except FileNotFoundError:
            headless = False
        if headless:
            self.folded = folded
            return
        if folded and self.folded is not True:
            current = p.hypr('activeworkspace')
            panel = next((m for m in p.hypr('monitors') if m['name'] == 'eDP-1'), None)
            destination = next((w for w in p.hypr('workspaces') if w['name'] == WORKSPACE), None)
            if (not panel or panel.get('disabled') or not panel.get('dpmsStatus', True)
                    or panel.get('specialWorkspace', {}).get('id', 0) or current.get('monitor') != 'eDP-1'
                    or (destination and destination.get('monitor') != 'eDP-1')):
                return
            state = call('status')
            if not state.get('running') and not state.get('recovery'):
                call('start-fold')
            elif state.get('running') and state.get('native'):
                call('adopt-fold')  # Preserve the current view, not restart Home.
            self.folded = True
        elif not folded:
            state = call('status')
            if state.get('running') and state.get('native') and state.get('automatic'):
                call('close')
            elif state.get('recovery'):
                record = json.loads((p.runtime() / 'recovery.json').read_text())['window']
                if record.get('native') and record.get('automatic'):
                    call('recover')  # Never activate on automatic recovery.
            self.folded = False


def watch():
    with (Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-fold-watch.lock').open('a') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another fold watcher is active; no replacement attempted')
        watcher = FoldEdges()
        last_error = None
        while True:
            try:
                watcher.tick()
                last_error = None
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                message = str(error)
                if message != last_error:
                    print(message, file=sys.stderr, flush=True)
                    last_error = message
                time.sleep(4)
            time.sleep(.5)


def main():
    p.Proof = Native
    p.recover = recover
    p.EXTRA_COMMANDS = ['adopt-fold', 'games', 'stremio']
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    if command in ('dismiss-app', 'resume-app'):
        import argparse
        parser = argparse.ArgumentParser(description='Request close of one exact tablet switcher card')
        parser.add_argument('command', choices=['dismiss-app', 'resume-app'])
        parser.add_argument('--target', required=True)
        args = parser.parse_args()
        if len(args.target) > 4096:
            raise RuntimeError('Switcher target too large')
        print(json.dumps(p.request(args.command, json.loads(args.target))))
        return
    if command == 'watch-fold':
        return watch()
    if command == 'toggle':
        sys.argv[1] = 'close' if call('status').get('running') else 'start'
        command = sys.argv[1]
    if command in ('start', 'start-fold'):
        os.environ['TABLET_NATIVE_AUTOMATIC'] = '1' if command == 'start-fold' else '0'
        sys.argv[1] = 'start'
    p.main()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
