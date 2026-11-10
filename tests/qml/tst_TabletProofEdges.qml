import QtQuick
import QtTest
import "../../home/packages/tablet-proof" as Proof

TestCase {
    id: test
    name: "TabletProofEdges"
    when: windowShown
    visible: true
    width: 960; height: 640
    Component {
        id: fixture
        Proof.EdgeGestures {
            width: 960; height: 640
            property int settings: 0
            property int home: 0
            onSettingsRequested: settings++
            onHomeRequested: home++
        }
    }
    function make() { const item=createTemporaryObject(fixture, test); wait(40); return item }
    function swipe(item,x,y,dx,dy,touch) {
        if (touch) {
            const sequence=touchEvent(item)
            sequence.press(0,item,x,y).commit();wait(30)
            sequence.move(0,item,x+dx/2,y+dy/2).commit();wait(30)
            sequence.move(0,item,x+dx,y+dy).commit();wait(30)
            sequence.release(0,item,x+dx,y+dy).commit()
        } else {
            mousePress(item,x,y)
            mouseMove(item,x+dx/2,y+dy/2,30)
            mouseMove(item,x+dx,y+dy,30)
            mouseRelease(item,x+dx,y+dy)
        }
    }
    function test_top_right_touch_and_mouse() {
        for(const touch of [true,false]) {
            const item=make()
            swipe(item,920,8,0,100,touch)
            tryCompare(item,"settings",1)
            compare(item.home,0)
        }
    }
    function test_other_origins_and_short_pulls_are_not_settings() {
        for(const touch of [true,false]) {
            const item=make()
            swipe(item,20,8,0,100,touch)
            swipe(item,480,300,0,100,touch)
            swipe(item,920,8,0,25,touch)
            compare(item.settings,0)
        }
    }
    function test_bottom_swipe_and_keyboard_inset() {
        for(const inset of [0,200]) {
            const item=make();item.keyboardInset=inset
            swipe(item,480,634-inset,0,-100,true)
            tryCompare(item,"home",1)
            compare(item.settings,0)
        }
    }
    function test_drawer_disables_edge_handlers() {
        const item=make();item.drawerVisible=true
        swipe(item,920,8,0,100,true)
        swipe(item,480,634,0,-100,true)
        compare(item.settings,0);compare(item.home,0)
    }
    function test_home_disables_redundant_bottom_gesture() {
        const item=make();item.homeVisible=true
        swipe(item,480,634,0,-100,true)
        compare(item.home,0)
        swipe(item,920,8,0,100,true)
        tryCompare(item,"settings",1)
    }
}
