#!/usr/bin/env python3
"""Local-only browser acceptance test. No personal profile or display required."""
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

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
            for args in (("open", "--headed"), ("attach",), ("show",), ("kill-all",)):
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
            print("PASS: snapshot, fill/click verification, storage/cookie persistence and isolation, cwd stability,")
            print("tabs, screenshot, console/network, refused unsafe controls, failure visibility,")
            print("private artifacts, actual headless/sandbox flags, no project pollution, close/reopen isolation")
        finally:
            for identity in ("acceptance-a", "acceptance-b"):
                run(identity, "close", ok=False)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
