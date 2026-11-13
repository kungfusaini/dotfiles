import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

// Explicit SDK path: no user configuration, credentials or provider network calls.
const sdkPath = process.env.PI_ENUM_SDK;
if (!sdkPath) throw new Error("Set PI_ENUM_SDK to the installed pi-monorepo/dist/index.js");
registerHooks({ resolve(specifier, context, next) {
  if (specifier === "@earendil-works/pi-coding-agent") return { url: pathToFileURL(resolve(sdkPath)).href, shortCircuit: true };
  return next(specifier, context);
} });
const sdk = await import(pathToFileURL(resolve(sdkPath)));
const { default: extension, parseItems, readQueue, transcript } = await import("../home/config/pi/extensions/enumerate.ts");
const usage = { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
function assistant(text) { return { role: "assistant", content: [{ type: "text", text }], api: "test", provider: "test", model: "test", stopReason: "stop", usage, timestamp: Date.now() }; }
function fixture(manager = sdk.SessionManager.inMemory("/tmp")) {
  const events = new Map(), commands = new Map(), notes = [], requests = [], widgets = new Map();
  const answers = [], responses = [];
  let idle = true, pending = false, cancelNavigation = false;
  const api = {
    on(name, handler) { events.set(name, handler); },
    registerCommand(name, def) { commands.set(name, def.handler); },
    appendEntry(type, data) { manager.appendCustomEntry(type, data); },
    sendMessage(m) { manager.appendCustomMessageEntry(m.customType, m.content, m.display, m.details); },
    setLabel(id, label) { manager.appendLabelChange(id, label); },
  };
  const ctx = {
    mode: "rpc", hasUI: true, cwd: "/tmp", sessionManager: manager,
    model: { provider: "test", id: "test" },
    modelRegistry: { streamSimple(_model, context, options) {
      requests.push({ context, options });
      return { result: async () => {
        const value = responses.shift();
        if (typeof value === "function") return value(options.signal);
        if (value instanceof Error) throw value;
        return assistant(value ?? '["Alpha","Beta"]');
      } };
    } },
    isIdle: () => idle, hasPendingMessages: () => pending,
    ui: {
      notify(message, type) { notes.push({ message, type }); },
      setStatus() {}, setWidget(key, value) { widgets.set(key, value); },
      async editor(title, prefill) { const answer = answers.shift(); return answer === "PREFILL" ? prefill : typeof answer === "function" ? answer() : answer; },
      async confirm() { const answer = answers.shift(); return typeof answer === "function" ? answer() : answer; },
      async select(title, options) { const answer = answers.shift(); return typeof answer === "function" ? answer(title, options) : typeof answer === "number" ? options[answer] : answer; },
    },
    async navigateTree(id, options) {
      assert.equal(options.summarize, false, "Never silently import Pi's own branch summary");
      if (cancelNavigation) return { cancelled: true };
      const entry = manager.getEntry(id);
      assert.equal(entry.type, "custom", "Anchor must not trigger Pi's user/custom-message edit semantics");
      manager.branch(id);
      await events.get("session_tree")?.({}, ctx);
      return { cancelled: false };
    },
  };
  extension(api);
  return { manager, ctx, api, events, commands, answers, responses, notes, requests, widgets,
    run(name, args = "") { return commands.get(name)(args, ctx); },
    setIdle(v) { idle = v; }, setPending(v) { pending = v; }, cancelNavigation(v) { cancelNavigation = v; },
    start: async function (args = "Alpha; Beta") { answers.push("PREFILL", true); await this.run("enum", args); assert.equal(readQueue(ctx)?.phase, "active", JSON.stringify(notes)); },
  };
}

test("parse editable lists, JSON and bounds; reject control sequences and empty agendas", () => {
  assert.deepEqual(parseItems("1. Alpha\n2) Beta"), ["Alpha", "Beta"]);
  assert.deepEqual(parseItems('```json\n["Alpha","Beta"]\n```'), ["Alpha", "Beta"]);
  for (const x of ["[]", "", '["x",null]', "bad\x1b[31m", Array(32).fill("a").join("\n"), "x".repeat(501)]) assert.throws(() => parseItems(x));
});

test("/enum extracts, permits editing and confirms before any queue mutation", async () => {
  const f = fixture();
  f.manager.appendMessage({ role: "user", content: "Compare Alpha and Beta", timestamp: Date.now() });
  f.answers.push("First revised\nSecond revised", true);
  await f.run("enum");
  assert.equal(f.requests.length, 1);
  const q = readQueue(f.ctx);
  assert.deepEqual(q.items.map((i) => i.title), ["First revised", "Second revised"]);
  assert.match(f.widgets.get("enumerate").join("\n"), /Item 1 of 2/);
  const before = f.manager.getLeafId();
  await f.events.get("before_agent_start")({}, f.ctx);
  assert.equal(f.manager.getLeafId(), before, "No agent event can advance the queue");
  const pacing = f.events.get("before_agent_start")({}, f.ctx);
  assert.match(pacing.message.content, /Completion is not advancement/);
  await f.run("enum");
  assert.equal(f.requests.length, 1, "Active /enum shows queue, never creates a replacement");
});

test("cancel extraction, edit, confirmation, navigation and carry dialogs without advancing", async () => {
  for (const answers of [[undefined], ["Alpha\nBeta", false]]) {
    const f = fixture(); f.answers.push(...answers); await f.run("enum", "Alpha; Beta");
    assert.equal(readQueue(f.ctx), undefined);
  }
  const f = fixture(); await f.start();
  f.answers.push(undefined); const leaf = f.manager.getLeafId(); await f.run("next");
  assert.equal(f.manager.getLeafId(), leaf);
  f.cancelNavigation(true); f.answers.push(2); await f.run("next");
  assert.equal(readQueue(f.ctx).index, 0);
});

test("nothing carryover creates sibling branches, preserves agenda, labels LAST and completes without automatic work", async () => {
  const f = fixture(); await f.start();
  f.manager.appendMessage(assistant("ALPHA_ONLY_PRIVATE_DETAIL"));
  const alphaLeaf = f.manager.getLeafId();
  const root = readQueue(f.ctx).rootId;
  f.answers.push(2); await f.run("next");
  const q = readQueue(f.ctx);
  assert.equal(q.index, 1);
  assert.equal(q.items[0].leafId, alphaLeaf);
  assert.match(f.widgets.get("enumerate")[0], /LAST ITEM/);
  assert.doesNotMatch(JSON.stringify(sdk.buildSessionContext(f.manager.getEntries(), f.manager.getLeafId()).messages), /ALPHA_ONLY_PRIVATE_DETAIL/);
  assert.match(JSON.stringify(f.manager.buildSessionProjection().messages), /Confirmed agenda/);
  assert.ok(f.manager.getBranch().some((e) => e.id === root));
  assert.ok(f.manager.getEntry(alphaLeaf));
  f.manager.appendMessage(assistant("BETA_ONLY_PRIVATE_DETAIL"));
  f.answers.push(2); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "complete");
  assert.equal(f.widgets.get("enumerate"), undefined);
  const text = JSON.stringify(f.manager.buildSessionProjection().messages);
  assert.match(text, /All 2 items covered/);
  assert.doesNotMatch(text, /ALPHA_ONLY_PRIVATE_DETAIL|BETA_ONLY_PRIVATE_DETAIL/);
  assert.equal(f.events.get("before_agent_start")({}, f.ctx), undefined);
  const end = f.manager.getLeafId(); await f.run("next"); assert.equal(f.manager.getLeafId(), end);
});

