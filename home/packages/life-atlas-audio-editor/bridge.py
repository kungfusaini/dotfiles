#!/usr/bin/env python3
"""Poll only the approved Aether transcript queue; no phone/audio access."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import editor

REMOTE = '/opt/life-atlas-audio/automation.py'


def remote(action, identity=None, payload=None):
    editor.require(action in {'pending', 'packet', 'accept', 'finish'})
    if identity is not None:
        editor.require(re.fullmatch('[0-9a-f]{64}', identity) is not None)
    command = 'python3 -B ' + REMOTE + ' ' + action + ((' '+identity) if identity else '')
    # User-service mount namespaces map Nix-store root ownership to nobody;
    # OpenSSH rejects the systemd-proxy Include in the global ssh_config there.
    # Use the existing caller-owned host config explicitly, preserving the two
    # other configured global settings and strict host-key checking. No host or
    # identity guesses, credential copying, or security-policy relaxation.
    p = subprocess.run(['ssh', '-F', str(Path.home()/'.ssh/config'),
        '-o', 'GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts', '-o', 'ForwardX11=no',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2',
        'aether', command], input=payload, capture_output=True, timeout=2000)
    editor.require(p.returncode == 0 and len(p.stdout) <= 16*1024*1024)
    return p.stdout.rstrip(b'\n')


def atomic(path, data):
    part = path.with_name('.'+uuid.uuid4().hex)
    with part.open('xb') as out:
        os.fchmod(out.fileno(), 0o600); out.write(data); out.flush(); os.fsync(out.fileno())
    os.replace(part, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def process(root, item):
    identity = item['id']
    editor.require(re.fullmatch('[0-9a-f]{64}', identity) is not None and type(item['has_review']) is bool)
    job = root/identity
    job.mkdir(mode=0o700, exist_ok=True); editor.private(job)
    if not item['has_review']:
        packet = remote('packet', identity)
        editor.packet_segments(json.loads(packet))
        editor.name_hints(json.loads(packet))
        packet_path = job/'packet.json'
        if packet_path.exists(): editor.require(packet_path.read_bytes() == packet)
        else: atomic(packet_path, packet)
        state_path = job/'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {'attempts': 0, 'review': None}
        editor.require(state['review'] is None or re.fullmatch('review-[0-9a-f]{32}', state['review']) is not None)
        review = job/state['review'] if state['review'] else None
        if review is None or not (review/'receipt.json').exists() or state.get('rejected', False):
            editor.require(state['attempts'] < 3)
            review = job/('review-'+uuid.uuid4().hex)
            state = {'attempts': state['attempts']+1, 'review': review.name}
            atomic(state_path, json.dumps(state).encode())
            editor.run(packet_path, review, os.environ['LIFE_ATLAS_PI_BIN'])
        editor.private(review)
        receipt_bytes = (review/'receipt.json').read_bytes()
        proposal_bytes = (review/'proposal.json').read_bytes()
        receipt = json.loads(receipt_bytes)
        editor.require(receipt['packet_sha256'] == hashlib.sha256(packet).hexdigest() and
            receipt['proposal_sha256'] == hashlib.sha256(proposal_bytes).hexdigest() and
            receipt['provider'] == editor.PROVIDER and receipt['model'] == editor.MODEL)
        accepted = json.loads(remote('accept', identity, json.dumps({'proposal': proposal_bytes.decode(), 'receipt': receipt}, ensure_ascii=False).encode()))
        if accepted.get('status') == 'rejected-proposal':
            editor.require(accepted.get('source_sha256') == identity)
            state['rejected'] = True
            atomic(state_path, json.dumps(state).encode())
            raise ValueError('Server rejected proposal; bounded regeneration pending')
        editor.require(accepted.get('status') in {'reviewed', 'already-reviewed'})
    completion = json.loads(remote('finish', identity))
    editor.require(completion['status'] == 'complete' and completion['source_sha256'] == identity and
                   completion['backup_restore_verified'] is True)
    atomic(job/'completion.json', json.dumps(completion, indent=2).encode())
    return identity


def main():
    os.umask(0o077)
    root = Path(os.environ.get('LIFE_ATLAS_AUDIO_STATE', str(Path.home()/'.local/state/life-atlas-audio')))
    root.mkdir(mode=0o700, parents=True, exist_ok=True); editor.private(root)
    with (root/'bridge.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        items = json.loads(remote('pending'))
        editor.require(isinstance(items, list) and len(items) <= 1000)
        completed = 0; failed = 0
        for item in items:
            try:
                process(root, item); completed += 1
            except Exception:
                failed += 1
        result = {'pending_seen': len(items), 'completed': completed, 'failed': failed, 'speech_logged': False}
        atomic(root/'health.json', json.dumps(result).encode())
        print(json.dumps(result))
        if failed: raise SystemExit(1)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Audio review bridge failed:', type(error).__name__, '(private diagnostics suppressed)', file=sys.stderr)
        raise SystemExit(1)
