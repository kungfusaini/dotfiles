import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import QtQuick

// One exact backend-registered tablet window, never a monitor capture. Kept
// offscreen; AppNavigator/ItemGrabResult consume it without touching app input.
Item {
    id: preview
    property string appId: ""
    property var record: null
    property var lifetime: null
    property var history: null
    property bool captureEnabled: false
    property bool liveCapture: false
    property bool overview: false
    readonly property string identityKey: lifetime
        ? [lifetime.instance, lifetime.address, lifetime.pid, lifetime.start, lifetime.stableId].join(":") : ""
    onIdentityKeyChanged: {
        if (history) history.setSource(appId, identityKey)
    }
    readonly property string permissionKey: record ? JSON.stringify(record) : ""
    onPermissionKeyChanged: Hyprland.refreshToplevels()
    onHistoryChanged: { if (history) history.setSource(appId, identityKey) }
    function matches(t) {
        if (!record || record.instance !== Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")) return false
        const c = t.lastIpcObject
        return c && t.address.replace(/^0x/, "") === record.address.replace(/^0x/, "")
            && c.pid === record.pid && c.class === record.class && c.stableId === record.stableId
            && c.mapped && c.workspace && c.workspace.name === "tablet-trial"
            && !c.pinned && !(c.grouped && c.grouped.length) && !!c.floating === record.floating
            && (!record.tag || (c.tags || []).some(tag => tag.replace(/\*$/, "") === record.tag))
    }
    readonly property var toplevel: Hyprland.toplevels.values.find(t => matches(t)) ?? null
    readonly property bool hasContent: !!loader.item && loader.item.hasContent
    function retain() {
        if (overview && hasContent && history && !history.capturing && !history.previews[appId])
            history.capture(appId, preview)
    }
    onHasContentChanged: retain()
    onOverviewChanged: retain()
    Timer {
        interval: 60; repeat: true
        running: preview.overview && preview.hasContent && !!preview.history && !preview.history.previews[preview.appId]
        onTriggered: preview.retain()
    }
    Rectangle { anchors.fill: parent; color: "#142a38" }
    Loader {
        id: loader
        anchors.fill: parent
        active: preview.captureEnabled && !!preview.toplevel
        sourceComponent: Item {
            readonly property bool hasContent: capture.hasContent
            ScreencopyView {
                id: capture
                readonly property real fit: sourceSize.width > 0 && sourceSize.height > 0
                    ? Math.min(parent.width / sourceSize.width, parent.height / sourceSize.height) : 0
                anchors.centerIn: parent
                width: sourceSize.width * fit; height: sourceSize.height * fit
                captureSource: preview.toplevel ? preview.toplevel.wayland : null
                live: preview.liveCapture && !preview.overview
                paintCursor: false
            }
        }
    }
}
