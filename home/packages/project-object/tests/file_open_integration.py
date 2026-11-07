#!/usr/bin/env python3
"""Hidden file-link handoff acceptance; private DBus, compositors and browser profile."""
import argparse
import base64
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


def run(args):
    root = Path(tempfile.mkdtemp(prefix="filelink."))
    runtime = root / "r"
    runtime.mkdir(mode=0o700)
    home = root / "home"
    home.mkdir()
    (root / "labwc").mkdir()
    env = {**os.environ, "HOME": str(home), "XDG_RUNTIME_DIR": str(runtime),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CONFIG_DIRS": str(root / "empty"),
           "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(root / "cache"),
           "XDG_STATE_HOME": str(root / "state"), "WLR_BACKENDS": "headless", "WLR_HEADLESS_OUTPUTS": "1",
           "WLR_RENDERER": "gles2", "WLR_RENDER_DRM_DEVICE": "/dev/dri/renderD128",
           "WLR_LIBINPUT_NO_DEVICES": "1", "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland",
           "PROJECT_PICKER_HYPRCTL": args.hyprctl, "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                "HL_INITIAL_WORKSPACE_TOKEN", "HL_EXEC_RULE_TOKEN", "PROJECT_OBJECT_LAUNCH_ID",
                "PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME", "PROJECT_OBJECT_WORKSPACE_NAME", "PROJECT_OBJECT_ID"):
        env.pop(key, None)
    browser = root / "vivaldi"
    browser.write_text("#!/bin/sh\nexec " + shlex.quote(args.vivaldi) + " --user-data-dir=" + shlex.quote(str(root / "profile"))
                       + ' --ozone-platform=wayland --no-first-run --no-default-browser-check --disable-background-networking'
                       + ' --disable-component-update --disable-sync --no-proxy-server --host-resolver-rules="MAP * ~NOTFOUND" "$@"\n')
    browser.chmod(0o700)
    env["PROJECT_FILE_VIVALDI"] = str(browser)
    apps = home / ".local/share/applications"
    apps.mkdir(parents=True)
    (apps / "vivaldi-test.desktop").write_text("[Desktop Entry]\nType=Application\nName=Vivaldi test\nExec=vivaldi %U\nMimeType=text/html;\n")
    # A real new GTK/terminal window stands in for each desktop viewer. GIO must
    # expand its Exec fields without shell interpretation and preserve the path.
    viewer = root / "zathura"
    viewer.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" >> " + shlex.quote(str(root / "viewer-paths"))
                      + "\nexec " + shlex.quote(args.kitty) + " --class file-fixture sh -c 'sleep 120'\n")
    viewer.chmod(0o700)
    (apps / "fixture.desktop").write_text("[Desktop Entry]\nType=Application\nName=File fixture\nExec=" + str(viewer) + " %f\nMimeType=image/png;application/pdf;\n")
    (apps / "folder.desktop").write_text("[Desktop Entry]\nType=Application\nName=Folder\nExec=" + args.kitty + " +open %U\nMimeType=inode/directory;\n")
    (apps / "editor.desktop").write_text("[Desktop Entry]\nType=Application\nName=Editor\nExec=nvim %F\nTerminal=true\nMimeType=text/plain;\n")
    config_dir = home / ".config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "mimeapps.list").write_text("[Default Applications]\ntext/html=vivaldi-test.desktop\nimage/png=fixture.desktop\napplication/pdf=fixture.desktop\ninode/directory=folder.desktop\ntext/plain=editor.desktop\n")
    kitty_dir = config_dir / "kitty"
    kitty_dir.mkdir()
    (kitty_dir / "open-actions.conf").write_text("protocol file\naction launch --type=background " + args.opener + " ${URL}\n")
    media = root / 'test files é ; $(no command)'
    media.mkdir()
    page = media / "gallery #100%.html"
    page.write_text('<title>Loading fixture</title><img src="asset.png" onload="document.title=\'Local file loaded\'">')
    image = media / "asset.png"
    image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC0cAAAAASUVORK5CYII="))
    pdf = media / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% fixture default-app dispatch only\n")
    text = media / "notes.txt"
    text.write_text("Safe local text fixture\n")
    processes, events = [], []

    def start(command, label):
        p = subprocess.Popen(command, env=env, stdout=(root / (label + ".log")).open("w"), stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(p)
        return p

    def ctl(*arguments):
        return subprocess.run([args.hyprctl, *arguments], env=env, capture_output=True, text=True, check=True, timeout=5).stdout

    def clients():
        return json.loads(ctl("clients", "-j"))

    def focus():
        return (json.loads(ctl("activeworkspace", "-j"))["name"], json.loads(ctl("activewindow", "-j")).get("address"))

    def record(path):
        with socket.socket(socket.AF_UNIX) as stream, (root / "events.log").open("w", buffering=1) as log:
            stream.connect(str(path))
            for line in stream.makefile():
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
        ctl("output", "create", "headless", "TEST")
        wait_for(lambda: json.loads(ctl("monitors", "-j")))
        env["WAYLAND_DISPLAY"] = wait_for(lambda: next((p for p in runtime.glob("wayland-*") if p.is_socket() and p != outer), None)).name
        threading.Thread(target=record, args=(ipc.parent / ".socket2.sock",), daemon=True).start()
        ctl("dispatch", "workspace", "name:Clicked chat")
        # Exercise Kitty's actual configured open_url -> open-actions -> background
        # launcher path, not just a direct invocation of the new helper.
        remote = root / "kitty.sock"
        ctl("dispatch", "exec", shlex.join([args.kitty, "--class", "clicked-chat", "-o", "allow_remote_control=yes",
                                               "--listen-on", "unix:" + str(remote), "sh", "-c", "sleep 180"]))
        wait_for(lambda: remote.exists())
        wait_for(lambda: any(c["class"] == "clicked-chat" for c in clients()))
        ctl("dispatch", "workspace", "name:Elsewhere")
        ctl("dispatch", "exec", shlex.join([args.kitty, "--class", "unrelated-user", "sh", "-c", "sleep 180"]))
        user = wait_for(lambda: next((c for c in clients() if c["class"] == "unrelated-user"), None))
        wait_for(lambda: focus()[1] == user["address"])
        for index, path in enumerate((page, page, image, pdf, media, page, image, pdf, media, text)):
            if index == 5:
                ctl("dispatch", "workspace", "name:Clicked chat")
                chat = next(c for c in clients() if c["class"] == "clicked-chat")
                ctl("dispatch", "focuswindow", "address:" + chat["address"])
                wait_for(lambda: focus()[1] == chat["address"])
            old = {c["address"] for c in clients()}
            before = focus()
            result = subprocess.run([args.kitty, "@", "--to", "unix:" + str(remote), "action", "open_url", path.as_uri()], env=env, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            new = wait_for(lambda: [c for c in clients() if c["address"] not in old], timeout=30)
            assert len(new) == 1, new
            window = new[0]
            assert window["workspace"]["name"] == "Clicked chat", window
            if path == page:
                wait_for(lambda: any(c["address"] == window["address"] and c["title"] == "Local file loaded" for c in clients()))
            elif path in (image, pdf):
                wait_for(lambda: (root / "viewer-paths").exists() and str(path) in (root / "viewer-paths").read_text().splitlines())
            else:
                assert window["class"] == "kitty", window
            time.sleep(0.2)
            assert focus() == before, (before, focus())
            address = window["address"].removeprefix("0x")
            wait_for(lambda: any(e.startswith("openwindow>>" + address + ",") for e in events))
            assert any(e.startswith("openwindow>>" + address + ",Clicked chat,") for e in events), events
            assert "activewindowv2>>" + address not in events, "transient focus theft"
            print(f"case {index}: configured Kitty file action, correct workspace, focus unchanged; {path.name}", flush=True)
        assert not ctl("configerrors").strip(), ctl("configerrors")
        print("PASS; logs: " + str(root), flush=True)
    finally:
        marker = ("XDG_RUNTIME_DIR=" + str(runtime)).encode()
        for proc in Path("/proc").iterdir():
            if proc.name.isdigit() and int(proc.name) != os.getpid():
                try:
                    if marker in (proc / "environ").read_bytes().split(b"\0"):
                        os.kill(int(proc.name), signal.SIGTERM)
                except OSError:
                    pass
        for p in reversed(processes):
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        print("Logs retained: " + str(root), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("hyprland", "hyprctl", "labwc", "kitty", "vivaldi", "opener"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if os.environ.get("FILE_OPEN_PRIVATE_DBUS") != "1":
        env = {**os.environ, "FILE_OPEN_PRIVATE_DBUS": "1"}
        env.pop("DBUS_SESSION_BUS_ADDRESS", None)
        with tempfile.TemporaryDirectory(prefix="filelink-bus.") as root:
            config = Path(root) / "bus.conf"
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
            result = subprocess.run(["dbus-run-session", "--config-file=" + str(config), "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
        raise SystemExit(result.returncode)
    run(args)


if __name__ == "__main__":
    main()
