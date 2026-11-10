"""Native caller: no browser debugging, page data, MPRIS or global input."""
import json
import os
from pathlib import Path
import socket

FIELDS = ('instance', 'address', 'pid', 'start', 'class', 'stableId')


class Media:
    def request(self, op, record=None, timeout=10, **payload):
        path = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-media/bridge.sock'
        if record is not None:
            payload['source'] = {key: record[key] for key in FIELDS}
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(timeout)
            connection.connect(str(path))
            connection.sendall(json.dumps({'op': op, **payload}).encode() + b'\n')
            line = connection.makefile('rb').readline(16385)
        if len(line) > 16384:
            raise RuntimeError('Invalid media response')
        response = json.loads(line)
        if not response.get('ok'):
            raise RuntimeError('Tablet media companion is unavailable or this window is not paired')
        return response

    def prepare(self):
        return self.request('prepare')

    def bind(self, record, nonce):
        return self.request('bind', record, nonce=nonce)

    def pause(self, record):
        return self.request('pause', record)

    def resume(self, record):
        return self.request('resume', record)

    def status(self, record):
        return self.request('status', record, timeout=.25)
