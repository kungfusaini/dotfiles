#!/usr/bin/env python3
"""Opt-in real user-service lifetime test; Steam operations are all synthetic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

UNIT = 'steam-session-independence-test'


def wait_for(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError('Timed out waiting for synthetic service state')


def worker(package, directory):
    root = Path(directory)
    sys.path.insert(0, str(Path(package) / 'libexec/steam-session'))
    import session
    s = session.steam
    s.STATE_DIR = root
    session.STATE = root / 'state.json'
    running = [False]
    s.manifests = lambda: [dict(appid=1687950, state_flags=4)]
    s.running_game_appids = lambda: []
    s.start_steam = lambda *_: running.__setitem__(0, True)
    s.wait_steam_ready = lambda *_: None
    s.request_url = lambda *a, **kw: None
    s.steam_running = lambda: running[0]
    s.shutdown_blockers = lambda: dict(running_games=[], active_downloads=[], active_cloud_syncs=[])
    s.settle = lambda *_: None
    def wait_game(*args, **kwargs):
        (root / 'game-running').touch()
        wait_for(lambda: (root / 'release').exists(), seconds=40)
    s.wait_game = wait_game
    def stop(timeout, force, approved, override_active):
        assert not force and not approved and not override_active
        (root / 'shutdown.json').write_text(json.dumps(dict(forced=force, override=override_active)))
        running[0] = False
    s.stop_steam = stop
    session.notify = lambda message: (root / 'notification').write_text(message)
    raise SystemExit(session.worker(1687950))


def main(package):
    root = Path(tempfile.mkdtemp(prefix='steam-session-lifetime.'))
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--wait', '--collect', '--property=Type=exec',
               sys.executable, str(Path(__file__).resolve()), '--worker', package, str(root)]
    waiter = subprocess.Popen(command)
    try:
        wait_for(lambda: (root / 'game-running').exists())
        # Terminate only our test foreground waiter, never the independent worker.
        waiter.terminate()
        waiter.wait(timeout=5)
        active = subprocess.run(['systemctl', '--user', 'is-active', UNIT], capture_output=True, text=True)
        assert active.stdout.strip() == 'active', active
        print('PASS: service survives foreground waiter exit', flush=True)
        (root / 'release').touch()
        def done():
            try:
                return json.loads((root / 'state.json').read_text())['phase'] == 'finished-steam-closed'
            except (OSError, ValueError):
                return False
        wait_for(done)
        assert json.loads((root / 'shutdown.json').read_text()) == dict(forced=False, override=False)
        assert not (root / 'notification').exists()
        print('PASS: synthetic game exit triggers ordinary guarded cleanup independently', flush=True)
    finally:
        (root / 'release').touch()
        if waiter.poll() is None:
            waiter.terminate()
            waiter.wait(timeout=5)
        print('Private synthetic test evidence retained at ' + str(root), flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--worker']:
        worker(*sys.argv[2:])
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        raise SystemExit('Usage: service_integration.py /nix/store/...-steam-session-1.0.0')
