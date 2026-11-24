#!/usr/bin/env python3
"""Launch-triggered stable-release notification; never installs or runs releases."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

RELEASE_URL = "https://git.magicbean.dev/api/v1/repos/MagicBeanDev/Longshot/releases/latest"
INTERVAL = 24 * 60 * 60


def version(tag):
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        raise ValueError("Not a stable release version")
    return tuple(map(int, match.groups()))


def installed_version(game):
    for line in (game / "longshot_version.txt").read_text().splitlines():
        if line.startswith("version="):
            tag = line.removeprefix("version=")
            version(tag)
            return tag
    raise ValueError("No installed version")


def fetch_release():
    result = subprocess.run(
        # Avoid AAAA lookup stalls on the current desktop's IPv4 network path.
        ["curl", "--ipv4", "--fail", "--silent", "--show-error", "--connect-timeout", "3",
         "--max-time", "8", "--max-filesize", "1048576", RELEASE_URL],
        check=True, capture_output=True, text=True, timeout=10,
    )
    release = json.loads(result.stdout)
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Not a published stable release")
    tag = release["tag_name"]
    version(tag)
    return tag


def notify(tag):
    subprocess.run(
        ["notify-send", "--app-name=Longshot", "--icon=system-software-update",
         "Longshot update available", f"{tag} is available. Open Longshot Launcher to update after saving and quitting."],
        check=True, timeout=5,
    )


def check(game, state_dir, *, now=None, fetch=fetch_release, send=notify):
    installed = installed_version(game)
    now = time.time() if now is None else now
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "check.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = state_dir / "state.json"
        try:
            state = json.loads(path.read_text())
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        last = state.get("last_attempt", 0)
        if isinstance(last, (int, float)) and 0 <= now - last < INTERVAL:
            return
        # Count even offline attempts: game launches must not cause repeated requests.
        state["last_attempt"] = now
        try:
            tag = fetch()
            available = version(tag)
            state["last_available"] = tag
            history = state.get("notified_versions", [])
            notified = {item for item in history if isinstance(item, str)} if isinstance(history, list) else set()
            previous = state.get("last_notified")
            if isinstance(previous, str):
                notified.add(previous)
            if available > version(installed) and tag not in notified:
                send(tag)
                state["last_notified"] = tag
                state["notified_versions"] = sorted(notified | {tag})
        finally:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state) + "\n")
            temporary.chmod(0o600)
            temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path)
    args = parser.parse_args()
    state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    try:
        check(args.game, state_home / "longshot-update-check")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # No failure notification: offline/unavailable checks must not interrupt play.
        print(f"Longshot update check skipped: {error}")


if __name__ == "__main__":
    main()
