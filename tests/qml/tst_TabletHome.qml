import QtQuick
import QtTest
import "../../home/config/quickshell/tablet-home-preview" as Tablet

TestCase {
    id: testCase
    name: "TabletHomePreview"
    when: windowShown
    visible: true
    width: 1100
    height: 960
    Component {
        id: surfaceComponent
        Tablet.TabletHome {
            liveClock: false
            clockText: "20:45"
            apps: [
                { id: "browser", label: "Browser" },
                { id: "music", label: "Music" },
                { id: "videos", label: "Videos" },
                { id: "games", label: "Games" },
                { id: "reading", label: "Reading" },
                { id: "steam", label: "Steam" }
            ]
        }
    }
    Component { id: signalSpyComponent; SignalSpy {} }
    Component { id: tileComponent; Tablet.GlassTile { width: 180; height: 100 } }
    Component { id: controlsComponent; Tablet.ControlCenter { width: 392; height: 480 } }
    function test_native_control_center_hides_exit_without_changing_preview_default() {
        const controls = createTemporaryObject(controlsComponent, testCase)
        const exit = findChild(controls, "exitPreview")
        compare(exit.visible, true)
        controls.live = true
        controls.showExit = false
        compare(exit.visible, false)
    }
    function test_native_home_animates_without_mock_app_and_uses_original_touch_navigation() {
        const surface = makeSurface()
        surface.nativePresentation = true
        surface.nativeAppId = "browser"
        surface.nativeAppVisible = true
        surface.history.open("browser")
        tryCompare(surface, "homeProgress", 0)
        compare(surface.homeVisible, false)
        compare(surface.activeApp, "") // no mock app rendering
        const homeSpy = createTemporaryObject(signalSpyComponent, testCase, {target: surface, signalName: "nativeHomeRequested"})
        surface.keyboardInset = 240
        const handle = findChild(surface, "homeHandle")
        compare(handle.mapToItem(surface, 0, handle.height).y, surface.height - 244)
        const sequence = touchEvent(handle)
        sequence.press(0, handle, 70, 24).commit()
        tryCompare(surface, "navigationContactActive", true)
        sequence.move(0, handle, 70, 4).commit()
        wait(25)
        sequence.move(0, handle, 70, -90).commit()
        wait(25)
        sequence.release(0, handle, 70, -90).commit()
        tryCompare(homeSpy, "count", 1)
        compare(surface.nativeAppVisible, true) // backend owns the state
        surface.nativeAppVisible = false
        wait(50)
        verify(surface.homeProgress > 0 && surface.homeProgress < 1)
        tryCompare(surface, "homeProgress", 1)
        surface.openSwitcher()
        compare(surface.switcherOpen, true)
        compare(surface.history.cards()[0].id, "browser")
    }
    function test_native_settings_delegates_without_changing_simulated_values() {
        const surface = makeSurface()
        surface.settingsExternallyManaged = true
        const spy = createTemporaryObject(signalSpyComponent, testCase, {target: surface, signalName: "settingsRequested"})
        surface.pullFromCorner(44)
        compare(spy.count, 1)
        compare(surface.settingsOpen, false)
    }
    function test_glass_tile_has_no_decorative_line_overlay() {
        const tile = createTemporaryObject(tileComponent, testCase)
        verify(tile !== null)
        compare(tile.children.length, 0)
    }
    function makeSurface(width, height) {
        const surface = createTemporaryObject(surfaceComponent, testCase, {
            width: width || 1100, height: height || 760
        })
        verify(surface !== null)
        wait(40)
        return surface
    }
    function openSettings(surface) {
        surface.settingsOpen = true
        tryCompare(surface, "settingsProgress", 1, 1000)
    }
    function dragFrom(surface, x, distance) {
        mousePress(surface, x, 8)
        mouseMove(surface, x, 24, 30)
        mouseMove(surface, x, 8 + distance, 30)
        mouseRelease(surface, x, 8 + distance)
    }
    function test_render_landscape_portrait_and_settings() {
        const surface = makeSurface()
        grabImage(surface).save("landscape.png")
        surface.width = 600
        surface.height = 960
        wait(40)
        grabImage(surface).save("portrait.png")
        openSettings(surface)
        grabImage(surface).save("settings.png")
        surface.width = 360
        surface.height = 480
        wait(40)
        grabImage(surface).save("narrow-settings.png")
    }
    function test_home_is_icons_only() {
        const surface = makeSurface()
        compare(surface.homeVisible, true)
        compare(surface.settingsOpen, false)
        compare(surface.gridColumns, 6)
        verify(findChild(surface, "app-browser") !== null)
        compare(findChild(surface, "dock"), null)
        compare(findChild(surface, "settingsButton"), null)
    }
    function test_portrait_and_narrow_layout() {
        for (const size of [[600, 960], [360, 480]]) {
            const surface = makeSurface(size[0], size[1])
            verify(surface.gridColumns >= 2)
            verify(findChild(surface, "appGrid").width <= surface.width)
            openSettings(surface)
            const drawer = findChild(surface, "settingsDrawer")
            verify(drawer.width <= surface.width)
            verify(drawer.height <= surface.height)
            verify(drawer.x >= 0)
            verify(drawer.y >= 0)
        }
    }
    function test_short_pull_does_not_open() {
        const surface = makeSurface()
        surface.pullFromCorner(30)
        compare(surface.settingsOpen, false)
        surface.pullFromCorner(44)
        compare(surface.settingsOpen, true)
    }
    function test_only_top_right_mouse_drag_opens() {
        for (const width of [1100, 600, 360]) {
            const surface = makeSurface(width, 760)
            for (const x of [20, width / 2, width - Math.min(120, width * 0.25) - 10]) {
                dragFrom(surface, x, 100)
                compare(surface.settingsOpen, false)
            }
            mouseClick(surface, width - 30, 10)
            mouseClick(findChild(surface, "settingsHint"))
            compare(surface.settingsOpen, false)
            dragFrom(surface, width - 30, 25)
            compare(surface.settingsOpen, false)
            dragFrom(surface, width - 30, 100)
            tryCompare(surface, "settingsOpen", true)
        }
    }
    function test_top_right_touch_swipe_opens_drawer() {
        const surface = makeSurface()
        const edge = findChild(surface, "topRightEdge")
        const sequence = touchEvent(edge)
        sequence.press(0, edge, 40, 8).commit()
        wait(30)
        sequence.move(0, edge, 40, 35).commit()
        wait(30)
        sequence.move(0, edge, 40, 110).commit()
        wait(30)
        sequence.release(0, edge, 40, 110).commit()
        tryCompare(surface, "settingsOpen", true)
    }
    function test_touch_from_top_left_does_not_open() {
        const surface = makeSurface()
        const sequence = touchEvent(surface)
        sequence.press(0, surface, 20, 8).commit()
        wait(30)
        sequence.move(0, surface, 20, 40).commit()
        wait(30)
        sequence.move(0, surface, 20, 120).commit()
        wait(30)
        sequence.release(0, surface, 20, 120).commit()
        compare(surface.settingsOpen, false)
    }
    function test_drawer_animates_both_directions_and_survives_reversal() {
        const surface = makeSurface()
        surface.settingsOpen = true
        wait(60)
        verify(surface.settingsProgress > 0 && surface.settingsProgress < 1)
        const drawer = findChild(surface, "settingsDrawer")
        const y = drawer.y
        tryCompare(surface, "settingsProgress", 1, 1000)
        verify(drawer.y > y)
        surface.settingsOpen = false
        wait(60)
        verify(surface.settingsProgress > 0 && surface.settingsProgress < 1)
        compare(drawer.enabled, false)
        surface.settingsOpen = true
        tryCompare(surface, "settingsProgress", 1, 1000)
        surface.settingsOpen = false
        tryCompare(surface, "settingsProgress", 0, 1000)
        compare(drawer.visible, false)
        compare(findChild(surface, "settingsScrim").visible, false)
    }
    function test_icon_press_and_home_app_transition() {
        const surface = makeSurface()
        const app = findChild(surface, "app-browser")
        mousePress(app)
        wait(50)
        verify(app.scale < 1 && app.scale > 0.92)
        mouseRelease(app)
        tryCompare(app, "scale", 1, 1000)
        surface.activeApp = "Browser"
        wait(50)
        verify(surface.homeProgress > 0 && surface.homeProgress < 1)
        tryCompare(surface, "homeProgress", 0, 1000)
        compare(findChild(surface, "homeContent").enabled, false)
        mouseClick(findChild(surface, "homeHandle"))
        tryCompare(surface, "homeProgress", 1, 1000)
        tryCompare(findChild(surface, "appContent"), "visible", false)
    }
    function test_app_activation_is_signal_only() {
        const surface = makeSurface()
        const spy = createTemporaryObject(signalSpyComponent, testCase, { target: surface, signalName: "appRequested" })
        mouseClick(findChild(surface, "app-browser"))
        compare(spy.count, 1)
        compare(spy.signalArguments[0][0], "browser")
        compare(surface.activeApp, "")
    }
    function test_simulated_controls_and_scrim() {
        const surface = makeSurface()
        openSettings(surface)
        mouseClick(findChild(surface, "muteButton"))
        compare(surface.muted, true)
        mouseClick(findChild(surface, "playPauseButton"))
        compare(surface.playing, true)
        const slider = findChild(surface, "volumeSlider")
        compare(slider.orientation, Qt.Vertical)
        mouseClick(slider, slider.width / 2, slider.height * 0.2)
        verify(surface.volume > 60)
        mouseClick(findChild(surface, "settingsScrim"), 20, 400)
        compare(surface.settingsOpen, false)
    }
    function test_brightness_and_settings_do_not_leak_app_input() {
        const surface = makeSurface()
        const spy = createTemporaryObject(signalSpyComponent, testCase, { target: surface, signalName: "appRequested" })
        openSettings(surface)
        const slider = findChild(surface, "brightnessSlider")
        compare(slider.orientation, Qt.Vertical)
        mouseClick(slider, slider.width / 2, slider.height * 0.7)
        verify(surface.brightness < 45)
        compare(spy.count, 0)
        mouseClick(findChild(surface, "closeSettings"))
        const brightness = surface.brightness
        openSettings(surface)
        compare(surface.brightness, brightness)
    }
    function test_vertical_pills_have_touch_targets_and_keyboard_support() {
        for (const width of [1100, 600, 360]) {
            const surface = makeSurface(width, 480)
            openSettings(surface)
            for (const name of ["volumeSlider", "brightnessSlider"]) {
                const slider = findChild(surface, name)
                verify(slider.width >= 48)
                verify(slider.height >= 180)
                const value = slider.value
                slider.forceActiveFocus()
                keyClick(Qt.Key_Up)
                verify(slider.value > value)
            }
            verify(findChild(surface, "homeContent").opacity < 0.15)
        }
    }
    function test_pill_touch_drag_updates_volume_without_scrolling() {
        const surface = makeSurface(360, 480)
        openSettings(surface)
        const slider = findChild(surface, "volumeSlider")
        const scroller = findChild(surface, "controlScroller")
        const y = scroller.contentY
        const x = slider.width / 2
        const sequence = touchEvent(slider)
        sequence.press(0, slider, x, slider.height * 0.75).commit()
        wait(30)
        sequence.move(0, slider, x, slider.height * 0.5).commit()
        wait(30)
        sequence.move(0, slider, x, slider.height * 0.2).commit()
        wait(30)
        sequence.release(0, slider, x, slider.height * 0.2).commit()
        verify(surface.volume > 65)
        compare(scroller.contentY, y)
    }
    function test_pill_endpoints_and_simulated_bindings() {
        const surface = makeSurface()
        openSettings(surface)
        const volume = findChild(surface, "volumeSlider")
        const brightness = findChild(surface, "brightnessSlider")
        mouseClick(volume, volume.width / 2, 1)
        compare(surface.volume, 100)
        mouseClick(volume, volume.width / 2, volume.height - 1)
        compare(surface.volume, 0)
        mouseClick(brightness, brightness.width / 2, brightness.height - 1)
        compare(surface.brightness, 5)
        surface.volume = 72
        compare(volume.value, 72)
        const spy = createTemporaryObject(signalSpyComponent, testCase, { target: surface, signalName: "exitRequested" })
        mouseClick(findChild(surface, "exitPreview"))
        compare(spy.count, 1)
    }
    function test_bottom_touch_swipe_returns_home() {
        const surface = makeSurface()
        surface.activeApp = "Videos"
        const handle = findChild(surface, "homeHandle")
        const sequence = touchEvent(handle)
        sequence.press(0, handle, 70, 40).commit()
        wait(30)
        sequence.move(0, handle, 70, 10).commit()
        wait(30)
        sequence.move(0, handle, 70, -60).commit()
        wait(30)
        sequence.release(0, handle, 70, -60).commit()
        tryCompare(surface, "homeVisible", true)
    }
    function test_escape_closes_settings_then_returns_home_then_exits() {
        const surface = makeSurface()
        surface.activeApp = "Videos"
        openSettings(surface)
        surface.forceActiveFocus()
        keyClick(Qt.Key_Escape)
        compare(surface.settingsOpen, false)
        compare(surface.activeApp, "Videos")
        keyClick(Qt.Key_Escape)
        tryCompare(surface, "homeVisible", true) // Preview capture finishes before unmapping.
        const spy = createTemporaryObject(signalSpyComponent, testCase, { target: surface, signalName: "exitRequested" })
        keyClick(Qt.Key_Escape)
        compare(spy.count, 1)
    }
}
