#!/usr/bin/env python3
"""Connect ThinkPad fold edges to the shared Tablet Home lifecycle."""
import fcntl
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time


def chat(command):
    result = subprocess.run(["tablet-chat", command], check=True, capture_output=True,
                            text=True, timeout=40)
    return json.loads(result.stdout)


def leave_home(workspace):
    # Closing is asynchronous: wait for input/settings/orientation restoration,
    # not just the IPC acknowledgment. Never run legacy leave under a live Home.
    if chat("status").get("running"):
        chat("close")
    deadline = time.monotonic() + 35
    runtime = Path(os.environ["XDG_RUNTIME_DIR"]) / "tablet-chat"
    while chat("status").get("running") or (runtime / "recovery.json").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Tablet Home cleanup is pending; journal retained; use tablet-chat recover if its owner exited")
        time.sleep(.1)
    # Also handles an old panel left active across the one-time migration.
    state = workspace["load_state"]()
    if state and (state.get("enabled") or state.get("exit_pending")):
        subprocess.run(["tablet-workspace", "leave-automatic"], check=True, timeout=15)


def watch():
    workspace = runpy.run_path(os.environ["TABLET_WORKSPACE_SOURCE"])
    # Share the legacy singleton, but NOT its action lock: Home's setup/cleanup
    # invokes tablet-workspace, which takes that lock itself.
    lock_path = workspace["state_path"]().with_name("tablet-fold-watch.lock")
    with lock_path.open("a") as singleton:
        try:
            fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        watcher = workspace["FoldWatcher"](
            enter_mode=lambda: chat("start-fold"),
            leave_mode=lambda: leave_home(workspace),
            mode_active=lambda: chat("status").get("automatic", False))
        last_error = None
        while True:
            try:
                watcher.tick()
                last_error = None
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                # Captured command errors can contain private backend diagnostics;
                # keep those in their existing private logs, not the fold log.
                message = str(error)
                if message != last_error:
                    print(f"tablet-fold-watch: {message}", file=sys.stderr, flush=True)
                    last_error = message
                time.sleep(4.5)
            time.sleep(.5)


if __name__ == "__main__":
    watch()
