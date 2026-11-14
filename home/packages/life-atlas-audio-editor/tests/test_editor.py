import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import editor


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.source = 'a'*64
        self.packet = {'schema': 1, 'source_sha256': self.source, 'segments': [
            {'id': 0, 'asr_text': ' A synthetic recording.', 'start_ms': 0, 'end_ms': 1000, 'review_signals': []}]}

    def events(self, **changes):
        message = {'role': 'assistant', 'provider': editor.PROVIDER, 'model': editor.MODEL,
                   'stopReason': 'stop', 'content': [{'type': 'text', 'text': json.dumps({'source_sha256': self.source, 'edits': []})}]}
        message.update(changes)
        return ('\n'.join(json.dumps(row) for row in [{'type': 'message_end', 'message': message}, {'type': 'agent_settled'}])+'\n').encode()

    def test_requires_exact_provider_model_and_success(self):
        self.assertEqual(editor.parse_events(self.events())['edits'], [])
        for changes in ({'model': 'other'}, {'provider': 'other'}, {'stopReason': 'error'}, {'stopReason': 'length'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): editor.parse_events(self.events(**changes))

    def test_requires_settlement_and_no_tools(self):
        unfinished = self.events().split(b'\n')[0]+b'\n'
        with self.assertRaises(ValueError): editor.parse_events(unfinished)
        with self.assertRaises(ValueError): editor.parse_events(self.events()+b'{"type":"tool_execution_start"}\n')

    def test_unicode_line_separator_not_protocol_delimiter(self):
        proposal = {'source_sha256': self.source, 'edits': []}
        text = json.dumps(proposal)+'\u2028'
        events = self.events(content=[{'type': 'text', 'text': text}])
        # Valid Unicode inside a JSON string must not split a protocol record.
        self.assertEqual(len(events.decode().split('\n')), 3)
        with self.assertRaises(ValueError): editor.parse_events(events)

    def test_chunking_preserves_global_ids(self):
        segments = [dict(self.packet['segments'][0], id=i) for i in range(75)]
        chunks = list(editor.chunks(segments))
        self.assertEqual([len(c) for c in chunks], [30, 30, 15])
        self.assertEqual(chunks[1][0]['id'], 30)

    def test_only_whitelisted_metadata_is_shared(self):
        self.packet['segments'][0]['unrelated_private_field'] = 'must not be forwarded'
        result = editor.packet_segments(self.packet)
        self.assertNotIn('unrelated_private_field', result[0])
        self.assertFalse(result[0]['low_token_probability_hint_not_accuracy'])

    def test_bad_proposals_fail_closed(self):
        base = {'source_sha256': self.source, 'edits': []}
        with self.assertRaises(ValueError): editor.validate_proposal(dict(base, source_sha256='b'*64), self.source, self.packet['segments'])
        edit = {'segment': 0, 'start': 0, 'end': 2, 'kind': 'guess', 'replacement': 'something', 'reason': 'Unverified'}
        for changes in ({'end': 2000}, {'segment': 99}, {'replacement': '[hidden]'}, {'kind': 'unclear'}, {'reason': ''}):
            with self.subTest(changes=changes):
                candidate = dict(base, edits=[dict(edit, **changes)])
                with self.assertRaises(ValueError): editor.validate_proposal(candidate, self.source, self.packet['segments'])
        with self.assertRaises(ValueError): editor.validate_proposal(dict(base, edits=[edit, edit]), self.source, self.packet['segments'])

    def test_valid_review_retains_bound_proposal_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'packet.json'; path.write_text(json.dumps(self.packet)); path.chmod(0o600)
            out = root/'review'
            with patch.object(editor, 'invoke', return_value=({'source_sha256': self.source, 'edits': []}, 'f'*64)):
                result = editor.run(path, out, 'unused')
            self.assertEqual(result['status'], 'proposed-awaiting-server-validation')
            receipt = json.loads((out/'receipt.json').read_text())
            self.assertFalse(receipt['audio_shared'])
            self.assertFalse(receipt['verified_verbatim'])
            self.assertEqual(receipt['model'], editor.MODEL)
            self.assertEqual((out/'proposal.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError): editor.run(path, out, 'unused')

    def test_failure_cannot_publish_final_proposal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'packet.json'; path.write_text(json.dumps(self.packet)); path.chmod(0o600)
            with patch.object(editor, 'invoke', side_effect=RuntimeError('synthetic')):
                with self.assertRaises(RuntimeError): editor.run(path, root/'review', 'unused')
            self.assertFalse((root/'review/proposal.json').exists())
            self.assertFalse((root/'review/receipt.json').exists())

    def test_input_must_be_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'packet.json'; path.write_text(json.dumps(self.packet)); path.chmod(0o644)
            with self.assertRaises(ValueError): editor.run(path, Path(temp)/'out', 'unused')

    def test_invocation_disables_context_tools_and_sessions(self):
        code = Path(editor.__file__).read_text()
        for flag in ('--no-session', '--no-tools', '--no-extensions', '--no-skills', '--no-context-files', '--no-prompt-templates', '--offline'):
            self.assertIn(flag, code)
        self.assertIn('start_new_session=True', code)
        self.assertIn('os.killpg', code)


if __name__ == '__main__':
    unittest.main()
