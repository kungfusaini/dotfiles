import QtQuick
import Quickshell
import Quickshell.Io

// Supported Pi JSONL subprocess interface. No terminal, shell, HTTP or credentials IPC.
Item {
    id: rpc
    visible: false
    property bool active: false
    property bool ready: false
    property bool busy: false
    property string error: ""
    property string activity: ""
    property var messages: []
    property var questions: []
    property var question: questions.length ? questions[0] : null
    property bool closing: false
    property int serial: 0
    property string promptId: ""
    property string pendingText: ""
    property bool awaitingPrompt: false
    property bool observedRun: false
    property string promptStateId: ""
    property var blocks: ({})
    property bool resetting: false
    property int generation: 0
    property string resetId: ""
    property string resetStep: ""
    property string selectedSession: ""
    signal newChatDone()
    signal sessionSelected(string path)
    signal closed()
    signal editorRequested(string text)
    signal promptRejected(string text)

    function command(record) {
        if (!child.running) return false
        child.write(JSON.stringify(record) + "\n")
        return true
    }
    function textOf(message) {
        if (typeof message.content === "string") return message.content
        return (message.content || []).filter(b => b.type === "text").map(b => b.text || "").join("\n")
    }
    function append(role, text) {
        messages = messages.concat([{role: role, text: text}])
    }
    function updateAssistant(text) {
        const copy = messages.slice()
        if (!copy.length || copy[copy.length - 1].role !== "assistant") copy.push({role: "assistant", text: text})
        else copy[copy.length - 1] = {role: "assistant", text: text}
        messages = copy
    }
    function prompt(text) {
        if (!ready || busy || resetting || !text.trim() || question) return false
        error = ""
        busy = true
        observedRun = false
        pendingText = text
        awaitingPrompt = true
        promptId = "prompt-" + (++serial)
        if (!command({id: promptId, type: "prompt", message: text})) {
            busy = false
            awaitingPrompt = false
            return false
        }
        return true
    }
    function newChat() {
        if (!ready || resetting || question || awaitingPrompt) return false
        resetting = true
        error = ""
        resetId = "new-chat-" + (++serial)
        resetStep = "clear_queue"
        command({id: resetId, type: resetStep})
        return true
    }
    function answer(value) {
        if (!question) return
        command(Object.assign({type: "extension_ui_response", id: question.id}, value))
        questions = questions.slice(1)
    }
    function shutdown() {
        if (!child.running) { closed(); return }
        closing = true
        // EOF asks Pi to dispose its runtime; stop is explicit, never a Home action.
        child.stdinEnabled = false
        shutdownDeadline.start()
    }
    function accept(record) {
        if (record.type === "response") {
            if (record.id === "startup-state" && record.success) {
                selectedSession = record.data.sessionFile || ""
                sessionSelected(selectedSession)
            }
            if (resetting && record.id === resetId) {
                if (!record.success || (record.data && record.data.cancelled)) {
                    resetting = false
                    error = record.error || "New chat was cancelled; your conversation and draft remain."
                    return
                }
                if (resetStep === "clear_queue") resetStep = "abort"
                else if (resetStep === "abort") resetStep = "new_session"
                else if (resetStep === "new_session") resetStep = "get_state"
                else if (resetStep === "get_state") {
                    selectedSession = record.data.sessionFile || ""
                    resetStep = "get_messages"
                }
                else {
                    messages = record.data.messages.filter(m => m.role === "user" || m.role === "assistant")
                        .map(m => ({role: m.role, text: textOf(m)})).filter(m => m.text)
                    blocks = ({})
                    activity = ""
                    pendingText = ""
                    busy = false
                    resetting = false
                    generation++
                    newChatDone()
                    command({id: "name-" + resetId, type: "set_session_name", name: "Tablet chat"})
                    return
                }
                // Each step is acknowledged before the next. In particular,
                // abort waits for idle; an extension may cancel new_session.
                resetId = "new-chat-" + (++serial)
                command({id: resetId, type: resetStep})
                return
            }
            if (record.id === promptId) {
                awaitingPrompt = false
                if (record.success) {
                    // An extension may handle a prompt without starting an
                    // agent run, so no agent_settled event will follow.
                    promptStateId = "prompt-state-" + promptId
                    command({id: promptStateId, type: "get_state"})
                }
            }
            if (record.id === promptStateId && record.success && !observedRun) {
                const state = record.data
                if (!state.isStreaming && !state.isCompacting && !state.pendingMessageCount) busy = false
            }
            if (!record.success) {
                error = record.error || "Pi rejected the request"
                if (record.id === promptId) { busy = false; promptRejected(pendingText) }
            } else if (record.command === "get_messages") {
                messages = record.data.messages.filter(m => m.role === "user" || m.role === "assistant")
                    .map(m => ({role: m.role, text: textOf(m)})).filter(m => m.text)
                ready = true
            }
        } else if (record.type === "agent_start") { observedRun = true; busy = true }
        else if (record.type === "agent_settled") { busy = false; activity = "" }
        else if (record.type === "message_start") {
            const m = record.message
            if (m.role === "user") append("user", textOf(m))
            else if (m.role === "assistant") { blocks = ({}); append("assistant", "") }
        } else if (record.type === "message_update") {
            const e = record.assistantMessageEvent
            if (e.type === "text_delta" || e.type === "text_end") {
                blocks[e.contentIndex] = e.type === "text_end" ? e.content : (blocks[e.contentIndex] || "") + e.delta
                updateAssistant(Object.keys(blocks).sort((a,b) => Number(a)-Number(b)).map(k => blocks[k]).join("\n"))
            }
        } else if (record.type === "message_end" && record.message.role === "assistant") {
            const m = record.message
            updateAssistant(textOf(m))
            if (m.errorMessage) error = m.errorMessage
        } else if (record.type === "tool_execution_start") activity = "Using " + record.toolName + "…"
        else if (record.type === "tool_execution_end") activity = record.isError ? "Tool reported an error" : "Working…"
        else if (record.type === "extension_ui_request") {
            if (["confirm", "select", "input", "editor"].includes(record.method)) {
                const q = Object.assign({}, record)
                q.deadline = record.timeout ? Date.now() + record.timeout : 0
                questions = questions.concat([q])
            } else if (record.method === "set_editor_text") editorRequested(record.text || "")
            else if (record.method === "notify") error = record.message || ""
        } else if (record.type === "extension_error") error = record.error || "Pi extension error"
    }
    Process {
        id: child
        running: rpc.active
        stdinEnabled: true
        workingDirectory: Quickshell.env("TABLET_CHAT_CWD")
        environment: ({KITTY_PID: null, KITTY_WINDOW_ID: null, PI_SESSION_ID: null, PI_SESSION_FILE: null, PROJECT_OBJECT_TERMINAL: null})
        command: [Quickshell.env("TABLET_CHAT_PI"), "--mode", "rpc", "--offline"]
            .concat(Quickshell.env("TABLET_CHAT_RESUME_FILE") ? ["--session", Quickshell.env("TABLET_CHAT_RESUME_FILE")]
                    : Quickshell.env("TABLET_CHAT_FORCE_FRESH") === "1" ? [] : ["--continue"])
            .concat(["--session-dir", Quickshell.env("TABLET_CHAT_SESSIONS"),
                  "--append-system-prompt", Quickshell.env("TABLET_CHAT_PROMPT"), "--name", "Tablet chat",
                  "--provider", Quickshell.env("TABLET_CHAT_PROVIDER"), "--model", Quickshell.env("TABLET_CHAT_MODEL")])
        onStarted: {
            rpc.command({id: "startup-state", type: "get_state"})
            rpc.command({id: "history", type: "get_messages"})
        }
        stdout: SplitParser {
            splitMarker: "\n"
            onRead: data => {
                try { rpc.accept(JSON.parse(data)) }
                catch (_) { rpc.error = "Invalid response from Pi" }
            }
        }
        // Drain diagnostics without treating harmless startup warnings as
        // failures or leaking arbitrary stderr into logs/UI. Protocol errors
        // and process exits have their own visible error paths.
        stderr: SplitParser { onRead: data => {} }
        onExited: (code, status) => {
            rpc.ready = false
            rpc.busy = false
            rpc.resetting = false
            rpc.questions = []
            if (rpc.awaitingPrompt) rpc.promptRejected(rpc.pendingText)
            rpc.awaitingPrompt = false
            if (rpc.closing) rpc.closed()
            else rpc.error = "Pi stopped. Close and reopen the tablet chat to reconnect."
        }
    }
    Timer {
        interval: rpc.question && rpc.question.deadline ? Math.max(1, rpc.question.deadline - Date.now()) : 1
        running: !!(rpc.question && rpc.question.deadline)
        onTriggered: rpc.answer({cancelled: true})
    }
    Timer {
        id: shutdownDeadline
        interval: 5000
        onTriggered: { if (child.running) child.running = false }
    }
}
