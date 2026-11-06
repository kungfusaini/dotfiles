"""Offline regression tests; never store real conversation contents."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "home/config/pi/skills/gemini-share-capture/scripts/extract-gemini-share.py"
spec = importlib.util.spec_from_file_location("capture", SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def turn(user, assistant):
    return [None, None, [[user]], [[[None, [assistant]]]]]


class CaptureTests(unittest.TestCase):
    def test_direct_url(self):
        self.assertEqual(capture.resolve_share("https://gemini.google.com/share/abc?tracking=1"),
                         ("abc", "https://gemini.google.com/share/abc?hl=en"))

    def test_short_link(self):
        with patch.object(capture.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://gemini.google.com/share/abc?skid=xyz")):
            self.assertEqual(capture.resolve_share("https://share.gemini.google/short")[0], "abc")

    def test_reject_untrusted_urls(self):
        for url in ["http://gemini.google.com/share/a", "https://example.com/share/a", "https://gemini.google.com.evil/share/a", "https://user@gemini.google.com/share/a"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture.resolve_share(url)

    def test_reject_external_short_redirect(self):
        with patch.object(capture.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "https://example.com/share/a")), self.assertRaises(ValueError):
            capture.resolve_share("https://share.gemini.google/a")

    def test_preserves_speakers_and_whitespace(self):
        self.assertEqual(capture.extract_turns([[None, [turn("  My idea\n", "A reply")]]]), [("  My idea\n", "A reply")])

    def test_empty_and_malformed_payloads(self):
        for payload in [[], None, [[None, []]], [[None, [turn("", "")]]], [[None, [None]]]]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                capture.extract_turns(payload)

    def test_one_malformed_speaker_fails(self):
        for value in [[None, None, [["valid user"]], []],
                      [None, None, [], [[[None, ["valid reply"]]]]],
                      [None, None, [["valid user"]], [[[None, "not chunks"]]]]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture.extract_turns([[None, [value]]])

    def test_curl_transport(self):
        result = subprocess.CompletedProcess([], 0, b"body\nhttps://gemini.google.com/share/a")
        with patch.object(capture.subprocess, "run", return_value=result) as run:
            self.assertEqual(capture.fetch_text("https://gemini.google.com/share/a"), ("https://gemini.google.com/share/a", "body"))
            self.assertIn("--disable", run.call_args.args[0])
            self.assertIn("--max-redirs", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
