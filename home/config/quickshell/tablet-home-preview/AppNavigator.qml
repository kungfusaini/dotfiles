import QtQuick
import QtQuick.Controls

// In-window scene only: no workspace switching, process launch or global input.
Item {
    id: nav
    objectName: "appNavigator"
    clip: true
    property Item sourceItem: null
    property var apps: []
    property var history: null
    readonly property bool capturing: !!history && history.capturing
    property string activeAppId: ""
    property bool blocked: false
    property real keyboardInset: 0
    property bool urgentInput: false
    property bool overview: false
    property var appAvailable: app => true
    property var appContext: app => null
    property var summary: app => app.id === "tablet-improve" ? "Your Pi conversation" : "Preview · no application launched"
    property bool homeCommitPending: false
    property real committedProgress: 0
    readonly property real progress: overview ? 1 : (homeCommitPending ? committedProgress
        : Math.min(1, gesture.pull / Math.max(120, height * .30)))
    readonly property bool navigating: overview || progress > 0
    readonly property bool dragging: gesture.dragging || capturing || cards.draggingCard
    readonly property bool contactActive: gesture.pressed || gesture.dragging
    // Single geometry source for the layer-shell input mask and visible handle.
    property real navigationWidth: width
    property bool edgeAnchored: false
    property bool externalAppActions: false
    readonly property rect navigationInputRect: Qt.rect(gesture.x, gesture.y, gesture.width, gesture.height)
    readonly property real availableHeight: edgeAnchored ? Math.max(120, height - keyboardInset - gesture.height - 4) : height
    readonly property real cardWidth: Math.min(width * .76, 760)
    readonly property real cardTop: edgeAnchored ? Math.max(52, availableHeight * .15) : height * .15
    readonly property real cardHeight: edgeAnchored
        ? Math.max(80, Math.min(availableHeight * .70, availableHeight - cardTop - 16)) : height * .70
    readonly property int activeIndex: apps.findIndex(app => app.id === activeAppId)
    property var pendingDismissals: ({})
    property int dismissalSerial: 0
    onOverviewChanged: { if (!overview) pendingDismissals = ({}) }
    signal closeRequested(string id, var context, int token)
    signal homeRequested()
    signal appRequested(string id, string label, var context)
    signal gestureBegan()
    signal blockedRequested()
    onBlockedChanged: { if (blocked) gesture.cancel() }
    onUrgentInputChanged: { if (urgentInput) cancelGesture() }
    function cancelGesture() { gesture.cancel(); overview = false }
    function showSwitcher() {
        if (blocked) { blockedRequested(); return }
        if (capturing) return
        if (history) history.capture(activeAppId, sourceItem)
        overview = true
        cards.forceLayout()
        cards.currentIndex = Math.max(0, activeIndex)
        cards.positionViewAtIndex(cards.currentIndex, ListView.Center)
    }
    function leave(action, failed) {
        if (blocked || capturing) { blockedRequested(); if (failed) failed(); return }
        if (history) history.capture(activeAppId, sourceItem, ok => {
            if (ok && !blocked) action()
            else if (failed) failed()
        })
        else action()
    }
    function goHome() {
        // Retaining a real window frame is asynchronous too. Keep the current
        // touch visual until capture hands off to the backend Home request.
        committedProgress = progress
        homeCommitPending = true
        leave(() => { overview = false; homeRequested(); homeCommitPending = false },
              () => { homeCommitPending = false })
    }
    function snapshotContext(id) {
        const value = appContext(apps.find(app => app.id === id) || {})
        return value === null || value === undefined ? null : JSON.parse(JSON.stringify(value))
    }
    function contextCurrent(id, context) {
        return JSON.stringify(snapshotContext(id)) === JSON.stringify(context)
    }
    function resume(id, label, context) {
        const selected = context === undefined ? snapshotContext(id) : context
        if (blocked || capturing || !appAvailable(apps.find(app => app.id === id) || {}) || !contextCurrent(id, selected)) return
        if (id === activeAppId && !externalAppActions) { overview = false; return }
        leave(() => {
            if (!contextCurrent(id, selected)) return
            if (!externalAppActions) overview = false
            appRequested(id, label, selected)
        })
    }
    function finishDismissal(id, token) {
        if (!pendingDismissals[id] || pendingDismissals[id].token !== token) return
        const next = Object.assign({}, pendingDismissals)
        delete next[id]
        pendingDismissals = next
    }
    function dismissCard(id, context) {
        const selected = context === undefined ? snapshotContext(id) : context
        const previous = pendingDismissals[id]
        if (blocked || capturing || (previous && contextCurrent(id, previous.context))
            || !appAvailable(apps.find(app => app.id === id) || {}) || !contextCurrent(id, selected)) return
        const token = ++dismissalSerial
        if (externalAppActions) pendingDismissals = Object.assign({}, pendingDismissals, {[id]: {context: selected, token: token}})
        // Retain the released visual while capture/backend acknowledgement is
        // pending, rather than snapping a successfully swiped card back in.
        const failed = () => finishDismissal(id, token)
        const request = () => {
            if (contextCurrent(id, selected)) closeRequested(id, selected, token)
            else failed()
        }
        if (id === activeAppId) leave(request, failed)
        else request()
    }
    // A new frontend can recapture its current app after handoff. Inactive
    // images intentionally never leave this process or get written to disk.
    Timer {
        interval: 150; repeat: true
        running: nav.visible && nav.overview && !!nav.history && !!nav.sourceItem
            && nav.activeIndex >= 0 && !nav.history.previews[nav.activeAppId]
        onTriggered: { if (!nav.capturing) nav.history.capture(nav.activeAppId, nav.sourceItem) }
    }
    Rectangle {
        anchors.fill: parent
        visible: nav.navigating
        color: "#a5122634"
        MouseArea { anchors.fill: parent; enabled: !nav.blocked; onClicked: { if (nav.overview) nav.goHome() } }
    }
    Label {
        anchors { top: parent.top; topMargin: Math.max(nav.edgeAnchored ? 12 : 20, nav.availableHeight * .05); horizontalCenter: parent.horizontalCenter }
        visible: nav.overview
        text: nav.apps.length ? "Open apps" : "No open apps"
        color: "#eef5f2"; font.family: "DejaVu Sans"; font.pixelSize: 23
    }
    ListView {
        id: cards
        objectName: "appCards"
        x: (nav.width - nav.cardWidth) / 2; y: nav.cardTop
        width: nav.cardWidth; height: nav.cardHeight + 36
        visible: nav.overview
        enabled: !nav.blocked && !nav.capturing
        property bool draggingCard: false
        orientation: ListView.Horizontal
        spacing: 24
        displayMarginBeginning: nav.width
        displayMarginEnd: nav.width
        model: nav.apps
        snapMode: ListView.SnapOneItem
        boundsBehavior: Flickable.StopAtBounds
        clip: false
        delegate: Item {
            id: card
            objectName: "appCard-" + modelData.id
            required property var modelData
            required property int index
            property var pressContext: null
            width: nav.cardWidth; height: nav.cardHeight
            readonly property bool dismissPending: !!nav.pendingDismissals[modelData.id]
                && nav.contextCurrent(modelData.id, nav.pendingDismissals[modelData.id].context)
            transform: Translate {
                y: swipe.active ? Math.min(0, swipe.offset) : (card.dismissPending ? -nav.height : 0)
                Behavior on y { enabled: !swipe.active; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
            opacity: swipe.active ? Math.max(.2, 1 + Math.min(0, swipe.offset) / height) : (dismissPending ? 0 : 1)
            Behavior on opacity { enabled: !swipe.active; NumberAnimation { duration: 180 } }
            DragHandler {
                id: swipe
                target: null
                xAxis.enabled: false
                enabled: nav.overview && !nav.blocked && !nav.capturing && !card.dismissPending && nav.appAvailable(card.modelData)
                property real offset: 0
                property bool cancelled: false
                onActiveTranslationChanged: { if (active) offset = activeTranslation.y }
                onGrabChanged: (transition, point) => {
                    if (transition === PointerDevice.GrabPassive) card.pressContext = nav.snapshotContext(card.modelData.id)
                }
                onCanceled: cancelled = true
                onActiveChanged: {
                    cards.draggingCard = active
                    if (active) { offset = 0; cancelled = false }
                    else if (enabled && !cancelled && offset < -Math.max(80, card.height * .20))
                        nav.dismissCard(card.modelData.id, card.pressContext)
                }
            }
            Label {
                y: 0; height: 30; width: parent.width
                text: modelData.label + (!nav.appAvailable(modelData) ? " · unavailable" : "") + (modelData.kind === "preview" || (!modelData.kind && modelData.id !== "tablet-improve") ? " · Preview" : "")
                textFormat: Text.PlainText
                font.family: "DejaVu Sans"; font.pixelSize: 18; color: "#eef5f2"
            }
            Rectangle {
                y: 34; width: parent.width; height: nav.cardHeight - 34
                radius: 22; color: "#142a38"
                Image {
                    id: retainedPreview
                    objectName: "appPreview-" + modelData.id
                    anchors { fill: parent; margins: 12 }
                    source: nav.history && nav.history.previews[modelData.id] ? nav.history.previews[modelData.id].url : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: false
                    cache: false
                }
                Label {
                    visible: retainedPreview.status !== Image.Ready
                    anchors { fill: parent; margins: 24 }
                    text: nav.summary(modelData)
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    font.family: "DejaVu Sans"; font.pixelSize: 18; color: "#d7e7e2"
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: nav.appAvailable(card.modelData) && !card.dismissPending
                    onPressed: card.pressContext = nav.snapshotContext(card.modelData.id)
                    onClicked: nav.resume(modelData.id, modelData.label, card.pressContext)
                }
            }
        }
    }
    Item {
        id: liveCard
        objectName: "liveAppCard"
        parent: nav
        visible: nav.navigating && !nav.overview && !!nav.sourceItem
        x: nav.overview ? nav.activeIndex * (nav.cardWidth + cards.spacing) : (nav.width - width) / 2
        y: nav.overview ? 34 : (nav.cardTop + 34) * nav.progress
        width: nav.overview ? nav.cardWidth : nav.width * (1 - .24 * nav.progress)
        height: nav.overview ? nav.cardHeight - 34 : nav.height + (nav.cardHeight - 34 - nav.height) * nav.progress
        z: 2
        Behavior on x { enabled: !gesture.dragging && !nav.overview; NumberAnimation { duration: 180 } }
        Behavior on y { enabled: !gesture.dragging && !nav.overview; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on width { enabled: !gesture.dragging && !nav.overview; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on height { enabled: !gesture.dragging && !nav.overview; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Rectangle { anchors.fill: parent; color: "#142a38"; radius: 22 * nav.progress }
        // Inset the live texture inside the rounded frame. No GPU-only mask or
        // screenshot file: software and hardware render the same card contents.
        Item {
            anchors { fill: parent; margins: 12 * nav.progress }
            ShaderEffectSource {
                objectName: "proportionalLivePreview"
                readonly property real fit: nav.sourceItem ? Math.min(parent.width / nav.sourceItem.width, parent.height / nav.sourceItem.height) : 0
                anchors.centerIn: parent
                width: nav.sourceItem ? nav.sourceItem.width * fit : 0
                height: nav.sourceItem ? nav.sourceItem.height * fit : 0
                // Keep the source hidden even when the live card gives way to
                // retained overview images. Home underneath remains the backdrop;
                // the source stays renderable for capture and is restored on resume.
                sourceItem: nav.navigating ? nav.sourceItem : null
                live: true
                hideSource: nav.navigating
            }
        }
        MouseArea {
            anchors.fill: parent
            enabled: nav.overview && !nav.blocked
            onClicked: nav.overview = false
        }
    }
    BottomGesture {
        id: gesture
        width: nav.navigationWidth
        z: 5
        edgeAnchored: nav.edgeAnchored
        anchors { bottom: parent.bottom; bottomMargin: (nav.edgeAnchored ? 0 : 4) + nav.keyboardInset; horizontalCenter: parent.horizontalCenter }
        blocked: nav.blocked
        onBegan: nav.gestureBegan()
        onHomeRequested: nav.goHome()
        onSwitcherRequested: nav.showSwitcher()
        onBlockedRequested: nav.blockedRequested()
    }
}
