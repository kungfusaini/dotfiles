#!/usr/bin/env python3
"""Rotate only an explicitly entered, foreground tablet workspace."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time

WORKSPACE = "tablet-trial"
ORIENTATIONS = {"normal": 0, "left-up": 1, "bottom-up": 2, "right-up": 3}
SAFE_NAME = re.compile(r"[a-zA-Z0-9_.:-]+\Z")
FLAT = {"undefined", "face-up", "face-down"}


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


class Sensor:
    """Reuse upstream monitor-sensor's D-Bus claim/release and buffer handling."""
    def __init__(self):
        self.process = subprocess.Popen(
            ["stdbuf", "-oL", "monitor-sensor", "--accel"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer = b""
        self.orientation = None
        self.tilt = "undefined"
        self.available = True

    def read(self):
        if self.process.poll() is not None:
            raise RuntimeError("monitor-sensor exited")
        while select.select([self.process.stdout], [], [], 0)[0]:
            chunk = os.read(self.process.stdout.fileno(), 8192)
            if not chunk:
                raise RuntimeError("monitor-sensor stream closed")
            self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            self.consume(line.decode(errors="replace"))
        if not self.available:
            raise RuntimeError("Accelerometer unavailable")
        return self.orientation if self.tilt not in FLAT else None

    def consume(self, line):
        if "No accelerometer" in line or "disappeared" in line:
            self.available = False
            self.orientation = None
        if "Has accelerometer" in line:
            self.available = True
        match = re.search(r"(?:orientation: |orientation changed: )(normal|left-up|right-up|bottom-up|undefined)", line)
        if match:
            self.orientation = match[1] if match[1] in ORIENTATIONS else None
        match = re.search(r"(?:tilt: |Tilt changed: )([a-z-]+)", line)
        if match:
            self.tilt = match[1]

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdout.close()


class Backend:
    def __init__(self):
        self.runtime = Path(os.environ["XDG_RUNTIME_DIR"])
        self.instance = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
        if not self.instance:
            raise RuntimeError("Missing Hyprland instance identity")
        self.policy = json.loads(Path(os.environ["TABLET_ORIENTATION_POLICY"]).read_text())
        self.monitor = self.policy["monitor"]
        names = [self.monitor] + [d["name"] for d in self.policy["devices"]]
        if not all(SAFE_NAME.fullmatch(name) for name in names):
            raise ValueError("Unsafe monitor/device identifier")
        self.journal = self.runtime / "tablet-orientation.json"
        self.config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hypr/hyprland.conf"

    def hypr(self, *args, json_output=False):
        reply = subprocess.run(["hyprctl", *args], check=True, capture_output=True, text=True, timeout=3).stdout
        return json.loads(reply) if json_output else reply.strip()

    def config_token(self):
        stat = self.config.stat()
        return [str(self.config.resolve()), stat.st_mtime_ns, stat.st_size]

    def headless(self):
        try:
            return Path("/run/headless-mode/state").read_text().strip() != "off"
        except FileNotFoundError:
            return False

    def panel(self):
        return next((m for m in self.hypr("monitors", "all", "-j", json_output=True)
                     if m["name"] == self.monitor and not m.get("disabled", False) and m.get("dpmsStatus", True)), None)

    def active(self):
        try:
            state = json.loads((self.runtime / "tablet-workspace.json").read_text())
        except (FileNotFoundError, ValueError):
            return False
        if not isinstance(state, dict):
            return False
        if state.get("enabled") is not True or state.get("instance") != self.instance or self.headless():
            return False
        workspace = self.hypr("activeworkspace", "-j", json_output=True)
        if workspace.get("name") != WORKSPACE or workspace.get("monitor") != self.monitor:
            return False
        panel = self.panel()
        if not panel or panel.get("specialWorkspace", {}).get("id", 0):
            return False
        # Mewtion configures the same buffered IIO device. Never stop it or
        # compete with it to obtain tablet rotation readings. Linux comm is
        # limited to 15 characters: .Mewtion-wrapped becomes .Mewtion-wrappe.
        result = subprocess.run(["pgrep", "-ix", r"mewtion|\.mewtion-wrappe"], capture_output=True, timeout=2)
        if result.returncode != 1:
            return False
        return True

    def snapshot(self):
        panel = self.panel()
        if not panel or panel["transform"] not in range(4):
            raise RuntimeError("Internal panel unavailable or reflected transforms unsupported")
        reported = self.hypr("devices", "-j", json_output=True)
        inputs = []
        for device in self.policy["devices"]:
            group = "touch" if device["kind"] == "touch" else "tablets"
            if not any(d.get("name") == device["name"] for d in reported[group]):
                raise RuntimeError("Built-in input missing: " + device["name"])
            baseline = {}
            for key in ("transform", "output"):
                value = device.get(key)
                if value is None:
                    prefix = "touchdevice" if device["kind"] == "touch" else "tablet"
                    option = self.hypr("getoption", f"input:{prefix}:{key}", "-j", json_output=True)
                    value = option["int" if key == "transform" else "str"]
                baseline[key] = value
            if baseline["transform"] not in range(4):
                raise RuntimeError("Unsupported input baseline transform")
            if baseline["output"] not in ("", "[[Auto]]", "[[EMPTY]]") and not SAFE_NAME.fullmatch(baseline["output"]):
                raise RuntimeError("Unsafe baseline input output")
            inputs.append({"name": device["name"], **baseline})
        return {"instance": self.instance, "config": self.config_token(), "monitor": self.monitor,
                "transform": panel["transform"], "inputs": inputs}

    def load(self):
        try:
            value = json.loads(self.journal.read_text())
        except FileNotFoundError:
            return None
        if not isinstance(value, dict):
            raise RuntimeError("Invalid orientation recovery journal")
        if value.get("instance") != self.instance:
            # Never replay an old compositor's transforms into a new session.
            self.clear()
            return None
        expected = {device["name"] for device in self.policy["devices"]}
        inputs = value.get("inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(device, dict) for device in inputs):
            raise RuntimeError("Invalid saved input list")
        if (value.get("monitor") != self.monitor or value.get("transform") not in range(4)
                or {device.get("name") for device in inputs} != expected or len(inputs) != len(expected)):
            raise RuntimeError("Invalid orientation recovery journal")
        for device in inputs:
            output = device.get("output")
            if device.get("transform") not in range(4) or not isinstance(output, str):
                raise RuntimeError("Invalid saved input baseline")
            if output not in ("", "[[Auto]]", "[[EMPTY]]") and not SAFE_NAME.fullmatch(output):
                raise RuntimeError("Unsafe saved input output")
        return value

    def save(self, value):
        atomic_json(self.journal, value)

    def clear(self):
        self.journal.unlink(missing_ok=True)

    def apply(self, snapshot, delta):
        commands = []
        for device in snapshot["inputs"]:
            output = self.monitor if delta is not None else (device["output"] or "[[EMPTY]]")
            transform = (device["transform"] + delta) % 4 if delta is not None else device["transform"]
            commands.extend([f"keyword device[{device['name']}]:output {output}",
                             f"keyword device[{device['name']}]:transform {transform}"])
        target = (snapshot["transform"] + delta) % 4 if delta is not None else snapshot["transform"]
        # This short form changes only transform on the named monitor rule.
        # The module supplies that named rule without replacing the generic one.
        commands.append(f"keyword monitor {self.monitor},transform,{target}")
        reply = self.hypr("--batch", "; ".join(commands))
        if [line.strip() for line in reply.splitlines() if line.strip()] != ["ok"] * len(commands):
            raise RuntimeError("Hyprland rejected orientation transaction: " + reply)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            panel = self.panel()
            if panel and panel["transform"] == target:
                return
            time.sleep(.05)
        raise RuntimeError("Internal monitor did not apply requested transform")


class Controller:
    def __init__(self, backend, sensor_factory=Sensor):
        self.backend = backend
        self.sensor_factory = sensor_factory
        self.sensor = None
        self.snapshot = backend.load()
        self.initial_config = backend.config_token()
        self.candidate = None
        self.since = 0
        self.applied = None
        self.retry_at = 0
        self.last_tick = None

    def stop_sensor(self):
        if self.sensor:
            self.sensor.close()
            self.sensor = None
        self.candidate = None
        self.applied = None

    def restore(self):
        snapshot = self.backend.load()
        if not snapshot:
            self.snapshot = None
            return True
        if snapshot["config"] != self.backend.config_token():
            # A config reload is authoritative. Do not replay an older input
            # policy over it; exit this daemon and use the newly packaged one.
            self.backend.clear()
            self.snapshot = None
            return True
        if self.backend.headless() or not self.backend.panel():
            return False  # keep journal for recovery when the panel returns
        self.backend.apply(snapshot, None)
        self.backend.clear()
        self.snapshot = None
        return True

    def tick(self, now):
        if self.initial_config != self.backend.config_token():
            self.stop_sensor()
            self.restore()
            raise RuntimeError("Configuration changed; restart controller on next explicit tablet entry")
        # CLOCK_BOOTTIME includes suspend. Reclaim/read the sensor after a long
        # pause instead of applying cached pre-suspend orientation on resume.
        if self.last_tick is not None and now - self.last_tick > 3:
            self.stop_sensor()
            self.restore()
        self.last_tick = now
        if not self.backend.active():
            self.stop_sensor()
            self.restore()
            return
        if now < self.retry_at:
            return
        if not self.sensor:
            # Recover from an interrupted previous controller before accepting
            # a new baseline (including any partially applied transaction).
            if not self.restore():
                return
            self.snapshot = self.backend.snapshot()
            self.sensor = self.sensor_factory()
        try:
            orientation = self.sensor.read()
        except (OSError, RuntimeError):
            self.stop_sensor()
            self.restore()
            self.retry_at = now + 2
            return
        if orientation not in ORIENTATIONS:
            self.candidate = None
            return
        if orientation != self.candidate:
            self.candidate = orientation
            self.since = now
        if now - self.since < .8:
            return
        if orientation == self.applied:
            target = (self.snapshot["transform"] + ORIENTATIONS[orientation]) % 4
            panel = self.backend.panel()
            if panel and panel["transform"] == target:
                return
        # Journal first so partial failures and SIGKILL can be recovered later.
        self.backend.save(self.snapshot)
        try:
            self.backend.apply(self.snapshot, ORIENTATIONS[orientation])
        except Exception:
            self.stop_sensor()
            self.restore()
            raise
        self.applied = orientation


STOP = False


def claim_daemon(backend, lock):
    owner = backend.runtime / "tablet-orientation-owner.json"
    deadline = time.monotonic() + 10
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            atomic_json(owner, {"instance": backend.instance, "config": backend.config_token()})
            return True
        except BlockingIOError:
            try:
                running = json.loads(owner.read_text())
            except (FileNotFoundError, ValueError):
                running = None  # existing daemon is still starting
            if (isinstance(running, dict) and running.get("instance") == backend.instance
                    and running.get("config") == backend.config_token()):
                return False  # healthy singleton already handles this policy
            # A stale daemon needs workspace.lock to observe the changed
            # config and exit. Wait here without holding that workspace lock.
            if time.monotonic() >= deadline:
                raise RuntimeError("Stale orientation controller has not exited; retry explicit entry")
            time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["daemon", "restore"])
    args = parser.parse_args()
    backend = Backend()
    runtime = backend.runtime
    with (runtime / "tablet-orientation-daemon.lock").open("w") as daemon_lock:
        if args.command == "daemon" and not claim_daemon(backend, daemon_lock):
            return 0
        def stop(*_):
            global STOP
            STOP = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        controller = Controller(backend)
        try:
            while True:
                # Same lock order as workspace leave: workspace, then rotation.
                # An explicit restore caller already holds workspace.lock.
                workspace_lock = None
                if args.command == "daemon":
                    workspace_lock = (runtime / "tablet-workspace.lock").open("w")
                    fcntl.flock(workspace_lock, fcntl.LOCK_EX)
                try:
                    with (runtime / "tablet-orientation-operation.lock").open("w") as operation:
                        fcntl.flock(operation, fcntl.LOCK_EX)
                        if args.command == "restore":
                            if not controller.restore():
                                raise RuntimeError("Panel unavailable; restore remains pending")
                            return 0
                        if STOP:
                            controller.stop_sensor()
                            controller.restore()
                            return 0
                        controller.tick(time.clock_gettime(time.CLOCK_BOOTTIME))
                finally:
                    if workspace_lock:
                        workspace_lock.close()
                time.sleep(.2)
        finally:
            try:
                controller.stop_sensor()
                # Keep an unrestored journal; never pretend partial rollback worked.
                with (runtime / "tablet-orientation-operation.lock").open("w") as operation:
                    fcntl.flock(operation, fcntl.LOCK_EX)
                    controller.restore()
            finally:
                if args.command == "daemon":
                    (runtime / "tablet-orientation-owner.json").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"tablet-orientation: {error}", file=sys.stderr)
        sys.exit(1)
