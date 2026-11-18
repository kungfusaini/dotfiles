import QtQuick
import QtQuick.Controls

Button {
    id: gesture
    objectName: "homeHandle"
    property bool edgeAnchored: false
    width: 180; height: edgeAnchored ? 56 : 52
    focusPolicy: Qt.NoFocus
    property bool blocked: false
    property real pull: 0
    property bool dragging: drag.active
    property double startedAt: 0
    property double movedAt: 0
    property bool claimed: false
    property bool cancelled: false
    signal began()
    signal homeRequested()
    signal switcherRequested()
    signal blockedRequested()
    Accessible.name: "Swipe up for Home; swipe up and pause for open apps"
    background: Item {
        Rectangle { anchors.centerIn: parent; anchors.verticalCenterOffset: gesture.edgeAnchored ? -2 : 0; width: 100; height: 5; radius: 3; color: "#d7e7e2" }
    }
    onBlockedChanged: { if (blocked) cancel() }
    onPressed: { if (!drag.active) { claimed = false; cancelled = false } }
    function cancel() { cancelled = true; pull = 0 }
    function begin() {
        startedAt = Date.now(); movedAt = startedAt
        claimed = false; cancelled = blocked; pull = 0
        if (blocked) blockedRequested()
        else began()
    }
    function move(distance) {
        if (cancelled) return
        pull = Math.max(0, distance)
        movedAt = Date.now()
    }
    function pause(now) {
        if (!cancelled && !claimed && pull >= 72 && now - startedAt >= 300 && now - movedAt >= 160) {
            claimed = true
            switcherRequested()
        }
    }
    function finish(now) {
        if (!cancelled && !claimed && pull >= 60) {
            claimed = true
            // Duration is not a hold: a deliberate, continuous touch swipe
            // can take longer than 300 ms. Only pause() selects the switcher.
            homeRequested()
        }
        pull = 0
    }
    onClicked: {
        if (blocked) blockedRequested()
        else if (!claimed && !cancelled) homeRequested()
    }
    DragHandler {
        id: drag
        target: null
        xAxis.enabled: false
        onActiveChanged: {
            if (active) gesture.begin()
            else gesture.finish(Date.now())
        }
        onActiveTranslationChanged: gesture.move(-activeTranslation.y)
        onCanceled: gesture.cancel()
    }
    Timer { interval: 30; repeat: true; running: drag.active; onTriggered: gesture.pause(Date.now()) }
}
