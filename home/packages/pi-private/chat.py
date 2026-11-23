"""Minimal text-only Pi RPC UI. No native TUI command, shell, or upload surface."""
import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request

MODEL = "private-qwen"
HISTORY = Path("/history")
ALLOWED_RPC = {"get_state", "get_commands", "prompt", "new_session", "switch_session", "get_messages"}


def plain(text):
    # Never interpret model/history text as terminal control sequences (OSC52,
    # hyperlinks, cursor movement, etc.). Also remove bidi/format controls.
    return "".join(c for c in str(text) if c in "\n\t" or not unicodedata.category(c).startswith("C"))


def action(text):
    text = text.strip()
    if not text:
        return "empty", None
    if text in ("/exit", "/quit"):
        return "exit", None
    if text in ("/new", "/history", "/help"):
        return text[1:], None
    if text.startswith("/resume ") and text[8:].isdigit():
        return "resume", int(text[8:])
    if text.startswith(("/", "!", "@")):
        raise ValueError("Only /new, /history, /resume NUMBER, /help and /exit are available. Text only; no shell or attachments.")
    return "prompt", text


def session_files():
    return sorted((p for p in HISTORY.glob("*.jsonl") if not p.is_symlink() and p.is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def configure():
    agent = Path(os.environ["PI_CODING_AGENT_DIR"])
    agent.mkdir(parents=True, exist_ok=True)
    settings = {"packages": [], "retry": {"enabled": False}, "cacheWarming": {"enabled": False}}
    (agent / "settings.json").write_text(json.dumps(settings))
    (agent / "models.json").write_text(json.dumps({"providers": {"private-local": {
        "baseUrl": "http://127.0.0.1:18080/v1", "api": "openai-completions", "apiKey": "local",
        "models": [{"id": MODEL, "name": "Private local Qwen", "input": ["text"],
                    "contextWindow": 8192, "maxTokens": 1024,
                    "compat": {"supportsStore": False, "supportsDeveloperRole": False,
                               "supportsReasoningEffort": False, "maxTokensField": "max_tokens"}}]
    }}}))


def pi_command(executable):
    return [executable, "--mode", "rpc", "--offline", "--no-approve", "--no-tools",
            "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
            "--no-context-files", "--session-dir", str(HISTORY),
            "--provider", "private-local", "--model", MODEL, "--thinking", "off",
            "--system-prompt", "You are a private, local, chat-only assistant. You have no tools or file access. Answer the user's messages directly."]


class Rpc:
    def __init__(self, executable, log):
        self.child = subprocess.Popen(pi_command(executable), stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=log, close_fds=True)
        self.records = queue.Queue()
        self.sequence = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.child.stdout:
                self.records.put(json.loads(line))
        except (ValueError, OSError) as error:
            self.records.put(error)
        finally:
            self.records.put(None)

    def request(self, kind, **fields):
        if kind not in ALLOWED_RPC:
            raise ValueError("RPC operation not allowed")
        self.sequence += 1
        ident = str(self.sequence)
        self.child.stdin.write((json.dumps({"id": ident, "type": kind, **fields}) + "\n").encode())
        self.child.stdin.flush()
        response = None
        settled = False
        deadline = time.monotonic() + (600 if kind == "prompt" else 60)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Private Pi timed out; closing without fallback")
            try:
                record = self.records.get(timeout=min(remaining, 1))
            except queue.Empty:
                continue
            if record is None or isinstance(record, Exception):
                raise RuntimeError("Private Pi stopped unexpectedly")
            if record.get("type") == "response" and record.get("id") == ident:
                if not record.get("success"):
                    raise RuntimeError(plain(record.get("error", "Private Pi rejected the request")))
                response = record
            if kind == "prompt":
                if record.get("type") == "message_update":
                    update = record.get("assistantMessageEvent", {})
                    if update.get("type") == "text_delta":
                        print(plain(update["delta"]), end="", flush=True)
                if record.get("type") == "message_end":
                    message = record.get("message", {})
                    if message.get("errorMessage"):
                        print("\nModel error: " + plain(message["errorMessage"]))
                if record.get("type") == "agent_settled":
                    settled = True
            if response is not None and (kind != "prompt" or settled):
                return response.get("data", {})

    def close(self):
        if self.child.stdin:
            self.child.stdin.close()
        try:
            self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.child.terminate()
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()


def isolation_check():
    for path in ["/home/sumeet", "/run/user", "/tmp/.X11-unix", "/etc/resolv.conf"]:
        if Path(path).exists():
            raise RuntimeError("Unexpected host resource exposed: " + path)
    for address in [("1.1.1.1", 443), ("127.0.0.1", 18080)]:
        try:
            with socket.create_connection(address, timeout=1):
                raise RuntimeError("Unexpected reachable network service")
        except OSError:
            pass
    if any(key in os.environ for key in ["OPENAI_API_KEY", "SSH_AUTH_SOCK", "DBUS_SESSION_BUS_ADDRESS", "PI_SESSION_FILE"]):
        raise RuntimeError("Unexpected inherited host environment")
    print("Network namespace: " + os.readlink("/proc/self/ns/net"))
    print("PASS: sandbox denies external/host-loopback access and omits host home, sockets, credentials and normal session environment.")


def wait_for_model(server):
    deadline = time.monotonic() + 180
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Private model failed to start; no cloud fallback")
        try:
            with opener.open("http://127.0.0.1:18080/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError("Private model startup timed out; no cloud fallback")


def interface(rpc):
    print("PRIVATE · LOCAL ONLY · saved separately · no tools\n/new  /history  /resume NUMBER  /exit\nCtrl-C exits private mode. Private history is not encrypted.")
    while True:
        try:
            kind, value = action(input("[PRIVATE · LOCAL ONLY] You> "))
        except ValueError as error:
            print(error)
            continue
        if kind == "exit":
            return
        if kind == "new":
            rpc.request("new_session")
            print("New private conversation.")
        elif kind == "history":
            for index, path in enumerate(session_files(), 1):
                print(f"{index}. {plain(path.stem)}")
        elif kind == "resume":
            files = session_files()
            if value < 1 or value > len(files):
                print("No such private conversation. Use /history.")
                continue
            path = files[value - 1].resolve()
            if path.parent != HISTORY:
                raise RuntimeError("Invalid private session path")
            rpc.request("switch_session", sessionPath=str(path))
            for message in rpc.request("get_messages").get("messages", []):
                if message.get("role") in ("user", "assistant"):
                    content = message.get("content", [])
                    text = content if isinstance(content, str) else "".join(c.get("text", "") for c in content if c.get("type") == "text")
                    print(plain(message["role"] + ": " + text))
        elif kind == "prompt":
            print("Private Pi> ", end="", flush=True)
            rpc.request("prompt", message=value)
            print()
        elif kind == "help":
            print("/new: fresh private chat; /history: list saved chats; /resume NUMBER: reopen; /exit: return to normal Pi. No shell, attachments, exports, uploads or cloud switching.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi", required=True)
    parser.add_argument("--llama", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.check:
        isolation_check()
        return
    configure()
    rpc = None
    server = None
    # In-memory sandbox /tmp only: model and RPC diagnostics are never journaled
    # or copied into the host's normal logs.
    with tempfile.TemporaryFile() as log:
        try:
            print("Starting isolated local model (CPU); this may take a moment.", flush=True)
            server = subprocess.Popen([args.llama, "--model", "/model.gguf", "--alias", MODEL,
                "--host", "127.0.0.1", "--port", "18080", "--ctx-size", "8192",
                "--parallel", "1", "--threads", "4", "--threads-batch", "4",
                "--n-gpu-layers", "0", "--jinja", "--reasoning", "off",
                "--log-disable"], stdout=log, stderr=log, close_fds=True)
            wait_for_model(server)
            rpc = Rpc(args.pi, log)
            state = rpc.request("get_state")
            model = state.get("model", {})
            if model.get("provider") != "private-local" or model.get("id") != MODEL:
                raise RuntimeError("Unexpected model selected; refusing private chat")
            commands = rpc.request("get_commands").get("commands", [])
            # Pi 0.87.1 always registers its bundled llama command even with
            # --no-extensions. The text UI never dispatches it (or any /command).
            if any(c.get("name") != "llama" for c in commands):
                raise RuntimeError("Unexpected commands loaded")
            interface(rpc)
        finally:
            if rpc:
                rpc.close()
            if server:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nPrivate chat closed.")
    except (OSError, RuntimeError) as error:
        print("Private chat closed: " + plain(error), file=sys.stderr)
        sys.exit(1)
