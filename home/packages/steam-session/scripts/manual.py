#!/usr/bin/env python3
"""Explicit human takeover of Steam UI; no game, download or save mutations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

import session
import steamctl as steam


def hypr(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True,
                            check=False, timeout=5)
    if result.returncode:
        raise steam.SteamError("Could not control Steam visibility: " + result.stderr.strip())
    return result.stdout.strip()


def workspace(desktop=False):
    # Agent/terminal invocations must resolve their own workspace. Only a human
    # desktop-entry launch (which has no terminal ancestor) uses the current one.
    explicit = (os.environ.get("PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME")
                or os.environ.get("PROJECT_OBJECT_WORKSPACE_NAME"))
    if explicit:
        name = explicit
    elif desktop:
        name = json.loads(hypr("activeworkspace", "-j"))["name"]
    else:
        name = session.invoking_workspace()
    if not isinstance(name, str) or not name or any(c in name for c in ";[],\r\n\0"):
        raise steam.SteamError("Cannot safely identify the manual Steam workspace.")
    return name


def owns_window(window):
    pid = window.get("pid")
    seen = set()
    mains = set(steam.steam_main_pids())
    while isinstance(pid, int) and pid > 1 and pid not in seen:
        if pid in mains:
            return True
        seen.add(pid)
        pid = session.parent_pid(pid)
    return False


def place_windows(target, routed=None):
    placed = []
    for window in steam.steam_windows():
        address = window.get("address", "")
        if (not window.get("mapped") or not isinstance(address, str)
                or not re.fullmatch(r"0x[0-9a-fA-F]+", address) or not owns_window(window)):
            continue
        if routed is not None and address in routed:
            continue  # Never undo a human moving an already-routed window.
        if window.get("workspace", {}).get("name") != target:
            if hypr("dispatch", "movetoworkspacesilent", f"name:{target},address:{address}") != "ok":
                raise steam.SteamError("Could not place the manual Steam window.")
        placed.append(address)
    # Re-read exact addresses and their live identity, never infer success from
    # a dispatch acknowledgement or an unrelated window on the target workspace.
    verified = {w.get("address") for w in steam.steam_windows()
                if w.get("address") in placed and w.get("mapped") and owns_window(w)
                and w.get("workspace", {}).get("name") == target}
    if routed is not None:
        routed.update(verified)
    return bool(verified)


def open_manual(target, arguments):
    executable = shutil.which("steam")
    if not executable:
        raise steam.SteamError("The official Steam client is not installed.")
    with steam.visibility_lock():
        # Protect startup as well as a pre-existing automated client. A failed
        # opener cannot leave an opt-out that affects future client lifetimes.
        steam.record_manual_session([os.getpid(), *steam.steam_main_pids()])
        if hypr("keyword", "windowrule[project-object-steam-hidden]:enable", "0") != "ok":
            raise steam.SteamError("Could not release the automated Steam window rule.")
    steam.stop_hide_watch()
    routed = set()
    confirmed = place_windows(target, routed)
    # Route new UI before it maps, including a fresh client's updater. A running
    # Steam instance receives the normal URI; its exact windows are placed above
    # and revalidated below. No global input or special-workspace toggle is used.
    command = [executable, *(arguments or ["steam://open/main"])]
    if hypr("dispatch", "exec", f"[workspace name:{target} silent] {shlex.join(command)}") != "ok":
        raise steam.SteamError("Could not request the manual Steam window.")
    deadline = time.monotonic() + 60
    last_new_at = time.monotonic()
    while time.monotonic() < deadline:
        pids = steam.steam_main_pids()
        if pids:
            with steam.visibility_lock():
                steam.record_manual_session([os.getpid(), *pids])
        # Existing main UI is not proof that a Settings/Friends URI has already
        # mapped its delayed secondary window. Route new UI until 15 quiet
        # seconds, without fighting human moves of windows already placed.
        before = len(routed)
        confirmed = place_windows(target, routed) or confirmed
        if len(routed) != before:
            last_new_at = time.monotonic()
        if confirmed and (not pids or time.monotonic() - last_new_at >= 15):
            with steam.visibility_lock():
                steam.record_manual_session(pids)
            return
        time.sleep(0.2)
    raise steam.SteamError("Steam UI did not appear on the requested workspace; existing work was not stopped.")


def main():
    arguments = sys.argv[1:]
    desktop = arguments[:1] == ["--desktop"]
    if desktop:
        arguments = arguments[1:]
    # Preserve normal explicit client-control commands from an interactive shell.
    if arguments[:1] in (["-shutdown"], ["-silent"]):
        executable = shutil.which("steam")
        if not executable:
            raise steam.SteamError("The official Steam client is not installed.")
        os.execv(executable, [executable, *arguments])
    open_manual(workspace(desktop), arguments)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (steam.SteamError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"steam-manual: {error}", file=sys.stderr)
        raise SystemExit(1)
