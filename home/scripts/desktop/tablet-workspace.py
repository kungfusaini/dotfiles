#!/usr/bin/env python3
"""Explicit, reversible workspace trial; never move or close existing clients."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

WORKSPACE = "tablet-trial"


def hypr(*args, json_output=False):
    result = subprocess.run(["hyprctl", *args], check=True, capture_output=True, text=True)
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


def enter():
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
    save_state(state)
    # Start only on explicit entry, never from login or a fold event. The
    # singleton daemon does not claim the sensor outside the foreground trial.
    log_path = state_path().with_name("tablet-orientation.log")
    with log_path.open("a") as output:
        subprocess.Popen(["tablet-orientation", "daemon"], stdout=output,
                         stderr=subprocess.STDOUT, start_new_session=True)
    # No user-manager environment imports, no compositor restarts. The panel
    # stays hidden while disabled; --no-duplicate handles rapid repeated entry.
    subprocess.Popen([
        "quickshell", "--no-duplicate", "--path",
        os.environ["TABLET_PANEL_QML"],
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def leave():
    state = load_state()
    if not state or not (state.get("enabled") or state.get("exit_pending")):
        raise RuntimeError("No active trial with a saved return workspace")
    names = {w["name"] for w in hypr("workspaces", "-j", json_output=True)}
    if state["return"] not in names:
        raise RuntimeError("Return workspace no longer exists; choose a workspace manually")
    # Disable rotation before the synchronous restore while holding the same
    # workspace lock as the daemon. It cannot apply a new sensor reading in
    # between restoration and the return-workspace dispatch.
    state["enabled"] = False
    state["exit_pending"] = True
    save_state(state)
    subprocess.run(["tablet-orientation", "restore"], check=True)
    dispatch("workspace", "name:" + state["return"])
    # Hide only the trial keyboard, never close a tablet application. A folded
    # laptop remains manually hidden until the existing OSK policy resets it.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["enter", "leave", "toggle", "status", "browser", "keyboard", "next"])
    args = parser.parse_args()
    try:
        # Serialize return-state updates and double taps from the touch panel.
        lock = state_path().with_suffix(".lock")
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if args.command == "status":
                status()
            elif args.command == "enter":
                enter()
            elif args.command == "leave":
                leave()
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
