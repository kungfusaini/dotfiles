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
    readonly property var targetScreen: Quickshell.screens.find(s => s.name === "eDP-1") ?? null
    readonly property var apps: state.browserAvailable ? [{id: "vivaldi", label: "Vivaldi", kind: "window", icon: Quickshell.iconPath("vivaldi", true)}] : []
    property real drawerProgress: state.drawer ? 1 : 0
    Behavior on drawerProgress { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
    onStateChanged: {
        if (frames) { frames.frames = 0; frames.requestFrame() }
        if (state.browserRunning) nativeHistory.open("vivaldi")
        if (state.running && !restoredNavigation) {
            restoredNavigation = true
            if (state.resumeOverview) Qt.callLater(() => home.openSwitcher())
        }
    }
    AppHistory { id: nativeHistory; apps: root.apps }
    IpcHandler {
        target: "tabletNativeScene"
        function status(): string {
            return JSON.stringify({home: !!root.state.home, drawer: !!root.state.drawer,
                rendered: frames.rendered, width: window.width, height: window.height,
                transitioning: (home.homeProgress > 0 && home.homeProgress < 1)
                    || (root.drawerProgress > 0 && root.drawerProgress < 1),
                overview: home.switcherOpen, navigationContact: home.navigationContactActive})
        }
    }
    function accept(text) {
        try {
            const value = JSON.parse(text)
            if (value.failed) localError = value.error
            else { state = value; localError = "" }
        } catch (_) { localError = "Invalid tablet controller response" }
    }
    function command(name, value) {
        const process = actionComponent.createObject(root)
        process.command = [Quickshell.env("TABLET_PROOF_BIN"), name]
        if (value !== undefined) process.command = process.command.concat(["--value", String(value)])
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
            stdout: SplitParser { onRead: text => root.accept(text) }
            stderr: SplitParser { onRead: text => root.localError = text }
            onExited: destroy()
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
            || home.homeProgress > 0 || home.navigationContactActive || home.navigationVisible
        readonly property real inset: Math.max(0, root.state.keyboardInset || 0)
        mask: Region {
            width: window.expanded ? window.width : 0
            height: window.expanded ? window.height : 0
            regions: [
                Region { x: window.width - 144; y: 0; width: 144; height: 24 },
                Region { x: (window.width - 160) / 2; y: window.height - window.inset - 14; width: 160; height: 14 }
            ]
        }
        FrameWitness {
            id: frames
            armed: window.backingWindowVisible && root.state.running

        }
        TabletHome {
            id: home
            anchors.fill: parent
            modeLabel: "TABLET"
            nativePresentation: true
            nativeAppVisible: !root.state.home
            nativeAppId: "vivaldi"
            keyboardInset: window.inset
            apps: root.apps
            history: nativeHistory
            settingsExternallyManaged: true
            navigationBlocked: !!root.state.drawer || !!root.state.launching
            appSummary: app => root.state.browserRunning ? "Your tablet browser · same windows and tabs" : "Open Vivaldi in your tablet workspace"
            onNativeHomeRequested: root.command("home")
            onSettingsRequested: root.command("settings")
            onAppRequested: (id, label) => root.command("app")
            onExitRequested: root.command("close")
            onWindowCloseRequested: id => root.localError = "Close the window in Vivaldi; desktop windows are not closed here."
        }
        ColumnLayout {
            visible: !!root.state.home && !root.state.drawer
            anchors { bottom: parent.bottom; bottomMargin: 42; horizontalCenter: parent.horizontalCenter }
            width: Math.min(520, parent.width - 48)
            Label {
                Layout.fillWidth: true
                visible: !root.state.browserRunning
                text: root.state.launching ? "Opening your tablet browser…" : "Open Vivaldi here. Your laptop apps stay on the desktop."
                color: "#b3cdcb"; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
            }
            Label {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.localError || root.state.error || ""
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
            homeVisible: true
            drawerVisible: !!root.state.drawer
            onSettingsRequested: root.command("settings")
            onHomeRequested: root.command("home")
        }
    }
}
