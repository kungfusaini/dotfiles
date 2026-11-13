#!/usr/bin/env python3
"""Hidden PTY smoke test: no windows, global input, credentials or model requests.

python3 tests/pi-enumerate-tui.py [extension-path]
"""
import errno
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

extension = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "home/config/pi/extensions/enumerate.ts").resolve()
root = Path(tempfile.mkdtemp(prefix="pi-enum-tui-"))
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 100, 0, 0))
env = {**os.environ, "PI_CODING_AGENT_DIR": str(root / "agent"), "TERM": "xterm-256color", "COLORTERM": "truecolor", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0"}
# No inherited provider secrets, and a private empty agent directory.
for key in list(env):
    if any(part in key for part in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN")):
        env.pop(key)
process = subprocess.Popen(["pi", "--no-extensions", "--extension", str(extension), "--no-skills", "--no-prompt-templates", "--no-themes", "--session", str(root / "session.jsonl")], cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
os.close(slave)
raw = bytearray()
ansi = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")

def pump(seconds=0.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ready, _, _ = select.select([master], [], [], max(0, end - time.monotonic()))
        if ready:
            try:
                data = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    return
                raise
            if not data:
                return
            raw.extend(data)

def expect(text, since=0, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump()
        if text in ansi.sub("", raw[since:].decode("utf-8", "replace")):
            return
        if process.poll() is not None:
            break
    raise AssertionError(f"Did not see {text!r}; transcript: {root / 'terminal.log'}")

def send(data):
    mark = len(raw)
    os.write(master, data.encode())
    return mark

try:
    pump(2)
    mark = send("/enum Alpha; Beta\r")
    expect("Review agenda", mark)
    mark = send("\r")
    expect("Start this agenda?", mark)
    mark = send("\r")
    expect("Item 1 of 2", mark)
    pump(0.5)
    # Verify Escape stays on the same item before accepting advancement.
    mark = send("/next\r")
    expect("Carry forward:", mark)
    send("\x1b")
    pump(0.5)
    mark = send("/enum status\r")
    expect("Item 1 of 2", mark)
    pump(0.5)
    mark = send("/next\r")
    expect("Carry forward:", mark)
    mark = send("\x1b[B\x1b[B\r")
    expect("LAST ITEM", mark)
    pump(0.5)
    mark = send("/next\r")
    expect("Last item: finish the queue", mark)
    mark = send("\x1b[B\x1b[B\r")
    expect("All 2 items covered", mark)
    pump(0.5)
    mark = send("/next\r")
    expect("No active enumeration", mark)
    # Resize and render the inactive UI without displaying a real terminal.
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 20, 35, 0, 0))
    os.kill(process.pid, signal.SIGWINCH)
    pump(0.5)
    assert process.poll() is None, "TUI crashed after resizing"
    print(f"PASS: hidden native TUI review/confirmation, Escape, /next, LAST, completion and resize ({root})")
finally:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    pump(0.1)
    (root / "terminal.log").write_bytes(raw)
    os.close(master)
