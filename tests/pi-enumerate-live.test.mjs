// Opt-in synthetic provider test. Shares no personal session messages with the model.
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

test("configured provider extracts a synthetic agenda and carries an actual generated decisions summary", { skip: process.env.PI_ENUM_LIVE !== "1", timeout: 180_000 }, async () => {
  const sdk = await import(sdkUrl);
  const { default: extension, readQueue } = await import("../home/config/pi/extensions/enumerate.ts");
  const runtime = await sdk.ModelRuntime.create({ allowModelNetwork: false });
  const registry = new sdk.ModelRegistry(runtime);
  const model = registry.find("openai-codex", "gpt-6.1-sol");
  assert.ok(model, "Configured Codex model is required for the opt-in live test");
  const manager = sdk.SessionManager.inMemory("/tmp");
  manager.appendMessage({ role: "user", content: "I want to tackle exactly these two topics, in this order: the local test server port, then the local test widget color. Enumerate those topics only.", timestamp: Date.now() });
  const commands = new Map(), events = new Map(), notes = [];
  const api = {
    on: (name, handler) => events.set(name, handler),
    registerCommand: (name, definition) => commands.set(name, definition.handler),
    appendEntry: (type, data) => manager.appendCustomEntry(type, data),
    sendMessage: (m) => manager.appendCustomMessageEntry(m.customType, m.content, m.display, m.details),
    setLabel: (id, label) => manager.appendLabelChange(id, label),
  };
  let finishing = false;
  const ctx = {
    mode: "rpc", hasUI: true, sessionManager: manager, modelRegistry: registry, model,
    isIdle: () => true, hasPendingMessages: () => false,
    ui: {
      setStatus() {}, setWidget() {}, notify: (message, type) => notes.push({ message, type }),
      editor: async (_title, prefill) => prefill, confirm: async () => true,
      select: async (_title, choices) => choices[finishing ? 2 : 0],
    },
    navigateTree: async (id) => { manager.branch(id); await events.get("session_tree")({}, ctx); return { cancelled: false }; },
  };
  extension(api);
  await commands.get("enum")("", ctx);
  assert.equal(readQueue(ctx)?.items.length, 2, JSON.stringify(notes));
  assert.match(readQueue(ctx).items[0].title.toLowerCase(), /port|server/);
  manager.appendMessage({ role: "user", content: "Decision for this synthetic test only: use port 7331. No files should be changed.", timestamp: Date.now() });
  await commands.get("next")("", ctx);
  assert.equal(readQueue(ctx)?.index, 1, JSON.stringify(notes));
  assert.match(JSON.stringify(manager.buildSessionProjection().messages), /7331/);
  assert.match(JSON.stringify(manager.buildSessionProjection().messages), /LAST ITEM/);
  finishing = true;
  await commands.get("next")("", ctx);
  assert.equal(readQueue(ctx).phase, "complete");
  assert.equal(manager.getEntries().filter((e) => e.type === "custom" && e.customType === "enumerate-model-usage").length, 2);
});
