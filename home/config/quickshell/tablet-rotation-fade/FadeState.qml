import QtQuick

// Non-visual state machine, also exercised by offscreen Qt Quick tests.
Item {
    id: root
    property bool hasScreen: false
    property bool mapped: false
    property string phase: "ready"
    property bool shown: false
    property real level: 0
    property int hardTimeout: 3000
    signal expired()

    function status(): string { return hasScreen ? phase : "unavailable" }
    function cover(): void {
        if (!hasScreen || phase !== "ready")
            return
        phase = "covering"
        shown = true
        watchdog.restart()
        fadeIn.restart()
    }
    function reveal(): void {
        if (phase !== "covered")
            return
        phase = "revealing"
        fadeOut.restart()
    }
    function expire(): void {
        fadeIn.stop()
        fadeOut.stop()
        rendered.stop()
        watchdog.stop()
        cleanup.stop()
        shown = false
        level = 0
        phase = "expired"
        expired()
    }

    // Standalone animations: Qt does NOT emit finished for animations inside
    // Behavior/Transition. The cover handshake depends on these callbacks.
    NumberAnimation {
        id: fadeIn
        target: root
        property: "level"
        from: 0
        to: 1
        duration: 120
        easing.type: Easing.InOutQuad
        onFinished: rendered.restart()
    }
    NumberAnimation {
        id: fadeOut
        target: root
        property: "level"
        from: 1
        to: 0
        duration: 160
        easing.type: Easing.InOutQuad
        onFinished: {
            root.phase = "done"
            root.shown = false
            watchdog.stop()
            cleanup.start()
        }
    }
    Timer {
        id: watchdog
        interval: root.hardTimeout
        running: true
        onTriggered: root.expire()
    }
    Timer {
        id: rendered
        interval: 34
        onTriggered: {
            if (root.mapped && root.hasScreen && root.level >= .999)
                root.phase = "covered"
            else
                restart()
        }
    }
    Timer {
        id: cleanup
        interval: 500
        onTriggered: root.expire()
    }
}
