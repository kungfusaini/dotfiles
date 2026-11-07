import Quickshell
import Quickshell.Io
import QtQuick

// Supervised independently of the visible scene. Reloading/replacing a screen
// never closes this process or Pi's stdin. No HTTP server or detached child.
ShellRoot {
    id: agent
    property bool piStarted: Quickshell.env("TABLET_DEFER_PI") !== "1"
    property int revision: 0
    property int editorVersion: 0
    property int editorAck: 0
    property string editorText: ""
    property int rejectedVersion: 0
    property int rejectedAck: 0
    property string rejectedText: ""
    property bool draftReadable: false
    property bool selectionReadable: false
    property bool selectionPending: false
    property string selectedPath: ""
    readonly property string selectionError: "Chat selection is not saved yet; keep this chat open until storage recovers."
    readonly property string storageError: "Draft is not safely saved yet; keep this chat open and resolve storage before updating."
    FileView { id: requestFile; blockAllReads: true; printErrors: false }
    FileView {
        id: draft
        path: Quickshell.env("TABLET_CHAT_SESSIONS") + "/draft.txt"
        blockWrites: true
        blockAllReads: true
        printErrors: false
        onLoaded: agent.draftReadable = true
        onLoadFailed: agent.draftReadable = false
        onSaveFailed: rpc.error = "New chat started, but the saved draft could not be cleared"
    }
    FileView {
        id: selection
        path: Quickshell.env("TABLET_CHAT_SESSIONS") + "/selection.json"
        blockWrites: true
        blockAllReads: true
        printErrors: false
        onLoaded: agent.selectionReadable = true
        onLoadFailed: agent.selectionReadable = false
        onSaveFailed: agent.selectionPending = true
    }
    function selectSession(path) {
        selectedPath = path
        selectionPending = true
        persistSelection()
    }
    function persistSelection() {
        const desired = JSON.stringify({sessionFile: selectedPath})
        selectionReadable = false
        selection.reload()
        const previous = selection.text()
        if (!selectionReadable || previous !== desired) selection.setText(desired)
        // Confirm disk rather than trusting a failed-write cache or signal.
        selectionReadable = false
        selection.reload()
        const actual = selection.text()
        selectionPending = !selectionReadable || actual !== desired
    }
    Timer { interval: 1000; running: agent.selectionPending; repeat: true; onTriggered: agent.persistSelection() }
    PiRpc {
        id: rpc
        active: agent.piStarted
        onMessagesChanged: agent.revision++
        onSessionSelected: path => agent.selectSession(path)
        onClosed: Qt.quit()
        onEditorRequested: text => { agent.editorText = text; agent.editorVersion++ }
        onPromptRejected: text => { agent.rejectedText = text; agent.rejectedVersion++ }
        onNewChatDone: {
            // The frontend pauses draft writes before requesting a reset.
            // An extension-cancelled/failed reset never reaches this signal.
            // Pi deliberately doesn't persist empty sessions. Remember the
            // chosen path so reopening an empty New chat never resumes the old
            // conversation. Startup resumes it once Pi creates the file.
            agent.selectSession(rpc.selectedSession)
            draft.reload()
            draft.text() // Refresh FileView's cache before clearing.
            draft.setText("")
        }
    }
    IpcHandler {
        target: "tabletAgent"
        function launchPi(): void { agent.piStarted = true }
        function snapshot(): string {
            return JSON.stringify({piStarted: agent.piStarted, revision: agent.revision, ready: rpc.ready, busy: rpc.busy,
                activity: rpc.activity, error: agent.selectionPending ? agent.selectionError : rpc.error,
                selectionPending: agent.selectionPending, messages: rpc.messages, question: rpc.question,
                awaitingPrompt: rpc.awaitingPrompt, pendingText: rpc.pendingText,
                resetting: rpc.resetting, generation: rpc.generation,
                editorVersion: agent.editorVersion, editorAck: agent.editorAck, editorText: agent.editorText,
                rejectedVersion: agent.rejectedVersion, rejectedAck: agent.rejectedAck, rejectedText: agent.rejectedText})
        }
        function shutdown(): void { rpc.shutdown() }
        function dispatch(path: string): string {
            // Contents travel through a 0600 file, not ps-visible command args.
            const prefix = Quickshell.env("XDG_RUNTIME_DIR") + "/tablet-chat/requests/"
            if (!path.startsWith(prefix) || path.slice(prefix.length).includes("/"))
                return JSON.stringify({accepted: false, error: "Invalid request path"})
            requestFile.path = path
            requestFile.reload()
            const record = JSON.parse(requestFile.text())
            requestFile.path = ""
            let accepted = true
            if (record.action === "prompt") accepted = rpc.prompt(record.text)
            else if (record.action === "new_chat") accepted = rpc.newChat()
            else if (record.action === "abort") accepted = rpc.command({id: "stop", type: "abort"})
            else if (record.action === "answer") {
                accepted = !!rpc.question && rpc.question.id === record.id
                if (accepted) rpc.answer(record.answer)
            } else if (record.action === "ack_editor" || record.action === "ack_rejected") {
                agent.draftReadable = false
                draft.reload()
                const text = draft.text()
                // Verify actual disk, not FileView's post-failure write cache.
                // This digest is an equality check, not an authentication token.
                accepted = agent.draftReadable && Qt.md5(text) === record.digest && Number.isInteger(record.version)
                if (accepted) {
                    if (record.action === "ack_editor") agent.editorAck = Math.max(agent.editorAck, Math.min(record.version, agent.editorVersion))
                    else agent.rejectedAck = Math.max(agent.rejectedAck, Math.min(record.version, agent.rejectedVersion))
                    if (rpc.error === agent.storageError) rpc.error = ""
                } else rpc.error = agent.storageError
            }
            else if (record.action === "shutdown") rpc.shutdown()
            else accepted = false
            return JSON.stringify({accepted: accepted, error: accepted ? "" : "Pi is not ready for that action"})
        }
    }
}
