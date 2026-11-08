#!/usr/bin/env python3
"""Lid-only display transitions; logind retains ownership of suspend policy."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


PANEL = "eDP-1"


def hypr(*args):
    return subprocess.run(["hyprctl", *args], check=True, capture_output=True,
                          text=True, timeout=4).stdout


def monitors():
    return json.loads(hypr("monitors", "all", "-j"))


def wait_monitors(predicate):
    # Monitor keywords return before the next compositor output transaction.
    deadline = time.monotonic() + 3
    while True:
        current = monitors()
        if predicate(current):
            return current
        if time.monotonic() >= deadline:
            raise RuntimeError("Display transition did not settle; recovery will retry")
        time.sleep(.05)


def lid_closed():
    states = list(Path("/proc/acpi/button/lid").glob("*/state"))
    if not states:
        raise RuntimeError("Lid state unavailable; leaving displays unchanged")
    return any(p.read_text().split()[-1] == "closed" for p in states)


def headless_busy():
    try:
        return Path("/run/headless-mode/state").read_text().strip() != "off"
    except FileNotFoundError:
        return False


def enabled(m):
    return not m.get("disabled", False)


def workspace_selector(name):
    return name if name.isdecimal() or name.startswith("special:") else "name:" + name


def rule(m, position=None, mirror=False):
    # Keep the current mode, scale and rotation, rather than resetting to a
    # preferred mode on every lid event. Names come only from compositor IPC.
    name = m["name"]
    if any(c in name for c in ",;\n\r"):
        raise ValueError("Unsafe output name")
    # Hyprland IPC reports native pixel dimensions, not transformed size.
    width, height = m["width"], m["height"]
    mode = f'{width}x{height}@{m["refreshRate"]}'
    pos = position or f'{m["x"]}x{m["y"]}'
    result = f'{name},{mode},{pos},{m["scale"]},transform,{m.get("transform", 0)}'
    if mirror and m.get("mirrorOf", "none") != "none":
        result += f',mirror,{m.get("mirrorTarget", m["mirrorOf"])}'
    return result


class Clamshell:
    def __init__(self, runtime, instance):
        self.path = runtime / "clamshell-mode" / "state.json"
        self.instance = instance

    def load(self):
        if not self.path.exists():
            return None
        state = json.loads(self.path.read_text())
        # Old compositor instances must never replay workspace/layout commands
        # into a new session. Its normal monitor rules already enable the panel.
        if state["instance"] != self.instance:
            self.path.unlink()
            return None
        return state

    def save(self, outputs):
        # IPC mirrorOf is a monitor ID, whereas monitor rules need its name.
        names = {str(m.get("id")): m["name"] for m in outputs}
        for m in outputs:
            target = str(m.get("mirrorOf", "none"))
            if target != "none":
                m["mirrorTarget"] = names.get(target, target)
        names = {m["name"] for m in outputs}
        workspaces = [{"name": w["name"], "monitor": w["monitor"]}
                      for w in json.loads(hypr("workspaces", "-j")) if w["monitor"] in names]
        self.store({"instance": self.instance, "outputs": outputs, "workspaces": workspaces})

    def store(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(self.path)

    def restore(self, state):
        state["restoring"] = True
        self.store(state)
        current = monitors()
        if not any(enabled(m) for m in current):
            # Hyprland's unsafe zero-output state can stop native monitor-rule
            # transactions. A temporary headless output supplies a render clock
            # so the real panel can be enabled. Journal it before creating it;
            # retries clean up this exact task-owned output, never another one.
            recovery = state.setdefault("recoveryOutput", "clamshell-recovery-" + uuid.uuid4().hex[:8])
            self.store(state)
            if not any(m["name"] == recovery for m in current):
                hypr("output", "create", "headless", recovery)
            current = wait_monitors(lambda ms: any(m["name"] == recovery and enabled(m) for m in ms))
        connected = {m["name"] for m in current}
        external = any(m["name"] not in (PANEL, state.get("recoveryOutput")) and enabled(m) for m in current)
        panel = next(m for m in state["outputs"] if m["name"] == PANEL)
        # Panel first: failures in optional external/workspace restoration must
        # never leave the user with no screen. Keep the journal until success.
        hypr("keyword", "monitor", rule(panel, None if external else "0x0"))
        settled = wait_monitors(lambda ms: any(m["name"] == PANEL and enabled(m)
                                               and m.get("mirrorOf", "none") == "none" for m in ms))
        if not next(m for m in settled if m["name"] == PANEL).get("dpmsStatus", True):
            hypr("dispatch", "dpms", f"on {PANEL}")
            wait_monitors(lambda ms: any(m["name"] == PANEL and m.get("dpmsStatus", True) for m in ms))
        for m in state["outputs"]:
            if m["name"] != PANEL and m["name"] in connected:
                hypr("keyword", "monitor", rule(m, mirror=True))
        expected = {m["name"]: m.get("mirrorOf", "none") for m in state["outputs"]
                    if m["name"] != PANEL and m["name"] in connected}
        wait_monitors(lambda ms: all(any(m["name"] == name and enabled(m)
                                         and m.get("mirrorOf", "none") == mirror for m in ms)
                                    for name, mirror in expected.items()))
        surviving = {w["name"] for w in json.loads(hypr("workspaces", "-j"))}
        for w in state.get("workspaces", []):
            if w["monitor"] in connected and w["name"] in surviving:
                hypr("dispatch", "moveworkspacetomonitor",
                     f'{workspace_selector(w["name"])} {w["monitor"]}')
        for m in state["outputs"]:
            if m["name"] not in connected:
                continue
            workspace = m.get("activeWorkspace", {}).get("name", "")
            if workspace and workspace != "-1" and workspace in surviving:
                hypr("dispatch", "focusmonitor", m["name"])
                hypr("dispatch", "workspace", workspace_selector(workspace))
        focused = next((m["name"] for m in state["outputs"]
                        if m.get("focused") and m["name"] in connected), PANEL)
        hypr("dispatch", "focusmonitor", focused)
        if state.get("recoveryOutput") and state["recoveryOutput"] in connected:
            hypr("output", "remove", state["recoveryOutput"])
            wait_monitors(lambda ms: not any(m["name"] == state["recoveryOutput"] for m in ms))
        self.path.unlink()

    def handle(self, action):
        state = self.load()
        # Share the folded-mode lock AND defer to its root state. Clamshell
        # never unloads ISH, inhibits touch/pen, or changes keyboard devices.
        if headless_busy():
            return
        closed = lid_closed()
        if state and state.get("panelOnly"):
            if not closed:
                hypr("dispatch", "dpms", f"on {PANEL}")
                self.path.unlink()
            elif any(m["name"] == PANEL and enabled(m) and m.get("dpmsStatus", True)
                     for m in monitors()):
                # Retry an interrupted/failed close without replaying layouts.
                hypr("dispatch", "dpms", f"off {PANEL}")
            return
        if state:
            if state.get("restoring") or not closed or not any(m["name"] not in (PANEL, state.get("recoveryOutput"))
                                     and enabled(m) for m in monitors()):
                self.restore(state)
            return
        # Hotplug/startup checks recover only: they never enter clamshell.
        # Only an actual close event can blank the panel or enter clamshell.
        if action != "close" or not closed:
            return
        outputs = [m for m in monitors() if enabled(m)]
        panel = next((m for m in outputs if m["name"] == PANEL), None)
        externals = [m for m in outputs if m["name"] != PANEL]
        if not panel:
            return
        if not externals:
            # Agents can now defer logind's suspend. Blank without disabling the
            # sole render output, and journal so reopen/recovery wakes it again.
            self.store({"instance": self.instance, "panelOnly": True})
            hypr("dispatch", "dpms", f"off {PANEL}")
            return
        self.save(outputs)
        try:
            for index, m in enumerate(externals):
                # A mirror cannot survive losing its source. Convert it to a
                # real output before disabling the panel. Preserve other screens.
                hypr("keyword", "monitor", rule(m, "0x0" if index == 0 else "auto-right"))
            wait_monitors(lambda ms: all(any(m["name"] == saved["name"] and enabled(m)
                                              and m.get("mirrorOf", "none") == "none" for m in ms)
                                         for saved in externals))
            if not lid_closed() or not any(m["name"] != PANEL and enabled(m) for m in monitors()):
                self.restore(self.load())
                return
            hypr("keyword", "monitor", f"{PANEL},disable")
            wait_monitors(lambda ms: not any(m["name"] == PANEL and enabled(m) for m in ms)
                          and any(m["name"] != PANEL and enabled(m) for m in ms))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            self.restore(self.load())
            raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("close", "open", "check"):
        raise SystemExit("usage: clamshell-mode {close|open|check}")
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    lock = runtime / "headless-mode" / "lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        Clamshell(runtime, os.environ["HYPRLAND_INSTANCE_SIGNATURE"]).handle(sys.argv[1])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"clamshell-mode: {error}", file=sys.stderr)
        sys.exit(1)
