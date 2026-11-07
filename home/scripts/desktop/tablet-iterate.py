#!/usr/bin/env python3
"""Reversible tablet iteration trial. Never start another Pi or record implicitly."""
import argparse
import fcntl
import json
import hashlib
import os
from pathlib import Path
import re
import runpy
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

WORKSPACE = "tablet-trial"
NIX_STORE = Path("/nix/store")
# Already deployed with no_anim; new namespace policies would need deployment.
GUARDED_NAMESPACE = "tablet-rotation-fade"
PANEL_ENV = ("PATH", "QT_QUICK_CONTROLS_STYLE", "QT_STYLE_OVERRIDE", "QML_IMPORT_PATH",
             "QT_PLUGIN_PATH", "GTK_THEME", "G_RESOURCE_OVERLAYS", "SQUEEKBOARD_KEYBOARDSDIR",
             "GIO_EXTRA_MODULES", "XDG_DATA_DIRS")


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, capture_output=True, timeout=5, **kwargs)


def hypr(*args):
    return json.loads(run("hyprctl", *args, "-j", text=True).stdout)


def dispatch(command, argument):
    run("hyprctl", "dispatch", command, argument)


def directory():
    name = "tablet-chat" if os.environ.get("TABLET_NATIVE_CHAT") == "1" else "tablet-iterate"
    path = Path(os.environ["XDG_RUNTIME_DIR"]) / name
    if path.is_symlink():
        raise RuntimeError("Unsafe iteration runtime directory")
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError("Iteration runtime directory is not owned by this user")
    path.chmod(0o700)
    return path


def save(name, value):
    path = directory() / name
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def start_time(pid):
    # comm can contain spaces/parentheses; fields after its final ')' are stable.
    return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]


def workspace_name(value):
    if not value or any(c in value for c in ",\n\r"):
        raise RuntimeError("Unsafe workspace name")
    return value


