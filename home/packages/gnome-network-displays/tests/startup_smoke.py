#!/usr/bin/env python3
"""Real GTK startup on private headless Wayland and an inert fake portal.

No host buses, screen/audio capture, device discovery or visible UI are used.
--expect-request is a negative control for the unpatched upstream client.
"""
import argparse
import asyncio
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from dbus_next import PropertyAccess, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, dbus_property, method


class Portal(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.portal.ScreenCast")
        self.requests = 0

    @dbus_property(access=PropertyAccess.READ)
    def version(self) -> 'u':
        return 5

    @dbus_property(access=PropertyAccess.READ)
    def AvailableSourceTypes(self) -> 'u':
        return 7

    @dbus_property(access=PropertyAccess.READ)
    def AvailableCursorModes(self) -> 'u':
        return 7

    @method()
    def CreateSession(self, options: 'a{sv}') -> 'o':
        self.requests += 1
        # Deliberately leave this inert request unanswered. No selection or
        # media-sharing implementation exists on the test bus.
        return "/org/freedesktop/portal/desktop/request/test/blocked"


class Settings(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.portal.Settings")

    @dbus_property(access=PropertyAccess.READ)
    def version(self) -> 'u':
        return 1

    @method()
    def ReadAll(self, namespaces: 'as') -> 'a{sa{sv}}':
        return {}

    @method()
    def Read(self, namespace: 's', key: 's') -> 'v':
        # The deprecated Settings.Read API wraps its value twice.
        return Variant('v', Variant('u', 0))


async def main(args):
    with tempfile.TemporaryDirectory(prefix="gnd-start.") as directory:
        root = Path(directory)
        runtime = root / "r"
        runtime.mkdir(mode=0o700)
        home = root / "home"
        home.mkdir()
        (root / "labwc").mkdir()
        bus_config = root / "bus.conf"
        bus_config.write_text(f'''<busconfig><type>session</type><listen>unix:tmpdir={runtime}</listen>
<auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/>
<allow receive_sender="*"/><allow own="*"/></policy></busconfig>''')
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / ".config"), XDG_CONFIG_DIRS=str(root / "empty"),
                   XDG_CACHE_HOME=str(home / ".cache"), XDG_STATE_HOME=str(home / ".state"),
                   WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="pixman",
                   WLR_LIBINPUT_NO_DEVICES="1", GDK_BACKEND="wayland", GSK_RENDERER="cairo",
                   GTK_A11Y="none", NO_AT_BRIDGE="1", GIO_USE_VFS="local",
                   XDG_CURRENT_DESKTOP="none", PULSE_SERVER="unix:" + str(root / "no-pulse"))
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                    "DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS"):
            env.pop(key, None)
        processes, logs = [], []
        connection = None

        def start(command, name, stdout=None):
            log = (root / (name + ".log")).open("w")
            logs.append(log)
            process = subprocess.Popen(command, env=env, stdout=stdout or log,
                                       stderr=log, start_new_session=True)
            processes.append(process)
            return process

        try:
            daemon = start([args.dbus_daemon, "--nofork", "--print-address=1",
                            "--config-file=" + str(bus_config)], "bus", subprocess.PIPE)
            address = (await asyncio.wait_for(asyncio.to_thread(daemon.stdout.readline), 5)).decode().strip()
            assert address.startswith("unix:")
            env["DBUS_SESSION_BUS_ADDRESS"] = env["DBUS_SYSTEM_BUS_ADDRESS"] = address
            connection = await asyncio.wait_for(MessageBus(bus_address=address).connect(), 5)
            portal = Portal()
            connection.export("/org/freedesktop/portal/desktop", portal)
            connection.export("/org/freedesktop/portal/desktop", Settings())
            await asyncio.wait_for(connection.request_name("org.freedesktop.portal.Desktop"), 5)
            compositor = start([args.labwc, "-C", str(root / "labwc")], "labwc")
            for _ in range(100):
                sockets = [p for p in runtime.glob("wayland-*") if p.is_socket()]
                if sockets:
                    break
                assert compositor.poll() is None, (root / "labwc.log").read_text()
                await asyncio.sleep(.05)
            assert sockets, "Private Wayland compositor did not start"
            env["WAYLAND_DISPLAY"] = sockets[0].name
            client = start([str(Path(args.package) / "bin/gnome-network-displays")], "client")
            # Let GTK construct and present the window; no receiver is selected.
            await asyncio.sleep(4)
            assert client.poll() is None, (root / "client.log").read_text()
            assert (portal.requests > 0) == args.expect_request, (portal.requests, (root / "client.log").read_text())
            print(f"PASS: real hidden GTK startup; ScreenCast requests={portal.requests}")
        finally:
            if connection:
                connection.disconnect()
            for process in reversed(processes):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
            for log in logs:
                log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--labwc", required=True)
    parser.add_argument("--dbus-daemon", required=True)
    parser.add_argument("--expect-request", action="store_true")
    asyncio.run(asyncio.wait_for(main(parser.parse_args()), timeout=35))
