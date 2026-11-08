#!/usr/bin/env python3
"""Opt-in real logind inhibitor test. Does not close the lid or request sleep.

Run with the lid open. Activity fixtures use a private runtime directory, never
real agent records. Only the test process's inhibitor is inspected/released.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def lid_open():
    result = subprocess.run([
        "busctl", "--system", "get-property", "org.freedesktop.login1",
        "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "LidClosed",
    ], check=True, capture_output=True, text=True, timeout=5)
    if result.stdout.strip() != "b false":
        raise RuntimeError("This test requires the physical lid to remain open")


def inhibitors(pid):
    result = subprocess.run(["systemd-inhibit", "--list", "--json=short"],
                            check=True, capture_output=True, text=True, timeout=5)
    return [row for row in json.loads(result.stdout) if row["pid"] == pid]


def wait_for(predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        lid_open()
        if predicate():
            return
        time.sleep(.1)
    raise AssertionError("Timed out waiting for inhibitor transition")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    args = parser.parse_args()
    lid_open()
    with tempfile.TemporaryDirectory(prefix="agent-lid-test.") as root:
        directory = Path(root) / "project-object/pi-activity"
        directory.mkdir(parents=True)
        pid = os.getpid()
        start = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        record = dict(version=1, pid=pid, processStartTime=start, state="working")
        target = directory / f"{pid}.json"

        def write(**changes):
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(record | changes))
            temporary.replace(target)

        write()
        process = subprocess.Popen([args.binary], env={**os.environ, "XDG_RUNTIME_DIR": root})
        try:
            wait_for(lambda: inhibitors(process.pid))
            rows = inhibitors(process.pid)
            assert len(rows) == 1 and rows[0]["what"] == "handle-lid-switch" and rows[0]["mode"] == "block", rows
            write(state="idle")
            time.sleep(1)
            assert inhibitors(process.pid), "Released before settle grace"
            wait_for(lambda: not inhibitors(process.pid))
            write()
            wait_for(lambda: inhibitors(process.pid))
            write(processStartTime="0")
            wait_for(lambda: not inhibitors(process.pid))
            write()
            wait_for(lambda: inhibitors(process.pid))
            process.terminate()
            assert process.wait(timeout=5) == 0
            wait_for(lambda: not inhibitors(process.pid))
            print("PASS: real logind lid-only block, grace, idle release, reacquire, stale PID and clean shutdown")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
