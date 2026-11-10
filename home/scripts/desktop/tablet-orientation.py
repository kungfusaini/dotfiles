#!/usr/bin/env python3
"""Rotate only an explicitly entered, foreground tablet workspace."""
import argparse
from contextlib import nullcontext
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
STABILITY_SECONDS = .15
GATE_INTERVAL = .2


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

    def wait(self, timeout):
        # Wake on upstream orientation output, not another desktop polling tick.
        select.select([self.process.stdout], [], [], timeout)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdout.close()


class RotationFade:
    """One disposable, screen-bound cover; QML also has its own hard timeout."""
    def __init__(self, monitor):
        self.monitor = monitor
        self.process = None
        self.deadline = None

    def timeout(self, reserve=0, cap=.2):
        remaining = self.deadline - time.monotonic() - reserve
        if remaining < .05:
            raise RuntimeError("Rotation cover deadline exhausted")
        return min(cap, remaining)

    def ensure_covered(self, reserve):
        if self.call("status", timeout=self.timeout(reserve)) != "covered":
            raise RuntimeError("Rotation cover lost before transform")
        self.timeout(reserve)  # the status request itself consumed budget

    def call(self, method, timeout=.4):
        if self.process.poll() is not None:
            raise RuntimeError("Rotation fade exited")
        result = subprocess.run(
            ["quickshell", "ipc", "--pid", str(self.process.pid), "call", "rotationFade", method],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()

    def wait_for(self, phase, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                if self.call("status") == phase:
                    return
            except (OSError, RuntimeError, subprocess.SubprocessError):
                pass  # IPC can register a moment after the process starts.
            time.sleep(.025)
        raise RuntimeError("Rotation fade did not acknowledge " + phase)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=.5)

    def __enter__(self):
        try:
            env = dict(os.environ, TABLET_FADE_MONITOR=self.monitor)
            self.process = subprocess.Popen(
                ["quickshell", "--path", os.environ["TABLET_ROTATION_FADE_QML"]], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            self.wait_for("ready", 1.5)
            # Conservative deadline: leave margin before QML's independent
            # three-second watchdog, measured before dispatching cover.
            self.deadline = time.monotonic() + 2.6
            self.call("cover")
            self.wait_for("covered", 1)
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is None:
                try:
                    self.call("reveal")
                    self.wait_for("done", .7)
                except (OSError, RuntimeError, subprocess.SubprocessError) as failure:
                    # A cosmetic reveal failure must not undo a correct input
                    # mapping. Killing this owned surface also clears it.
                    print(f"tablet-orientation: clearing failed fade: {failure}", file=sys.stderr)
        finally:
            self.close()


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
        self.native = os.environ.get("TABLET_ORIENTATION_SESSION") == "native"
        self.prefix = "tablet-native-orientation" if self.native else "tablet-orientation"
        self.journal = self.runtime / (self.prefix + ".json")
        self.config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hypr/hyprland.conf"

    def hypr(self, *args, json_output=False, timeout=3):
        reply = subprocess.run(["hyprctl", *args], check=True, capture_output=True, text=True, timeout=timeout).stdout
        return json.loads(reply) if json_output else reply.strip()

    def config_token(self):
        stat = self.config.stat()
        return [str(self.config.resolve()), stat.st_mtime_ns, stat.st_size]

    def headless(self):
        try:
            return Path("/run/headless-mode/state").read_text().strip() != "off"
        except FileNotFoundError:
            return False

    def panel(self, timeout=3):
        return next((m for m in self.hypr("monitors", "all", "-j", json_output=True, timeout=timeout)
                     if m["name"] == self.monitor and not m.get("disabled", False) and m.get("dpmsStatus", True)), None)

    def active(self, timeout=3):
        native = getattr(self, "native", False)
        try:
            path = self.runtime / ("tablet-proof/recovery.json" if native else "tablet-workspace.json")
            state = json.loads(path.read_text())
            if native:
                state = state["window"]
                owner = state["owner"]
                # A journal is not a live session: require the exact backend
                # lifetime, not a recycled PID or a leftover recovery record.
                actual = Path(f'/proc/{int(owner["pid"])}/stat').read_text().rsplit(')', 1)[1].split()[19]
                if actual != owner["start"] or not state.get("native"):
                    return False
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            return False
        if not isinstance(state, dict):
            return False
        enabled = state.get("rotation_enabled") if native else state.get("enabled")
        if enabled is not True or state.get("instance") != self.instance or self.headless():
            return False
        workspace = self.hypr("activeworkspace", "-j", json_output=True, timeout=timeout)
        expected = state.get("workspace") if native else WORKSPACE
        if workspace.get("name") != expected or workspace.get("monitor") != self.monitor:
            return False
        if native and not state.get("home_only"):
            focus = self.hypr("activewindow", "-j", json_output=True, timeout=timeout)
            if focus.get("address") != state.get("address") or focus.get("stableId") != state.get("stableId"):
                return False
        panel = self.panel(timeout=timeout)
        if not panel or panel.get("specialWorkspace", {}).get("id", 0):
            return False
        # Mewtion configures the same buffered IIO device. Never stop it or
        # compete with it to obtain tablet rotation readings. Linux comm is
        # limited to 15 characters: .Mewtion-wrapped becomes .Mewtion-wrappe.
        result = subprocess.run(["pgrep", "-ix", r"mewtion|\.mewtion-wrappe"], capture_output=True, timeout=min(2, timeout))
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

    def settle_delay(self):
        try:
            groups = self.hypr("animations", "-j", json_output=True)[0]
            by_name = {item["name"]: item for item in groups}
            for name in ("windowsMove", "windows", "global"):
                item = by_name.get(name, {})
                if item.get("overridden"):
                    return min(1., max(.05, float(item["speed"]) / 10 + .05)) if item["enabled"] else .05
        except (ValueError, TypeError, KeyError, IndexError, OSError, subprocess.SubprocessError):
            pass
        return .55

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
        panel = self.panel()
        if not panel:
            raise RuntimeError("Internal panel unavailable before rotation")
        changing = panel["transform"] != target
        settle = self.settle_delay() if changing else 0
        if changing and (self.headless() or (delta is not None and not self.active())):
            raise RuntimeError("Rotation gate closed before fade")
        with RotationFade(self.monitor) if changing else nullcontext() as cover:
            reserve = settle + .3
            if changing:
                # One panel query plus active()'s two IPC queries and pgrep:
                # share the budget instead of granting each its full remainder.
                query_timeout = min(.2, cover.timeout(reserve, cap=.8) / 4)
                if (not self.panel(timeout=query_timeout) or self.headless()
                        or (delta is not None and not self.active(timeout=query_timeout))):
                    raise RuntimeError("Rotation gate closed while fading")
                # Revalidate the owned cover after potentially slow gate IPC,
                # immediately before the first mutating request.
                cover.ensure_covered(reserve)
            reply = self.hypr("--batch", "; ".join(commands),
                              timeout=cover.timeout(reserve, cap=3) if changing else 3)
            if [line.strip() for line in reply.splitlines() if line.strip()] != ["ok"] * len(commands):
                raise RuntimeError("Hyprland rejected orientation transaction: " + reply)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                panel = self.panel(timeout=cover.timeout(reserve) if changing else 3)
                if panel and panel["transform"] == target:
                    if changing:
                        cover.timeout(reserve)  # don't sleep beyond cover life
                    # Keep the opaque cover through the inherited window-resize
                    # animation instead of exposing its stretched old buffer.
                    time.sleep(settle)
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

    def next_wait(self, now):
        if self.candidate is not None and self.candidate != self.applied:
            return min(GATE_INTERVAL, max(0., self.since + STABILITY_SECONDS - now))
        return GATE_INTERVAL

    def wait_for_work(self, now):
        delay = self.next_wait(now)
        if self.sensor:
            self.sensor.wait(delay)
        else:
            time.sleep(delay)

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
        if now - self.since < STABILITY_SECONDS:
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
    owner = backend.runtime / (getattr(backend, "prefix", "tablet-orientation") + "-owner.json")
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
    prefix = getattr(backend, "prefix", "tablet-orientation")
    with (runtime / (prefix + "-daemon.lock")).open("w") as daemon_lock:
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
                controller.wait_for_work(time.clock_gettime(time.CLOCK_BOOTTIME))
        finally:
            try:
                controller.stop_sensor()
                # Keep an unrestored journal; never pretend partial rollback worked.
                with (runtime / "tablet-orientation-operation.lock").open("w") as operation:
                    fcntl.flock(operation, fcntl.LOCK_EX)
                    controller.restore()
            finally:
                if args.command == "daemon":
                    (runtime / (prefix + "-owner.json")).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"tablet-orientation: {error}", file=sys.stderr)
        sys.exit(1)
