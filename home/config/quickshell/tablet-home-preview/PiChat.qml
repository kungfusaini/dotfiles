import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes

// Native text input: Squeekboard follows the Wayland text-input focus lifecycle.
Control {
    id: chat
    font.family: "DejaVu Sans"
    property var messages: []
    property bool ready: false
    property bool busy: false
    property string activity: ""
    property string notice: ""
    property bool locked: false
    property string error: ""
    property var voice: ({})
    property var question: null
    property bool followOutput: true
    readonly property bool inputActive: composer.activeFocus
    readonly property bool inputPanelActive: (composer.activeFocus && composer.visible && composer.enabled)
        || (!!response && interaction.visible && response.visible && response.enabled && response.activeFocus)
    signal inputPanelRequested()
    readonly property bool voiceActive: !!(voice.recording || voice.transcribing || voice.uncertain || voice.ready)
    property alias draft: composer.text
    property alias cursorPosition: composer.cursorPosition
    signal newChatRequested()
    signal sendRequested(string text)
    signal stopRequested()
    signal homeRequested()
    signal closeRequested()
    signal voiceRequested(string action)
    signal answerRequested(var answer)
    component ActionButton: Button {
        id: button
        implicitWidth: Math.max(72, contentItem.implicitWidth + 28)
        implicitHeight: 48
        property bool preservesInput: true
        focusPolicy: Qt.NoFocus
        background: Rectangle { radius: 14; color: button.down ? "#407385" : "#2a4a5b"; opacity: button.enabled ? 1 : 0.45 }
        contentItem: Label {
            text: button.text; textFormat: Text.PlainText
            color: button.enabled ? "#f2f8f6" : "#8ca6b2"
            font.pixelSize: 16
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
    }

    // An app/window activation must have a non-text focus path. Clearing the
    // nested editor flag also prevents ScrollView from restoring it on remap.
    Item { id: idleFocus; objectName: "chatIdleFocus"; focus: true }
    Component.onCompleted: blurInput()
    function blurInput() {
        composer.focus = false
        if (response) response.focus = false
        idleFocus.forceActiveFocus()
        Qt.inputMethod.hide()
        inputPanelRequested()
    }
    function focusInput() { composer.forceActiveFocus(); Qt.inputMethod.show(); inputPanelRequested() }
    function insertDictation(text) {
        composer.insert(composer.cursorPosition, text)
        focusInput()
    }
    onMessagesChanged: { if (followOutput) Qt.callLater(() => transcript.positionViewAtEnd()) }
    function hit(item, point) {
        if (!item || !item.visible) return false
        return item.contains(item.mapFromItem(chat, point.x, point.y))
    }
    // Passive observation preserves child button presses, scrolling and text
    // selection. Editing/voice actions intentionally retain the editor cursor.
    TapHandler {
        parent: chat
        onTapped: eventPoint => {
            if (chat.hit(composerFrame, eventPoint.position)) return
            for (const child of inputActions.children)
                if (child.preservesInput && chat.hit(child, eventPoint.position)) return
            chat.blurInput()
        }
    }
    onQuestionChanged: { if (question) blurInput() }
    background: Rectangle { color: "#142a38" }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: chat.width < 600 ? 14 : 24
        anchors.bottomMargin: (chat.width < 600 ? 14 : 24) + 52
        spacing: 12
        Item {
            Layout.fillWidth: true
            implicitHeight: 48
            ActionButton {
                id: homeButton
                anchors.left: parent.left
                height: 48
                text: "Home"
                enabled: !chat.locked
                onClicked: { chat.blurInput(); chat.homeRequested() }
            }
            ColumnLayout {
                visible: chat.width >= 500
                anchors { left: homeButton.right; leftMargin: 12; right: newButton.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 2
                Label { text: "Pi"; color: "#f1f6f5"; font.pixelSize: 25; font.weight: Font.DemiBold }
                Label { text: "Tablet workspace"; color: "#a3c0c9"; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
            }
            ActionButton {
                id: newButton
                objectName: "chatNew"
                anchors { right: closeButton.left; rightMargin: 8 }
                height: 48
                text: "New chat"
                enabled: chat.ready && !chat.locked && !chat.voiceActive
                ToolTip.text: chat.voiceActive ? "Finish or cancel dictation first" : "Start a fresh conversation"
                ToolTip.visible: hovered
                onClicked: chat.newChatRequested()
            }
            ActionButton {
                id: closeButton
                anchors.right: parent.right
                height: 48
                text: "Exit tablet"
                Accessible.name: "Exit tablet and return to laptop"
                enabled: !chat.locked
                onClicked: { chat.blurInput(); chat.closeRequested() }
            }
        }
        ListView {
            id: transcript
            objectName: "chatMessages"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10
            model: chat.messages
            onMovementStarted: { chat.followOutput = false; chat.blurInput() }
            onMovementEnded: chat.followOutput = atYEnd
            delegate: Rectangle {
                required property var modelData
                width: transcript.width
                height: modelData.text ? message.implicitHeight + 28 : 0
                visible: !!modelData.text
                radius: 18
                color: modelData.role === "user" ? "#274d63" : "#1b3545"
                Label {
                    id: message
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                    text: modelData.text
                    // Plain text prevents remote images/HTML fetching from replies.
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    font.pixelSize: 17
                    color: "#eff5f5"
                }
            }
            Label {
                anchors.centerIn: parent
                visible: chat.messages.length === 0
                text: "What would you like to change?"
                color: "#9ebbc6"; font.pixelSize: 19
            }
            // Flickable filters pointer delivery; observe its taps locally as
            // well as the root's otherwise uncovered margins/header.
            TapHandler { onTapped: chat.blurInput() }
        }
        Label {
            Layout.fillWidth: true
            visible: !!(chat.error || chat.busy || chat.notice)
            text: chat.error || chat.notice || chat.activity || "Pi is working…"
            textFormat: Text.PlainText
            color: chat.error ? "#ffb9af" : "#b4cfda"
            wrapMode: Text.Wrap
            font.pixelSize: 13
        }
        Rectangle {
            id: composerFrame
            Layout.fillWidth: true
            implicitHeight: Math.min(144, Math.max(64, composer.contentHeight + 28))
            color: "#233f50"
            radius: 18
            border.width: composer.activeFocus ? 2 : 1
            border.color: composer.activeFocus ? "#83cdd0" : "#3d5b6c"
            TapHandler { onTapped: chat.focusInput() }
            ScrollView {
                anchors.fill: parent
                anchors.margins: 8
                TextArea {
                    id: composer
                    objectName: "chatComposer"
                    enabled: !chat.locked
                    placeholderText: "Message Pi…"
                    color: "#f4f8f6"
                    placeholderTextColor: "#aac0ca"
                    wrapMode: TextEdit.Wrap
                    font.pixelSize: 18
                    background: null
                    selectByMouse: true
                    onActiveFocusChanged: {
                        if (activeFocus) Qt.inputMethod.show()
                        else Qt.inputMethod.hide()
                        chat.inputPanelRequested()
                    }
                }
            }
        }
        Flow {
            id: inputActions
            objectName: "chatInputActions"
            Layout.fillWidth: true
            spacing: 8
            ActionButton {
                objectName: "chatMic"
                height: 48; focusPolicy: Qt.NoFocus
                Accessible.name: "Start dictation"
                ToolTip.text: "Start dictation"
                ToolTip.visible: hovered
                contentItem: Item {
                    implicitWidth: 24
                    implicitHeight: 24
                    Shape {
                        objectName: "chatMicIcon"
                        anchors.centerIn: parent
                        width: 24; height: 24
                        ShapePath {
                            strokeColor: "#f2f8f6"
                            strokeWidth: 2
                            fillColor: "transparent"
                            capStyle: ShapePath.RoundCap
                            joinStyle: ShapePath.RoundJoin
                            PathSvg { path: "M 12 2 C 10.34 2 9 3.34 9 5 L 9 11 C 9 12.66 10.34 14 12 14 C 13.66 14 15 12.66 15 11 L 15 5 C 15 3.34 13.66 2 12 2 Z M 5 10 L 5 11 C 5 14.87 8.13 18 12 18 C 15.87 18 19 14.87 19 11 L 19 10 M 12 18 L 12 22 M 8 22 L 16 22" }
                        }
                    }
                }
                visible: chat.inputActive && !chat.voiceActive && !chat.locked
                onClicked: chat.voiceRequested("mic")
            }
            Label {
                text: chat.voice.uncertain ? "Voice needs attention" : chat.voice.recording ? "● Recording" : "Transcribing…"
                visible: !!(chat.voice.uncertain || chat.voice.recording || chat.voice.transcribing)
                color: "#ffb9af"; height: 48; verticalAlignment: Text.AlignVCenter
            }
            ActionButton { text: "Stop recording"; height: 48; focusPolicy: Qt.NoFocus; visible: !!chat.voice.recording; onClicked: chat.voiceRequested("stop") }
            ActionButton { text: "Use dictation"; height: 48; focusPolicy: Qt.NoFocus; visible: !!chat.voice.ready; enabled: !chat.locked; onClicked: chat.voiceRequested("insert") }
            ActionButton { text: "Cancel voice"; height: 48; focusPolicy: Qt.NoFocus; visible: chat.voiceActive; onClicked: chat.voiceRequested("cancel") }
            ActionButton {
                objectName: "chatSend"
                text: chat.busy ? "Stop reply" : "Send"
                height: 48; focusPolicy: Qt.NoFocus
                enabled: !chat.locked && (chat.busy || (chat.ready && !!composer.text.trim() && !chat.question))
                onClicked: {
                    if (chat.busy) chat.stopRequested()
                    else { chat.followOutput = true; chat.sendRequested(composer.text) }
                }
            }
        }
    }
    Dialog {
        id: interaction
        anchors.centerIn: parent
        width: Math.min(480, chat.width - 24)
        modal: true
        enabled: !chat.locked
        title: chat.question ? chat.question.title || "Pi asks" : ""
        visible: chat.question !== null
        closePolicy: Popup.CloseOnEscape
        Overlay.onPressed: chat.blurInput()
        header: Label {
            objectName: "piDialogHeader"
            text: interaction.title; textFormat: Text.PlainText; padding: 16; wrapMode: Text.Wrap
            TapHandler { onTapped: chat.blurInput() }
        }
        contentItem: ColumnLayout {
            id: dialogContent
            TapHandler {
                onTapped: eventPoint => {
                    const point = response.mapFromItem(dialogContent, eventPoint.position.x, eventPoint.position.y)
                    if (!response.visible || !response.contains(point)) chat.blurInput()
                }
            }
            Label { text: chat.question ? chat.question.message || "" : ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ComboBox {
                id: choice
                visible: !!chat.question && chat.question.method === "select"
                model: chat.question ? chat.question.options || [] : []
                contentItem: Label { text: choice.displayText; textFormat: Text.PlainText; padding: 8 }
                delegate: ItemDelegate {
                    required property string modelData
                    contentItem: Label { text: parent.modelData; textFormat: Text.PlainText }
                }
                Layout.fillWidth: true
            }
            TextArea {
                id: response
                objectName: "piDialogResponse"
                visible: !!chat.question && (chat.question.method === "input" || chat.question.method === "editor")
                text: chat.question ? chat.question.prefill || "" : ""
                onActiveFocusChanged: chat.inputPanelRequested()
                placeholderText: chat.question ? chat.question.placeholder || "" : ""
                wrapMode: TextEdit.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                ActionButton { objectName: "piDialogCancel"; text: "Cancel"; onClicked: chat.answerRequested({cancelled: true}) }
                ActionButton {
                    objectName: "piDialogAccept"
                    text: "OK"
                    onClicked: {
                        const q = chat.question
                        if (!q) return
                        chat.answerRequested(q.method === "confirm" ? {confirmed: true} : {value: q.method === "select" ? choice.currentText : response.text})
                    }
                }
            }
        }
        onRejected: chat.answerRequested({cancelled: true})
    }
}
