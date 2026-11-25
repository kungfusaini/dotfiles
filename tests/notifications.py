"""Policy matrix and isolated headless Mako integration.

nix eval --raw '.#nixosConfigurations.kirax1.config.home-manager.users.sumeet.xdg.configFile."mako/config".text' > /tmp/notifications-mako.conf
python3 tests/notifications.py /tmp/notifications-mako.conf [--sway /nix/store/.../bin/sway]

The live test starts only a headless software-rendered Wayland compositor and a
private session bus. It does not start X11 or connect to the desktop session.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER = argparse.ArgumentParser()
PARSER.add_argument("config", type=Path)
PARSER.add_argument("--sway")
PARSER.add_argument("--inner", action="store_true")
ARGS = PARSER.parse_args()
CONFIG = ARGS.config.read_text()


def settings(app, mode="all", urgency="normal", desktop=""):
    result = {}
    matches = True
    values = {"app-name": app, "urgency": urgency, "desktop-entry": desktop}
    for line in CONFIG.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            fields = dict(part.split("=", 1) for part in shlex.split(line[1:-1]))
            matches = all((mode == value if key == "mode" else values.get(key) == value)
                          for key, value in fields.items())
        elif matches:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def allowed(app, mode="all", **kw):
    return settings(app, mode, **kw).get("invisible") == "false"


class PolicyTests(unittest.TestCase):
    def test_matrix(self):
        sources = {
            "Slack": (True, False, False), "teams-for-linux": (True, False, False),
            "ZapZap": (True, False, False), "Steam": (True, False, False),
            "Nicotine+": (True, False, False),
            "Pi": (True, True, False), "Screenshots": (True, True, False),
            "Kirax1 Backup": (True, True, False), "Bluetooth controls": (True, True, False),
            "Sony headphones": (True, True, False), "Spotify": (True, True, False),
            "Project Workspace": (True, True, True),
            "Thunderbird": (False, False, False), "thunderbird": (False, False, False),
            "notify-send": (False, False, False), "New Chat App": (False, False, False),
            "Vivaldi": (False, False, False),
        }
        for source, expected in sources.items():
            with self.subTest(source=source):
                self.assertEqual(tuple(allowed(source, mode) for mode in
                    ("all", "no-contact", "do-not-disturb")), expected)

    def test_safety_requires_registered_sender_and_urgency(self):
        self.assertTrue(allowed("Power", "do-not-disturb", urgency="critical"))
        self.assertFalse(allowed("Power", "do-not-disturb"))
        self.assertFalse(allowed("Slack", "do-not-disturb", urgency="critical"))
        self.assertFalse(allowed("unknown", urgency="critical"))

    def test_desktop_identity_and_permanent_mute(self):
        self.assertTrue(allowed("different name", desktop="com.rtosta.zapzap"))
        self.assertFalse(allowed("different name", "no-contact", desktop="com.rtosta.zapzap"))
        self.assertFalse(allowed("Pi", desktop="thunderbird"))

    def test_suppressed_sources_expire_without_history(self):
        for source, mode in (("unknown", "all"), ("Slack", "no-contact"), ("Pi", "do-not-disturb"), ("Thunderbird", "all")):
            style = settings(source, mode)
            self.assertEqual(style["history"], "false")
            self.assertEqual(style["default-timeout"], "1")
            self.assertEqual(style["ignore-timeout"], "true")

    def test_waybar_cycle_preserves_unrelated_modes_and_reports_failure(self):
        with tempfile.TemporaryDirectory(prefix="notification-toggle-") as tmp:
            root = Path(tmp)
            state = root / "modes"
            state.write_text("default\nunrelated\n")
            (root / "makoctl").write_text('''#!/usr/bin/env python3
import os, pathlib, sys
p=pathlib.Path(os.environ['TEST_MODES'])
if os.environ.get('TEST_FAIL'): sys.exit(1)
a=sys.argv[1:]
command=a.pop(0)
if command=='dismiss': sys.exit()
assert command=='mode'
m=p.read_text().splitlines()
if not a: print('\\n'.join(m)); sys.exit()
for op, value in zip(a[::2], a[1::2]):
 if op=='-a' and value not in m: m.append(value)
 elif op=='-r' and value in m: m.remove(value)
p.write_text('\\n'.join(m)+'\\n')
''')
            (root / "makoctl").chmod(0o755)
            (root / "pkill").write_text("#!/bin/sh\nexit 0\n")
            (root / "pkill").chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", XDG_RUNTIME_DIR=tmp, TEST_MODES=str(state))
            script = ROOT / "hosts/kirax1/scripts/desktop/dnd-waybar"
            def run(*args):
                return subprocess.check_output(["bash", str(script), *args], env=env, text=True)
            for wanted in ("inactive", "no-contact", "active", "inactive"):
                self.assertEqual(json.loads(run())["class"], wanted)
                self.assertIn("unrelated", state.read_text())
                run("toggle")
            env["TEST_FAIL"] = "1"
            self.assertEqual(json.loads(run())["class"], "error")
            self.assertNotEqual(subprocess.run(["bash", str(script), "toggle"], env=env).returncode, 0)


def live():
    """Run inside a dedicated dbus-run-session with a fresh runtime directory."""
    with tempfile.TemporaryDirectory(prefix="notification-live-") as tmp:
        root = Path(tmp)
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        sway_config = root / "sway.conf"
        sway_config.write_text("xwayland disable\noutput HEADLESS-1 resolution 1280x720\n")
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime),
                   HOME=tmp, XDG_CONFIG_HOME=str(root / "config"),
                   WLR_BACKENDS="headless", WLR_RENDERER="pixman", WLR_LIBINPUT_NO_DEVICES="1",
                   DBUS_SYSTEM_BUS_ADDRESS=f"unix:path={tmp}/no-system-bus")
        for key in ("DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE"):
            env.pop(key, None)
        processes = []
        with (root / "compositor.log").open("w+") as log:
            def run(*args):
                return subprocess.check_output(args, env=env, text=True, stderr=subprocess.STDOUT)
            def start(*args):
                p = subprocess.Popen(args, env=env, stdout=log, stderr=log)
                processes.append(p)
                return p
            try:
                env.pop("WAYLAND_DISPLAY", None)
                sway = start(ARGS.sway, "--config", str(sway_config))
                for _ in range(100):
                    sockets = list(runtime.glob("wayland-*"))
                    sockets = [p for p in sockets if p.is_socket()]
                    if sockets:
                        env["WAYLAND_DISPLAY"] = sockets[0].name
                        break
                    if sway.poll() is not None: raise AssertionError("Headless compositor exited")
                    time.sleep(.05)
                else: raise AssertionError("Headless compositor failed to start")
                mako = start("mako", "--config", str(ARGS.config.resolve()))
                for _ in range(100):
                    if mako.poll() is not None: raise AssertionError("Mako failed to parse config")
                    try:
                        run("makoctl", "mode")
                        break
                    except subprocess.CalledProcessError:
                        time.sleep(.05)
                else: raise AssertionError("Mako failed to own private bus")
                for mode in ("all", "no-contact", "do-not-disturb"):
                    run("makoctl", "mode", "-s", mode)
                    for app, urgency in (("unknown", "normal"), ("notify-send", "normal"), ("Thunderbird", "critical"),
                                         ("Slack", "normal"), ("Pi", "normal"), ("Project Workspace", "normal"),
                                         ("Power", "normal"), ("Power", "critical")):
                        run("makoctl", "dismiss", "--all", "--no-history")
                        run("notify-send", f"--app-name={app}", f"--urgency={urgency}", "--expire-time=0", "Synthetic policy probe")
                        time.sleep(.15)
                        data = json.loads(run("makoctl", "list", "-j"))
                        present = bool(data.get("data", []) if isinstance(data, dict) else data)
                        assert present == allowed(app, mode, urgency=urgency), (mode, app, urgency, data)
                # The real button must remove already displayed conversations
                # before tightening policy, with no replay when All is restored.
                (root / "pkill").write_text("#!/bin/sh\nexit 0\n")
                (root / "pkill").chmod(0o755)
                env["PATH"] = f"{root}:" + env["PATH"]
                toggle = str(ROOT / "hosts/kirax1/scripts/desktop/dnd-waybar")
                run("makoctl", "dismiss", "--all", "--no-history")
                run("makoctl", "mode", "-s", "all")
                run("notify-send", "--app-name=Slack", "Synthetic policy probe")
                for _ in range(3):
                    run("bash", toggle, "toggle")
                    time.sleep(.05)
                assert "Synthetic policy probe" not in run("makoctl", "list", "-j")
                # Suppressed messages must not reappear when restrictions lift.
                run("makoctl", "mode", "-s", "all")
                run("makoctl", "dismiss", "--all", "--no-history")
                history = run("makoctl", "history", "-j")
                assert "Synthetic policy probe" not in history, history
                print("PASS: real Mako accepted generated config; 24 live policy probes and no suppressed history")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    if ARGS.inner:
        live()
    else:
        result = unittest.main(argv=[sys.argv[0]], exit=False)
        if not result.result.wasSuccessful(): sys.exit(1)
        if ARGS.sway:
            env = dict(os.environ)
            env.pop("DBUS_SESSION_BUS_ADDRESS", None)
            # No service directories: never autoactivate desktop services with
            # the parent session's environment on this private bus.
            with tempfile.TemporaryDirectory(prefix="notification-bus-") as tmp:
                bus_config = Path(tmp) / "bus.conf"
                bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                    '<auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/>'
                    '<allow receive_sender="*"/><allow own="*"/><allow send_type="error"/>'
                    '<allow receive_type="error"/><allow send_requested_reply="false"/>'
                    '<allow receive_requested_reply="false"/></policy></busconfig>')
                subprocess.run(["dbus-run-session", "--config-file", str(bus_config), "--", sys.executable,
                                __file__, str(ARGS.config.resolve()), "--sway", ARGS.sway, "--inner"],
                               env=env, check=True)
