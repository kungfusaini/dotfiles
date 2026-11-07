#!/usr/bin/env python3
"""Pegasus Steam launcher: independent game-exit monitoring and safe cleanup."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import steamctl as steam

UNIT = "pegasus-steam-session"
STATE = steam.STATE_DIR / "session.json"
SCRIPT = Path(__file__).resolve()
ENV_KEYS = ("PATH", "HOME", "USER", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
            "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE",
            "XDG_SESSION_TYPE")


def status(appid, phase, detail=""):
    steam.STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(appid=appid, phase=phase, detail=detail,
                                         updated=time.time())) + "\n")
    temporary.replace(STATE)
    print(f"steam-session: {appid}: {phase}" + (f": {detail}" if detail else ""), flush=True)


def notify(message):
    executable = shutil.which("notify-send")
    if executable:
        try:
            subprocess.run([executable, "--app-name=Steam session", "Steam needs attention", message],
                           check=False, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"steam-session: notification failed: {exc}", file=sys.stderr)


def parent_pid(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        return int(text[text.rfind(")") + 2:].split()[1])
    except (OSError, ValueError, IndexError):
        return 1


def invoking_workspace():
    """Capture the invoking Pegasus/terminal workspace, never the active one."""
    result = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                            text=True, check=True, timeout=5)
    clients = json.loads(result.stdout)
    pid, seen = os.getpid(), set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        names = {c.get("workspace", {}).get("name") for c in clients if c.get("pid") == pid}
        names.discard(None)
        if len(names) == 1:
            name = next(iter(names))
            break
        if names:
            raise steam.SteamError("Invoking process owns windows on multiple workspaces.")
        pid = parent_pid(pid)
    else:
        name = os.environ.get("PROJECT_OBJECT_WORKSPACE_NAME", "")
    if not name or any(c in name for c in ";[],\r\n\0"):
        raise steam.SteamError("Cannot safely identify the invoking workspace; nothing launched.")
    return name


def dispatch(appid):
    workspace = invoking_workspace()
    args = ["systemd-run", "--user", f"--unit={UNIT}", "--collect", "--wait",
            "--property=Type=exec"]
    for key in ENV_KEYS:
        if key in os.environ:
            args.append(f"--setenv={key}={os.environ[key]}")
    args.append(f"--setenv=PROJECT_OBJECT_WORKSPACE_NAME={workspace}")
    # No --pipe: closing Pegasus/the invoking terminal must not break the worker's
    # stdout or kill monitoring. Worker output and failures remain in the journal.
    args.extend([sys.executable, str(SCRIPT), "--worker", str(appid)])
    result = subprocess.run(args, check=False)
    if result.returncode:
        print(f"steam-session: inspect journalctl --user -u {UNIT}", file=sys.stderr)
    return result.returncode


def cleanup(appid, timeout=86400):
    started = time.monotonic()
    deadline = started + timeout
    warned = False
    while time.monotonic() < deadline:
        if not steam.steam_running():
            steam.stop_hide_watch()
            return
        blockers = steam.shutdown_blockers()
        if any(blockers.values()):
            status(appid, "waiting-for-activity", json.dumps(blockers, sort_keys=True))
            if not warned and time.monotonic() - started >= 300:
                notify("Steam is still open for protected game/download/cloud activity. "
                       "See journalctl --user -u " + UNIT + "; no force-close will be used.")
                warned = True
            time.sleep(5)
            continue
        status(appid, "settling")
        try:
            steam.settle(20, 60)
        except steam.SteamError:
            continue
        try:
            steam.stop_steam(90, force=False, approved=False, override_active=False)
        except steam.SteamError:
            if any(steam.shutdown_blockers().values()):
                continue
            raise
        if steam.steam_running():
            raise steam.SteamError("Steam is still running after graceful shutdown.")
        return
    raise steam.SteamError("Steam still has protected activity after 24 hours; no force-kill attempted.")


def worker(appid):
    # Preflight before acquiring cleanup ownership: invalid/duplicate launches
    # must not shut down a client's existing legitimate game session.
    game = next((g for g in steam.manifests() if g["appid"] == appid), None)
    if not game or not game["state_flags"] & steam.FULLY_INSTALLED:
        raise steam.SteamError("Game is not installed; this launcher never installs games.")
    steam.STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (steam.STATE_DIR / "session.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise steam.SteamError("A Steam session already owns launch/cleanup monitoring.")
        if appid in steam.running_game_appids():
            raise steam.SteamError("This game is already running; existing gameplay was left alone.")
        error = None
        reported_error = None
        try:
            status(appid, "starting")
            steam.start_steam(120)
            steam.wait_steam_ready(120)
            steam.request_url(f"steam://rungameid/{appid}", approved=True)
            status(appid, "waiting-for-game")
            steam.wait_game(appid, 86400, startup_timeout=180)
            status(appid, "game-exited")
        except Exception as exc:
            error = str(exc)
            # Report failed startup/placement immediately: protected work may
            # make cleanup wait, and the user must not be left guessing why.
            notify(error)
            reported_error = error
        finally:
            try:
                cleanup(appid)
            except Exception as exc:
                error = (error + "; " if error else "") + str(exc)
            status(appid, "needs-attention" if error else "finished-steam-closed", error or "")
            if error and error != reported_error:
                notify(error)
        return 1 if error else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("appid", type=int)
    args = parser.parse_args()
    if args.appid <= 0:
        parser.error("App ID must be positive")
    try:
        return worker(args.appid) if args.worker else dispatch(args.appid)
    except (steam.SteamError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"steam-session: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
