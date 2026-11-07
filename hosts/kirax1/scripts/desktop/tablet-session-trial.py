#!/usr/bin/env python3
"""Explicit, reversible second-user Plasma Mobile feasibility trial. No freezing."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import time

USER = "tablet-trial"
LAPTOP_USER = "sumeet"
UNIT = "tablet-session-trial.service"
STATE = Path("/run/tablet-session-trial-control/source.json")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90, **kwargs).stdout.strip()


def properties(kind, name):
    text = run("loginctl", "show-" + kind, name, "--no-pager")
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def active():
    return properties("seat", "seat0").get("ActiveSession", "")


def trial_session():
    user = properties("user", USER)
    for session in user.get("Sessions", "").split():
        value = properties("session", session)
        if (value.get("Name") == USER and value.get("Seat") == "seat0"
                and value.get("VTNr") == "8" and value.get("Class") == "user"):
            return session
    return ""


def save_source():
    session = active()
    value = properties("session", session)
    if value.get("Name") != LAPTOP_USER or value.get("Type") != "wayland" or value.get("Seat") != "seat0":
        raise RuntimeError("Start this trial only from the active laptop Wayland session")
    if value.get("LockedHint") == "yes":
        raise RuntimeError("Unlock the laptop normally before starting the trial")
    # Never overwrite a record with an arbitrary caller-controlled session ID.
    STATE.parent.mkdir(mode=0o700, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=STATE.parent, prefix="source-", delete=False) as output:
            temporary = Path(output.name)
            json.dump({"session": session, "user": LAPTOP_USER, "vt": value["VTNr"]}, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(STATE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def return_to_laptop():
    if not STATE.exists():
        return
    source = json.loads(STATE.read_text())
    value = properties("session", source["session"])
    if (value.get("Name") != LAPTOP_USER or value.get("Seat") != "seat0"
            or value.get("VTNr") != source["vt"]):
        raise RuntimeError("Saved laptop session is no longer valid; not guessing a destination")
    current = active()
    if current == source["session"]:
        return
    # A failed startup may leave tty8 active without a registered user session.
    vt = Path("/sys/class/tty/tty0/active").read_text().strip()
    current_user = properties("session", current).get("Name") if current else ""
    if vt != "tty8" or (current_user and current_user != USER):
        raise RuntimeError("Trial is not foreground; refusing to steal another session's focus")
    run("loginctl", "activate", source["session"])


def check_vt():
    for unit in ("getty@tty8.service", "autovt@tty8.service"):
        text = run("systemctl", "show", unit, "--property=LoadState", "--property=ActiveState")
        state = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        if (state.get("LoadState") not in ("loaded", "not-found")
                or state.get("ActiveState") not in ("inactive", "failed")):
            raise RuntimeError("tty8 has a busy or unqueryable getty; refusing to stop or replace it")
    sessions = run("loginctl", "list-sessions", "--no-legend").splitlines()
    for line in sessions:
        value = properties("session", line.split()[0])
        if value.get("VTNr") == "8":
            raise RuntimeError("tty8 already belongs to a session; refusing to replace it")
    if Path("/sys/class/tty/tty0/active").read_text().strip() == "tty8":
        raise RuntimeError("tty8 is already active; refusing to claim it")
    if not STATE.exists():
        raise RuntimeError("Use tablet-session-trial enter; no saved laptop session")


class HomeRenderFailure(RuntimeError):
    pass


def trial_bus(uid, destination, path, method, *arguments):
    return run("runuser", "-u", USER, "--", "env",
               f"XDG_RUNTIME_DIR=/run/user/{uid}",
               f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
               "gdbus", "call", "--session", "--dest", destination,
               "--object-path", path, "--method", method, *arguments)


def verify_mobile_home(uid):
    count = trial_bus(uid, "org.kde.plasmashell", "/PlasmaShell",
                      "org.kde.PlasmaShell.evaluateScript", "print(desktops().length)")
    if not re.fullmatch(r"\('([1-9][0-9]*)',\)", count):
        raise RuntimeError("Waiting for a mobile desktop containment")
    value = trial_bus(uid, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                      "org.freedesktop.DBus.GetConnectionUnixProcessID", "org.kde.plasmashell")
    match = re.fullmatch(r"\(uint32 ([0-9]+),\)", value)
    if not match:
        raise RuntimeError("Cannot identify the trial shell for readiness checking")
    # Qt routes its errors to journald by default, not its parent's stdout.
    # A bus owner/desktop count can coexist with a completely failed QML root.
    time.sleep(2)
    log = run("journalctl", "-b", "--since=-2min", "--no-pager", "--output=cat",
              f"_UID={uid}", f"_PID={match[1]}")
    if re.search(r"Error loading QML file|QQmlComponent: Component is not ready|module .* is not installed|error when loading applet", log):
        raise HomeRenderFailure("Mobile Home failed to load its QML; see the trial shell journal")


def ready():
    uid = pwd.getpwnam(USER).pw_uid
    deadline = time.monotonic() + 60
    last_error = "No registered tablet session"
    while time.monotonic() < deadline:
        try:
            session = trial_session()
            if session:
                for name in ("org.kde.KWin", "org.kde.plasmashell"):
                    result = trial_bus(uid, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                                       "org.freedesktop.DBus.NameHasOwner", name)
                    if result != "(true,)":
                        raise RuntimeError("Waiting for " + name)
                verify_mobile_home(uid)
                return {"session": session, "shell": "Plasma Mobile", "ready": True}
        except HomeRenderFailure:
            raise
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            last_error = str(error)
        time.sleep(.5)
    raise RuntimeError("Tablet session did not become ready: " + last_error)


def enter():
    save_source()
    started = time.monotonic()
    state = subprocess.run(["systemctl", "is-active", UNIT], capture_output=True, text=True, timeout=5)
    if state.returncode == 0 and state.stdout.strip() == "active":
        session = trial_session()
        if not session:
            raise RuntimeError("Trial service is active without its registered session")
        run("loginctl", "activate", session)
        return {"session": session, "cold": False, "activationAckSeconds": time.monotonic() - started}
    check_vt()  # Before the start transaction, not only inside ExecStartPre.
    run("systemctl", "start", UNIT)
    return {"session": trial_session(), "cold": True, "serviceReadySeconds": time.monotonic() - started}


def stop_trial():
    # A stale return destination must not strand a battery-consuming session.
    # Preserve focus safety, but attempt both cleanup operations independently.
    errors = []
    actions = [
        ("return", return_to_laptop),
        ("service stop", lambda: run("systemctl", "stop", UNIT)),
        ("trial user termination", lambda: run("loginctl", "terminate-user", USER)),
    ]
    for name, action in actions:
        try:
            action()
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(name + ": " + str(error))
    if errors:
        raise RuntimeError("Trial cleanup attempted; " + "; ".join(errors))
    return {"stopped": True}


def status():
    try:
        session = trial_session()
    except subprocess.CalledProcessError:
        session = ""
    return {"trialSession": session, "activeSession": active(), "freezing": False}


def sample(seconds):
    """Read-only measurements; no claim that CPU accounting equals battery use."""
    paths = {}
    for name in (LAPTOP_USER, USER):
        try:
            uid = pwd.getpwnam(name).pw_uid
            paths[name] = Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice")
        except KeyError:
            pass
    def read():
        result = {"monotonic": time.monotonic(), "cpuUsec": {}, "memoryBytes": {}}
        for name, path in paths.items():
            try:
                stats = dict(line.split() for line in (path / "cpu.stat").read_text().splitlines())
                result["cpuUsec"][name] = int(stats["usage_usec"])
                result["memoryBytes"][name] = int((path / "memory.current").read_text())
            except FileNotFoundError:
                pass
        battery = Path("/sys/class/power_supply/BAT0")
        for name in ("status", "energy_now", "power_now"):
            try:
                result[name] = (battery / name).read_text().strip()
            except FileNotFoundError:
                pass
        result["activeSession"] = active()
        return result
    first = read()
    time.sleep(seconds)
    last = read()
    duration = last["monotonic"] - first["monotonic"]
    return {"first": first, "last": last, "durationSeconds": duration,
            "cpuCorePercent": {name: (value - first["cpuUsec"][name]) / (duration * 10000)
                               for name, value in last["cpuUsec"].items() if name in first["cpuUsec"]},
            "batteryDataUsable": first.get("status") == last.get("status") == "Discharging"
                                      and first["activeSession"] == last["activeSession"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["enter", "return", "stop", "status", "check-vt", "ready", "measure"])
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if args.command == "measure":
        if not 1 <= args.seconds <= 3600:
            parser.error("--seconds must be between 1 and 3600")
        print(json.dumps(sample(args.seconds)))
        return
    if args.command == "status":
        print(json.dumps(status()))
        return
    if os.geteuid() != 0:
        os.execv("/run/wrappers/bin/sudo", ["sudo", "--", "/run/current-system/sw/bin/tablet-session-trial", *sys.argv[1:]])
    if os.environ.get("SUDO_USER", "root") not in (LAPTOP_USER, "root"):
        raise RuntimeError("Only the laptop owner may control trial lifecycle")
    # Startup/stop callbacks execute during systemctl start/stop, so they must
    # not contend on the interactive controller's lock.
    if args.command in ("check-vt", "ready", "return"):
        result = {"check-vt": check_vt, "ready": ready, "return": return_to_laptop}[args.command]()
    else:
        STATE.parent.mkdir(mode=0o700, exist_ok=True)
        with STATE.with_name("action.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == "enter":
                result = enter()
            else:
                result = stop_trial()
    if result is not None:
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
