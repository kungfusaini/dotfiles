import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick

ShellRoot {
    id: root
    readonly property var targetScreen: Quickshell.screens.find(
        s => s.name === Quickshell.env("TABLET_FADE_MONITOR")) ?? null

    FadeState {
        id: transition
        hasScreen: root.targetScreen !== null
        mapped: window.backingWindowVisible
        onExpired: Qt.quit()
    }
    IpcHandler {
        target: "rotationFade"
        function status(): string { return transition.status() }
        function cover(): void { transition.cover() }
        function reveal(): void { transition.reveal() }
    }

    PanelWindow {
        id: window
        screen: root.targetScreen
        visible: transition.shown && root.targetScreen !== null
        color: "transparent"
        surfaceFormat.opaque: false
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "tablet-rotation-fade"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        onClosed: Qt.quit()
        onResourcesLost: Qt.quit()

        Rectangle {
            anchors.fill: parent
            color: "#000000"
            opacity: transition.level
            // Block taps only during transition; never grab keyboard focus.
            MouseArea { anchors.fill: parent }
        }
    }
}
