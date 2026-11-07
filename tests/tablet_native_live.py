"""Private-compositor integration: fake Pi only, no OSK/audio/host input."""
import importlib.util
import io
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from PIL import Image

spec = importlib.util.spec_from_file_location("tablet_live_controller", sys.argv[1])
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
os.umask(0o077)
ui.hypr = lambda *_: [{"name": "eDP-1", "reserved": [0, 0, 0, 0]}]
trial = ui.Trial(target={"instance": "isolated-fixture"})
trial.foreground = lambda: True
trial.safe = lambda: True
ui.binding = lambda: (trial.target, None)  # No host project/terminal lookup in native navigation.
trial.view = "home"
trial.pi_started = False
stop = threading.Event()
errors = []
log = Path("live-surfaces.log").open("w")
server = socket.socket(socket.AF_UNIX)
server.bind(str(ui.directory() / "control.sock"))
server.listen(8)


def serve():
    try:
        while not stop.is_set():
            if select.select([server], [], [], .02)[0]:
                with server.accept()[0] as connection:
                    ui.respond(trial, connection)
            trial.tick()
    except Exception as error:
        errors.append(error)


def until(predicate, label):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if errors: raise errors[0]
        try:
            if predicate(): return
        except (RuntimeError, subprocess.SubprocessError):
            pass  # Quickshell IPC registration is asynchronous during startup.
        time.sleep(.05)
    raise AssertionError(label)


def screenshot():
    # Only the hermetic compositor: never read a host display.
    assert os.environ.get("TABLET_STAGE_SCREEN") == "HEADLESS-1"
    assert not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    return Image.open(io.BytesIO(subprocess.check_output([os.environ["TABLET_TEST_GRIM"], "-"]))).convert("RGB")


def assert_home_backdrop(home, name):
    time.sleep(.1)
    image = screenshot()
    # Left gutter: outside the cards and Home labels. The switcher's scrim is
    # #a5122634, so every sampled pixel must be dimmed Home, not dimmed Pi/mock.
    for x in (5, 10, 20):
        for y in range(160, 480, 10):
            expected = tuple(round((base * 90 + tint * 165) / 255)
                             for base, tint in zip(home.getpixel((x, y)), (18, 38, 52)))
            actual = image.getpixel((x, y))
            assert max(abs(a - b) for a, b in zip(actual, expected)) <= 2, (name, "not Home behind cards", x, y, actual, expected)
    image.save(name + "-home-backdrop.png")


def state():
    return ui.request("agent-state")


def action(record):
    requests = ui.directory() / "requests"
    requests.mkdir(exist_ok=True)
    path = requests / "test-command"
    ui.private_write(path, json.dumps(record))
    try:
        return ui.request("agent-command", path=str(path))
    finally:
        path.unlink()


def queue(bundle):
    roots = ui.chat_state() / "ui-roots"
    roots.mkdir(exist_ok=True)
    root = roots / ui.uuid.uuid4().hex
    root.symlink_to(bundle)
    return ui.request("apply-ui", bundle=bundle, root=str(root))


def navigation(method, *arguments):
    result = trial.ipc(trial.shell, "testNavigation", method, *arguments)
    return json.loads(result) if method == "state" else result


def private_click(x, y):
    # Virtual pointer is permitted only in the hermetic single-headless-output
    # fixture, never on a host compositor or physical input device.
    assert os.environ.get("TABLET_STAGE_SCREEN") == "HEADLESS-1"
    assert not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    for args in (("move", "-10000", "-10000"), ("move", str(x), str(y)), ("click", "left")):
        subprocess.run(["wlrctl", "pointer", *args], check=True, timeout=4)


