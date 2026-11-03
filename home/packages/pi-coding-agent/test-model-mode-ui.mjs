// Exercise the actual installed/built native components without model requests.
// node test-model-mode-ui.mjs STOCK_STORE_PATH PATCHED_STORE_PATH
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

async function load(root) {
  const base = resolve(root, "lib/node_modules/pi-monorepo");
  const module = (path) => import(pathToFileURL(`${base}/${path}`));
  const { initTheme } = await module("dist/modes/interactive/theme/theme.js");
  initTheme("dark");
  return {
    ...await module("node_modules/@earendil-works/pi-tui/dist/index.js"),
    ...await module("dist/modes/interactive/components/extension-selector.js"),
    ...await module("dist/modes/interactive/components/footer.js"),
  };
}
const stock = await load(process.argv[2]);
const patched = await load(process.argv[3]);
const labels = ["Fast", "Normal", "Deep", "Extreme"];
for (let index = 0; index < labels.length; index++) {
  let chosen;
  const selector = new patched.ExtensionSelectorComponent("Mode", labels,
    (choice) => { chosen = choice; }, () => {}, { initialIndex: index });
  selector.handleInput("\r");
  assert.equal(chosen, labels[index], "Enter selects the current mode without navigation");
  selector.handleInput("\x1b[A");
  selector.handleInput("\r");
  assert.equal(chosen, labels[Math.max(0, index - 1)]);
  selector.handleInput("\x1b[B");
  selector.handleInput("\r");
  assert.equal(chosen, labels[Math.min(labels.length - 1, Math.max(0, index - 1) + 1)]);
  for (const width of [8, 30, 100]) {
    assert.ok(selector.render(width).every((line) => patched.visibleWidth(line) <= width));
  }
  selector.invalidate();
  selector.dispose();
}
for (const [index, expected] of [[undefined, "Fast"], [-1, "Fast"], [100, "Extreme"], [NaN, "Fast"], [1.5, "Fast"]]) {
  let chosen;
  const selector = new patched.ExtensionSelectorComponent("Mode", labels,
    (choice) => { chosen = choice; }, () => {}, { initialIndex: index });
  selector.handleInput("\r");
  assert.equal(chosen, expected);
  selector.dispose();
}

const session = {
  state: { model: { id: "gpt-6.1-sol", provider: "openai-codex", reasoning: true, contextWindow: 272000 }, thinkingLevel: "high" },
  sessionManager: { getEntries: () => [], getCwd: () => "/tmp/example", getSessionName: () => "Test" },
  getContextUsage: () => ({ contextWindow: 272000, percent: 12 }),
  modelRuntime: { isUsingSubscription: () => true },
};
const statuses = new Map();
const footerData = {
  getGitBranch: () => "main",
  getExtensionStatuses: () => statuses,
  getAvailableProviderCount: () => 2,
};
const before = new stock.FooterComponent(session, footerData);
const after = new patched.FooterComponent(session, footerData);
for (const width of [1, 5, 12, 40, 100]) {
  assert.deepEqual(after.render(width), before.render(width), "Unconfigured footer remains identical");
}
statuses.set("other", "Other status 日本語");
for (const width of [1, 5, 12, 40, 100]) {
  assert.deepEqual(after.render(width), before.render(width), "Other extension statuses remain identical");
}
statuses.set("model-mode", "mode:deep");
for (const width of [1, 5, 12, 40, 100]) {
  const actual = after.render(width);
  const previous = before.render(width);
  assert.deepEqual(actual.slice(0, 2), previous.slice(0, 2), "Preserve native path, stats, context, cost, model and reasoning");
  assert.equal(patched.visibleWidth(actual[2]), width, "Mode row ends at the right edge");
  if (width >= 12) assert.ok(actual[2].endsWith("mode:deep"));
  assert.ok(actual.every((line) => patched.visibleWidth(line) <= width));
  after.invalidate();
}
statuses.delete("other");
const loneMode = after.render(100)[2];
assert.equal(loneMode.trim(), "mode:deep");
assert.equal(patched.visibleWidth(loneMode), 100);
console.log("PASS: native initial selection, Enter/arrows, bounded indices, narrow layouts, footer parity and right alignment");
