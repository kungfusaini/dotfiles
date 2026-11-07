"""One-shot playback selection, called only by the Sony priming coordinator."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SONY_CARD = "bluez_card.58_18_62_B5_3F_E4"
CONTROLLER = "98:B6:E9:7C:21:83"
GAMING_EXECUTABLES = {
    "pegasus-fe", ".pegasus-fe-wrapped", "pcsx2-qt", ".pcsx2-qt-wrapped",
    "Ryujinx", ".Ryujinx-wrapped", "ryujinx", "SymphonyRecomp",
    "symphony-recomp", ".symphony-recomp-wrapped",
}


def is_gaming_process(executable, environment, arguments=()):
    if executable in GAMING_EXECUTABLES:
        return True
    if executable == "dotnet" and any(
        arg.startswith("/nix/store/") and arg.endswith("/lib/symphony-recomp/sotn.dll")
        for arg in arguments
    ):
        return True
    return any(value.isdigit() and int(value) > 0 for value in (
        environment.get("SteamAppId", ""), environment.get("SteamGameId", "")
    ))


def gaming_active(proc=Path("/proc")):
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            executable = Path(os.readlink(entry / "exe")).name
            # Read only the two public Steam identity fields; never log environments.
            environment = {}
            for field in (entry / "environ").read_bytes().split(b"\0"):
                if field.startswith((b"SteamAppId=", b"SteamGameId=")):
                    key, value = field.decode(errors="replace").split("=", 1)
                    environment[key] = value
            arguments = [arg.decode(errors="replace") for arg in (entry / "cmdline").read_bytes().split(b"\0")] if executable == "dotnet" else ()
            if is_gaming_process(executable, environment, arguments):
                return True
        except (OSError, ValueError):
            continue
    return False


def snapshot(objects):
    cards = [obj for obj in objects if obj.get("info", {}).get("props", {}).get("device.name") == SONY_CARD]
    if len(cards) != 1:
        return None
    card = cards[0]
    info = card["info"]
    params = info.get("params", {})
    profiles = params.get("Profile", [])
    if len(profiles) != 1:
        return None
    # Be conservative: an active recording stream, even on the laptop mic,
    # takes priority over changing a Bluetooth playback profile.
    capturing = any(
        obj.get("info", {}).get("props", {}).get("media.class") == "Stream/Input/Audio"
        and obj["info"].get("state", "running") == "running"
        for obj in objects
    )
    serial = str(info.get("props", {}).get("object.serial", card["id"]))
    core = next((obj.get("info", {}) for obj in objects if obj.get("type") == "PipeWire:Interface:Core"), {})
    if core.get("cookie") is not None:
        serial = str(core["cookie"]) + ":" + serial
    return {
        "card": card["id"], "serial": serial,
        "current": profiles[0], "profiles": params.get("EnumProfile", []), "capturing": capturing,
    }


def decide(view, gaming, restore=False, pending_restore=False):
    if view is None:
        return {"reason": "headset unavailable"}
    # Off/unknown is an intentional cancellation, even during a recording or
    # incomplete profile enumeration. Never retain stale priming intent here.
    if not view["current"].get("name", "").startswith(("a2dp-", "headset-")):
        return {"reason": "playback not selected"}
    name = "a2dp-sink-aac" if gaming else "a2dp-sink"
    targets = [p for p in view["profiles"] if p.get("name") == name and p.get("available") != "no"]
    if len(targets) != 1:
        return {"reason": "required playback profile unavailable", "pending_restore": restore or pending_restore}
    target = targets[0]
    if view["current"]["index"] == target["index"]:
        return {"reason": "already selected"}
    if view["capturing"]:
        return {"reason": "recording has priority", "pending_restore": restore or pending_restore}
    if view["current"].get("name", "").startswith("headset-") and not (restore or pending_restore):
        return {"reason": "leave headset profile to WirePlumber"}
    return {"reason": "gaming AAC" if gaming else "normal LDAC", "target": target["index"]}


def request_allowed(state, key, now):
    if state.get("request_key") != key:
        return True
    return state.get("attempts", 0) < 3 and now - state.get("requested_at", 0) >= 10


def run(command):
    return subprocess.check_output(command, text=True, timeout=5)


def reconcile(state, restore=False, now=None):
    now = time.monotonic() if now is None else now
    view = snapshot(json.loads(run(["pw-dump"])))
    if view is None:
        # --begin-priming registers the current PipeWire connection before any
        # HFP transition. Retain a first restore request only in that scope;
        # a newly observed connection serial will discard it.
        if restore and state.get("serial"):
            return {**state, "pending_restore": True}
        return state
    if state.get("serial") != view["serial"]:
        state = {}
        # An explicit request belongs to the registered connection, not an
        # HFP profile that appeared after a reconnect or PipeWire restart.
        restore = False
    connected = "Connected: yes" in run(["bluetoothctl", "info", CONTROLLER])
    gaming = connected and gaming_active()
    decision = decide(view, gaming, restore, state.get("pending_restore", False))
    updated = {**state, "serial": view["serial"],
               "pending_restore": decision.get("pending_restore", restore or state.get("pending_restore", False))}
    if "target" not in decision:
        if decision["reason"] in ("already selected", "playback not selected"):
            # Acknowledged playback, or an intentional off/unknown profile,
            # completes/cancels restoration and its request history.
            return {"serial": view["serial"], "pending_restore": False}
        # Recording/profile enumeration can be transient. Neither grants new
        # retry budget nor cancels an outstanding priming restoration.
        return updated
    # Keep explicit priming restoration intent through every intervening poll,
    # including cooldown, until the graph acknowledges an A2DP profile.
    updated["pending_restore"] = restore or state.get("pending_restore", False)
    key = [view["serial"], view["current"]["index"], decision["target"]]
    if not request_allowed(state, key, now):
        return {**state, **updated}
    # Re-read immediately before selection to avoid overriding a newly started
    # microphone or using an object ID that disappeared during detection.
    fresh = snapshot(json.loads(run(["pw-dump"])))
    if fresh is None or fresh["serial"] != view["serial"]:
        return updated
    rechecked = decide(fresh, gaming, restore, state.get("pending_restore", False))
    if rechecked.get("target") != decision["target"]:
        if rechecked["reason"] in ("already selected", "playback not selected"):
            return {"serial": fresh["serial"], "pending_restore": False}
        return {**updated, "pending_restore": rechecked.get("pending_restore", updated["pending_restore"])}
    attempts = state.get("attempts", 0) + 1 if state.get("request_key") == key else 1
    updated.update(request_key=key, attempts=attempts, requested_at=now,
                   pending_restore=restore or state.get("pending_restore", False))
    try:
        run(["wpctl", "set-profile", str(fresh["card"]), str(decision["target"])])
        print("sony-headset-playback: " + decision["reason"], flush=True)
    except (OSError, subprocess.SubprocessError):
        # Retain the bounded retry state; no adapter resets or fallback codecs.
        print("sony-headset-playback: profile selection failed; retry is bounded", flush=True)
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--restore-playback", action="store_true", help="Return from priming to playback, deferring while recording")
    modes.add_argument("--begin-priming", action="store_true", help="Register connection identity before priming; defer while recording")
    args = parser.parse_args()
    directory = Path(os.environ["XDG_RUNTIME_DIR"]) / "sony-headset-prime"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "playback.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 2 if args.begin_priming else 0
        path = directory / "playback.json"
        try:
            state = json.loads(path.read_text())
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        # Register restoration intent before any command that can fail. Keep
        # it scoped to the serial remembered before HFP priming started.
        intent = {**state, "pending_restore": True} if args.restore_playback and state.get("serial") else state
        try:
            if args.begin_priming:
                view = snapshot(json.loads(run(["pw-dump"])))
                if view is None or view["capturing"]:
                    return 2
                updated = {"serial": view["serial"], "pending_restore": False}
            else:
                updated = reconcile(intent, args.restore_playback)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            # A disconnected/restarting graph is not permission to reset devices,
            # or to lose the first connection-scoped restoration request.
            if args.begin_priming:
                return 2
            updated = intent
        if updated != state:
            fd, temporary = tempfile.mkstemp(dir=directory, prefix=".playback-")
            with os.fdopen(fd, "w") as stream:
                json.dump(updated, stream)
            os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
