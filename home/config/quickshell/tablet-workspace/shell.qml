import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ShellRoot {
    id: root
    property bool tabletVisible: false
    property string monitorName: ""
    property string errorMessage: ""

    function run(action) {
        if (actionRunner.running)
            return
        actionRunner.command = ["tablet-workspace", action]
        actionRunner.running = true
    }

    Process {
        id: statusRunner
        command: ["tablet-workspace", "status"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const state = JSON.parse(this.text)
                    // Stay alive but hidden when parked. Exiting on a stale
                    // disabled response can race with immediate re-entry.
                    root.monitorName = state.monitor
                    root.tabletVisible = state.visible
                } catch (error) {
                    root.tabletVisible = false
                }
            }
        }
        onExited: (code, status) => {
            if (code !== 0)
                root.tabletVisible = false
        }
    }

    Process {
        id: actionRunner
        stderr: StdioCollector {
            onStreamFinished: root.errorMessage = this.text.trim()
        }
    }

    Timer {
        interval: 500
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!statusRunner.running)
                statusRunner.running = true
        }
    }

    PanelWindow {
        visible: root.tabletVisible
        screen: Quickshell.screens.find(s => s.name === root.monitorName) ?? null
        anchors { top: true; left: true; right: true }
        margins.top: 30 // Keep the existing Waybar visible and unchanged.
        implicitHeight: root.errorMessage ? 128 : 96
        color: "#151922"
        WlrLayershell.namespace: "tablet-workspace"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Label {
                    visible: parent.width > 900
                    text: "Tablet trial"
                    color: "#f4f4f5"
                    font.pixelSize: 22
                    Layout.leftMargin: 8
                    Layout.rightMargin: 16
                }
                Repeater {
                    model: [
                        { label: "New browser", action: "browser" },
                        { label: "Keyboard", action: "keyboard" },
                        { label: "Next app", action: "next" },
                        { label: "Back to laptop", action: "leave" }
                    ]
                    delegate: Button {
                        required property var modelData
                        text: modelData.label
                        font.pixelSize: 20
                        Layout.fillWidth: true
                        Layout.minimumWidth: 130
                        Layout.preferredHeight: 64
                        enabled: !actionRunner.running
                        onClicked: root.run(modelData.action)
                    }
                }
            }
            Label {
                visible: root.errorMessage !== ""
                text: root.errorMessage
                color: "#ffb4a9"
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }
    }
}
