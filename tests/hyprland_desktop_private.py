"""Private compositor helpers only; no tablet prototype runtime dependency."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def until(check, reason, timeout=25):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            last = error
        time.sleep(.05)
    raise AssertionError(reason + (": " + str(last) if last else ""))


def outer(script):
    # Keep compositor Unix socket paths short, including the Qt event socket.
    root = Path(tempfile.mkdtemp(prefix="twa.s."))
    (root / "r").mkdir(mode=0o700)
    (root / "home").mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PI_", "PROJECT_OBJECT_", "HL_"))}
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE",
                 "DBUS_SESSION_BUS_ADDRESS", "QT_PLUGIN_PATH", "QML_IMPORT_PATH"):
        env.pop(name, None)
    env.update(TABLET_WINDOW_TEST_ROOT=str(root), HOME=str(root / "home"), XDG_RUNTIME_DIR=str(root / "r"),
        XDG_CONFIG_HOME=str(root / "config"), XDG_CONFIG_DIRS=str(root / "empty"), XDG_DATA_HOME=str(root / "data"),
        XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"), GSETTINGS_BACKEND="keyfile",
        WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="gles2",
        WLR_RENDER_DRM_DEVICE="/dev/dri/renderD128", WLR_LIBINPUT_NO_DEVICES="1",
        QT_QPA_PLATFORM="wayland", QT_QUICK_CONTROLS_STYLE="Basic", QT_FORCE_STDERR_LOGGING="1",
        DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(root / "no-system-bus"), PYTHONDONTWRITEBYTECODE="1")
    print("Private desktop artifacts:", root, flush=True)
    return subprocess.call(["bwrap", "--unshare-net", "--bind", "/", "/", "--dev-bind", "/dev", "/dev",
                            "--tmpfs", "/tmp/.X11-unix", "dbus-run-session", "--", sys.executable, script], env=env)
