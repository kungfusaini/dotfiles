#!/usr/bin/env python3
"""Local-only browser acceptance test. No personal profile or display required."""
import http.server
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

PAGE = b'''<!doctype html><title>Pi browser fixture</title>
<label>Name <input id="name"></label><button id="save" onclick="
localStorage.setItem('name', document.querySelector('#name').value);
document.querySelector('#result').textContent='Saved '+localStorage.getItem('name');
">Save</button><p id="result">Not saved</p>
<script>console.log('fixture loaded')</script>'''


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


def main():
    executable = str(Path(sys.argv[1]).resolve())
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    with tempfile.TemporaryDirectory(prefix="pi-browser-acceptance-") as temp:
        work = Path(temp)
        first_cwd = work / "first"
        second_cwd = work / "second"
        first_cwd.mkdir()
        second_cwd.mkdir()
        base = dict(os.environ, XDG_STATE_HOME=str(work / "state"),
                    PLAYWRIGHT_MCP_CDP_ENDPOINT="http://127.0.0.1:1",
                    PLAYWRIGHT_MCP_HEADLESS="false")

        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "XAUTHORITY"):
            base.pop(key, None)

        def run(identity, *args, cwd=first_cwd, ok=True):
            result = subprocess.run([executable, *args], env={**base, "PI_SESSION_ID": identity},
                                    cwd=cwd, text=True, capture_output=True, timeout=70)
            if ok and (result.returncode or "### Error" in result.stdout):
                raise AssertionError(f"{args}: {result.returncode}\n{result.stdout}\n{result.stderr}")
            return result

        def root(identity):
            return Path(json.loads(run(identity, "paths").stdout)["session"])

        def snapshot(identity):
            result = run(identity, "snapshot")
            match = re.search(r'\[Snapshot\]\((.*?)\)', result.stdout)
            if match:
                return (root(identity) / match[1]).read_text()
            assert "```yaml" in result.stdout, result.stdout
            return result.stdout

        try:
            for identity in ("acceptance-a", "acceptance-b"):
                run(identity, "open", url)
            text = snapshot("acceptance-a")
            input_ref = re.search(r'textbox "Name" \[ref=(e\d+)\]', text).group(1)
            button_ref = re.search(r'button "Save" \[ref=(e\d+)\]', text).group(1)
            run("acceptance-a", "fill", input_ref, "Alice")
            run("acceptance-a", "click", button_ref)
            assert "Saved Alice" in snapshot("acceptance-a")
            for literal in ("-draft", "--help", "--headed"):
                run("acceptance-a", "fill", "#name", "--", literal)
                assert literal in run("acceptance-a", "eval", "document.querySelector('#name').value").stdout
            assert "Not saved" in snapshot("acceptance-b")
            assert "Alice" in run("acceptance-a", "localstorage-get", "name", cwd=second_cwd).stdout
            assert "Alice" not in run("acceptance-b", "localstorage-get", "name").stdout
            run("acceptance-a", "cookie-set", "fixture-cookie", "synthetic-test-only")
            assert "synthetic-test-only" in run("acceptance-a", "cookie-get", "fixture-cookie").stdout
            assert "synthetic-test-only" not in run("acceptance-b", "cookie-get", "fixture-cookie").stdout
            run("acceptance-a", "reload")
            assert "Alice" in run("acceptance-a", "localstorage-get", "name").stdout
            run("acceptance-a", "tab-new", url + "second")
            assert "second" in run("acceptance-a", "tab-list").stdout
            run("acceptance-a", "tab-select", "0")
            run("acceptance-a", "screenshot")
            assert list((root("acceptance-a") / "artifacts").glob("*.png"))
            assert "fixture loaded" in run("acceptance-a", "console").stdout
            requests = run("acceptance-a", "requests", "--static").stdout
            if "127.0.0.1" not in requests:
                links = re.findall(r'\]\((.*?)\)', requests)
                assert any("127.0.0.1" in (root("acceptance-a") / link).read_text()
                           for link in links), requests
            for args in (("kill-all",), ("close-all",), ("install",), ("open", "--session=other")):
                assert run("acceptance-a", *args, ok=False).returncode != 0
            assert root("acceptance-a") != root("acceptance-b")
            for identity in ("acceptance-a", "acceptance-b"):
                directory = root(identity)
                assert directory.stat().st_mode & 0o777 == 0o700
                sessions = list((directory / "cache").rglob("*.session"))
                assert len(sessions) == 1
                config = json.loads(sessions[0].read_text())
                assert config["browser"]["launchOptions"]["headless"] is True
                assert config["browser"]["launchOptions"]["chromiumSandbox"] is True
                assert not config.get("attached")
                # Verify the actual browser command, not just requested configuration.
                assert "Pi browser fixture" in run(identity, "eval", "document.title").stdout
                runtime = json.loads(run(identity, "paths").stdout)["temporary"]
                # Use procps, which handles this host's /proc access policy.
                ps = subprocess.check_output(["ps", "-eo", "args"], text=True)
                processes = [line.split() for line in ps.splitlines()
                             if "--user-data-dir=" + runtime + "/" in line]
                assert processes, f"No Chromium process for {identity}"
                assert all("--no-sandbox" not in command for command in processes)
                assert any(any(arg.startswith("--headless") for arg in command) for command in processes)
            assert not list(first_cwd.iterdir()) and not list(second_cwd.iterdir())
            failed = run("acceptance-a", "click", "#nonexistent", ok=False)
            assert failed.returncode != 0 and "### Error" in failed.stdout
            run("acceptance-a", "close")
            run("acceptance-a", "open", url)
            assert "Alice" not in run("acceptance-a", "localstorage-get", "name").stdout
            assert "synthetic-test-only" not in run("acceptance-a", "cookie-get", "fixture-cookie").stdout
            assert "Not saved" in snapshot("acceptance-b")
            run("acceptance-a", "close")
            run("acceptance-a", "open", "--persistent", url)
            run("acceptance-a", "localstorage-set", "persistent-fixture", "synthetic-login")
            run("acceptance-a", "eval", "document.cookie='persisted=synthetic; max-age=3600; path=/'")
            run("acceptance-a", "close")
            run("acceptance-a", "open", "--persistent", url)
            assert "synthetic-login" in run("acceptance-a", "localstorage-get", "persistent-fixture").stdout
            assert "synthetic" in run("acceptance-a", "cookie-get", "persisted").stdout
            run("acceptance-a", "close")
            run("acceptance-b", "close")
            # Explicit profiles can be reused sequentially across Pi sessions.
            run("acceptance-a", "open", "--profile=shared-profile", url)
            run("acceptance-a", "localstorage-set", "shared-fixture", "synthetic-shared")
            run("acceptance-a", "close")
            profile = first_cwd / "shared-profile"
            run("acceptance-b", "open", "--profile=" + str(profile), url, cwd=second_cwd)
            assert "synthetic-shared" in run("acceptance-b", "localstorage-get", "shared-fixture").stdout
            run("acceptance-b", "close")
            # User configs replace wrapper defaults and resolve from caller cwd.
            config = json.loads((root("acceptance-a") / "config.json").read_text())
            chromium = config["browser"]["launchOptions"]["executablePath"]
            (first_cwd / "custom.json").write_text(json.dumps(config))
            run("acceptance-a", "open", "--config=custom.json", url)
            assert "Pi browser fixture" in run("acceptance-a", "eval", "document.title").stdout
            run("acceptance-a", "close")
            # Attach to a separately owned synthetic headless browser, then detach
            # without terminating it. Never use a personal debugging endpoint.
            temporary = Path(json.loads(run("acceptance-a", "paths").stdout)["temporary"])
            external_profile = temporary / "external-profile"
            external_env = {k: v for k, v in base.items() if not k.startswith("PLAYWRIGHT_")}
            external_env["TMPDIR"] = str(temporary)
            with (work / "external.log").open("w") as log:
                external = subprocess.Popen([chromium, "--headless", "--remote-debugging-address=127.0.0.1",
                                             "--remote-debugging-port=0", "--user-data-dir=" + str(external_profile),
                                             "--no-first-run", "--no-default-browser-check", url],
                                            env=external_env, stdout=log, stderr=log, start_new_session=True)
                try:
                    active_port = external_profile / "DevToolsActivePort"
                    deadline = time.monotonic() + 20
                    while not active_port.exists() and time.monotonic() < deadline:
                        assert external.poll() is None, (work / "external.log").read_text()
                        time.sleep(0.05)
                    port = int(active_port.read_text().splitlines()[0])
                    endpoint = f"http://127.0.0.1:{port}"
                    run("acceptance-a", "attach", "--cdp=" + endpoint)
                    assert "Pi browser fixture" in run("acceptance-a", "eval", "document.title").stdout
                    run("acceptance-a", "fill", "#name", "Attached")
                    run("acceptance-a", "click", "#save")
                    assert "Saved Attached" in snapshot("acceptance-a")
                    run("acceptance-a", "detach")
                    assert external.poll() is None
                    with urllib.request.urlopen(endpoint + "/json/list", timeout=5) as response:
                        assert any(page.get("title") == "Pi browser fixture" for page in json.load(response))
                finally:
                    os.killpg(external.pid, signal.SIGTERM)
                    external.wait(timeout=10)
            print("PASS: headless interaction and isolation, persistent close/reopen login state,")
            print("cross-session explicit profiles, custom config, external CDP attach/drive/detach,")
            print("tabs/screenshots/diagnostics, failure visibility and actual sandbox/headless flags")
        finally:
            for identity in ("acceptance-a", "acceptance-b"):
                run(identity, "close", ok=False)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
