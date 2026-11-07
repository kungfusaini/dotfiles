import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import QtQuick

// Native windows keep their own rendering/input. This window accepts input only
// at the shared bottom handle, expanding to the card scene during navigation.
PanelWindow {
    id: window
    property var state: ({})
    property var history: null
    property var apps: []
    property bool blocked: false
    property alias overview: navigator.overview
    readonly property bool navigationBusy: navigator.dragging
    readonly property bool contentReady: !!captureLoader.item && captureLoader.item.hasContent
    readonly property bool rendered: witness.rendered
    readonly property string activeId: state.apps ? state.apps.active : ""
    readonly property var record: state.apps && state.apps.windows ? state.apps.windows[activeId] : null
    onRecordChanged: { if (record) Hyprland.refreshToplevels() }
    readonly property var toplevel: record ? Hyprland.toplevels.values.find(t => t.address.replace(/^0x/, "") === record.address.replace(/^0x/, "") && t.lastIpcObject.pid === record.pid && (t.lastIpcObject.tags || []).some(tag => tag.replace(/\*$/, "") === record.tag)) ?? null : null
    function showSwitcher() { navigator.showSwitcher() }
    function resume(id, label) { navigator.resume(id, label) }
    function requestHome() { navigator.goHome() }
    function dismissApp(id) { navigator.dismissCard(id) }
    signal homeRequested()
    signal appRequested(string id, string label)
    signal closeRequested(string id)
    signal gestureBegan()
    visible: state.running && state.visible && state.view === "external"
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "tablet-rotation-fade"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    mask: Region {
        width: window.width
        height: navigator.navigating ? window.height : 32
        regions: [Region {
            y: window.height - (window.state.keyboardInset || 0) - 56
            width: window.width; height: 56
        }]
    }
    FrameWitness { id: witness; armed: window.backingWindowVisible && window.contentReady }
    Item {
        id: scene
        anchors.fill: parent
        TabletHome { anchors.fill: parent; apps: window.apps; enabled: false; visible: navigator.navigating }
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: "#142a38"; visible: !navigator.navigating
            Text { anchors { fill: parent; margins: 6 } text: window.state.error || ""; color: "#ffb0ab"; elide: Text.ElideRight }
        }
        Rectangle { anchors { bottom: parent.bottom; bottomMargin: window.state.keyboardInset || 0; left: parent.left; right: parent.right } height: 56; color: "#142a38"; visible: !navigator.navigating }
        // Offscreen source, not an overlay copy of the interactive app. Qt grabs
        // this subtree for retained cards; the native toplevel is the only source.
        Item {
            id: captureFrame
            x: -width * 2
            width: scene.width; height: scene.height
            Rectangle { anchors.fill: parent; color: "#142a38" }
            Item {
                anchors { fill: parent; topMargin: 32; bottomMargin: 56 + (window.state.keyboardInset || 0) }
                Loader {
                    id: captureLoader
                    anchors.fill: parent
                    // Home/Pi-only and software tests must not initialize an
                    // unused native GPU-capture context.
                    active: window.visible && !!window.toplevel
                    sourceComponent: Item {
                        readonly property bool hasContent: capture.hasContent
                        ScreencopyView {
                            id: capture
                            anchors.centerIn: parent
                            readonly property real fit: sourceSize.width > 0 ? Math.min(parent.width / sourceSize.width, parent.height / sourceSize.height) : 0
                            width: sourceSize.width * fit; height: sourceSize.height * fit
                            captureSource: window.toplevel ? window.toplevel.wayland : null
                            live: window.visible && !navigator.overview
                            paintCursor: false
                        }
                    }
                }
            }
        }
        AppNavigator {
            id: navigator
            anchors { fill: parent; bottomMargin: window.state.keyboardInset || 0 }
            apps: window.history ? window.history.cards() : []
            history: window.history
            activeAppId: window.activeId
            sourceItem: window.contentReady ? captureFrame : null
            blocked: window.blocked || !window.contentReady || !!(window.state.apps && window.state.apps.pending)
            onGestureBegan: window.gestureBegan()
            onHomeRequested: window.homeRequested()
            onAppRequested: (id, label) => window.appRequested(id, label)
            onCloseRequested: id => { overview = false; window.closeRequested(id) }
        }
    }
}
