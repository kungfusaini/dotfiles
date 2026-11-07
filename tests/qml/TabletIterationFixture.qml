import Quickshell
import Quickshell.Wayland

// Isolated compositor fixture: glaring work wallpaper and a normal white app.
ShellRoot {
    PanelWindow {
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "#ff00ff"
        WlrLayershell.layer: WlrLayer.Background
        WlrLayershell.namespace: "test-work-wallpaper"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    }
    PanelWindow {
        anchors { top: true; left: true; right: true }
        implicitHeight: 12
        exclusionMode: ExclusionMode.Ignore
        color: "#ff00ff"
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: "test-desktop-chrome"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    }
    FloatingWindow {
        title: "Test floating Pi"
        implicitWidth: 420
        implicitHeight: 300
        minimumSize: Qt.size(420, 300)
        maximumSize: Qt.size(420, 300)
        color: "#fefefe"
    }
}
