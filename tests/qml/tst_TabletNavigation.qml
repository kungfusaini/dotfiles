import QtQuick
import QtTest
import "../../home/config/quickshell/tablet-home-preview" as Tablet

TestCase {
    id: suite
    name: "TabletNavigation"
    when: windowShown
    visible: true
    width: 1000; height: 760
    Component { id: gestureComponent; Tablet.BottomGesture {} }
    Component { id: spyComponent; SignalSpy {} }
    Component { id: historyComponent; Tablet.AppHistory { apps: [{id:"tablet-improve",label:"Pi"},{id:"music",label:"Music"}] } }
    Component {
        id: deckComponent
        Item {
            id: deck
            width: 900; height: 700
            property alias navigator: nav
            property alias history: history
            property alias surface: app
            Tablet.AppHistory {
                id: history
                apps: [{id:"tablet-improve",label:"Pi"},{id:"music",label:"Music"}]
                opened: ["tablet-improve", "music"]
            }
            Rectangle { anchors.fill: parent; color: "#00ff00" } // Read-only Home behind the app.
            Rectangle {
                id: app; anchors.fill: parent; color: "#142a38"
                Rectangle { anchors.centerIn: parent; width: 120; height: 120; color: "#ff0000" }
                Text { x: 20; y: 20; text: "Live Pi content"; color: "white" }
            }
            Tablet.AppNavigator {
                id: nav; anchors.fill: parent; sourceItem: app; activeAppId: "tablet-improve"; history: deck.history
                apps: [{id:"tablet-improve",label:"Pi"},{id:"music",label:"Music"}]
            }
        }
    }
    function spy(target, name) { return createTemporaryObject(spyComponent, suite, {target:target,signalName:name}) }
    function test_quick_slow_pause_cancel_and_blocked_classification() {
        const g = createTemporaryObject(gestureComponent, suite)
        const home = spy(g,"homeRequested"), overview = spy(g,"switcherRequested")
        g.begin(); g.move(130); g.finish(g.startedAt + 160)
        compare(home.count,1); compare(overview.count,0)
        g.begin(); g.move(130); g.finish(g.startedAt + 600)
        compare(home.count,1); compare(overview.count,1)
        g.begin(); g.move(130); g.pause(g.startedAt + 600); g.finish(g.startedAt + 700)
        compare(overview.count,2) // Hold and release must not act twice.
        g.begin(); g.move(20); g.finish(g.startedAt + 160)
        compare(home.count,1)
        g.begin(); g.move(130); g.cancel(); g.finish(g.startedAt + 600)
        compare(overview.count,2)
        g.begin(); g.move(130); g.blocked=true; g.finish(g.startedAt + 160)
        compare(home.count,1)
    }
    function test_pointer_flick_and_hold_use_the_same_handle() {
        const deck = createTemporaryObject(deckComponent,suite)
        const nav = deck.navigator
        const home = spy(nav,"homeRequested")
        const handle = findChild(nav,"homeHandle")
        mousePress(handle,90,26)
        mouseMove(handle,90,2,15)
        mouseMove(handle,90,-110,20)
        mouseRelease(handle,90,-110)
        tryCompare(home,"count",1)
        mousePress(handle,90,26)
        mouseMove(handle,90,2,25)
        mouseMove(handle,90,-110,50)
        wait(400)
        tryCompare(nav,"overview",true)
        mouseRelease(handle,90,-110)
        compare(home.count,1)
        grabImage(deck).save("switcher.png")
    }
    function test_pointer_horizontal_card_swipe_and_resume() {
        const deck = createTemporaryObject(deckComponent,suite)
        const nav = deck.navigator
        const resumed = spy(nav,"appRequested")
        nav.showSwitcher(); wait(100)
        const cards = findChild(nav,"appCards"), before = cards.contentX
        mousePress(nav,650,350)
        for (const x of [600,540,480,400,300,200,100]) mouseMove(nav,x,350,30)
        mouseRelease(nav,100,350)
        wait(500)
        tryVerify(() => cards.contentX > before + 80)
        wait(400)
        mouseClick(nav,450,350)
        tryCompare(resumed,"count",1)
        verify(!nav.overview)
    }
    function test_touch_hold_horizontal_cards_and_resume() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        const resumed = spy(nav,"appRequested"), home = spy(nav,"homeRequested")
        const handle = findChild(nav,"homeHandle"), seq = touchEvent(handle)
        seq.press(0,handle,450,26).commit(); wait(30)
        seq.move(0,handle,450,2).commit(); wait(30)
        seq.move(0,handle,450,-130).commit(); wait(400)
        tryCompare(nav,"overview",true)
        seq.release(0,handle,450,-130).commit(); wait(100)
        compare(home.count,0)
        const cards = findChild(nav,"appCards"), before = cards.contentX
        const swipe = touchEvent(nav)
        swipe.press(0,nav,650,350).commit(); wait(30)
        for (const x of [600,540,480,400,300,200,100]) { swipe.move(0,nav,x,350).commit(); wait(30) }
        swipe.release(0,nav,100,350).commit()
        tryVerify(() => cards.contentX > before + 80)
        wait(500)
        swipe.press(0,nav,450,350).commit(); wait(30)
        swipe.release(0,nav,450,350).commit()
        tryCompare(resumed,"count",1)
    }
    Component { id: homeComponent; Tablet.TabletHome { apps: [{id:"music",label:"Music"}] } }
    function test_clock_remains_without_pull_down_wording() {
        const home=createTemporaryObject(homeComponent,suite,{width:900,height:700,liveClock:false,clockText:"12:34"})
        compare(findChild(home,"settingsHint").text,"12:34")
    }
    function test_home_switcher_alias_and_reversible_update_lock() {
        const home = createTemporaryObject(homeComponent,suite,{width:900,height:700})
        home.activeApp="Music"; home.showHome(); home.switcherOpen=true
        verify(home.switcherOpen)
        home.navigationBlocked=true
        verify(home.switcherOpen) // Update lock freezes, not discards, the switcher.
        home.navigationUrgent=true
        verify(!home.switcherOpen)
    }
    function test_switcher_hides_app_background_and_restores_it_on_resume() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        deck.surface.color = "#cc0000"
        wait(50)
        compare(grabImage(deck).red(20,200),204)
        nav.showSwitcher()
        tryCompare(deck.history,"capturing",false)
        wait(50)
        const overview = grabImage(deck)
        verify(overview.green(20,200) > 90, "Home must be visible outside the cards")
        verify(overview.red(20,200) < 30, "Full-size app must not bleed behind the switcher")
        const preview = findChild(nav,"appPreview-tablet-improve")
        tryCompare(preview,"status",Image.Ready)
        const point = preview.mapToItem(deck,preview.width / 2,preview.height * .25)
        verify(overview.red(Math.floor(point.x),Math.floor(point.y)) > 180, "App must remain inside its card")
        overview.save("switcher-home-backdrop.png")
        nav.resume("tablet-improve","Pi")
        wait(50)
        compare(grabImage(deck).red(20,200),204)
        verify(!nav.overview)
    }
    function test_mock_switcher_reveals_home_content_without_enabling_it() {
        const home = createTemporaryObject(homeComponent,suite,{width:900,height:700})
        home.activeApp = "Music"
        wait(250)
        const content = findChild(home,"homeContent")
        compare(content.opacity,0)
        home.openSwitcher()
        tryCompare(home.history,"capturing",false)
        compare(content.opacity,1)
        verify(!content.enabled)
        home.openApp("music","Music")
        tryCompare(home,"switcherOpen",false)
        compare(home.activeApp,"Music")
        compare(content.opacity,0)
    }
    function test_proportional_previews_survive_other_apps_and_home() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        nav.showSwitcher()
        tryCompare(deck.history,"capturing",false)
        tryVerify(() => !!deck.history.previews["tablet-improve"])
        const piUrl = String(deck.history.previews["tablet-improve"].url)
        const preview = findChild(nav,"appPreview-tablet-improve")
        tryCompare(preview,"status",Image.Ready)
        verify(Math.abs(preview.paintedWidth / preview.paintedHeight - deck.width / deck.height) < .001)
        wait(100)
        const image = grabImage(deck)
        const center = preview.mapToItem(deck,preview.width / 2,preview.height / 2)
        const cx = Math.floor(center.x), cy = Math.floor(center.y)
        compare(image.red(cx,cy),255)
        compare(image.green(cx,cy),0)
        let redWidth = 0, redHeight = 0
        for (let x = 0; x < image.width; x++) if (image.red(x,cy) === 255 && image.green(x,cy) === 0) redWidth++
        for (let y = 0; y < image.height; y++) if (image.red(cx,y) === 255 && image.green(cx,y) === 0) redHeight++
        verify(Math.abs(redWidth-redHeight) <= 1, "The captured square must remain square")
        // Opening another app replaces only that app's image, never Pi's.
        nav.overview = false
        nav.activeAppId = "music"
        deck.surface.color = "#005500"
        wait(30)
        nav.showSwitcher()
        tryCompare(deck.history,"capturing",false)
        tryVerify(() => !!deck.history.previews.music)
        compare(String(deck.history.previews["tablet-improve"].url),piUrl)
        verify(String(deck.history.previews.music.url) !== piUrl)
        nav.overview = false; nav.sourceItem = null; nav.activeAppId = ""
        nav.showSwitcher()
        compare(String(deck.history.previews["tablet-improve"].url),piUrl)
        tryCompare(preview,"status",Image.Ready)
        grabImage(deck).save("switcher-retained.png")
    }
    function test_live_transition_preserves_source_proportions() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        // Exercise the actual bottom drag rather than setting a render-only flag.
        const handle = findChild(nav,"homeHandle")
        mousePress(handle,90,26); mouseMove(handle,90,-60,30)
        const live = findChild(nav,"proportionalLivePreview")
        tryVerify(() => live.width > 0)
        verify(Math.abs(live.width / live.height - deck.width / deck.height) < .001)
        mouseRelease(handle,90,-60)
    }
    function test_upward_card_swipe_dismisses_not_short_or_downward() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        const closed = spy(nav,"closeRequested")
        nav.showSwitcher(); tryCompare(deck.history,"capturing",false); wait(100)
        function drag(distance) {
            mousePress(nav,450,380)
            for (let y = 0; y > distance; y -= 20) mouseMove(nav,450,380+y,20)
            mouseMove(nav,450,380+distance,20)
            mouseRelease(nav,450,380+distance)
        }
        drag(-40); wait(100); compare(closed.count,0)
        drag(100); wait(100); compare(closed.count,0)
        nav.blocked = true; drag(-180); compare(closed.count,0); nav.blocked = false
        drag(-180)
        tryCompare(closed,"count",1)
        compare(closed.signalArguments[0][0],"tablet-improve")
        // Removal releases the image, not conversation data or another card.
        deck.history.close("tablet-improve")
        verify(!deck.history.previews["tablet-improve"])
        compare(JSON.stringify(deck.history.opened),'["music"]')
    }
    function test_touch_upward_card_swipe() {
        const deck = createTemporaryObject(deckComponent,suite), nav = deck.navigator
        const closed = spy(nav,"closeRequested")
        nav.showSwitcher(); tryCompare(deck.history,"capturing",false); wait(100)
        const seq = touchEvent(nav)
        seq.press(0,nav,450,380).commit(); wait(30)
        for (let y = 360; y >= 160; y -= 20) { seq.move(0,nav,450,y).commit(); wait(20) }
        seq.release(0,nav,450,160).commit()
        tryCompare(closed,"count",1)
    }
    function test_open_apps_resume_and_no_duplicate_history() {
        const history = createTemporaryObject(historyComponent,suite)
        history.open("tablet-improve"); history.open("music"); history.open("tablet-improve"); history.open("invalid")
        compare(JSON.stringify(history.opened),'["tablet-improve","music"]')
        history.restore(["invalid","music","music","tablet-improve"])
        compare(JSON.stringify(history.opened),'["music","tablet-improve"]')
        const deck = createTemporaryObject(deckComponent,suite)
        const nav = deck.navigator
        const resume = spy(nav,"appRequested")
        nav.showSwitcher(); verify(nav.overview); tryCompare(deck.history,"capturing",false)
        nav.resume("tablet-improve","Pi"); verify(!nav.overview); compare(resume.count,0)
        nav.showSwitcher(); tryCompare(deck.history,"capturing",false)
        nav.resume("music","Music"); tryCompare(resume,"count",1)
        nav.showSwitcher(); nav.blocked=true; verify(nav.overview)
        nav.urgentInput=true; verify(!nav.overview)
    }
}
