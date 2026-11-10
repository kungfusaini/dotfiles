import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Deliberately has no process, compositor, sensor or system-control access.
// The preview host supplies app metadata; gestures and layout are reusable.
Control {
    id: root
    font.family: "DejaVu Sans"
    property var apps: []
    property string modeLabel: "TABLET / PREVIEW"
    property bool settingsExternallyManaged: false
    signal settingsRequested()
    property bool nativePresentation: false
    property bool nativeAppVisible: false
    property string nativeAppId: ""
    property real keyboardInset: 0
    signal nativeHomeRequested()
    readonly property bool navigationContactActive: navigator.contactActive
    readonly property bool navigationVisible: navigator.navigating
    property bool liveClock: true
    property string clockText: Qt.formatTime(new Date(), "hh:mm")
    Timer { interval: 30000; running: root.liveClock; repeat: true; onTriggered: root.clockText = Qt.formatTime(new Date(), "hh:mm") }
    property string activeApp: ""
    property bool settingsOpen: false
    property real settingsProgress: settingsOpen ? 1 : 0
    property real homeProgress: homeVisible ? 1 : 0
    property string displayedApp: ""
    property var history: localHistory
    property alias switcherOpen: navigator.overview
    readonly property bool navigationBusy: navigator.dragging
    property bool navigationBlocked: false
    property bool navigationUrgent: false
    property var appSummary: app => app.id === "tablet-improve" ? "Your Pi conversation" : "Preview · no application launched"
    AppHistory { id: localHistory; apps: root.apps }
    onActiveAppChanged: {
        if (activeApp !== "") {
            displayedApp = activeApp
            const app = apps.find(app => app.label === activeApp)
            if (app) history.open(app.id)
        }
    }
    Behavior on settingsProgress { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
    Behavior on homeProgress { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    property real volume: 45
    property real brightness: 65
    property bool muted: false
    property bool playing: false
    readonly property int gridColumns: Math.max(2, Math.min(6, Math.floor((width - 48) / 144)))
    readonly property bool homeVisible: nativePresentation ? !nativeAppVisible : activeApp === ""
    signal appRequested(string id, string label)
    signal exitRequested()
    signal windowCloseRequested(string id)

    function openApp(id, label) { navigator.leave(() => { navigator.overview = false; root.appRequested(id, label) }) }
    function openSwitcher() { navigator.showSwitcher() }
    function dismissApp(id) { navigator.dismissCard(id) }
    function requestHome() { navigator.goHome() }
    function pullFromCorner(distance) {
        if (distance >= 44) {
            if (settingsExternallyManaged) settingsRequested()
            else settingsOpen = true
        }
    }
    function showHome() {
        navigator.overview = false
        activeApp = ""
        settingsOpen = false
    }
    function dismiss() {
        if (navigator.overview)
            navigator.overview = false
        else if (settingsOpen)
            settingsOpen = false
        else if (!homeVisible)
            navigator.goHome()
        else
            exitRequested()
    }

    focus: true
    Keys.onEscapePressed: dismiss()

    TabletWallpaper {
        anchors.fill: parent
        opacity: root.nativePresentation ? root.homeProgress : 1
        visible: opacity > 0
    }

    RowLayout {
        opacity: (1 - root.settingsProgress) * (root.nativePresentation ? root.homeProgress : 1)
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
        Label { text: root.modeLabel; color: "#a9c9ca"; font.pixelSize: 12; font.letterSpacing: 2 }
        Item { Layout.fillWidth: true }
        Label {
            objectName: "settingsHint"
            text: root.clockText
            color: "#eef5f2"
            Accessible.name: "Drag down from the top-right corner for quick settings"
        }
    }

    ColumnLayout {
        objectName: "homeContent"
        // The non-interactive Home scene is also the app-switcher backdrop.
        opacity: (navigator.navigating ? 1 : root.homeProgress) * (1 - 0.9 * root.settingsProgress)
        scale: 0.97 + 0.03 * root.homeProgress - 0.02 * root.settingsProgress
        visible: opacity > 0
        enabled: root.homeVisible && root.settingsProgress === 0
        anchors { top: parent.top; topMargin: 112; bottom: parent.bottom; bottomMargin: 72; left: parent.left; right: parent.right; margins: 24 }
        spacing: 24
        Label {
            text: "Your time."
            color: "#f0f5ef"
            font.pixelSize: root.width < 600 ? 36 : 48
            font.weight: Font.Light
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            text: "Watch, listen, read, play."
            color: "#b3cdcb"; font.pixelSize: 17
            Layout.alignment: Qt.AlignHCenter
        }
        Flickable {
            objectName: "appScroller"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentHeight: appGrid.height + 24
            boundsBehavior: Flickable.StopAtBounds
            GridLayout {
                id: appGrid
                objectName: "appGrid"
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width, root.gridColumns * 152)
                columns: root.gridColumns
                columnSpacing: 8
                rowSpacing: 22
                Repeater {
                    model: root.apps
                    delegate: Item {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 132
                        Button {
                            id: appButton
                            objectName: "app-" + modelData.id
                            anchors { top: parent.top; horizontalCenter: parent.horizontalCenter }
                            width: 88; height: 88
                            Accessible.name: modelData.label
                            scale: down ? 0.92 : 1
                            Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                            background: Rectangle {
                                radius: 23
                                color: appButton.down ? "#52747b" : "#ffffff"
                                opacity: appButton.down ? 0.5 : 0.12
                                border.color: "#90c9d1d0"; border.width: 1
                                Behavior on color { ColorAnimation { duration: 110 } }
                                Behavior on opacity { NumberAnimation { duration: 110 } }
                            }
                            contentItem: Item {
                                Image {
                                    id: appIcon
                                    anchors.centerIn: parent
                                    width: 58; height: 58
                                    source: modelData.icon || ""
                                    fillMode: Image.PreserveAspectFit
                                    sourceSize: Qt.size(116, 116)
                                }
                                Label {
                                    anchors.centerIn: parent
                                    visible: appIcon.status !== Image.Ready
                                    text: modelData.label.slice(0, 1)
                                    font.pixelSize: 38; color: "#f0f5ef"
                                }
                            }
                            onClicked: root.openApp(modelData.id, modelData.label)
                        }
                        Label {
                            anchors { top: appButton.bottom; topMargin: 10; left: parent.left; right: parent.right }
                            text: modelData.label
                            color: "#f0f5ef"; font.pixelSize: 15
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    AppSurface {
        id: mockSurface
        anchors.fill: parent
        opened: !root.homeVisible && !root.nativePresentation
    ColumnLayout {
        objectName: "appContent"
        opacity: 1 - 0.9 * root.settingsProgress
        scale: 1 - 0.02 * root.settingsProgress
        visible: opacity > 0
        enabled: !root.homeVisible && root.settingsProgress === 0
        anchors.centerIn: parent
        width: Math.min(root.width - 48, 480)
        spacing: 20
        Label {
            text: root.displayedApp
            font.pixelSize: 36; color: "#f0f5ef"
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            text: "App preview — nothing was launched.\nUse the bottom handle to return home.\nDrag down from the top-right corner for settings."
            color: "#b3cdcb"; font.pixelSize: 17
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    }

    AppNavigator {
        id: navigator
        anchors.fill: parent
        visible: root.settingsProgress === 0
        sourceItem: root.nativePresentation || root.homeVisible ? null : mockSurface
        history: root.history
        apps: root.history.cards()
        activeAppId: root.nativePresentation ? (root.nativeAppVisible ? root.nativeAppId : "") : (root.apps.find(app => app.label === root.activeApp) || {}).id || ""
        keyboardInset: root.keyboardInset
        blocked: root.navigationBlocked
        urgentInput: root.navigationUrgent
        summary: root.appSummary
        onHomeRequested: { if (root.nativePresentation) root.nativeHomeRequested(); else root.showHome() }
        onAppRequested: (id, label) => root.appRequested(id, label)
        onCloseRequested: id => {
            const app = root.apps.find(app => app.id === id)
            if (app && app.kind === "window") { root.windowCloseRequested(id); return }
            if (id === activeAppId) { overview = false; root.showHome() }
            root.history.close(id)
        }
    }

    // Only drags STARTING in this corner can summon settings. No tap opener
    // and no full-width touch strip or compositor gesture plugin.
    Item {
        id: topEdge
        objectName: "topRightEdge"
        anchors { right: parent.right; top: parent.top }
        width: Math.min(120, root.width * 0.25)
        height: 28
        enabled: root.settingsProgress === 0 && !navigator.navigating
        DragHandler {
            target: null
            xAxis.enabled: false
            onTranslationChanged: { if (active) root.pullFromCorner(translation.y) }
        }
    }

    Rectangle {
        objectName: "settingsScrim"
        anchors.fill: parent
        visible: root.settingsProgress > 0
        opacity: root.settingsProgress
        color: "#99060e17"
        MouseArea { anchors.fill: parent; onClicked: root.settingsOpen = false }
    }

    ControlCenter {
        id: drawer
        objectName: "settingsDrawer"
        visible: root.settingsProgress > 0
        enabled: root.settingsOpen
        opacity: root.settingsProgress
        anchors { right: parent.right; rightMargin: root.width < 600 ? 16 : 28 }
        y: (root.width < 600 ? 16 : 28) - (1 - root.settingsProgress) * 56
        scale: 0.98 + root.settingsProgress * 0.02
        transformOrigin: Item.TopRight
        width: Math.min(392, root.width - 32)
        height: Math.min(480, root.height - 32)
        volume: root.volume
        brightness: root.brightness
        muted: root.muted
        playing: root.playing
        onVolumeEdited: value => root.volume = value
        onBrightnessEdited: value => root.brightness = value
        onMuteRequested: root.muted = !root.muted
        onPlaybackRequested: root.playing = !root.playing
        onCloseRequested: root.settingsOpen = false
        onExitRequested: root.exitRequested()
    }
}
