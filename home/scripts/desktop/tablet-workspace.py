#!/usr/bin/env python3
"""Reversible tablet workspace with automatic ThinkPad fold transitions."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORKSPACE = "tablet-trial"


def hypr(*args, json_output=False):
    result = subprocess.run(["hyprctl", *args], check=True, capture_output=True, text=True, timeout=3)
    return json.loads(result.stdout) if json_output else result.stdout


def dispatch(*args):
    hypr("dispatch", *args)


def state_path():
    return Path(os.environ["XDG_RUNTIME_DIR"]) / "tablet-workspace.json"


def load_state():
    try:
        state = json.loads(state_path().read_text())
    except FileNotFoundError:
        return None
    if state.get("instance") != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    return state


def save_state(state):
    path = state_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state))
    temporary.chmod(0o600)
    temporary.replace(path)


def foreground():
    return hypr("activeworkspace", "-j", json_output=True)["name"] == WORKSPACE


def enter(automatic=False, panel=True):
    if (Path(os.environ["XDG_RUNTIME_DIR"]) / "tablet-proof/recovery.json").exists():
        raise RuntimeError("Close/recover the native tablet session before entering the legacy workspace")
    state = load_state()
    previous_state = dict(state) if state else None
    if state and state.get("exit_pending"):
        raise RuntimeError("Pending orientation restore; retry Back to laptop or tablet-workspace leave first")
    current = hypr("activeworkspace", "-j", json_output=True)
    if current["name"] == WORKSPACE:
        if not state:
            raise RuntimeError("Already in tablet-trial without a saved return workspace")
    else:
        # Remember the workspace being left on every explicit entry, including
        # after the user has manually switched away from an earlier trial.
        if not state and any(w["name"] == WORKSPACE for w in hypr("workspaces", "-j", json_output=True)):
            raise RuntimeError("Workspace tablet-trial already exists; refusing to claim it")
        state = {"instance": os.environ["HYPRLAND_INSTANCE_SIGNATURE"], "return": current["name"]}
        save_state(state)
        try:
            dispatch("workspace", "name:" + WORKSPACE)
        except Exception:
            if previous_state:
                save_state(previous_state)
            else:
                state_path().unlink(missing_ok=True)
            raise
    state["enabled"] = True
    state["automatic"] = automatic
    save_state(state)
    # The singleton daemon claims the sensor only in the foreground workspace.
    log_path = state_path().with_name("tablet-orientation.log")
    with log_path.open("a") as output:
        subprocess.Popen(["tablet-orientation", "daemon"], stdout=output,
                         stderr=subprocess.STDOUT, start_new_session=True)
    if not panel:
        return
    # No user-manager environment imports, no compositor restarts. The panel
    # stays hidden while disabled; --no-duplicate handles rapid repeated entry.
    subprocess.Popen([
        "quickshell", "--no-duplicate", "--path",
        os.environ["TABLET_PANEL_QML"],
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def leave(automatic=False):
    state = load_state()
    if not state or not (state.get("enabled") or state.get("exit_pending")):
        raise RuntimeError("No active trial with a saved return workspace")
    names = {w["name"] for w in hypr("workspaces", "-j", json_output=True)}
    if state["return"] not in names and not automatic:
        raise RuntimeError("Return workspace no longer exists; choose a workspace manually")
    # Disable rotation before the synchronous restore while holding the same
    # workspace lock as the daemon. It cannot apply a new sensor reading in
    # between restoration and the return-workspace dispatch.
    state["enabled"] = False
    state["exit_pending"] = True
    save_state(state)
    subprocess.run(["tablet-orientation", "restore"], check=True)
    # Automatic unfolding must not steal focus if the user switched away.
    if not automatic or (state["return"] in names and foreground()):
        dispatch("workspace", "name:" + state["return"])
    # Hide only the tablet keyboard, never close a tablet application.
    subprocess.run(["tablet-osk", "dismiss"], check=True)
    # Keep compositor-scoped ownership while applications remain parked here.
    state["enabled"] = False
    state["exit_pending"] = False
    save_state(state)


def status():
    state = load_state()
    current = hypr("activeworkspace", "-j", json_output=True)
    print(json.dumps({
        "enabled": bool(state and state.get("enabled")),
        "visible": bool(state and (state.get("enabled") or state.get("exit_pending"))) and current["name"] == WORKSPACE,
        "monitor": current.get("monitor", ""),
    }))


def action(command):
    state = load_state()
    if not state or not state.get("enabled") or not foreground():
        raise RuntimeError("Tablet controls are only available inside the active trial workspace")
    if command == "browser":
        # Bypass project-browser: this is an explicitly separate new window,
        # not a project link and not a request to move an existing browser.
        dispatch("exec", "[workspace name:tablet-trial silent] vivaldi --new-window about:blank")
    elif command == "keyboard":
        subprocess.run(["tablet-osk", "toggle"], check=True)
    elif command == "next":
        dispatch("cyclenext")


class FoldWatcher:
    """Consume fold edges, not level-triggered entry that fights manual exits."""

    def __init__(self, enter_mode=None, leave_mode=None, mode_active=None):
        self.folded = None
        self.headless = False
        self.enter_mode = enter_mode or (lambda: enter(automatic=True))
        self.leave_mode = leave_mode or (lambda: leave(automatic=True))
        self.mode_active = mode_active

    def tick(self):
        try:
            headless = Path("/run/headless-mode/state").read_text().strip() != "off"
        except FileNotFoundError:
            headless = False
        if headless:
            if not self.headless:
                subprocess.run(["tablet-osk", "dismiss"], check=True)
                self.headless = True
        else:
            self.headless = False
        # Keyboard safety must not depend on being able to read posture.
        # Unknown posture is not an unfold. Never guess from a failed read.
        value = Path("/sys/devices/platform/thinkpad_acpi/hotkey_tablet_mode").read_text().strip()
        if value not in ("0", "1"):
            raise ValueError("Unknown ThinkPad tablet posture: " + value)
        folded = value == "1"
        if headless:
            # A headless fold must not later hijack the desktop when it wakes.
            self.folded = folded
            return
        state = load_state()
        if not folded:
            if state and (state.get("enabled") or state.get("exit_pending")) and (
                    self.folded is True or state.get("automatic") or state.get("exit_pending")):
                self.leave_mode()
            self.folded = False
        elif self.folded is not True:
            monitors = hypr("monitors", "-j", json_output=True)
            current = hypr("activeworkspace", "-j", json_output=True)
            panel = next((m for m in monitors if m["name"] == "eDP-1"
                          and not m.get("disabled", False) and m.get("dpmsStatus", True)), None)
            if not panel or current.get("monitor") != "eDP-1" or panel.get("specialWorkspace", {}).get("id", 0):
                # Wait for the laptop display/focus to become usable.
                return
            # A retained workspace may have been moved to an external display.
            # Do not focus that output (or move its apps) on a physical fold.
            workspaces = hypr("workspaces", "-j", json_output=True)
            destination = next((w for w in workspaces if w["name"] == WORKSPACE), None)
            if destination and destination.get("monitor") != "eDP-1":
                return
            if (not state or not state.get("enabled") or current.get("name") != WORKSPACE
                    or (self.mode_active is not None and not self.mode_active())):
                self.enter_mode()
            self.folded = True


def watch():
    # Separate singleton lock; never hold the action/restore lock while idle.
    with state_path().with_name("tablet-fold-watch.lock").open("w") as singleton:
        try:
            fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        watcher = FoldWatcher()
        last_error = None
        while True:
            try:
                with state_path().with_suffix(".lock").open("w") as handle:
                    fcntl.flock(handle, fcntl.LOCK_EX)
                    watcher.tick()
                last_error = None
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                if str(error) != last_error:
                    print(f"tablet-workspace watch: {error}", file=sys.stderr, flush=True)
                    last_error = str(error)
                time.sleep(4.5)
            time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["enter", "leave", "toggle", "status", "browser", "keyboard", "next", "watch", "leave-automatic", "enter-iteration", "enter-fold", "adopt-fold"])
    args = parser.parse_args()
    try:
        if args.command == "watch":
            watch()
            return 0
        # Serialize return-state updates and double taps from the touch panel.
        lock = state_path().with_suffix(".lock")
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if args.command == "status":
                status()
            elif args.command == "enter":
                enter()
            elif args.command in ("enter-iteration", "enter-fold"):
                enter(automatic=args.command == "enter-fold", panel=False)
            elif args.command == "adopt-fold":
                state = load_state()
                if not state or not state.get("enabled") or state.get("exit_pending") or not foreground():
                    raise RuntimeError("Cannot adopt an inactive tablet workspace")
                state["automatic"] = True
                save_state(state)
            elif args.command == "leave":
                leave()
            elif args.command == "leave-automatic":
                leave(automatic=True)
            elif args.command == "toggle":
                state = load_state()
                leave() if state and (state.get("exit_pending") or (state.get("enabled") and foreground())) else enter()
            else:
                action(args.command)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"tablet-workspace: {error}", file=sys.stderr)
        subprocess.run(["notify-send", "Tablet workspace", str(error)], check=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())
