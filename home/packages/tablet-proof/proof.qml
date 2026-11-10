import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ShellRoot {
    id: root
    property var state: ({running: false, home: false, drawer: false, keyboardInset: 0})
    property string localError: ""
    property bool sentReady: false
    readonly property var targetScreen: Quickshell.screens.find(s => s.name === "eDP-1") ?? null
    onStateChanged: { if (frames) { frames.frames = 0; frames.requestFrame() } }
    IpcHandler {
        target: "tabletProofScene"
        function status(): string {
            return JSON.stringify({home: !!root.state.home, drawer: !!root.state.drawer,
                rendered: frames.rendered, width: window.width, height: window.height})
        }
    }
    function accept(text) {
        try {
            const value = JSON.parse(text)
            if (value.failed) localError = value.error
            else { state = value; localError = "" }
        } catch (_) { localError = "Invalid proof controller response" }
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
        WlrLayershell.namespace: "tablet-native-proof"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        readonly property bool expanded: !!root.state.home || !!root.state.drawer
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
            onRenderedChanged: {
                if (rendered && !root.sentReady) { root.sentReady = true; root.command("ui-ready") }
            }
        }
        Item {
            id: scene
            anchors.fill: parent
            TabletWallpaper { anchors.fill: parent; visible: !!root.state.home }
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 520)
                visible: !!root.state.home
                spacing: 24
                Label { text: "TABLET HOME"; color: "#eff5ff"; font.pixelSize: 28; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignHCenter }
                Label {
                    text: "Same browser. Same session."
                    color: "#bdcddc"; font.pixelSize: 15
                    Layout.alignment: Qt.AlignHCenter
                }
                Button {
                    objectName: "resumeBrowser"
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 180; implicitHeight: 136
                    background: GlassTile {}
                    contentItem: ColumnLayout {
                        Image { source: Quickshell.iconPath("vivaldi", true); sourceSize.width: 56; sourceSize.height: 56; Layout.preferredWidth: 56; Layout.preferredHeight: 56; Layout.alignment: Qt.AlignHCenter }
                        Label { text: "Resume browser"; color: "white"; font.pixelSize: 17; Layout.alignment: Qt.AlignHCenter }
                    }
                    onClicked: root.command("app")
                }
                Button {
                    objectName: "returnDesktop"
                    text: "Return to desktop"
                    implicitHeight: 52; Layout.alignment: Qt.AlignHCenter
                    onClicked: root.command("close")
                }
                Label {
                    text: root.localError || root.state.error || "Swipe down from the top-right for settings"
                    color: "#cbdde6"; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
            }
            Rectangle {
                anchors.fill: parent
                color: "#99050d18"
                visible: !!root.state.drawer
                MouseArea { anchors.fill: parent; onClicked: root.command("dismiss") }
                GlassTile {
                    id: drawer
                    objectName: "globalSettings"
                    anchors { top: parent.top; right: parent.right; margins: 16 }
                    width: Math.min(380, parent.width - 32)
                    height: Math.min(520, parent.height - 32)
                    MouseArea { anchors.fill: parent }
                    ColumnLayout {
                        anchors { fill: parent; margins: 20 }
                        spacing: 16
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "CONTROL CENTRE"; color: "white"; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Button { text: "Close"; implicitHeight: 48; onClicked: root.command("dismiss") }
                        }
                        Label { text: "Live volume and display brightness"; color: "#bdcddc"; font.pixelSize: 12 }
                        RowLayout {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            spacing: 18
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                Button {
                                    text: root.state.muted ? "Unmute" : "Mute"
                                    enabled: root.state.volume !== null && root.state.volume !== undefined
                                    implicitHeight: 64; Layout.fillWidth: true
                                    onClicked: root.command("mute")
                                }
                                Button { text: "Hide keyboard"; implicitHeight: 64; Layout.fillWidth: true; onClicked: root.command("hide-keyboard") }
                                Button { text: "Home"; implicitHeight: 64; Layout.fillWidth: true; onClicked: root.command("home") }
                                Button { text: "Exit proof"; implicitHeight: 64; Layout.fillWidth: true; onClicked: root.command("close") }
                            }
                            PillSlider {
                                id: brightnessSlider
                                objectName: "liveBrightness"
                                Layout.fillHeight: true; Layout.preferredWidth: 72
                                label: "Brightness"; iconName: "sun"; from: 5
                                enabled: root.state.brightness !== null && root.state.brightness !== undefined
                                value: root.state.brightness || 0
                                onMoved: { pendingBrightness = value; brightnessDelay.restart() }
                                property real pendingBrightness: 0
                                Timer { id: brightnessDelay; interval: 70; onTriggered: root.command("brightness", brightnessSlider.pendingBrightness) }
                            }
                            PillSlider {
                                id: volumeSlider
                                objectName: "liveVolume"
                                Layout.fillHeight: true; Layout.preferredWidth: 72
                                label: "Volume"; iconName: root.state.muted ? "muted" : "volume"
                                enabled: root.state.volume !== null && root.state.volume !== undefined
                                value: root.state.volume || 0
                                onMoved: { pendingVolume = value; volumeDelay.restart() }
                                property real pendingVolume: 0
                                Timer { id: volumeDelay; interval: 70; onTriggered: root.command("volume", volumeSlider.pendingVolume) }
                            }
                        }
                        Label { text: root.localError || root.state.error || "Unavailable controls are disabled"; color: "#cbdde6"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
            }
            EdgeGestures {
                anchors.fill: parent
                keyboardInset: window.inset
                homeVisible: !!root.state.home
                drawerVisible: !!root.state.drawer
                onSettingsRequested: { console.log("Global settings gesture"); root.command("settings") }
                onHomeRequested: { console.log("Global Home gesture"); root.command("home") }
            }
        }
    }
}
