"""Hidden PTY regression tests against actual Pi; no windows or cloud inference."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]


def until(fd, needle, timeout=60):
    deadline = time.monotonic() + timeout
    result = b""
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                data = os.read(fd, 65536)
            except OSError:
                break
            if not data:
                break
            result += data
            if needle.encode() in result:
                return result
    raise AssertionError(f"Did not observe {needle!r}; synthetic terminal tail: {result[-2500:]!r}")


def wait_exit(pid, fd):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        found, status = os.waitpid(pid, os.WNOHANG)
        if found:
            assert os.waitstatus_to_exitcode(status) == 0, status
            return
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                os.read(fd, 65536)
            except OSError:
                pass
    raise AssertionError("Normal Pi did not exit cleanly after /quit")


def descendants(pid):
    found = []
    try:
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    except FileNotFoundError:
        return found
    for child in children:
        found.append(int(child))
        found.extend(descendants(int(child)))
    return found


def running(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


def run_case(package, pi, interrupt, terminate_parent=False):
    with tempfile.TemporaryDirectory(prefix="pi-private-pty-") as tmp:
        home = Path(tmp)
        agent = home / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text(json.dumps({"packages": [], "defaultProjectTrust": "never"}))
        (agent / "models.json").write_text(json.dumps({"providers": {"fixture": {
            "baseUrl": "http://127.0.0.1:1/v1", "api": "openai-completions", "apiKey": "local",
            "models": [{"id": "fixture-model", "contextWindow": 8192, "maxTokens": 128}]
        }}}))
        extension = home / "private.ts"
        extension.write_text((ROOT / "home/config/pi/extensions/private.ts").read_text()
            .replace("@privateChat@", str(package))
            .replace('export default function (pi: ExtensionAPI) {',
                'export default function (pi: ExtensionAPI) { pi.on("session_start", () => { setTimeout(() => process.stdout.write("PRIVATE_TEST_NORMAL_READY"), 100); });'))
        model = home / "matrix/models/LLM/Qwen3.5-4B-Q4_K_M.gguf"
        model.parent.mkdir(parents=True)
        if interrupt or terminate_parent:
            model.symlink_to(Path.home() / "matrix/models/LLM/Qwen3.5-4B-Q4_K_M.gguf")
        else:
            model.write_bytes(b"synthetic-invalid-model")
        normal_history = home / "normal-sessions"
        env = {"HOME": str(home), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
               "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0", "TERM": "xterm-256color",
               "LANG": "C.UTF-8", "PATH": os.environ["PATH"]}
        argv = [str(pi), "--offline", "--no-approve", "--no-tools", "--no-extensions",
                "--extension", str(extension), "--no-skills", "--no-prompt-templates", "--no-themes",
                "--no-context-files", "--provider", "fixture", "--model", "fixture-model",
                "--session-dir", str(normal_history)]
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(home)
            os.execve(str(pi), argv, env)
        exited = False
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
            until(fd, "PRIVATE_TEST_NORMAL_READY")
            os.write(fd, b"/private\r")
            if interrupt or terminate_parent:
                until(fd, "[PRIVATE", timeout=210)
                if terminate_parent:
                    children = descendants(pid)
                    assert len(children) >= 3, "Expected launcher, sandbox and private children"
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)
                    exited = True
                    deadline = time.monotonic() + 15
                    while any(running(child) for child in children) and time.monotonic() < deadline:
                        time.sleep(0.1)
                    assert not any(running(child) for child in children), "Private processes outlived normal Pi"
                    with (home / ".local/state/pi-private/active.lock").open("r+") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    print("PASS: terminating only normal Pi tears down private processes and releases storage lock")
                    return
                os.write(fd, b"\x03")
            else:
                until(fd, "Starting isolated local model")
                os.write(fd, b"PRIVATE_SENTINEL_DO_NOT_FORWARD\n")
            until(fd, "Private chat failed", timeout=30)
            assert os.waitpid(pid, os.WNOHANG) == (0, 0), "Ctrl-C killed the normal Pi parent"
            os.write(fd, b"/quit\r")
            wait_exit(pid, fd)
            exited = True
            for path in normal_history.glob("*.jsonl"):
                text = path.read_text()
                assert "PRIVATE_SENTINEL_DO_NOT_FORWARD" not in text, "Private terminal input leaked to normal history"
                for line in text.splitlines():
                    record = json.loads(line)
                    if record.get("type") == "model_change":
                        assert record.get("provider") == "fixture", record
            print("PASS: " + ("Ctrl-C returns to the unchanged normal Pi" if interrupt else "startup failure discards queued private input"))
        finally:
            if not exited:
                try:
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)
                except ProcessLookupError:
                    pass
            os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--pi", required=True, type=Path)
    args = parser.parse_args()
    run_case(args.package, args.pi, interrupt=False)
    run_case(args.package, args.pi, interrupt=True)
    run_case(args.package, args.pi, interrupt=False, terminate_parent=True)
