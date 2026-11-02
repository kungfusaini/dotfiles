// Local-only benchmark: real Pi components, synthetic content, no model or session access.
// Usage: node benchmark.mjs /nix/store/...-pi-coding-agent-VERSION [duration-ms]
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
const root = resolve(process.argv[2], 'lib/node_modules/pi-monorepo');
const load = (p) => import(pathToFileURL(`${root}/${p}`));
const { TuiMainScreen, Text } = await load('node_modules/@earendil-works/pi-tui/dist/index.js');
const { initTheme } = await load('dist/modes/interactive/theme/theme.js');
const { AssistantMessageComponent } = await load('dist/modes/interactive/components/assistant-message.js');
initTheme('dark');
let writes = 0, bytes = 0, frames = 0;
const terminal = {
  columns: 100, rows: 35,
  start() {}, stop() {}, moveBy() {}, hideCursor() {}, showCursor() {},
  clearLine() {}, clearFromCursor() {}, clearScreen() {},
  write(data) { writes++; bytes += Buffer.byteLength(data); },
};
const ui = new TuiMainScreen(terminal);
for (let i = 0; i < 200; i++) ui.addChild(new Text(('Historical output with ✓ Unicode and **markdown**.\n').repeat(50), 0, 0));
const message = { role: 'assistant', content: [{ type: 'text', text: ('- Streaming **answer** with Unicode ✓ and useful detail.\n').repeat(250) }], stopReason: 'stop' };
const component = new AssistantMessageComponent(undefined);
ui.addChild(component);
const spinner = new Text('Working...', 0, 0);
ui.addChild(spinner);
const originalRender = component.render.bind(component);
component.render = (width) => { frames++; return originalRender(width); };
ui.start();
await sleep(150); // Exclude initial history layout from measured work.
frames = writes = bytes = 0;
const cpu = process.cpuUsage();
const start = performance.now();
let chunks = 0;
const timer = setInterval(() => {
  message.content[0].text += `- New chunk ${chunks++}: more detail ✓.\n`;
  component.updateContent(message, true);
  ui.requestRender();
}, 8);
const loader = setInterval(() => { spinner.setText(`Working ${chunks}`); ui.requestRender(); }, 80);
await sleep(Number(process.argv[3] ?? 3000));
clearInterval(timer); clearInterval(loader);
component.updateContent(message, false);
ui.renderNow();
const elapsed = performance.now() - start;
const used = process.cpuUsage(cpu);
ui.stop();
console.log(JSON.stringify({ elapsedMs: elapsed, cpuMs: (used.user + used.system)/1000, cpuPercent: (used.user + used.system)/10/elapsed, chunks, frames, writes, bytes }));
