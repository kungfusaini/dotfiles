#!/usr/bin/env python3
"""Opt-in native backend/browser differential test on the private compositor.

Use headed_integration.py's harness arguments, --chromium carries the browser
binary (not pi-browser), plus --backend playwright|puppeteer --module /module.mjs.
No real profiles, authentication, host display/input, MCP server or telemetry.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import http.server
import threading

import headed_integration as headed
from manual_integration import PAGE

spec = importlib.util.spec_from_file_location('browser_wrapper', Path(__file__).parents[1] / 'browser.py')
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/pixel':
            self.server.pixels += 1
            self.send_response(200)
            self.send_header('Content-Type', 'image/gif')
            self.end_headers()
            self.wfile.write(bytes.fromhex('47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b'))
        elif self.path.startswith('/phase?'):
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


def launch(root, executable, target):
    root = Path(root)
    env = {**os.environ, 'PROJECT_PICKER_HYPRCTL': shutil.which('hyprctl'),
           'XDG_STATE_HOME': str(root / 'state'), 'XDG_CACHE_HOME': str(root / 'cache'),
           'VIVALDI_FFMPEG_AUTO': '0'}
    rule = wrapper.placement_rule(root, env)
    profile = (root.parent / 'probe-shared-profile' if env.get('PI_PROBE_SHARED_PROFILE') == '1'
               else root / 'synthetic-profile')
    wrapper.private_dir(profile)
    if wrapper.profile_locked(profile):
        raise ValueError('Synthetic profile is already in use')
    with (root / 'browser.log').open('w') as log:
        process = subprocess.Popen([executable, '--ozone-platform=wayland', '--no-first-run',
            '--no-default-browser-check', '--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0', '--user-data-dir=' + str(profile),
            '--class=' + rule['class'], *json.loads(env.get('PI_PROBE_BROWSER_ARGS', '[]')),
            'about:blank'], env=env, stdout=log, stderr=log)
        start = wrapper.process_start(process.pid)
        assert start, 'Private browser exited before identity verification'
        state = {**rule, 'pid': process.pid, 'start': start, 'profile': str(profile)}
        (root / 'browser-state.json').write_text(json.dumps(state))
        wrapper.open_manual_tab(process, state, executable, target, root, env)
        process.wait()  # Preserve readable ancestry until the private browser exits.


def worker(arguments):
    root, helper, executable, strip = arguments
    root = Path(root)
    headed.wait_for_file(root / 'go')
    assert Path(os.environ['XDG_RUNTIME_DIR']).resolve().is_relative_to(root.parent.resolve())
    port_file = root.parent / 'probe-fixture-port'
    reuse = os.environ.get('PI_PROBE_SHARED_PROFILE') == '1'
    port = int(port_file.read_text()) if reuse and port_file.exists() else 0
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    if reuse:
        port_file.write_text(str(server.server_port))
    server.pixels = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    state = None
    try:
        launcher = 'import os,subprocess,time;'
        if strip == 'yes':
            launcher += "os.environ.pop('HL_EXEC_RULE_TOKEN',None);os.environ.pop('HL_INITIAL_WORKSPACE_TOKEN',None);time.sleep(1.2);"
        launcher += 'subprocess.run(' + repr([sys.executable, __file__, '--launch', str(root), executable, origin + '/']) + ')'
        opened = subprocess.run([helper, sys.executable, '-c', launcher], capture_output=True, text=True, timeout=25)
        assert opened.returncode == 0, opened.stderr
        state = json.loads((root / 'browser-state.json').read_text())
        marker = Path(state['profile']) / 'DevToolsActivePort'
        deadline = time.monotonic() + 15
        while not marker.exists():
            assert time.monotonic() < deadline, 'Private browser endpoint not ready'
            time.sleep(.05)
        info = marker.read_text().splitlines()
        assert info[0].isdigit() and len(info) == 2
        endpoint = 'ws://127.0.0.1:' + info[0] + info[1]
        result = subprocess.run(['node', str(Path(__file__).with_name('backend_probe.mjs')),
            os.environ['PI_PROBE_BACKEND'], os.environ['PI_PROBE_MODULE'], endpoint, origin],
            capture_output=True, text=True, timeout=35,
            env={**os.environ, 'PI_PROBE_REOPEN': '1' if reuse and strip == 'yes' else '0'})
        (root / 'probe.stdout').write_text(result.stdout)
        (root / 'probe.stderr').write_text(result.stderr)
        assert result.returncode == 0, result.stderr[-2000:]
        data = json.loads(result.stdout)
        assert data['popup'] and data['navigation'] and data['reconnect'] and data['stateRetained']
        assert server.pixels == 1
        assert wrapper.process_start(state['pid']) == state['start'], 'Reconnect stopped the browser'
        (root / 'result.json').write_text(json.dumps({'status': 0, 'stdout': result.stdout, 'stderr': ''}))
        headed.wait_for_file(root / 'done')
    except Exception as error:
        (root / 'result.json').write_text(json.dumps({'status': 1, 'stdout': '', 'stderr': str(error)}))
        raise
    finally:
        if state is None and (root / 'browser-state.json').exists():
            state = json.loads((root / 'browser-state.json').read_text())
        if state:
            if wrapper.process_start(state['pid']) == state['start']:
                os.kill(state['pid'], signal.SIGTERM)
                deadline = time.monotonic() + 10
                while wrapper.process_start(state['pid']) == state['start']:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Private browser did not stop; no replacement attempted')
                    time.sleep(.05)
            wrapper.release_rule(state)
        server.shutdown()
        server.server_close()


def main():
    if sys.argv[1:2] == ['--worker']:
        worker(sys.argv[2:])
        return
    if sys.argv[1:2] == ['--launch']:
        launch(*sys.argv[2:])
        return
    for flag, variable in (('--backend', 'PI_PROBE_BACKEND'), ('--module', 'PI_PROBE_MODULE')):
        if flag in sys.argv:
            index = sys.argv.index(flag)
            os.environ[variable] = sys.argv[index + 1]
            del sys.argv[index:index + 2]
        assert variable in os.environ, flag + ' is required'
    assert os.environ['PI_PROBE_BACKEND'] in ('playwright', 'puppeteer')
    headed.__file__ = __file__
    headed.main()


if __name__ == '__main__':
    if '--harness' not in sys.argv and sys.argv[1:2] not in (['--worker'], ['--launch']) and os.environ.get('PI_BROWSER_TEST_HARNESS'):
        sys.argv += ['--harness', os.environ['PI_BROWSER_TEST_HARNESS']]
    main()
