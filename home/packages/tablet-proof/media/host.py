#!/usr/bin/env python3
"""Private native-messaging bridge; fixed window registration and media commands."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('tablet_core', os.environ['TABLET_PROOF_SOURCE'])
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
FIELDS = ('instance', 'address', 'pid', 'start', 'class', 'stableId')
HOSTNAME = 'tablet.localhost'


def fingerprint(record):
    return {key: record[key] for key in FIELDS}


def key(source):
    return tuple(source[field] for field in FIELDS)


def directory():
    root = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-media'
    if root.is_symlink():
        raise RuntimeError('Unsafe media runtime')
    root.mkdir(mode=0o700, exist_ok=True)
    if root.stat().st_uid != os.getuid():
        raise RuntimeError('Wrong media runtime owner')
    root.chmod(0o700)
    return root


def current():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-proof/recovery.json'
    if path.exists():
        record = json.loads(path.read_text())['window']
        if record.get('native') and record.get('tablet_session', {}).get('workspace') == 'tablet-trial':
            return record
    return None


def source_client(source):
    if source.get('class') != 'vivaldi-stable' or core.start_time(source['pid']) != source['start']:
        raise RuntimeError('Tablet source changed')
    return next((client for client in core.hypr('clients')
                 if client.get('address') == source['address'] and client.get('stableId') == source['stableId']
                 and client.get('pid') == source['pid'] and client.get('class') == source['class']
                 and client.get('workspace', {}).get('name') == 'tablet-trial'
                 and client.get('mapped') and not client.get('xwayland')), None)


class Bridge:
    def __init__(self, output):
        self.output = output
        self.write_lock = threading.Lock()
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.requests = {}
        self.prepared = {}
        self.bindings = {}
        self.sequence = 0
        self.port = None

    def send(self, value):
        data = json.dumps(value, separators=(',', ':')).encode()
        with self.write_lock:
            self.output.write(struct.pack('=I', len(data)) + data)
            self.output.flush()

    def ask(self, op, **payload):
        with self.lock:
            self.sequence += 1
            identifier = 'host-' + str(self.sequence)
            event = threading.Event()
            request = {'event': event}
            self.requests[identifier] = request
        try:
            self.send({'id': identifier, 'op': op, **payload})
            if not event.wait(5) or not request.get('result', {}).get('ok'):
                raise RuntimeError('Window-scoped browser operation failed')
            return request['result']
        finally:
            with self.lock:
                self.requests.pop(identifier, None)

    def prepare(self, source=None):
        nonce = secrets.token_hex(32)
        value = {'nonce': nonce, 'source': source, 'marker': 'tablet-media-' + nonce,
                 'url': f'http://{HOSTNAME}:{self.port}/register/{nonce}',
                 'deadline': time.monotonic() + 45, 'event': threading.Event(), 'report': None}
        with self.lock:
            self.prepared = {k: v for k, v in self.prepared.items() if v['deadline'] > time.monotonic()}
            self.prepared[nonce] = value
        return value

    def registration(self, nonce):
        with self.lock:
            value = self.prepared.get(nonce)
        if not value or time.monotonic() >= value['deadline']:
            raise RuntimeError('Registration expired')
        return value

    def finalize(self, value, source):
        with self.operation_lock:
            return self.finalize_locked(value, source)

    def finalize_locked(self, value, source):
        report = value['report']
        if not report:
            raise RuntimeError('Registration not reported')
        self.ask('verify', windowId=report['windowId'], tabId=report['tabId'], url=value['url'])
        # The unique active-tab title links the extension window ID to the
        # exact native window. No focus guess, shared PID or arbitrary title.
        deadline = time.monotonic() + 2
        while True:
            client = source_client(source)
            if client and client.get('title', '').startswith(value['marker']):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Registration is not in the tablet window')
            time.sleep(.025)
        record = current()
        if not record or record.get('home_only') or fingerprint(record) != source:
            raise RuntimeError('Tablet lease changed during registration')
        self.ask('verify', windowId=report['windowId'], tabId=report['tabId'], url=value['url'])
        confirmed = source_client(source)
        if not confirmed or not confirmed.get('title', '').startswith(value['marker']):
            raise RuntimeError('Registration moved during confirmation')
        latest = current()
        if not latest or fingerprint(latest) != source:
            raise RuntimeError('Tablet lease changed before registration commit')
        self.ask('pause' if latest.get('media_suspended') else 'resume', windowId=report['windowId'])
        # Publish only after the initial state is acknowledged. Native exit
        # requests use the same operation lock, so a late pairing resume cannot
        # race after a successfully acknowledged exit pause.
        with self.lock:
            self.bindings[key(source)] = {'source': dict(source), 'windowId': report['windowId']}

    def browser_message(self, message):
        identifier = message.get('id')
        with self.lock:
            request = self.requests.get(identifier)
        if request:
            request['result'] = message
            request['event'].set()
            return
        if not identifier or message.get('op') not in ('prepare-existing', 'register'):
            return
        # Never block the framing reader while awaiting an extension reply.
        threading.Thread(target=self.browser_request, args=(message,), daemon=True).start()

    def browser_request(self, message):
        try:
            if message['op'] == 'prepare-existing':
                record = current()
                if not record or record.get('home_only'):
                    raise RuntimeError('Open the tablet browser before pairing')
                source = fingerprint(record)
                if not source_client(source):
                    raise RuntimeError('Tablet window not available')
                value = self.prepare(source)
                self.send({'id': message['id'], 'ok': True, 'url': value['url']})
            else:
                value = self.registration(message.get('nonce'))
                report = {field: message[field] for field in ('windowId', 'tabId')}
                if any(type(v) is not int or v < 0 for v in report.values()):
                    raise RuntimeError('Invalid browser identity')
                with self.lock:
                    if value['report'] and value['report'] != report:
                        raise RuntimeError('Ambiguous registration')
                    value['report'] = report
                    value['event'].set()
                if value['source']:
                    self.finalize(value, value['source'])
                self.send({'id': message['id'], 'ok': True, 'closeRegistration': bool(value['source'])})
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            self.send({'id': message['id'], 'ok': False, 'error': 'Tablet window registration failed'})

    def native_request(self, message, peer_pid):
        with self.operation_lock:
            return self.native_request_locked(message, peer_pid)

    def native_request_locked(self, message, peer_pid):
        record = current()
        if not record:
            raise RuntimeError('No tablet owner')
        owners = (record.get('owner', {}), record.get('media_recovery_owner', {}))
        if not any(owner.get('pid') == peer_pid and core.start_time(peer_pid) == owner.get('start') for owner in owners):
            raise RuntimeError('Not the tablet owner')
        if record.get('instance') != os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            raise RuntimeError('Wrong compositor')
        op = message.get('op')
        if op == 'prepare':
            if core.hypr('activeworkspace').get('name') != 'tablet-trial':
                raise RuntimeError('Tablet workspace not foreground')
            value = self.prepare()
            return {'ok': True, **{k: value[k] for k in ('nonce', 'url', 'marker')}}
        source = message.get('source')
        if record.get('home_only') or source != fingerprint(record):
            raise RuntimeError('Wrong tablet source')
        client = source_client(source)
        if not client:
            return {'ok': True, 'closed': True}
        if op == 'bind':
            value = self.registration(message.get('nonce'))
            if value['source'] or not value['event'].wait(5):
                raise RuntimeError('New window registration not available')
            self.finalize(value, source)
            return {'ok': True}
        with self.lock:
            binding = self.bindings.get(key(source))
        if op == 'status':
            return {'ok': True, 'registered': bool(binding)}
        if op not in ('pause', 'resume') or not binding:
            raise RuntimeError('Tablet window is not paired')
        result = self.ask(op, windowId=binding['windowId'])
        return {'ok': True, **{k: result[k] for k in ('elements', 'playing', 'unsupportedAudible') if k in result}}


def serve_socket(bridge, server):
    while True:
        connection, _ = server.accept()
        threading.Thread(target=socket_request, args=(bridge, connection), daemon=True).start()


def socket_request(bridge, connection):
    with connection:
        connection.settimeout(12)
        try:
            pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise RuntimeError('Wrong user')
            line = connection.makefile('rb').readline(16385)
            if len(line) > 16384:
                raise RuntimeError('Oversized request')
            value = bridge.native_request(json.loads(line), pid)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            value = {'ok': False, 'error': 'Tablet media operation unavailable or unverified'}
        try:
            connection.sendall(json.dumps(value).encode() + b'\n')
        except OSError:
            pass  # A bounded caller may already have disconnected.


def main():
    os.umask(0o077)
    if len(sys.argv) < 2 or sys.argv[1] != 'chrome-extension://' + os.environ['TABLET_MEDIA_EXTENSION_ID'] + '/':
        raise RuntimeError('Unexpected extension origin')
    root = directory()
    with (root / 'owner.lock').open('a') as singleton:
        fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bridge = Bridge(sys.stdout.buffer)
        class Registration(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    if self.headers.get('Host') != f'{HOSTNAME}:{bridge.port}' or not self.path.startswith('/register/'):
                        raise RuntimeError('Wrong origin')
                    value = bridge.registration(self.path.removeprefix('/register/'))
                    body = ('<!doctype html><meta charset=utf-8><title>' + value['marker']
                            + '</title><p>Your tablet browser is ready.</p>').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Security-Policy', "default-src 'none'")
                    self.end_headers(); self.wfile.write(body)
                except (OSError, RuntimeError):
                    self.send_error(404)
            def log_message(self, *args):
                pass  # Registration nonces and URLs never enter logs.
        http = ThreadingHTTPServer(('127.0.0.1', 0), Registration)
        bridge.port = http.server_port
        threading.Thread(target=http.serve_forever, daemon=True).start()
        path = root / 'bridge.sock'
        path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(path)); path.chmod(0o600); server.listen(8)
        threading.Thread(target=serve_socket, args=(bridge, server), daemon=True).start()
        try:
            stream = sys.stdin.buffer
            while True:
                header = stream.read(4)
                if not header:
                    break
                if len(header) != 4:
                    raise RuntimeError('Truncated message')
                length = struct.unpack('=I', header)[0]
                if not 0 < length <= 262144:
                    raise RuntimeError('Invalid message length')
                body = stream.read(length)
                if len(body) != length:
                    raise RuntimeError('Truncated message')
                bridge.browser_message(json.loads(body))
        finally:
            server.close(); path.unlink(missing_ok=True); http.shutdown(); http.server_close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        sys.exit(1)  # No page data, registration capabilities or raw frames logged.
