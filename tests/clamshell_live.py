#!/usr/bin/env python3
"""Opt-in real IPC test inside Hyprland nested in a headless labwc.

Run under dbus-run-session. No live desktop sockets or input devices are used.
Only the physical lid reading is simulated; display commands use real Hyprland.
Logs remain in the printed temporary directory.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from unittest.mock import patch


def wait_for(predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError("Timed out waiting for private compositor state")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labwc", required=True)
    parser.add_argument("--watcher", required=True, help="Packaged headless-monitor-watch executable")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="clam."))
    print(f"Isolated logs: {root}", flush=True)
    runtime = root / "r"
    runtime.mkdir(mode=0o700)
    home = root / "home"
    home.mkdir()
    config_dir = root / "labwc"
    config_dir.mkdir()
    env = {**os.environ, "HOME": str(home), "XDG_RUNTIME_DIR": str(runtime),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CONFIG_DIRS": str(root / "empty"),
           "XDG_STATE_HOME": str(root / "state"),
           "WLR_BACKENDS": "headless", "WLR_HEADLESS_OUTPUTS": "1", "WLR_RENDERER": "gles2",
           "WLR_RENDER_DRM_DEVICE": "/dev/dri/renderD128", "WLR_LIBINPUT_NO_DEVICES": "1",
           "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                "HL_INITIAL_WORKSPACE_TOKEN", "HL_EXEC_RULE_TOKEN"):
        env.pop(key, None)
    processes = []

    def start(command, name):
        with (root / (name + ".log")).open("w") as log:
            processes.append(subprocess.Popen(command, env=env, stdout=log,
                                               stderr=subprocess.STDOUT, start_new_session=True))

    def ctl(*arguments):
        return subprocess.run(["hyprctl", *arguments], env=env, text=True,
                              capture_output=True, check=True, timeout=5).stdout

    def active(name):
        return any(m["name"] == name and not m.get("disabled", False)
                   for m in json.loads(ctl("monitors", "all", "-j")))

    try:
        start([args.labwc, "-C", str(config_dir)], "labwc")
        socket = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket()), None))
        env["WAYLAND_DISPLAY"] = socket.name
        config = root / "hypr.conf"
        config.write_text("monitor=,1920x1080@60,auto,1\nxwayland {\n enabled=false\n}\ndebug {\n disable_logs=false\n}\n")
        start(["Hyprland", "-c", str(config)], "hyprland")
        ipc = wait_for(lambda: next((runtime / "hypr").glob("*/.socket.sock"), None))
        env["HYPRLAND_INSTANCE_SIGNATURE"] = ipc.parent.name
        inner = wait_for(lambda: next((p for p in runtime.glob("wayland-*")
                                      if p.is_socket() and p != socket), None))
        env["WAYLAND_DISPLAY"] = inner.name
        for name in ("eDP-1", "DP-3"):
            assert ctl("output", "create", "headless", name).strip() == "ok"
            wait_for(lambda: active(name))
        for m in json.loads(ctl("monitors", "all", "-j")):
            if m["name"] not in ("eDP-1", "DP-3"):
                ctl("keyword", "monitor", m["name"] + ",disable")
        ctl("keyword", "monitor", "eDP-1,1920x1080@60,0x0,1")
        ctl("keyword", "monitor", "DP-3,1600x900@60,1920x0,1")
        wait_for(lambda: next(m for m in json.loads(ctl("monitors", "all", "-j"))
                              if m["name"] == "DP-3")["width"] == 1600)
        for name in ("clam-a", "clam-b", "clam-ext"):
            ctl("keyword", "workspace", f"name:{name},persistent:true")
        for name, monitor in (("clam-a", "eDP-1"), ("clam-b", "eDP-1"), ("clam-ext", "DP-3")):
            ctl("dispatch", "moveworkspacetomonitor", f"name:{name} {monitor}")
        ctl("dispatch", "focusmonitor", "eDP-1")
        ctl("dispatch", "workspace", "name:clam-b")
        ctl("dispatch", "workspace", "name:clam-a")
        ctl("dispatch", "focusmonitor", "DP-3")
        ctl("dispatch", "workspace", "name:clam-ext")
        ctl("dispatch", "focusmonitor", "eDP-1")
        source = Path(__file__).resolve().parents[1] / "home/scripts/display/clamshell-mode.py"
        spec = importlib.util.spec_from_file_location("clamshell_live_module", source)
        mode = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mode)
        lid_file = root / "lid"
        lid_file.write_text("closed")
        cli = root / "clamshell-test"
        cli.write_text(f'#!{os.sys.executable}\nimport runpy\nfrom pathlib import Path\n'
                       f'm = runpy.run_path({str(source)!r})\ng = m["main"].__globals__\n'
                       f'g["lid_closed"] = lambda: Path({str(lid_file)!r}).read_text() == "closed"\n'
                       'g["headless_busy"] = lambda: False\nm["main"]()\n')
        cli.chmod(0o755)
        fake_root_state = root / "folded-state"
        fake_root_state.write_text("off")
        watcher = root / "watcher"
        watcher_source = Path(args.watcher).read_text().replace("/run/headless-mode/state", str(fake_root_state))
        watcher_source = watcher_source.replace("clamshell-mode check", f"{cli} check")
        watcher_source = watcher_source.replace("# Socket events", f"touch {root / 'ready'}\n# Socket events")
        watcher.write_text(watcher_source)
        watcher.chmod(0o755)
        start([str(watcher)], "watcher")
        wait_for(lambda: (root / "ready").exists())
        # A stale saved Shift-F7 position must NOT replace the snapshot restored
        # on panel enable, even when those events queue past journal deletion.
        position = Path(env["XDG_STATE_HOME"]) / "external-display-position"
        position.parent.mkdir()
        position.write_text("-900 200\n")

        def entry(action):
            subprocess.run([str(cli), action], env=env, check=True, capture_output=True, timeout=20)

        with patch.dict(os.environ, env, clear=True), patch.object(mode, "headless_busy", return_value=False), \
                patch.object(mode, "lid_closed", return_value=True) as lid:
            controller = mode.Clamshell(runtime, env["HYPRLAND_INSTANCE_SIGNATURE"])
            panel_id = str(next(m for m in mode.monitors() if m["name"] == "eDP-1")["id"])
            for mirrored in (False, True):
                if mirrored:
                    ctl("keyword", "monitor", "DP-3,1600x900@60,auto,1,mirror,eDP-1")
                    wait_for(lambda: next(m for m in mode.monitors() if m["name"] == "DP-3")["mirrorOf"] == panel_id)
                entry("close")
                wait_for(lambda: not active("eDP-1"))
                assert active("DP-3")
                assert next(m for m in mode.monitors() if m["name"] == "DP-3")["dpmsStatus"]
                assert next(m for m in mode.monitors() if m["name"] == "DP-3")["mirrorOf"] == "none"
                lid.return_value = False
                lid_file.write_text("open")
                entry("open")
                wait_for(lambda: active("eDP-1"))
                external = next(m for m in mode.monitors() if m["name"] == "DP-3")
                assert external["mirrorOf"] == (panel_id if mirrored else "none")
                assert external["width"] == 1600
                if not mirrored:
                    assert external["x"] == 1920
                assert not controller.path.exists()
                # Leave enough time for the watcher's queued socket events.
                time.sleep(3)
                if not mirrored:
                    after_events = next(m for m in mode.monitors() if m["name"] == "DP-3")
                    assert after_events["x"] == 1920
                    assert after_events["width"] == 1600
                workspaces = {w["name"]: w["monitor"] for w in json.loads(ctl("workspaces", "-j"))}
                assert workspaces["clam-a"] == "eDP-1", workspaces
                assert workspaces["clam-b"] == "eDP-1", workspaces
                assert workspaces["clam-ext"] == ("eDP-1" if mirrored else "DP-3"), workspaces
                lid.return_value = True
                lid_file.write_text("closed")
            # Restart the watcher with an open-lid journal. Startup recovery
            # must not immediately reapply the conflicting Shift-F7 layout.
            ctl("keyword", "monitor", "DP-3,1600x900@60,1920x0,1")
            wait_for(lambda: next(m for m in mode.monitors() if m["name"] == "DP-3")["mirrorOf"] == "none")
            entry("close")
            previous = processes[-1]
            os.killpg(previous.pid, signal.SIGTERM)
            previous.wait(timeout=5)
            (root / "ready").unlink()
            lid_file.write_text("open")
            start([str(watcher)], "watcher-restart")
            wait_for(lambda: (root / "ready").exists())
            wait_for(lambda: not controller.path.exists())
            time.sleep(3)
            restored = next(m for m in mode.monitors() if m["name"] == "DP-3")
            assert restored["x"] == 1920 and restored["width"] == 1600, restored
            lid_file.write_text("closed")
            # External loss recovery must restore the panel, even while closed.
            entry("close")
            ctl("output", "remove", "DP-3")
            # The real watcher, rather than the controller test driver, recovers
            # the last-output removal and cleans up its temporary output.
            wait_for(lambda: not controller.path.exists())
            wait_for(lambda: active("eDP-1"))
            assert not any(m["name"].startswith("clamshell-recovery-") for m in mode.monitors())
            assert not controller.path.exists()
            # Deferred sleep with no external output: keep the render output
            # enabled, blank only its panel, and wake it on lid reopen.
            entry("close")
            wait_for(lambda: not next(m for m in mode.monitors() if m["name"] == "eDP-1")["dpmsStatus"])
            assert active("eDP-1")
            assert controller.load()["panelOnly"]
            lid_file.write_text("open")
            entry("open")
            wait_for(lambda: next(m for m in mode.monitors() if m["name"] == "eDP-1")["dpmsStatus"])
            assert not controller.path.exists()
        assert ctl("configerrors").strip() == "", ctl("configerrors")
        print("PASS: extended, mirrored, reopen, external loss and panel-only blanking through real IPC")
    finally:
        if "HYPRLAND_INSTANCE_SIGNATURE" in env:
            try:
                (root / "final-monitors.json").write_text(ctl("monitors", "all", "-j"))
            except subprocess.SubprocessError:
                pass
        for process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    main()
