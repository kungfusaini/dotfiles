#!/usr/bin/env python3
"""Safe local Steam inspection and lifecycle helper for the steam-organizer skill."""

from __future__ import annotations

import argparse
import fcntl
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

STEAM_ROOT = Path.home() / ".local/share/Steam"
STEAM_APPS = STEAM_ROOT / "steamapps"
USERDATA = STEAM_ROOT / "userdata"
LOGS = STEAM_ROOT / "logs"
STATE_DIR = Path.home() / ".local/state/steam-organizer"
HIDE_WATCH_PID = STATE_DIR / "hide-watch.pid"
HIDE_WATCH_LOCK = STATE_DIR / "hide-watch.lock"
STEAM64_BASE = 76561197960265728
FULLY_INSTALLED = 4
SECRET_ATTRIBUTES = ("application", "steam-organizer", "credential", "web-api-key")
CATALOG_CACHE = STATE_DIR / "catalog-v1.json"
CATALOG_CACHE_VERSION = 1
CATALOG_TTL_DAYS = 30
PROTON_TTL_DAYS = 7
MULTIPLAYER_CATEGORY_IDS = {1, 9, 24, 36, 37, 38, 39, 47, 48, 49}
MODE_CATEGORY_IDS = {
    "couch": {24, 37, 39},
    "co-op": {9, 38, 39, 48},
    "online": {1, 36, 38},
    "competitive": {36, 37, 47, 49},
    "singleplayer": {2},
}
TWO_PLAYER_CATEGORY_IDS = MULTIPLAYER_CATEGORY_IDS


class SteamError(RuntimeError):
    pass


def emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def human_bytes(value: int | str | None) -> str | None:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return None
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return None


def tokenize_vdf(text: str) -> list[str]:
    return re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text)


def decode_token(token: str) -> str:
    value = token[1:-1]
    return value.replace(r"\n", "\n").replace(r'\"', '"').replace(r"\\", "\\")


