#!/usr/bin/env python3
"""Headed/profile acceptance on Project Object's private headless compositor.

Usage: python3 headed_integration.py --harness /absolute/workspace_exec_integration.py
  --hyprland ... --hyprctl ... --labwc ... --kitty ... --chromium /nix/store/.../bin/pi-browser
  --helper /nix/store/.../bin/project-workspace-exec

The harness's --chromium argument carries pi-browser here. Its launcher and focus
assertions are reused unchanged. No host windows, input or real credentials.
"""
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

PAGE = b'''<!doctype html><title>Manual handoff fixture</title>
<input id="name" aria-label="Name"><button id="login" onclick="
localStorage.setItem('login','synthetic-user');document.querySelector('#status').textContent='Signed in'
">Login</button><p id="status">Signed out</p><button id="continue" onclick="
document.querySelector('#status').textContent='Agent continued'
">Continue</button><script>if(localStorage.getItem('login'))document.querySelector('#status').textContent='Signed in'</script>'''


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


def wait_for_file(path):
    deadline = time.monotonic() + 30
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists(), path


def worker(arguments):
    root, helper, browser, strip = arguments
    root = Path(root)
    wait_for_file(root / "go")
    port_file = root.parent / "fixture-port"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", int(port_file.read_text()) if port_file.exists() else 0), Handler)
    port_file.write_text(str(server.server_port))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    environment = {**os.environ, "PI_SESSION_ID": f"headed-{root.parent.name}-{strip}",
                   "XDG_STATE_HOME": str(root / "state"), "NIXOS_OZONE_WL": "1"}
    command = [browser, "open", "--headed", "--config=./custom-config.json", "--profile=../shared-profile",
               f"http://127.0.0.1:{server.server_port}/"]
    launcher = "import os,subprocess,time;"
    if strip == "yes":
        launcher += "os.environ.pop('HL_EXEC_RULE_TOKEN',None);os.environ.pop('HL_INITIAL_WORKSPACE_TOKEN',None);time.sleep(1.2);"
    launcher += "raise SystemExit(subprocess.run(" + repr(command) + ").returncode)"

    def call(*args):
        result = subprocess.run([browser, *args], env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and "### Error" not in result.stdout, result
        return result.stdout

    result = None
    try:
        call("--help")
        session = Path(json.loads(call("paths"))["session"])
        (root / "custom-config.json").write_text((session / "config.json").read_text())
        result = subprocess.run([helper, sys.executable, "-c", launcher], env=environment, cwd=root,
                                capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result
        # Window mapping can precede daemon readiness by a few milliseconds.
        deadline = time.monotonic() + 10
        while True:
            ready = subprocess.run([browser, "snapshot"], env=environment, capture_output=True, text=True, timeout=15)
            if ready.returncode == 0:
                break
            assert time.monotonic() < deadline, ready
            time.sleep(0.1)
        if strip == "yes":
            assert "synthetic-user" in call("localstorage-get", "login"), "profile login did not persist"
        else:
            # Simulated manual phase: local fixture only, no real login or input.
            call("fill", "#name", "Synthetic human")
            call("click", "#login")
            assert "Signed in" in call("eval", "document.querySelector('#status').textContent")
        # Agent resumes in the same live browser after the simulated handback.
        call("snapshot")
        call("click", "#continue")
        assert "Agent continued" in call("eval", "document.querySelector('#status').textContent")
        (root / "result.json").write_text(json.dumps({"status": 0, "stdout": result.stdout, "stderr": result.stderr}))
        wait_for_file(root / "done")
    except Exception as error:
        (root / "result.json").write_text(json.dumps({"status": 1, "stdout": result.stdout if result else "",
                                                     "stderr": str(error)}))
        raise
    finally:
        # Leave the window for the harness controller to verify and close.
        server.shutdown()
        server.server_close()


def main():
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2:])
        return
    index = sys.argv.index("--harness")
    harness = sys.argv[index + 1]
    del sys.argv[index:index + 2]
    # The reused harness invokes its own __file__ for worker/private-DBus reentry.
    # Carry the harness path through both subprocess paths and dispatch our worker.
    os.environ["PI_BROWSER_TEST_HARNESS"] = harness
    spec = importlib.util.spec_from_file_location("workspace_harness", harness)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__file__ = str(Path(__file__).resolve())
    module.main()


if __name__ == "__main__":
    if "--harness" not in sys.argv and sys.argv[1:2] != ["--worker"] and os.environ.get("PI_BROWSER_TEST_HARNESS"):
        sys.argv += ["--harness", os.environ["PI_BROWSER_TEST_HARNESS"]]
    main()
