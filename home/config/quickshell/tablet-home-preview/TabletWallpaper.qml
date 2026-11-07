import QtQuick

// Shared opaque tablet wallpaper; never fall back to the work desktop between views.
Item {
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#172b3c" }
            GradientStop { position: 0.55; color: "#153e46" }
            GradientStop { position: 1; color: "#101c32" }
        }
    }
    Item {
        anchors.fill: parent
        clip: true
        Rectangle {
            width: parent.width * 0.8; height: width; radius: width / 2
            x: parent.width * 0.5; y: parent.height * 0.45
            color: "#16626b"; opacity: 0.25
        }
        Rectangle {
            width: parent.width * 0.7; height: width; radius: width / 2
            x: -width * 0.5; y: -height * 0.65
            color: "#b4d6b2"; opacity: 0.09
        }
    }
}
