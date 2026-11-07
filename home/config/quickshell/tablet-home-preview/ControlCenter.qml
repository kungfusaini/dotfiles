import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Apple Control Center-inspired geometry; original artwork and Qt materials.
// No live system access: every editable value is owned by the preview host.
Item {
    id: panel
    property real volume: 45
    property real brightness: 65
    property bool muted: false
    property bool playing: false
    signal volumeEdited(real value)
    signal brightnessEdited(real value)
    signal muteRequested()
    signal playbackRequested()
    signal closeRequested()
    signal exitRequested()

    component RoundButton: Button {
        id: button
        property string glyph: "close"
        property color glyphColor: "white"
        property color restingColor: "#16ffffff"
        implicitWidth: 48
        implicitHeight: 48
        scale: down ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: width / 2
            color: button.down ? "#45ffffff" : button.restingColor
            border.width: button.visualFocus ? 2 : 1
            border.color: button.visualFocus ? "#f8fbff" : "#20ffffff"
            Behavior on color { ColorAnimation { duration: 100 } }
        }
        contentItem: Item {
            ControlIcon {
                anchors.centerIn: parent
                width: 25; height: 25
                name: button.glyph
                ink: button.glyphColor
            }
        }
    }

    // Keep gaps inside the control cluster from dismissing the scrim.
    MouseArea { anchors.fill: parent }
    Flickable {
        id: scroller
        objectName: "controlScroller"
        anchors.fill: parent
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ColumnLayout {
            id: content
            width: scroller.width
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                ColumnLayout {
                    Layout.leftMargin: 8
                    Layout.fillWidth: true
                    spacing: 3
                    Label { text: "CONTROL CENTRE"; color: "#eff5ff"; font.pixelSize: 11; font.letterSpacing: 1.5 }
                    Label { text: "PREVIEW · SIMULATED"; color: "#bdcddc"; font.pixelSize: 9; font.letterSpacing: 1 }
                }
                RoundButton {
                    objectName: "closeSettings"
                    glyph: "close"
                    Accessible.name: "Close settings"
                    onClicked: panel.closeRequested()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                GlassTile {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 154
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 10
                        RowLayout {
                            spacing: 10
                            Rectangle {
                                width: 44; height: 44; radius: 22
                                color: "#158bff"
                                ControlIcon { anchors.centerIn: parent; name: "wifi"; width: 26; height: 26 }
                            }
                            ColumnLayout {
                                spacing: 2
                                Label { text: "Wi-Fi"; color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold }
                                Label { text: "Connected"; color: "#c5d6e7"; font.pixelSize: 10 }
                            }
                        }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            Layout.fillWidth: true
                            ControlIcon { name: "battery"; width: 24; height: 24; ink: "#d8f4e5" }
                            Label { text: "82%"; color: "#f4f8ff"; font.pixelSize: 15; Layout.fillWidth: true }
                        }
                    }
                }
                GlassTile {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 154
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 9
                            Rectangle {
                                width: 38; height: 38; radius: 12
                                gradient: Gradient {
                                    GradientStop { position: 0; color: "#83a9bf" }
                                    GradientStop { position: 1; color: "#344c70" }
                                }
                                ControlIcon { anchors.centerIn: parent; name: "music"; width: 23; height: 23 }
                            }
                            Label {
                                text: panel.playing ? "Playing" : "Not playing"
                                font.pixelSize: 13; font.weight: Font.DemiBold; color: "white"
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                        Item { Layout.fillHeight: true }
                        RoundButton {
                            objectName: "playPauseButton"
                            Layout.alignment: Qt.AlignHCenter
                            glyph: panel.playing ? "pause" : "play"
                            glyphColor: "#263b51"
                            restingColor: "#edf4fc"
                            Accessible.name: panel.playing ? "Pause" : "Play"
                            onClicked: panel.playbackRequested()
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 218
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: 12
                    Button {
                        id: muteButton
                        objectName: "muteButton"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Accessible.name: panel.muted ? "Unmute" : "Mute"
                        scale: down ? 0.96 : 1
                        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                        background: GlassTile {
                            opacity: muteButton.down ? 0.7 : 1
                            border.color: muteButton.visualFocus ? "#f8fbff" : "#40ffffff"
                        }
                        contentItem: ColumnLayout {
                            spacing: 8
                            ControlIcon {
                                Layout.alignment: Qt.AlignHCenter
                                width: 28; height: 28
                                name: panel.muted ? "muted" : "volume"
                                ink: panel.muted ? "#a7ceff" : "white"
                            }
                            Label {
                                Layout.alignment: Qt.AlignHCenter
                                text: panel.muted ? "Muted" : "Sound on"
                                color: "#f1f6fd"; font.pixelSize: 12
                            }
                        }
                        onClicked: panel.muteRequested()
                    }
                    Button {
                        id: exitButton
                        objectName: "exitPreview"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Accessible.name: "Close preview"
                        scale: down ? 0.96 : 1
                        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                        background: GlassTile {
                            opacity: exitButton.down ? 0.7 : 1
                            border.color: exitButton.visualFocus ? "#f8fbff" : "#40ffffff"
                        }
                        contentItem: ColumnLayout {
                            spacing: 8
                            ControlIcon { Layout.alignment: Qt.AlignHCenter; width: 28; height: 28; name: "power" }
                            Label { Layout.alignment: Qt.AlignHCenter; text: "Close preview"; color: "#f1f6fd"; font.pixelSize: 12 }
                        }
                        onClicked: panel.exitRequested()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: 12
                    PillSlider {
                        objectName: "brightnessSlider"
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        from: 5
                        label: "Brightness"
                        iconName: "sun"
                        value: panel.brightness
                        onMoved: panel.brightnessEdited(value)
                    }
                    PillSlider {
                        objectName: "volumeSlider"
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        label: "Volume"
                        iconName: panel.muted ? "muted" : "volume"
                        value: panel.volume
                        onMoved: panel.volumeEdited(value)
                    }
                }
            }
        }
    }
}
