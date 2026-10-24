import Quickshell
import Quickshell.Wayland
import Quickshell.Io
import QtQuick

ShellRoot {
    id: shell
    property int secondsLeft: 10
    property bool cancelRequested: false

    function cancel() {
        if (cancelRequested)
            return
        cancelRequested = true
        const command = Quickshell.env("HEADLESS_CANCEL_COMMAND")
        if (command) {
            cancelProcess.command = [command, "restore"]
            cancelProcess.running = true
        } else {
            Qt.quit()
        }
    }

    Process {
        id: cancelProcess
        onExited: Qt.quit()
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            required property var modelData
            screen: modelData
            visible: modelData.name === "eDP-1"

            anchors { top: true; right: true; bottom: true; left: true }
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
            color: "transparent"

            Item {
                anchors.fill: parent
                focus: true
                Keys.onEscapePressed: shell.cancel()
            }

            Rectangle {
                anchors.fill: parent
                color: "#f20b0d12"

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width * 0.82, 900)
                    spacing: 22

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: shell.cancelRequested ? "HEADLESS MODE CANCELLED" : (Quickshell.env("HEADLESS_PREVIEW") === "1" ? "HEADLESS COUNTDOWN PREVIEW" : "HEADLESS MODE PRIMED")
                        color: "#ffffff"
                        font.pixelSize: 46
                        font.weight: Font.DemiBold
                        font.letterSpacing: 2
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: shell.cancelRequested ? "Restoring hinge sensing…" : (Quickshell.env("HEADLESS_PREVIEW") === "1" ? "Nothing will be disabled" : "Fold the display — the keyboard stays active")
                        color: "#c9ced8"
                        font.pixelSize: 28
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: shell.cancelRequested ? "CANCELLING…" : shell.secondsLeft
                        color: shell.cancelRequested ? "#86efac" : (shell.secondsLeft <= 3 ? "#ff6b6b" : "#7dd3fc")
                        font.pixelSize: shell.cancelRequested ? 58 : 150
                        font.weight: Font.Bold
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: shell.cancelRequested ? "Please wait; the countdown has stopped" : "Press Esc to cancel"
                        color: "#9299a8"
                        font.pixelSize: 20
                    }
                }
            }
        }
    }

    Timer {
        interval: 1000
        running: !shell.cancelRequested
        repeat: true
        onTriggered: {
            shell.secondsLeft -= 1
            if (shell.secondsLeft <= 0)
                Qt.quit()
        }
    }
}