test("full effective carry retains tool details/images, but excludes reasoning, redacted and hidden bash messages", async () => {
  const f = fixture(); await f.start();
  const removed = f.manager.appendMessage(assistant("REDACT_ME"));
  f.manager.appendContextEdit(removed, null);
  f.manager.appendMessage({ ...assistant("visible text"), content: [{ type: "thinking", thinking: "HIDDEN_REASONING" }, { type: "text", text: "visible text" }, { type: "toolCall", id: "call1", name: "read", arguments: { path: "fixture.txt" } }] });
  f.manager.appendMessage({ role: "toolResult", toolCallId: "call1", toolName: "read", content: [{ type: "text", text: "tool output" }, { type: "image", data: "ZmFrZQ==", mimeType: "image/png" }], isError: false, timestamp: Date.now() });
  f.manager.appendMessage({ role: "bashExecution", command: "private", output: "HIDDEN_BASH", excludeFromContext: true, timestamp: Date.now() });
  f.answers.push(1); await f.run("next");
  const text = JSON.stringify(f.manager.buildSessionProjection().messages);
  assert.match(text, /visible text/); assert.match(text, /fixture.txt/); assert.match(text, /tool output/); assert.match(text, /ZmFrZQ==/);
  assert.doesNotMatch(text, /REDACT_ME|HIDDEN_REASONING|HIDDEN_BASH/);
});

