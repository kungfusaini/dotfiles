#!/usr/bin/env python3
"""Opt-in shared-profile Vivaldi regression, entirely inside a hidden desktop.

Requires labwc, Hyprland, Kitty, Vivaldi, dbus-run-session and a DRM render node.
Never connects to the user's compositor, profile or session bus. Logs stay in /tmp.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

from workspace_exec_integration import wait_for


def worker(arguments):
    case, helper, router, mode, *urls = arguments
    case = Path(case)
    wait_for(lambda: (case / "go").exists())
    command = [router, "open", "--mode", "project", *urls]
    if mode == "wrapped":
        command = [sys.executable, "-c", "import subprocess; subprocess.run(" + repr(command) + ",check=True)"]
    if mode == "direct":
        # Pi context should auto-route direct project-browser calls safely.
        command = [router, "open", *urls]
    else:
        command = [helper, *command]
    result = subprocess.run(command, capture_output=True, text=True)
    (case / "result.json").write_text(json.dumps({"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}))
    wait_for(lambda: (case / "done").exists(), timeout=120)


def run(args):
    root = Path(tempfile.mkdtemp(prefix="abtest."))
    runtime = root / "r"
    runtime.mkdir(mode=0o700)
    (root / "home").mkdir()
    (root / "labwc").mkdir()
    env = {**os.environ, "HOME": str(root / "home"), "XDG_RUNTIME_DIR": str(runtime),
           "XDG_CONFIG_HOME": str(root / "home" / ".config"), "XDG_CONFIG_DIRS": str(root / "empty"),
           "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
           "XDG_STATE_HOME": str(root / "state"), "WLR_BACKENDS": "headless", "WLR_HEADLESS_OUTPUTS": "1",
           "WLR_RENDERER": "gles2", "WLR_RENDER_DRM_DEVICE": args.render_node,
           "WLR_LIBINPUT_NO_DEVICES": "1", "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland",
           "PROJECT_PICKER_HYPRCTL": args.hyprctl, "PROJECT_BROWSER_HYPRCTL": args.hyprctl,
           "PROJECT_OBJECT_RUNTIME_DIR": str(runtime / "project-object"), "PI_CODING_AGENT": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ["DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                "HL_INITIAL_WORKSPACE_TOKEN", "HL_EXEC_RULE_TOKEN", "PROJECT_OBJECT_LAUNCH_ID",
                "PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME", "PROJECT_OBJECT_WORKSPACE_NAME", "PROJECT_OBJECT_ID",
                "PROJECT_OBJECT_DATA_DIR"]:
        env.pop(key, None)
    wrapper = root / "vivaldi"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(args.vivaldi) + " --user-data-dir=" + shlex.quote(str(root / "profile"))
                       + ' --ozone-platform=wayland --no-first-run --no-default-browser-check --disable-background-networking'
                       + ' --disable-component-update --disable-sync --no-proxy-server'
                       + ' --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" "$@"\n')
    wrapper.chmod(0o700)
    env["PROJECT_BROWSER_VIVALDI"] = str(wrapper)
    # Direct auto-routing must use this test helper, not the deployed helper.
    bindir = root / "bin"
    bindir.mkdir()
    (bindir / "project-workspace-exec").symlink_to(Path(args.helper).resolve())
    env["PATH"] = str(bindir) + ":" + env["PATH"]
    processes, events, requests = [], [], []

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path": self.path, "cookie": self.headers.get("Cookie")})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "agenttest=shared; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(b"<title>Agent shared-session test</title><p>Local test page</p>")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:" + str(server.server_port)

    def start(command, name):
        process = subprocess.Popen(command, env=env, stdout=(root / (name + ".log")).open("w"),
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    def ctl(*command):
        return subprocess.run([args.hyprctl, *command], env=env, capture_output=True, text=True, check=True, timeout=5).stdout

    def clients():
        return json.loads(ctl("clients", "-j"))

    def focus():
        return (json.loads(ctl("activeworkspace", "-j"))["name"], json.loads(ctl("activewindow", "-j")).get("address"))

    def record_events(path):
        with socket.socket(socket.AF_UNIX) as stream, (root / "events.log").open("w", buffering=1) as log:
            stream.connect(str(path))
            with stream.makefile() as lines:
                for line in lines:
                    events.append(line.rstrip())
                    log.write(line)

    try:
        start([args.labwc, "-C", str(root / "labwc")], "labwc")
        outer = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket()), None))
        env["WAYLAND_DISPLAY"] = outer.name
        config = root / "hyprland.conf"
        config.write_text("monitor=,960x640@60,auto,1\nmisc {\n disable_hyprland_logo=true\n disable_splash_rendering=true\n}\nxwayland {\n enabled=false\n}\n")
        start([args.hyprland, "-c", str(config)], "hyprland")
        ipc = wait_for(lambda: next((runtime / "hypr").glob("*/.socket.sock"), None))
        env["HYPRLAND_INSTANCE_SIGNATURE"] = ipc.parent.name
        assert ctl("output", "create", "headless", "TEST").strip() == "ok"
        wait_for(lambda: json.loads(ctl("monitors", "-j")))
        env["WAYLAND_DISPLAY"] = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket() and p != outer), None)).name
        threading.Thread(target=record_events, args=(ipc.parent / ".socket2.sock",), daemon=True).start()
        browser_pid, normal = None, None
        app_addresses = []
        labels = ["fresh", "existing", "same-workspace", "wrapped", "multi", "direct"]
        for label in labels:
            case = root / label
            case.mkdir()
            ctl("dispatch", "workspace", "name:Agent · Target")
            urls = [base + "/" + label + "/" + str(i) for i in range(2 if label == "multi" else 1)]
            mode = label if label in ("wrapped", "direct") else "helper"
            worker_command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(case), str(Path(args.helper).resolve()), str(Path(args.router).resolve()), mode, *urls]
            ctl("dispatch", "exec", shlex.join([args.kitty, "--class", "agent-" + label, "env", "PROJECT_OBJECT_WORKSPACE_NAME=Wrong recorded workspace", *worker_command]))
            wait_for(lambda: any(c["class"] == "agent-" + label for c in clients()))
            target = "Agent · Target" if label == "same-workspace" else "User elsewhere"
            ctl("dispatch", "workspace", "name:" + target)
            ctl("dispatch", "exec", shlex.join([args.kitty, "--class", "user-" + label, "sh", "-c", "sleep 180"]))
            user = wait_for(lambda: next((c for c in clients() if c["class"] == "user-" + label), None))
            wait_for(lambda: focus()[1] == user["address"])
            before, old = focus(), {c["address"] for c in clients()}
            (case / "go").touch()
            wait_for(lambda: (case / "result.json").exists(), timeout=45)
            result = json.loads((case / "result.json").read_text())
            assert result["status"] == 0, result
            apps = wait_for(lambda: [c for c in clients() if c["address"] not in old and c["class"].startswith("vivaldi-127.0.0.1__poagent")])
            assert len(apps) == len(urls), apps
            assert focus() == before, (before, focus())
            for app in apps:
                assert app["workspace"]["name"] == "Agent · Target", app
                if browser_pid is None:
                    browser_pid = app["pid"]
                assert app["pid"] == browser_pid, "separate browser process"
                address = app["address"].removeprefix("0x")
                app_addresses.append(address)
                wait_for(lambda: any(e.startswith("openwindow>>" + address + ",") for e in events))
                assert any(e.startswith("openwindow>>" + address + ",Agent · Target,") for e in events), "mapped on wrong workspace"
                assert "activewindowv2>>" + address not in events, "transient focus theft"
            wait_for(lambda: all(any(r["path"] == url.removeprefix(base) for r in requests) for url in urls))
            if label != "fresh":
                assert all(any(r["path"] == url.removeprefix(base) and r["cookie"] == "agenttest=shared" for r in requests) for url in urls), requests
                assert next(c for c in clients() if c["address"] == normal["address"])["workspace"]["name"] == "Normal browser"
            (case / "windows.json").write_text(json.dumps(apps, indent=2))
            print(label + ": beside agent, focus unchanged, same browser PID; shared cookies verified" if label != "fresh" else "fresh: app mapped beside agent without focus", flush=True)
            if label == "fresh":
                ctl("dispatch", "workspace", "name:Normal browser")
                start([str(wrapper), "--new-window", base + "/normal"], "normal-browser")
                normal = wait_for(lambda: next((c for c in clients() if c["class"] == "vivaldi-stable"), None))
                assert normal["pid"] == browser_pid
        assert all("activewindowv2>>" + address not in events for address in app_addresses), "late app focus theft"
        for label in labels:
            (root / label / "done").touch()
        assert not ctl("configerrors").strip(), "compositor configuration errors"
        print("PASS; logs: " + str(root), flush=True)
    finally:
        server.shutdown()
        server.server_close()
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
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        print("Logs retained: " + str(root), flush=True)


def main():
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["hyprland", "hyprctl", "labwc", "kitty", "vivaldi"]:
        parser.add_argument("--" + name, required=True)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--helper", default=str(root / "bin" / "project-workspace-exec"))
    parser.add_argument("--router", default=str(root / "bin" / "project-browser"))
    parser.add_argument("--render-node", default="/dev/dri/renderD128")
    args = parser.parse_args()
    if os.environ.get("AGENT_BROWSER_TEST_PRIVATE_DBUS") != "1":
        environment = {**os.environ, "AGENT_BROWSER_TEST_PRIVATE_DBUS": "1"}
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        with tempfile.TemporaryDirectory(prefix="abtest-bus.") as directory:
            config = Path(directory) / "bus.conf"
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
            result = subprocess.run(["dbus-run-session", "--config-file=" + str(config), "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=environment)
        raise SystemExit(result.returncode)
    run(args)


if __name__ == "__main__":
    main()
