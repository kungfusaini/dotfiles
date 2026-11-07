import QtQuick
import Quickshell
import Quickshell.Io

// Presentation-only client. Commands use stdin/private files; never put drafts
// in argv. The independently supervised agent retains all streaming/RPC state.
Item {
    id: client
    visible: false
    property bool active: false
    property bool deliveryEnabled: true
    // Returns a digest only after synchronously persisting the current draft.
    property var persistDraft: null
    property bool connected: false
    property bool ready: false
    property bool busy: false
    property bool resetting: false
    property bool selectionPending: false
    property bool resetAcknowledged: false
    property bool awaitingPrompt: false
    property string pendingText: ""
    property string activity: ""
    property string error: ""
    property var messages: []
    property var question: null
    property int revision: -1
    property int generation: -1
    property int editorDelivered: 0
    property int rejectedDelivered: 0
    property var outgoing: []
    property var sending: null
    readonly property bool pendingWrites: sender.running || outgoing.length > 0
    signal closed()
    signal editorRequested(string text)
    signal promptRejected(string text)
    signal newChatDone()

    function enqueue(record) {
        outgoing = outgoing.concat([record])
        pump()
    }
    function pump() {
        if (sender.running || !outgoing.length) return
        sending = outgoing[0]
        outgoing = outgoing.slice(1)
        sender.stdinEnabled = true
        sender.running = true
    }
    function prompt(text) {
        if (!ready || busy || resetting || question || !text.trim()) return false
        busy = true
        awaitingPrompt = true
        pendingText = text
        enqueue({action: "prompt", text: text})
        return true
    }
    function newChat() {
        if (!ready || resetting || pendingWrites || awaitingPrompt || question) return false
        resetting = true
        resetAcknowledged = false
        enqueue({action: "new_chat"})
        return true
    }
    function command(record) { if (record.type === "abort") enqueue({action: "abort"}) }
    function answer(value) { if (question) enqueue({action: "answer", id: question.id, answer: value}) }
    function shutdown() { closed() } // Supervisor owns orderly shutdown and fallback.
    function persistAndAck(action, version) {
        if (!persistDraft || pendingWrites) return
        const digest = persistDraft()
        if (digest) enqueue({action: action, version: version, digest: digest})
    }
    function accept(state) {
        connected = true
        ready = state.ready
        selectionPending = !!state.selectionPending
        const promptInFlight = (sender.running && sending && sending.action === "prompt") || outgoing.some(r => r.action === "prompt")
        busy = state.busy || promptInFlight
        activity = state.activity
        error = state.error
        // Preserve object identity: replacing an unchanged question would blur
        // its text input and reset the user's answer on every polling tick.
        if (JSON.stringify(question) !== JSON.stringify(state.question)) question = state.question
        awaitingPrompt = state.awaitingPrompt || promptInFlight
        if (!promptInFlight) pendingText = state.pendingText
        if (revision !== state.revision) { revision = state.revision; messages = state.messages }
        if (generation >= 0 && generation !== state.generation) {
            resetting = false
            newChatDone()
        } else if (resetting && resetAcknowledged && !state.resetting) resetting = false
        generation = state.generation
        if (state.resetting) resetting = true
        if (!deliveryEnabled || resetting) return
        if (state.editorVersion > state.editorAck) {
            if (state.editorVersion > editorDelivered) {
                editorDelivered = state.editorVersion
                editorRequested(state.editorText)
            }
            // Retry saving, not insertion: repeated snapshots must not replace
            // later edits or duplicate a rejected prompt after a failed save.
            persistAndAck("ack_editor", state.editorVersion)
        }
        if (state.rejectedVersion > state.rejectedAck) {
            if (state.rejectedVersion > rejectedDelivered) {
                rejectedDelivered = state.rejectedVersion
                promptRejected(state.rejectedText)
            }
            persistAndAck("ack_rejected", state.rejectedVersion)
        }
    }
    Process {
        id: poll
        command: [Quickshell.env("TABLET_ITERATE_BIN"), "agent-state"]
        stdout: StdioCollector {
            onStreamFinished: {
                try { client.accept(JSON.parse(text)) }
                catch (_) { if (client.connected) client.error = "Could not read Pi state" }
            }
        }
        stderr: SplitParser { onRead: data => {} }
    }
    Timer {
        interval: 200; repeat: true; running: client.active; triggeredOnStart: true
        onTriggered: { if (!poll.running) poll.running = true }
    }
    Timer {
        interval: 10000; running: client.active && !client.connected
        onTriggered: client.error = "Pi backend is unavailable. Close and reopen the chat."
    }
    Process {
        id: sender
        command: [Quickshell.env("TABLET_ITERATE_BIN"), "agent-command"]
        onStarted: { write(JSON.stringify(client.sending) + "\n"); stdinEnabled = false }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text)
                    if (!result.accepted) throw new Error(result.error || "Pi rejected the action")
                    if (client.sending.action === "new_chat") client.resetAcknowledged = true
                } catch (_) {
                    client.error = "Pi could not accept the action"
                    if (client.sending.action === "prompt") client.promptRejected(client.sending.text)
                    if (client.sending.action === "new_chat") client.resetting = false
                }
            }
        }
        stderr: SplitParser { onRead: data => {} }
        onExited: Qt.callLater(client.pump)
    }
}
