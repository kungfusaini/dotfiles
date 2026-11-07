"""Exact-window tablet app lifecycle. Never own/terminate an application's PID.

The normal browser profile may share one process with unrelated desktop windows.
A fresh local-page nonce identifies only the requested NEW window; a dynamic
window tag then protects against address reuse within that long-lived process.
"""
import html
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid


class WindowApps:
    def __init__(self, directory, registry, hypr, dispatch, start_time, workspace="tablet-trial"):
        self.directory = Path(directory)
        self.registry = {a["id"]: a for a in registry if a.get("kind") == "window"}
        self.hypr, self.dispatch, self.start_time = hypr, dispatch, start_time
        self.workspace = workspace
        self.windows = {}
        self.pending = None
        self.launcher = None
        self.launchers = []
        self.error = ""
        self.active = ""
        self.layout = None
        self.ownership_escape = False
        self.instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        path = self.directory / "app-windows.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if saved.get("instance") == self.instance:
                self.windows = {k: v for k, v in saved.get("windows", {}).items() if k in self.registry}

    def save(self):
        path = self.directory / "app-windows.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"instance": self.instance, "windows": self.windows}))
        temporary.chmod(0o600)
        temporary.replace(path)

    def identity(self, client, record):
        try:
            return (client.get("address") == record["address"] and client.get("pid") == record["pid"]
                    and client.get("class") in self.registry[record["id"]]["classes"]
                    and record["tag"] in [t.rstrip("*") for t in client.get("tags", [])]
                    and self.start_time(record["pid"]) == record["start"])
        except (OSError, ValueError, KeyError):
            return False

    def owned(self, app, clients=None):
        record = self.windows.get(app)
        if not record:
            return None
        clients = self.hypr("clients") if clients is None else clients
        parking = record.get("parking", "")
        allowed = (self.workspace, parking) if isinstance(parking, str) and re.fullmatch(r"special:tablet-app-[0-9a-f]{12}", parking) else (self.workspace,)
        return next((c for c in clients if self.identity(c, record)
                     and c.get("workspace", {}).get("name") in allowed
                     and not c.get("pinned") and not c.get("grouped")), None)

    def browser_pids(self, policy):
        result = set()
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit(): continue
            try:
                if proc.stat().st_uid != os.getuid(): continue
                executable = (proc / "exe").readlink().name.lstrip(".").lower()
                if executable.startswith(policy["processPrefix"]): result.add(int(proc.name))
            except (OSError, ValueError):
                continue  # Sandboxed children may be unreadable; their main process is still probed.
        return result

    def check_compatible(self, app):
        if app not in self.registry:
            raise RuntimeError("This app has no real-window integration")
        # Chromium launch switches cannot reconfigure an already-running shared
        # process. Never pretend a forwarded --new-window enabled native IME.
        # Read only the two capability switches; never retain/log browser URLs.
        policy = self.registry[app]
        required = [flag.encode() for flag in policy.get("requiredProcessFlags", [])]
        if not required:
            return {}
        matching = [c for c in self.hypr("clients") if str(c.get("class", "")).lower().startswith(policy["processPrefix"])]
        if any(c.get("xwayland") for c in matching):
            raise RuntimeError("The existing browser uses XWayland; normal startup needs native Wayland configuration before tablet integration. No windows were restarted.")
        # Background browser applications can keep the normal-profile process
        # alive with no compositor windows. Probe same-user executables too;
        # an empty client list is not evidence of a cold launch.
        pids = {c.get("pid") for c in matching} | self.browser_pids(policy)
        verified = {}
        for pid in pids:
            # Chromium may expose its GPU process as the Wayland client PID.
            # Walk only that process's real, same-user ancestry to the browser;
            # never infer capability from an arbitrary sibling process.
            compatible = False
            seen = set()
            for _ in range(16):
                try:
                    pid = int(pid)
                    if pid <= 1 or pid in seen: break
                    seen.add(pid)
                    proc = Path(f"/proc/{pid}")
                    if proc.stat().st_uid != os.getuid(): break
                    identity_start = self.start_time(pid)
                    args = [a for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
                    executable = (proc / "exe").readlink().name.lstrip(".").lower()
                    # Vivaldi rewrites argv into a single process-title field.
                    # Parse that known executable's title too, stopping before
                    # any URL, so page addresses cannot masquerade as flags.
                    if len(args) == 1:
                        args = [a.encode() for a in shlex.split(os.fsdecode(args[0]))]
                    flags = []
                    for arg in args[1:]:
                        if re.match(rb"[A-Za-z][A-Za-z0-9+.-]*:", arg): break
                        flags.append(arg)
                    if executable.startswith(policy["processPrefix"]) and all(flag in flags for flag in required):
                        if self.start_time(pid) != identity_start:
                            raise RuntimeError("Browser process changed during capability verification")
                        verified[pid] = identity_start
                        compatible = True
                        break
                    pid = int((proc / "stat").read_text().rsplit(")", 1)[1].split()[1])
                except (OSError, ValueError, TypeError, IndexError):
                    break
            if not compatible:
                raise RuntimeError("Cannot verify native keyboard support in the running Vivaldi process. Normal Vivaldi startup needs verified native Wayland IME flags before using this preview; no existing windows were changed or restarted.")
        return verified

    def require_compatible(self, app):
        windows = []
        for client in self.hypr("clients"):
            if client.get("class") in self.registry[app]["classes"] and client.get("mapped", False):
                try: windows.append({"address": client["address"], "pid": client["pid"], "start": self.start_time(client["pid"])})
                except (OSError, ValueError): pass
        verified = self.check_compatible(app)
        if self.registry[app].get("warmOnly") and (not verified or not windows):
            raise RuntimeError("Vivaldi cold startup is not enabled: its first normal window may restore other desktop windows. Start a compatible normal Vivaldi window outside tablet mode first; no browser process was started.")
        return {"processes": verified, "windows": windows}

    def verify_launch(self, app, verification):
        if not self.registry[app].get("warmOnly"):
            return
        try:
            if not verification["processes"] or any(self.start_time(pid) != start for pid, start in verification["processes"].items()):
                raise RuntimeError("Verified browser changed before launch; no browser process was started")
            current = self.hypr("clients")
            valid = any(c.get("address") == w["address"] and c.get("pid") == w["pid"]
                        and c.get("class") in self.registry[app]["classes"] and c.get("mapped", False)
                        and self.start_time(w["pid"]) == w["start"]
                        and self.from_authorized_process(w["pid"], verification["processes"])
                        for w in verification["windows"] for c in current)
        except OSError as error:
            raise RuntimeError("Verified browser exited before launch; no replacement was started") from error
        if not valid:
            raise RuntimeError("Verified normal browser window changed before launch; no process was started")

    def open(self, app):
        if app not in self.registry:
            raise RuntimeError("This app has no real-window integration")
        if self.pending:
            raise RuntimeError("An app launch is already pending")
        verification = self.require_compatible(app)
        self.error = ""
        if self.active and self.active != app:
            self.park(self.active)
        self.active = app
        self.layout = None
        client = self.owned(app)
        if client:
            if client.get("workspace", {}).get("name") != self.workspace:
                self.dispatch("movetoworkspacesilent", "name:" + self.workspace + ",address:" + client["address"])
            return  # Reuse only the previously verified exact tablet window.
        self.windows.pop(app, None)
        nonce = uuid.uuid4().hex
        marker = "tablet-launch-" + nonce
        page = self.directory / (marker + ".html")
        page.write_text("<!doctype html><meta charset=utf-8><title>" + html.escape(marker)
                        + "</title><style>body{background:#142a38;color:#eef5f2;font:24px sans-serif;padding:3em}</style>"
                        + "<h1>Vivaldi</h1><p>Your tablet browser is ready. Use the address bar to browse.</p>")
        page.chmod(0o600)
        previous = [c["address"] for c in self.hypr("clients")]
        self.verify_launch(app, verification)
        self.pending = {"id": app, "marker": marker, "page": str(page), "previous": previous,
                        "authorities": verification["processes"], "deadline": time.monotonic() + 15}
        # Product launcher, explicitly scoped to tablet-trial. No alternate
        # profile, debugging port, agent browser route, or guessed window move.
        command = [*self.registry[app]["command"], *self.registry[app].get("openArguments", []), page.as_uri()]
        self.spawn(command)

    def from_authorized_process(self, pid, authorities):
        seen = set()
        for _ in range(16):
            try:
                pid = int(pid)
                if pid <= 1 or pid in seen: return False
                seen.add(pid)
                proc = Path(f"/proc/{pid}")
                if proc.stat().st_uid != os.getuid(): return False
                if pid in authorities and self.start_time(pid) == authorities[pid]: return True
                pid = int((proc / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, TypeError): return False
        return False

    def spawn(self, command):
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith(("PI_", "TABLET_", "PROJECT_OBJECT_", "HL_"))}
        with (self.directory / "app-launch.log").open("a") as output:
            self.launcher = subprocess.Popen(command, env=environment, stdout=output, stderr=output)
            self.launchers.append(self.launcher)

    def geometry(self, monitor, keyboard_inset=0):
        width, height = monitor["width"], monitor["height"]
        if monitor.get("transform", 0) % 2:
            width, height = height, width
        scale = monitor.get("scale", 1)
        # Opaque Home strips cover desktop chrome above/below the normal native
        # window. No focus-dependent fullscreen dispatcher or global rule.
        x, y = int(monitor.get("x", 0)), int(monitor.get("y", 0)) + 32
        w = int(width / scale)
        # Vivaldi's native minimum height is 400px. When IME leaves less room,
        # keep that minimum and let the keyboard overlay the lower app area.
        # The gesture strip still moves above the keyboard; never loop resizing
        # below a client constraint or keep a cover trapped over the editor.
        minimum = self.registry.get(self.active, {}).get("minimumHeight", 0)
        h = max(minimum, int(height / scale) - 88 - int(keyboard_inset))
        if w < 160 or h < 120:
            raise RuntimeError("Not enough room for the tablet app")
        return x, y, w, h

    def policy_changed(self, client, monitor, keyboard_inset=0):
        return self.layout != (client["address"], *self.geometry(monitor, keyboard_inset))

    def placed(self, client, monitor, keyboard_inset=0):
        x, y, w, h = self.geometry(monitor, keyboard_inset)
        return client.get("floating") and client.get("at") == [x, y] and client.get("size") == [w, h]

    def fit(self, client, monitor, keyboard_inset=0):
        x, y, w, h = self.geometry(monitor, keyboard_inset)
        signature = (client["address"], x, y, w, h)
        if signature != self.layout or not self.placed(client, monitor, keyboard_inset):
            target = "address:" + client["address"]
            self.dispatch("setprop", target + " no_anim on")
            self.dispatch("setfloating", target)
            self.dispatch("resizewindowpixel", f"exact {w} {h},{target}")
            self.dispatch("movewindowpixel", f"exact {x} {y},{target}")
            self.layout = signature
        # Re-check actual geometry on the next controller tick before revealing.
        return self.placed(client, monitor, keyboard_inset)

    def tick(self):
        self.launchers = [p for p in self.launchers if p.poll() is None]
        if self.launcher and self.launcher.poll() is not None:
            self.launcher = None  # Reap launcher; it may have handed off to an existing process.
        if not self.windows and not self.pending:
            return
        clients = self.hypr("clients")
        changed = False
        for app in list(self.windows):
            if not self.owned(app, clients):
                # Grouping/pinning a presented app is an explicit move back to
                # desktop window management. Do not hide that now-unowned focus
                # under Home or move a whole group as if it were our window.
                record = self.windows[app]
                if any(self.identity(c, record) and c.get("workspace", {}).get("name") == self.workspace
                       and (c.get("pinned") or c.get("grouped")) for c in clients):
                    self.ownership_escape = True
                del self.windows[app]  # Closed, moved by user, replaced, or untagged: never reclaim it.
                changed = True
        pending = self.pending
        if pending:
            candidates = [c for c in clients if c.get("address") not in pending["previous"]
                          and c.get("class") in self.registry[pending["id"]]["classes"]
                          and pending["marker"] in c.get("title", "") and c.get("mapped", False)]
            if len(candidates) > 1:
                self.fail("Ambiguous browser launch; no window was claimed")
            elif len(candidates) == 1:
                client = candidates[0]
                if self.registry[pending["id"]].get("warmOnly") and not self.from_authorized_process(client["pid"], pending["authorities"]):
                    self.fail("The verified browser process changed during launch; no replacement window was claimed")
                elif (not re.fullmatch(r"0x[0-9a-f]+", client["address"]) or client.get("pinned")
                        or client.get("grouped") or client.get("fullscreen")):
                    self.fail("Browser window changed during launch; refusing to claim it")
                else:
                    pid = client["pid"]
                    if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
                        raise RuntimeError("Browser belongs to another user")
                    record = {"id": pending["id"], "address": client["address"], "pid": pid,
                              "start": self.start_time(pid), "tag": "tablet-app-" + uuid.uuid4().hex,
                              "parking": "special:tablet-app-" + uuid.uuid4().hex[:12]}
                    self.dispatch("tagwindow", "+" + record["tag"] + " address:" + record["address"])
                    # The unique nonce, not the current workspace or shared PID,
                    # authorizes placement of this exact newly created window.
                    if client.get("workspace", {}).get("name") != self.workspace:
                        self.dispatch("movetoworkspacesilent", "name:" + self.workspace + ",address:" + record["address"])
                    self.windows[record["id"]] = record
                    self.pending = None
                    changed = True
            elif time.monotonic() >= pending["deadline"]:
                self.fail("Browser launch could not be verified; no existing window was moved or closed")
        if changed:
            self.save()

    def fail(self, message):
        self.error = message
        self.pending = None
        self.active = ""
        # An unverified launch can still exist. Never close it or kill its PID.

    def unmanaged_clients(self):
        clients = self.hypr("clients")
        managed = {c["address"] for app in self.windows if (c := self.owned(app, clients))}
        return [c for c in clients if c.get("mapped", True) and c.get("workspace", {}).get("name") == self.workspace
                and c.get("address") not in managed]

    def park(self, app):
        if self.unmanaged_clients():
            raise RuntimeError("Finish other tablet windows/dialogs or return to desktop management before going Home")
        client = self.owned(app)
        if not client:
            return
        record = self.windows[app]
        if not re.fullmatch(r"special:tablet-app-[0-9a-f]{12}", str(record.get("parking", ""))):
            record["parking"] = "special:tablet-app-" + uuid.uuid4().hex[:12]
        self.save()  # Journal the exact destination before moving anything.
        self.dispatch("movetoworkspacesilent", record["parking"] + ",address:" + client["address"])
        if self.active == app:
            self.active = ""
        self.layout = None

    def release(self):
        # Explicit tablet exit returns parked windows to the ordinary tablet
        # workspace, silently. Browser processes and unrelated windows survive.
        for app in list(self.windows):
            client = self.owned(app)
            if client and client.get("workspace", {}).get("name") != self.workspace:
                try:
                    self.dispatch("movetoworkspacesilent", "name:" + self.workspace + ",address:" + client["address"])
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    if self.owned(app): raise  # A concurrent close needs no recovery.

    def focus(self, app):
        client = self.owned(app)
        if not client or client.get("workspace", {}).get("name") != self.workspace:
            raise RuntimeError("The verified app window is not presented in the tablet workspace")
        self.dispatch("focuswindow", "address:" + client["address"])

    def close(self, app):
        client = self.owned(app)
        if not client or client.get("workspace", {}).get("name") != self.workspace:
            raise RuntimeError("No presented tablet window to close")
        # Graceful per-window request: beforeunload/confirmation is not bypassed.
        self.dispatch("closewindow", "address:" + client["address"])

    def status(self):
        return {"windows": {k: {"address": v["address"], "pid": v["pid"], "tag": v["tag"]} for k, v in self.windows.items()},
                "pending": self.pending["id"] if self.pending else "", "active": self.active}
