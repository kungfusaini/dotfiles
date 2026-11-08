#!/usr/bin/env python3
"""Defer only lid-triggered sleep while live, tracked Pi agents work.

No suspend calls: logind rechecks a closed lid when our low-level inhibitor
is released. Manual sleep and critical-battery actions remain independent.
"""
import json
import logging
import os
from pathlib import Path
import signal
import select
import stat
import time

POLL_SECONDS = 0.25
SETTLE_SECONDS = 5.0
MAX_RECORD_BYTES = 16384


def process_start_time(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        # A zombie is finished even while its parent has not reaped it.
        return fields[19] if fields[0] not in ("Z", "X") else None
    except (OSError, IndexError):
        return None


def agents_working(directory):
    """All projects/streams; process birth time prevents stale PID reuse.

    No heartbeat timeout: a long tool call can legitimately leave an unchanged
    working record. Untracked jobs cannot be inferred from this protocol.
    """
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise RuntimeError("Activity directory must be an owned, non-symlink directory")
    for path in directory.iterdir():
        if path.suffix != ".json" or not path.stem.isdecimal():
            continue
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                        or metadata.st_size > MAX_RECORD_BYTES):
                    continue
                value = json.loads(stream.read(MAX_RECORD_BYTES + 1))
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(value, dict) or value.get("version") != 1:
            continue
        pid = value.get("pid")
        start = value.get("processStartTime")
        if (type(pid) is not int or pid <= 0 or path.name != f"{pid}.json"
                or not isinstance(start, str) or not start.isdecimal()):
            continue
        if value.get("state") == "working" and process_start_time(pid) == start:
            return True
    return False


class LidGuard:
    def __init__(self, acquire, close=os.close):
        self.acquire = acquire
        self.close = close
        self.fd = None
        self.idle_since = None

    def update(self, working, now):
        if working:
            self.idle_since = None
            if self.fd is None:
                self.fd = self.acquire()
                logging.info("Working agents: deferring lid-triggered sleep")
        elif self.fd is not None:
            if self.idle_since is None:
                self.idle_since = now
            if now - self.idle_since >= SETTLE_SECONDS:
                self.release()
                logging.info("Agents settled: normal lid policy restored")

    def release(self):
        if self.fd is not None:
            self.close(self.fd)
            self.fd = None
        self.idle_since = None


def main():
    import dbus

    logging.basicConfig(level=logging.INFO, format="agent-lid-sleep: %(message)s")
    directory = Path(os.environ["XDG_RUNTIME_DIR"]) / "project-object" / "pi-activity"
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1"),
                             "org.freedesktop.login1.Manager")

    def acquire():
        return manager.Inhibit("handle-lid-switch", "Agent Lid Sleep",
                               "Tracked agents are working; waiting before lid sleep", "block").take()

    guard = LidGuard(acquire)
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Cover startup and require a settled interval before releasing.
        guard.update(True, time.monotonic())
        while running:
            if not bus.get_is_connected():
                raise RuntimeError("System bus disconnected")
            if guard.fd is not None:
                poller = select.poll()
                poller.register(guard.fd, select.POLLERR | select.POLLHUP)
                if poller.poll(0):
                    raise RuntimeError("Lid inhibitor disconnected; restarting")
            guard.update(agents_working(directory), time.monotonic())
            time.sleep(POLL_SECONDS)
    finally:
        guard.release()
        bus.close()


if __name__ == "__main__":
    main()
