#!/usr/bin/env python3
"""One explicitly requested screen-off/agent-aware suspend, cancelled by input."""
import fcntl
import logging
import os
from pathlib import Path
import signal
import select
import subprocess
import sys
import time

from agent_lid_sleep import agents_working, SETTLE_SECONDS
from hyprland_control import desktop_args


def set_dpms(action):
    result = subprocess.run(['hyprctl', *desktop_args('hyprctl', ['dispatch','dpms',action])],
                            capture_output=True, text=True, check=True, timeout=5)
    if result.stdout.strip() != 'ok':
        raise RuntimeError('Compositor refused display power change: ' + result.stdout.strip())


class SleepRequest:
    def __init__(self):
        self.armed = False
        self.cancelled = False
        self.idle_since = None
        self.submitted = False

    def activity(self, event):
        if event == "idle" and not self.cancelled:
            self.armed = True
        else:
            self.cancelled = True
            self.idle_since = None

    def ready(self, working, now):
        if self.cancelled or not self.armed or self.submitted:
            return False
        if working:
            self.idle_since = None
        elif self.idle_since is None:
            self.idle_since = now
        return self.idle_since is not None and now - self.idle_since >= SETTLE_SECONDS


def main():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    logging.basicConfig(level=logging.INFO, format="agent-screen-sleep: %(message)s")
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    # Keep the inode: unlinking a flock file would allow duplicate requests.
    fd = os.open(runtime / "agent-screen-sleep.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return

    request = SleepRequest()
    loop = GLib.MainLoop()
    monitor = None
    bus = None
    sources = []
    display_off = False
    failed = False
    sleep_started = False
    submitted_at = None

    def cancel(reason):
        request.activity("active")
        logging.info("Cancelled: %s", reason)
        loop.quit()

    def prepare_for_sleep(sleeping):
        nonlocal sleep_started
        if sleeping:
            if request.submitted:
                sleep_started = True
            else:
                cancel("another sleep operation started")
        elif request.submitted and sleep_started:
            logging.info("Resumed; completing request")
            loop.quit()

    def logind_changed(name, old_owner, new_owner):
        cancel("logind owner changed")

    def disconnected():
        cancel("system bus disconnected")

    def activity(stream, condition):
        nonlocal display_off, failed
        # Drain the entire pipe before considering suspend. HUP fails closed even
        # when a final idle event remains buffered.
        if condition & (GLib.IO_HUP | GLib.IO_ERR | GLib.IO_NVAL):
            failed = True
            cancel("activity monitor disconnected")
            return False
        try:
            data = os.read(stream, 4096)
            if not data:
                raise RuntimeError("activity monitor closed")
            events = data.decode("ascii").splitlines()
            if not events or any(event not in ("idle", "active") for event in events):
                raise RuntimeError("invalid activity event")
            # Once logind has accepted sleep, keep the monitor and singleton
            # alive until PrepareForSleep(false), not merely CLI completion.
            if request.submitted:
                return True
            for event in events:
                request.activity(event)
            if request.cancelled:
                cancel("keyboard or pointer activity")
                return False
            if request.armed and not display_off:
                display_off = True
                set_dpms('off')
                logging.info("Display off; waiting for tracked agents")
        except Exception:
            failed = True
            logging.exception("Activity handling failed")
            cancel("activity handling failed")
            return False
        return True

    def tick():
        nonlocal failed, submitted_at
        if request.cancelled:
            loop.quit()
            return False
        try:
            if monitor.poll() is not None:
                raise RuntimeError("activity monitor exited")
            if not bus.get_is_connected():
                raise RuntimeError("system bus disconnected")
            if request.submitted:
                if not sleep_started and time.monotonic() - submitted_at >= 30:
                    raise RuntimeError("logind did not begin sleep within 30 seconds")
                return True
            # Input has higher GLib priority than this timer, but cannot
            # interrupt a synchronous tracker scan. Drain again after scanning.
            if request.ready(agents_working(runtime / "project-object" / "pi-activity"),
                             time.monotonic()):
                context = GLib.MainContext.default()
                while context.pending() and not request.cancelled:
                    context.iteration(False)
                while not request.cancelled and select.select([monitor.stdout], [], [], 0)[0]:
                    if not activity(monitor.stdout.fileno(), GLib.IO_IN):
                        break
                if request.cancelled:
                    return False
                request.submitted = True
                submitted_at = time.monotonic()
                logging.info("Agents settled; suspending")
                subprocess.run(["systemctl", "suspend"], check=True)
                return True
        except Exception:
            failed = True
            logging.exception("Sleep request failed")
            cancel("sleep request failed")
            return False
        return True

    try:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        # Subscribe before checking ownership, closing the restart race.
        bus.add_signal_receiver(logind_changed, signal_name="NameOwnerChanged",
                                dbus_interface="org.freedesktop.DBus",
                                bus_name="org.freedesktop.DBus",
                                path="/org/freedesktop/DBus", arg0="org.freedesktop.login1")
        bus.add_signal_receiver(disconnected, signal_name="Disconnected",
                                dbus_interface="org.freedesktop.DBus.Local")
        bus.get_name_owner("org.freedesktop.login1")
        bus.add_signal_receiver(prepare_for_sleep, signal_name="PrepareForSleep",
                                dbus_interface="org.freedesktop.login1.Manager",
                                bus_name="org.freedesktop.login1",
                                path="/org/freedesktop/login1")
        monitor = subprocess.Popen([sys.argv[1]], stdout=subprocess.PIPE)
        sources.append(GLib.io_add_watch(monitor.stdout.fileno(), GLib.PRIORITY_HIGH,
                          GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR | GLib.IO_NVAL, activity))
        sources.append(GLib.timeout_add(250, tick))
        for sig in (signal.SIGTERM, signal.SIGINT):
            sources.append(GLib.unix_signal_add(
                GLib.PRIORITY_HIGH, sig, lambda: (cancel("signal"), False)[1]))
        loop.run()
    finally:
        for source in sources:
            context = GLib.MainContext.default()
            if context.find_source_by_id(source) is not None:
                GLib.source_remove(source)
        if bus is not None:
            bus.remove_signal_receiver(prepare_for_sleep, signal_name="PrepareForSleep",
                                       dbus_interface="org.freedesktop.login1.Manager",
                                       bus_name="org.freedesktop.login1",
                                       path="/org/freedesktop/login1")
            bus.remove_signal_receiver(logind_changed, signal_name="NameOwnerChanged",
                                       dbus_interface="org.freedesktop.DBus",
                                       bus_name="org.freedesktop.DBus",
                                       path="/org/freedesktop/DBus", arg0="org.freedesktop.login1")
            bus.remove_signal_receiver(disconnected, signal_name="Disconnected",
                                       dbus_interface="org.freedesktop.DBus.Local")
            bus.close()
        if monitor is not None:
            if monitor.poll() is None:
                monitor.terminate()
            try:
                monitor.wait(timeout=3)
            except subprocess.TimeoutExpired:
                monitor.kill()
                monitor.wait()
            monitor.stdout.close()
        if display_off:
            try:
                set_dpms('on')
            except Exception:
                failed = True
                logging.exception('Display restoration failed')
        os.close(fd)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
