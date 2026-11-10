import QtQuick

// Only contacts beginning inside these small edge Items can become gestures.
// Layer-shell input masking and full-screen passthrough are compositor-tested.
// Accept the initial press immediately: a delayed passive drag grab can lose
// mouse motion as it leaves the narrow native input region. Qt synthesizes the
// same sequence for single-finger touch; no input outside the zones is grabbed.
Item {
    id: root
    property real keyboardInset: 0
    property bool homeVisible: false
    property bool drawerVisible: false
    signal settingsRequested()
    signal homeRequested()
    Item {
        id: topEdge
        objectName: "globalTopEdge"
        anchors { top: parent.top; right: parent.right }
        width: 144; height: 24
        enabled: !root.drawerVisible
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            property real startY: 0
            property bool fired: false
            onPressed: mouse => { startY = mouse.y; fired = false }
            onPositionChanged: mouse => {
                if (pressed && mouse.y - startY >= 44 && !fired) {
                    fired = true
                    root.settingsRequested()
                }
            }
        }
    }
    Item {
        id: bottomEdge
        objectName: "globalBottomEdge"
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: root.keyboardInset }
        width: 160; height: 14
        enabled: !root.drawerVisible && !root.homeVisible
        Rectangle {
            anchors { bottom: parent.bottom; bottomMargin: 5; horizontalCenter: parent.horizontalCenter }
            width: 100; height: 4; radius: 2; color: "#cceff5ff"
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            property real startY: 0
            property bool fired: false
            onPressed: mouse => { startY = mouse.y; fired = false }
            onPositionChanged: mouse => {
                if (pressed && mouse.y - startY <= -44 && !fired) {
                    fired = true
                    root.homeRequested()
                }
            }
        }
    }
}
