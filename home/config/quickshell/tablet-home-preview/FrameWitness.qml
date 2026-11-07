import QtQuick
import QtQuick.Window

// Observe queued frames, not merely QWindow.visible. A second requested frame
// keeps static scenes from acknowledging only their initial empty allocation.
Item {
    id: witness
    property bool armed: false
    property int frames: 0
    property int requiredFrames: 2
    readonly property bool rendered: armed && frames >= requiredFrames
    readonly property var windowHandle: Window.window
    readonly property real viewportWidth: windowHandle ? windowHandle.width : 0
    readonly property real viewportHeight: windowHandle ? windowHandle.height : 0
    onViewportWidthChanged: { frames = 0; requestFrame() }
    onViewportHeightChanged: { frames = 0; requestFrame() }
    function requestFrame() { if (armed && windowHandle) windowHandle.update() }
    onArmedChanged: { frames = 0; requestFrame() }
    onWindowHandleChanged: { frames = 0; requestFrame() }
    Connections {
        target: witness.windowHandle
        function onFrameSwapped() {
            if (!witness.armed) return
            witness.frames++
            if (witness.frames < witness.requiredFrames) witness.requestFrame()
        }
    }
}
