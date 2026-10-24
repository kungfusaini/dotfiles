import Quickshell
import Quickshell.Io
import QtQuick
import QtQuick.Controls

ShellRoot {
    id: shell

    readonly property real layoutFactor: Number(Quickshell.env("LAYOUT_FACTOR"))

    function displaysOverlap() {
        return externalDisplay.x < laptopDisplay.x + laptopDisplay.width
            && externalDisplay.x + externalDisplay.width > laptopDisplay.x
            && externalDisplay.y < laptopDisplay.y + laptopDisplay.height
            && externalDisplay.y + externalDisplay.height > laptopDisplay.y
    }

    function snapDisplaysTogether() {
        // Every valid extended layout must share an edge: a gap creates a
        // disconnected desktop island that the pointer cannot enter. Preserve
        // free movement along that edge while requiring a useful overlap in
        // the perpendicular direction.
        const overlap = 20
        const clamp = (value, low, high) => Math.max(low, Math.min(high, value))
        const verticalY = clamp(externalDisplay.y,
            laptopDisplay.y - externalDisplay.height + overlap,
            laptopDisplay.y + laptopDisplay.height - overlap)
        const horizontalX = clamp(externalDisplay.x,
            laptopDisplay.x - externalDisplay.width + overlap,
            laptopDisplay.x + laptopDisplay.width - overlap)
        const choices = [
            { x: laptopDisplay.x - externalDisplay.width, y: verticalY },
            { x: laptopDisplay.x + laptopDisplay.width, y: verticalY },
            { x: horizontalX, y: laptopDisplay.y - externalDisplay.height },
            { x: horizontalX, y: laptopDisplay.y + laptopDisplay.height }
        ]
        let best = choices[0]
        let bestDistance = Infinity
        for (const choice of choices) {
            const distance = Math.pow(choice.x - externalDisplay.x, 2)
                           + Math.pow(choice.y - externalDisplay.y, 2)
            if (distance < bestDistance) {
                best = choice
                bestDistance = distance
            }
        }
        externalDisplay.x = best.x
        externalDisplay.y = best.y
    }

    function applyLayout() {
        snapDisplaysTogether()
        if (displaysOverlap())
            return
        const dx = externalDisplay.x - laptopDisplay.x
        const dy = externalDisplay.y - laptopDisplay.y
        runner.command = [Quickshell.env("DISPLAY_LAYOUT_APPLY"), "custom", dx.toString(), dy.toString(), layoutFactor.toString()]
        runner.running = true
    }

    Process {
        id: runner
        onExited: Qt.quit()
    }

    FloatingWindow {
        id: window
        title: "Display Layout"
        implicitWidth: 760
        implicitHeight: 560
        color: "#101218"

        Rectangle {
            anchors.fill: parent
            color: "#101218"
            radius: 18
            border.width: 1
            border.color: "#343946"

            Text {
                id: heading
                anchors.top: parent.top
                anchors.topMargin: 25
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Arrange displays"
                color: "#f4f4f5"
                font.pixelSize: 27
                font.weight: Font.DemiBold
            }

            Text {
                anchors.top: heading.bottom
                anchors.topMargin: 6
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Drag the external display around the laptop"
                color: "#9299a8"
                font.pixelSize: 15
            }

            Rectangle {
                id: canvas
                width: 690
                height: 370
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: heading.bottom
                anchors.topMargin: 42
                radius: 14
                color: "#151922"
                border.width: 1
                border.color: "#2d3340"
                clip: true

                // Fine grid gives the dragger spatial context without turning
                // it into a full display-settings application.
                Canvas {
                    anchors.fill: parent
                    opacity: 0.24
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.strokeStyle = "#566071"
                        ctx.lineWidth = 1
                        for (let x = 20; x < width; x += 20) {
                            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
                        }
                        for (let y = 20; y < height; y += 20) {
                            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                        }
                    }
                }

                Rectangle {
                    id: laptopDisplay
                    x: Number(Quickshell.env("LAYOUT_INTERNAL_X"))
                    y: Number(Quickshell.env("LAYOUT_INTERNAL_Y"))
                    width: Number(Quickshell.env("LAYOUT_INTERNAL_W"))
                    height: Number(Quickshell.env("LAYOUT_INTERNAL_H"))
                    radius: 9
                    color: "#252b36"
                    border.width: 2
                    border.color: "#7dd3fc"

                    Column {
                        anchors.centerIn: parent
                        spacing: 5
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Laptop"; color: "#f4f4f5"; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "eDP-1"; color: "#9299a8"; font.pixelSize: 12 }
                    }
                }

                Rectangle {
                    id: externalDisplay
                    x: Number(Quickshell.env("LAYOUT_EXTERNAL_X"))
                    y: Number(Quickshell.env("LAYOUT_EXTERNAL_Y"))
                    width: Number(Quickshell.env("LAYOUT_EXTERNAL_W"))
                    height: Number(Quickshell.env("LAYOUT_EXTERNAL_H"))
                    radius: 9
                    color: shell.displaysOverlap() ? "#4a252b" : (dragArea.pressed ? "#29485a" : (dragArea.containsMouse ? "#243b49" : "#202832"))
                    border.width: 2
                    border.color: shell.displaysOverlap() ? "#ff6b6b" : (dragArea.pressed || dragArea.containsMouse ? "#00e5b0" : "#55c9a5")

                    Column {
                        anchors.centerIn: parent
                        spacing: 5
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "External"; color: "#f4f4f5"; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Quickshell.env("LAYOUT_EXTERNAL_NAME") + " · drag me"; color: shell.displaysOverlap() ? "#fca5a5" : "#86efac"; font.pixelSize: 12 }
                    }

                    MouseArea {
                        id: dragArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                        drag.target: externalDisplay
                        drag.axis: Drag.XAndYAxis
                        drag.minimumX: 0
                        drag.maximumX: canvas.width - externalDisplay.width
                        drag.minimumY: 0
                        drag.maximumY: canvas.height - externalDisplay.height
                        onReleased: shell.snapDisplaysTogether()
                    }
                }
            }

            Rectangle {
                id: cancelButton
                width: 110
                height: 42
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 20
                anchors.right: applyButton.left
                anchors.rightMargin: 12
                radius: 9
                color: cancelMouse.containsMouse ? "#2a303b" : "#1d222b"
                border.width: 1
                border.color: "#3b4250"
                Text { anchors.centerIn: parent; text: "Cancel"; color: "#d1d5db"; font.pixelSize: 15 }
                MouseArea { id: cancelMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Qt.quit() }
            }

            Rectangle {
                id: applyButton
                width: 120
                height: 42
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 20
                anchors.right: parent.right
                anchors.rightMargin: 35
                radius: 9
                color: shell.displaysOverlap() ? "#3b4049" : (applyMouse.containsMouse ? "#20b98b" : "#14966f")
                Text { anchors.centerIn: parent; text: shell.displaysOverlap() ? "Separate displays" : "Apply"; color: shell.displaysOverlap() ? "#9ca3af" : "white"; font.pixelSize: 15; font.weight: Font.DemiBold }
                MouseArea { id: applyMouse; anchors.fill: parent; enabled: !shell.displaysOverlap(); hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.applyLayout() }
            }

            Item {
                anchors.fill: parent
                focus: true
                Keys.onEscapePressed: Qt.quit()
            }
        }
    }
}
