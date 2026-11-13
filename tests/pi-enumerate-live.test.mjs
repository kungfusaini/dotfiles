// Opt-in long-conversation trial with synthetic source material only.
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

if (!process.env.PI_ENUM_SDK) throw new Error("Set PI_ENUM_SDK to pi-monorepo/dist/index.js");
const sdkUrl = pathToFileURL(resolve(process.env.PI_ENUM_SDK)).href;
registerHooks({ resolve(specifier, context, next) {
  return specifier === "@earendil-works/pi-coding-agent" ? { url: sdkUrl, shortCircuit: true } : next(specifier, context);
} });

test("live full-history extraction and three native topic branches; only explicit final carry generates a summary", { skip: process.env.PI_ENUM_LIVE !== "1", timeout: 240_000 }, async () => {
  const sdk = await import(sdkUrl);
  const { default: extension, readQueue } = await import("../home/config/pi/extensions/enumerate.ts");
  const runtime = await sdk.ModelRuntime.create({ allowModelNetwork: false });
  const registry = new sdk.ModelRegistry(runtime);
  const model = registry.find("openai-codex", "gpt-6.1-sol");
  assert.ok(model, "Configured Codex model is required for the opt-in live test");
  const manager = sdk.SessionManager.inMemory("/tmp");
  const baseline = `EARLY_SHARED_HISTORY\n${"Synthetic implementation evidence. This old work is completed, not an outstanding topic.\n".repeat(2300)}`;
  assert.ok(baseline.length > 180_000);
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
  manager.appendMessage({ role: "assistant", content: [{ type: "text", text: baseline }], api: "test", provider: "test", model: "test", stopReason: "stop", usage, timestamp: Date.now() });
  manager.appendMessage({ role: "user", content: "For a story, gather exactly these three topics one at a time in this order: 1. Which fruit? 2. Which colour? 3. Which location? Writing the story is AFTER the queue, not a fourth item. Enumerate those three questions only.", timestamp: Date.now() });
  const commands = new Map(), events = new Map(), notes = [];
  const api = {
    on: (name, handler) => events.set(name, handler),
    registerCommand: (name, definition) => commands.set(name, definition.handler),
    appendEntry: (type, data) => manager.appendCustomEntry(type, data),
    sendMessage: (m) => manager.appendCustomMessageEntry(m.customType, m.content, m.display, m.details),
    setLabel: (id, label) => manager.appendLabelChange(id, label),
  };
  const ctx = {
    mode: "rpc", hasUI: true, sessionManager: manager, modelRegistry: registry, model,
    isIdle: () => true, hasPendingMessages: () => false,
    ui: {
      setStatus() {}, setWidget() {}, notify: (message, type) => notes.push({ message, type }),
      editor: async (_title, prefill) => prefill, confirm: async () => true,
      select: async (_title, choices) => choices[0],
    },
    navigateTree: async (id) => { manager.branch(id); await events.get("session_tree")({}, ctx); return { cancelled: false }; },
  };
  extension(api);
  await commands.get("enum")("", ctx);
  assert.equal(readQueue(ctx)?.items.length, 3, JSON.stringify(notes));
  for (const [i, expected] of [[0, /fruit/], [1, /colou?r/], [2, /location|place/]]) assert.match(readQueue(ctx).items[i].title.toLowerCase(), expected);
  for (const [i, answer] of [[0, "mango"], [1, "violet"], [2, "Kyoto"]]) {
    assert.equal(readQueue(ctx).index, i, JSON.stringify(notes));
    assert.ok(JSON.stringify(manager.buildSessionProjection().messages).includes(JSON.stringify(baseline).slice(1, -1)));
    const identity = events.get("before_agent_start")({}, ctx).message.content;
    assert.match(identity, new RegExp(`Item ${i + 1} of 3`));
    if (i === 2) assert.match(identity, /LAST ITEM/);
    manager.appendMessage({ role: "user", content: `My answer is ${answer}.`, timestamp: Date.now() });
    // Default switches do not generate summaries. Only final explicit carry does.
    await commands.get("next")(i === 2 ? "carry" : "", ctx);
  }
  assert.equal(readQueue(ctx).phase, "complete", JSON.stringify(notes));
  const conclusions = JSON.stringify(manager.buildSessionProjection().messages);
  for (const answer of ["mango", "violet", "Kyoto"]) assert.match(conclusions, new RegExp(answer, "i"));
  assert.equal(manager.getEntries().filter((e) => e.type === "custom" && e.customType === "enumerate-model-usage").length, 2);
});
