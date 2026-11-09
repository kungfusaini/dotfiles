#!/usr/bin/env python3
"""Session-scoped launcher for the official Playwright CLI, not a workflow policy."""

import fcntl
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import socket
import shutil
import select
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

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


def boolean_option(args, name, default=False):
    options = args[:args.index("--")] if "--" in args else args
    result = default
    for index, arg in enumerate(options):
        if arg == "--no-" + name:
            result = False
        elif arg == "--" + name:
            result = not (index + 1 < len(options) and options[index + 1] == "false")
    return result


# Native startup needs the URL before starting the official daemon. These are
# the pinned CLI's open options (not a workflow/capability policy).
OPEN_FLAGS = {"browser": "string", "headed": "boolean", "mobile": "boolean",
              "device": "string", "persistent": "boolean", "profile": "string",
              "config": "string", "idle-timeout": "string", "manual": "boolean", "native-consent": "boolean",
              "json": "boolean", "raw": "boolean", "help": "boolean", "version": "boolean"}


def open_target(args):
    positional = []
    index = 1
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional += args[index + 1:]
            break
        if arg.startswith("--"):
            flag, separator, value = arg[2:].partition("=")
            flag = flag.removeprefix("no-")
            kind = OPEN_FLAGS.get(flag)
            if kind is None:
                raise ValueError(f"Unknown open option: --{flag}")
            if kind == "boolean":
                if separator:
                    raise ValueError(f"Boolean option --{flag} does not accept =value")
                if index + 1 < len(args) and args[index + 1] in ("true", "false"):
                    index += 1
            elif not separator:
                if index + 1 >= len(args) or args[index + 1].startswith("--"):
                    raise ValueError(f"--{flag} requires a value")
                index += 1
        else:
            positional.append(arg)
        index += 1
    if len(positional) > 1:
        raise ValueError("open accepts one URL")
    return positional[0] if positional else "about:blank"


def headed_requested(args):
    return boolean_option(args, "headed")


def option_value(args, name):
    options = args[:args.index("--")] if "--" in args else args
    result = None
    for index, arg in enumerate(options):
        if arg.startswith(name + "="):
            result = arg.split("=", 1)[1]
        elif arg == name and index + 1 < len(options):
            result = options[index + 1]
    return result


def replace_config(args, path):
    result = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            result += args[index:]
            break
        if arg == "--config":
            index += 2
            continue
        if not arg.startswith("--config="):
            result.append(arg)
        index += 1
    return result


def without_manual_option(args):
    result = []
    index = 0
    while index < len(args):
        if args[index] == "--":
            return result + args[index:]
        if args[index] in ("--manual", "--no-manual", "--native-consent", "--no-native-consent"):
            index += 1
            if index < len(args) and args[index] in ("true", "false"):
                index += 1
            continue
        result.append(args[index])
        index += 1
    return result


def launch_options(browser_executable, args):
    options = {"executablePath": browser_executable, "headless": not headed_requested(args),
               "chromiumSandbox": True}
    # Keep the pinned Vivaldi binary/profile/extensions, but use its Chromium
    # interface. Vivaldi's custom UI deadlocks on automated popup creation.
    options["args"] = ["--disable-vivaldi"]
    if not options["headless"]:
        options["args"].append("--force-dark-mode")
    return options


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
    result.pop("PI_BROWSER_METADATA_ONLY", None)
    result.update({
        "NO_UPDATE_NOTIFIER": "1",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        "VIVALDI_FFMPEG_AUTO": "0",
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(runtime_root(root)),
    })
    return result


def process_start(pid):
    try:
        value = Path(f"/proc/{pid}/stat").read_text()
        fields = value[value.rfind(")") + 2:].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def read_state(root):
    try:
        state = json.loads((root / "vivaldi-process.json").read_text())
        if isinstance(state.get("pid"), int) and state["pid"] > 1 and state.get("start"):
            return state
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def managed_state(root):
    state = read_state(root)
    if state and state.get("bound", True) and process_start(state["pid"]) == state["start"]:
        return state
    return None


