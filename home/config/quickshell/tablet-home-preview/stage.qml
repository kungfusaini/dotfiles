import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls

// Stable for the whole tablet lifetime, never replaced with an app scene.
ShellRoot {
    id: stage
    readonly property var targetScreen: Quickshell.screens.find(s => s.name === (Quickshell.env("TABLET_STAGE_SCREEN") || "eDP-1")) ?? null
    property var apps: []
    FileView {
        id: appRegistry
        path: Quickshell.env("TABLET_APPS_REGISTRY") || Qt.resolvedUrl("apps.json").toString().replace(/^file:\/\//, "")
        blockAllReads: true
        onLoaded: stage.loadApps()
    }
    function loadApps() {
        try { apps = JSON.parse(appRegistry.text()).map(app => Object.assign({}, app, {icon: Quickshell.iconPath(app.icon, true)})) }
        catch (_) { apps = [] }
    }
    Component.onCompleted: loadApps()
    property string assetDirectory: Quickshell.env("TABLET_STAGE_ASSETS") || ""
    property real coverLevel: 1
    property string message: "Opening app…"
    onCoverLevelChanged: { if (coverLevel <= 0) coverLoader.active = false }
    Behavior on coverLevel { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    FileView {
        id: owner
        path: "/proc/" + Quickshell.env("TABLET_STAGE_OWNER_PID") + "/stat"
        blockAllReads: true
        printErrors: false
    }
    function ownerAlive() {
        owner.reload()
        const text = owner.text()
        const fields = text.slice(text.lastIndexOf(")") + 1).trim().split(/\s+/)
        return fields[19] === Quickshell.env("TABLET_STAGE_OWNER_START") && fields[0] !== "Z"
    }
    Timer { interval: 500; running: true; repeat: true; onTriggered: { if (!stage.ownerAlive()) Qt.quit() } }
    IpcHandler {
        target: "tabletStage"
        function status(): string {
            const window = coverLoader.item
            return JSON.stringify({cover: !!window && window.ready && stage.coverLevel >= .999,
                backdrop: backdropFrames.rendered && baseHome.status === Loader.Ready, covering: stage.coverLevel > 0,
                coverFrames: window ? window.queuedFrames : 0, baseFrames: backdropFrames.frames,
                screen: stage.targetScreen !== null, coverAssets: window ? window.assetState : 0, baseAssets: baseHome.status})
        }
        function assets(path: string): void {
            if (!path.startsWith("/nix/store/")) throw new Error("Tablet assets must be immutable")
            stage.assetDirectory = path
        }
        function cover(label: string): void {
            stage.message = label
            // A remapped old layer can remain below newer app layers. Create a
            // fresh overlay while the old app still covers the screen.
            coverLoader.active = false
            stage.coverLevel = 1
            coverLoader.active = true
        }
        function reveal(): void { stage.coverLevel = 0 }
    }
    PanelWindow {
        id: base
        visible: stage.targetScreen !== null
        screen: stage.targetScreen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "#172b3c" // Opaque even while live visual assets are reloaded.
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: "tablet-rotation-fade" // Existing deployed no_anim policy.
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        Loader {
            id: baseHome
            anchors.fill: parent
            source: "file://" + stage.assetDirectory + "/TabletHome.qml"
            onLoaded: { item.apps = Qt.binding(() => stage.apps); item.enabled = false }
        }
        FrameWitness { id: backdropFrames; requiredFrames: 1; armed: base.backingWindowVisible }
    }
    LazyLoader {
        id: coverLoader
        active: stage.coverLevel > 0 && stage.targetScreen !== null
        PanelWindow {
            id: cover
            readonly property bool ready: coverFrames.rendered && coverHome.status === Loader.Ready
            readonly property int queuedFrames: coverFrames.frames
            readonly property int assetState: coverHome.status
            property bool showNotice: false
            screen: stage.targetScreen
            visible: stage.coverLevel > 0 && stage.targetScreen !== null
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            color: "transparent"
            surfaceFormat.opaque: false
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: "tablet-rotation-fade"
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            Timer { interval: 500; running: cover.backingWindowVisible; onTriggered: cover.showNotice = true }
            Item {
                anchors.fill: parent
                opacity: stage.coverLevel
                Rectangle { anchors.fill: parent; color: "#172b3c" }
                Loader {
                    id: coverHome
                    anchors.fill: parent
                    source: "file://" + stage.assetDirectory + "/TabletHome.qml"
                    onLoaded: { item.apps = Qt.binding(() => stage.apps); item.enabled = false }
                }
                MouseArea { anchors.fill: parent }
                Label {
                    visible: cover.showNotice
                    anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 120 }
                    text: stage.message
                    color: "#eef5f2"
                    font.pixelSize: 18
                }
                Button {
                    id: cancelButton
                    visible: cover.showNotice
                    anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 56 }
                    width: 160; height: 48
                    text: "Cancel launch"
                    focusPolicy: Qt.NoFocus
                    background: Rectangle { radius: 16; color: cancelButton.down ? "#407385" : "#2a4a5b" }
                    contentItem: Label { text: cancelButton.text; color: "#f2f8f6"; font.pixelSize: 16; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (stage.ownerAlive()) cancel.running = true
                        else Qt.quit()
                    }
                }
            }
            FrameWitness { id: coverFrames; armed: cover.backingWindowVisible && stage.coverLevel >= .999 && coverHome.status === Loader.Ready }
        }
    }
    Process {
        id: cancel
        // Exact PID/start identity is checked immediately before signalling the
        // owning supervisor. No global key injection or desktop focus changes.
        command: ["kill", "-TERM", Quickshell.env("TABLET_STAGE_OWNER_PID")]
        stdout: SplitParser { onRead: data => {} }
        stderr: SplitParser { onRead: data => {} }
    }
}