thread = None
preview = recorder = virtual_keyboard = osk = None
record_log = Path("transition-recording.log").open("w")
try:
    # Headless wlroots otherwise has no keyboard seat capability, so even a
    # clicked OnDemand layer cannot receive wl_keyboard.enter. Register a
    # private virtual keyboard but sleep throughout; it sends NO keys.
    assert os.environ.get("TABLET_STAGE_SCREEN") == "HEADLESS-1" and not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    virtual_keyboard = subprocess.Popen(["wtype", "-s", "600000", "-k", "Shift_L"], stdout=log, stderr=log)
    time.sleep(.1)
    assert virtual_keyboard.poll() is None, "private virtual keyboard was unavailable"
    subprocess.run(["gsettings", "set", "org.gnome.desktop.a11y.applications", "screen-keyboard-enabled", "true"], check=True)
    osk = subprocess.Popen(["squeekboard"], stdout=log, stderr=log)
    trial.keyboard = osk
    def keyboard_visible():
        result = subprocess.run(["gdbus", "call", "--session", "--dest", "sm.puri.OSK0", "--object-path", "/sm/puri/OSK0",
                                 "--method", "org.freedesktop.DBus.Properties.Get", "sm.puri.OSK0", "Visible"],
                                check=True, capture_output=True, text=True, timeout=3).stdout
        return "<true>" in result
    until(lambda: keyboard_visible() in (True, False), "private Squeekboard service never became available")
    # Closing a Home-first session before opening Pi must terminate the idle
    # backend cleanly without ever starting the model/RPC process.
    probe = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_AGENT_QML"]],
                             env=dict(os.environ, TABLET_DEFER_PI="1"), stdout=log, stderr=log)
    try:
        until(lambda: json.loads(trial.ipc(probe, "tabletAgent", "snapshot"))["piStarted"] is False, "idle backend never ready")
        assert not Path(os.environ["TABLET_FAKE_RPC_LOG"]).exists()
        trial.ipc(probe, "tabletAgent", "shutdown")
        probe.wait(timeout=5)
    finally:
        if probe.poll() is None: probe.terminate(); probe.wait(timeout=5)
    # The production stage covers entry before the FIRST Home. There is no
    # standalone launcher/second UI in this journey. Labwc has no workspace
    # animations; Hyprland policy/geometry and entry ordering have unit checks.
    trial.layer_opaque = lambda *_: True
    trial.verify_presentation_policy = lambda: None
    trial.start_stage(os.environ["TABLET_ITERATION_QML"])
    recorder = subprocess.Popen(["wf-recorder", "--no-dmabuf", "-D", "-r", "60", "-c", "rawvideo", "-x", "rgb24", "-m", "nut", "-f", "transition-recording.nut"], stdout=record_log, stderr=record_log)
    time.sleep(.3)
    assert recorder.poll() is None, "private recorder did not start"
    time.sleep(.6)
    draft_path = ui.chat_state() / "draft.txt"
    ui.private_write(draft_path, "Hand-off draft 🌿")
    draft_backup = ui.chat_state() / "draft-startup-backup"
    history_gate = ui.directory() / "history-ready"
    startup_gate = ui.directory() / "startup-question"
    os.environ["TABLET_RPC_HISTORY_GATE"] = str(history_gate)
    os.environ["TABLET_RPC_STARTUP_QUESTION_GATE"] = str(startup_gate)
    trial.agent = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_AGENT_QML"]],
                                   env=dict(os.environ, TABLET_DEFER_PI="1"), stdout=log, stderr=log)
    trial.shell = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_ITERATION_QML"]], stdout=log, stderr=log)
    trial.entry_pending = True
    trial.entry_deadline = time.monotonic() + 20
    trial.journal()
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    until(lambda: json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["connected"], "UI bridge never connected")
    until(lambda: not trial.entry_pending, "first Home did not become presented")
    assert not state()["piStarted"] and not Path(os.environ["TABLET_FAKE_RPC_LOG"]).exists(), "Pi started before icon click"
    until(lambda: not keyboard_visible(), "Squeekboard remained visible over Home without text input")
    assert "tablet-improve" not in navigation("state")["opened"]
    first_identity = (trial.shell.pid, trial.stage.pid, trial.agent.pid)
    home_backdrop = screenshot()
    for app in ("browser", "music", "games", "art"):
        navigation("choose", app)
        time.sleep(.15)
        if app == "music":
            navigation("openOverview")
            until(lambda: not json.loads(navigation("previews"))["capturing"], "mock preview capture stuck")
            assert_home_backdrop(home_backdrop, "mock-switcher")
            navigation("choose", app)
            until(lambda: not navigation("state")["overview"], "mock resume failed")
        navigation("home")
        time.sleep(.1)
    navigation("choose", "tablet-improve")
    until(lambda: trial.view == "pi" and trial.pi_started, "Pi icon did not start in the existing session")
    assert (trial.shell.pid, trial.stage.pid, trial.agent.pid) == first_identity, "Pi spawned a second tablet interface"
    assert "music" in navigation("state")["opened"], "Pi entry lost the first Home's app history"
    time.sleep(.4)
    blocked = json.loads(trial.ipc(trial.shell, "tabletUi", "status"))
    assert not state()["ready"] and not blocked["mapped"] and not blocked["contentReady"]
    assert json.loads(trial.ipc(trial.stage, "tabletStage", "status"))["cover"], "unready backend obscured launch cover"
    startup_gate.touch()
    until(lambda: state()["question"] is not None, "startup question missing")
    until(lambda: not trial.entry_pending, "actionable startup question was not presented")
    assert action({"action": "answer", "id": "startup-confirm", "answer": {"confirmed": False}})["accepted"]
    until(lambda: state()["question"] is None, "startup answer was not accepted")
    time.sleep(.4)
    admitted = json.loads(trial.ipc(trial.shell, "tabletUi", "status"))
    assert not state()["ready"] and not admitted["contentReady"]
    assert admitted["mapped"], "answering startup question unmapped an already-admitted app"
    # Re-cover before deliberately replacing this test frontend with one whose
    # draft cannot be restored. The backend and its delayed history stay alive.
    stop.set()
    thread.join(timeout=10)
    trial.ipc(trial.stage, "tabletStage", "cover", "Checking startup recovery…")
    trial.wait_stage()
    trial.entry_pending = True
    trial.shell.terminate()
    trial.shell.wait(timeout=5)
    draft_path.replace(draft_backup)
    draft_path.mkdir()
    trial.shell = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_ITERATION_QML"]], stdout=log, stderr=log)
    trial.entry_deadline = time.monotonic() + 20
    trial.journal()
    stop.clear()
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    history_gate.touch()
    until(lambda: state()["ready"], "agent never ready")
    until(lambda: json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["connected"], "failed-restore UI never connected")
    blocked = json.loads(trial.ipc(trial.shell, "tabletUi", "status"))
    assert not blocked["draftRestored"] and not blocked["mapped"]
    assert json.loads(trial.ipc(trial.stage, "tabletStage", "status"))["cover"], "failed draft restore obscured launch cover"
    # Replace only the still-unmapped frontend after repairing the private test
    # fixture. Use the production responder so retired polling clients are safe.
    stop.set()
    thread.join(timeout=10)
    draft_path.rmdir()
    draft_backup.replace(draft_path)
    trial.shell.terminate()
    trial.shell.wait(timeout=5)
    trial.shell = subprocess.Popen(["quickshell", "--path", os.environ["TABLET_ITERATION_QML"]], stdout=log, stderr=log)
    trial.entry_deadline = time.monotonic() + 20
    trial.journal()
    stop.clear()
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    until(lambda: json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["connected"]
          and json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["mapped"], "UI never ready")
    assert not json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["updating"], "ordinary startup incorrectly locked as an update"
    until(lambda: not trial.entry_pending, "cover revealed before app presentation or never revealed")
    time.sleep(.3)
    private_click(400, 4)  # Activate the app by tapping non-text header padding.
    until(lambda: json.loads(navigation("inputState"))["windowActive"], "private Pi window did not activate")
    assert not json.loads(navigation("inputState"))["inputActive"], "non-text activation focused the composer"
    point = json.loads(navigation("editorPoint"))
    private_click(point["x"], point["y"])
    until(lambda: json.loads(navigation("inputState"))["inputActive"], "composer tap did not activate input")
    until(keyboard_visible, "Squeekboard did not actually show for selected composer")
    private_click(400, 4)
    until(lambda: not json.loads(navigation("inputState"))["inputActive"], "header tap did not blur input")
    until(lambda: not keyboard_visible(), "Squeekboard stayed visible after header tap")
    assert subprocess.run(["gsettings", "get", "org.gnome.desktop.a11y.applications", "screen-keyboard-enabled"],
                          check=True, capture_output=True, text=True).stdout.strip() == "true", "visibility API unexpectedly changed keyboard enablement"
    for outside in ((4, 250), (796, 250), (400, 200)):
        private_click(point["x"], point["y"])
        until(keyboard_visible, "Squeekboard did not reopen before tap-away check")
        private_click(*outside)
        until(lambda: not json.loads(navigation("inputState"))["inputActive"], "tap-away region did not blur editor")
        until(lambda: not keyboard_visible(), "real Squeekboard stayed visible after tap-away")
    private_click(point["x"], point["y"])
    until(keyboard_visible, "Squeekboard did not reopen for selected composer")
    # Exercise controller-driven navigation as well as the gesture path; the
    # frontend must clear stale nested TextArea/ScrollView focus on remapping.
    ui.request("home")
    until(lambda: not trial.entry_pending, "external Home did not finish")
    ui.request("pi")
    until(lambda: not trial.entry_pending, "external Pi resume did not finish")
    time.sleep(.3)
    private_click(400, 4)
    until(lambda: json.loads(navigation("inputState"))["windowActive"], "resumed private Pi did not activate")
    assert not json.loads(navigation("inputState"))["inputActive"], "Pi resume restored unrequested editor focus"
    until(lambda: not keyboard_visible(), "Squeekboard reappeared on Pi resume without input selection")
    point = json.loads(navigation("editorPoint"))
    private_click(point["x"], point["y"])
    until(lambda: json.loads(navigation("inputState"))["inputActive"], "explicit input selection stopped working")
    input_before = json.loads(navigation("inputState"))
    focused_ui, focused_agent = trial.shell.pid, trial.agent.pid
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    until(lambda: trial.ui_update["phase"] == "applied" and trial.shell.pid != focused_ui, "focused input handoff failed")
    until(lambda: json.loads(navigation("inputState"))["inputActive"], "genuine editor focus was not restored")
    input_after = json.loads(navigation("inputState"))
    assert input_after["cursor"] == input_before["cursor"] and input_after["draftHash"] == input_before["draftHash"]
    assert trial.agent.pid == focused_agent, "focus update restarted Pi"
    until(keyboard_visible, "Squeekboard did not restore for a genuinely focused handoff")
    private_click(400, 200)  # Transcript padding, outside any input field.
    until(lambda: not json.loads(navigation("inputState"))["inputActive"], "outside tap did not clear input")
    until(lambda: not keyboard_visible(), "Squeekboard remained visible after transcript tap")
    navigation("home")
    until(lambda: trial.view == "home", "quick Home did not navigate")
    until(lambda: not trial.entry_pending, "Home transition did not finish under cover")
    navigation("choose", "music")
    until(lambda: navigation("state")["mock"] == "Spotify", "mock app did not open")
    navigation("home")
    until(lambda: navigation("state")["mock"] == "", "mock Home did not finish preview capture")
    until(lambda: not json.loads(navigation("previews"))["capturing"], "preview capture stuck")
    saved_previews = json.loads(navigation("previews"))["images"]
    assert "tablet-improve" in saved_previews and "music" in saved_previews, "inactive app previews were lost"
    navigation("choose", "browser")
    until(lambda: navigation("state")["mock"] == "Vivaldi", "second mock did not open")
    navigation("home")
    until(lambda: navigation("state")["mock"] == "", "second mock did not return Home")
    images = json.loads(navigation("previews"))["images"]
    assert all(images[key] == value for key, value in saved_previews.items()), "opening another app replaced retained previews"
    assert "browser" in images
    navigation("dismiss", "browser")
    assert "browser" not in navigation("state")["opened"]
    assert "browser" not in json.loads(navigation("previews"))["images"]
    shown = json.loads(navigation("openOverview"))
    assert shown["overview"], ("during-show", shown, navigation("debug"))
    home_nav = navigation("state")
    assert home_nav["overview"] and "music" in home_nav["opened"], (home_nav, navigation("debug"))
    time.sleep(.3)
    home_card_ui = trial.shell.pid
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    until(lambda: trial.ui_update["phase"] == "applied" and trial.shell.pid != home_card_ui, "Home switcher handoff failed")
    assert navigation("state") == home_nav, "Home app cards lost during frontend replacement"
    navigation("choose", "tablet-improve")
    until(lambda: trial.view == "pi", "Pi card did not resume its app")
    until(lambda: not trial.entry_pending, "Pi transition did not finish under cover")
    agent_pid = trial.agent.pid
    assert action({"action": "prompt", "text": "stream"})["accepted"]
    until(lambda: state()["messages"][-1]["text"] == "Stream before refresh", "stream missing")
    before = state()
    navigation("openOverview")
    until(lambda: not json.loads(navigation("previews"))["capturing"], "Pi preview capture stuck")
    assert_home_backdrop(home_backdrop, "pi-switcher")
    nav_before = navigation("state")
    assert nav_before["overview"] and "music" in nav_before["opened"]
    old_card_ui = trial.shell.pid
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    until(lambda: trial.ui_update["phase"] == "applied" and trial.shell.pid != old_card_ui, "switcher handoff failed")
    assert navigation("state") == nav_before, "open apps/switcher lost during frontend replacement"
    assert trial.agent.pid == agent_pid and state()["messages"] == before["messages"]
    navigation("choose", "tablet-improve")
    assert not navigation("state")["overview"]
    old_ui = trial.shell.pid
    # Simulate unresolved dictation, without a recording process or audio API.
    trial.transcript.write_text("Pending fake dictation")
    queue(os.environ["TABLET_TEST_ALTERNATE_UI"])
    time.sleep(.4)
    assert trial.ui_update["phase"] == "queued" and trial.shell.pid == old_ui
    assert trial.transcript.read_text() == "Pending fake dictation"
    ui.request("cancel")
    until(lambda: trial.ui_update["phase"] == "applied", "UI replacement did not apply")
    assert trial.agent.pid == agent_pid and trial.agent.poll() is None
    assert trial.shell.pid != old_ui and trial.shell.poll() is None
    after = state()
    assert after["busy"] and after["messages"] == before["messages"]
    assert (ui.chat_state() / "draft.txt").read_text() == "Hand-off draft 🌿"
    # Events continue arriving through the same backend after the UI handoff.
    assert action({"action": "abort"})["accepted"]
    until(lambda: not state()["busy"], "stream did not settle")
    assert state()["messages"][-1]["text"] == "Stream stopped after refresh"
    # A broken immutable scene must leave the old UI/backend/draft usable.
    good_ui = trial.shell.pid
    current = (ui.chat_state() / "current-ui.json").read_text()
    queue(os.environ["TABLET_TEST_BAD_UI"])
    until(lambda: trial.ui_update["phase"] == "failed", "bad UI was not rolled back")
    assert trial.shell.pid == good_ui and trial.shell.poll() is None
    assert trial.agent.pid == agent_pid and trial.agent.poll() is None
    assert (ui.chat_state() / "current-ui.json").read_text() == current
    assert (ui.chat_state() / "draft.txt").read_text() == "Hand-off draft 🌿"
    # Defer on unfinished extension input instead of losing a dialog answer.
    assert action({"action": "prompt", "text": "/question"})["accepted"]
    until(lambda: state()["question"] is not None, "extension question missing")
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    time.sleep(.4)
    assert trial.ui_update["phase"] == "queued" and trial.shell.pid == good_ui
    assert state()["question"]["id"] == "confirm-1"
    draft = ui.chat_state() / "draft.txt"
    ui.chat_state().chmod(0o500)  # Private temp storage only: force atomic-save failure.
    assert action({"action": "answer", "id": "confirm-1", "answer": {"confirmed": False}})["accepted"]
    until(lambda: state()["editorVersion"] == 1 and not json.loads(trial.ipc(trial.shell, "tabletUi", "status"))["draftSaved"], "save failure not observed")
    assert state()["editorAck"] == 0 and draft.read_text() == "Hand-off draft 🌿"
    assert not json.loads(trial.ipc(trial.shell, "tabletUi", "persistDraft"))["saved"]
    try:
        trial.action("close")
        raise AssertionError("unfold discarded an unsaved draft")
    except RuntimeError as error:
        assert "draft" in str(error)
    assert not trial.stopping and trial.shell.poll() is None
    # Even an erroneous frontend ack cannot discard the recoverable event.
    digest = hashlib.md5(b"Unsent draft").hexdigest()
    assert not action({"action": "ack_editor", "version": 1, "digest": digest})["accepted"]
    assert state()["editorAck"] == 0
    time.sleep(.4)
    assert trial.ui_update["phase"] == "queued" and trial.shell.pid == good_ui
    ui.chat_state().chmod(0o700)
    until(lambda: state()["editorAck"] == 1, "editor event was not retried/saved/acknowledged")
    until(lambda: trial.ui_update["phase"] == "applied", "resolved-input handoff failed")
    assert draft.read_text() == "Unsent draft"
    # Dismiss the active Pi card without terminating its backend or saved chat.
    dismissal_state = state()
    dismissal_agent = trial.agent.pid
    navigation("openOverview")
    until(lambda: not json.loads(navigation("previews"))["capturing"], "Pi preview capture stuck")
    # Hold the frontend poll across the controller's Home acknowledgement to
    # reproduce a queued handoff in the pending-dismissal window deterministically.
    navigation("pauseStatus")
    until(lambda: json.loads(navigation("statusIdle")), "status poll did not stop")
    navigation("dismiss", "tablet-improve")
    until(lambda: trial.view == "home", "Pi dismissal did not return Home")
    until(lambda: json.loads(navigation("actionIdle")), "dismissal command did not exit")
    # Repeated Home / another-app navigation cannot clear the pending close.
    navigation("choose", "music")
    navigation("home")
    assert json.loads(navigation("debug"))["dismissPiPending"], "subsequent navigation cancelled dismissal"
    dismissal_ui = trial.shell.pid
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    time.sleep(.5)
    assert trial.ui_update["phase"] == "queued" and trial.shell.pid == dismissal_ui, "handoff raced pending card dismissal"
    navigation("resumeStatus")
    until(lambda: trial.ui_update["phase"] == "applied" and trial.shell.pid != dismissal_ui, "dismissal did not release handoff")
    until(lambda: "tablet-improve" not in navigation("state")["opened"], "Pi card reappeared after dismissal")
    time.sleep(.4)  # Status polling must not recreate the dismissed card.
    assert "tablet-improve" not in navigation("state")["opened"]
    assert trial.agent.pid == dismissal_agent and state()["messages"] == dismissal_state["messages"]
    assert draft.read_text() == "Unsent draft"
    navigation("choose", "tablet-improve")
    until(lambda: trial.view == "pi" and not trial.entry_pending, "dismissed Pi could not reopen")
    assert trial.agent.pid == dismissal_agent and state()["messages"] == dismissal_state["messages"]
    assert draft.read_text() == "Unsent draft"
    # A cancelled reset preserves history and draft; a successful one clears both.
    history = state()["messages"]
    assert action({"action": "new_chat"})["accepted"]
    until(lambda: not state()["resetting"], "cancelled reset stuck")
    assert state()["generation"] == 0 and state()["messages"] == history
    assert (ui.chat_state() / "draft.txt").read_text() == "Unsent draft"
    selection = ui.chat_state() / "selection.json"
    backup = ui.chat_state() / "selection-fixture-backup.json"
    selection.replace(backup)
    selection.mkdir()  # Break only marker writes; draft/session storage stays usable.
    assert action({"action": "new_chat"})["accepted"]
    until(lambda: state()["generation"] == 1, "new chat stuck")
    until(lambda: state()["selectionPending"], "failed selection was not retained")
    assert "selection is not saved" in state()["error"]
    pending_ui = trial.shell.pid
    queue(os.environ["TABLET_TEST_GOOD_UI"])
    time.sleep(1.2)  # Repeated failed saves must keep a visible pending state.
    assert state()["selectionPending"] and trial.ui_update["phase"] == "queued"
    assert trial.shell.pid == pending_ui
    selection.rmdir()
    backup.replace(selection)
    until(lambda: not state()["selectionPending"], "selection save was not retried after recovery")
    until(lambda: trial.ui_update["phase"] == "applied", "selection recovery did not release queued UI update")
    until(lambda: (ui.chat_state() / "draft.txt").read_text() == "", "draft not cleared")
    assert state()["messages"] == [] and state()["ready"]
    assert json.loads((ui.chat_state() / "selection.json").read_text())["sessionFile"].endswith("/new-session.jsonl")
    assert ui.session_environment()["TABLET_CHAT_FORCE_FRESH"] == "1", "empty new chat would resume the old conversation"
    assert not ui.session_environment()["TABLET_CHAT_RESUME_FILE"]
    metrics = [json.loads(line) for line in Path(os.environ["TABLET_FAKE_RPC_LOG"]).read_text().splitlines()]
    assert len([m for m in metrics if "started" in m]) == 1, "Pi restarted during UI replacement"
    assert sum(m.get("command") == "prompt" for m in metrics) == 2, "unexpected/automatic prompt"
    assert ui.request("home")["view"] == "home"
    until(lambda: not trial.entry_pending, "Home failed after live backdrop asset reloads")
    trial.cover_view("pi")
    until(lambda: not trial.entry_pending, "Pi failed after live backdrop asset reloads")
    recorder.send_signal(signal.SIGINT)
    assert recorder.wait(timeout=15) == 0
    record_log.flush()
    subprocess.run([sys.executable, os.environ["TABLET_FRAME_CHECKER"], "transition-recording.nut", "."], check=True)
    print("Live UI handoff: same Pi process, stream/draft preserved, voice deferral, rollback, pending-input deferral, failed-save retry/verified ack, selection-save recovery and new-chat reset passed")
finally:
    stop.set()
    if thread: thread.join(timeout=10)
    if osk and osk.poll() is None:
        osk.terminate()
        osk.wait(timeout=5)
    if virtual_keyboard and virtual_keyboard.poll() is None:
        virtual_keyboard.terminate()
        virtual_keyboard.wait(timeout=5)
    if recorder and recorder.poll() is None:
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=15)
    if preview and preview.poll() is None:
        preview.terminate()
        preview.wait(timeout=5)
    record_log.close()
    ui.chat_state().chmod(0o700)
    server.close()
    # The OSK/keyfile settings/virtual input were private test fixtures only.
    # No host audio/settings/input were touched; cleanup our fake agent/UI.
    trial.recording = trial.voice_pending = trial.voice_guard = False
    trial.cleanup()
    log.close()