def parse_vdf(path: Path) -> dict[str, Any]:
    try:
        tokens = tokenize_vdf(path.read_text(errors="replace"))
    except OSError as exc:
        raise SteamError(f"Could not read Steam metadata: {path}") from exc

    def parse_object(index: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(tokens):
            token = tokens[index]
            if token == "}":
                return result, index + 1
            if not token.startswith('"'):
                raise SteamError(f"Malformed Steam metadata: {path}")
            key = decode_token(token)
            index += 1
            if index >= len(tokens):
                raise SteamError(f"Malformed Steam metadata: {path}")
            if tokens[index] == "{":
                value, index = parse_object(index + 1)
            else:
                value = decode_token(tokens[index])
                index += 1
            result[key] = value
        return result, index

    parsed, _ = parse_object(0)
    return parsed


def library_paths() -> list[Path]:
    paths = [STEAM_ROOT]
    config = STEAM_APPS / "libraryfolders.vdf"
    if config.exists():
        data = parse_vdf(config).get("libraryfolders", {})
        if isinstance(data, dict):
            for entry in data.values():
                if isinstance(entry, dict) and entry.get("path"):
                    paths.append(Path(str(entry["path"])))
    unique: list[Path] = []
    for path in paths:
        path = path.expanduser()
        if path not in unique:
            unique.append(path)
    return unique


def manifests() -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for library in library_paths():
        appdir = library / "steamapps"
        for manifest in sorted(appdir.glob("appmanifest_*.acf")):
            try:
                state = parse_vdf(manifest).get("AppState", {})
            except SteamError:
                continue
            if not isinstance(state, dict):
                continue
            try:
                appid = int(state.get("appid", manifest.stem.split("_")[-1]))
                flags = int(state.get("StateFlags", 0))
                size = int(state.get("SizeOnDisk", 0))
                downloaded = int(state.get("BytesDownloaded", 0))
                to_download = int(state.get("BytesToDownload", 0))
            except (TypeError, ValueError):
                continue
            games.append(
                {
                    "appid": appid,
                    "name": state.get("name", f"App {appid}"),
                    "library": str(library),
                    "install_dir": str(appdir / "common" / str(state.get("installdir", ""))),
                    "state_flags": flags,
                    "fully_installed": bool(flags & FULLY_INSTALLED)
                    and (not to_download or downloaded >= to_download),
                    "size_bytes": size,
                    "size": human_bytes(size),
                    "bytes_downloaded": downloaded,
                    "bytes_to_download": to_download,
                    "manifest": str(manifest),
                }
            )
    return games


def steam_main_pids() -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            parts = (entry / "cmdline").read_bytes().split(b"\0")
            argv = [part.decode(errors="replace") for part in parts if part]
        except (OSError, PermissionError):
            continue
        if not argv:
            continue
        executable = argv[0]
        if executable.endswith("/ubuntu12_32/steam") and "-child-update-ui" not in argv:
            pids.append(int(entry.name))
    return sorted(pids)


def steam_running() -> bool:
    return bool(steam_main_pids())


def running_game_appids() -> list[int]:
    """Combine process-environment and Steam-log evidence of running games."""
    appids: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            values = (entry / "environ").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        for raw in values:
            if raw.startswith((b"SteamAppId=", b"SteamGameId=")):
                try:
                    appid = int(raw.split(b"=", 1)[1])
                except ValueError:
                    continue
                if appid not in (0, 7, 760):
                    appids.add(appid)
    appids.update(running_game_log_appids())
    return sorted(appids)


def steam_session_start_time() -> float | None:
    """Current client lifetime, independent of log rotation or version markers."""
    try:
        boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        ticks = [process_start_ticks(pid) for pid in steam_main_pids()]
        starts = [boot + tick / os.sysconf("SC_CLK_TCK") for tick in ticks if tick is not None]
        return min(starts) if starts else None
    except (OSError, ValueError, StopIteration):
        return None


def current_session_lines(name: str) -> list[str]:
    """Keep history on disk; only interpret evidence from the running client."""
    if not steam_running():
        return []
    try:
        text = (LOGS / name).read_text(errors="replace")
    except OSError:
        return []
    text = text.rsplit("Client version:", 1)[-1]
    started = steam_session_start_time()
    lines = []
    for line in text.splitlines():
        stamp = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
        if started is not None and stamp:
            try:
                if time.mktime(time.strptime(stamp[1], "%Y-%m-%d %H:%M:%S")) < started - 2:
                    continue
            except ValueError:
                pass  # Unknown timestamps are not proof that activity ended.
        lines.append(line)
    return lines


def active_download_appids() -> list[int]:
    if not steam_running():
        return []
    # Steam's StateFlags are a bitmask: UpdateRequired/FullyInstalled (6)
    # describes an idle pending update, not a running transfer. See AppsCommon.h.
    phases: dict[tuple[int, str], bool] = {}
    pattern = re.compile(r"AppID (\d+) (App|Shader|Workshop) update changed\s*:\s*(.*)", re.I)
    for line in current_session_lines("content_log.txt"):
        match = pattern.search(line)
        if match:
            phases[(int(match[1]), match[2].lower())] = "running update" in match[3].lower()
    logged = {appid: any(active for (item, _), active in phases.items() if item == appid)
              for appid, _ in phases}
    active = {appid for appid, running in logged.items() if running}
    # Running, reconfiguring/validating/adding/preallocating/downloading/staging/
    # committing, uninstalling and stopping are real work. Started alone is
    # ambiguous: retain the guard unless current-session logs confirm it ended.
    work_mask = 0x100 | 0xFF0000 | 0x800
    for game in manifests():
        appid, flags = int(game["appid"]), int(game["state_flags"])
        if flags & work_mask:
            active.add(appid)
        elif appid not in logged and flags & 0x400 and not flags & 0x200:
            active.add(appid)
    # Leftover staging directories alone cannot demonstrate active I/O.
    return sorted(active)


def active_cloud_appids() -> list[int]:
    lines = current_session_lines("cloud_log.txt")
    states: dict[int, bool] = {}
    sync_success_seen: set[int] = set()
    initializing: set[int] = set()
    uploading: set[int] = set()
    downloading: set[int] = set()
    pattern = re.compile(r"\[AppID (\d+)\]", re.I)
    completed = (
        "eval complete",
        "not running autocloud",
        "getappquotausage - success",
    )
    for line in lines:
        if "Client version:" in line:
            states.clear()
            sync_success_seen.clear()
            initializing.clear()
            uploading.clear()
            downloading.clear()
            continue
        match = pattern.search(line)
        if not match:
            continue
        appid = int(match.group(1))
        lower = line.lower()
        if "starting sync" in lower:
            states[appid] = True
            if "(init," in lower:
                initializing.add(appid)
            else:
                initializing.discard(appid)
        if "upload batch initiated" in lower or "http upload" in lower and "beginning" in lower:
            uploading.add(appid)
            states[appid] = True
        if "http download" in lower and "beginning" in lower:
            downloading.add(appid)
            states[appid] = True
        download_done = "download complete" in lower or "download failed" in lower
        upload_done = "upload complete" in lower
        if download_done:
            downloading.discard(appid)
        if upload_done:
            uploading.discard(appid)
        transferring = appid in uploading or appid in downloading
        if appid in initializing and not transferring and "init cache request complete" in lower:
            states[appid] = False
            initializing.discard(appid)
        if "successfully synced" in lower:
            sync_success_seen.add(appid)
        if appid in sync_success_seen and not transferring and "yldwritecachedirectorytofile" in lower:
            states[appid] = False
            sync_success_seen.discard(appid)
        if (download_done or upload_done or any(marker in lower for marker in completed)) and not transferring:
            states[appid] = False
            sync_success_seen.discard(appid)
            initializing.discard(appid)
    return sorted(appid for appid, active in states.items() if active)


def shutdown_blockers() -> dict[str, list[int]]:
    return {
        "running_games": running_game_appids(),
        "active_downloads": active_download_appids(),
        "active_cloud_syncs": active_cloud_appids(),
    }


def steam_windows() -> list[dict[str, Any]]:
    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return []
    try:
        result = subprocess.run(
            [hyprctl, "clients", "-j"], capture_output=True, text=True, timeout=5, check=False
        )
        clients = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    windows = []
    for client in clients:
        cls = str(client.get("class", "")).lower()
        initial = str(client.get("initialClass", "")).lower()
        title = str(client.get("title", ""))
        pid = client.get("pid")
        if cls == "steam" or initial == "steam" or (title == "Steam" and pid):
            windows.append(client)
    return windows


def hide_windows() -> int:
    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return 0
    moved = 0
    for window in steam_windows():
        address = window.get("address")
        if not address:
            continue
        result = subprocess.run(
            [
                hyprctl,
                "dispatch",
                "movetoworkspacesilent",
                "special:steam-hidden,address:" + str(address),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        moved += result.returncode == 0
    return moved


def process_start_ticks(pid: int) -> int | None:
    try:
        suffix = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return int(suffix[19])
    except (OSError, ValueError, IndexError):
        return None


def watcher_record() -> dict[str, Any] | None:
    try:
        data = json.loads(HIDE_WATCH_PID.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def valid_watcher_pid() -> int | None:
    record = watcher_record()
    if not record:
        return None
    try:
        pid = int(record["pid"])
        expected_start = int(record["start_ticks"])
        cmdline = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    except (OSError, KeyError, TypeError, ValueError):
        return None
    args = [part.decode(errors="replace") for part in cmdline if part]
    script = str(Path(__file__).resolve())
    if process_start_ticks(pid) != expected_start or script not in args or "hide-watch" not in args:
        return None
    return pid


def hide_watch_running() -> bool:
    if valid_watcher_pid() is not None:
        return True
    HIDE_WATCH_PID.unlink(missing_ok=True)
    return False


def start_hide_watch() -> None:
    if not shutil.which("hyprctl"):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with HIDE_WATCH_LOCK.open("a+") as lock:
        os.chmod(HIDE_WATCH_LOCK, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if hide_watch_running():
            return
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "hide-watch"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        start_ticks = None
        for _ in range(20):
            start_ticks = process_start_ticks(process.pid)
            if start_ticks is not None:
                break
            time.sleep(0.05)
        if start_ticks is None:
            process.terminate()
            return
        temporary = HIDE_WATCH_PID.with_suffix(".tmp")
        temporary.write_text(json.dumps({"pid": process.pid, "start_ticks": start_ticks}) + "\n")
        temporary.replace(HIDE_WATCH_PID)


def stop_hide_watch() -> None:
    pid = valid_watcher_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    HIDE_WATCH_PID.unlink(missing_ok=True)


def run_hide_watch() -> None:
    """Hide Steam windows across updater startup and short client restart gaps."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    seen_steam = False
    absent_since: float | None = None
    try:
        while True:
            windows = steam_windows()
            running = steam_running()
            if windows:
                hide_windows()
            if running or windows:
                seen_steam = True
                absent_since = None
            elif seen_steam:
                absent_since = absent_since or time.monotonic()
                if time.monotonic() - absent_since >= 45:
                    break
            elif time.monotonic() - started_at >= 180:
                break
            time.sleep(1)
    finally:
        if valid_watcher_pid() == os.getpid():
            HIDE_WATCH_PID.unlink(missing_ok=True)


def start_steam(timeout: int) -> dict[str, Any]:
    if steam_running():
        start_hide_watch()
        return {"running": True, "started": False, "pids": steam_main_pids(), "hidden_windows": hide_windows()}
    steam = shutil.which("steam")
    if not steam:
        raise SteamError("The official Steam client is not installed.")
    start_hide_watch()
    workspace_exec = shutil.which("project-workspace-exec")
    if not workspace_exec:
        raise SteamError("project-workspace-exec is required for a safely routed Steam startup.")
    command = [workspace_exec, steam, "-silent"]
    try:
        # Preserve launch diagnostics and require the helper's placement result.
        result = subprocess.run(command, stdin=subprocess.DEVNULL, timeout=45, check=False)
        if result.returncode:
            raise SteamError("Steam startup placement could not be verified; no routing fallback was used.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SteamError("Could not verify Steam startup.") from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if steam_running():
            start_hide_watch()
            time.sleep(2)
            return {
                "running": True,
                "started": True,
                "pids": steam_main_pids(),
                "hidden_windows": hide_windows(),
            }
        time.sleep(1)
    try:
        subprocess.run(
            [steam, "-shutdown"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    raise SteamError(
        f"Steam did not start within {timeout} seconds; a graceful cleanup request was sent."
    )


def stop_steam(
    timeout: int, force: bool, approved: bool, override_active: bool
) -> dict[str, Any]:
    if not steam_running():
        stop_hide_watch()
        return {"running": False, "stopped": False, "reason": "already stopped"}
    blockers = shutdown_blockers()
    active = {name: appids for name, appids in blockers.items() if appids}
    if active and not override_active:
        raise SteamError(
            "Refusing to stop Steam while activity is present: " + json.dumps(active, sort_keys=True)
        )
    if active and (not override_active or not approved):
        raise SteamError("Overriding active Steam work requires --override-active and --approved.")
    if not active:
        time.sleep(1)
        blockers = shutdown_blockers()
        active = {name: appids for name, appids in blockers.items() if appids}
        if active:
            raise SteamError(
                "Refusing to stop Steam because new activity appeared: "
                + json.dumps(active, sort_keys=True)
            )
    steam = shutil.which("steam")
    if not steam:
        raise SteamError("The Steam launcher is unavailable for graceful shutdown.")
    try:
        subprocess.run(
            [steam, "-shutdown"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not steam_running():
            stop_hide_watch()
            return {"running": False, "stopped": True, "forced": False}
        time.sleep(1)
    if not force:
        raise SteamError(
            f"Steam did not stop gracefully within {timeout} seconds; it was not force-killed."
        )
    if not approved:
        raise SteamError("Force shutdown requires both --force and --approved.")
    targets = [(pid, process_start_ticks(pid)) for pid in steam_main_pids()]
    for pid, start_ticks in targets:
        if start_ticks is None or process_start_ticks(pid) != start_ticks or pid not in steam_main_pids():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(5)
    for pid, start_ticks in targets:
        if start_ticks is None or process_start_ticks(pid) != start_ticks or pid not in steam_main_pids():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)
    if not steam_running():
        stop_hide_watch()
    return {"running": steam_running(), "stopped": not steam_running(), "forced": True}


def game_log_marker() -> dict[str, int]:
    path = LOGS / "gameprocess_log.txt"
    try:
        stat = path.stat()
        return {"inode": stat.st_ino, "offset": stat.st_size}
    except OSError:
        return {"inode": 0, "offset": 0}


def launch_marker_path(appid: int) -> Path:
    return STATE_DIR / f"launch-{appid}.json"


def file_marker(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
        return {"inode": stat.st_ino, "offset": stat.st_size}
    except OSError:
        return {"inode": 0, "offset": 0}


def file_text_since(path: Path, marker: dict[str, int]) -> str:
    try:
        stat = path.stat()
        offset = int(marker.get("offset", 0)) if stat.st_ino == int(marker.get("inode", 0)) else 0
        with path.open("rb") as handle:
            handle.seek(min(offset, stat.st_size))
            return handle.read().decode(errors="replace")
    except OSError:
        return ""


def steam_login_ready_text(text: str) -> bool:
    session = text.rsplit("Client version:", 1)[-1]
    return "SetLoginState: Success" in session


def wait_steam_ready(timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if steam_login_ready_text("\n".join(current_session_lines("steamui_login.txt"))):
            return
        hide_windows()
        if not steam_running():
            raise SteamError("Steam exited before login completed.")
        time.sleep(1)
    raise SteamError(f"Steam did not finish login within {timeout} seconds.")


def console_command_acknowledged(text: str, command: str, appid: int) -> bool:
    pattern = re.compile(
        rf"ExecCommandLine:.*['\"]\+{re.escape(command)}['\"].*['\"]{appid}['\"]",
        re.I,
    )
    return bool(pattern.search(text))


def console_command_failed(text: str, command: str) -> bool:
    lower = text.lower()
    return (
        f"unknown command: {command}" in lower
        or f'unknown command "{command}"' in lower
        or (command.lower() in lower and "no subscription" in lower)
        or (command.lower() in lower and "failed to install" in lower)
    )


def request_console_install(appid: int, *, approved: bool, timeout: int = 60) -> dict[str, Any]:
    if not approved:
        raise SteamError("This operation requires the literal --approved guard.")
    if not steam_running():
        start_steam(120)
    wait_steam_ready(120)
    steam = shutil.which("steam")
    if not steam:
        raise SteamError("The Steam launcher is unavailable.")
    console_log = LOGS / "console_log.txt"
    marker = file_marker(console_log)
    try:
        subprocess.Popen(
            [steam, "-console", "+app_install", str(appid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise SteamError("Could not send the hidden install command to Steam.") from exc
    deadline = time.monotonic() + timeout
    observed = ""
    while time.monotonic() < deadline:
        hide_windows()
        observed = file_text_since(console_log, marker)
        if console_command_failed(observed, "app_install"):
            raise SteamError(f"Steam rejected the hidden install command for appid {appid}.")
        if console_command_acknowledged(observed, "app_install", appid):
            unexpected = [window for window in steam_windows() if window.get("title") == "Install"]
            if unexpected:
                hide_windows()
                raise SteamError(
                    "Steam opened an unexpected install dialog; it remains hidden and no GUI fallback was used."
                )
            return {
                "requested": True,
                "acknowledged": True,
                "appid": appid,
                "method": "official Steam client console",
                "hidden_windows": hide_windows(),
            }
        if not steam_running():
            raise SteamError("Steam exited before acknowledging the hidden install command.")
        time.sleep(1)
    raise SteamError(
        f"Steam did not acknowledge the hidden install command for appid {appid} within {timeout} seconds."
    )


def request_url(url: str, *, approved: bool) -> dict[str, Any]:
    if not approved:
        raise SteamError("This operation requires the literal --approved guard.")
    if not steam_running():
        start_steam(120)
    steam = shutil.which("steam")
    if not steam:
        raise SteamError("The Steam launcher is unavailable.")
    launch_match = re.fullmatch(r"steam://rungameid/(\d+)", url)
    if launch_match:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        launch_marker_path(int(launch_match.group(1))).write_text(
            json.dumps(game_log_marker()) + "\n"
        )
    try:
        if launch_match:
            workspace_exec = shutil.which("project-workspace-exec")
            if not workspace_exec:
                raise SteamError("project-workspace-exec is required for verified game placement.")
            result = subprocess.run([workspace_exec, steam, url], stdin=subprocess.DEVNULL,
                                    timeout=195, check=False)
            if result.returncode:
                raise SteamError("Steam game placement could not be verified; no routing fallback was used.")
        else:
            subprocess.Popen([steam, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SteamError("Could not send or verify the request to Steam.") from exc
    time.sleep(3)
    return {"requested": True, "url": url, "hidden_windows": hide_windows()}


def http_json(url: str, timeout: int = 20) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "steam-organizer/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SteamError("The Steam service query failed.") from exc


def strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def store_search(query: str, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"term": query, "l": "english", "cc": "GB"})
    data = http_json(f"https://store.steampowered.com/api/storesearch/?{params}")
    items = data.get("items", []) if isinstance(data, dict) else []
    return [
        {
            "appid": item.get("id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "price": item.get("price"),
            "platforms": item.get("platforms"),
        }
        for item in items[:limit]
    ]


def storage_gb(*requirements: str) -> float | None:
    values: list[float] = []
    pattern = re.compile(r"(?:Storage|Hard Drive):\s*([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB)", re.I)
    for requirement in requirements:
        for amount, unit in pattern.findall(requirement):
            value = float(amount)
            if unit.upper() == "TB":
                value *= 1024
            elif unit.upper() == "MB":
                value /= 1024
            values.append(value)
    return max(values) if values else None


def app_details(appid: int) -> dict[str, Any]:
    params = urllib.parse.urlencode({"appids": appid, "l": "english", "cc": "GB"})
    payload = http_json(f"https://store.steampowered.com/api/appdetails?{params}")
    entry = payload.get(str(appid), {}) if isinstance(payload, dict) else {}
    if not entry.get("success"):
        raise SteamError(f"Steam Store details are unavailable for appid {appid}.")
    data = entry.get("data", {})
    requirements = data.get("pc_requirements", {})
    minimum = strip_html(requirements.get("minimum")) if isinstance(requirements, dict) else ""
    recommended = strip_html(requirements.get("recommended")) if isinstance(requirements, dict) else ""
    categories = [
        {"id": int(item.get("id", 0)), "description": item.get("description")}
        for item in data.get("categories", [])
        if isinstance(item, dict)
    ]
    category_ids = {item["id"] for item in categories}
    controller_support = data.get("controller_support")
    if not controller_support:
        controller_support = "full" if 28 in category_ids else "partial" if 18 in category_ids else None
    genres = [
        {"id": str(item.get("id", "")), "description": item.get("description")}
        for item in data.get("genres", [])
        if isinstance(item, dict)
    ]
    return {
        "appid": appid,
        "name": data.get("name"),
        "type": data.get("type"),
        "short_description": strip_html(data.get("short_description")),
        "is_free": data.get("is_free"),
        "price": data.get("price_overview"),
        "developers": data.get("developers", []),
        "publishers": data.get("publishers", []),
        "platforms": data.get("platforms", {}),
        "controller_support": controller_support,
        "categories": categories,
        "genres": genres,
        "recommendation_count": int((data.get("recommendations") or {}).get("total", 0)),
        "metacritic_score": int((data.get("metacritic") or {}).get("score", 0)),
        "release_date": data.get("release_date", {}),
        "publisher_declared_pc_minimum": minimum,
        "publisher_declared_pc_recommended": recommended,
        "publisher_declared_storage_gb": storage_gb(minimum, recommended),
        "size_note": "Requirements are publisher-declared guidance, not exact depot download size.",
    }


def load_catalog_cache() -> dict[str, Any]:
    try:
        data = json.loads(CATALOG_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"version": CATALOG_CACHE_VERSION, "apps": {}, "proton": {}}
    if not isinstance(data, dict) or data.get("version") != CATALOG_CACHE_VERSION:
        return {"version": CATALOG_CACHE_VERSION, "apps": {}, "proton": {}}
    data.setdefault("apps", {})
    data.setdefault("proton", {})
    return data


def save_catalog_cache(cache: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CATALOG_CACHE.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(CATALOG_CACHE)


def cache_fresh(entry: Any, days: int) -> bool:
    if not isinstance(entry, dict):
        return False
    return time.time() - float(entry.get("fetched_at", 0)) < days * 86400


def sync_catalog(limit: int, refresh: bool, delay: float) -> dict[str, Any]:
    response, source = owned_response()
    owned = sorted(response.get("games", []), key=lambda item: int(item.get("appid", 0)))
    cache = load_catalog_cache()
    pending = [
        game for game in owned
        if refresh or not cache_fresh(cache["apps"].get(str(game.get("appid"))), CATALOG_TTL_DAYS)
    ]
    selected = pending if limit == 0 else pending[:limit]
    updated = 0
    unavailable: list[int] = []
    failures: list[int] = []
    consecutive_failures = 0
    for index, game in enumerate(selected):
        appid = int(game["appid"])
        try:
            details = app_details(appid)
        except SteamError as exc:
            if "Store details are unavailable" in str(exc):
                cache["apps"][str(appid)] = {
                    "fetched_at": int(time.time()),
                    "data": {
                        "appid": appid,
                        "name": game.get("name"),
                        "type": "store_unavailable",
                    },
                }
                unavailable.append(appid)
                consecutive_failures = 0
            else:
                failures.append(appid)
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    break
        else:
            cache["apps"][str(appid)] = {"fetched_at": int(time.time()), "data": details}
            updated += 1
            consecutive_failures = 0
            if updated % 10 == 0:
                save_catalog_cache(cache)
        if delay and index + 1 < len(selected):
            time.sleep(delay)
    save_catalog_cache(cache)
    fresh = sum(cache_fresh(entry, CATALOG_TTL_DAYS) for entry in cache["apps"].values())
    return {
        "owned_games": len(owned),
        "fresh_metadata_entries": fresh,
        "updated": updated,
        "store_unavailable": unavailable,
        "failures": failures,
        "remaining": max(0, len(pending) - updated - len(unavailable) - len(failures)),
        "credential_source": source,
        "cache": str(CATALOG_CACHE),
    }


def proton_compatibility(appid: int, platforms: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    if platforms.get("linux"):
        return {"status": "native_linux", "tier": "native", "source": "Steam Store"}
    key = str(appid)
    entry = cache["proton"].get(key)
    if not cache_fresh(entry, PROTON_TTL_DAYS):
        try:
            summary = http_json(f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json")
        except SteamError:
            summary = None
        cache["proton"][key] = {"fetched_at": int(time.time()), "data": summary}
        entry = cache["proton"][key]
    summary = entry.get("data") if isinstance(entry, dict) else None
    tier = summary.get("tier") if isinstance(summary, dict) else None
    return {
        "status": "proton_community_rating" if tier else "proton_required_unverified",
        "tier": tier or "unverified",
        "confidence": summary.get("confidence") if isinstance(summary, dict) else None,
        "report_count": summary.get("total") if isinstance(summary, dict) else None,
        "source": "ProtonDB (unofficial community endpoint)" if tier else "Steam Store platforms",
    }


def recommendation_score(game: dict[str, Any], mode: str) -> float:
    metadata = game["metadata"]
    categories = {item["id"] for item in metadata.get("categories", [])}
    score = float(metadata.get("metacritic_score", 0))
    recommendations = int(metadata.get("recommendation_count", 0))
    if recommendations:
        score += min(50.0, 10.0 * __import__("math").log10(recommendations + 1))
    if mode != "any":
        score += 30
    if mode in {"couch", "co-op"} and 9 in categories and 2 not in categories:
        score += 25
    if mode == "competitive" and categories & {36, 37, 47, 49} and 9 not in categories:
        score += 15
    if metadata.get("controller_support") == "full":
        score += 5
    elif mode == "couch" and not metadata.get("controller_support"):
        score -= 20
    if not game.get("playtime_hours"):
        score += 3
    return round(score, 1)


def recommend_games(
    mode: str,
    genre: str | None,
    players: int | None,
    max_size_gb: float | None,
    unplayed: bool,
    controller: str,
    linux: str,
    query: str | None,
    limit: int,
) -> dict[str, Any]:
    if players not in (None, 2):
        raise SteamError("Steam Store metadata supports a reliable two-player capability filter only.")
    response, source = owned_response()
    cache = load_catalog_cache()
    games: list[dict[str, Any]] = []
    missing = 0
    for owned in response.get("games", []):
        appid = int(owned.get("appid", 0))
        entry = cache["apps"].get(str(appid))
        if not cache_fresh(entry, CATALOG_TTL_DAYS):
            missing += 1
            continue
        metadata = entry["data"]
        if metadata.get("type") != "game":
            continue
        categories = {int(item["id"]) for item in metadata.get("categories", [])}
        genres = [str(item.get("description", "")) for item in metadata.get("genres", [])]
        if mode != "any" and not categories & MODE_CATEGORY_IDS[mode]:
            continue
        if players == 2 and not categories & TWO_PLAYER_CATEGORY_IDS:
            continue
        if genre:
            genre_needle = genre.casefold()
            descriptive_text = " ".join(
                [str(owned.get("name", "")), metadata.get("short_description", "")]
            ).casefold()
            if not any(genre_needle in item.casefold() for item in genres) and genre_needle not in descriptive_text:
                continue
        playtime = round(int(owned.get("playtime_forever", 0)) / 60, 1)
        if unplayed and playtime:
            continue
        size = metadata.get("publisher_declared_storage_gb")
        if max_size_gb is not None and (size is None or float(size) > max_size_gb):
            continue
        support = metadata.get("controller_support")
        if not support:
            support = "full" if 28 in categories else "partial" if 18 in categories else "none_declared"
            if support != "none_declared":
                metadata["controller_support"] = support
        if controller != "any" and support != controller:
            continue
        native = bool((metadata.get("platforms") or {}).get("linux"))
        if linux == "native" and not native:
            continue
        if linux == "proton" and native:
            continue
        if query:
            haystack = " ".join([str(owned.get("name", "")), metadata.get("short_description", ""), *genres])
            if query.casefold() not in haystack.casefold():
                continue
        game = {
            "appid": appid,
            "name": owned.get("name") or metadata.get("name"),
            "ownership": "self_owned",
            "playtime_hours": playtime,
            "last_played": owned.get("rtime_last_played"),
            "genres": genres,
            "multiplayer_modes": [
                str(item.get("description"))
                for item in metadata.get("categories", [])
                if int(item.get("id", 0)) in MULTIPLAYER_CATEGORY_IDS
            ],
            "controller_support": support,
            "publisher_declared_storage_gb": size,
            "metacritic_score": metadata.get("metacritic_score") or None,
            "steam_recommendation_count": metadata.get("recommendation_count", 0),
            "short_description": metadata.get("short_description"),
            "platforms": metadata.get("platforms", {}),
            "metadata": metadata,
        }
        game["recommendation_score"] = recommendation_score(game, mode)
        games.append(game)
    games.sort(key=lambda item: (-item["recommendation_score"], item["name"].casefold()))
    selected = games[:limit]
    for game in selected:
        game["compatibility"] = proton_compatibility(game["appid"], game["platforms"], cache)
        game.pop("metadata", None)
    save_catalog_cache(cache)
    free = max((shutil.disk_usage(path).free for path in library_paths() if path.exists()), default=0)
    return {
        "filters": {
            "mode": mode,
            "genre": genre,
            "players": players,
            "max_size_gb": max_size_gb,
            "unplayed": unplayed,
            "controller": controller,
            "linux": linux,
            "query": query,
        },
        "matched": len(games),
        "returned": len(selected),
        "games": selected,
        "library_free_gb": round(free / (1024 ** 3), 1),
        "credential_source": source,
        "metadata_missing_or_stale": missing,
        "scope_note": (
            "Recommendations include confirmed self-owned games only. Steam categories prove the "
            "listed multiplayer mode, not an exact maximum player count. Storage is publisher-declared."
        ),
    }


def account_id64() -> int:
    loginusers = STEAM_ROOT / "config/loginusers.vdf"
    if loginusers.exists():
        users = parse_vdf(loginusers).get("users", {})
        if isinstance(users, dict):
            recent = [
                int(steamid)
                for steamid, data in users.items()
                if steamid.isdigit() and isinstance(data, dict) and data.get("MostRecent") == "1"
            ]
            if len(recent) == 1:
                return recent[0]
            if len(recent) > 1:
                raise SteamError("Steam login metadata marks multiple accounts as most recent.")
            available = [int(steamid) for steamid in users if steamid.isdigit()]
            if len(available) == 1:
                return available[0]
            if len(available) > 1:
                raise SteamError("Multiple Steam login accounts are present and none is unambiguously active.")
    accounts = [
        int(path.name)
        for path in USERDATA.iterdir()
        if path.is_dir() and path.name.isdigit()
    ] if USERDATA.exists() else []
    if len(accounts) == 1:
        return STEAM64_BASE + accounts[0]
    if not accounts:
        raise SteamError("No local Steam account metadata was found.")
    raise SteamError("Multiple Steam accounts are present; the active account is ambiguous.")


def secret_tool_path() -> str | None:
    configured = os.environ.get("STEAM_SECRET_TOOL")
    if configured and Path(configured).is_file():
        return configured
    available = shutil.which("secret-tool")
    if available:
        return available
    candidates = sorted(Path("/nix/store").glob("*-libsecret-*/bin/secret-tool"))
    return str(candidates[-1]) if candidates else None


def steam_api_key() -> tuple[str, str]:
    for variable in ("STEAM_WEB_API_KEY", "STEAM_API_KEY"):
        key = os.environ.get(variable)
        if key:
            return key, variable
    secret_tool = secret_tool_path()
    if secret_tool:
        try:
            result = subprocess.run(
                [secret_tool, "lookup", *SECRET_ATTRIBUTES],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        key = result.stdout.strip() if result and result.returncode == 0 else ""
        if key:
            return key, "desktop Secret Service"
    raise SteamError(
        "Owned-library queries need a Steam Web API key. Store it in the desktop "
        "Secret Service for steam-organizer or set STEAM_WEB_API_KEY."
    )


def owned_response() -> tuple[dict[str, Any], str]:
    key, source = steam_api_key()
    params = urllib.parse.urlencode(
        {
            "key": key,
            "steamid": account_id64(),
            "include_appinfo": "true",
            "include_played_free_games": "true",
            "format": "json",
        }
    )
    data = http_json(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?{params}")
    response = data.get("response", {}) if isinstance(data, dict) else {}
    if not isinstance(response, dict) or "games" not in response:
        raise SteamError(
            "Steam returned no owned-game list. Check the API key and Game details privacy."
        )
    return response, source


def public_game(game: dict[str, Any]) -> dict[str, Any]:
    return {
        "appid": game.get("appid"),
        "name": game.get("name"),
        "playtime_hours": round(int(game.get("playtime_forever", 0)) / 60, 1),
        "last_played": game.get("rtime_last_played"),
    }


def owned_games(search: str | None, limit: int, offset: int) -> dict[str, Any]:
    response, source = owned_response()
    games = response.get("games", [])
    if search:
        needle = search.casefold()
        games = [game for game in games if needle in str(game.get("name", "")).casefold()]
    games.sort(key=lambda game: str(game.get("name", "")).casefold())
    page = games[offset : offset + limit]
    return {
        "total_api_visible": response.get("game_count"),
        "matched": len(games),
        "offset": offset,
        "limit": limit,
        "credential_source": source,
        "games": [public_game(game) for game in page],
        "scope_note": "Steam Web API self-owned games; Steam Families entitlements are absent.",
    }


def ownership(appid: int) -> dict[str, Any]:
    response, source = owned_response()
    game = next(
        (item for item in response.get("games", []) if int(item.get("appid", 0)) == appid),
        None,
    )
    installed = next((item for item in manifests() if item["appid"] == appid), None)
    cache_present = (STEAM_ROOT / "appcache/librarycache" / str(appid)).is_dir()
    if game:
        classification = "self_owned"
        note = "The official Steam Web API lists this game as owned by the active account."
    elif cache_present:
        classification = "not_self_owned_cache_present"
        note = (
            "The game is absent from the account-owned API list but present in Steam's local "
            "cache. It may be supplied by Steam Family; cache presence alone cannot prove that."
        )
    else:
        classification = "not_self_owned_no_local_cache"
        note = "The game is absent from both the account-owned API list and local library cache."
    return {
        "appid": appid,
        "classification": classification,
        "credential_source": source,
        "owned_game": public_game(game) if game else None,
        "installed": bool(installed),
        "cache_present": cache_present,
        "note": note,
    }


def wait_install(appid: int, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_report: tuple[int, int, int] | None = None
    while time.monotonic() < deadline:
        game = next((item for item in manifests() if item["appid"] == appid), None)
        if game:
            current = (
                int(game["state_flags"]),
                int(game["bytes_downloaded"]),
                int(game["bytes_to_download"]),
            )
            if current != last_report:
                downloaded, total = current[1], current[2]
                progress = round(downloaded / total * 100, 1) if total else None
                print(
                    json.dumps(
                        {
                            "appid": appid,
                            "state_flags": current[0],
                            "downloaded": human_bytes(downloaded),
                            "total": human_bytes(total),
                            "progress_percent": progress,
                        }
                    ),
                    file=sys.stderr,
                    flush=True,
                )
                last_report = current
            if game["fully_installed"]:
                return game
        if not steam_running():
            raise SteamError("Steam exited before the installation completed.")
        time.sleep(5)
    raise SteamError(f"Installation of appid {appid} did not complete within {timeout} seconds.")


def parse_game_lifecycle(text: str, appid: int) -> tuple[bool | None, int, int, int]:
    state: bool | None = None
    starts = 0
    stops = 0
    matches = 0
    tracked: set[int] = set()
    app_pattern = re.compile(rf"(?:AppID|appid)[^0-9]*{appid}(?![0-9])", re.I)
    add_pid = re.compile(r"adding PID (\d+)", re.I)
    remove_pid = re.compile(r"no longer tracking PID (\d+)", re.I)
    for line in text.splitlines():
        if "Client version:" in line:
            state = None
            starts = 0
            stops = 0
            matches = 0
            tracked.clear()
            continue
        if not app_pattern.search(line):
            continue
        matches += 1
        lower = line.lower()
        added = add_pid.search(line)
        removed = remove_pid.search(line)
        if added:
            tracked.add(int(added.group(1)))
            starts += 1
            state = True
        elif (
            "app running" in lower
            or "game process added" in lower
            or ("tracking pid" in lower and "no longer tracking" not in lower)
        ):
            starts += 1
            state = True
        if removed:
            tracked.discard(int(removed.group(1)))
            stops += 1
            state = bool(tracked)
        elif "game process removed" in lower or "app stopped" in lower:
            stops += 1
            state = bool(tracked)
        elif "state changed" in lower and "fully installed" in lower and "app running" not in lower:
            stops += 1
            state = bool(tracked)
    return state, starts, stops, matches


def parse_game_running_state(text: str, appid: int) -> tuple[bool | None, int]:
    state, _, _, matches = parse_game_lifecycle(text, appid)
    return state, matches


def running_game_log_appids() -> list[int]:
    session = "\n".join(current_session_lines("gameprocess_log.txt"))
    appids = {int(value) for value in re.findall(r"(?:AppID|appid)[^0-9]*(\d+)", session, re.I)}
    return sorted(
        appid for appid in appids if appid not in (0, 7, 760) and parse_game_lifecycle(session, appid)[0]
    )


def app_running_state(appid: int) -> tuple[bool | None, int]:
    path = LOGS / "gameprocess_log.txt"
    if not path.exists():
        return None, 0
    try:
        return parse_game_running_state(path.read_text(errors="replace"), appid)
    except OSError:
        return None, 0


def wait_game(appid: int, timeout: int, *, startup_timeout: int | None = None) -> dict[str, Any]:
    marker_path = launch_marker_path(appid)
    try:
        marker = json.loads(marker_path.read_text()) if marker_path.exists() else game_log_marker()
    except (OSError, json.JSONDecodeError):
        marker = game_log_marker()
    log_path = LOGS / "gameprocess_log.txt"
    inode = int(marker.get("inode", 0))
    offset = int(marker.get("offset", 0))
    observed = ""
    initially_running = appid in running_game_appids()
    seen_running = initially_running
    process_seen = initially_running
    process_absent_since: float | None = None
    deadline = time.monotonic() + timeout
    startup_deadline = time.monotonic() + startup_timeout if startup_timeout is not None else None
    try:
        while time.monotonic() < deadline:
            try:
                stat = log_path.stat()
                if stat.st_ino != inode or stat.st_size < offset:
                    inode = stat.st_ino
                    offset = 0
                    observed = ""
                with log_path.open("rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                    offset = handle.tell()
                if chunk:
                    observed += chunk.decode(errors="replace")
            except OSError:
                pass
            state, starts, stops, _ = parse_game_lifecycle(observed, appid)
            current_running = running_game_appids()
            if appid in current_running:
                process_seen = True
                process_absent_since = None
            elif process_seen:
                process_absent_since = process_absent_since or time.monotonic()
            if starts or state is True or appid in current_running:
                seen_running = True
            if seen_running and stops and state is False and appid not in current_running:
                return {"appid": appid, "started": True, "exited": True}
            if process_seen and process_absent_since is not None:
                if time.monotonic() - process_absent_since >= 5:
                    return {"appid": appid, "started": True, "exited": True}
            if not seen_running and startup_deadline is not None and time.monotonic() >= startup_deadline:
                raise SteamError(f"Game appid {appid} was not observed starting within {startup_timeout} seconds.")
            if not steam_running() and not seen_running:
                raise SteamError("Steam exited before the game was observed running.")
            time.sleep(1)
        raise SteamError(f"Game appid {appid} did not exit within {timeout} seconds.")
    finally:
        marker_path.unlink(missing_ok=True)


def settle(quiet_seconds: int, timeout: int) -> dict[str, Any]:
    watched = [LOGS / "cloud_log.txt", LOGS / "content_log.txt"]

    def signature() -> tuple[tuple[int, int], ...]:
        values = []
        for path in watched:
            try:
                stat = path.stat()
                values.append((stat.st_size, stat.st_mtime_ns))
            except OSError:
                values.append((0, 0))
        return tuple(values)

    last = signature()
    quiet_since = time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        current = signature()
        if current != last:
            last = current
            quiet_since = time.monotonic()
        if time.monotonic() - quiet_since >= quiet_seconds:
            return {"settled": True, "quiet_seconds": quiet_seconds}
    raise SteamError(f"Steam activity did not settle within {timeout} seconds.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("libraries")
    installed = sub.add_parser("installed")
    installed.add_argument("--search")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)

    details = sub.add_parser("details")
    details.add_argument("appid", type=int)

    owned = sub.add_parser("owned")
    owned.add_argument("--search")
    owned.add_argument("--limit", type=int, default=50)
    owned.add_argument("--offset", type=int, default=0)

    ownership_parser = sub.add_parser("ownership")
    ownership_parser.add_argument("appid", type=int)

    catalog_sync = sub.add_parser("catalog-sync")
    catalog_sync.add_argument("--limit", type=int, default=50, help="0 refreshes every pending game")
    catalog_sync.add_argument("--refresh", action="store_true")
    catalog_sync.add_argument("--delay", type=float, default=1.0)

    recommend = sub.add_parser("recommend")
    recommend.add_argument(
        "--mode", choices=["any", "couch", "co-op", "online", "competitive", "singleplayer"], default="any"
    )
    recommend.add_argument("--genre")
    recommend.add_argument("--players", type=int)
    recommend.add_argument("--max-size-gb", type=float)
    recommend.add_argument("--unplayed", action="store_true")
    recommend.add_argument("--controller", choices=["any", "full", "partial"], default="any")
    recommend.add_argument("--linux", choices=["any", "native", "proton"], default="any")
    recommend.add_argument("--query")
    recommend.add_argument("--limit", type=int, default=20)

    start = sub.add_parser("start")
    start.add_argument("--timeout", type=int, default=120)
    sub.add_parser("hide")

    stop = sub.add_parser("stop")
    stop.add_argument("--timeout", type=int, default=90)
    stop.add_argument("--force", action="store_true")
    stop.add_argument("--override-active", action="store_true")
    stop.add_argument("--approved", action="store_true")

    for name in ("request-install", "request-launch", "request-verify", "request-uninstall"):
        action = sub.add_parser(name)
        action.add_argument("appid", type=int)
        action.add_argument("--approved", action="store_true")

    wait_install_parser = sub.add_parser("wait-install")
    wait_install_parser.add_argument("appid", type=int)
    wait_install_parser.add_argument("--timeout", type=int, default=86400)

    wait_game_parser = sub.add_parser("wait-game")
    wait_game_parser.add_argument("appid", type=int)
    wait_game_parser.add_argument("--timeout", type=int, default=43200)

    settle_parser = sub.add_parser("settle")
    settle_parser.add_argument("--quiet-seconds", type=int, default=15)
    settle_parser.add_argument("--timeout", type=int, default=180)
    sub.add_parser("hide-watch", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "status":
            emit(
                {
                    "running": steam_running(),
                    "pids": steam_main_pids(),
                    "windows": [
                        {
                            "class": item.get("class"),
                            "title": item.get("title"),
                            "workspace": item.get("workspace", {}).get("name"),
                        }
                        for item in steam_windows()
                    ],
                    "installed_games": len(manifests()),
                    "shutdown_blockers": shutdown_blockers(),
                }
            )
        elif args.command == "libraries":
            result = []
            games = manifests()
            for path in library_paths():
                usage = shutil.disk_usage(path) if path.exists() else None
                result.append(
                    {
                        "path": str(path),
                        "exists": path.exists(),
                        "installed_games": sum(game["library"] == str(path) for game in games),
                        "free_bytes": usage.free if usage else None,
                        "free": human_bytes(usage.free) if usage else None,
                        "total_bytes": usage.total if usage else None,
                        "total": human_bytes(usage.total) if usage else None,
                    }
                )
            emit(result)
        elif args.command == "installed":
            games = manifests()
            if args.search:
                needle = args.search.casefold()
                games = [game for game in games if needle in str(game["name"]).casefold()]
            emit(games)
        elif args.command == "search":
            emit(store_search(args.query, max(1, min(args.limit, 100))))
        elif args.command == "details":
            emit(app_details(args.appid))
        elif args.command == "owned":
            emit(owned_games(args.search, max(1, min(args.limit, 500)), max(0, args.offset)))
        elif args.command == "ownership":
            emit(ownership(args.appid))
        elif args.command == "catalog-sync":
            emit(sync_catalog(max(0, args.limit), args.refresh, max(0.0, args.delay)))
        elif args.command == "recommend":
            emit(
                recommend_games(
                    args.mode,
                    args.genre,
                    args.players,
                    args.max_size_gb,
                    args.unplayed,
                    args.controller,
                    args.linux,
                    args.query,
                    max(1, min(args.limit, 100)),
                )
            )
        elif args.command == "start":
            emit(start_steam(max(10, args.timeout)))
        elif args.command == "hide":
            emit({"hidden_windows": hide_windows()})
        elif args.command == "stop":
            emit(
                stop_steam(
                    max(10, args.timeout),
                    args.force,
                    args.approved,
                    args.override_active,
                )
            )
        elif args.command.startswith("request-"):
            action = args.command.removeprefix("request-")
            if action == "install":
                emit(request_console_install(args.appid, approved=args.approved))
            else:
                routes = {
                    "launch": "rungameid",
                    "verify": "validate",
                    "uninstall": "uninstall",
                }
                emit(request_url(f"steam://{routes[action]}/{args.appid}", approved=args.approved))
        elif args.command == "wait-install":
            emit(wait_install(args.appid, max(10, args.timeout)))
        elif args.command == "wait-game":
            emit(wait_game(args.appid, max(10, args.timeout)))
        elif args.command == "settle":
            emit(settle(max(1, args.quiet_seconds), max(args.quiet_seconds, args.timeout)))
        elif args.command == "hide-watch":
            run_hide_watch()
        return 0
    except SteamError as exc:
        print(f"steam-organizer: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
