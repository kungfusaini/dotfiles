import QtQuick

// Shared presentation for native Pi and every simulated app: the opaque tablet
// Home remains behind the expanding app, never the desktop/workspace wallpaper.
Item {
    id: surface
    property bool opened: false
    property real progress: opened ? 1 : 0
    opacity: progress
    scale: 0.96 + 0.04 * progress
    visible: progress > 0
    enabled: opened
    Behavior on progress { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
}
