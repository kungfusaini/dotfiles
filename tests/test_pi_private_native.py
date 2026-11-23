"""Actual native Pi TUI + isolated inference/history test in a hidden PTY."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import tempfile
import termios
import time

from test_pi_private import load
from test_pi_private_terminal import until, wait_exit


class Native:
    def __init__(self, command):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execv(command[0], command)
        self.output = b""
        self.closed = False
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        try:
            self.output += until(self.fd, "Private chat ready.", timeout=210)
        except BaseException:
            self.cleanup()
            raise

    def send(self, text):
        os.write(self.fd, text.encode())

    def wait(self, text):
        self.output += until(self.fd, text, timeout=60)

    def poll_until(self, condition, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            ready, _, _ = select.select([self.fd], [], [], 0.1)
            if ready:
                try:
                    self.output += os.read(self.fd, 65536)
                except OSError:
                    break
        raise AssertionError("Native TUI condition did not complete: " + repr(self.output[-2000:]))

    def quit(self):
        self.send("/quit\r")
        self.output += wait_exit(self.pid, self.fd)
        self.closed = True
        os.close(self.fd)
        assert b"\x1b[?1049l" in self.output, "Native fullscreen must restore the terminal"
        tail = self.output.rsplit(b"\x1b[?1049l", 1)[1]
        assert b"NATIVE_PRIVATE_SCROLLBACK_SENTINEL" not in tail, "Private transcript spilled into shell scrollback"
        assert b"To resume this session" not in tail, "Do not suggest opening private history in normal Pi"

    def cleanup(self):
        if not self.closed:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except ProcessLookupError:
                pass
            os.close(self.fd)
            self.closed = True


def records(history):
    result = []
    for path in history.glob("*.jsonl"):
        for line in path.read_text().splitlines():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # A concurrent append may not have completed yet.
    return result


def run(package):
    built = load("native_built_launcher", package / "bin/pi-private")
    with tempfile.TemporaryDirectory(prefix="pi-private-native-") as tmp:
        history = Path(tmp) / "sessions"
        history.mkdir(mode=0o700)
        command = built.sandbox_command(history, Path.home() / built.MODEL_RELATIVE)
        native = Native(command)
        try:
            assert b"PRIVATE" in native.output
            # These are handled by native Pi, not interpreted by a text frontend.
            native.send("/share\r")
            native.wait("Unavailable in private chat")
            native.send("!touch /history/SHOULD_NOT_EXIST\r")
            native.wait("Unavailable in private chat")
            native.send("\x0c")  # Native Ctrl-L model selector shortcut.
            native.wait("Unavailable in private chat")
            prompt = "Reply briefly in Markdown with a bold heading and two bullet points.\nNATIVE_PRIVATE_SCROLLBACK_SENTINEL is a native multiline editor test; @/not-a-file is literal text."
            native.send("\x1b[200~" + prompt + "\x1b[201~\r")
            def completed():
                return any(r.get("type") == "message" and r["message"].get("role") == "assistant" for r in records(history))
            native.poll_until(completed)
            saved = records(history)
            messages = [r["message"] for r in saved if r.get("type") == "message"]
            user = next(m for m in messages if m.get("role") == "user")
            text = user["content"] if isinstance(user["content"], str) else "".join(c.get("text", "") for c in user["content"])
            assert text == prompt, text
            assistant = next(m for m in messages if m.get("role") == "assistant")
            assert assistant.get("stopReason") != "error", assistant.get("errorMessage")
            assert not any(m.get("role") in ("toolResult", "bashExecution") for m in messages)
            assert not (history / "SHOULD_NOT_EXIST").exists()
            native.send("/name Native private fixture\r")
            native.poll_until(lambda: any(r.get("type") == "session_info" and r.get("name") == "Native private fixture" for r in records(history)))
            native.quit()
        finally:
            native.cleanup()
        files = list(history.glob("*.jsonl"))
        assert len(files) == 1
        assert files[0].stat().st_mode & 0o077 == 0
        reopened = Native(command)
        try:
            reopened.send("/resume\r")
            reopened.wait("Resume Session")
            reopened.send("Native private fixture")
            time.sleep(0.2)
            reopened.send("\r")
            reopened.wait("Resumed session")
            reopened.send("/session\r")
            reopened.wait("Native private fixture")
            reopened.quit()
        finally:
            reopened.cleanup()
        assert len(list(history.glob("*.jsonl"))) == 1
        for record in records(history):
            if record.get("type") == "model_change":
                assert record.get("provider") == "private-local", record
        print("PASS: actual Pi native TUI, multiline editor, guarded commands/shortcut, real isolated inference, named native history picker and session reopening")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=Path)
    run(parser.parse_args().package)
