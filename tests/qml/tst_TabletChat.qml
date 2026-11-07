import QtQuick
import QtQuick.Window
import QtTest
import "../../home/config/quickshell/tablet-home-preview" as Tablet

TestCase {
    id: testCase
    name: "NativeTabletChat"
    when: windowShown
    visible: true
    width: 800
    height: 800
    Component { id: chatComponent; Tablet.PiChat { width: 700; height: 700; ready: true } }
    Component { id: spyComponent; SignalSpy {} }
    function makeChat() {
        const chat = createTemporaryObject(chatComponent, testCase)
        verify(chat !== null)
        wait(30)
        return chat
    }
    Component {
        id: windowComponent
        Window {
            width: 700; height: 700
            property alias chat: content
            Tablet.PiChat { id: content; anchors.fill: parent; ready: true }
        }
    }
    function test_window_activation_starts_with_non_text_focus() {
        const win = createTemporaryObject(windowComponent, testCase)
        win.show(); win.requestActivate()
        tryCompare(win,"active",true)
        wait(50)
        compare(win.chat.inputActive,false)
        compare(findChild(win.chat,"chatMic").visible,false)
        mouseClick(findChild(win.chat,"chatComposer"),40,24)
        tryCompare(win.chat,"inputActive",true)
        win.chat.blurInput()
        win.hide(); wait(20); win.show(); win.requestActivate()
        tryCompare(win,"active",true)
        compare(win.chat.inputActive,false)
        compare(findChild(win.chat,"chatComposer").focus,false)
        keyClick(Qt.Key_Tab)
        tryCompare(win.chat,"inputActive",true)
    }
    function test_dialog_text_input_still_accepts_explicit_selection() {
        const chat = makeChat()
        chat.question = {id:"input",method:"input",title:"Answer",prefill:"Keep this"}
        wait(50)
        const editor = findChild(chat,"piDialogResponse")
        mouseClick(editor,30,15)
        tryCompare(editor,"activeFocus",true)
        compare(editor.text,"Keep this")
        compare(chat.inputActive,false)
        mouseClick(findChild(chat,"piDialogHeader"))
        tryCompare(editor,"activeFocus",false)
        compare(editor.text,"Keep this")
        mouseClick(editor,30,15)
        tryCompare(editor,"activeFocus",true)
    }
    function test_keyboard_and_mic_follow_composer_focus_without_auto_recording() {
        const chat = makeChat()
        const mic = findChild(chat, "chatMic")
        const spy = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "voiceRequested"})
        compare(chat.inputActive, false)
        compare(mic.visible, false)
        findChild(chat, "chatComposer").forceActiveFocus()
        tryCompare(chat, "inputActive", true)
        compare(mic.visible, true)
        compare(mic.text, "")
        compare(mic.Accessible.name, "Start dictation")
        verify(mic.width >= 48)
        verify(mic.height >= 48)
        const icon = findChild(mic, "chatMicIcon")
        verify(icon !== null)
        compare(icon.visible, true)
        compare(spy.count, 0)
        wait(30) // Let Flow place the newly visible input action before tapping.
        mouseClick(mic)
        compare(spy.count, 1)
        compare(spy.signalArguments[0][0], "mic")
        compare(chat.inputActive, true)
        chat.blurInput()
        compare(chat.inputActive, false)
        compare(mic.visible, false)
    }
    function test_tap_away_covers_header_margins_messages_and_unused_action_space() {
        const chat = makeChat()
        chat.draft = "Keep this draft"
        chat.messages = [{role:"assistant",text:"A message"}]
        const actions = findChild(chat,"chatInputActions")
        wait(40)
        const blankActions = actions.mapToItem(chat,actions.width - 4,actions.height / 2)
        for (const point of [[350,4],[150,35],[4,250],[696,250],[350,150],[blankActions.x,blankActions.y]]) {
            chat.focusInput(); compare(chat.inputActive,true)
            const cursor = chat.cursorPosition
            mouseClick(chat,point[0],point[1])
            tryVerify(() => !chat.inputActive, 2000, "tap-away point " + JSON.stringify(point))
            compare(chat.draft,"Keep this draft")
            compare(chat.cursorPosition,cursor)
        }
        mouseClick(findChild(chat,"chatComposer"),30,20)
        tryCompare(chat,"inputActive",true)
    }
    function test_touch_tap_away_preserves_voice_and_draft() {
        const chat = makeChat()
        chat.draft = "Keep touch draft"
        chat.voice = {recording:true}
        for (const point of [[350,4],[4,250],[350,150]]) {
            chat.focusInput()
            const seq = touchEvent(chat)
            seq.press(0,chat,point[0],point[1]).commit(); wait(30)
            seq.release(0,chat,point[0],point[1]).commit()
            tryCompare(chat,"inputActive",false)
            compare(chat.draft,"Keep touch draft")
            verify(chat.voiceActive)
        }
    }
    function test_voice_recording_controls_cannot_hide_on_blur() {
        const chat = makeChat()
        chat.voice = {recording: true}
        chat.blurInput()
        compare(chat.voiceActive, true)
        compare(findChild(chat, "chatMic").visible, false)
    }
    function test_send_is_explicit_and_voice_insertion_never_sends() {
        const chat = makeChat()
        const spy = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "sendRequested"})
        chat.draft = "First "
        findChild(chat, "chatComposer").cursorPosition = 6
        chat.insertDictation("dictation")
        compare(chat.draft, "First dictation")
        compare(spy.count, 0)
        mouseClick(findChild(chat, "chatSend"))
        compare(spy.count, 1)
        compare(spy.signalArguments[0][0], "First dictation")
    }
    function test_busy_send_is_stop_not_another_prompt() {
        const chat = makeChat()
        chat.busy = true
        const prompt = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "sendRequested"})
        const stop = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "stopRequested"})
        mouseClick(findChild(chat, "chatSend"))
        compare(prompt.count, 0)
        compare(stop.count, 1)
    }
    function test_extension_confirmation_is_visible_and_never_automatic() {
        const chat = makeChat()
        const spy = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "answerRequested"})
        findChild(chat, "chatComposer").forceActiveFocus()
        chat.question = {id: "question", method: "confirm", title: "Allow?", message: "A test operation"}
        wait(40)
        compare(chat.inputActive, false)
        compare(spy.count, 0)
        mouseClick(findChild(chat, "piDialogCancel"))
        compare(spy.count, 1)
        compare(spy.signalArguments[0][0].cancelled, true)
    }
    function test_new_chat_is_explicit_and_does_not_clear_draft_itself() {
        const chat = makeChat()
        chat.draft = "Keep this until reset succeeds"
        const spy = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "newChatRequested"})
        const button = findChild(chat, "chatNew")
        compare(spy.count, 0)
        verify(button.enabled)
        verify(button.width >= 48 && button.height >= 48)
        mouseClick(button)
        compare(spy.count, 1)
        compare(chat.draft, "Keep this until reset succeeds")
    }
    function test_new_chat_cannot_discard_unresolved_voice() {
        const chat = makeChat()
        const button = findChild(chat, "chatNew")
        for (const state of [{recording: true}, {transcribing: true}, {uncertain: true}, {ready: true}]) {
            chat.voice = state
            compare(button.enabled, false)
        }
        chat.voice = {}
        compare(button.enabled, true)
    }
    function test_handoff_blocks_edits_and_new_prompts_without_discarding_draft() {
        const chat = makeChat()
        chat.draft = "Preserved through UI update"
        chat.locked = true
        compare(findChild(chat, "chatComposer").enabled, false)
        compare(findChild(chat, "chatSend").enabled, false)
        compare(findChild(chat, "chatNew").enabled, false)
        compare(chat.draft, "Preserved through UI update")
        chat.locked = false
        compare(findChild(chat, "chatComposer").enabled, true)
    }
    function test_new_chat_header_fits_portrait() {
        const chat = makeChat()
        chat.width = 400
        wait(30)
        const button = findChild(chat, "chatNew")
        verify(button.x >= 0 && button.x + button.width <= chat.width)
    }
    function test_quarantined_scene_cannot_answer_extension_dialog() {
        const chat = makeChat()
        const spy = createTemporaryObject(spyComponent, testCase, {target: chat, signalName: "answerRequested"})
        chat.question = {id: "late-question", method: "input", title: "Answer", prefill: "Keep this"}
        wait(40)
        chat.locked = true
        compare(findChild(chat, "piDialogAccept").enabled, false)
        compare(findChild(chat, "piDialogCancel").enabled, false)
        compare(spy.count, 0)
        chat.locked = false
        compare(findChild(chat, "piDialogAccept").enabled, true)
    }
    function test_home_preserves_draft_and_blurs_input() {
        const chat = makeChat()
        chat.draft = "Unsent feedback"
        findChild(chat, "chatComposer").forceActiveFocus()
        chat.blurInput()
        compare(chat.draft, "Unsent feedback")
        compare(chat.inputActive, false)
    }
}
