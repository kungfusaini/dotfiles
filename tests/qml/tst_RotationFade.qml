import QtQuick
import QtTest
import "../../home/config/quickshell/tablet-rotation-fade" as Fade

TestCase {
    id: testCase
    name: "RotationFadeState"
    when: windowShown

    Component {
        id: stateComponent
        Fade.FadeState { hasScreen: true; mapped: true }
    }
    function makeState(properties) {
        const state = createTemporaryObject(stateComponent, testCase, properties || {})
        verify(state !== null)
        return state
    }
    function test_actual_animation_completes_handshake() {
        const state = makeState()
        compare(state.status(), "ready")
        compare(state.shown, false)
        state.cover()
        compare(state.phase, "covering")
        compare(state.shown, true)
        tryCompare(state, "phase", "covered", 1000)
        compare(state.level, 1)
        state.reveal()
        tryCompare(state, "phase", "done", 1000)
        compare(state.level, 0)
        compare(state.shown, false)
    }
    function test_unmapped_cover_never_acknowledges() {
        const state = makeState({mapped: false, hardTimeout: 300})
        state.cover()
        tryCompare(state, "level", 1, 250)
        compare(state.phase, "covering")
        tryCompare(state, "phase", "expired", 1000)
        compare(state.shown, false)
        state.mapped = true
        wait(100)
        compare(state.phase, "expired")
    }
    function test_missing_monitor_never_shows() {
        const state = makeState({hasScreen: false})
        compare(state.status(), "unavailable")
        state.cover()
        compare(state.shown, false)
        compare(state.level, 0)
    }
    function test_driver_loss_clears_covered_state() {
        const state = makeState({hardTimeout: 450})
        state.cover()
        tryCompare(state, "phase", "covered", 400)
        tryCompare(state, "phase", "expired", 1000)
        compare(state.shown, false)
        compare(state.level, 0)
    }
    function test_timeout_stops_animation_and_late_ack() {
        const state = makeState({hardTimeout: 40})
        state.cover()
        tryCompare(state, "phase", "expired", 500)
        wait(200)
        compare(state.phase, "expired")
        compare(state.shown, false)
        compare(state.level, 0)
    }
    function test_idle_startup_expires_without_drawing() {
        const state = makeState({hardTimeout: 40})
        tryCompare(state, "phase", "expired", 500)
        compare(state.shown, false)
    }
}
