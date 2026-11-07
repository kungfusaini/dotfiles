#!/usr/bin/env python3
"""Opt-in real compositor test. Never connects to the user's Wayland/DBus session.

Requires Hyprland, labwc (wlroots GLES2), Kitty, Chromium, dbus-run-session,
and an accessible DRM render node. Supply executable paths with the CLI options.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import socket as socket_module
import subprocess
import sys
import tempfile
import threading
import time


def wait_for(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("timed out waiting for isolated test state")


def assert_browser_events(events, browser_class, workspace, address, *, human_consent=False):
    """Check all browser lifetimes; optionally bound explicit hidden human input."""
    opened = []
    human_class = None
    for event in events:
        if event.startswith("custom>>pi-consent-begin:"):
            assert human_consent and human_class is None, "unexpected human-input interval"
            human_class = event.split(":", 1)[1]
            assert human_class.startswith("pi-vivaldi-"), "unbounded human-input target"
        elif event.startswith("custom>>pi-consent-end:"):
            assert human_class == event.split(":", 1)[1], "mismatched human-input interval"
            human_class = None
        if event.startswith("activewindow>>"):
            active_class = event.split(">>", 1)[1].split(",", 1)[0]
            assert browser_class not in active_class or active_class == human_class, "transient browser focus theft"
        if event.startswith("openwindow>>"):
            fields = event.split(">>", 1)[1].split(",", 3)
            if len(fields) == 4 and browser_class in fields[2]:
                opened.append(fields)
    assert human_class is None, "human-input interval was not closed"
    assert any(fields[0] == address for fields in opened), "browser mapping event missing"
    assert all(fields[1] == workspace for fields in opened), "initial placement was wrong"


def worker(arguments):
    root, helper, browser, strip = arguments
    root = Path(root)
    wait_for(lambda: (root / "go").exists())
    args = [browser, "--user-data-dir=" + str(root / "profile"), "--ozone-platform=wayland",
            "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
            "--disable-component-update", "--disable-sync", "--new-window", "about:blank"]
    launcher = "import os,subprocess,time;"
    if strip == "yes":
        # Fault injection: lose native exec rules and initial-workspace tracking,
        # while preserving our independent launch marker. Must recover by address.
        launcher += "os.environ.pop('HL_EXEC_RULE_TOKEN',None);os.environ.pop('HL_INITIAL_WORKSPACE_TOKEN',None);time.sleep(1.2);"
    launcher += "subprocess.run(" + repr(args) + ",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    result = subprocess.run([helper, sys.executable, "-c", launcher], text=True, capture_output=True)
    (root / "result.json").write_text(json.dumps({"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}))
    # Retain the invoking terminal until the controller has checked the outcome.
    wait_for(lambda: (root / "done").exists())


def run(args):
    # Short runtime path keeps Hyprland's instance socket below AF_UNIX limits.
    root = Path(tempfile.mkdtemp(prefix="wex."))
    runtime = root / "r"
    runtime.mkdir(mode=0o700)
    (root / "home").mkdir()
    (root / "labwc").mkdir()
    env = {**os.environ, "HOME": str(root / "home"), "XDG_RUNTIME_DIR": str(runtime),
           "XDG_CONFIG_HOME": str(root / "home" / ".config"), "XDG_CONFIG_DIRS": str(root / "empty"),
           "WLR_BACKENDS": "headless", "WLR_HEADLESS_OUTPUTS": "1", "WLR_RENDERER": "gles2",
           "WLR_RENDER_DRM_DEVICE": args.render_node, "WLR_LIBINPUT_NO_DEVICES": "1",
           "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}
    for key in ["DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                "HL_INITIAL_WORKSPACE_TOKEN", "HL_EXEC_RULE_TOKEN", "PROJECT_OBJECT_LAUNCH_ID",
                "PROJECT_OBJECT_WORKSPACE_NAME", "PROJECT_PICKER_HYPRCTL"]:
        env.pop(key, None)
    env["PROJECT_PICKER_HYPRCTL"] = args.hyprctl
    processes, events = [], []
    event_ready = threading.Event()

    def record_events(path):
        with socket_module.socket(socket_module.AF_UNIX) as stream, (root / "events.log").open("w", buffering=1) as log:
            stream.connect(str(path))
            event_ready.set()
            with stream.makefile() as lines:
                for line in lines:
                    events.append(line.rstrip())
                    log.write(line)

    def start(command, name):
        process = subprocess.Popen(command, env=env, stdout=(root / (name + ".log")).open("w"),
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    def ctl(*command):
        return subprocess.run([args.hyprctl, *command], env=env, capture_output=True, text=True, check=True, timeout=5).stdout

    def clients():
        return json.loads(ctl("clients", "-j"))

    try:
        start([args.labwc, "-C", str(root / "labwc")], "labwc")
        socket = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket()), None))
        env["WAYLAND_DISPLAY"] = socket.name
        config = root / "config.conf"
        config.write_text("monitor=,960x640@60,auto,1\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\nxwayland {\n enabled=false\n}\ndebug {\n disable_logs=false\n}\n")
        start([args.hyprland, "-c", str(config)], "hyprland")
        ipc = wait_for(lambda: next((runtime / "hypr").glob("*/.socket.sock"), None))
        env["HYPRLAND_INSTANCE_SIGNATURE"] = ipc.parent.name
        threading.Thread(target=record_events, args=(ipc.parent / ".socket2.sock",), daemon=True).start()
        assert event_ready.wait(5), "compositor event monitor did not connect"
        # The nested Wayland backend supplies the render allocator. Test windows
        # live on a separate headless output, never on a visible host surface.
        assert ctl("output", "create", "headless", "TEST").strip() == "ok"
        if args.keep_target_visible:
            assert ctl("output", "create", "headless", "TEST_FOCUS").strip() == "ok"
            assert ctl("dispatch", "focusmonitor", "TEST").strip() == "ok"
        wait_for(lambda: json.loads(ctl("monitors", "-j")))
        inner_socket = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket() and p != socket), None))
        env["WAYLAND_DISPLAY"] = inner_socket.name
        helper = str(Path(args.helper).resolve())
        for label, strip in [("wrapped", "no"), ("lost-native-rules", "yes")]:
            case = root / label
            case.mkdir()
            assert ctl("dispatch", "workspace", "name:Agent · Target").strip() == "ok"
            worker_command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(case), helper, args.chromium, strip]
            # Deliberately stale fallback: only real terminal ancestry can find Target.
            terminal_command = ["env", "PROJECT_OBJECT_WORKSPACE_NAME=Wrong recorded workspace", *worker_command]
            assert ctl("dispatch", "exec", shlex.join([args.kitty, "--class", "workspace-test", *terminal_command])).strip() == "ok"
            terminal = wait_for(lambda: next((c for c in clients() if c["class"] == "workspace-test"), None))
            assert terminal["workspace"]["name"] == "Agent · Target", terminal
            if args.keep_target_visible:
                # Extension-backed browser UI may need its first rendered frame.
                # Keep Target visible while focus moves to a separate virtual output.
                assert ctl("dispatch", "focusmonitor", "TEST_FOCUS").strip() == "ok"
            assert ctl("dispatch", "workspace", "name:Focused elsewhere").strip() == "ok"
            (case / "before-launch.json").write_text(json.dumps({
                "monitors": json.loads(ctl("monitors", "-j")), "clients": clients()}))
            (case / "go").touch()
            result_path = case / "result.json"
            wait_for(result_path.exists, timeout=60)
            result = json.loads(result_path.read_text())
            assert result["status"] == 0, result
            windows = wait_for(lambda: [c for c in clients() if args.browser_class in c["class"]])
            assert len(windows) == 1, windows
            assert windows[0]["workspace"]["name"] == "Agent · Target", windows
            assert json.loads(ctl("activeworkspace", "-j"))["name"] == "Focused elsewhere"
            assert json.loads(ctl("activewindow", "-j")) == {}, "launch stole focus"
            address = windows[0]["address"].removeprefix("0x")
            if args.check_transient_focus:
                assert_browser_events(events, args.browser_class, "Agent · Target", address,
                                      human_consent=args.simulate_human_consent)
            print(label + f": real {args.browser_class} window verified beside invoking Kitty; focused workspace unchanged", flush=True)
            (case / "done").touch()
            assert ctl("dispatch", "closewindow", "address:" + windows[0]["address"]).strip() == "ok"
            wait_for(lambda: not clients())
        print("PASS; isolated logs: " + str(root), flush=True)
    finally:
        # Include compositor-spawned descendants/crash handlers. Only processes
        # with this private runtime directory can be affected by this cleanup.
        marker = ("XDG_RUNTIME_DIR=" + str(runtime)).encode()
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                if marker in (proc / "environ").read_bytes().split(b"\0"):
                    os.kill(int(proc.name), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        for process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            # Hyprland's crash-handler child can outlive a clean parent exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        print("Logs retained at " + str(root), flush=True)


def main():
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["hyprland", "hyprctl", "labwc", "kitty", "chromium"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--check-transient-focus", action="store_true")
    parser.add_argument("--simulate-human-consent", action="store_true",
                        help="Allow only explicitly bounded private test-human consent focus events")
    parser.add_argument("--keep-target-visible", action="store_true")
    parser.add_argument("--browser-class", default="chromium")
    parser.add_argument("--render-node", default="/dev/dri/renderD128")
    parser.add_argument("--helper", default=str(Path(__file__).resolve().parents[1] / "bin" / "project-workspace-exec"))
    args = parser.parse_args()
    if os.environ.get("WORKSPACE_TEST_PRIVATE_DBUS") != "1":
        # Do not let a test compositor import/unset live desktop activation env.
        environment = {**os.environ, "WORKSPACE_TEST_PRIVATE_DBUS": "1"}
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        with tempfile.TemporaryDirectory(prefix="wex-bus.") as directory:
            config = Path(directory) / "bus.conf"
            # No service directories: private clients must not auto-start
            # portals, keyrings or notification daemons with live-session env.
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
            result = subprocess.run(["dbus-run-session", "--config-file=" + str(config), "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=environment)
        raise SystemExit(result.returncode)
    run(args)


if __name__ == "__main__":
    main()
