#!/usr/bin/env python3
"""Headed/profile acceptance on Project Object's private headless compositor.

Usage: python3 headed_integration.py --harness /absolute/workspace_exec_integration.py
  --hyprland ... --hyprctl ... --labwc ... --kitty ... --chromium /nix/store/.../bin/pi-browser
  --browser-class vivaldi --keep-target-visible --helper /nix/store/.../bin/project-workspace-exec

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
import urllib.request

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
    shared_profile = os.environ.get("PI_BROWSER_TEST_SHARED") == "1"
    if shared_profile:
        environment["XDG_STATE_HOME"] = str(root.parent / "shared-state")
    command = [browser, "open", "--headed", "--json", "--config=./custom-config.json", "--profile=../shared-profile",
               f"http://127.0.0.1:{server.server_port}/"]
    temporary_profile = os.environ.get("PI_BROWSER_TEST_TEMPORARY") == "1"
    if temporary_profile:
        command = [arg for arg in command if not arg.startswith("--profile=")]
    if shared_profile:
        command = [arg for arg in command if not arg.startswith(("--profile=", "--config="))]
    launcher = "import os,subprocess,time;"
    if strip == "yes" and not shared_profile:
        launcher += "os.environ.pop('HL_EXEC_RULE_TOKEN',None);os.environ.pop('HL_INITIAL_WORKSPACE_TOKEN',None);time.sleep(1.2);"
    launcher += ("import pathlib;opened=subprocess.run(" + repr(command) + ",capture_output=True,text=True);"
                 "pathlib.Path(" + repr(str(root / "open-output.json")) + ").write_text(opened.stdout);"
                 "pathlib.Path(" + repr(str(root / "open-error.log")) + ").write_text(opened.stderr);"
                 "raise SystemExit(opened.returncode)")

    def call(*args):
        result = subprocess.run([browser, *args], env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and "### Error" not in result.stdout, result
        return result.stdout

    result = None
    try:
        call("open", "--headed", "--help")
        session = Path(json.loads(call("paths"))["session"])
        (root / "custom-config.json").write_text((session / "config.json").read_text())
        result = subprocess.run([helper, sys.executable, "-c", launcher], env=environment, cwd=root,
                                capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result
        # Window mapping can precede daemon readiness by a few milliseconds.
        deadline = time.monotonic() + 10
        while True:
            ready = subprocess.run([browser, "snapshot"], env=environment, capture_output=True, text=True, timeout=45)
            if ready.returncode == 0:
                break
            assert time.monotonic() < deadline, ready
            time.sleep(0.1)
        wait_for_file(root / "open-output.json")
        json.loads((root / "open-output.json").read_text())  # Exactly one JSON document.
        state = json.loads((session / "vivaldi-process.json").read_text())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(state["endpoint"] + "/json/list", timeout=5) as response:
            targets = json.load(response)
        assert any(target["type"] == "app" and "chrome-extension://mpognobb" in target["url"]
                   for target in targets), "native Vivaldi UI is not running"
        bitwarden = "chrome-extension://nngceckbapebfimnlniiiahkandclblb/"
        deadline = time.monotonic() + 10
        while True:
            worker_target = next((target for target in targets
                                  if target["type"] == "service_worker" and target["url"].startswith(bitwarden)), None)
            if worker_target:
                break
            assert time.monotonic() < deadline, "packaged Bitwarden extension did not load"
            time.sleep(0.1)
            with opener.open(state["endpoint"] + "/json/list", timeout=5) as response:
                targets = json.load(response)
        # Public extension identity/permission metadata only. No vault storage,
        # native messages, credentials or real Desktop account are accessed.
        script = """let input='';process.stdin.on('data',b=>input+=b);process.stdin.on('end',()=>{
const ws=new WebSocket(JSON.parse(input));const timer=setTimeout(()=>process.exit(1),7000);
ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{awaitPromise:true,returnByValue:true,
expression:`(async()=>({id:chrome.runtime.id,version:chrome.runtime.getManifest().version,
nativePermission:await chrome.permissions.contains({permissions:['nativeMessaging']})}))()`}}));
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id===1){clearTimeout(timer);console.log(JSON.stringify(m.result?.result?.value));ws.close();}};
ws.onerror=()=>process.exit(1);});"""
        metadata = subprocess.run(["node", "-e", script], input=json.dumps(worker_target["webSocketDebuggerUrl"]),
                                  env=environment, text=True, capture_output=True, timeout=10, check=True)
        installed = json.loads(metadata.stdout)
        assert installed == {"id": "nngceckbapebfimnlniiiahkandclblb", "version": "2026.10.2", "nativePermission": False}, installed
        if shared_profile:
            assert Path(state["profile"]) == session.parent / "shared-profile"
            assert not state["temporary"]
            # Only synthetic extension data in this harness's fresh private profile.
            # Proves MV3 storage survives cross-chat restarts without real vault access.
            def evaluate(target, expression):
                program = """let input='';process.stdin.on('data',b=>input+=b);process.stdin.on('end',()=>{
const [url,expression]=JSON.parse(input);const ws=new WebSocket(url);const timer=setTimeout(()=>process.exit(1),7000);
ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{awaitPromise:true,returnByValue:true,expression}}));
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id===1){clearTimeout(timer);console.log(JSON.stringify(m.result?.result?.value));ws.close();}};
ws.onerror=()=>process.exit(1);});"""
                result = subprocess.run(["node", "-e", program],
                    input=json.dumps([target["webSocketDebuggerUrl"], expression]), env=environment,
                    text=True, capture_output=True, timeout=10, check=True)
                return json.loads(result.stdout)
            if strip == "yes":
                assert evaluate(worker_target, "chrome.storage.local.get('piSyntheticPersistence')") == {"piSyntheticPersistence": "retained"}
            else:
                assert evaluate(worker_target, "chrome.storage.local.set({piSyntheticPersistence:'retained'}).then(()=>true)") is True
            ui = next(t for t in targets if t["type"] == "app" and "chrome-extension://mpognobb" in t["url"])
            appearance = evaluate(ui, """(()=>({background:getComputedStyle(document.querySelector('#browser')).backgroundColor,
panel:document.querySelector('#panels-container')?.getBoundingClientRect().width||0,
footer:document.querySelector('footer')?.getBoundingClientRect().height||0,
tabs:!!document.querySelector('.tab-strip'),address:!!document.querySelector('.UrlBar-UrlField')}))()""")
            # Inactive-window dimming changes the exact native Dark RGB value.
            import re
            colors = [int(c) for c in re.findall(r'\d+', appearance.pop("background"))]
            assert len(colors) == 3 and max(colors) < 80, colors
            assert appearance == {"panel": 0, "footer": 0, "tabs": True, "address": True}, appearance
            collision_env = {**environment, "PI_SESSION_ID": "concurrent-profile-probe"}
            collision = subprocess.run([browser, "open", "--headed", "about:blank"], env=collision_env,
                                       capture_output=True, text=True, timeout=15)
            assert collision.returncode != 0 and "already open" in collision.stderr, collision
            deletion = subprocess.run([browser, "delete-data"], env=environment, capture_output=True, text=True, timeout=15)
            assert deletion.returncode != 0 and "retained" in deletion.stderr, deletion
        host = Path(state["profile"]) / "NativeMessagingHosts" / "com.8bit.bitwarden.json"
        manifest = json.loads(host.read_text())
        assert host.is_symlink() and str(host.resolve()).startswith("/nix/store/")
        assert manifest["allowed_origins"] == [bitwarden]
        assert Path(manifest["path"]).is_file() and os.access(manifest["path"], os.X_OK)
        ps = subprocess.check_output(["ps", "-p", str(state["pid"]), "-o", "args="], text=True)
        assert "vivaldi-bin" in ps and "--disable-vivaldi" not in ps and "--no-sandbox" not in ps
        extensions = [arg for arg in ps.split() if arg.startswith("--load-extension=")]
        assert len(extensions) == 1 and "pi-browser-bitwarden-extension" in extensions[0], extensions
        assert "project-object-browser-extension" in extensions[0], "existing browser bridge was replaced"
        if strip == "yes" and not temporary_profile:
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
        # After verification/controller closure, also stop the owned Vivaldi
        # background process so it releases the persistent profile lock.
        call("close")
        if 'state' in locals():
            profile = Path(state["profile"])
            assert profile.exists() is not temporary_profile
            if not temporary_profile and not shared_profile:
                # Explicit profiles remain reusable headlessly too. The shared
                # suite exercises native cross-chat reuse in its second case.
                call("open", "--profile=" + str(profile), f"http://127.0.0.1:{server.server_port}/")
                assert "synthetic-user" in call("localstorage-get", "login")
                call("close")
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
    if os.environ.get("PI_BROWSER_TEST_SHARED") == "1":
        # This suite adds extension storage, native chrome and collision checks
        # to the original placement case; allow its controller adequate time.
        original_wait = module.wait_for
        module.wait_for = lambda predicate, timeout=20: original_wait(predicate, 120 if timeout == 60 else timeout)
    if "--check-transient-focus" not in sys.argv:
        sys.argv.append("--check-transient-focus")
    module.main()


if __name__ == "__main__":
    if "--harness" not in sys.argv and sys.argv[1:2] != ["--worker"] and os.environ.get("PI_BROWSER_TEST_HARNESS"):
        sys.argv += ["--harness", os.environ["PI_BROWSER_TEST_HARNESS"]]
    main()