test("projection carries compaction/branch summaries instead of resurrecting raw compacted messages", async () => {
  const f = fixture(); await f.start();
  f.manager.appendMessage(assistant("OLD_COMPACTED_DETAIL"));
  f.manager.appendCompaction("COMPACTED_CONCLUSION", f.manager.getLeafId(), 1000);
  const text = JSON.stringify(transcript(f.ctx));
  assert.match(text, /COMPACTED_CONCLUSION/);
  const id = f.manager.getLeafId();
  f.manager.branchWithSummary(id, "BRANCH_CONCLUSION");
  assert.match(JSON.stringify(transcript(f.ctx)), /BRANCH_CONCLUSION/);
});

test("summary carry and final all/selected summaries use saved item branches, including dropped earlier contexts", async () => {
  const f = fixture(); await f.start("Alpha; Beta; Gamma");
  f.manager.appendMessage(assistant("FIRST_DECISION"));
  f.answers.push(2); await f.run("next");
  f.manager.appendMessage(assistant("SECOND_DECISION"));
  f.answers.push(0); f.responses.push("SECOND_SUMMARY"); await f.run("next");
  assert.equal(readQueue(f.ctx).index, 2);
  assert.match(JSON.stringify(f.manager.buildSessionProjection().messages), /SECOND_SUMMARY/);
  assert.doesNotMatch(JSON.stringify(f.manager.buildSessionProjection().messages), /FIRST_DECISION/);
  f.manager.appendMessage(assistant("THIRD_DECISION"));
  f.answers.push(0); f.responses.push("ALL_SUMMARY"); await f.run("next");
  const source = JSON.stringify(f.requests.at(-1).context.messages);
  for (const expected of ["FIRST_DECISION", "SECOND_DECISION", "THIRD_DECISION"]) assert.match(source, new RegExp(expected));
  assert.match(JSON.stringify(f.manager.buildSessionProjection().messages), /ALL_SUMMARY/);
  assert.equal(readQueue(f.ctx).phase, "complete");

  const g = fixture(); await g.start();
  g.manager.appendMessage(assistant("EXCLUDED_ALPHA")); g.answers.push(2); await g.run("next");
  g.manager.appendMessage(assistant("SELECTED_BETA"));
  g.answers.push(1, 1, 0); g.responses.push("SELECTED_SUMMARY"); await g.run("next");
  assert.doesNotMatch(JSON.stringify(g.requests.at(-1).context.messages), /EXCLUDED_ALPHA/);
  assert.match(JSON.stringify(g.requests.at(-1).context.messages), /SELECTED_BETA/);
});

