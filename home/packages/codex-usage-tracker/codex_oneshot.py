#!/usr/bin/env python3
"""Launch one ordinary Pi session, owned by an absolute reset deadline."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from codex_usage import fetch_quota

PREFIX = "pi-oneshot-"
ENV_NAMES = (
    "PATH", "TERM", "COLORTERM", "LANG", "LC_ALL", "DISPLAY", "WAYLAND_DISPLAY",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE",
    "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR",
    "PROJECT_OBJECT_ID", "PROJECT_OBJECT_NAME", "PROJECT_OBJECT_HOME",
    "PROJECT_OBJECT_MAIN_DIRECTORY", "PROJECT_OBJECT_STREAM_ID",
    "PROJECT_OBJECT_STREAM_NAME", "PROJECT_OBJECT_STREAM_HOME",
    "PROJECT_OBJECT_WORKSPACE_NAME",
)


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "command-center/oneshot.json"


def fresh_quota():
    quota, status = fetch_quota()
    if status != "ok" or quota is None:
        raise ValueError("Cannot confirm current Codex allowance (" + status + "); not starting.")
    account, _plan, reset, _duration, used, allowed, reached = quota
    if reset <= time.time() + 5:
        raise ValueError("This allowance window has ended or is too close to launch safely.")
    if not allowed or reached or used >= 100:
        raise ValueError("Codex currently reports a usage restriction; not starting.")
    return account, reset, used


def unit_names(session):
    unit = PREFIX + session + ".service"
    return unit, PREFIX + session + "-cutoff"


def timer_command(session, reset):
    unit, cutoff = unit_names(session)
    return [
        "systemd-run", "--user", "--collect", "--unit=" + cutoff,
        "--on-calendar=@" + str(reset), "--timer-property=AccuracySec=1us",
        "--timer-property=RandomizedDelaySec=0", "--timer-property=WakeSystem=false",
        "--timer-property=RemainAfterElapse=false",
        "--property=Type=exec", "--property=UMask=0077",
        "--", "systemctl", "--user", "kill", "--kill-whom=all", "--signal=SIGKILL", unit,
    ]


def session_command(session, account, reset, cwd):
    unit, _cutoff = unit_names(session)
    command = [
        "systemd-run", "--user", "--collect", "--pty", "--wait",
        "--service-type=exec", "--unit=" + unit, "--working-directory=" + str(cwd),
        "--property=KillMode=control-group", "--property=TimeoutStopSec=2s",
        "--property=Restart=no", "--property=UMask=0077",
        # A second, monotonic bound if the calendar timer is disrupted. The
        # absolute timer remains authoritative, including across suspend.
        "--property=RuntimeMaxSec=" + str(max(1, reset - time.time())),
    ]
    for name in ENV_NAMES:
        if name in os.environ:
            command.append("--setenv=" + name + "=" + os.environ[name])
    command += ["--", sys.executable, "-B", str(Path(__file__).resolve()), "_exec",
                "--session", session, "--account", account, "--reset", str(reset)]
    return command


def cleanup(session):
    unit, cutoff = unit_names(session)
    # Stop the session FIRST. Removing its deadline while it is still alive is unsafe.
    stopped = subprocess.run(["systemctl", "--user", "stop", unit], check=False,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    if stopped.returncode:
        loaded = subprocess.run(["systemctl", "--user", "show", "--property=LoadState", "--value", unit],
                                check=False, capture_output=True, text=True, timeout=10)
        if loaded.returncode or loaded.stdout.strip() != "not-found":
            raise ValueError("Cannot confirm session stopped; retained its deadline timer.")
    subprocess.run(["systemctl", "--user", "stop", cutoff + ".timer", cutoff + ".service"],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)


def launch():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("Run pi-oneshot in an interactive project terminal.")
    account, reset, used = fresh_quota()
    session = uuid.uuid4().hex
    deadline = dt.datetime.fromtimestamp(reset, dt.timezone.utc).isoformat()
    print(f"Codex: {100-used:g}% left. This Pi session will be killed at {deadline}.", flush=True)
    print(f"Session: {session}. Enter your big prompt in Pi; normal approval rules still apply.", flush=True)
    # Arm independently BEFORE Pi can start. This timer survives a launcher crash.
    subprocess.run(timer_command(session, reset), check=True, timeout=20)
    try:
        return subprocess.run(session_command(session, account, reset, Path.cwd()), check=False).returncode
    finally:
        cleanup(session)


def execute(args):
    unit, cutoff = unit_names(args.session)
    subprocess.run(["systemctl", "--user", "is-active", "--quiet", cutoff + ".timer"],
                   check=True, timeout=10)
    account, reset, _used = fresh_quota()
    # One-second reset jitter is observed upstream; never extend the pinned deadline.
    if account != args.account or abs(reset - args.reset) > 2 or time.time() >= args.reset:
        raise ValueError("Account/window changed or deadline passed; not starting Pi.")
    config = json.loads(config_path().read_text())
    pi = config["piBin"]
    if not isinstance(pi, str) or not pi.startswith("/nix/store/"):
        raise ValueError("Expected the managed Pi executable.")
    model, thinking = config["model"], config["thinking"]
    if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
        raise ValueError("Expected an exact managed Codex model ID.")
    if thinking not in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("Invalid managed thinking level.")
    instructions = (
        "This is a dedicated pre-reset one-shot session. Its process group will be forcibly "
        "terminated at the allowance reset timestamp. Preserve useful progress as you work. "
        "Normal authorization rules still apply. Do not launch work via separate systemd units, "
        "Project Object workers, external/cloud agents, or other mechanisms outside this session's "
        "owned process tree. Do not change provider/account or use paid-credit/API fallbacks. "
        "Do not schedule automatic continuation or restart after reset."
    )
    os.execv(pi, [pi, "--provider", "openai-codex", "--model", model,
                 "--thinking", thinking, "--session-id", args.session,
                 "--name", "One-shot · stops at reset", "--append-system-prompt", instructions])


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("start", help="Open a dedicated Pi session in this terminal (default)")
    sub.add_parser("status", help="Show active one-shot sessions and deadline timers")
    stop = sub.add_parser("stop", help="Stop one owned session early")
    stop.add_argument("session", help="Exact session ID printed at launch")
    internal = sub.add_parser("_exec", help=argparse.SUPPRESS)
    internal.add_argument("--session", required=True)
    internal.add_argument("--account", required=True)
    internal.add_argument("--reset", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.command == "status":
            return subprocess.run(["systemctl", "--user", "list-units", "--all",
                                   "--no-pager", PREFIX + "*"], check=False).returncode
        if args.command in ("stop", "_exec") and not re.fullmatch(r"[a-f0-9]{32}", args.session):
            raise ValueError("Expected an exact one-shot session ID.")
        if args.command == "stop":
            cleanup(args.session)
            return 0
        if args.command == "_exec":
            execute(args)
            return 0
        return launch()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        # Never print subprocess command lines or configuration/auth payloads.
        print("pi-oneshot: " + (str(exc) if isinstance(exc, ValueError) else
                               "launch/control failed; inspect systemctl --user status pi-oneshot-*"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
