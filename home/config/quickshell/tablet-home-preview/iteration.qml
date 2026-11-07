import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ShellRoot {
    id: root
    property var state: ({ running: false, visible: false, view: "home", recording: false, transcribing: false, uncertain: false, ready: false, error: "" })
    readonly property bool nativeChat: Quickshell.env("TABLET_NATIVE_CHAT") === "1"
    property bool connected: false
    property string error: ""
    property bool draftRestored: false
    property bool draftReadable: false
    property bool draftSaved: false
    property bool awaitingActivation: !!Quickshell.env("TABLET_UI_TOKEN")
    property bool updating: awaitingActivation
    property bool pendingInsert: false
    property bool closePending: false
    property var panelAcknowledged: undefined
    property string panelError: ""
    readonly property bool panelWanted: root.state.view === "pi" && root.state.visible && chatWindow.backingWindowVisible
        && !piNavigator.navigating && nativeChatView.inputPanelActive
    Process {
        id: panelRunner
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const response = JSON.parse(text)
                    if (response.accepted) { root.panelAcknowledged = response.visible; root.panelError = "" }
                } catch (_) { root.panelError = "Could not confirm keyboard visibility" }
            }
        }
        stderr: StdioCollector { onStreamFinished: { if (text.trim()) root.panelError = text.trim() } }
    }
    Timer {
        interval: 150; repeat: true
        running: root.nativeChat && root.state.running && root.state.visible && !root.updating
            && (root.state.view !== "external" || externalView.overview)
        onTriggered: {
            if (!panelRunner.running && root.panelAcknowledged !== root.panelWanted) {
                panelRunner.command = [Quickshell.env("TABLET_ITERATE_BIN"), "input-panel",
                    JSON.stringify({visible: root.panelWanted, frontend: Quickshell.processId})]
                panelRunner.running = true
            }
        }
    }
    readonly property bool chatContentReady: nativeAgent.connected && root.draftRestored
        && !!(nativeAgent.ready || nativeAgent.question || nativeAgent.error)
    property bool chatAdmitted: false
    AppHistory { id: appHistory; apps: root.apps }
    readonly property bool voicePending: !!(state.recording || state.transcribing || state.uncertain || state.ready)
    function appSummary(app) {
        if (app.kind === "window") return "Native application window"
        if (app.id !== "tablet-improve") return "Preview · no application launched"
        const last = nativeAgent.messages.length ? nativeAgent.messages[nativeAgent.messages.length - 1].text : "Your Pi conversation"
        return String(last || "Your Pi conversation").slice(0, 300) + (nativeChatView.draft ? "\n\nDraft: " + nativeChatView.draft.slice(0, 120) : "")
    }
    property string pendingNavigation: Quickshell.env("TABLET_UI_NAVIGATION") || ""
    property bool dismissPiPending: false
    function goHome(appLabel, dismissPi) {
        if (voicePending || nativeAgent.question) { error = "Finish or cancel the pending input before going Home"; return }
        if (root.updating || dismissPiPending || actionRunner.running || appHistory.capturing || !saveDraft(true)) return
        nativeChatView.blurInput()
        appHistory.capture("tablet-improve", nativeChatView, ok => {
            if (!ok) { error = "Could not retain the app preview; please try again"; return }
            if (voicePending || nativeAgent.question || root.updating || actionRunner.running || !saveDraft(true)) return
            const destination = root.apps.find(app => app.label === appLabel)
            if (destination && destination.kind !== "window") homeView.activeApp = appLabel
            else homeView.showHome()
            dismissPiPending = !!dismissPi
            if (destination && destination.kind === "window") run("app-open", destination.id)
            else run("home")
        })
    }
    function navigationSnapshot() {
        return JSON.stringify({opened: appHistory.opened, mock: homeView.activeApp,
            overview: root.state.view === "external" ? externalView.overview : root.state.view === "pi" ? piNavigator.overview : homeView.switcherOpen})
    }
    function restoreNavigation(text) {
        if (!text) return
        try {
            const navigation = JSON.parse(text)
            if (apps.some(app => app.id !== "tablet-improve" && app.label === navigation.mock)) homeView.activeApp = navigation.mock
            appHistory.restore(navigation.opened)
            if (state.view === "pi") piNavigator.overview = !!navigation.overview
            else homeView.switcherOpen = !!navigation.overview
        } catch (_) { error = "Could not restore app navigation" }
    }
    onChatContentReadyChanged: { if (chatContentReady) chatAdmitted = true }
    IpcHandler {
        target: "tabletUi"
        function status(): string {
            return JSON.stringify({view: root.state.view, updating: root.updating, connected: nativeAgent.connected,
                draftRestored: root.draftRestored, draftSaved: root.draftSaved,
                mapped: root.state.view === "external" ? externalView.backingWindowVisible : root.nativeChat && root.state.view === "pi" ? chatWindow.backingWindowVisible : homeWindow.backingWindowVisible,
                contentReady: root.chatContentReady, externalReady: externalView.contentReady,
                rendered: root.state.view === "external" ? externalView.rendered : root.nativeChat && root.state.view === "pi" ? chatFrames.rendered : root.state.view === "home" ? homeFrames.rendered : backdropFrames.rendered})
        }
        function persistDraft(): string {
            return JSON.stringify({saved: root.saveClosingDraft()})
        }
        function prepare(): string {
            if (root.state.view === "external" || externalView.navigationBusy || !root.draftRestored || actionRunner.running || panelRunner.running || root.pendingInsert || nativeAgent.pendingWrites || nativeAgent.resetting || nativeAgent.question || dismissPiPending || appHistory.capturing || piNavigator.dragging || homeView.navigationBusy)
                return JSON.stringify({ready: false})
            const focused = nativeChatView.inputActive
            const cursor = nativeChatView.cursorPosition
            const navigation = root.navigationSnapshot()
            root.saveDraft(true)
            draftSave.stop()
            root.updating = true
            nativeChatView.blurInput()
            return JSON.stringify({ready: true, focused: focused, cursor: cursor, draft: nativeChatView.draft, navigation: navigation})
        }
        function activate(focused: bool, cursor: int): void {
            root.awaitingActivation = false
            root.updating = false
            nativeChatView.cursorPosition = Math.min(cursor, nativeChatView.draft.length)
            if (focused && root.state.visible && root.state.view === "pi" && !nativeAgent.question && !piNavigator.overview) nativeChatView.focusInput()
        }
    }
    Process {
        id: readyRunner
        command: [Quickshell.env("TABLET_ITERATE_BIN"), "ui-ready", Quickshell.env("TABLET_UI_TOKEN")]
        stdout: SplitParser { onRead: data => {} }
        stderr: SplitParser { onRead: data => {} }
    }
    Timer {
        interval: 100; repeat: true
        running: root.awaitingActivation && root.updating
        onTriggered: {
            const rendered = root.state.view === "pi" ? chatFrames.rendered : homeFrames.rendered
            if (nativeAgent.connected && root.draftRestored && rendered && !readyRunner.running) readyRunner.running = true
        }
    }
    FileView {
        id: draftFile
        path: root.nativeChat ? Quickshell.env("TABLET_CHAT_SESSIONS") + "/draft.txt" : ""
        blockAllReads: true
        printErrors: false
        onLoaded: root.draftReadable = true
        onLoadFailed: { root.draftReadable = false; root.error = "Could not read the saved chat draft" }
        onSaved: root.draftSaved = true
        onSaveFailed: { root.draftSaved = false; root.error = "Could not save the chat draft" }
    }
    Component.onCompleted: {
        loadApps()
        if (nativeChat) {
            const text = draftFile.text()
            if (draftFile.loaded && draftReadable) { nativeChatView.draft = text; draftRestored = true; draftSaved = true }
            else root.error = "Could not restore the saved draft; it will not be overwritten"
        }
    }
    function saveDraft(blocking) {
        if (!nativeChat || !draftRestored) return false
        let alreadySaved = false
        if (blocking) {
            draftSave.stop()
            // A failed FileView write still changes its cache. Reload actual
            // disk contents so retries cannot skip an identical cached value.
            root.draftReadable = false
            draftFile.reload()
            const disk = draftFile.text()
            alreadySaved = root.draftReadable && disk === nativeChatView.draft
        }
        root.draftSaved = alreadySaved
        draftFile.blockWrites = blocking
        draftFile.setText(nativeChatView.draft)
        draftFile.blockWrites = false
        if (blocking && root.draftSaved && ["Could not save the chat draft", "Could not read the saved chat draft"].includes(root.error)) root.error = ""
        return blocking && root.draftSaved
    }
    function saveClosingDraft() {
        if (nativeAgent.awaitingPrompt && !nativeChatView.draft) nativeChatView.draft = nativeAgent.pendingText
        return saveDraft(true)
    }
    function closeNative() {
        if (!saveClosingDraft()) return
        nativeAgent.shutdown()
    }
    Timer { id: draftSave; interval: 250; onTriggered: root.saveDraft(false) }
    readonly property var targetScreen: Quickshell.screens.find(s => s.name === "eDP-1") ?? null
    property var apps: []
    FileView {
        id: appRegistry
        path: Quickshell.env("TABLET_APPS_REGISTRY") || Qt.resolvedUrl("apps.json").toString().replace(/^file:\/\//, "")
        blockAllReads: true
        onLoaded: root.loadApps()
    }
    function loadApps() {
        try { apps = JSON.parse(appRegistry.text()).map(app => Object.assign({}, app, {kind: !root.nativeChat && app.kind === "window" ? "preview" : app.kind, icon: Quickshell.iconPath(app.icon, true)})) }
        catch (_) { error = "Could not load the tablet app registry" }
    }
    function openApp(id, label) {
        const app = apps.find(app => app.id === id)
        if (!app || voicePending || root.updating) return
        if (nativeAgent.question && app.kind !== "native") { error = "Return to Pi to answer the pending question"; return }
        if (app.kind === "window") { homeView.showHome(); run("app-open", id) }
        else if (app.kind === "native") run("pi")
        else { homeView.activeApp = label; run("home") }
    }
    function closeApp(id) {
        const app = apps.find(app => app.id === id)
        if (app && app.kind === "window") run("app-close", id)
        else appHistory.close(id)
    }
    function run(action, app) {
        if (!actionRunner.running) {
            error = ""
            if (action === "insert") pendingInsert = true
            actionRunner.command = [Quickshell.env("TABLET_ITERATE_BIN"), action]
            if (app) actionRunner.command = actionRunner.command.concat([JSON.stringify({app: app, frontend: Quickshell.processId})])
            actionRunner.running = true
        }
    }
    Process {
        id: statusRunner
        command: [Quickshell.env("TABLET_ITERATE_BIN"), "status"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const previousView = root.state.view
                    const previousWindows = root.state.apps ? root.state.apps.windows || {} : {}
                    const nextState = Object.assign({visible: false, recording: false, transcribing: false, uncertain: false, ready: false, error: ""}, JSON.parse(text))
                    if (previousView !== nextState.view || root.state.visible !== nextState.visible) {
                        nativeChatView.blurInput()
                        // Native apps can change OSK visibility autonomously.
                        // A former Pi/Home acknowledgement is no longer evidence.
                        root.panelAcknowledged = undefined
                    }
                    root.state = nextState
                    if (root.state.running) {
                        root.connected = true
                        const windows = root.state.apps ? root.state.apps.windows || {} : {}
                        for (const id of Object.keys(previousWindows)) if (!windows[id]) appHistory.close(id)
                        if (root.state.view === "external" && root.state.apps && windows[root.state.apps.active]) appHistory.open(root.state.apps.active)
                        if (previousView === "external" && root.state.view !== "external") externalView.overview = false
                        if (previousView === "pi" && root.state.view === "home") {
                            piNavigator.overview = false
                            if (root.dismissPiPending) { appHistory.close("tablet-improve"); root.dismissPiPending = false }
                        }
                        if (root.nativeChat && root.state.view === "pi" && (previousView !== "pi" || !appHistory.opened.includes("tablet-improve"))) appHistory.open("tablet-improve")
                        if (root.pendingNavigation) {
                            root.restoreNavigation(root.pendingNavigation)
                            root.pendingNavigation = ""
                        }
                    }
                    else if (root.connected) Qt.quit()
                } catch (_) { root.error = "Unable to read iteration status" }
            }
        }
    }
    PiClient {
        id: nativeAgent
        active: root.nativeChat && !!root.state.running
        deliveryEnabled: root.draftRestored && !root.updating
        persistDraft: () => root.saveDraft(true) ? Qt.md5(nativeChatView.draft) : ""
        onClosed: { if (actionRunner.running) root.closePending = true; else root.run("close") }
        onEditorRequested: text => nativeChatView.draft = text
        onPromptRejected: text => {
            nativeChatView.draft = nativeChatView.draft ? text + "\n\n" + nativeChatView.draft : text
        }
        onNewChatDone: { nativeChatView.draft = ""; root.saveDraft(true) }
    }
    Process {
        id: actionRunner
        stdout: StdioCollector {
            onStreamFinished: {
                if (!root.nativeChat || !text.trim()) return
                try {
                    const response = JSON.parse(text)
                    if (typeof response.insertText === "string") {
                        nativeChatView.insertDictation(response.insertText)
                        root.saveDraft(true)
                    }
                } catch (_) { root.error = "Could not insert dictation into the draft" }
                root.pendingInsert = false
            }
        }
        stderr: StdioCollector { onStreamFinished: root.error = text.trim() }
        onExited: (code, status) => {
            if (code !== 0) { root.pendingInsert = false; root.dismissPiPending = false }
            if (root.closePending) Qt.callLater(() => { root.closePending = false; root.run("close") })
        }
    }
    Timer {
        id: statusPoll
        interval: 300; running: true; repeat: true; triggeredOnStart: true
        onTriggered: { if (!statusRunner.running) statusRunner.running = true }
    }
    PanelWindow {
        id: backdropWindow
        // Remains mapped across Home/Pi and Home-overlay visibility changes. Bottom is
        // above the work wallpaper but below the ordinary floating Pi client.
        visible: root.state.running && root.state.visible
        screen: root.targetScreen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: "tablet-rotation-fade" // Shared deployed no_anim policy.
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        FrameWitness { id: backdropFrames; requiredFrames: 1; armed: backdropWindow.backingWindowVisible }
        TabletHome {
            anchors.fill: parent
            apps: root.apps
            enabled: false
        }
    }
    PanelWindow {
        id: homeWindow
        visible: root.state.running && root.state.visible && root.state.view === "home"
        screen: root.targetScreen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        // Interactive Home covers apps; the separate opaque base never unmaps.
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "tablet-rotation-fade"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        FrameWitness { id: homeFrames; armed: homeWindow.backingWindowVisible }
        TabletHome {
            id: homeView
            anchors.fill: parent
            enabled: root.state.view === "home" && !root.updating
            apps: root.apps
            history: appHistory
            appSummary: root.appSummary
            navigationBlocked: root.updating || root.voicePending
            navigationUrgent: root.voicePending || !!nativeAgent.question
            onAppRequested: (id, label) => root.openApp(id, label)
            onWindowCloseRequested: id => root.closeApp(id)
            onExitRequested: {
                if (root.nativeChat) root.closeNative()
                else root.run("close")
            }
            Label {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 24; bottomMargin: 68 }
                visible: root.state.view === "home" && !!(root.error || root.state.error || root.panelError || (root.nativeChat && nativeAgent.error))
                text: root.error || root.state.error || (root.nativeChat ? nativeAgent.error : "") || root.panelError || ""
                color: "#ffb0ab"
                wrapMode: Text.WordWrap
            }
        }
    }
    PanelWindow {
        id: chatWindow
        visible: root.nativeChat && root.state.running && root.state.visible && root.state.view === "pi"
                 && root.chatAdmitted
        screen: root.targetScreen
        anchors { top: true; bottom: true; left: true; right: true }
        margins.bottom: root.state.keyboardInset || 0
        exclusionMode: ExclusionMode.Ignore
        color: "#142a38"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "tablet-rotation-fade"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
        TabletHome { anchors.fill: parent; apps: root.apps; enabled: false }
        FrameWitness { id: chatFrames; armed: chatWindow.backingWindowVisible && nativeAgent.connected && root.draftRestored && appSurface.progress >= .999 }
        AppSurface {
            id: appSurface
            anchors.fill: parent
            opened: chatWindow.backingWindowVisible
        PiChat {
            id: nativeChatView
            anchors.fill: parent
            enabled: !piNavigator.navigating
            messages: nativeAgent.messages
            ready: nativeAgent.ready && !nativeAgent.pendingWrites && !nativeAgent.awaitingPrompt
            busy: nativeAgent.busy
            activity: nativeAgent.activity
            locked: root.updating || nativeAgent.resetting
            notice: root.updating ? "Updating interface…" : !nativeAgent.ready && !nativeAgent.question && !nativeAgent.error ? "Loading conversation…" : nativeAgent.resetting ? "Starting a new chat…" : root.state.uiUpdate && root.state.uiUpdate.phase === "queued" ? "UI update ready · finish dictation or the pending action to apply" : ""
            error: root.error || root.state.error || nativeAgent.error || root.panelError || ""
            voice: root.state
            question: nativeAgent.question
            onSendRequested: text => { if (nativeAgent.prompt(text)) draft = "" }
            onStopRequested: nativeAgent.command({id: "stop", type: "abort"})
            onDraftChanged: { if (root.draftRestored && !root.updating && !nativeAgent.resetting) draftSave.restart() }
            onNewChatRequested: {
                if (nativeAgent.busy || draft.trim()) confirmNew.open()
                else if (root.saveDraft(true)) nativeAgent.newChat()
            }
            onHomeRequested: root.goHome()
            onInputPanelRequested: root.panelAcknowledged = undefined
            onVoiceRequested: action => root.run(action)
            onAnswerRequested: answer => nativeAgent.answer(answer)
            onCloseRequested: {
                if (nativeAgent.busy || voiceActive || nativeAgent.selectionPending) confirmClose.open()
                else root.closeNative()
            }
            Dialog {
                id: confirmNew
                objectName: "confirmNewChat"
                anchors.centerIn: parent
                title: "Start a new chat?"
                standardButtons: Dialog.Cancel | Dialog.Ok
                Label { text: "This stops the current reply and clears the draft.\nThe old conversation stays saved." }
                onAccepted: { if (root.saveDraft(true)) nativeAgent.newChat() }
            }
            Dialog {
                id: confirmClose
                anchors.centerIn: parent
                title: "Exit tablet?"
                standardButtons: Dialog.Cancel | Dialog.Ok
                Label { text: nativeAgent.selectionPending ? "The new chat selection is not saved yet.\nKeep this chat open until storage recovers.\nClosing now may reopen the previous conversation." : "This stops the reply and discards pending voice input.\nYour saved conversation and file changes remain." }
                onAccepted: root.closeNative()
            }
        }
        }
        AppNavigator {
            id: piNavigator
            anchors.fill: parent
            sourceItem: nativeChatView
            activeAppId: "tablet-improve"
            apps: appHistory.cards()
            history: appHistory
            summary: root.appSummary
            urgentInput: root.voicePending || !!nativeAgent.question || confirmNew.visible || confirmClose.visible
            blocked: root.updating || root.dismissPiPending || nativeAgent.resetting || urgentInput
            onGestureBegan: { if (!root.saveDraft(true)) cancelGesture(); else nativeChatView.blurInput() }
            onBlockedRequested: root.error = "Finish or cancel the pending input before switching apps"
            onHomeRequested: root.goHome()
            onCloseRequested: id => {
                if (id === "tablet-improve") root.goHome("", true)
                else root.closeApp(id)
            }
            onAppRequested: (id, label) => {
                if (!root.saveDraft(true)) return
                root.goHome(label)
            }
        }
    }
    ExternalAppView {
        id: externalView
        screen: root.targetScreen
        state: root.state
        history: appHistory
        apps: root.apps
        // A question arriving in background Pi must not trap the user inside
        // the browser; Home/Pi remain reachable to answer it. Other app opens
        // are rejected by openApp/the controller until the question is resolved.
        blocked: root.updating || root.voicePending
        onGestureBegan: root.panelAcknowledged = undefined
        onHomeRequested: { homeView.showHome(); root.run("home") }
        onAppRequested: (id, label) => root.openApp(id, label)
        onCloseRequested: id => root.closeApp(id)
    }
    PanelWindow {
        id: inputPanel
        visible: !root.nativeChat && root.state.running && root.state.visible && (root.state.view === "pi" || root.state.recording || root.state.transcribing || root.state.uncertain || root.state.ready)
        screen: root.targetScreen
        anchors { top: true; left: true; right: true }
        margins.top: 30
        implicitHeight: inputContent.implicitHeight + 16
        color: "#182d3c"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "tablet-iteration-input"
        // Buttons never take keyboard focus away from the exact Pi terminal.
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        ColumnLayout {
            id: inputContent
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
            spacing: 8
            Label {
                text: root.state.uncertain ? "Voice state uncertain · check Voxtype" : root.state.recording ? "● Recording" : root.state.transcribing ? "Transcribing…" : root.state.ready ? "Dictation ready · insertion does not send" : "This Pi stream · automatic keyboard"
                color: root.state.recording ? "#ffb0ab" : "#e5eff8"
                font.pixelSize: 16
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                enabled: !actionRunner.running
                Button { text: "Home"; height: 48; onClicked: root.run("home") }
                Button {
                    text: "Mic"
                    Accessible.name: "Start dictation"
                    height: 48
                    visible: !root.state.uncertain && !root.state.recording && !root.state.transcribing && !root.state.ready
                    onClicked: root.run("mic")
                }
                Button { text: "Stop"; height: 48; visible: root.state.recording; onClicked: root.run("stop") }
                Button { text: "Insert draft"; height: 48; visible: root.state.ready; onClicked: root.run("insert") }
                Button {
                    text: "Cancel"; height: 48
                    visible: root.state.uncertain || root.state.recording || root.state.transcribing || root.state.ready
                    onClicked: root.run("cancel")
                }
                Button { text: "Close trial"; height: 48; onClicked: root.run("close") }
            }
            Label {
                visible: !!(root.error || root.state.error)
                text: root.error || root.state.error || ""
                color: "#ffb0ab"; font.pixelSize: 13
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }
    }
}