test("single-item queue is immediately LAST; cancellation of selection/model error cannot finish it", async () => {
  const f = fixture(); await f.start("Only"); assert.match(f.widgets.get("enumerate")[0], /LAST ITEM/);
  f.answers.push(1, undefined); await f.run("next"); assert.equal(readQueue(f.ctx).phase, "active");
  f.answers.push(0); f.responses.push(new Error("synthetic failure")); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "active"); assert.match(f.notes.at(-1).message, /synthetic failure/);
  f.answers.push(2); await f.run("next"); assert.equal(readQueue(f.ctx).phase, "complete");
});

test("busy/queued sessions and concurrent commands cannot advance, and stale dialogs fail closed", async () => {
  const f = fixture(); f.setIdle(false); await f.run("enum", "A"); assert.equal(readQueue(f.ctx), undefined);
  f.setIdle(true); f.setPending(true); await f.run("enum", "A"); assert.equal(readQueue(f.ctx), undefined);
  f.setPending(false); await f.start();
  let resolveDialog;
  f.answers.push(() => new Promise((resolve) => { resolveDialog = resolve; }));
  const first = f.run("next"); await Promise.resolve(); await f.run("next");
  assert.equal(f.events.get("input")({}, f.ctx).action, "handled");
  f.manager.appendMessage(assistant("new message during dialog"));
  resolveDialog("Nothing from this item — agenda only"); await first;
  assert.equal(readQueue(f.ctx).index, 0); assert.match(f.notes.at(-1).message, /session changed/);
});

test("shutdown aborts generation, late results cannot append to or navigate a replaced session", async () => {
  const f = fixture(); let finish;
  f.responses.push(() => new Promise((resolve) => { finish = resolve; }));
  const job = f.run("enum"); await Promise.resolve();
  f.events.get("session_shutdown")({ reason: "reload" }, f.ctx);
  finish(assistant('["Alpha"]')); await job;
  assert.equal(f.manager.getEntries().length, 0);
});

test("manual /tree and reload restore branch-local state; completing another branch does not erase earlier work", async () => {
  const f = fixture(); await f.start();
  f.manager.appendMessage(assistant("alpha discussion")); const alpha = f.manager.getLeafId();
  f.answers.push(2); await f.run("next"); f.manager.appendMessage(assistant("beta discussion"));
  f.answers.push(2); await f.run("next");
  f.manager.branch(alpha);
  const resumed = fixture(f.manager);
  await resumed.events.get("session_start")({}, resumed.ctx);
  assert.equal(readQueue(resumed.ctx).index, 0);
  assert.match(resumed.widgets.get("enumerate")[0], /Item 1 of 2/);
  resumed.answers.push(true); await resumed.run("enum", "cancel");
  assert.equal(readQueue(resumed.ctx).phase, "complete");
  assert.ok(f.manager.getEntry(alpha));
});

test("oversized carry refuses without silently truncating or advancing; non-UI mode refuses", async () => {
  const f = fixture(); await f.start(); f.manager.appendMessage(assistant("X".repeat(181_000)));
  f.answers.push(1); await f.run("next"); assert.equal(readQueue(f.ctx).index, 0); assert.match(f.notes.at(-1).message, /too large/);
  const g = fixture(); g.ctx.hasUI = false; await g.run("enum", "A"); assert.equal(readQueue(g.ctx), undefined);
});

test("TUI generation uses a real cancellable loader; Escape and late model results cannot create a queue", async () => {
  const { initTheme } = await import(new URL("./modes/interactive/theme/theme.js", pathToFileURL(resolve(sdkPath))));
  initTheme("dark");
  for (const cancel of [false, true]) {
    const f = fixture(); f.ctx.mode = "tui";
    let finish;
    if (cancel) f.responses.push(() => new Promise((resolve) => { finish = resolve; }));
    f.answers.push("PREFILL", true);
    f.ctx.ui.custom = async (factory) => {
      let component;
      const result = new Promise((resolve) => {
        component = factory({ requestRender() {} }, { fg: (_color, text) => text }, {}, resolve);
        assert.ok(component.render(30).length > 0);
        if (cancel) component.handleInput("\x1b");
      });
      try { return await result; } finally { component.dispose(); }
    };
    await f.run("enum");
    if (cancel) {
      finish(assistant('["Too late"]'));
      await new Promise((resolve) => setImmediate(resolve));
      assert.equal(readQueue(f.ctx), undefined);
      assert.equal(f.manager.getEntries().length, 0);
    } else assert.equal(readQueue(f.ctx)?.index, 0, JSON.stringify(f.notes));
  }
});

