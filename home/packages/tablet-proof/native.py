#!/usr/bin/env python3
"""Resume a dedicated tablet workspace without borrowing laptop applications."""
import fcntl
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

    def journal(self):
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
        config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'hypr/hyprland.conf'
        if not re.search(r'(?m)^\s*layerrule\s*=\s*match:namespace\s+\^tablet-rotation-fade\$\s*,\s*no_anim\s+on\s*$', config.read_text()):
            raise RuntimeError('Tablet entry requires the installed guarded no-animation policy')
        environment = dict(os.environ, TABLET_STAGE_OWNER_PID=str(os.getpid()),
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
        self.session['entered'] = True
        self.journal()
        p.dispatch('workspace', 'name:' + WORKSPACE)
        self.guard()
        if source:
            self.attach(source)
        self.keyboard.start()
        self.values = self.controls.read()
        self.home = bool(self.saved.get('home', True)) if self.source else True
        self.drawer = bool(self.saved.get('drawer', False))
        self.resume_overview = bool(self.saved.get('overview', False)) and bool(self.source)
        self.rotation_enabled = True
        self.record['media_suspended'] = False
        self.journal()
        if self.source:
            try:
                self.media.resume(self.record)  # Unblock only; never auto-play.
            except (OSError, ValueError, RuntimeError):
                self.error = 'Pair the tablet media companion to pause YouTube on exit.'
        self.remember()
        with (p.runtime() / 'orientation.log').open('a') as log:
            self.orientation = subprocess.Popen([os.environ['TABLET_NATIVE_ORIENTATION_BIN'], 'daemon'], stdout=log, stderr=log)
        self.journal()

    def attach(self, client):
        if not eligible(client):
            raise RuntimeError('Only tablet-local native browser windows may be presented')
        p.dispatch('focuswindow', 'address:' + client['address'])
        self.lease(client['address'])
        self.source = identity(client)
        self.journal()

    def guard(self):
        if not self.record.get('home_only'):
            return super().guard()
        current = p.hypr('activeworkspace')
        panel = self.panel()
        if (self.record['instance'] != os.environ['HYPRLAND_INSTANCE_SIGNATURE']
                or current.get('monitor') != 'eDP-1' or current.get('name') != WORKSPACE):
            raise RuntimeError('Tablet workspace is no longer foreground')
        return None, panel

    def remember(self):
        if self.session is None:
            return
        store({'instance': os.environ['HYPRLAND_INSTANCE_SIGNATURE'], 'source': self.source,
               'home': self.home, 'drawer': self.drawer, 'overview': self.resume_overview,
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
            p.dispatch('exec', '[workspace name:' + WORKSPACE + ' silent] ' + shlex.join(command))
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

    def state(self):
        self.guard()
        if not self.stopping:
            self.poll_launch()
        if not self.record.get('home_only'):
            state = super().state()
        else:
            _, panel = self.guard()
            state = {'running': True, 'ready': self.ready, 'home': True, 'drawer': self.drawer,
                     'backend': {'pid': os.getpid(), 'start': p.start_time(os.getpid())},
                     'media': False, 'keyboardInset': panel.get('reserved', [0, 0, 0, 0])[3],
                     'error': self.error, **self.values}
        if self.source and time.monotonic() >= self.media_status_at:
            self.media_status_at = time.monotonic() + 1
            try:
                self.media_paired = bool(self.media.status(self.record).get('registered'))
            except (OSError, ValueError, RuntimeError):
                self.media_paired = False
        return dict(state, native=True, automatic=self.automatic, workspace=WORKSPACE,
                    mediaPaired=self.media_paired,
                    browserAvailable=True, browserRunning=bool(self.source), launching=bool(self.pending),
                    resumeOverview=self.resume_overview)

    def action(self, command, value=None):
        self.guard()
        if command == 'adopt-fold':
            self.automatic = True
            self.journal()
            return self.state()
        if command == 'app' and self.record.get('home_only'):
            self.error = ''
            self.launch_browser()
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
                    p.run('notify-send', 'Tablet playback was not paused',
                          'Pair the tablet media companion. No other browser window was paused.')
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
        pending_lease = not self.record.get('home_only') and not self.record.get('lease_released')
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
        pending = not record.get('home_only') and not record.get('lease_released')
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
                for fn in (proof.keyboard.stop, lambda: p.run(os.environ['TABLET_NATIVE_ORIENTATION_BIN'], 'restore')):
                    try:
                        fn()
                    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                        errors.append(str(error))
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
    p.EXTRA_COMMANDS = ['adopt-fold']
    command = sys.argv[1] if len(sys.argv) > 1 else ''
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
