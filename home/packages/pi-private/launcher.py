#!@python@
"""Launch the complete private chat and model inside a fail-closed sandbox."""
import ctypes
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import termios

MODEL_RELATIVE = "matrix/models/LLM/Qwen3.5-4B-abliterated.Q4_K_M.gguf"
IMAGE_MODEL_RELATIVE = "matrix/models/image/checkpoints/Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"


def sandbox_command(history, model, check=False, images=None, image_model=None):
    command = [
        "@bwrap@", "--unshare-all", "--unshare-user", "--die-with-parent", "--new-session",
        "--disable-userns", "--cap-drop", "ALL", "--clearenv",
        "--ro-bind", "/nix/store", "/nix/store",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/run", "--dir", "/home", "--dir", "/home/private",
        "--bind", str(history), "/history",
        "--chdir", "/home/private",
    ]
    # kirax1's Intel iGPU: render access only, never the display/card device.
    # libdrm needs PCI identity metadata, not the rest of host sysfs. Build a
    # minimal discovery tree instead of exposing /sys or the whole GPU subtree.
    gpu = "/sys/devices/pci0000:00/0000:00:02.0"
    command += [
        "--dev-bind", "/dev/dri/renderD128", "/dev/dri/renderD128",
        "--dir", gpu + "/drm/renderD128",
        "--symlink", "../../../0000:00:02.0", gpu + "/drm/renderD128/device",
        "--symlink", "../../../bus/pci", gpu + "/subsystem",
        "--symlink", "../../devices/pci0000:00/0000:00:02.0/drm/renderD128", "/sys/dev/char/226:128",
    ]
    for attribute in ["uevent", "vendor", "device", "subsystem_vendor", "subsystem_device", "revision"]:
        path = gpu + "/" + attribute
        command += ["--ro-bind", path, path]
    if model is not None:
        command += ["--ro-bind", str(model), "/model.gguf"]
    if images is not None:
        command += ["--bind", str(images), "/images"]
    if image_model is not None:
        command += ["--ro-bind", str(image_model), "/image-model.safetensors"]
    for key, value in {
        "HOME": "/home/private", "LANG": "C.UTF-8", "TMPDIR": "/tmp",
        "TERM": "xterm-256color", "COLORTERM": "truecolor",
        "PATH": "/nonexistent", "PI_CODING_AGENT_DIR": "/home/private/agent",
        "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        "PI_HYPERLINKS": "0", "PI_IMAGE_PROTOCOL": "none",
        "VK_DRIVER_FILES": "@intelVulkanIcd@",
    }.items():
        command += ["--setenv", key, value]
    command += ["@python@", "@chat@", "--pi", "@pi@", "--llama", "@llama@"]
    if check:
        command += ["--check"]
    return command


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Private storage must be an owned directory, not a symlink")
    path.chmod(0o700)
    return path


def flush_input():
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)


def protect_parent_lifetime():
    # Bubblewrap watches this launcher; this launcher must also watch normal Pi
    # (or the invoking shell). Close the race where that parent already exited.
    expected = int(os.environ.get("PI_PRIVATE_PARENT_PID", os.getppid()))
    def terminate(_signal, _frame):
        flush_input()
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, terminate)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "Cannot establish private parent lifetime")
    if os.getppid() != expected:
        raise RuntimeError("Private chat parent already exited")


def main():
    protect_parent_lifetime()
    if sys.argv[1:] == ["--flush-input"]:
        flush_input()
        return 0
    if sys.argv[1:] not in ([], ["--check"]):
        raise RuntimeError("Usage: pi-private [--check]")
    os.umask(0o077)
    home = Path.home()
    root = private_directory(home / ".local/state/pi-private")
    history = private_directory(root / "sessions")
    images = private_directory(root / "images")
    lock = os.open(root / "active.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock)
        raise RuntimeError("Another private chat is already open; close it first") from None
    check = sys.argv[1:] == ["--check"]
    model = None if check else home / MODEL_RELATIVE
    if model is not None and not model.is_file():
        raise RuntimeError("Required local Qwen3.5-4B Abliterated model is missing; no cloud fallback is available")
    # A foreground child inherits only terminal streams, never prompts or context.
    # No network or namespace failure has a fallback path.
    try:
        image_model = home / IMAGE_MODEL_RELATIVE
        return subprocess.call(sandbox_command(history, model, check, images=images,
                               image_model=image_model if image_model.is_file() else None), close_fds=True)
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, RuntimeError) as error:
        print(f"Private chat not started: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        flush_input()
