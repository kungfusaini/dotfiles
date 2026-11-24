"""Start the pinned local model and Pi's native private-only TUI in the sandbox."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

MODEL = "private-qwen"
HISTORY = Path("/history")


def configure():
    agent = Path(os.environ["PI_CODING_AGENT_DIR"])
    agent.mkdir(parents=True, exist_ok=True)
    settings = {"packages": [], "retry": {"enabled": False}, "cacheWarming": {"enabled": False},
                "fullscreenCopyOnSelect": False, "fullscreenExitOutput": "resume-hint"}
    (agent / "settings.json").write_text(json.dumps(settings))
    (agent / "models.json").write_text(json.dumps({"providers": {"private-local": {
        "baseUrl": "http://127.0.0.1:18080/v1", "api": "openai-completions", "apiKey": "local",
        "models": [{"id": MODEL, "name": "Private Qwen3.5-4B Abliterated", "input": ["text"],
                    "contextWindow": 8192, "maxTokens": 1024,
                    "compat": {"supportsStore": False, "supportsDeveloperRole": False,
                               "supportsReasoningEffort": False, "maxTokensField": "max_tokens"}}]
    }}}))


def pi_command(executable):
    return [executable, "--tui-mode", "fullscreen", "--offline", "--no-approve",
            "--no-builtin-tools", "--tools", "generate_image",
            "--no-extensions", "--extension", "@imageExtension@", "--no-skills", "--no-prompt-templates", "--no-themes",
            "--no-context-files", "--session-dir", str(HISTORY),
            "--provider", "private-local", "--model", MODEL, "--thinking", "off",
            "--system-prompt", "You are a private, local assistant. Your only tool is generate_image, which creates one image on the local GPU. Call it when the user explicitly asks you to create, draw, render or generate an image; do not tell them to use /image instead. Use the quality preset by default and fast only when the user asks for speed. Never generate images for unrelated conversation or automatically retry. The tool displays the image preview and saves the full PNG privately. You cannot view or analyze the image, browse, run shell commands or read files. The /image command remains a manual alternative."]


def model_command(executable):
    return [executable, "--model", "/model.gguf", "--alias", MODEL,
            "--host", "127.0.0.1", "--port", "18080", "--ctx-size", "8192",
            "--parallel", "1", "--threads", "4", "--threads-batch", "4",
            "--device", "Vulkan0", "--n-gpu-layers", "999", "--flash-attn", "off",
            "--jinja", "--reasoning", "off", "--log-disable"]


def isolation_check():
    for path in ["/home/sumeet", "/run/user", "/tmp/.X11-unix", "/etc/resolv.conf",
                 "/dev/dri/card0", "/dev/input", "/dev/snd", "/sys/class", "/sys/bus", "/sys/devices/system"]:
        if Path(path).exists():
            raise RuntimeError("Unexpected host resource exposed: " + path)
    if sorted(p.name for p in Path("/dev/dri").iterdir()) != ["renderD128"]:
        raise RuntimeError("Unexpected GPU device exposure")
    gpu = Path("/sys/devices/pci0000:00/0000:00:02.0")
    for attribute in ["uevent", "vendor", "device", "subsystem_vendor", "subsystem_device", "revision"]:
        if not os.statvfs(gpu / attribute).f_flag & os.ST_RDONLY:
            raise RuntimeError("GPU identity metadata must be read-only")
    for address in [("1.1.1.1", 443), ("127.0.0.1", 18080)]:
        try:
            with socket.create_connection(address, timeout=1):
                raise RuntimeError("Unexpected reachable network service")
        except OSError:
            pass
    if any(key in os.environ for key in ["OPENAI_API_KEY", "SSH_AUTH_SOCK", "DBUS_SESSION_BUS_ADDRESS", "PI_SESSION_FILE"]):
        raise RuntimeError("Unexpected inherited host environment")
    print("Network namespace: " + os.readlink("/proc/self/ns/net"))
    print("PASS: sandbox denies external/host-loopback access and omits host home, sockets, credentials and normal session environment.")


def wait_for_model(server):
    deadline = time.monotonic() + 180
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Private model failed to start; no cloud fallback")
        try:
            with opener.open("http://127.0.0.1:18080/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError("Private model startup timed out; no cloud fallback")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi", required=True)
    parser.add_argument("--llama", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.check:
        isolation_check()
        return 0
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise RuntimeError("Private chat requires an interactive terminal")
    configure()
    server = None
    # Model and startup diagnostics stay only in the sandbox's tmpfs. The native
    # Pi TUI owns the terminal and Pi's session manager owns conversation history.
    with tempfile.TemporaryFile() as log:
        try:
            print("Starting isolated local model (Intel GPU); this may take a moment.", flush=True)
            server = subprocess.Popen(model_command(args.llama),
                                      stdout=log, stderr=log, close_fds=True)
            wait_for_model(server)
            return subprocess.call(pi_command(args.pi), stderr=log, close_fds=True)
        finally:
            if server:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
    except (OSError, RuntimeError) as error:
        print("Private chat closed: " + str(error), file=sys.stderr)
        sys.exit(1)
