// Regression checks against both actual installed/built packages; no model calls.
// node test.mjs STOCK_STORE_PATH PATCHED_STORE_PATH
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
async function load(root) {
  const base = resolve(root, 'lib/node_modules/pi-monorepo');
  const module = (p) => import(pathToFileURL(`${base}/${p}`));
  const { initTheme } = await module('dist/modes/interactive/theme/theme.js');
  initTheme('dark');
  return {
    ...await module('node_modules/@earendil-works/pi-tui/dist/index.js'),
    ...await module('dist/modes/interactive/components/assistant-message.js'),
  };
}
const stock = await load(process.argv[2]);
const patched = await load(process.argv[3]);
const message = (content, extra = {}) => ({ role: 'assistant', content, stopReason: 'stop', ...extra });
const cases = [
  message([{ type: 'text', text: '# Title\n\n**bold**, _italic_, 日本語 ✓ 👩🏽‍💻\n\n```js\nconst x = 1;\n```' }]),
  message([{ type: 'thinking', thinking: 'First reasoning' }, { type: 'thinking', thinking: 'Second reasoning' }, { type: 'text', text: 'Final answer' }]),
  message([{ type: 'text', text: 'Partial output' }], { stopReason: 'aborted', errorMessage: 'Cancelled by user' }),
  message([{ type: 'text', text: 'Partial output' }], { stopReason: 'error', errorMessage: 'Network error' }),
  message([{ type: 'text', text: 'Partial output' }], { stopReason: 'length' }),
  message([{ type: 'text', text: 'Calling tool' }, { type: 'toolCall', id: 't1', name: 'bash', arguments: { command: 'true' } }]),
  message([{ type: 'text', text: ' ' }]),
];
let assertions = 0;
for (const hide of [false, true]) {
  for (const m of cases) {
    const a = new stock.AssistantMessageComponent(undefined, hide);
    const b = new patched.AssistantMessageComponent(undefined, hide);
    for (const streaming of [true, true, false]) {
      a.updateContent(m, streaming); b.updateContent(m, streaming);
      for (const width of [100, 30, 8, 100]) {
        assert.deepEqual(b.render(width), a.render(width)); assertions++;
      }
    }
    a.setOutputPad(2); b.setOutputPad(2);
    a.invalidate(); b.invalidate();
    assert.deepEqual(b.render(60), a.render(60)); assertions++;
    a.setHideThinkingBlock(!hide); b.setHideThinkingBlock(!hide);
    assert.deepEqual(b.render(60), a.render(60)); assertions++;
  }
}
// Rapid updates coalesce to the latest content without discarding any text.
const c = new patched.AssistantMessageComponent();
for (let i = 0; i < 100; i++) c.updateContent(message([{ type: 'text', text: `Latest ${i}` }]), true);
assert.equal(c.contentContainer.children.length, 0);
assert.match(c.render(100).join('\n'), /Latest 99/);
assert.equal(c.contentPending, false);
c.updateContent(message([{ type: 'text', text: 'Complete' }]), false);
assert.equal(c.contentPending, false);
assert.match(c.render(100).join('\n'), /Complete/);

// The actual TUI scheduler bounds background frames, but not typing/final output.
for (const Renderer of [patched.TuiMainScreen, patched.TuiAltScreen]) {
let frames = 0, input;
const terminal = {
  columns: 100, rows: 30,
  start(onInput) { input = onInput; }, stop() {}, write() {}, moveBy() {},
  hideCursor() {}, showCursor() {}, clearLine() {}, clearFromCursor() {}, clearScreen() {},
};
const ui = new Renderer(terminal);
const text = new patched.Text('Start', 0, 0);
ui.addChild(text);
const render = text.render.bind(text);
text.render = (width) => { frames++; return render(width); };
ui.start(); await sleep(150);
frames = 0;
const timer = setInterval(() => { text.setText(`Frame ${Date.now()}`); ui.requestRender(); }, 5);
await sleep(350); clearInterval(timer);
assert.ok(frames >= 3 && frames <= 5, `Expected ~10 fps, got ${frames} frames in 350 ms`);
// Force a recent frame, ensuring input arrives during the throttle window.
ui.renderNow();
ui.setFocus({ render: () => [], invalidate() {}, handleInput: () => text.setText('Typed') });
const beforeInput = frames;
input('x');
await new Promise((r) => process.nextTick(r));
assert.ok(frames > beforeInput, 'Keyboard input must bypass the background throttle');
text.setText('Final');
const beforeFinal = frames;
ui.renderNow();
assert.ok(frames > beforeFinal, 'Final render must be synchronous');
ui.requestRender();
ui.stop();
const afterStop = frames;
await sleep(150);
assert.equal(frames, afterStop, 'No scheduled rendering after stop');
}
console.log(`PASS: ${assertions} output-parity checks, streaming coalescing, typing, final rendering, timer shutdown`);
