"""Shared-profile, focus-preserving Vivaldi app windows for agent launches.

The loopback URL supplies a unique app_id even through Chromium's singleton
handoff. No debugger, extension, separate profile, or browser-wide rule is used.
Call with the project-browser lock held: the named rule is deliberately reused.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from urllib.parse import quote, urlsplit, urlunsplit

RULE = "windowrule[project-object-agent-launch]"
TIMEOUT = 15.0
ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
APP_PREFIX = "vivaldi-127.0.0.1__poagent"


def app_launch_matches(client, launch_id):
    """Recognize only our capability-bearing app identity, not arbitrary browsers."""
    if not re.fullmatch(r"[0-9a-f]{32}", launch_id):
        return False
    pattern = re.escape(APP_PREFIX + launch_id) + r"[0-9a-f]{16}-.+"
    return any(re.fullmatch(pattern, str(client.get(key, ""))) for key in ("class", "initialClass"))


def validate(workspace, urls, launch_id):
    if not workspace or any(c in workspace for c in ";[],\r\n\0"):
        raise ValueError("Unsafe or missing agent browser workspace")
    if not re.fullmatch(r"[0-9a-f]{32}", launch_id):
        raise ValueError("Missing or invalid agent browser launch identity")
    for url in urls:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or any(ord(c) < 32 or ord(c) == 127 for c in url)):
            raise ValueError("Agent browser requires an HTTP(S) URL without control characters")


def ascii_uri(url):
    parsed = urlsplit(url)
    host = parsed.hostname.encode("idna").decode("ascii")
    if ":" in host:
        host = "[" + host + "]"
    if parsed.port is not None:
        host += ":" + str(parsed.port)
    if "@" in parsed.netloc:
        host = quote(parsed.netloc.rsplit("@", 1)[0], safe=":!$&'()*+,;=-._~%") + "@" + host
    safe = "/:@!$&'()*+,;=-._~%"
    return urlunsplit((parsed.scheme, host, quote(parsed.path, safe=safe),
                       quote(parsed.query, safe=safe + "?"), quote(parsed.fragment, safe=safe + "?")))


def command(hyprctl, *arguments):
    try:
        result = subprocess.run([hyprctl, *arguments], capture_output=True, text=True, check=False, timeout=5)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Agent browser compositor request timed out") from None
    if result.returncode != 0:
        raise RuntimeError("Agent browser compositor request failed")
    return result.stdout


def keyword(hyprctl, key, value):
    if command(hyprctl, "keyword", RULE + ":" + key, value).strip() != "ok":
        raise RuntimeError("Hyprland refused the agent browser rule")


@contextmanager
def placement_rule(hyprctl, workspace, pattern):
    # Disable before changing matches/effects. Never briefly match all windows.
    keyword(hyprctl, "enable", "0")
    try:
        for key, value in (("match:class", pattern), ("no_initial_focus", "on"),
                           ("suppress_event", "activate activatefocus"),
                           ("workspace", "name:" + workspace + " silent"), ("enable", "1")):
            keyword(hyprctl, key, value)
        yield
    finally:
        # One reusable disabled rule, not an accumulating rule per launch.
        keyword(hyprctl, "enable", "0")


class RedirectServer(ThreadingHTTPServer):
    # Request parsing cannot block the launch/deadline loop. Cap concurrent
    # clients and explicitly close them on exit, including slow header senders.
    def __init__(self, *args):
        self.connections = set()
        self.connection_lock = threading.Lock()
        super().__init__(*args)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(0.25)
        with self.connection_lock:
            if len(self.connections) >= 8:
                connection.close()
                raise OSError("Too many agent redirect connections")
            self.connections.add(connection)
        return connection, address

    def shutdown_request(self, request):
        with self.connection_lock:
            self.connections.discard(request)
        super().shutdown_request(request)

    def handle_error(self, request, client_address):
        pass  # Do not log request details; launch verification reports failure.

    def server_close(self):
        with self.connection_lock:
            connections = list(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        super().server_close()


@contextmanager
def redirect_server(token, target):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            expected_host = "127.0.0.1:" + str(self.server.server_port)
            if self.path != "/" + token or self.headers.get_all("Host") != [expected_host]:
                self.send_error(404)
                return
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.server.redirected = True

        def log_message(self, *_args):
            pass  # Never log capability paths or destination URLs.

    with RedirectServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 0.05
        server.redirected = False
        yield server


def browser_environment():
    # A cold-started shared browser must not retain Pi/launch context and later
    # misclassify the user's own browser actions as agent requests.
    prefixes = ("PI_", "PROJECT_OBJECT_", "PROJECT_BROWSER_", "PROJECT_PICKER_")
    activation = {"HL_EXEC_RULE_TOKEN", "HL_INITIAL_WORKSPACE_TOKEN", "XDG_ACTIVATION_TOKEN", "DESKTOP_STARTUP_ID"}
    return {key: value for key, value in os.environ.items()
            if not key.startswith(prefixes) and key not in activation}


def open_agent_urls(urls, workspace, launch_id, *, hyprctl, vivaldi):
    validate(workspace, urls, launch_id)
    # Normalize every target before any browser launch or Location header write.
    targets = [ascii_uri(url) for url in urls]
    for url in targets:
        token = "poagent" + launch_id + secrets.token_hex(8)
        app_class = "vivaldi-127.0.0.1__" + token
        pattern = "^" + re.escape(app_class) + r"-.+$"
        with redirect_server(token, url) as server, placement_rule(hyprctl, workspace, pattern):
            before = json.loads(command(hyprctl, "clients", "-j"))
            if not isinstance(before, list):
                raise RuntimeError("Invalid agent browser client snapshot")
            addresses = {c.get("address") for c in before if isinstance(c, dict)}
            bootstrap = "http://127.0.0.1:" + str(server.server_port) + "/" + token
            # The normal profile is intentional: singleton IPC shares login state.
            # --no-activate is only a hint; the class-specific compositor rule is
            # what suppresses initial focus and activation, including handoffs.
            subprocess.Popen([vivaldi, "--no-activate", "--app=" + bootstrap],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True, env=browser_environment())
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                server.handle_request()
                current = json.loads(command(hyprctl, "clients", "-j"))
                if not isinstance(current, list):
                    raise RuntimeError("Invalid agent browser client snapshot")
                matches = [c for c in current if isinstance(c, dict) and c.get("mapped")
                           and re.fullmatch(pattern, str(c.get("class", "")))
                           and ADDRESS.fullmatch(str(c.get("address", "")))
                           and c["address"] not in addresses]
                if len(matches) > 1:
                    raise RuntimeError("Ambiguous agent browser window; refusing to guess")
                if matches:
                    if matches[0].get("workspace", {}).get("name") != workspace:
                        raise RuntimeError("Agent browser did not map on the invoking workspace")
                    if server.redirected:
                        break
            else:
                raise RuntimeError("Agent browser launch timed out; a window may still be running")
