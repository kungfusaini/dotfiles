import QtQuick

// Original line artwork, drawn locally: no platform fonts or copied assets.
Canvas {
    id: icon
    property string name: "sun"
    property color ink: "white"
    implicitWidth: 28
    implicitHeight: 28
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const c = getContext("2d")
        c.reset()
        c.scale(width / 32, height / 32)
        c.strokeStyle = ink
        c.fillStyle = ink
        c.lineWidth = 2.2
        c.lineCap = "round"
        c.lineJoin = "round"
        function line(x, y, xx, yy) {
            c.beginPath(); c.moveTo(x, y); c.lineTo(xx, yy); c.stroke()
        }
        function circle(x, y, r, fill) {
            c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2)
            if (fill) c.fill(); else c.stroke()
        }
        if (name === "sun") {
            circle(16, 16, 5, false)
            for (let i = 0; i < 8; ++i) {
                const angle = i * Math.PI / 4
                line(16 + Math.cos(angle) * 10, 16 + Math.sin(angle) * 10,
                     16 + Math.cos(angle) * 13, 16 + Math.sin(angle) * 13)
            }
        } else if (name === "volume" || name === "muted") {
            c.beginPath(); c.moveTo(4, 12); c.lineTo(10, 12); c.lineTo(16, 6)
            c.lineTo(16, 26); c.lineTo(10, 20); c.lineTo(4, 20); c.closePath(); c.stroke()
            if (name === "muted") {
                line(22, 12, 29, 20); line(22, 20, 29, 12)
            } else {
                c.beginPath(); c.arc(16, 16, 8, -0.8, 0.8); c.stroke()
                c.beginPath(); c.arc(16, 16, 13, -0.8, 0.8); c.stroke()
            }
        } else if (name === "wifi") {
            for (let i = 0; i < 3; ++i) {
                const inset = i * 4
                c.beginPath(); c.moveTo(4 + inset, 12 + inset)
                c.quadraticCurveTo(16, 2 + inset * 2, 28 - inset, 12 + inset); c.stroke()
            }
            circle(16, 26, 1.5, true)
        } else if (name === "battery") {
            c.strokeRect(3, 9, 23, 14)
            c.fillRect(6, 12, 16, 8)
            line(29, 13, 29, 19)
        } else if (name === "play") {
            c.beginPath(); c.moveTo(11, 6); c.lineTo(27, 16); c.lineTo(11, 26); c.closePath(); c.fill()
        } else if (name === "pause") {
            c.fillRect(8, 6, 6, 20); c.fillRect(19, 6, 6, 20)
        } else if (name === "close") {
            line(9, 9, 23, 23); line(23, 9, 9, 23)
        } else if (name === "power") {
            c.beginPath(); c.arc(16, 17, 11, -1.05, Math.PI + 1.05); c.stroke()
            line(16, 3, 16, 16)
        } else if (name === "music") {
            c.beginPath(); c.moveTo(13, 24); c.lineTo(13, 8); c.lineTo(26, 5); c.lineTo(26, 21); c.stroke()
            c.beginPath(); c.ellipse(3, 21, 10, 6); c.fill()
            c.beginPath(); c.ellipse(16, 18, 10, 6); c.fill()
        }
    }
}
