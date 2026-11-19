import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ShellRoot {
    id: root
    property var state: ({running: false, home: true, drawer: false, keyboardInset: 0})
    property string localError: ""
    property bool restoredNavigation: false
    property string lastActiveApp: ""
    readonly property var targetScreen: Quickshell.screens.find(s => s.name === "eDP-1") ?? null
    readonly property var apps: [
        {id: "vivaldi", label: "Vivaldi", kind: "window", icon: Quickshell.iconPath("vivaldi", true)},
        {id: "games", label: "Pegasus", kind: "window", icon: Quickshell.iconPath("org.pegasus_frontend.Pegasus", true)},
        {id: "stremio", label: "Stremio", kind: "window", icon: Quickshell.iconPath("com.stremio.Stremio", true)}
    ]
    readonly property var activePreview: previewCopies.itemAt(Math.max(0, apps.findIndex(app => app.id === state.activeApp)))
    property real drawerProgress: state.drawer ? 1 : 0
    Behavior on drawerProgress { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
    onStateChanged: {
        if (frames) { frames.frames = 0; frames.requestFrame() }
        // Do not rebuild the ListView model on every status/IME update: that
        // destroys an active card DragHandler before it receives touch release.
        for (const app of apps) {
            const alive = !!(state.cardLifetimes && state.cardLifetimes[app.id])
            if (alive && !nativeHistory.opened.includes(app.id)) nativeHistory.open(app.id)
            else if (!alive && nativeHistory.opened.includes(app.id)) nativeHistory.close(app.id)
        }
        if (state.activeApp && state.activeApp !== lastActiveApp) {
            lastActiveApp = state.activeApp
            if (nativeHistory.opened.includes(lastActiveApp) && nativeHistory.opened[0] !== lastActiveApp)
                nativeHistory.open(lastActiveApp)
        }
        if (state.running && !restoredNavigation) {
            restoredNavigation = true
            if (state.resumeOverview) Qt.callLater(() => home.openSwitcher())
        }
    }
    AppHistory { id: nativeHistory; apps: root.apps }
    IpcHandler {
        target: "tabletNativeScene"
        // Read-only geometry for test input; never invokes UI actions directly.
        function targetRect(name: string): string {
            function find(item) {
                if (item.objectName === name && item.visible && item.enabled) return item
                for (const child of item.children || []) {
                    const result = find(child)
                    if (result) return result
                }
                return null
            }
            if (!["app-vivaldi", "app-games", "closeSettings", "muteButton", "brightnessSlider", "volumeSlider", "appCard-vivaldi", "appCard-games", "appPreview-vivaldi", "appPreview-games", "app-stremio", "appCard-stremio", "appPreview-stremio"].includes(name)) return "null"
            const item = find(window.contentItem)
            if (!item || !item.visible || !item.enabled) return "null"
            const point = item.mapToItem(window.contentItem, 0, 0)
            return JSON.stringify({x: point.x, y: point.y, width: item.width, height: item.height})
        }
        function status(): string {
            const cardWindows = {}
            for (const app of root.apps)
                if (root.state.cardSources && root.state.cardSources[app.id]) cardWindows[app.id] = root.state.cardSources[app.id].stableId
            return JSON.stringify({home: !!root.state.home, drawer: !!root.state.drawer,
                rendered: frames.rendered, width: window.width, height: window.height,
                transitioning: (home.homeProgress > 0 && home.homeProgress < 1)
                    || (root.drawerProgress > 0 && root.drawerProgress < 1),
                overview: home.switcherOpen, navigationContact: home.navigationContactActive,
                previewImages: Object.keys(nativeHistory.previews), capturing: nativeHistory.capturing,
                registeredCards: Object.keys(root.state.cardLifetimes || {}), eligibleCards: Object.keys(root.state.cardSources || {}), cardWindows: cardWindows,
                captureReady: !!root.activePreview && root.activePreview.hasContent,
                presentationProgress: home.homePresentationProgress,
                navigationInput: {x: home.navigationInputRect.x, y: home.navigationInputRect.y,
                    width: home.navigationInputRect.width, height: home.navigationInputRect.height}})
        }
    }
    function accept(text) {
        try {
            const value = JSON.parse(text)
            if (value.failed) { localError = value.error; return false }
            state = value; localError = ""
            return true
        } catch (_) { localError = "Invalid tablet controller response"; return false }
    }
    function command(name, value, failure) {
        const process = actionComponent.createObject(root)
        process.requestName = name
        process.failureCallback = failure || null
        process.command = [Quickshell.env("TABLET_PROOF_BIN"), name]
        if (value !== undefined) process.command = process.command.concat((name === "dismiss-app" || name === "resume-app")
            ? ["--target", JSON.stringify(value)] : ["--value", String(value)])
        process.running = true
    }
    Process {
        id: subscription
        command: [Quickshell.env("TABLET_PROOF_BIN"), "watch"]
        running: true
        stdout: SplitParser { onRead: text => root.accept(text) }
        onExited: { root.state = {running: false}; Qt.quit() }
    }
    Process {
        id: readyRunner
        command: [Quickshell.env("TABLET_PROOF_BIN"), "ui-ready"]
        stdout: SplitParser { onRead: text => root.accept(text) }
        stderr: SplitParser { onRead: text => root.localError = text }
    }
    Timer {
        interval: 150; repeat: true
        running: !!root.state.running && frames.rendered && !root.state.ready
        onTriggered: { if (!readyRunner.running) readyRunner.running = true }
    }
    Component {
        id: actionComponent
        Process {
            id: actionProcess
            property string requestName: ""
            property var failureCallback: null
            property bool acknowledged: false
            stdout: SplitParser {
                onRead: text => {
                    if (root.accept(text)) {
                        actionProcess.acknowledged = true
                        if (actionProcess.requestName === "resume-app" || actionProcess.requestName === "dismiss-app")
                            home.switcherOpen = false
                    }
                }
            }
            stderr: SplitParser { onRead: text => root.localError = text }
            onExited: {
                if (!acknowledged && failureCallback) failureCallback()
                destroy()
            }
        }
    }
    PanelWindow {
        id: window
        screen: root.targetScreen
        visible: !!root.targetScreen && !!root.state.running
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "tablet-rotation-fade"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        readonly property bool expanded: !!root.state.home || root.drawerProgress > 0
            || home.homePresentationProgress > 0 || home.navigationContactActive || home.navigationVisible
        readonly property real inset: Math.max(0, root.state.keyboardInset || 0)
        mask: Region {
            width: window.expanded ? window.width : 0
            height: window.expanded ? window.height : 0
            regions: [
                Region { x: window.width - 144; y: 0; width: 144; height: 24 },
                Region {
                    x: home.navigationInputRect.x; y: home.navigationInputRect.y
                    width: home.navigationInputRect.width; height: home.navigationInputRect.height
                }
            ]
        }
        FrameWitness {
            id: frames
            armed: window.backingWindowVisible && root.state.running

        }
        Repeater {
            id: previewCopies
            model: root.apps
            NativeAppPreview {
                required property var modelData
                appId: modelData.id
                record: root.state.cardSources ? root.state.cardSources[appId] || null : null
                lifetime: root.state.cardLifetimes ? root.state.cardLifetimes[appId] || null : null
                history: nativeHistory
                x: -width * 2
                width: window.width; height: window.height
                overview: home.switcherOpen
                captureEnabled: !!root.state.running && (overview || (!root.state.home && root.state.activeApp === appId))
                liveCapture: !root.state.home && root.state.activeApp === appId
            }
        }
        TabletHome {
            id: home
            anchors.fill: parent
            modeLabel: "TABLET"
            nativePresentation: true
            nativeAppVisible: !root.state.home
            nativeSourceItem: !root.state.home && root.activePreview && root.activePreview.hasContent ? root.activePreview : null
            nativeAppId: root.state.activeApp || "vivaldi"
            keyboardInset: window.inset
            apps: root.apps
            history: nativeHistory
            settingsExternallyManaged: true
            navigationBlocked: !!root.state.drawer || !!root.state.launching
            appAvailable: app => !!(root.state.cardSources && root.state.cardSources[app.id])
            appContext: app => root.state.cardSources ? root.state.cardSources[app.id] || null : null
            appSummary: app => app.id === "games"
                ? (root.state.gameRunning ? "Game running · kept on unfold"
                    : root.state.pegasusRunning ? "Your tablet game library" : "Open Pegasus in your tablet workspace")
                : app.id === "stremio" ? "Your tablet player · normal close may hide to tray"
                : (root.state.browserRunning ? "Your tablet browser · same windows and tabs" : "Open Vivaldi in your tablet workspace")
            onNativeHomeRequested: root.command("home")
            onSettingsRequested: root.command("settings")
            onAppRequested: (id, label) => {
                if (root.state.cardLifetimes && root.state.cardLifetimes[id] && !(root.state.cardSources && root.state.cardSources[id])
                    && !(id === "stremio" && root.state.stremioHidden)) {
                    root.localError = "That window is unavailable here; no replacement was opened."
                    return
                }
                root.command(id === "games" || id === "stremio" ? id : "app")
            }
            onExitRequested: root.command("close")
            onWindowResumeRequested: (id, context) => {
                if (!context) { root.localError = "That tablet window is unavailable; no replacement was opened."; return }
                root.command("resume-app", {app: id, window: context})
            }
            onWindowCloseRequested: (id, context, token) => {
                if (!context) { root.localError = "That tablet window is no longer available."; home.finishWindowDismissal(id, token); return }
                root.command("dismiss-app", {app: id, window: context}, () => home.finishWindowDismissal(id, token))
            }
        }
        ColumnLayout {
            visible: !!root.state.home && !root.state.drawer
            anchors { bottom: parent.bottom; bottomMargin: 42; horizontalCenter: parent.horizontalCenter }
            width: Math.min(520, parent.width - 48)
            Label {
                Layout.fillWidth: true
                visible: !root.state.browserRunning
                text: root.state.launching ? "Opening your tablet app…" : "Open Vivaldi, Pegasus or Stremio here. Your laptop apps stay on the desktop."
                color: "#b3cdcb"; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
            }
            Label {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.localError || root.state.error || root.state.gamesError || root.state.stremioError || ""
                color: "#b3cdcb"; wrapMode: Text.Wrap
            }
        }
        Rectangle {
            anchors.fill: parent
            visible: root.drawerProgress > 0
            opacity: root.drawerProgress
            color: "#99060e17"
            MouseArea { anchors.fill: parent; onClicked: root.command("dismiss") }
        }
        ControlCenter {
            objectName: "globalSettings"
            visible: root.drawerProgress > 0
            enabled: !!root.state.drawer
            opacity: root.drawerProgress
            anchors { right: parent.right; rightMargin: window.width < 600 ? 16 : 28 }
            y: (window.width < 600 ? 16 : 28) - (1 - root.drawerProgress) * 56
            scale: 0.98 + root.drawerProgress * 0.02
            transformOrigin: Item.TopRight
            width: Math.min(392, window.width - 32)
            height: Math.min(480, window.height - 32)
            live: true
            showExit: false
            volumeAvailable: root.state.volume !== null && root.state.volume !== undefined
            brightnessAvailable: root.state.brightness !== null && root.state.brightness !== undefined
            volume: root.state.volume || 0
            brightness: root.state.brightness || 0
            muted: !!root.state.muted
            onVolumeEdited: value => { volumeDelay.pending = value; volumeDelay.restart() }
            onBrightnessEdited: value => { brightnessDelay.pending = value; brightnessDelay.restart() }
            onMuteRequested: root.command("mute")
            onCloseRequested: root.command("dismiss")
            onExitRequested: root.command("close")
        }
        Timer { id: volumeDelay; property real pending: 0; interval: 70; onTriggered: root.command("volume", pending) }
        Timer { id: brightnessDelay; property real pending: 0; interval: 70; onTriggered: root.command("brightness", pending) }
        EdgeGestures {
            anchors.fill: parent
            keyboardInset: window.inset
            // Native navigation uses the original AppNavigator/BottomGesture;
            // keep only this component's globally proven top-right edge.
            bottomNavigationEnabled: false
            homeVisible: !!root.state.home
            drawerVisible: !!root.state.drawer
            onSettingsRequested: root.command("settings")
            onHomeRequested: root.command("home")
        }
    }
}
