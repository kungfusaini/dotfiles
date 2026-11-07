import Quickshell
import QtQuick
import "." as App

ShellRoot {
    id: root
    property int phase: 0
    property int proxyEditors: 0
    property int proxyRejections: 0
    property int persistAttempts: 0
    function check(condition, message) {
        if (!condition) { console.error(message); Qt.exit(1) }
    }
    App.PiClient {
        id: proxy
        active: false
        persistDraft: () => { root.persistAttempts++; return "" }
        onEditorRequested: root.proxyEditors++
        onPromptRejected: root.proxyRejections++
    }
    Component.onCompleted: {
        const state = {revision: 1, ready: true, busy: false, activity: "", error: "",
            question: {id: "pending", method: "input", prefill: "Keep the answer"}, messages: [],
            awaitingPrompt: false, pendingText: "", resetting: false, generation: 0,
            editorVersion: 0, editorAck: 0, rejectedVersion: 0, rejectedAck: 0}
        proxy.accept(state)
        const question = proxy.question
        const messages = proxy.messages
        proxy.accept(JSON.parse(JSON.stringify(state)))
        root.check(proxy.question === question, "polling must not reset a pending dialog's answer/focus")
        root.check(proxy.messages === messages, "unchanged history must not reset scrolling")
        state.editorVersion = 1; state.editorText = "Recover editor"
        state.rejectedVersion = 1; state.rejectedText = "Recover rejected prompt"
        proxy.accept(JSON.parse(JSON.stringify(state)))
        proxy.accept(JSON.parse(JSON.stringify(state)))
        root.check(root.proxyEditors === 1 && root.proxyRejections === 1, "failed save retry must not duplicate insertion or replace later edits")
        root.check(root.persistAttempts >= 4 && !proxy.pendingWrites, "failed persistence must retry without acknowledging")
    }
    App.PiRpc {
        id: client
        active: true
        onEditorRequested: text => {
            root.check(text === "Unsent draft", "editor text did not arrive")
            root.check(!busy, "settled state lost")
            root.check(prompt("/handled"), "extension prompt not accepted")
            root.phase = 4
        }
        onClosed: Qt.quit()
    }
    Timer {
        interval: 20; running: true; repeat: true
        onTriggered: {
            if (root.phase === 0 && client.ready) {
                root.check(client.messages[0].text === "Tablet chat ready.", "history not restored")
                root.check(client.prompt("Hello tablet"), "prompt rejected")
                root.phase = 1
            } else if (root.phase === 1 && client.messages.length === 3 && client.messages[2].text === "Hello\u2028\n tablet") {
                root.check(client.busy, "agent_end is not settled")
                client.command({id: "state", type: "get_state"})
                root.phase = 2
            } else if (root.phase === 2 && client.question) {
                root.check(client.question.id === "confirm-1", "dialog correlation lost")
                client.answer({confirmed: false})
                root.phase = 3
            } else if (root.phase === 4 && !client.busy) {
                root.check(client.ready, "extension-handled prompt left chat unusable")
                root.check(client.newChat(), "new chat was not accepted")
                root.phase = 5
            } else if (root.phase === 5 && !client.resetting) {
                root.check(client.generation === 0 && client.messages.length === 3, "cancelled new session lost history")
                root.check(client.error.indexOf("cancelled") >= 0, "cancelled new session was not reported")
                root.check(client.newChat(), "second new chat was not accepted")
                root.phase = 6
            } else if (root.phase === 6 && !client.resetting) {
                root.check(client.generation === 1 && client.messages.length === 0, "new session did not clear history")
                root.check(client.ready && !client.busy, "new session not ready")
                root.phase = 7
                client.shutdown()
            }
        }
    }
    Timer { interval: 5000; running: true; onTriggered: { console.error("RPC protocol test timed out"); Qt.exit(1) } }
}