def write_json(path, data):
    fd, temporary = tempfile.mkstemp(prefix="config-", suffix=".new", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def profile_locked(profile):
    lock = profile / "SingletonLock"
    if not lock.is_symlink() and not lock.exists():
        return False
    try:
        host, pid = os.readlink(lock).rsplit("-", 1)
        return host != os.uname().nodename or process_start(int(pid)) is not None
    except (OSError, ValueError):
        return True


def placement_rule(root, env):
    workspace = env.get("PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME")
    launch_id = env.get("PROJECT_OBJECT_LAUNCH_ID")
    if not workspace and not launch_id:
        return {}
    if (not workspace or any(c in workspace for c in ";[],\r\n\0")
            or not re.fullmatch(r"[a-f0-9]{32}", launch_id or "")):
        raise ValueError("Invalid native Vivaldi workspace launch context")
    rule = "windowrule[pi-browser-" + root.name + "]"
    browser_class = "pi-vivaldi-" + launch_id
    hyprctl = env.get("PROJECT_PICKER_HYPRCTL", "@HYPRCTL@")
    state = {"rule": rule, "hyprctl": hyprctl, "class": browser_class}
    try:
        for key, value in (("enable", "0"), ("match:class", "^" + browser_class + "$"),
                           ("no_initial_focus", "on"), ("suppress_event", "activate activatefocus"),
                           ("workspace", "name:" + workspace + " silent"), ("enable", "1")):
            result = subprocess.run([hyprctl, "keyword", rule + ":" + key, value],
                                    env=env, capture_output=True, text=True, timeout=5, check=False)
            if result.returncode or result.stdout.strip() != "ok":
                raise ValueError("Could not install the native Vivaldi placement rule")
        return state
    except BaseException:
        release_rule(state)
        raise


def release_rule(state):
    if state.get("rule"):
        result = subprocess.run([state["hyprctl"], "keyword", state["rule"] + ":enable", "0"],
                                capture_output=True, text=True, timeout=5, check=False)
        if result.returncode or result.stdout.strip() != "ok":
            print("pi-browser: could not disable its exact-class placement rule", file=sys.stderr)


def remove_temporary_profile(root, state):
    profile = Path(state["profile"])
    if state.get("temporary"):
        if (profile.is_symlink() or profile != profile.resolve()
                or profile.parent != runtime_root(root).resolve() or not profile.name.startswith("headed-")):
            raise ValueError("Refusing unowned temporary-profile deletion")
        if profile_locked(profile):
            raise ValueError("Temporary profile is still locked; refusing deletion")
        if profile.exists():
            shutil.rmtree(profile)


def stop_managed(root):
    state = read_state(root)
    if state and state.get("bound", True):
        stop_runtime_daemon(state)
    if state and state.get("bound", True) and process_start(state["pid"]) == state["start"]:
        # Only the exact process session we launched; never a reused PID or the
        # everyday Vivaldi process. SIGTERM allows profile data to flush.
        closed = False
        if state.get("endpoint"):
            try:
                endpoint = urllib.parse.urlsplit(state["endpoint"])
                if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port:
                    raise ValueError("Invalid managed loopback endpoint")
                if state.get("preauthorized") and (not state.get("websocketPath")
                        or endpoint.username or endpoint.password or endpoint.path or endpoint.query or endpoint.fragment
                        or not loopback_listener_owned(state["pid"], endpoint.port)):
                    raise ValueError("Preauthorized listener is not owned; skip endpoint access")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(state["endpoint"] + "/json/version", timeout=3) as response:
                    websocket = json.load(response)["webSocketDebuggerUrl"]
                address = urllib.parse.urlsplit(websocket)
                expected = urllib.parse.urlsplit(state["endpoint"])
                if (address.scheme != "ws" or address.netloc != expected.netloc
                        or address.path != state.get("websocketPath")):
                    raise ValueError("Managed debugging endpoint identity changed")
                script = """let data='';process.stdin.on('data',b=>data+=b);process.stdin.on('end',()=>{
const ws=new WebSocket(JSON.parse(data)); const timer=setTimeout(()=>process.exit(1),7000);
ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Browser.close'}));
ws.onclose=()=>{clearTimeout(timer);process.exit(0)};ws.onerror=()=>process.exit(1);});"""
                closed = subprocess.run(["@NODE@", "-e", script], input=json.dumps(websocket),
                                        text=True, capture_output=True, timeout=8, check=False).returncode == 0
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                pass
        if not closed and process_start(state["pid"]) == state["start"]:
            os.kill(state["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 10
        while process_start(state["pid"]) == state["start"] and time.monotonic() < deadline:
            # A reaped or zombie child no longer owns a browser/profile.
            try:
                if Path(f"/proc/{state['pid']}/stat").read_text().split(")", 1)[1].split()[0] == "Z":
                    break
            except OSError:
                break
            time.sleep(0.05)
        else:
            if process_start(state["pid"]) == state["start"]:
                raise ValueError("Managed Vivaldi has not exited; refusing to replace it")
    if state and state.get("bound", True):
        remove_temporary_profile(root, state)
        release_rule(state)
    (root / "vivaldi-process.json").unlink(missing_ok=True)


def validate_native_settings(config, args):
    browser = config["browser"]
    launch = browser["launchOptions"]
    if (browser.get("contextOptions") or browser.get("initPage") or browser.get("initScript")
            or option_value(args, "--device") or boolean_option(args, "mobile")
            or option_value(args, "--browser") not in (None, "chromium")):
        raise ValueError("Native Vivaldi does not apply emulation/context/init settings; use headless mode or an external endpoint")
    unsupported = set(launch) - {"executablePath", "headless", "chromiumSandbox", "args"}
    if unsupported or launch.get("chromiumSandbox") is False:
        raise ValueError("Unsupported native Vivaldi launch setting; use explicit browser args or an external endpoint")
    extra = launch.get("args", [])
    if any(arg.startswith(("--user-data-dir", "--remote-debugging", "--no-sandbox", "--class")) for arg in extra):
        raise ValueError("Native Vivaldi owns its profile, sandbox and endpoint; use attach for external endpoints")
    target = open_target(args)
    if not (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target)
            or re.match(r"^(about|data|blob|javascript):", target, re.I)):
        target = ("http://" if target.startswith(("localhost", "127.0.0.1", "0.0.0.0", "[::1]")) else "https://") + target
    if urllib.parse.urlsplit(target).scheme.lower() == "file" and not config.get("allowUnrestrictedFileAccess"):
        raise ValueError("File URLs require allowUnrestrictedFileAccess in the explicit config")
    return target


def provision_bitwarden_host(profile, template="@BITWARDEN_HOST@"):
    """Install only our immutable host link; preserve app/user-owned manifests."""
    template = Path(template)
    if not template.is_absolute() or not template.is_file():
        raise ValueError("Packaged Bitwarden native host manifest is unavailable")
    directory = profile / "NativeMessagingHosts"
    private_dir(directory)
    destination = directory / "com.8bit.bitwarden.json"
    if destination.is_symlink():
        previous = os.readlink(destination)
        if previous == str(template):
            return
        if not (previous.startswith("/nix/store/") and previous.endswith("-pi-browser-bitwarden-native-host.json")):
            return
    elif destination.exists():
        return
    fd, name = tempfile.mkstemp(prefix=".bitwarden-host-", dir=directory)
    os.close(fd)
    temporary = Path(name)
    try:
        temporary.unlink()
        temporary.symlink_to(template)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def open_manual_tab(process, state, executable, target, root, env):
    """Use ordinary Vivaldi URL handoff after its native UI has mapped."""
    deadline = time.monotonic() + 20
    hyprctl = state.get("hyprctl", "@HYPRCTL@")
    while True:
        result = subprocess.run([hyprctl, "clients", "-j"], env=env,
                                capture_output=True, text=True, timeout=5, check=True)
        clients = json.loads(result.stdout)
        if any(c.get("mapped") and c.get("pid") == process.pid for c in clients):
            break
        if process.poll() is not None or time.monotonic() >= deadline:
            raise ValueError("Manual Vivaldi window did not map")
        time.sleep(0.05)
    # A fresh Vivaldi profile initially selects its own welcome tab. Hand the
    # task URL to that already-running instance, rather than inspecting pages
    # or controlling it through a debugger during the manual phase.
    with (root / "vivaldi.log").open("a") as log:
        subprocess.run([executable, "--user-data-dir=" + state["profile"], "--new-tab", target],
                       cwd=root, env=env, stdout=log, stderr=log, timeout=15, check=True)
    if process.poll() is not None:
        raise ValueError("Manual Vivaldi exited during URL handoff")


def shared_profile(root):
    """Only native headed defaults share human login state; headless stays isolated."""
    return root.parent / "shared-profile"


@contextmanager
def profile_launch_lock(profile):
    """Serialize the check-to-SingletonLock startup gap across Pi sessions."""
    fd = os.open(profile / ".pi-browser-launch.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("Invalid profile launch lock")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Vivaldi profile is starting in another session; do not replace it") from None
        if profile_locked(profile):
            raise ValueError("Vivaldi profile is already open; use its owning chat, or --no-persistent for an isolated browser")
        yield


def seed_appearance(profile):
    """Set managed chrome preferences only while the browser is stopped.

    Never touch cookies, extension storage, vault settings or native debugging
    consent. Malformed or redirected preferences fail closed, not get replaced.
    """
    directory = profile / "Default"
    private_dir(directory)
    path = directory / "Preferences"
    if path.is_symlink():
        raise ValueError("Refusing redirected browser preferences")
    data = json.loads(path.read_text()) if path.exists() else {}
    for keys in ((), ("vivaldi",), ("vivaldi", "themes"), ("vivaldi", "theme"),
                 ("vivaldi", "theme", "schedule"), ("vivaldi", "status_bar"),
                 ("vivaldi", "panels"), ("vivaldi", "panels", "window_defaults")):
        value = data
        for key in keys:
            value = value.get(key, {})
        if not isinstance(value, dict):
            raise ValueError("Invalid browser appearance preferences; refusing replacement")
    vivaldi = data.setdefault("vivaldi", {})
    vivaldi.setdefault("themes", {})["current"] = "Vivaldi2"
    vivaldi.setdefault("theme", {}).setdefault("schedule", {})["enabled"] = 0
    vivaldi.setdefault("status_bar", {})["display"] = 1  # Vivaldi enum: off
    panels = vivaldi.setdefault("panels", {})
    panels["show_toggle"] = False
    panels.setdefault("window_defaults", {})["barVisible"] = False
    write_json(path, data)


def start_headed(root, config, args, env):
    target = validate_native_settings(config, args)
    manual = boolean_option(args, "manual")
    browser = config["browser"]
    launch = browser["launchOptions"]
    extra = launch.get("args", [])
    profile = option_value(args, "--profile") or browser.get("userDataDir")
    if not profile and boolean_option(args, "persistent"):
        profile = str(root / "profile")
    temporary = not profile
    if temporary:
        profile = tempfile.mkdtemp(prefix="headed-", dir=runtime_root(root))
    # Config userDataDir paths follow the upstream daemon cwd semantics; explicit
    # --profile arguments were already resolved against the invoking cwd.
    profile = (root / profile).resolve()
    private_dir(profile)
    with profile_launch_lock(profile):
        if profile == shared_profile(root):
            seed_appearance(profile)
        return launch_headed_profile(root, config, args, env, target, manual, profile, temporary)


def unused_loopback_port():
    # A nonzero standard developer port keeps manual browser behavior intact
    # (port=0 itself enables Chromium's webdriver indicator). No JS overrides.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def loopback_listener_owned(pid, port):
    """Fail closed on port-selection races; never probe another browser's CDP."""
    try:
        inodes = set()
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                link = str(fd.readlink())
            except OSError:
                continue
            if link.startswith("socket:[") and link.endswith("]"):
                inodes.add(link[8:-1])
        found = False
        for family, loopback in (("tcp", "0100007F"), ("tcp6", "00000000000000000000000001000000")):
            try:
                lines = Path(f"/proc/{pid}/net/{family}").read_text().splitlines()[1:]
            except FileNotFoundError:
                if family == "tcp6":
                    continue  # IPv6 can be absent; IPv4 ownership remains required.
                raise
            for line in lines:
                fields = line.split()
                address, number = fields[1].split(":")
                if fields[3] != "0A" or int(number, 16) != port or fields[9] not in inodes:
                    continue
                if address != loopback:
                    raise ValueError("Owned debugging listener is not restricted to loopback")
                found = found or family == "tcp"
        return found
    except OSError:
        return False


def preauthorized_endpoint(state):
    """Only version metadata, after exact PID/start and listening-socket checks."""
    value = state.get("endpoint")
    if not isinstance(value, str):
        raise ValueError("Invalid preauthorized loopback endpoint")
    try:
        endpoint = urllib.parse.urlsplit(value)
        port = endpoint.port
    except ValueError:
        raise ValueError("Invalid preauthorized loopback endpoint") from None
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not port
            or endpoint.username or endpoint.password or endpoint.path or endpoint.query or endpoint.fragment):
        raise ValueError("Invalid preauthorized loopback endpoint")
    if process_start(state["pid"]) != state["start"] or not loopback_listener_owned(state["pid"], port):
        return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(state["endpoint"] + "/json/version", timeout=2) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("Invalid owned debugging version metadata")
    data = json.loads(data)
    websocket = data.get("webSocketDebuggerUrl") if isinstance(data, dict) else None
    if not isinstance(websocket, str):
        raise ValueError("Missing owned debugging endpoint")
    address = urllib.parse.urlsplit(websocket)
    if (address.scheme != "ws" or address.netloc != endpoint.netloc or address.query or address.fragment
            or not re.fullmatch(r"/devtools/browser/[a-f0-9-]{36}", address.path)
            or state.get("websocketPath", address.path) != address.path):
        raise ValueError("Owned debugging endpoint identity changed")
    return websocket


def owned_runtime_endpoint(state, profile):
    return preauthorized_endpoint(state) if state.get("preauthorized") else runtime_endpoint(profile)


def launch_headed_profile(root, config, args, env, target, manual, profile, temporary):
    browser = config["browser"]
    launch = browser["launchOptions"]
    extra = launch.get("args", [])
    # Leave stale-lock recovery to Vivaldi itself, never unlink a live lock.
    port_file = profile / "DevToolsActivePort"
    port_file.unlink(missing_ok=True)
    preauthorized = manual and not boolean_option(args, "native-consent")
    port = unused_loopback_port() if preauthorized else 0
    state = {"profile": str(profile), "temporary": temporary, "bound": True,
             "manual": manual, "preauthorized": preauthorized, "url": target}
    if preauthorized:
        state["endpoint"] = f"http://127.0.0.1:{port}"
    try:
        provision_bitwarden_host(profile)
        state.update(placement_rule(root, env))
        window_class = ["--class=" + state["class"]] if state.get("class") else []
        with (root / "vivaldi.log").open("a") as log:
            process = subprocess.Popen([
                launch["executablePath"], "--no-first-run", "--no-default-browser-check",
                "--disable-dev-shm-usage",
                *([] if manual and not preauthorized else ["--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}"]),
                "--user-data-dir=" + str(profile), *extra, *window_class, "about:blank"],
                cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
    except BaseException:
        remove_temporary_profile(root, state)
        release_rule(state)
        raise
    try:
        start = process_start(process.pid)
        if start is None:
            raise ValueError("Vivaldi exited before its process identity could be verified")
        state.update({"pid": process.pid, "start": start})
        write_json(root / "vivaldi-process.json", state)
        deadline = time.monotonic() + 30
        if manual:
            # No agent connection or page observation before human handback.
            # Default mode has an authorized localhost debugging server; explicit
            # --native-consent instead leaves startup debugging disabled.
            while not profile_locked(profile):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError("Manual Vivaldi did not acquire its profile; see vivaldi.log")
                time.sleep(0.05)
            if preauthorized:
                while True:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise ValueError("Owned loopback debugging server did not become ready; no foreign endpoint used")
                    try:
                        endpoint = preauthorized_endpoint(state)
                    except OSError:
                        endpoint = None
                    if endpoint:
                        state["websocketPath"] = urllib.parse.urlsplit(endpoint).path
                        write_json(root / "vivaldi-process.json", state)
                        break
                    time.sleep(0.05)
            open_manual_tab(process, state, launch["executablePath"], target, root, env)
            return process, None
        while not port_file.exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise ValueError("Vivaldi did not publish its owned endpoint; see vivaldi.log")
            time.sleep(0.05)
        port_info = port_file.read_text().splitlines()
        port = int(port_info[0])
        if not 0 < port < 65536 or process.poll() is not None:
            raise ValueError("Invalid managed Vivaldi endpoint")
        # Use the official CLI over CDP, not Playwright's Chromium startup pipe:
        # Vivaldi's extension-backed UI does not complete that startup handshake.
        browser["cdpEndpoint"] = f"http://127.0.0.1:{port}"
        state["endpoint"] = browser["cdpEndpoint"]
        state["websocketPath"] = port_info[1]
        write_json(root / "vivaldi-process.json", state)
        # Vivaldi initially exposes its welcome/UI extension, not a normal page.
        # Create a web target before the CLI attaches; otherwise its initial
        # page handshake can wait indefinitely on the extension-backed UI.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        bootstrap = "data:text/html,<title>Browser ready</title>"
        request = urllib.request.Request(browser["cdpEndpoint"] + "/json/new?" +
                                         urllib.parse.quote(bootstrap, safe=""), method="PUT")
        with opener.open(request, timeout=10) as response:
            target_info = json.load(response)
        # Attaching during Vivaldi's UI bootstrap can strand target creation.
        # Wait on an actual rendered web target instead of sleeping a fixed time.
        deadline = time.monotonic() + 20
        while True:
            with opener.open(browser["cdpEndpoint"] + "/json/list", timeout=5) as response:
                targets = json.load(response)
            if any(page.get("id") == target_info.get("id") and page.get("title") for page in targets):
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                raise ValueError("Vivaldi web target is not ready; its workspace may not have rendered yet")
            time.sleep(0.1)
        with opener.open(browser["cdpEndpoint"] + "/json/activate/" + target_info["id"], timeout=5) as response:
            response.read()
        browser["cdpTimeout"] = 45000
        browser["isolated"] = False
        return process, target_info["id"]
    except BaseException:
        stop_managed(root)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        remove_temporary_profile(root, state)
        raise


def connect_headed(cli, root, config, args, env, target_id):
    # Start the pinned official daemon without CLI open/attach's implicit first
    # snapshot/navigation, which could otherwise touch a restored unrelated tab.
    options = [f"--config={config}"]
    for name in ("headed", "persistent", "mobile"):
        if boolean_option(args, name):
            options.append("--" + name)
    for name in ("browser", "device", "profile", "idle-timeout"):
        value = option_value(args, "--" + name)
        if value is not None:
            options.append("--" + name + "=" + value)
    with (root / "daemon.log").open("a") as log:
        daemon = subprocess.Popen(["@NODE@", "@DAEMON@", "agent", *options], cwd=root, env=env,
                                  stdout=subprocess.PIPE, stderr=log, text=True, start_new_session=True)
    deadline = time.monotonic() + 45
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([daemon.stdout], [], [], max(0, remaining))[0]:
                raise ValueError("Official Playwright daemon did not become ready; see daemon.log")
            line = daemon.stdout.readline()
            if "Daemon listening on" in line:
                break
            if not line and daemon.poll() is not None:
                raise ValueError("Official Playwright daemon exited; see daemon.log")
    except BaseException:
        daemon.terminate()
        raise
    finally:
        daemon.stdout.close()
    # Resolve the exact target we created, not whichever restored tab happens to
    # be first. Only target identity is read; no unrelated DOM/screenshot capture.
    script = """async(page)=>{const pages=page.context().pages();for(let i=0;i<pages.length;i++){
const s=await page.context().newCDPSession(pages[i]);try{const info=await s.send('Target.getTargetInfo');
if(info.targetInfo.targetId===""" + json.dumps(target_id) + """)return i;}finally{await s.detach();}}
throw new Error('Owned Vivaldi target not found');}"""
    index = subprocess.run([cli, "-s=agent", "run-code", script, "--json"],
                           cwd=root, env=env, text=True, capture_output=True, timeout=15, check=False)
    if index.returncode:
        raise ValueError("Could not select the owned Vivaldi tab")
    tab = int(json.loads(index.stdout)["result"])
    if tab < 0:
        raise ValueError("Invalid owned Vivaldi tab index")
    command = [cli, "-s=agent", "tab-select", str(tab)]
    for name in ("json", "raw"):
        if boolean_option(args, name):
            command.append("--" + name)
    selected = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
    if selected.stderr:
        print(selected.stderr, file=sys.stderr, end="")
    if selected.returncode:
        print(selected.stdout, end="")
        return selected.returncode
    # The requested URL is navigated only after the official backend has applied
    # its file/network policy and the exact owned target is selected.
    navigation = [cli, "-s=agent", "goto", open_target(args)]
    for name in ("json", "raw"):
        if boolean_option(args, name):
            navigation.append("--" + name)
    return subprocess.run(navigation, cwd=root, env=env, check=False).returncode


def stop_runtime_daemon(state):
    daemon = state.get("runtime_daemon", {})
    if (isinstance(daemon, dict) and isinstance(daemon.get("pid"), int)
            and daemon["pid"] > 1 and daemon["pid"] != state.get("pid")
            and daemon.get("start") and process_start(daemon["pid"]) == daemon["start"]):
        try:
            os.kill(daemon["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass


def runtime_endpoint(profile):
    path = profile / "DevToolsActivePort"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 256:
            raise ValueError("Invalid owned runtime debugging marker")
        lines = stream.read().splitlines()
    if (len(lines) != 2 or not lines[0].isdigit() or not 0 < int(lines[0]) < 65536
            or not re.fullmatch(r"/devtools/browser/[a-f0-9-]{36}", lines[1])):
        raise ValueError("Invalid owned runtime debugging marker")
    return "ws://127.0.0.1:" + lines[0] + lines[1]


def private_cli_result(cli, root, env, *args):
    try:
        response = subprocess.run([cli, "-s=agent", *args, "--json"], cwd=root, env=env,
                                  text=True, capture_output=True, timeout=20, check=False)
        envelope = json.loads(response.stdout)
        if response.returncode or not isinstance(envelope, dict) or envelope.get("isError"):
            raise ValueError
        value = envelope.get("result")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        return value
    except (OSError, ValueError, subprocess.SubprocessError):
        # Never forward CLI code/page/tab/error metadata, which may contain
        # private authentication URLs or credentials, to the transcript.
        raise ValueError("Runtime browser command failed; private output was suppressed") from None


def connect_manual(cli, root, env, browser_executable):
    state = managed_state(root)
    if not state or not state.get("bound", True) or not (state.get("manual") or state.get("runtime")):
        raise ValueError("No owned manual Vivaldi is running; open --headed --manual first")
    profile = Path(state["profile"])
    try:
        host, pid = os.readlink(profile / "SingletonLock").rsplit("-", 1)
    except (OSError, ValueError):
        raise ValueError("Owned manual profile lock is unavailable") from None
    if host != os.uname().nodename or pid != str(state["pid"]):
        raise ValueError("Manual profile is not owned by the recorded browser")
    if not state.get("manual"):
        # Reuse only a previously approved, still-owned native connection. No
        # CLI page command here: ensureTab can create a tab when one is missing.
        # This is connection metadata, not proof of page/task responsiveness.
        daemon = state.get("runtime_daemon")
        if (not isinstance(daemon, dict) or not isinstance(daemon.get("pid"), int) or daemon["pid"] <= 1
                or daemon["pid"] == state["pid"] or not daemon.get("start")
                or process_start(daemon["pid"]) != daemon["start"]
                or not daemon.get("endpoint") or owned_runtime_endpoint(state, profile) != daemon["endpoint"]):
            raise ValueError("Approved connection is unavailable or changed; no new connection was started")
        print(json.dumps({"connected": True, "reused": True}))
        return 0
    config = state.get("manual_config") or json.loads((root / "config.json").read_text())
    if (config.get("browser", {}).get("launchOptions", {}).get("executablePath") != browser_executable
            or config.get("browser", {}).get("remoteEndpoint")):
        raise ValueError("Manual browser configuration changed; reopen explicitly")
    validate_native_settings(config, ["open", "--headed", "--", state["url"]])
    url = urllib.parse.urlsplit(state["url"])
    if url.scheme not in ("http", "https") or not url.hostname:
        raise ValueError("Runtime connection requires an HTTP(S) task URL")
    host_name = "[" + url.hostname + "]" if ":" in url.hostname else url.hostname
    port = url.port
    origin = url.scheme + "://" + host_name + ((":" + str(port)) if port and
             (url.scheme, port) not in (("http", 80), ("https", 443)) else "")
    endpoint = owned_runtime_endpoint(state, profile)
    if not endpoint and state.get("preauthorized"):
        raise ValueError("Owned preauthorized debugging server is unavailable; no consent mode fallback attempted")
    if not endpoint:
        # Merely show the native setting. Only Sumeet may enable it.
        with (root / "vivaldi.log").open("a") as log:
            subprocess.run([browser_executable, "--user-data-dir=" + str(profile), "--new-tab",
                            "vivaldi://inspect/#remote-debugging"], env=env, cwd=root,
                           stdout=log, stderr=log, timeout=15, check=True)
        print(json.dumps({"status": "enable-debugging", "connected": False}))
        return 0
    daemon = state.get("runtime_daemon")
    if not daemon:
        state["manual_config"] = config
        attached = json.loads(json.dumps(config))
        attached["browser"].update(cdpEndpoint=endpoint, cdpTimeout=0, isolated=False, userDataDir=str(profile))
        attached["saveSession"] = False
        write_json(root / "runtime-config.json", attached)
        with (root / "runtime-daemon.log").open("ab") as log:
            offset = log.tell()
            process = subprocess.Popen(["@NODE@", "@DAEMON@", "agent",
                                        "--config=" + str(root / "runtime-config.json"), "--cdp=" + endpoint, "--headed"],
                                       cwd=root, env={**env, "PI_BROWSER_METADATA_ONLY": "1"},
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        start = process_start(process.pid)
        if not start:
            raise ValueError("Runtime connection could not start; browser remains manual")
        state["runtime_daemon"] = {"pid": process.pid, "start": start, "offset": offset, "endpoint": endpoint}
        write_json(root / "vivaldi-process.json", state)
        print(json.dumps({"status": "connecting" if state.get("preauthorized") else "approve-connection", "connected": False}))
        return 0
    if daemon.get("endpoint") != endpoint:
        raise ValueError("Runtime endpoint changed; close or detach the prior connection first")
    if process_start(daemon["pid"]) != daemon["start"]:
        state.pop("runtime_daemon", None)
        write_json(root / "vivaldi-process.json", state)
        raise ValueError("Runtime connection ended or was declined; browser remains manual")
    with (root / "runtime-daemon.log").open("rb") as log:
        log.seek(daemon["offset"])
        ready = b"Daemon listening on" in log.read(65536)
    if not ready:
        print(json.dumps({"status": "connecting" if state.get("preauthorized") else "awaiting-approval", "connected": False}))
        return 0
    # No navigation, new tab, cookie copy or restart: select the existing task.
    selection = "return found[0];}"
    if state.get("preauthorized"):
        selection = ("const index=found[0];const session=await page.context().newCDPSession(pages[index]);"
                     "try{const info=await session.send('Target.getTargetInfo');return {index,targetId:info.targetInfo.targetId};}"
                     "finally{await session.detach();}}")
    script = ("async(page)=>{const pages=page.context().pages();const found=[];"
              "for(let i=0;i<pages.length;i++){try{if(new URL(pages[i].url()).origin==="
              + json.dumps(origin) + ")found.push(i);}catch{}}"
              "if(found.length!==1)throw Error('Task origin is missing or ambiguous');" + selection)
    selected = private_cli_result(cli, root, env, "run-code", script)
    index = selected.get("index") if state.get("preauthorized") and isinstance(selected, dict) else selected
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ValueError("Could not identify one task tab")
    if state.get("preauthorized"):
        if (not isinstance(selected, dict) or not isinstance(selected.get("targetId"), str)
                or not re.fullmatch(r"[A-Fa-f0-9]{32}", selected["targetId"])):
            raise ValueError("Could not identify the owned task target")
        if preauthorized_endpoint(state) != endpoint:
            raise ValueError("Owned debugging endpoint changed before task selection")
        # Page.bringToFront alone may leave a first-install extension tab active
        # in an unfocused window. Reuse the owned HTTP target-activation API,
        # never global desktop focus/input, navigation or new-tab creation.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(state["endpoint"] + "/json/activate/" + selected["targetId"], timeout=5) as response:
            response.read(1024)
    private_cli_result(cli, root, env, "tab-select", str(index))
    value = private_cli_result(cli, root, env, "run-code",
                               "async(page)=>({origin:new URL(page.url()).origin})")
    if not isinstance(value, dict) or value.get("origin") != origin:
        raise ValueError("Task origin changed; no page content was inspected")
    state["manual"] = False
    state["runtime"] = True
    state.pop("manual_config", None)
    write_json(root / "vivaldi-process.json", state)
    print(json.dumps({"connected": True, "origin": origin}))
    return 0


def run(args, *, cli, browser_executable):
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
        settings = {
            # Vivaldi is the executable; chromium is Playwright's engine name.
            "browser": {"browserName": "chromium",
                        "launchOptions": launch_options(browser_executable, args)},
            "outputDir": str(root / "artifacts"),
            "timeouts": {"action": 5000, "navigation": 45000},
        }
        custom = option_value(args, "--config")
        supplied = None
        if custom and args[0] == "open":
            contents = Path(custom).read_text(encoding="utf-8-sig")
            try:
                supplied = json.loads(contents)
            except json.JSONDecodeError as error:
                if contents.lstrip().startswith("{"):
                    raise ValueError("Invalid JSON browser configuration") from error
                # Non-JSON configs remain entirely on the upstream path. They
                # must never trigger native-mode selection from our defaults.
                supplied = None
            if isinstance(supplied, dict):
                settings = supplied
        configured = settings.get("browser", {})
        launch = configured.get("launchOptions", {})
        help_only = has_option(args, "--help") or has_option(args, "--version") or "-h" in args
        if help_only and args and args[0] == "open" and has_option(args, "--manual"):
            print("--manual: agent stays disconnected until handback; localhost debugging is preauthorized by default. --native-consent opts into native approval instead")
            return 0
        if args and args[0] == "open" and not help_only:
            open_target(args)  # Validate before any native process/profile side effect.
        native = bool(args and args[0] == "open" and not help_only
                      and (not custom or isinstance(supplied, dict))
                      and launch.get("executablePath") == browser_executable
                      and boolean_option(args, "headed", not launch.get("headless", True))
                      and not configured.get("cdpEndpoint") and not configured.get("remoteEndpoint"))
        if native:
            validate_native_settings(settings, args)
        env = child_env(os.environ, root)
        operation = args[0] if args else ""
        if operation == "connect":
            if args[1:] in (["--help"], ["-h"]):
                print("pi-browser connect: after handback, attach to the owned preauthorized loopback server without prompts, or request native approval in --native-consent mode; existing connections are reused")
                return 0
            if args[1:]:
                raise ValueError("connect takes no options or URL")
            return connect_manual(cli, root, env, browser_executable)
        manual = bool(operation == "open" and boolean_option(args, "manual"))
        if operation == "open" and not help_only and boolean_option(args, "native-consent") and not manual:
            raise ValueError("--native-consent requires --headed --manual")
        if manual and not help_only:
            if not native:
                raise ValueError("--manual requires native Vivaldi with --headed")
            if any(arg.startswith(("--enable-automation", "--headless")) for arg in launch.get("args", [])):
                raise ValueError("Manual mode does not accept automation/headless launch flags")
        current = managed_state(root)
        if current and operation == "open" and not help_only:
            raise ValueError("Owned browser is already open; use connect after handback, or goto/tab-new if connected. "
                             "Replacing it requires an explicit close first")
        if current and current.get("manual") and operation == "list" and not help_only:
            pending = "connecting" if current.get("preauthorized") else "awaiting-consent"
            print(json.dumps({"mode": pending if current.get("runtime_daemon") else "manual", "running": True,
                              "connected": False, "debugging": "preauthorized" if current.get("preauthorized") else "native-consent"}))
            return 0
        if current and current.get("manual") and operation == "detach" and not help_only:
            # Upstream may retain a stale non-attached headless session entry.
            # Ownership handback must not depend on that unrelated CLI status.
            stop_runtime_daemon(current)
            current.pop("runtime_daemon", None)
            release_rule(current)
            current.pop("rule", None)
            current["bound"] = False
            write_json(root / "vivaldi-process.json", current)
            print(json.dumps({"status": "detached"}))
            return 0
        if (current and current.get("manual") and not help_only
                and operation not in {"", "open", "close", "detach", "delete-data", "list"}):
            raise ValueError("Manual browser has no agent connection; use connect after explicit handback")
        if args and args[0] == "attach" and not help_only and managed_state(root):
            raise ValueError("Close or detach the managed Vivaldi before attaching another browser")
        if operation == "delete-data" and not help_only:
            previous = json.loads(config.read_text()) if config.exists() else {}
            profile = (read_state(root) or {}).get("profile") or previous.get("browser", {}).get("userDataDir")
            if profile and Path(profile) == shared_profile(root):
                raise ValueError("Shared sign-in profile is retained; use close, not delete-data")
        if native and not custom and not option_value(args, "--profile") and boolean_option(args, "persistent", True):
            profile = shared_profile(root)
            private_dir(profile)  # Refuse redirected shared profile directories.
            configured["userDataDir"] = str(profile)
        if args and args[0] == "open" and not help_only and (native or managed_state(root)):
            closed = subprocess.run([cli, "-s=agent", "close"], cwd=root, env=env,
                                    text=True, capture_output=True, check=False)
            if closed.returncode:
                print(closed.stdout or "", end="")
                print(closed.stderr or "", file=sys.stderr, end="")
                return closed.returncode
            stop_managed(root)
        if not native and not custom and boolean_option(args, "persistent"):
            # Headless persistence stays session-local; never inherit human auth.
            configured["userDataDir"] = str(root / "profile")
        process = None
        target_id = None
        if native:
            process, target_id = start_headed(root, settings, args, env)
        try:
            if not (current and current.get("manual") and (operation != "open" or help_only)):
                write_json(config, settings)
            command = [cli, "-s=agent"]
            if args and args[0] in ("open", "attach") and (native or not custom):
                command += [f"--config={config}"]
            # Upstream delete-data may remove a descriptor's userDataDir even
            # after close discarded our ownership record. Never delegate data
            # deletion: only the checked session/profile cleanup below is ours.
            command += (["close"] if operation == "delete-data" and not help_only else
                        (replace_config(args, config) if native else without_manual_option(args))) or ["--help"]
            print(f"pi-browser artifacts: {root / 'artifacts'}", file=sys.stderr, flush=True)
            if native and manual:
                # Keep a readable parent for the sandboxed browser until exit.
                # The workspace helper verifies exact launch ancestry; Chromium
                # may hide /proc/<pid>/environ, and an early-exiting launcher
                # would discard that proof before the native window maps.
                threading.Thread(target=process.wait, daemon=False).start()
                if boolean_option(args, "json"):
                    print(json.dumps({"mode": "manual", "connected": False,
                                      "debugging": "preauthorized" if read_state(root).get("preauthorized") else "native-consent"}))
                else:
                    print("Manual browser opened without agent control. After explicit handback, connect uses preauthorized localhost debugging (or native approval if --native-consent was selected).")
                return 0
            result = (connect_headed(cli, root, config, args, env, target_id) if native else
                      subprocess.run(command, cwd=root, env=env, check=False).returncode)
            if (not args or has_option(args, "--help")) and operation in ("", "open"):
                print("Wrapper: headed defaults retain a cross-chat profile; --no-persistent is temporary. --manual defers agent attachment; localhost debugging is preauthorized unless --native-consent is selected.")
            if args and args[0] in ("close", "delete-data"):
                stop_managed(root)
                if args[0] == "delete-data" and result == 0:
                    profile = root / "profile"
                    if profile.is_symlink():
                        raise ValueError("Refusing persistent-profile symlink deletion")
                    if profile_locked(profile):
                        raise ValueError("Persistent profile is locked; refusing deletion")
                    if profile.exists():
                        shutil.rmtree(profile)
            elif args and args[0] == "detach" and result == 0:
                state = read_state(root)
                if state:
                    stop_runtime_daemon(state)
                    state.pop("runtime_daemon", None)
                    release_rule(state)
                    state.pop("rule", None)
                    state["bound"] = False  # Explicitly handed back; no later close may kill it.
                    write_json(root / "vivaldi-process.json", state)
            if native and result:
                stop_managed(root)
            return result
        except BaseException:
            if process is not None:
                stop_managed(root)
            raise


def main():
    try:
        return run(sys.argv[1:], cli="@CLI@", browser_executable="@BROWSER_EXECUTABLE@")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"pi-browser: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
