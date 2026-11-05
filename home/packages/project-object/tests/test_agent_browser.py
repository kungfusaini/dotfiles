import contextlib
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.parse import urlsplit
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agent_browser as agent

ID = "a" * 32
NONCE = "b" * 16
TOKEN = "poagent" + ID + NONCE
CLASS = "vivaldi-127.0.0.1__" + TOKEN + "-Default"
WINDOW = {"address": "0xabc", "mapped": True, "class": CLASS, "workspace": {"name": "Agent"}}


class AgentBrowserTests(unittest.TestCase):
    def test_shared_browser_does_not_retain_agent_or_native_launch_context(self):
        with mock.patch.dict(os.environ, {"PI_CODING_AGENT": "1", "PI_SESSION_ID": "private",
                             "PROJECT_OBJECT_ID": "project", "PROJECT_OBJECT_LAUNCH_ID": ID,
                             "PROJECT_BROWSER_VIVALDI": "wrapper", "HL_EXEC_RULE_TOKEN": "stale",
                             "HL_INITIAL_WORKSPACE_TOKEN": "stale", "XDG_ACTIVATION_TOKEN": "stale",
                             "HOME": "/test", "XDG_RUNTIME_DIR": "/private/runtime"}, clear=True):
            self.assertEqual(agent.browser_environment(), {"HOME": "/test", "XDG_RUNTIME_DIR": "/private/runtime"})

    def test_international_destinations_become_ascii_uris(self):
        url = "https://例え.テスト/日本語?q=é&already=%20#汉"
        normalized = agent.ascii_uri(url)
        self.assertEqual(normalized, "https://xn--r8jz45g.xn--zckzah/%E6%97%A5%E6%9C%AC%E8%AA%9E?q=%C3%A9&already=%20#%E6%B1%89")
        with agent.redirect_server(TOKEN, normalized) as server:
            status, headers = self.request(server, "/" + TOKEN)
            self.assertEqual(status, 302)
            self.assertEqual(headers["Location"], normalized)
        self.assertEqual(agent.ascii_uri("http://[::1]:8080/a"), "http://[::1]:8080/a")

    def test_slow_header_client_cannot_hold_launch_deadline_or_rule_cleanup(self):
        stop = threading.Event()
        threads = []

        def launch(argv, **_kwargs):
            parsed = urlsplit(argv[-1].removeprefix("--app="))
            connection = socket.create_connection((parsed.hostname, parsed.port), timeout=1)

            def drip():
                with connection:
                    try:
                        connection.sendall(b"GET / HTTP/1.1\\r\\nHost: ")
                        while not stop.wait(0.1):
                            connection.sendall(b"x")
                    except OSError:
                        pass
            thread = threading.Thread(target=drip, daemon=True)
            threads.append(thread)
            thread.start()

        start = time.monotonic()
        try:
            with mock.patch.object(agent, "TIMEOUT", 0.3), \
                    mock.patch.object(agent, "command", side_effect=lambda _ctl, kind, *a: "[]" if kind == "clients" else "ok"), \
                    mock.patch.object(agent.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(agent, "keyword", wraps=agent.keyword) as keyword, \
                    self.assertRaisesRegex(RuntimeError, "timed out"):
                agent.open_agent_urls(["https://example.com"], "Agent", ID, hyprctl="ctl", vivaldi="browser")
            self.assertLess(time.monotonic() - start, 2)
            self.assertEqual(keyword.call_args_list[-1], mock.call("ctl", "enable", "0"))
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=1)
                self.assertFalse(thread.is_alive())

    def test_exact_app_identity_only(self):
        self.assertTrue(agent.app_launch_matches(WINDOW, ID))
        self.assertTrue(agent.app_launch_matches({"initialClass": CLASS}, ID))
        for value in ["vivaldi-stable", CLASS + "\n", CLASS.replace(ID, "c" * 32), "x" + CLASS]:
            self.assertFalse(agent.app_launch_matches({"class": value}, ID))
        self.assertFalse(agent.app_launch_matches(WINDOW, ".*"))

    def test_rejects_unsafe_input_before_any_launch(self):
        cases = [("bad,name", ["https://example.com"], ID), ("Agent", ["file:///tmp/x"], ID),
                 ("Agent", ["https://example.com/\r\nX: y"], ID), ("Agent", ["https://example.com"], "")]
        for workspace, urls, identity in cases:
            with self.subTest(urls=urls), mock.patch.object(agent.subprocess, "Popen") as launch, self.assertRaises(ValueError):
                agent.open_agent_urls(urls, workspace, identity, hyprctl="ctl", vivaldi="browser")
            launch.assert_not_called()

    def request(self, server, path, host=None):
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            headers = {} if host is None else {"Host": host}
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            status, headers = response.status, dict(response.getheaders())
            response.read()
            connection.close()
            return status, headers
        finally:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_redirect_requires_capability_and_exact_host_and_is_not_cached_or_referred(self):
        with agent.redirect_server(TOKEN, "https://example.com/private?state=value") as server:
            for path, host in [("/wrong", None), ("/" + TOKEN + "?extra", None), ("/" + TOKEN, "attacker.test")]:
                status, headers = self.request(server, path, host)
                self.assertEqual(status, 404)
                self.assertNotIn("Location", headers)
                self.assertFalse(server.redirected)
            status, headers = self.request(server, "/" + TOKEN)
            self.assertEqual(status, 302)
            self.assertEqual(headers["Location"], "https://example.com/private?state=value")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertTrue(server.redirected)
            self.assertEqual(server.server_address[0], "127.0.0.1")

    def test_named_rule_is_disabled_before_configuration_and_after_failure(self):
        with mock.patch.object(agent, "keyword") as keyword:
            with self.assertRaisesRegex(RuntimeError, "test"):
                with agent.placement_rule("ctl", "Agent", "^exact$"):
                    raise RuntimeError("test")
        self.assertEqual(keyword.call_args_list[0], mock.call("ctl", "enable", "0"))
        self.assertEqual(keyword.call_args_list[-1], mock.call("ctl", "enable", "0"))
        self.assertIn(mock.call("ctl", "match:class", "^exact$"), keyword.call_args_list)
        self.assertIn(mock.call("ctl", "workspace", "name:Agent silent"), keyword.call_args_list)

    def test_rule_failure_prevents_browser_launch(self):
        with mock.patch.object(agent, "keyword", side_effect=RuntimeError("refused")), \
                mock.patch.object(agent.subprocess, "Popen") as launch, self.assertRaisesRegex(RuntimeError, "refused"):
            agent.open_agent_urls(["https://example.com"], "Agent", ID, hyprctl="ctl", vivaldi="browser")
        launch.assert_not_called()

    def test_keyword_exit_zero_error_is_not_success(self):
        with mock.patch.object(agent, "command", return_value="invalid rule"), self.assertRaises(RuntimeError):
            agent.keyword("ctl", "enable", "1")

    def launch_fixture(self, snapshots):
        server = mock.Mock(server_port=9099, redirected=True)
        return (mock.patch.object(agent, "redirect_server", return_value=contextlib.nullcontext(server)),
                mock.patch.object(agent, "placement_rule", return_value=contextlib.nullcontext()),
                mock.patch.object(agent.secrets, "token_hex", return_value=NONCE),
                mock.patch.object(agent, "command", side_effect=[json.dumps(s) for s in snapshots]),
                mock.patch.object(agent.subprocess, "Popen"))

    def test_success_launches_app_only_using_default_profile(self):
        with contextlib.ExitStack() as stack:
            contexts = [stack.enter_context(p) for p in self.launch_fixture([[], [WINDOW]])]
            agent.open_agent_urls(["https://example.com"], "Agent", ID, hyprctl="ctl", vivaldi="browser")
            launch = contexts[-1]
        argv = launch.call_args.args[0]
        self.assertEqual(argv, ["browser", "--no-activate", "--app=http://127.0.0.1:9099/" + TOKEN])
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertNotIn("https://example.com", " ".join(argv))

    def test_wrong_workspace_and_ambiguous_windows_fail_without_moving_any_window(self):
        for windows in [[{**WINDOW, "workspace": {"name": "Wrong"}}], [WINDOW, {**WINDOW, "address": "0xdef"}]]:
            with contextlib.ExitStack() as stack:
                contexts = [stack.enter_context(p) for p in self.launch_fixture([[], windows])]
                with self.assertRaises(RuntimeError):
                    agent.open_agent_urls(["https://example.com"], "Agent", ID, hyprctl="ctl", vivaldi="browser")
                self.assertTrue(all(c.args[1:] == ("clients", "-j") for c in contexts[3].call_args_list))

    def test_no_exact_new_window_times_out(self):
        for windows in [[], [{**WINDOW, "mapped": False}], [{**WINDOW, "class": "vivaldi-stable"}]]:
            with contextlib.ExitStack() as stack:
                for p in self.launch_fixture([[], windows]): stack.enter_context(p)
                stack.enter_context(mock.patch.object(agent.time, "monotonic", side_effect=[0, 0, 16]))
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    agent.open_agent_urls(["https://example.com"], "Agent", ID, hyprctl="ctl", vivaldi="browser")


if __name__ == "__main__":
    unittest.main()
