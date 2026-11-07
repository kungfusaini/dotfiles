"""Optional installed-Pi probe: windowless/offline, fixtures only, no model prompt.

Usage: python tests/tablet_pi_selection.py CONTROLLER.py UI_BUNDLE PI_BINARY
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location("selection_probe", sys.argv[1])
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
bundle, pi = Path(sys.argv[2]), sys.argv[3]

with tempfile.TemporaryDirectory(prefix="tablet-selection-check-", dir=os.environ["XDG_RUNTIME_DIR"]) as temporary:
    os.umask(0o077)
    root = Path(temporary)
    sessions = root / "sessions"
    sessions.mkdir()
    (root / "project").mkdir()
    (sessions / "draft.txt").touch()
    wrapper = root / "offline-pi"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(pi) + ' --no-extensions --no-skills --no-prompt-templates --no-themes "$@"\n')
    wrapper.chmod(0o700)
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic",
                      XDG_RUNTIME_DIR=temporary, HOME=temporary, PI_CODING_AGENT_DIR=temporary + "/agent-config",
                      XDG_CONFIG_HOME=temporary + "/config", XDG_CACHE_HOME=temporary + "/cache", XDG_STATE_HOME=temporary + "/state",
                      WAYLAND_DISPLAY="", DISPLAY="", TABLET_NATIVE_CHAT="1", TABLET_CHAT_PI=str(wrapper),
                      TABLET_CHAT_CWD=str(root / "project"), TABLET_CHAT_SESSIONS=str(sessions), TABLET_CHAT_PROVIDER="openai-codex",
                      TABLET_CHAT_MODEL="gpt-5.4", TABLET_CHAT_PROMPT=str(bundle / "share/tablet-ui/tablet-context.md"))

    def seed(path, text):
        message = dict(role="assistant", content=[dict(type="text", text=text)], api="openai-codex-responses",
                       provider="openai-codex", model="gpt-5.4", stopReason="stop", timestamp=1793793600000,
                       usage=dict(input=0, output=0, cacheRead=0, cacheWrite=0, totalTokens=0,
                                  cost=dict(input=0, output=0, cacheRead=0, cacheWrite=0, total=0)))
        common = dict(timestamp="2026-11-04T12:00:00.000Z")
        entries = [dict(common, type="session", version=3, id=str(uuid.uuid4()), cwd=str(root / "project")),
                   dict(common, type="message", id="a1234567", parentId=None, message=message)]
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    old = sessions / "old.jsonl"
    seed(old, "Offline old fixture")
    process = None

    def ipc(method, *arguments):
        return subprocess.run(["quickshell", "ipc", "--pid", str(process.pid), "call", "tabletAgent", method, *arguments],
                              check=True, capture_output=True, text=True, timeout=4).stdout

    def state():
        return json.loads(ipc("snapshot"))

    def wait(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Windowless backend exited")
            try:
                current = state()
                if predicate(current): return current
            except (subprocess.SubprocessError, ValueError):
                pass
            time.sleep(.05)
        raise RuntimeError("Windowless selection probe timed out")

    def start():
        global process
        process = subprocess.Popen(["quickshell", "--path", str(bundle / "share/tablet-ui/agent.qml")],
                                   env=ui.session_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return wait(lambda current: current["ready"] and not current["selectionPending"])

    def close():
        ipc("shutdown")
        process.wait(timeout=8)

    try:
        assert start()["messages"][0]["text"] == "Offline old fixture"
        selection = sessions / "selection.json"
        backup = sessions / "selection-backup.json"
        selection.replace(backup)
        selection.mkdir()  # Fail only selection writes, not session/draft storage.
        requests = ui.directory() / "requests"
        requests.mkdir()
        request = requests / "new"
        request.write_text(json.dumps(dict(action="new_chat")))
        assert json.loads(ipc("dispatch", str(request)))["accepted"]
        wait(lambda current: current["generation"] == 1 and current["selectionPending"])
        time.sleep(1.1)
        assert state()["selectionPending"] and "selection is not saved" in state()["error"]
        selection.rmdir()
        backup.replace(selection)
        wait(lambda current: not current["selectionPending"])
        chosen = Path(json.loads(selection.read_text())["sessionFile"])
        close()
        assert start()["messages"] == [], "Empty New chat resumed the old conversation"
        refreshed = Path(json.loads(selection.read_text())["sessionFile"])
        if not chosen.exists(): assert refreshed != chosen, "Fresh startup did not refresh selection"
        close()
        seed(refreshed, "Offline new fixture")  # Saved-message fixture, never a model call.
        assert start()["messages"][0]["text"] == "Offline new fixture", "Wrong session resumed"
        close()
        assert "Offline old fixture" in old.read_text(), "Old session was changed/deleted"
        print("Installed Pi: selection write failure/retry, empty New chat close/reopen and exact saved-session resume passed; no model/extension/display/audio/input.")
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
