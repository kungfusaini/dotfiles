#!/usr/bin/env python3
"""Session-scoped headless launcher for the official Playwright CLI, not a sandbox."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

COMMANDS = set("""
open close goto type click dblclick fill drag drop hover select upload check uncheck
snapshot find eval dialog-accept dialog-dismiss resize go-back go-forward reload
press keydown keyup mousemove mousedown mouseup mousewheel screenshot pdf
 tab-list tab-new tab-close tab-select state-load state-save
cookie-list cookie-get cookie-set cookie-delete cookie-clear
localstorage-list localstorage-get localstorage-set localstorage-delete localstorage-clear
sessionstorage-list sessionstorage-get sessionstorage-set sessionstorage-delete sessionstorage-clear
set-color-scheme set-reduced-motion set-forced-colors set-contrast set-media
clear-color-scheme clear-reduced-motion clear-forced-colors clear-contrast clear-media
requests request request-headers request-body response-headers response-body
route route-list unroute network-state-set console run-code tracing-start tracing-stop
recording-start recording-stop generate-locator highlight
""".split())
# Deliberately no launch, profile, attachment, global-session, installation, or UI flags.
OPTIONS = set("""
json raw help filename depth boxes regex submit full-page hires path data domain
expires httpOnly secure sameSite status body content-type headers remove-header
hide style isolated-context static
""".split())


def validate_args(args):
    if args in ([], ["--help"], ["--version"], ["paths"]):
        return
    # Require command first; don't let upstream's permissive parser accept -s aliases.
    if args[0] not in COMMANDS:
        raise ValueError("Use a supported page command; attach, show, install and global session commands are disabled")
    for arg in args[1:]:
        if arg == "--":
            break  # Upstream treats everything after this as literal positional data.
        if arg.startswith("-"):
            # Negative mouse coordinates and numeric values are ordinary arguments.
            try:
                float(arg)
                continue
            except ValueError:
                pass
            if not arg.startswith("--") or arg[2:].split("=", 1)[0] not in OPTIONS:
                raise ValueError(f"Unsupported option: {arg.split('=', 1)[0]}")


def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise ValueError(f"Directory is not owned by this user: {path}")
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def session_root(env):
    identity = env.get("PI_SESSION_ID") or env.get("PI_SESSION_FILE")
    if not identity:
        raise ValueError("PI_SESSION_ID or PI_SESSION_FILE is required; refusing a shared default browser")
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    base = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "pi-browser"
    private_dir(base)
    root = base / key
    private_dir(root)
    return root


def runtime_root(root):
    # Chromium's SingletonSocket must fit Linux's 108-byte Unix socket limit.
    key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return Path(f"/run/user/{os.getuid()}/pib") / key


def child_env(env, root):
    result = {k: v for k, v in env.items()
              if not k.startswith(("PLAYWRIGHT_", "PWTEST_"))
              and k not in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY")}
    result.update({
        "NO_UPDATE_NOTIFIER": "1",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(runtime_root(root)),
    })
    return result


def run(args, *, cli, chromium):
    validate_args(args)
    os.umask(0o077)
    root = session_root(os.environ)
    for name in (".playwright", "cache", "artifacts"):
        private_dir(root / name)
    runtime = runtime_root(root)
    private_dir(runtime.parent)
    private_dir(runtime)
    if args == ["paths"]:
        print(json.dumps({"session": str(root), "artifacts": str(root / "artifacts"),
                          "temporary": str(runtime)}))
        return 0
    fd = os.open(root / "command.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("Invalid command lock")
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = root / "config.json"
        # Replace atomically, never follow a pre-existing config symlink.
        out, temp = tempfile.mkstemp(prefix="config-", suffix=".new", dir=root)
        with os.fdopen(out, "w") as stream:
            json.dump({
                "browser": {"browserName": "chromium", "isolated": True,
                            "launchOptions": {"executablePath": chromium, "headless": True,
                                              "chromiumSandbox": True}},
                "outputDir": str(root / "artifacts"),
                "timeouts": {"action": 5000, "navigation": 45000},
            }, stream)
        os.replace(temp, config)
        command = [cli, "-s=agent"]
        if args and args[0] == "open":
            command += [f"--config={config}", "--idle-timeout=900000"]
        command += args or ["--help"]
        print(f"pi-browser artifacts: {root / 'artifacts'}", file=sys.stderr, flush=True)
        return subprocess.run(command, cwd=root, env=child_env(os.environ, root), check=False).returncode


def main():
    try:
        return run(sys.argv[1:], cli="@CLI@", chromium="@CHROMIUM@")
    except (OSError, ValueError) as error:
        print(f"pi-browser: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