def binding():
    if os.environ.get("TABLET_NATIVE_CHAT") == "1":
        context = json.loads((directory() / "context.json").read_text())
        cwd = Path(context["cwd"])
        if not cwd.is_absolute() or not cwd.is_dir():
            raise RuntimeError("The registered tablet workspace is no longer available")
        os.environ.update(context.get("project", {}))
        os.environ["TABLET_CHAT_CWD"] = str(cwd)
        key = hashlib.sha256(str(cwd).encode()).hexdigest()[:16]
        sessions = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "tablet-chat" / key
        sessions.mkdir(parents=True, exist_ok=True, mode=0o700)
        sessions.chmod(0o700)
        os.environ["TABLET_CHAT_SESSIONS"] = str(sessions)
        draft = sessions / "draft.txt"
        try:
            descriptor = os.open(draft, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
        return {"instance": os.environ["HYPRLAND_INSTANCE_SIGNATURE"], "workspace": WORKSPACE,
                "pid": 0, "start": "", "address": "0x0", "stream": "tablet-native"}, {}
    value = json.loads((directory() / "binding.json").read_text())
    if value["instance"] != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        raise RuntimeError("Pi binding belongs to an old compositor; bind again")
    if not re.fullmatch(r"0x[0-9a-f]+", value["address"]):
        raise RuntimeError("Invalid Pi client address")
    workspace_name(value["workspace"])
    if start_time(value["pid"]) != value["start"]:
        raise RuntimeError("The bound Pi terminal was replaced; bind again")
    clients = hypr("clients")
    client = next((c for c in clients if c["address"] == value["address"] and c["pid"] == value["pid"]), None)
    if not client or client.get("class") != "kitty" or value["stream"] not in client.get("title", ""):
        raise RuntimeError("The exact bound Pi stream is not open; no replacement will be started")
    return value, client


def bind():
    if (directory() / "control.sock").exists():
        raise RuntimeError("Close the active iteration trial before rebinding")
    if os.environ.get("TABLET_NATIVE_CHAT") == "1":
        names = ("PROJECT_OBJECT_ID", "PROJECT_OBJECT_NAME", "PROJECT_OBJECT_HOME", "PROJECT_OBJECT_MAIN_DIRECTORY",
                 "PROJECT_OBJECT_STREAM_ID", "PROJECT_OBJECT_STREAM_NAME", "PROJECT_OBJECT_STREAM_HOME", "PROJECT_OBJECT_WORKSPACE_NAME")
        save("context.json", {"cwd": str(Path.cwd().resolve()),
                              "project": {k: os.environ[k] for k in names if k in os.environ}})
        return
    stream = os.environ.get("PROJECT_OBJECT_STREAM_ID", "")
    pid = int(os.environ.get("KITTY_PID", "0"))
    if not stream or not pid:
        raise RuntimeError("Bind from the intended Project Object Pi terminal")
    client = next((c for c in hypr("clients") if c["pid"] == pid and c.get("class") == "kitty"
                   and stream in c.get("title", "")), None)
    if not client:
        raise RuntimeError("Cannot identify this exact Pi terminal")
    value = {"instance": os.environ["HYPRLAND_INSTANCE_SIGNATURE"], "stream": stream,
             "pid": pid, "start": start_time(pid), "address": client["address"],
             "workspace": workspace_name(client["workspace"]["name"])}
    save("binding.json", value)


class Trial:
    def __init__(self, target=None):
        self.target = target if target is not None else binding()[0]
        self.native_chat = os.environ.get("TABLET_NATIVE_CHAT") == "1"
        self.automatic = os.environ.get("TABLET_AUTOMATIC") == "1"
        self.pi_started = os.environ.get("TABLET_START_VIEW") != "home"
        self.settings = []
        self.keyboard = None
        self.shell = None
        self.stage = None
        self.entry_pending = False
        self.entry_deadline = 0
        self.agent = None
        self.replacement = None
        self.retired_ui = None
        self.retired_deadline = 0
        self.ui_update = {}
        self.panel_commands = []
        self.entered = False
        self.borrowed = False
        self.window_restore = None
        self.layout_signature = None
        self.recording = False
        self.voice_token = None
        self.voice_pending = False
        self.voice_guard = False
        self.voice_daemon = None
        self.voice_identity = None
        self.voice_runtime = directory() / "voice-runtime"
        self.voice_env = dict(os.environ, XDG_RUNTIME_DIR=str(self.voice_runtime),
                              PIPEWIRE_RUNTIME_DIR=os.environ["XDG_RUNTIME_DIR"],
                              PULSE_SERVER=os.environ.get("PULSE_SERVER", "unix:" + os.environ["XDG_RUNTIME_DIR"] + "/pulse/native"))
        if os.environ.get("WAYLAND_DISPLAY"):
            self.voice_env["WAYLAND_DISPLAY"] = str(Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"])
        self.transcriber = None
        self.transcript = directory() / "transcript.txt"
        self.view = "home"
        self.error = ""
        self.stopping = False
        self.owns_journal = False
        self.recovery_children = []
        self.window_apps = None
        self.external_ready = False
        self.close_after_reveal = None

    def apps(self):
        if self.window_apps is None:
            source = os.environ.get("TABLET_APPS_MODULE", str(Path(__file__).with_name("tablet_apps.py")))
            registry = json.loads(Path(os.environ["TABLET_APPS_REGISTRY"]).read_text())
            module = runpy.run_path(source)
            self.window_apps = module["WindowApps"](directory(), registry, hypr, self.app_dispatch, start_time)
        return self.window_apps

    @staticmethod
    def app_dispatch(command, argument):
        result = run("hyprctl", "dispatch", command, argument, text=True)
        if result.stdout.strip() != "ok":
            raise RuntimeError("App window operation refused: " + result.stdout.strip())

    def app_action(self, command, app, frontend):
        if (not self.native_chat or not self.shell or self.shell.poll() is not None or frontend != self.shell.pid
                or not self.foreground() or not self.safe() or self.replacement):
            raise RuntimeError("App navigation requires the current foreground frontend")
        if self.recording or self.transcriber or self.voice_pending or self.voice_guard or self.transcript.exists():
            raise RuntimeError("Finish or cancel dictation before switching apps")
        if self.agent_state().get("question"):
            raise RuntimeError("Finish the pending question before switching apps")
        apps = self.apps()
        if app not in apps.registry or apps.pending:
            raise RuntimeError("Invalid app or a launch is already pending")
        self.close_after_reveal = None
        if command == "app-close":
            if not apps.owned(app):
                raise RuntimeError("No verified tablet window to close")
            # Present the requested window before closing, so browser confirmation
            # is visible even when its card was dismissed from Home or Pi.
            if self.view == "external" and apps.active == app and self.external_ready and not self.entry_pending:
                apps.focus(app)
                apps.close(app)
                return self.status()
            self.close_after_reveal = app
        apps.require_compatible(app)
        self.external_ready = False
        self.cover_view("external", force=self.view == "external" and apps.active != app)
        try:
            apps.open(app)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            self.fail_external(str(error))
        return self.status()

    def fail_external(self, message):
        self.close_after_reveal = None
        self.external_ready = False
        self.error = message
        if self.window_apps:
            if self.window_apps.unmanaged_clients():
                # An unowned dialog/restored window must never inherit focus
                # invisibly behind Home. Leave ordinary desktop management and
                # its windows intact rather than guessing which window to move.
                self.stopping = True
                return
            active = self.window_apps.active
            if active and self.window_apps.owned(active):
                try:
                    self.window_apps.park(active)
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    if self.window_apps.owned(active):
                        # Do not paint Home over a surviving focused browser.
                        # A persistent parking failure requires safety cleanup,
                        # not an apparently successful but input-unsafe Home.
                        raise RuntimeError("Cannot safely background the native app; Home was not revealed: " + str(error)) from error
            self.window_apps.fail(message)
        self.cover_view("home")

    def prepare_app_workspace(self):
        apps = self.apps()
        apps.tick()
        if apps.unmanaged_clients():
            raise RuntimeError("Tablet workspace contains unowned windows/dialogs; no existing window was moved or closed")
        for app in list(apps.windows):
            apps.park(app)  # Entry Home must never cover a focused native app from a prior trial.

    def setting(self, schema, key, value):
        old = run("gsettings", "get", schema, key, text=True).stdout.strip()
        # Persist recovery before mutation, not after starting a child.
        self.settings.append([schema, key, old, value])
        self.journal()
        run("gsettings", "set", schema, key, value)

    def journal(self):
        children = [{"pid": p.pid, "start": start_time(p.pid)}
                    for p in (self.keyboard, self.shell, self.stage, self.agent, self.retired_ui,
                              self.replacement.get("process") if self.replacement else None,
                              self.voice_daemon, self.transcriber) if p and p.poll() is None]
        children.extend(self.recovery_children)
        save("recovery.json", {"target": self.target, "settings": self.settings,
                               "borrowed": self.borrowed, "entered": self.entered, "window": self.window_restore,
                               "panels": self.panel_commands, "children": children,
                               "voice": self.voice_guard or self.recording or self.voice_pending,
                               "voice_owner": self.voice_identity})
        self.owns_journal = True

    def foreground(self):
        return hypr("activeworkspace").get("name") == WORKSPACE

    def safe(self):
        try:
            headless = Path("/run/headless-mode/state").read_text().strip() != "off"
        except FileNotFoundError:
            headless = False
        return not headless and any(m["name"] == "eDP-1" and m.get("dpmsStatus", True)
                                   and not m.get("disabled", False) for m in hypr("monitors"))

    def setup(self):
        if (directory() / "recovery.json").exists():
            raise RuntimeError("Previous trial needs tablet-iterate recover first")
        if not self.safe() or hypr("activeworkspace").get("monitor") != "eDP-1":
            raise RuntimeError("Use the awake laptop display with headless mode off")
        for name in ("squeekboard", "wvkbd", "wvkbd-mobintl"):
            result = subprocess.run(["pgrep", "-x", name], capture_output=True)
            if result.returncode == 0:
                raise RuntimeError("An existing keyboard is active; refusing to replace it")
        self.verify_presentation_policy()
        source = self.selected_ui()
        self.start_stage(source)
        if self.stopping:
            raise RuntimeError("Tablet entry cancelled")
        # Reuse the recovered, successful input-method configuration.
        self.setting("org.gnome.desktop.a11y.applications", "screen-keyboard-enabled", "true")
        self.setting("sm.puri.Squeekboard", "scale-in-horizontal-screen-orientation", "1.45")
        self.setting("sm.puri.Squeekboard", "layout-shape-changes-to-fit-panel", "true")
        if self.stopping:
            raise RuntimeError("Tablet entry cancelled")
        # Validate coverage before claiming workspace ownership, so a failed
        # cover cannot undo another actor's already-active tablet workspace.
        self.wait_stage()
        if self.native_chat and os.environ.get("TABLET_APPS_MODULE"):
            self.prepare_app_workspace()
        state = Path(os.environ["XDG_RUNTIME_DIR"]) / "tablet-workspace.json"
        previous = json.loads(state.read_text()) if state.exists() else {}
        # Fold entry also owns cleanup when replacing the old panel in place.
        self.entered = self.automatic or not (previous.get("enabled") and self.foreground())
        self.journal()
        run("tablet-workspace", "enter-fold" if self.automatic else "enter-iteration")
        # Retire only the exact old tablet panel, not arbitrary Quickshell apps.
        expected = Path(os.environ["TABLET_NORMAL_PANEL"]).read_bytes()
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                args = [os.fsdecode(a) for a in (path / "cmdline").read_bytes().split(b"\0") if a]
                if path.stat().st_uid != os.getuid() or not args or "quickshell" not in Path(args[0]).name:
                    continue
                for option in ("--path", "-p"):
                    if option in args:
                        panel_source = Path(args[args.index(option) + 1])
                        if panel_source.is_file() and panel_source.read_bytes() == expected:
                            # Keep only non-secret rendering/runtime settings,
                            # not the original process's complete environment.
                            original_env = {}
                            for raw in (path / "environ").read_bytes().split(b"\0"):
                                key, separator, value = raw.partition(b"=")
                                if separator and os.fsdecode(key) in PANEL_ENV:
                                    original_env[os.fsdecode(key)] = os.fsdecode(value)
                            self.panel_commands.append({"argv": args, "environment": original_env})
                            self.journal()
                            os.kill(int(path.name), signal.SIGTERM)
            except (OSError, IndexError):
                continue
        with (directory() / "keyboard.log").open("a") as output:
            self.keyboard = subprocess.Popen(["squeekboard"], stdout=output, stderr=output)
        self.journal()
        if self.native_chat:
            with (directory() / "agent.log").open("a") as output:
                environment = dict(session_environment(), TABLET_DEFER_PI="0" if self.pi_started else "1")
                self.agent = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_AGENT_QML"]], env=environment, stdout=output, stderr=output)
            self.journal()
        with (directory() / "surface.log").open("a") as output:
            self.shell = subprocess.Popen(["quickshell", "--path", source], stdout=output, stderr=output)
        self.entry_pending = True
        self.entry_deadline = time.monotonic() + 20
        self.journal()

    def selected_ui(self):
        source = os.environ["TABLET_ITERATION_QML"]
        if self.native_chat:
            current = chat_state() / "current-ui.json"
            if current.exists():
                try:
                    selected = json.loads(current.read_text())
                    source = str(ui_bundle(selected["bundle"], selected["root"]) / "iteration.qml")
                except (OSError, ValueError, KeyError, RuntimeError):
                    self.error = "Saved UI is incompatible; using the packaged interface"
        return source

    def verify_presentation_policy(self):
        # Hyprland layers JSON reports alpha.goal(), NOT current animation
        # opacity. Only the existing no_anim namespace makes that a safe gate.
        path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hypr/hyprland.conf"
        pattern = r"(?m)^\s*layerrule\s*=\s*match:namespace\s+\^tablet-rotation-fade\$\s*,\s*no_anim\s+on\s*$"
        if not path.is_file() or not re.search(pattern, path.read_text()):
            raise RuntimeError("Safe tablet presentation requires the deployed tablet no_anim policy; refusing workspace entry")

    def start_stage(self, source):
        environment = dict(os.environ, TABLET_STAGE_OWNER_PID=str(os.getpid()),
                           TABLET_STAGE_OWNER_START=start_time(os.getpid()),
                           TABLET_STAGE_ASSETS=str(Path(source).parent))
        with (directory() / "stage.log").open("a") as output:
            self.stage = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_STAGE_QML"]],
                                          env=environment, stdout=output, stderr=output)
        self.journal()
        self.wait_stage()

    def layer_opaque(self, process, namespace):
        if not process or process.poll() is not None:
            return False
        monitor = next((m for m in hypr("monitors") if m["name"] == "eDP-1"), None)
        if not monitor:
            return False
        width, height = monitor["width"], monitor["height"]
        if monitor.get("transform", 0) % 2: width, height = height, width
        scale = monitor.get("scale", 1)
        inset = monitor.get("reserved", [0, 0, 0, 0])[3] if namespace == "tablet-native-chat" else 0
        levels = hypr("layers").get("eDP-1", {}).get("levels", {})
        level = "1" if namespace in ("tablet-stage-backdrop", "tablet-iteration-backdrop") else "3"
        matching = [layer for layer in levels.get(level, [])
                    if layer.get("pid") == process.pid and layer.get("namespace") == GUARDED_NAMESPACE]
        # Never mistake an old remapping/fading surface for the replacement.
        return (len(matching) == 1 and matching[0].get("alpha", 0) >= .999
                and matching[0].get("w", 0) >= int(width / scale)
                and matching[0].get("h", 0) >= int(height / scale) - inset)

    def stage_ready(self):
        state = json.loads(self.ipc(self.stage, "tabletStage", "status"))
        self.stage_observation = state
        return (state["cover"] and state["backdrop"]
                and self.layer_opaque(self.stage, "tablet-stage-cover")
                and self.layer_opaque(self.stage, "tablet-stage-backdrop"))

    def wait_stage(self):
        deadline = time.monotonic() + 6
        while not self.stopping and time.monotonic() < deadline:
            try:
                if self.stage_ready(): return
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                pass  # IPC registration/rendering can lag process creation.
            time.sleep(.025)
        raise RuntimeError("Tablet cover did not become rendered and compositor-opaque; workspace not switched: " + json.dumps(getattr(self, "stage_observation", {})))

    def cover_view(self, view, force=False):
        if self.stage and (self.view != view or force):
            self.verify_presentation_policy()
            if not self.entry_pending:
                self.ipc(self.stage, "tabletStage", "cover", "Opening app…" if view == "external" else "Opening Pi…" if view == "pi" else "Returning Home…")
                self.wait_stage()
            self.entry_pending = True
            self.entry_deadline = time.monotonic() + 20
        self.view = view

    def reveal_entry(self):
        if not self.entry_pending:
            return
        if time.monotonic() > self.entry_deadline:
            if self.view == "external":
                self.fail_external("Native app could not be presented safely; its window was left intact")
                return
            raise RuntimeError("App presentation timed out under the tablet cover")
        try:
            self.verify_presentation_policy()
            ready = json.loads(self.ipc(self.shell, "tabletUi", "status"))
            namespace = ("tablet-native-chat" if self.view == "pi" else "tablet-iteration-home") if self.native_chat else "tablet-iteration-backdrop"
            if self.view == "external" and (not self.external_ready or not ready.get("externalReady")):
                return
            if (ready.get("view") == self.view and ready.get("rendered") and (not self.native_chat or ready.get("draftRestored"))
                    and (not self.native_chat or ready.get("connected"))
                    and self.layer_opaque(self.shell, namespace) and self.stage_ready()):
                self.ipc(self.stage, "tabletStage", "reveal")
                self.entry_pending = False
                if self.view == "external":
                    closing, self.close_after_reveal = self.close_after_reveal, None
                    try:
                        self.apps().focus(self.apps().active)
                        if closing:
                            self.apps().close(closing)
                    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                        self.fail_external(str(error))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            pass

    def ipc(self, process, target, method, *arguments):
        if not process or process.poll() is not None:
            raise RuntimeError("Tablet process is unavailable")
        return run("quickshell", "ipc", "--pid", str(process.pid), "call", target, method, *arguments, text=True).stdout

    def agent_state(self):
        return json.loads(self.ipc(self.agent, "tabletAgent", "snapshot"))

    def queue_ui(self, bundle, root):
        if not self.native_chat or self.replacement:
            raise RuntimeError("A UI update is already pending or native chat is not running")
        source = ui_bundle(bundle, root)
        self.replacement = {"bundle": bundle, "root": root, "source": str(source / "iteration.qml"), "token": uuid.uuid4().hex}
        self.error = ""
        self.ui_update = {"phase": "queued", "token": self.replacement["token"]}
        return self.ui_update

    def ui_tick(self):
        if self.retired_ui:
            if self.retired_ui.poll() is None:
                if time.monotonic() <= self.retired_deadline:
                    return  # Never overwrite ownership with another handoff.
                self.retired_ui.kill()  # Quiesced, stateless old screen only.
                self.retired_ui.wait(timeout=3)
            self.retired_ui = None
            self.journal()
        update = self.replacement
        if not update:
            return
        try:
            if "process" in update:
                if update["process"].poll() is not None or time.monotonic() > update["deadline"]:
                    raise RuntimeError("New UI did not become ready; previous interface retained")
                return
            # Keep native-window capture/input intact; apply when back on Home/Pi.
            if self.view == "external" or (self.window_apps and self.window_apps.pending):
                return
            # Never interrupt capture or pending dictation to refresh a screen.
            if self.recording or self.transcriber or self.voice_pending or self.voice_guard or self.transcript.exists():
                return
            state = self.agent_state()
            if (state["resetting"] or state["awaitingPrompt"] or state.get("question") or state.get("selectionPending")
                    or state.get("editorVersion", 0) > state.get("editorAck", 0)
                    or state.get("rejectedVersion", 0) > state.get("rejectedAck", 0)):
                return  # Preserve unfinished dialog answers and unsaved recovery.
            prepared = json.loads(self.ipc(self.shell, "tabletUi", "prepare"))
            if not prepared["ready"]:
                return
            update["handoff"] = {"focused": prepared["focused"], "cursor": prepared["cursor"]}
            private_write(chat_state() / "draft.txt", prepared["draft"])
            environment = dict(os.environ, TABLET_UI_TOKEN=update["token"], TABLET_UI_NAVIGATION=prepared.get("navigation", ""))
            with (directory() / "surface.log").open("a") as output:
                update["process"] = subprocess.Popen(["quickshell", "--path", update["source"]], env=environment, stdout=output, stderr=output)
            update["deadline"] = time.monotonic() + 12
            self.journal()  # Both interfaces and the stable backend are owned.
            self.ui_update["phase"] = "loading"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            self.fail_ui(str(error))

    def fail_ui(self, error):
        update = self.replacement
        process = update.get("process")
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()  # Disposable candidate only; never Pi/voice.
                process.wait(timeout=3)
        handoff = update.get("handoff", {"focused": False, "cursor": 0})
        self.ipc(self.shell, "tabletUi", "activate", str(handoff["focused"]).lower(), str(handoff["cursor"]))
        self.replacement = None
        self.ui_update.update(phase="failed", error=error)
        self.error = error
        self.journal()

    def ui_ready(self, token):
        update = self.replacement
        if not update or token != update["token"] or "process" not in update or update["process"].poll() is not None:
            raise RuntimeError("Stale UI readiness acknowledgement")
        if not self.foreground() or not self.safe():
            raise RuntimeError("UI update cannot activate outside the tablet workspace")
        readiness = json.loads(self.ipc(update["process"], "tabletUi", "status"))
        if not all(readiness.get(k) for k in ("mapped", "rendered", "connected", "draftRestored", "updating")):
            raise RuntimeError("Replacement UI is not mapped and reconnected yet")
        namespace = "tablet-native-chat" if self.view == "pi" else "tablet-iteration-home"
        if self.stage:
            self.verify_presentation_policy()
            if not self.layer_opaque(update["process"], namespace):
                raise RuntimeError("Replacement app is still compositor-transparent")
        handoff = update["handoff"]
        current = chat_state() / "current-ui.json"
        previous = current.read_text() if current.exists() else None
        try:
            private_write(current, json.dumps({"bundle": update["bundle"], "root": update["root"]}))
            self.ipc(update["process"], "tabletUi", "activate", str(handoff["focused"]).lower(), str(handoff["cursor"]))
            if self.stage:
                self.ipc(self.stage, "tabletStage", "assets", str(Path(update["source"]).parent))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            if previous is None: current.unlink(missing_ok=True)
            else: private_write(current, previous)
            self.fail_ui(str(error))
            return self.ui_update
        # The replacement has mapped and reconnected before retiring the old
        # screen. Neither the RPC child nor keyboard/voice processes are touched.
        self.retired_ui, self.shell = self.shell, update["process"]
        self.retired_deadline = time.monotonic() + 3
        self.replacement = None
        self.journal()
        try: self.retired_ui.terminate()
        except ProcessLookupError: pass
        self.ui_update["phase"] = "applied"
        return self.ui_update

    def pi(self):
        self.close_after_reveal = None
        if not self.foreground() or not self.safe():
            raise RuntimeError("Pi entry is only available inside the active tablet trial")
        self.target, client = binding()
        if self.native_chat:
            previous = self.view
            self.cover_view("pi")
            try:
                if self.window_apps and self.window_apps.active:
                    self.window_apps.park(self.window_apps.active)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                self.view = previous  # Keep the native app visible if focus cannot be released.
                raise
            if not self.pi_started:
                self.ipc(self.agent, "tabletAgent", "launchPi")
                self.pi_started = True
            return
        if client["workspace"]["name"] not in (self.target["workspace"], WORKSPACE):
            raise RuntimeError("The bound terminal was moved elsewhere; refusing to steal it")
        if not self.borrowed:
            # Do not implicitly dismantle fullscreen, pinned or grouped work
            # sessions. Ordinary tiled/floating stream terminals are supported.
            if client.get("fullscreen", 0) or client.get("fullscreenClient", 0) or client.get("pinned") or client.get("grouped"):
                raise RuntimeError("Pi is fullscreen, pinned or grouped; leave that state before borrowing it")
            self.window_restore = {"floating": bool(client.get("floating", False)),
                                   "at": client.get("at", [0, 0]), "size": client.get("size", [800, 600])}
        if self.stage:
            self.ipc(self.stage, "tabletStage", "cover", "Opening Pi…")
            self.wait_stage()
        self.borrowed = True
        self.journal()
        dispatch("movetoworkspacesilent", f"name:{WORKSPACE},address:{self.target['address']}")
        dispatch("setfloating", "address:" + self.target["address"])
        self.layout_signature = None
        self.fit_pi()
        dispatch("focuswindow", "address:" + self.target["address"])
        self.cover_view("pi")

    def fit_pi(self):
        monitor = next(m for m in hypr("monitors") if m["name"] == "eDP-1")
        signature = tuple(monitor.get(k) for k in ("width", "height", "scale", "transform", "x", "y")) + tuple(monitor.get("reserved", [0, 0, 0, 0]))
        if signature == self.layout_signature:
            return
        width, height = monitor["width"], monitor["height"]
        if monitor.get("transform", 0) % 2:
            width, height = height, width
        scale = monitor.get("scale", 1)
        left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
        top = max(144, top)  # Keep the trial input controls clear while mapping.
        available_width = int(width / scale) - left - right
        available_height = int(height / scale) - top - bottom
        if available_width < 160 or available_height < 120:
            raise RuntimeError("Not enough display space for Pi; tablet Home remains covered")
        w = min(1100, max(128, int(available_width * .86)))
        h = min(760, max(96, int(available_height * .84)))
        x = int(monitor.get("x", 0) + left + (available_width - w) / 2)
        y = int(monitor.get("y", 0) + top + (available_height - h) / 2)
        address = "address:" + self.target["address"]
        dispatch("resizewindowpixel", f"exact {w} {h},{address}")
        dispatch("movewindowpixel", f"exact {x} {y},{address}")
        self.layout_signature = signature

    def return_terminal(self):
        if self.borrowed:
            client = next((c for c in hypr("clients") if c["address"] == self.target["address"]
                           and c["pid"] == self.target["pid"]), None)
            if client and start_time(self.target["pid"]) == self.target["start"]:
                address = "address:" + self.target["address"]
                original_location = client["workspace"]["name"] in (WORKSPACE, self.target["workspace"])
                if client["workspace"]["name"] == WORKSPACE:
                    dispatch("movetoworkspacesilent", f"name:{self.target['workspace']},{address}")
                if self.window_restore:
                    if self.window_restore["floating"]:
                        dispatch("setfloating", address)
                        w, h = map(int, self.window_restore["size"])
                        x, y = map(int, self.window_restore["at"])
                        dispatch("resizewindowpixel", f"exact {w} {h},{address}")
                        if original_location:
                            dispatch("movewindowpixel", f"exact {x} {y},{address}")
                        # On a third workspace, preserve the user's destination
                        # and position while undoing our floating/size changes.
                    else:
                        dispatch("settiled", address)
            self.borrowed = False
            self.window_restore = None
            self.layout_signature = None
            self.journal()

    def start_voice(self):
        if self.voice_daemon and self.voice_daemon.poll() is None:
            return
        self.voice_runtime.mkdir(mode=0o700, exist_ok=True)
        if self.voice_runtime.is_symlink():
            raise RuntimeError("Unsafe private voice runtime")
        self.voice_runtime.chmod(0o700)
        old_pid = self.voice_runtime / "voxtype/pid"
        if old_pid.exists():
            try:
                os.kill(int(old_pid.read_text().strip()), 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError("A private voice instance still exists; recover before restarting")
        (self.voice_runtime / "voxtype/state").unlink(missing_ok=True)
        with (directory() / "voice.log").open("a") as output:
            self.voice_daemon = subprocess.Popen(["voxtype", "--config", os.environ["TABLET_VOICE_CONFIG"],
                                                 "--on-demand-loading", "--quiet", "daemon"],
                                                env=self.voice_env, stdout=output, stderr=output)
        self.voice_identity = {"pid": self.voice_daemon.pid, "start": start_time(self.voice_daemon.pid)}
        self.journal()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if self.voice_daemon.poll() is not None:
                raise RuntimeError("Private Voxtype could not start; see voice.log")
            try:
                if self.owns_voice() and self.voice_state() == "idle":
                    return
            except OSError:
                pass
            time.sleep(.05)
        raise RuntimeError("Private Voxtype did not become ready")

    def voice_snapshot(self):
        path = self.voice_runtime / "voxtype/state"
        before = path.stat()
        state = path.read_text().strip()
        after = path.stat()
        if (before.st_ino, before.st_mtime_ns) != (after.st_ino, after.st_mtime_ns):
            raise RuntimeError("Voxtype state changed during inspection; retry")
        return (after.st_ino, after.st_mtime_ns, state)

    def voice_state(self):
        return self.voice_snapshot()[2]

    def await_voice(self, state, previous):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            token = self.voice_snapshot()
            if token != previous and token[2] == state:
                return token
            if state == "transcribing" and token[2] == "idle":
                return None  # Very short recordings may have already finished.
            time.sleep(.02)
        raise RuntimeError("Could not establish private dictation ownership; Cancel or recover the trial")

    def owns_voice(self):
        # All tablet operations use a private runtime namespace. Global desktop
        # hotkeys cannot address this daemon, eliminating check-then-signal races.
        try:
            return (self.voice_identity is not None
                    and int((self.voice_runtime / "voxtype/pid").read_text().strip()) == self.voice_identity["pid"]
                    and int((self.voice_runtime / "voxtype/voxtype.lock").read_text().strip()) == self.voice_identity["pid"]
                    and start_time(self.voice_identity["pid"]) == self.voice_identity["start"])
        except (OSError, ValueError):
            return False

    def uncertain_voice(self):
        self.voice_guard = True
        self.voice_pending = True
        self.journal()

    def confirm_voice_idle(self):
        # Inspection errors deliberately leave both durable guards intact.
        if self.voice_state() == "idle":
            self.voice_guard = False
            self.voice_pending = False
            return True
        return False

    def mic(self):
        if self.view != "pi" or not self.foreground() or not self.safe():
            raise RuntimeError("Open this Pi stream before recording")
        binding()
        if self.recording or self.transcriber or self.voice_pending or self.transcript.exists():
            raise RuntimeError("Finish or cancel the current dictation first")
        self.start_voice()
        before = self.voice_snapshot()
        if before[2] != "idle":
            raise RuntimeError("Voxtype is already busy; refusing to take over")
        # Recording may start even if the CLI times out. Persist uncertainty
        # BEFORE signalling; never claim cleanup succeeded until idle is known.
        self.uncertain_voice()
        run("voxtype", "record", "start", "--file=" + str(self.transcript),
            "--no-auto-submit", "--no-smart-auto-submit", "--no-osd", env=self.voice_env)
        self.voice_token = self.await_voice("recording", before)
        self.recording = True
        self.voice_pending = False
        self.journal()

    def stop_voice(self):
        if not self.recording:
            raise RuntimeError("This trial is not recording")
        if not self.owns_voice():
            self.uncertain_voice()
            self.recording = False
            try:
                self.confirm_voice_idle()
            finally:
                self.journal()
            raise RuntimeError("Dictation changed outside this trial; refusing to stop it")
        self.voice_guard = True
        self.journal()
        previous = self.voice_token
        self.transcriber = subprocess.Popen(["voxtype", "record", "stop", "--wait", "--wait-file", str(self.transcript), "--json", "--timeout", "90"],
                                            env=self.voice_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.journal()  # Persist waiter identity before any asynchronous-state wait.
        self.recording = False
        self.voice_token = None
        try:
            self.voice_token = self.await_voice("transcribing", previous)
        finally:
            self.journal()

    def cancel(self):
        active = self.voice_guard or self.recording or self.transcriber or self.voice_pending
        if active:
            if self.owns_voice():
                run("voxtype", "record", "cancel", env=self.voice_env)
                self.voice_pending = True
                self.journal()
                deadline = time.monotonic() + 2
                while self.voice_state() != "idle":
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Dictation cancellation is unconfirmed; recovery remains pending")
                    time.sleep(.02)
            elif self.voice_state() != "idle":
                self.voice_pending = True
                self.journal()
                raise RuntimeError("Private voice ownership is unconfirmed; Cancel again or recover the trial")
        self.recording = False
        self.voice_token = None
        self.voice_pending = False
        self.voice_guard = False
        if self.transcriber:
            self.transcriber.terminate()
            self.transcriber.wait(timeout=5)
            self.transcriber = None
        self.transcript.unlink(missing_ok=True)
        if self.owns_journal:
            self.journal()

    def insert(self):
        if self.recording or self.transcriber or self.voice_pending or not self.transcript.exists():
            raise RuntimeError("No completed dictation to insert")
        if self.view != "pi" or not self.foreground() or not self.safe():
            raise RuntimeError("Return to Pi before inserting dictation")
        binding()
        if self.transcript.stat().st_size > 65536:
            raise RuntimeError("Transcript is too large for draft insertion")
        text = self.transcript.read_bytes()
        if self.native_chat:
            result = text.decode("utf-8")
            self.transcript.unlink(missing_ok=True)
            return result
        # This is an explicit user action. Focus and verify the bound terminal;
        # never let asynchronous transcription paste into some other app.
        dispatch("focuswindow", "address:" + self.target["address"])
        if hypr("activewindow").get("address") != self.target["address"]:
            raise RuntimeError("Pi did not receive focus; dictation has not been inserted")
        # Preserve plain-text clipboard only. Refuse to destroy non-text data.
        types = subprocess.run(["wl-paste", "--list-types"], capture_output=True, timeout=3)
        formats = types.stdout.splitlines()
        if types.returncode == 0 and (not formats or any(
                not t.startswith(b"text/plain") and t not in (b"UTF8_STRING", b"STRING", b"TEXT") for t in formats)):
            raise RuntimeError("Clipboard contains rich/non-text data; insertion left pending")
        previous = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
        run("wl-copy", input=text)
        try:
            if hypr("activewindow").get("address") != self.target["address"]:
                raise RuntimeError("Focus changed; insertion cancelled")
            run("wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl")
            time.sleep(0.2)
        finally:
            current = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
            if current.returncode == 0 and current.stdout == text:
                if previous.returncode == 0:
                    run("wl-copy", input=previous.stdout)
                else:
                    run("wl-copy", "--clear")
        self.transcript.unlink(missing_ok=True)

    def input_panel(self, visible, frontend):
        if type(visible) is not bool or type(frontend) is not int:
            raise RuntimeError("Invalid input-panel request")
        # Retired/quarantined frontends cannot undo the current scene's input.
        if (not self.native_chat or not self.shell or self.shell.poll() is not None
                or self.shell.pid != frontend or (visible and self.view != "pi")
                or not self.foreground() or not self.safe()):
            return {"accepted": False}
        if not self.keyboard or self.keyboard.poll() is not None:
            raise RuntimeError("The owned tablet keyboard is unavailable")
        owner = run("gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                    "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetNameOwner",
                    "sm.puri.OSK0", text=True).stdout.strip()
        match = re.fullmatch(r"\('(:[A-Za-z0-9_.-]+)',\)", owner)
        if not match: raise RuntimeError("Could not identify the tablet keyboard service")
        unique = match[1]
        identity = run("gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                       "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetConnectionUnixProcessID",
                       unique, text=True).stdout.strip()
        match = re.fullmatch(r"\(uint32 ([0-9]+),\)", identity)
        if not match or int(match[1]) != self.keyboard.pid:
            raise RuntimeError("Keyboard service is not owned by this tablet session")
        # Address the verified unique peer, never a possibly replaced bus name.
        run("gdbus", "call", "--session", "--dest", unique, "--object-path", "/sm/puri/OSK0",
            "--method", "sm.puri.OSK0.SetVisible", str(visible).lower(), text=True)
        return {"accepted": True, "visible": visible}

    def status(self):
        inset = 0
        if self.native_chat:
            monitor = next((m for m in hypr("monitors") if m["name"] == "eDP-1"), {})
            inset = monitor.get("reserved", [0, 0, 0, 0])[3]
        return {"apps": self.window_apps.status() if self.window_apps else {"windows": {}, "pending": "", "active": ""}, "keyboardInset": inset, "running": True, "view": self.view, "visible": self.foreground(),
                "piStarted": self.pi_started, "automatic": self.automatic,
                "recording": self.recording, "transcribing": bool(self.transcriber), "uncertain": self.voice_pending,
                "ready": self.transcript.exists() and not self.recording and not self.transcriber and not self.voice_pending,
                "error": self.error, "uiUpdate": self.ui_update}

    def action(self, command, **payload):
        if command == "status":
            return self.status()
        if command == "adopt-fold":
            if not self.native_chat or not self.foreground() or not self.safe() or self.stopping:
                raise RuntimeError("Cannot adopt an inactive Tablet Home")
            # Adopt the existing Home without rebinding Pi, resetting navigation
            # or restarting apps/input services. Persist before acknowledging.
            run("tablet-workspace", "adopt-fold")
            self.automatic = True
            self.entered = True
            self.journal()
            return self.status()
        if command == "input-panel":
            return self.input_panel(payload.get("visible"), payload.get("frontend"))
        if command in ("app-open", "app-close"):
            return self.app_action(command, payload.get("app"), payload.get("frontend"))
        if command == "agent-state":
            return self.agent_state()
        if command == "agent-command":
            path = Path(payload["path"])
            if path.parent != directory() / "requests" or path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid() or path.stat().st_size > 1048576:
                raise RuntimeError("Invalid private agent request")
            record = json.loads(path.read_text())
            if record.get("action") in ("prompt", "new_chat", "abort", "answer"):
                self.error = ""
            if record.get("action") == "new_chat" and (self.replacement or self.recording or self.transcriber or self.voice_pending or self.voice_guard or self.transcript.exists()):
                raise RuntimeError("Finish dictation or the UI update before starting a new chat")
            return json.loads(self.ipc(self.agent, "tabletAgent", "dispatch", str(path)))
        if command == "apply-ui":
            return self.queue_ui(payload["bundle"], payload["root"])
        if command == "ui-ready":
            return self.ui_ready(payload["token"])
        self.error = ""
        if command == "pi": self.pi()
        elif command == "home":
            self.close_after_reveal = None
            if self.native_chat and (self.recording or self.transcriber or self.voice_pending or self.voice_guard or self.transcript.exists()):
                raise RuntimeError("Finish or cancel dictation before going Home")
            self.cancel()
            previous = self.view
            self.cover_view("home")
            try:
                if self.window_apps and self.window_apps.active:
                    self.window_apps.park(self.window_apps.active)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                self.view = previous
                raise
            self.return_terminal()
        elif command == "mic": self.mic()
        elif command == "stop": self.stop_voice()
        elif command == "cancel": self.cancel()
        elif command == "insert":
            text = self.insert()
            if self.native_chat:
                return dict(self.status(), insertText=text)
        elif command == "close":
            # Physical unfold/shortcut exits bypass the frontend close button.
            # Flush its current draft before acknowledging any teardown.
            if self.native_chat and self.shell and self.shell.poll() is None:
                saved = json.loads(self.ipc(self.shell, "tabletUi", "persistDraft"))
                if not saved.get("saved"):
                    raise RuntimeError("Could not save the chat draft; Tablet Home remains open")
            self.cancel()
            self.stopping = True
        else: raise RuntimeError("Unknown iteration action")
        return self.status()

    def tick(self):
        if self.recording and not self.owns_voice():
            self.uncertain_voice()
            self.recording = False
            self.voice_token = None
            self.error = "Dictation changed externally; this trial will not stop or cancel it"
            try:
                self.confirm_voice_idle()
            finally:
                self.journal()
        if not self.foreground() or not self.safe():
            self.stopping = True
        elif self.view == "pi" and not self.native_chat:
            client = next((c for c in hypr("clients") if c["address"] == self.target["address"]
                           and c["pid"] == self.target["pid"]), None)
            if not client or client["workspace"]["name"] != WORKSPACE:
                # Closing/moving Pi is not an exit from the tablet environment.
                # Do not leave a recording hidden behind the Home view.
                try:
                    self.cancel()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    self.error = str(error)
                self.view = "home"
            else:
                try:
                    self.fit_pi()
                except (RuntimeError, subprocess.SubprocessError) as error:
                    self.error = str(error)  # Never drop Home on a layout failure.
        if not self.stopping and self.window_apps:
            try:
                self.window_apps.tick()
                if self.view == "external" and self.window_apps.ownership_escape:
                    self.error = "Native app was pinned/grouped; returning to desktop window management"
                    self.stopping = True
                if self.view == "external" and not self.stopping:
                    client = self.window_apps.owned(self.window_apps.active)
                    if client:
                        monitor = next(m for m in hypr("monitors") if m["name"] == "eDP-1")
                        inset = monitor.get("reserved", [0, 0, 0, 0])[3]
                        if (self.external_ready and not self.window_apps.placed(client, monitor, inset)
                                and not self.window_apps.policy_changed(client, monitor, inset)):
                            self.cover_view("external", force=True)
                        # Expected IME/rotation changes resize over opaque Home,
                        # without a cover flash or swallowing the next tap.
                        self.external_ready = self.window_apps.fit(client, monitor, inset)
                    elif not self.window_apps.pending:
                        self.fail_external(self.window_apps.error)
            except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError) as error:
                # A disappearing window/refused dispatch is local app failure,
                # not permission to tear down Pi, input services or tablet Home.
                self.fail_external(str(error))
        if not self.stopping:
            self.reveal_entry()
        if self.stage and self.stage.poll() is not None:
            raise RuntimeError("Persistent tablet stage stopped; closing trial safely")
        if self.native_chat and not self.stopping:
            self.ui_tick()
            if self.agent and self.agent.poll() is not None:
                self.stopping = True
        if self.keyboard and self.keyboard.poll() is not None:
            raise RuntimeError("Automatic keyboard stopped; closing trial")
        if self.shell and self.shell.poll() is not None:
            raise RuntimeError("Iteration surface stopped; closing trial")
        if self.transcriber and self.transcriber.poll() is not None:
            if self.transcriber.returncode != 0:
                self.uncertain_voice()
                self.error = "Transcription did not finish; check Voxtype before retrying"
                self.transcript.unlink(missing_ok=True)
            self.transcriber = None
            try:
                self.confirm_voice_idle()
            finally:
                self.journal()
        elif self.voice_guard and not self.recording and not self.transcriber:
            if self.confirm_voice_idle():
                self.journal()

    def cleanup(self):
        if not self.owns_journal:
            return
        errors = []
        def attempt(fn):
            try: fn()
            except Exception as error: errors.append(str(error))
        attempt(self.cancel)
        if self.agent and self.agent.poll() is None:
            attempt(lambda: self.ipc(self.agent, "tabletAgent", "shutdown"))
            try:
                self.agent.wait(timeout=6)
            except subprocess.TimeoutExpired:
                pass
        for process in (self.shell, self.agent, self.retired_ui,
                        self.replacement.get("process") if self.replacement else None,
                        self.keyboard, self.voice_daemon):
            if process is self.voice_daemon and self.voice_guard:
                continue  # Keep a verifiable owner for unresolved-voice recovery.
            if process and process.poll() is None:
                attempt(process.terminate)
                attempt(lambda: process.wait(timeout=5))
        attempt(self.return_terminal)
        if self.window_apps:
            attempt(self.window_apps.release)
        for schema, key, old, applied in reversed(self.settings):
            def restore(schema=schema, key=key, old=old, applied=applied):
                if run("gsettings", "get", schema, key, text=True).stdout.strip() == applied:
                    run("gsettings", "set", schema, key, old)
            attempt(restore)
        for panel in self.panel_commands:
            def restart(panel=panel):
                environment = {k: v for k, v in os.environ.items() if not k.startswith("TABLET_") and k not in PANEL_ENV}
                environment.update(panel["environment"])
                subprocess.Popen(panel["argv"], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            attempt(restart)
        if self.entered:
            def leave_introduced_mode():
                path = Path(os.environ["XDG_RUNTIME_DIR"]) / "tablet-workspace.json"
                state = json.loads(path.read_text()) if path.exists() else {}
                if state.get("enabled") or state.get("exit_pending"):
                    run("tablet-workspace", "leave-automatic")
            attempt(leave_introduced_mode)
        # The persistent stage is last: teardown and workspace return happen
        # behind it, not in a naked Hyprland workspace between app surfaces.
        if self.stage and self.stage.poll() is None and not errors:
            attempt(self.stage.terminate)
            attempt(lambda: self.stage.wait(timeout=5))
        if errors:
            if self.voice_guard or self.voice_pending or self.recording or self.transcriber:
                try:
                    run("notify-send", "Tablet voice needs attention", "Private recording may still be active. Recover the tablet trial before restarting it.")
                except Exception:
                    pass
            raise RuntimeError("Trial cleanup needs recovery: " + "; ".join(errors))
        (directory() / "recovery.json").unlink(missing_ok=True)


def same_live_child(child):
    try:
        fields = Path(f"/proc/{int(child['pid'])}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] == child["start"] and fields[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


def stop_recovered_child(child):
    if not same_live_child(child):
        return
    try:
        os.kill(child["pid"], signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 3
    while same_live_child(child):
        if time.monotonic() >= deadline:
            raise RuntimeError("A recovered keyboard/UI child did not stop; journal retained")
        time.sleep(.05)


def recover():
    with (directory() / "owner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory() / "recovery.json"
        if not path.exists():
            (directory() / "control.sock").unlink(missing_ok=True)
            return
        value = json.loads(path.read_text())
        if value["target"]["instance"] != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            raise RuntimeError("Recovery is scoped to the original compositor")
        trial = Trial(value["target"])
        trial.settings = value["settings"]
        trial.borrowed = value["borrowed"]
        trial.window_restore = value.get("window")
        trial.entered = value["entered"]
        trial.panel_commands = value["panels"]
        trial.owns_journal = True
        trial.voice_pending = value.get("voice", False)
        trial.voice_guard = value.get("voice", False)
        trial.voice_identity = value.get("voice_owner")
        trial.recovery_children = value.get("children", [])
        # Only the PID/start-time verified daemon in our private namespace can
        # be cancelled. Never signal the shared desktop daemon during recovery.
        if value.get("voice") and trial.voice_state() != "idle":
            if not trial.owns_voice():
                raise RuntimeError("Private voice ownership unconfirmed; recovery guard retained")
            trial.cancel()
        for child in value.get("children", []):
            stop_recovered_child(child)
        trial.recovery_children = []
        trial.journal()
        if trial.native_chat and (directory() / "app-windows.json").exists():
            # Reload only compositor/PID/start/tag-verified ownership. Otherwise
            # a crashed Home could strand its browser in a hidden workspace.
            trial.apps()
        trial.cleanup()
        (directory() / "control.sock").unlink(missing_ok=True)


def chat_state():
    return Path(os.environ["TABLET_CHAT_SESSIONS"])


def session_environment():
    environment = dict(os.environ, TABLET_CHAT_RESUME_FILE="", TABLET_CHAT_FORCE_FRESH="")
    selection = chat_state() / "selection.json"
    if selection.exists():
        value = json.loads(selection.read_text())["sessionFile"]
        environment["TABLET_CHAT_FORCE_FRESH"] = "1"
        if value:
            path = Path(value)
            if not path.is_absolute() or path.suffix != ".jsonl" or path.is_symlink() or path.parent.resolve() != chat_state().resolve():
                raise RuntimeError("Saved tablet chat selection points outside its workspace history")
            if path.is_file():
                environment["TABLET_CHAT_RESUME_FILE"] = str(path)
    return environment


def private_write(path, text):
    descriptor, temporary = tempfile.mkstemp(prefix=".tablet-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(text)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def ui_bundle(bundle, root):
    bundle, root = Path(bundle), Path(root)
    roots = chat_state() / "ui-roots"
    if not bundle.is_absolute() or bundle.parent != NIX_STORE or not bundle.is_dir() or bundle.resolve() != bundle:
        raise RuntimeError("UI must be an immutable Nix store bundle")
    if root.parent != roots or not re.fullmatch(r"[0-9a-f]{32}", root.name) or not root.is_symlink() or root.resolve() != bundle:
        raise RuntimeError("UI bundle needs its own workspace GC root")
    source = bundle / "share/tablet-ui"
    if not source.resolve().is_relative_to(bundle):
        raise RuntimeError("UI source must stay inside its immutable bundle")
    manifest = json.loads((source / "ui-manifest.json").read_text())
    if manifest != {"protocol": 1, "backend": os.environ["TABLET_UI_BACKEND"]}:
        raise RuntimeError("This change affects the backend; close and restart the trial instead of live-updating it")
    if not (source / "iteration.qml").is_file():
        raise RuntimeError("UI bundle has no tablet scene")
    return source


def update_ui():
    # Run as a normal Pi Bash tool/CLI child, not on the supervisor event loop.
    # Nothing stages files, prompts a model, records audio, rebuilds or deploys NixOS.
    binding()
    cwd = Path(os.environ["TABLET_CHAT_CWD"])
    if not (cwd / "home/modules/tablet-workspace.nix").is_file():
        raise RuntimeError("UI updates require a registered Nix repository worktree")
    if not request("status").get("running"):
        raise RuntimeError("Open the native tablet trial before updating it")
    roots = chat_state() / "ui-roots"
    roots.mkdir(mode=0o700, exist_ok=True)
    root = roots / uuid.uuid4().hex
    expression = '''let
      flake = builtins.getFlake (toString ./.);
      pkgs = flake.nixosConfigurations.kirax1.pkgs;
      packages = flake.nixosConfigurations.kirax1.config.home-manager.users.sumeet.home.packages;
    in [
      (import (flake.outPath + "/tests/tablet-home-preview.nix") { inherit pkgs; })
      (import (flake.outPath + "/tests/tablet-iteration-shell.nix") { inherit pkgs; })
      (builtins.head (builtins.filter (p: (p.name or "") == "tablet-ui-bundle") packages))
    ]'''
    # Multiple outputs get suffixed links. Build the tests without links first,
    # then root the bundle alone so the selected UI survives garbage collection.
    checked = subprocess.run(["nix", "build", "--impure", "--no-link", "--print-out-paths", "--expr", expression], cwd=cwd, check=True, stdout=subprocess.PIPE, text=True)
    candidates = [p for p in checked.stdout.splitlines() if (Path(p) / "share/tablet-ui/ui-manifest.json").is_file()]
    if len(candidates) != 1:
        raise RuntimeError("Build did not produce exactly one tablet UI bundle")
    bundle = candidates[0]
    subprocess.run(["nix-store", "--realise", bundle, "--add-root", str(root), "--indirect"], check=True, stdout=subprocess.PIPE)
    ui_bundle(bundle, str(root))
    result = request("apply-ui", bundle=bundle, root=str(root))
    # A queued update deliberately waits for voice/extension/UI actions. Don't
    # block the agent's reply waiting for the user to finish dictation.
    return dict(result, message="UI update staged; applies automatically when input handoff is safe")


def request(command, **payload):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(8)
        connection.connect(str(directory() / "control.sock"))
        connection.sendall(json.dumps(dict(payload, command=command)).encode() + b"\n")
        connection.shutdown(socket.SHUT_WR)
        data = b""
        while len(data) < 8388608:
            block = connection.recv(4096)
            if not block: break
            data += block
        result = json.loads(data)
        if result.get("failed"):
            raise RuntimeError(result["error"])
        return result


def respond(trial, connection):
    connection.settimeout(2)
    command = ""
    try:
        message = connection.recv(1024)
        if not message:
            return  # A retired frontend can close an outstanding poll.
        fields = json.loads(message)
        command = fields.pop("command")
        result = trial.action(command, **fields)
    except ConnectionResetError:
        return
    except Exception as error:
        if command not in ("agent-state", "ui-ready", "input-panel"):
            trial.error = str(error)
        result = {"failed": True, "error": str(error)}
    try:
        connection.sendall(json.dumps(result).encode())
    except (BrokenPipeError, ConnectionResetError, TimeoutError):
        pass  # Losing a reply recipient must never tear down tablet mode.


def daemon():
    with (directory() / "owner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        trial = Trial()
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, lambda *_: setattr(trial, "stopping", True))
        path = directory() / "control.sock"
        try:
            trial.setup()
            with socket.socket(socket.AF_UNIX) as server:
                path.unlink(missing_ok=True)
                server.bind(str(path))
                server.listen(4)
                if os.environ.get("TABLET_START_VIEW") != "home": trial.pi()
                # A physically folded session lasts until unfold/explicit exit,
                # not the experimental trial's arbitrary one-hour timeout.
                deadline = time.monotonic() + 3600
                while not trial.stopping and (trial.automatic or time.monotonic() < deadline):
                    if select.select([server], [], [], .25)[0]:
                        with server.accept()[0] as connection:
                            respond(trial, connection)
                    trial.tick()
        finally:
            path.unlink(missing_ok=True)
            trial.cleanup()


def start_trial(initial_view="pi", automatic=False, registered=False):
    if initial_view not in ("home", "pi"):
        raise RuntimeError("Invalid initial tablet view")
    # Serialize entry/binding; attaching to a running session must not rebind,
    # reset its current view, or create another frontend/workspace lifecycle.
    with (directory() / "launch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return request("adopt-fold" if automatic else "status" if initial_view == "home" else "pi")
        except (FileNotFoundError, ConnectionRefusedError):
            if (directory() / "recovery.json").exists():
                raise RuntimeError("Previous trial cleanup is pending; do not start another")
            if initial_view == "home":
                if os.environ.get("TABLET_NATIVE_CHAT") != "1":
                    raise RuntimeError("Home-first entry requires native tablet mode")
                # Physical folding is not a request to rebind Pi to the fold
                # watcher's cwd. Retain the explicitly registered context;
                # on first use choose HOME, never a repository runtime dependency.
                if not automatic and not registered:
                    bind()
                elif not (directory() / "context.json").exists():
                    save("context.json", {"cwd": str(Path.home()), "project": {}})
            binding()
            environment = dict(os.environ, TABLET_START_VIEW=initial_view,
                               TABLET_AUTOMATIC="1" if automatic else "0")
            with (directory() / "supervisor.log").open("a") as output:
                process = subprocess.Popen([os.environ["TABLET_ITERATE_BIN"], "daemon"],
                                          env=environment, stdout=output, stderr=output, start_new_session=True)
            for _ in range(80):
                if process.poll() is not None:
                    raise RuntimeError("Trial could not start; see private supervisor.log")
                try:
                    return request("status")
                except (FileNotFoundError, ConnectionRefusedError): time.sleep(.1)
            raise RuntimeError("Trial did not become ready")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bind", "start", "start-fold", "start-home", "toggle", "open", "daemon", "recover", "status", "pi", "home", "mic", "stop", "cancel", "insert", "close", "input-panel", "agent-state", "agent-command", "update-ui", "ui-ready", "app-open", "app-close"])
    parser.add_argument("token", nargs="?")
    args = parser.parse_args()
    command = args.command
    if command == "bind": bind()
    elif command == "daemon": daemon()
    elif command == "recover": recover()
    elif command == "update-ui": print(json.dumps(update_ui()))
    elif command == "ui-ready": print(json.dumps(request(command, token=args.token)))
    elif command in ("input-panel", "app-open", "app-close"):
        print(json.dumps(request(command, **json.loads(args.token))))
    elif command == "agent-command":
        data = sys.stdin.buffer.read(1048577)
        if len(data) > 1048576: raise RuntimeError("Agent request is too large")
        record = json.loads(data)
        requests = directory() / "requests"
        if requests.is_symlink(): raise RuntimeError("Unsafe request directory")
        requests.mkdir(mode=0o700, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=requests)
        try:
            with os.fdopen(descriptor, "w") as output: json.dump(record, output)
            print(json.dumps(request(command, path=name)))
        finally:
            Path(name).unlink(missing_ok=True)
    elif command in ("start", "start-fold", "start-home", "open"):
        print(json.dumps(start_trial("pi" if command == "open" else "home",
                                     automatic=command == "start-fold", registered=command == "start-home")))
    elif command == "toggle":
        try:
            result = request("close")
        except (FileNotFoundError, ConnectionRefusedError):
            result = start_trial("home", registered=True)
        print(json.dumps(result))
    elif command == "status":
        try: print(json.dumps(request(command)))
        except (FileNotFoundError, ConnectionRefusedError): print('{"running": false}')
    else:
        print(json.dumps(request(command)))


if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
