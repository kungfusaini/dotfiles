#!/usr/bin/env python3
"""Opt-in headless real-systemd/Pi smoke test. No prompts or model requests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_oneshot as one


def alive(pid):
    try:
        # A reaped-or-zombie process cannot execute or consume allowance.
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="oneshot-deadline-") as tmp:
        root = Path(tmp)
        # Isolate Pi state/config; do not inspect or use real credentials.
        stub = root / "worker.py"
        stub.write_text('''import json, os, pathlib, subprocess, sys, time
root = pathlib.Path(sys.argv[1])
env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
           XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"),
           PI_CODING_AGENT_DIR=str(root / "agent"))
for name in tuple(env):
    if name.startswith("PROJECT_OBJECT_") or name.startswith("PI_CODING_AGENT_SESSION") or "API_KEY" in name:
        env.pop(name)
(root / "agent").mkdir()
(root / "agent/settings.json").write_text(json.dumps({"defaultProvider":"anthropic", "defaultModel":"claude-opus-4-8"}))
pi = subprocess.Popen([sys.argv[2], "--mode", "rpc", "--offline", "--no-extensions",
                       "--no-skills", "--no-session", "--provider", "openai-codex",
                       "--model", "gpt-5.5"], stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=root)
pi.stdin.write(b'{"id":"state","type":"get_state"}\\n'); pi.stdin.flush()
while True:
    line = pi.stdout.readline()
    if not line:
        raise RuntimeError("Pi exited before state response")
    record = json.loads(line)
    if record.get("id") == "state":
        assert record.get("success") is True
        assert record["data"]["model"]["provider"] == "openai-codex", "saved provider default leaked into one-shot"
        assert record["data"]["model"]["id"] == "gpt-5.5"
        break
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
(root / "pids.json").write_text(json.dumps([os.getpid(), pi.pid, child.pid]))
while True:
    (root / "tick").write_text(str(time.time()))
    time.sleep(0.02)
''')
        session = uuid.uuid4().hex
        other = "oneshot-test-unrelated-" + uuid.uuid4().hex
        deadline = int(time.time()) + 8
        process = None
        try:
            subprocess.run(["systemd-run", "--user", "--collect", "--unit=" + other,
                            "--", sys.executable, "-c", "import time; time.sleep(60)"], check=True)
            subprocess.run(one.timer_command(session, deadline), check=True)
            command = one.session_command(session, "test-account", deadline, root)
            command[command.index("--pty")] = "--pipe"
            # Exercise exactly the production unit properties, with an isolated,
            # no-request worker replacing only the private quota/startup gate.
            command = command[:command.index("--") + 1] + [sys.executable, "-B", str(stub), str(root), args.pi]
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            while not (root / "pids.json").exists() and time.time() < deadline - 1:
                if process.poll() is not None:
                    raise RuntimeError("Worker failed: " + process.stderr.read().decode())
                time.sleep(0.05)
            assert (root / "pids.json").exists(), "worker did not start before deadline"
            pids = json.loads((root / "pids.json").read_text())
            assert all(alive(pid) for pid in pids), "worker/Pi/detached child not alive before reset"
            process.wait(timeout=max(1, deadline-time.time()) + 5)
            stopped = time.time()
            for _ in range(50):
                if not any(alive(pid) for pid in pids):
                    break
                time.sleep(0.02)
            assert not any(alive(pid) for pid in pids), "owned process escaped cutoff"
            last_tick = float((root / "tick").read_text())
            assert deadline - 0.5 < last_tick <= deadline + 0.5, (deadline, last_tick)
            assert stopped < deadline + 1, (deadline, stopped)
            subprocess.run(["systemctl", "--user", "is-active", "--quiet", other + ".service"], check=True)
            print(f"PASS: real Pi RPC + worker + detached child stopped at reset; "
                  f"last execution {last_tick-deadline:+.3f}s, observed exit {stopped-deadline:+.3f}s; unrelated unit survived.")
        finally:
            one.cleanup(session)
            subprocess.run(["systemctl", "--user", "stop", other + ".service"], check=False)
            if process and process.poll() is None:
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
