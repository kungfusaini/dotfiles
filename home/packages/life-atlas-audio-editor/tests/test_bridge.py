import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
import editor


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = 'a'*64
        self.packet = json.dumps({'schema': 1, 'source_sha256': 'b'*64, 'segments': [
            {'id': 0, 'asr_text': ' synthetic', 'start_ms': 0, 'end_ms': 1000}]}).encode()
        self.completion = {'status': 'complete', 'source_sha256': self.identity, 'backup_restore_verified': True}

    def fake_model(self, packet_path, output, pi):
        output.mkdir(mode=0o700)
        proposal = json.dumps({'source_sha256': 'b'*64, 'edits': []}).encode()
        receipt = {'packet_sha256': hashlib.sha256(self.packet).hexdigest(),
                   'proposal_sha256': hashlib.sha256(proposal).hexdigest(),
                   'provider': editor.PROVIDER, 'model': editor.MODEL}
        for name, data in [('proposal.json', proposal), ('receipt.json', json.dumps(receipt).encode())]:
            (output/name).write_bytes(data); (output/name).chmod(0o600)

    def test_success_and_reuse_after_upload_failure(self):
        calls = []
        def remote(action, identity, payload=None):
            calls.append(action)
            if action == 'packet': return self.packet
            if action == 'accept': return b'{"status":"reviewed"}'
            return json.dumps(self.completion).encode()
        with patch.dict(os.environ, {'LIFE_ATLAS_PI_BIN': 'unused'}), patch.object(bridge, 'remote', side_effect=remote), patch.object(editor, 'run', side_effect=self.fake_model) as model:
            bridge.process(self.root, {'id': self.identity, 'has_review': False})
            bridge.process(self.root, {'id': self.identity, 'has_review': False})
            self.assertEqual(model.call_count, 1)
        self.assertTrue((self.root/self.identity/'completion.json').exists())
        self.assertEqual(calls, ['packet', 'accept', 'finish', 'packet', 'accept', 'finish'])

    def test_rejected_proposal_gets_bounded_regeneration(self):
        accepts = 0
        def remote(action, identity, payload=None):
            nonlocal accepts
            if action == 'packet': return self.packet
            if action == 'accept':
                accepts += 1
                if accepts == 1: return json.dumps({'status': 'rejected-proposal', 'source_sha256': self.identity}).encode()
                return b'{"status":"reviewed"}'
            return json.dumps(self.completion).encode()
        item = {'id': self.identity, 'has_review': False}
        with patch.dict(os.environ, {'LIFE_ATLAS_PI_BIN': 'unused'}), patch.object(bridge, 'remote', side_effect=remote), patch.object(editor, 'run', side_effect=self.fake_model) as model:
            with self.assertRaises(ValueError): bridge.process(self.root, item)
            bridge.process(self.root, item)
            self.assertEqual(model.call_count, 2)
        self.assertEqual(len(list((self.root/self.identity).glob('review-*'))), 2)

    def test_existing_server_review_needs_no_model(self):
        with patch.object(bridge, 'remote', return_value=json.dumps(self.completion).encode()), patch.object(editor, 'run') as model:
            bridge.process(self.root, {'id': self.identity, 'has_review': True})
            model.assert_not_called()

    def test_model_retries_are_bounded(self):
        item = {'id': self.identity, 'has_review': False}
        with patch.dict(os.environ, {'LIFE_ATLAS_PI_BIN': 'unused'}), patch.object(bridge, 'remote', return_value=self.packet), patch.object(editor, 'run', side_effect=RuntimeError('synthetic')) as model:
            for _ in range(5):
                with self.assertRaises((RuntimeError, ValueError)): bridge.process(self.root, item)
            self.assertEqual(model.call_count, 3)
        self.assertFalse((self.root/self.identity/'completion.json').exists())

    def test_sandbox_ssh_preserves_host_trust_with_caller_config(self):
        result = type('Result', (), {'returncode': 0, 'stdout': b'[]\n'})()
        with patch.object(bridge.subprocess, 'run', return_value=result) as run:
            self.assertEqual(bridge.remote('pending'), b'[]')
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('-F')+1], str(Path.home()/'.ssh/config'))
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts', args)
        self.assertIn('ForwardX11=no', args)

    def test_unsafe_queue_identity_rejected(self):
        with self.assertRaises(ValueError): bridge.process(self.root, {'id': '../escape', 'has_review': False})


if __name__ == '__main__': unittest.main()
