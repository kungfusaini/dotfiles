"""Offline protocol fixture; never invokes a model, tools or authentication."""
import json
import os
import sys
import time
from pathlib import Path


def emit(record):
    print(json.dumps(record, ensure_ascii=False), flush=True)


prompts = 0
startup_question = False
new_sessions = 0
history = [{"role": "assistant", "content": [{"type": "text", "text": "Tablet chat ready."}]}]
live = os.environ.get("TABLET_RPC_LIVE_TEST") == "1"
streaming = False
log = os.environ.get("TABLET_FAKE_RPC_LOG")
if log:
    with open(log, "a") as output: output.write(json.dumps({"started": os.getpid()}) + "\n")
for line in sys.stdin.buffer:
    request = json.loads(line)
    kind = request["type"]
    if log:
        with open(log, "a") as output: output.write(json.dumps({"command": kind}) + "\n")
    if kind == "get_messages":
        gate = os.environ.get("TABLET_RPC_HISTORY_GATE")
        while gate and not Path(gate).exists():
            question_gate = os.environ.get("TABLET_RPC_STARTUP_QUESTION_GATE")
            if question_gate and Path(question_gate).exists() and not startup_question:
                emit({"type": "extension_ui_request", "id": "startup-confirm", "method": "confirm", "title": "Startup question", "message": "Offline fixture only"})
                startup_question = True
            time.sleep(.01)
        emit({"id": request.get("id"), "type": "response", "command": kind, "success": True,
              "data": {"messages": history}})
    elif kind == "prompt":
        if request["message"] == "/handled":
            emit({"id": request["id"], "type": "response", "command": kind, "success": True})
            continue
        if live and request["message"] == "/question":
            emit({"id": request["id"], "type": "response", "command": kind, "success": True})
            emit({"type": "extension_ui_request", "id": "confirm-1", "method": "confirm", "title": "Test approval", "message": "Not a real operation"})
            continue
        prompts += 1
        if prompts > 1 and not live:
            sys.exit("The editor update must not automatically submit")
        emit({"id": request["id"], "type": "response", "command": kind, "success": True})
        emit({"type": "agent_start"})
        emit({"type": "message_start", "message": {"role": "user", "content": request["message"]}})
        emit({"type": "message_start", "message": {"role": "assistant", "content": []}})
        if live and request["message"] == "stream":
            streaming = True
            emit({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "Stream before refresh"}})
            continue
        for index, text in [(0, "Hello\u2028"), (1, " tablet")]:
            emit({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "contentIndex": index, "delta": text}})
        emit({"type": "message_end", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Hello\u2028"}, {"type": "text", "text": " tablet"}]}})
        emit({"type": "agent_end", "messages": []})
    elif kind == "get_state":
        if request.get("id", "").startswith("new-chat-") or request.get("id") == "startup-state":
            filename = "/initial-session.jsonl" if request.get("id") == "startup-state" else "/new-session.jsonl"
            emit({"id": request["id"], "type": "response", "command": kind, "success": True,
                  "data": {"sessionFile": os.environ["TABLET_CHAT_SESSIONS"] + filename}})
            continue
        if request.get("id", "").startswith("prompt-state-"):
            emit({"id": request["id"], "type": "response", "command": kind, "success": True,
                  "data": {"isStreaming": streaming, "isCompacting": False, "pendingMessageCount": 0}})
            continue
        emit({"type": "agent_settled"})
        emit({"type": "extension_ui_request", "id": "confirm-1", "method": "confirm", "title": "Test approval", "message": "Not a real operation"})
    elif kind == "extension_ui_response":
        if request["id"] == "startup-confirm":
            assert request.get("confirmed") is False
            continue
        assert request.get("confirmed") is False and request["id"] == "confirm-1"
        emit({"type": "extension_ui_request", "id": "editor", "method": "set_editor_text", "text": "Unsent draft"})
    elif kind == "abort":
        if streaming:
            emit({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "Stream stopped after refresh"}]}})
        streaming = False
        emit({"type": "agent_settled"})
        emit({"id": request.get("id"), "type": "response", "command": kind, "success": True})
    elif kind == "new_session":
        new_sessions += 1
        cancelled = os.environ.get("TABLET_FAKE_CANCEL_NEW") == "1" and new_sessions == 1
        if not cancelled: history = []
        emit({"id": request["id"], "type": "response", "command": kind, "success": True, "data": {"cancelled": cancelled}})
    elif kind in ("clear_queue", "set_session_name"):
        emit({"id": request["id"], "type": "response", "command": kind, "success": True})