test("file-backed SessionManager reopens the selected item with all sibling branches intact", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-enum-persistence-"));
  const manager = sdk.SessionManager.create(dir, join(dir, "sessions"));
  const f = fixture(manager);
  manager.appendMessage(assistant("seed to flush JSONL"));
  await f.start(); manager.appendMessage(assistant("PERSISTED_ALPHA")); const alpha = manager.getLeafId();
  f.answers.push(2); await f.run("next"); manager.appendMessage(assistant("PERSISTED_BETA"));
  const file = manager.getSessionFile();
  const reopened = sdk.SessionManager.open(file, join(dir, "sessions"));
  const g = fixture(reopened);
  assert.equal(readQueue(g.ctx).index, 1);
  assert.ok(reopened.getEntry(alpha));
  assert.doesNotMatch(JSON.stringify(reopened.buildSessionProjection().messages), /PERSISTED_ALPHA/);
  assert.match(readFileSync(file, "utf8"), /PERSISTED_ALPHA/);
});

// Exercise actual extension loading, command dispatch and AgentSession tree navigation.
// The public API is used end-to-end, without a provider, auth or a visible terminal.
test("real SDK loads extension and dispatches /enum, /next and native tree navigation", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-enum-sdk-"));
  const settingsManager = sdk.SettingsManager.inMemory({ packages: [], compaction: { enabled: false } });
  const resourceLoader = new sdk.DefaultResourceLoader({ cwd: dir, agentDir: dir, settingsManager,
    noExtensions: true, noSkills: true, noThemes: true, noPromptTemplates: true, noContextFiles: true,
    extensionFactories: [extension], systemPrompt: "Synthetic enumeration test. Never call a provider." });
  await resourceLoader.reload();
  const modelRuntime = await sdk.ModelRuntime.create({ authPath: join(dir, "auth.json"), modelsPath: null, modelsStorePath: join(dir, "models-cache.json"), refreshOnCreate: false, allowModelNetwork: false });
  const manager = sdk.SessionManager.inMemory(dir);
  const { session } = await sdk.createAgentSession({ cwd: dir, agentDir: dir, settingsManager, resourceLoader, modelRuntime, sessionManager: manager, noTools: true });
  const answers = ["Alpha\nBeta", true];
  const ui = fixture().ctx.ui;
  ui.editor = async () => answers.shift(); ui.confirm = async () => answers.shift();
  ui.select = async (_title, choices) => choices[2];
  let navigations = 0;
  try {
    await session.bindExtensions({ mode: "rpc", uiContext: ui, commandContextActions: {
      waitForIdle: () => session.waitForIdle(),
      navigateTree: async (id, opts) => { navigations++; return session.navigateTree(id, opts); },
    }, onError: (e) => assert.fail(JSON.stringify(e)) });
    assert.ok(session.extensionRunner.getRegisteredCommands().some((c) => c.name === "enum"));
    await session.prompt("/enum Alpha; Beta");
    assert.equal(readQueue({ sessionManager: manager }).index, 0);
    manager.appendMessage(assistant("SDK_ALPHA_DETAIL"));
    await session.prompt("/next");
    assert.equal(readQueue({ sessionManager: manager }).index, 1);
    assert.doesNotMatch(JSON.stringify(session.messages), /SDK_ALPHA_DETAIL/);
    assert.match(JSON.stringify(session.messages), /Confirmed agenda/);
    await session.prompt("/next");
    assert.equal(readQueue({ sessionManager: manager }).phase, "complete");
    assert.equal(navigations, 2);
  } finally { session.dispose(); }
});
