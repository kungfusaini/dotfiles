#!/usr/bin/env python3
"""Session-scoped launcher for the official Playwright CLI, not a workflow policy."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

# Installation belongs to Nix; cross-session destructive controls are not scoped.
UNSCOPED_COMMANDS = {"install", "install-browser", "close-all", "kill-all"}


def validate_args(args):
    if args in ([], ["--help"], ["-h"], ["--version"]):
        return
    if args[0].startswith("-"):
        raise ValueError("Put the command before its options")
    if args[0] in UNSCOPED_COMMANDS:
        raise ValueError("Use Nix for installation and close/delete-data for this browser session")
    for arg in args:
        if arg == "--":
            break  # Upstream treats the rest as literal positional data.
        if arg.startswith("-"):
            try:
                float(arg)
                continue
            except ValueError:
                pass
            # Upstream accepts packed short aliases, including -sNAME and -hsNAME.
            if ((not arg.startswith("--") and arg != "-h")
                    or arg.split("=", 1)[0] in {"--session", "--s", "--no-session", "--no-s"}):
                raise ValueError("Session selection is supplied by Pi; use long option names")


def absolute_inputs(args, cwd):
    """Config/profile paths belong to the caller, not the private daemon cwd."""
    result = list(args)
    for index, arg in enumerate(result):
        if arg == "--":
            break
        if arg in ("--config", "--profile") and index + 1 < len(result):
            if not result[index + 1]:
                raise ValueError(f"{arg} requires a non-empty path")
            if not result[index + 1].startswith("-"):
                result[index + 1] = str((cwd / result[index + 1]).resolve())
        elif arg.startswith(("--config=", "--profile=")):
            name, value = arg.split("=", 1)
            if not value:
                raise ValueError(f"{name} requires a non-empty path")
            result[index] = name + "=" + str((cwd / value).resolve())
    return result


def has_option(args, option):
    options = args[:args.index("--")] if "--" in args else args
    return any(arg == option or arg.startswith(option + "=") for arg in options)


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
    # Explicit CLI/config arguments select modes; inherited MCP connection settings
    # must not silently attach to an unrelated browser. Keep display/exec-rule env
    # so headed launches can use the verified project workspace launcher.
    result = {k: v for k, v in env.items()
              if not k.startswith(("PLAYWRIGHT_", "PWTEST_"))}
    result.update({
        "NO_UPDATE_NOTIFIER": "1",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(runtime_root(root)),
    })
    return result


def run(args, *, cli, chromium):
    validate_args(args)
    args = absolute_inputs(args, Path.cwd())
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
        out, temp = tempfile.mkstemp(prefix="config-", suffix=".new", dir=root)
        with os.fdopen(out, "w") as stream:
            json.dump({
                # Leave isolated unset: upstream derives it from --persistent,
                # --profile and attachment mode instead of overriding those modes.
                "browser": {"browserName": "chromium",
                            "launchOptions": {"executablePath": chromium, "headless": True,
                                              "chromiumSandbox": True}},
                "outputDir": str(root / "artifacts"),
                "timeouts": {"action": 5000, "navigation": 45000},
            }, stream)
        os.replace(temp, config)
        command = [cli, "-s=agent"]
        if args and args[0] in ("open", "attach"):
            if not has_option(args, "--config"):
                command += [f"--config={config}"]
            # Headless sessions keep upstream's idle timeout; headed/attached
            # sessions are not forcibly ended while a human is logging in.
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
