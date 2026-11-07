import QtQuick
import QtQuick.Controls

Slider {
    id: control
    property string iconName: "sun"
    property color iconInk: "#243544"
    property string label: "Brightness"
    implicitWidth: 78
    implicitHeight: 204
    orientation: Qt.Vertical
    padding: 0
    from: 0
    to: 100
    stepSize: 1
    Accessible.name: label
    Accessible.description: Math.round(value) + " percent"
    background: Rectangle {
        id: track
        implicitWidth: 78
        implicitHeight: 204
        radius: 27
        gradient: Gradient {
            GradientStop { position: 0; color: "#99758290" }
            GradientStop { position: 1; color: "#80515d6a" }
        }
        border.color: control.visualFocus ? "#f8fbff" : "#40ffffff"
        border.width: control.visualFocus ? 2 : 1
        Rectangle {
            objectName: "pillFill"
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 1 }
            height: Math.max(0, (track.height - 2) * control.position)
            visible: height > 0
            bottomLeftRadius: 26
            bottomRightRadius: 26
            topLeftRadius: control.position > 0.94 ? 26 : 0
            topRightRadius: control.position > 0.94 ? 26 : 0
            gradient: Gradient {
                GradientStop { position: 0; color: "#ffffff" }
                GradientStop { position: 1; color: "#e0e8f1" }
            }
        }
        ControlIcon {
            anchors { bottom: parent.bottom; bottomMargin: 21; horizontalCenter: parent.horizontalCenter }
            width: 28; height: 28
            name: control.iconName
            // The glyph remains visible even when the fill is below it.
            ink: control.position > 0.26 ? control.iconInk : "#f6f8ff"
        }
        Text {
            anchors { top: parent.top; topMargin: 18; horizontalCenter: parent.horizontalCenter }
            text: Math.round(control.value)
            color: control.position > 0.90 ? "#243544" : "#eef4fb"
            font.family: "DejaVu Sans"
            font.pixelSize: 12
            opacity: control.pressed ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 100 } }
        }
    }
    // The whole pill is the touch target; there is no desktop slider thumb.
    handle: Item { width: 0; height: 0 }
}
