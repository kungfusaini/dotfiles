import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

// Installed SDK only; no user configuration, credentials or provider calls.
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
  const events = new Map(), commands = new Map(), notes = [], requests = [], widgets = new Map(), statuses = new Map();
  const responses = [];
  let idle = true, pending = false, cancelNavigation = false;
  const api = {
    on(name, handler) { events.set(name, handler); },
    registerCommand(name, def) { commands.set(name, def.handler); },
    appendEntry(type, data) { manager.appendCustomEntry(type, data); },
    sendMessage(m) { manager.appendCustomMessageEntry(m.customType, m.content, m.display, m.details); },
    setLabel(id, label) { manager.appendLabelChange(id, label); },
  };
  const noDialog = async () => assert.fail("Enumeration must not open a dialog");
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
      setStatus(key, value) { statuses.set(key, value); },
      setWidget(key, value, options) { assert.equal(options.placement, "aboveEditor"); widgets.set(key, value); },
      editor: noDialog, confirm: noDialog, select: noDialog, custom: noDialog,
    },
    async navigateTree(id, options) {
      assert.equal(options.summarize, false, "Never silently import Pi's own branch summary");
      if (cancelNavigation) return { cancelled: true };
      assert.equal(manager.getEntry(id).type, "custom", "Anchor must not trigger message edit semantics");
      manager.branch(id);
      await events.get("session_tree")?.({}, ctx);
      return { cancelled: false };
    },
  };
  extension(api);
  return { manager, ctx, api, events, commands, responses, notes, requests, widgets, statuses,
    run(name, args = "") { return commands.get(name)(args, ctx); },
    setIdle(v) { idle = v; }, setPending(v) { pending = v; }, cancelNavigation(v) { cancelNavigation = v; },
    start: async function (args = "Alpha; Beta") { await this.run("enum", args); assert.equal(readQueue(ctx)?.phase, "active", JSON.stringify(notes)); },
  };
}
const visible = (f) => f.manager.getBranch().filter((e) => e.type === "custom_message" && e.display).map((e) => e.content);
const effective = (f) => JSON.stringify(f.manager.buildSessionProjection().messages);

test("parse lists, JSON and bounds; reject control sequences and empty agendas", () => {
  assert.deepEqual(parseItems("1. Alpha\n2) Beta"), ["Alpha", "Beta"]);
  assert.deepEqual(parseItems('```json\n["Alpha","Beta"]\n```'), ["Alpha", "Beta"]);
  for (const x of ["[]", "", '["x",null]', "bad\x1b[31m", Array(32).fill("a").join("\n"), "x".repeat(501)]) assert.throws(() => parseItems(x));
});

test("/enum extracts once, immediately acknowledges topic, and shows only Branch: x of y", async () => {
  const f = fixture();
  f.manager.appendMessage({ role: "user", content: "Compare Alpha and Beta", timestamp: Date.now() });
  await f.run("enum");
  assert.equal(f.requests.length, 1);
  assert.deepEqual(readQueue(f.ctx).items.map((i) => i.title), ["Alpha", "Beta"]);
  assert.deepEqual(visible(f), ["Okay, let's tackle: Alpha"]);
  assert.deepEqual(f.widgets.get("enumerate"), ["Branch: 1 of 2"]);
  assert.equal(f.statuses.get("enumerate"), undefined);
  assert.deepEqual(f.notes, []);
  const leaf = f.manager.getLeafId();
  const pacing = f.events.get("before_agent_start")({}, f.ctx);
  assert.equal(pacing.message.display, false);
  assert.match(pacing.message.content, /Completion is not advancement/);
  assert.equal(f.manager.getLeafId(), leaf);
  await f.run("enum");
  assert.equal(f.requests.length, 1, "Active /enum never re-extracts");
});

test("long full-history extraction, isolated topic branches and automatic all-item collection", async () => {
  const f = fixture();
  const baseline = `EARLY_HISTORY_MUST_SURVIVE\n${"old completed implementation evidence ".repeat(6000)}`;
  f.manager.appendMessage(assistant(baseline));
  const omitted = f.manager.appendMessage(assistant("REMOVED_CONTEXT_MUST_STAY_REMOVED"));
  f.manager.appendContextEdit(omitted, null);
  f.manager.appendMessage({ role: "user", content: "Now enumerate which fruit, which colour, and which location?", timestamp: Date.now() });
  f.responses.push('["Which fruit?","Which colour?","Which location?"]');
  await f.run("enum");
  const source = JSON.stringify(f.requests[0].context.messages);
  assert.ok(source.length > 180_000);
  assert.match(source, /EARLY_HISTORY_MUST_SURVIVE/);
  assert.match(source, /which fruit, which colour, and which location/);
  assert.doesNotMatch(source, /REMOVED_CONTEXT_MUST_STAY_REMOVED/);
  for (const [index, answer] of [[0, "mango"], [1, "violet"], [2, "Kyoto"]]) {
    assert.equal(readQueue(f.ctx).index, index);
    assert.ok(effective(f).includes(JSON.stringify(baseline).slice(1, -1)));
    assert.doesNotMatch(effective(f), /REMOVED_CONTEXT_MUST_STAY_REMOVED/);
    for (const previous of ["mango", "violet"].slice(0, index)) assert.ok(!effective(f).includes(previous));
    assert.match(f.events.get("before_agent_start")({}, f.ctx).message.content, new RegExp(`Item ${index + 1} of 3`));
    assert.deepEqual(f.widgets.get("enumerate"), [`Branch: ${index + 1} of 3`]);
    f.manager.appendMessage({ role: "user", content: answer, timestamp: Date.now() });
    f.manager.appendMessage(assistant("item-local evidence ".repeat(10_000)));
    if (index === 2) f.responses.push("The answers are mango, violet and Kyoto.");
    await f.run("next");
    assert.equal(f.requests.length, index === 2 ? 2 : 1, "Only extraction and final collection call a model");
  }
  const collected = JSON.stringify(f.requests.at(-1).context.messages);
  for (const answer of ["mango", "violet", "Kyoto"]) assert.ok(collected.includes(answer));
  assert.ok(collected.length > 180_000, "No obsolete carryover cap at completion");
  assert.doesNotMatch(collected, /EARLY_HISTORY_MUST_SURVIVE/);
  assert.equal(readQueue(f.ctx).phase, "complete");
  assert.deepEqual(visible(f), ["All topics covered.\n\nThe answers are mango, violet and Kyoto."]);
  assert.equal(f.widgets.get("enumerate"), undefined);
  assert.equal(f.events.get("before_agent_start")({}, f.ctx), undefined);
});

test("native sibling branches preserve saved work, labels and shared agenda", async () => {
  const f = fixture(); await f.start();
  f.manager.appendMessage(assistant("ALPHA_ONLY_PRIVATE_DETAIL"));
  const alpha = f.manager.getLeafId();
  const root = readQueue(f.ctx).rootId;
  await f.run("next");
  assert.equal(readQueue(f.ctx).items[0].leafId, alpha);
  assert.doesNotMatch(effective(f), /ALPHA_ONLY_PRIVATE_DETAIL/);
  assert.match(effective(f), /Agenda:/);
  assert.ok(f.manager.getBranch().some((e) => e.id === root));
  assert.ok(f.manager.getEntry(alpha));
  assert.match(f.manager.getLabel(f.manager.getBranch().find((e) => e.type === "custom" && e.customType === "enumerate-state-v1").id), /:2 Beta/);
  f.responses.push("Both results."); await f.run("next");
  const end = f.manager.getLeafId(); await f.run("next"); assert.equal(f.manager.getLeafId(), end);
});

test("final projection includes effective tools/images, excluding reasoning, edits and hidden bash", async () => {
  const f = fixture(); await f.start();
  const removed = f.manager.appendMessage(assistant("REDACT_ME"));
  f.manager.appendContextEdit(removed, null);
  f.manager.appendMessage({ ...assistant("visible text"), content: [{ type: "thinking", thinking: "HIDDEN_REASONING" }, { type: "text", text: "visible text" }, { type: "toolCall", id: "call1", name: "read", arguments: { path: "fixture.txt" } }] });
  f.manager.appendMessage({ role: "toolResult", toolCallId: "call1", toolName: "read", content: [{ type: "text", text: "tool output" }, { type: "image", data: "ZmFrZQ==", mimeType: "image/png" }], isError: false, timestamp: Date.now() });
  f.manager.appendMessage({ role: "bashExecution", command: "private", output: "HIDDEN_BASH", excludeFromContext: true, timestamp: Date.now() });
  await f.run("next");
  assert.doesNotMatch(effective(f), /visible text|tool output/);
  f.responses.push("Collected"); await f.run("next");
  const text = JSON.stringify(f.requests.at(-1).context.messages);
  for (const expected of ["visible text", "fixture.txt", "tool output", "ZmFrZQ=="]) assert.ok(text.includes(expected));
  assert.doesNotMatch(text, /REDACT_ME|HIDDEN_REASONING|HIDDEN_BASH/);
});

test("projection respects compaction/branch summaries and final collection does not resurrect old details", async () => {
  const f = fixture(); await f.start("Only");
  f.manager.appendMessage(assistant("OLD_COMPACTED_DETAIL"));
  const retained = f.manager.appendMessage(assistant("RETAINED_DETAIL"));
  f.manager.appendCompaction("COMPACTED_CONCLUSION", retained, 1000);
  assert.match(JSON.stringify(transcript(f.ctx)), /COMPACTED_CONCLUSION/);
  assert.doesNotMatch(JSON.stringify(transcript(f.ctx)), /OLD_COMPACTED_DETAIL/);
  f.responses.push("Done"); await f.run("next");
  const source = JSON.stringify(f.requests.at(-1).context.messages);
  assert.match(source, /COMPACTED_CONCLUSION/);
  assert.doesNotMatch(source, /OLD_COMPACTED_DETAIL/);
});

test("single item completes automatically; failed or cancelled summaries/navigation stay active", async () => {
  const f = fixture(); await f.start("Only");
  assert.deepEqual(f.widgets.get("enumerate"), ["Branch: 1 of 1"]);
  f.responses.push(new Error("synthetic failure")); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "active"); assert.match(f.notes.at(-1).message, /synthetic failure/);
  f.responses.push(() => ({ ...assistant("aborted"), stopReason: "aborted" })); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "active");
  f.cancelNavigation(true); f.responses.push("Summary"); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "active");
  f.cancelNavigation(false); f.responses.push("Summary"); await f.run("next");
  assert.equal(readQueue(f.ctx).phase, "complete");
});

test("busy/pending/concurrent commands and stale model results cannot advance", async () => {
  const f = fixture(); f.setIdle(false); await f.run("enum", "A"); assert.equal(readQueue(f.ctx), undefined);
  f.setIdle(true); f.setPending(true); await f.run("enum", "A"); assert.equal(readQueue(f.ctx), undefined);
  f.setPending(false); await f.start("Only");
  let finish;
  f.responses.push(() => new Promise((resolve) => { finish = resolve; }));
  const first = f.run("next"); await Promise.resolve(); await f.run("next");
  assert.equal(f.events.get("input")({}, f.ctx).action, "handled");
  f.manager.appendMessage(assistant("new message while summarizing"));
  finish(assistant("Stale summary")); await first;
  assert.equal(readQueue(f.ctx).phase, "active"); assert.match(f.notes.at(-1).message, /session changed/);
  assert.doesNotMatch(effective(f), /Stale summary/);
});

test("shutdown aborts generation and late results cannot create queues or finish items", async () => {
  for (const name of ["enum", "next"]) {
    const f = fixture(); if (name === "next") await f.start("Only");
    const before = f.manager.getLeafId(); let finish;
    f.responses.push(() => new Promise((resolve) => { finish = resolve; }));
    const job = f.run(name); await Promise.resolve();
    f.events.get("session_shutdown")({ reason: "reload" }, f.ctx);
    finish(assistant('["Too late"]')); await job;
    assert.equal(f.manager.getLeafId(), before);
  }
});

test("manual tree/reload restores only the compact branch line; cancel requires no dialog", async () => {
  const f = fixture(); await f.start();
  f.manager.appendMessage(assistant("alpha discussion")); const alpha = f.manager.getLeafId();
  await f.run("next"); f.responses.push("Done"); await f.run("next");
  f.manager.branch(alpha);
  const resumed = fixture(f.manager);
  await resumed.events.get("session_start")({}, resumed.ctx);
  assert.equal(readQueue(resumed.ctx).index, 0);
  assert.deepEqual(resumed.widgets.get("enumerate"), ["Branch: 1 of 2"]);
  await resumed.run("enum", "cancel");
  assert.equal(readQueue(resumed.ctx).phase, "complete");
  assert.equal(resumed.widgets.get("enumerate"), undefined);
  assert.ok(f.manager.getEntry(alpha));
});

test("invalid extraction, removed carry syntax and non-UI sessions fail without navigation", async () => {
  const f = fixture(); f.responses.push("[]"); await f.run("enum"); assert.equal(readQueue(f.ctx), undefined);
  await f.start(); const leaf = f.manager.getLeafId(); await f.run("next", "carry");
  assert.equal(f.manager.getLeafId(), leaf); assert.match(f.notes.at(-1).message, /without arguments/);
  const g = fixture(); g.ctx.hasUI = false; await g.run("enum", "A"); assert.equal(readQueue(g.ctx), undefined);
});

test("TUI extraction opens no editor, confirmation, selection or custom loader", async () => {
  const f = fixture(); f.ctx.mode = "tui"; await f.run("enum");
  assert.equal(readQueue(f.ctx).index, 0);
  assert.deepEqual(visible(f), ["Okay, let's tackle: Alpha"]);
});

test("file-backed resume retains branch state and sibling history", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-enum-persistence-"));
  const manager = sdk.SessionManager.create(dir, join(dir, "sessions"));
  const f = fixture(manager); manager.appendMessage(assistant("seed to flush JSONL"));
  await f.start(); manager.appendMessage(assistant("PERSISTED_ALPHA")); const alpha = manager.getLeafId();
  await f.run("next"); manager.appendMessage(assistant("PERSISTED_BETA"));
  const file = manager.getSessionFile();
  const reopened = sdk.SessionManager.open(file, join(dir, "sessions")); const g = fixture(reopened);
  assert.equal(readQueue(g.ctx).index, 1); assert.ok(reopened.getEntry(alpha));
  assert.doesNotMatch(effective(g), /PERSISTED_ALPHA/);
  assert.match(readFileSync(file, "utf8"), /PERSISTED_ALPHA/);
  g.responses.push("Both saved results"); await g.run("next");
  for (const answer of ["PERSISTED_ALPHA", "PERSISTED_BETA"]) assert.ok(JSON.stringify(g.requests[0].context.messages).includes(answer));
});

test("actual SDK dispatch/navigation preserves shared history and automatically collects at completion", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-enum-sdk-"));
  const settingsManager = sdk.SettingsManager.inMemory({ packages: [], compaction: { enabled: false } });
  const resourceLoader = new sdk.DefaultResourceLoader({ cwd: dir, agentDir: dir, settingsManager,
    noExtensions: true, noSkills: true, noThemes: true, noPromptTemplates: true, noContextFiles: true,
    extensionFactories: [extension], systemPrompt: "Synthetic enumeration test. Never call a provider." });
  await resourceLoader.reload();
  const modelRuntime = await sdk.ModelRuntime.create({ authPath: join(dir, "auth.json"), modelsPath: null, modelsStorePath: join(dir, "models-cache.json"), refreshOnCreate: false, allowModelNetwork: false });
  const manager = sdk.SessionManager.inMemory(dir);
  const sharedHistory = `NATIVE_SHARED_HISTORY ${"prior implementation evidence ".repeat(7000)}`;
  manager.appendMessage(assistant(sharedHistory));
  const { session } = await sdk.createAgentSession({ cwd: dir, agentDir: dir, settingsManager, resourceLoader, modelRuntime, model: { provider: "test", id: "test", api: "test", name: "Synthetic model", reasoning: false, input: ["text"], contextWindow: 1_000_000, maxTokens: 4096, cost: usage.cost }, sessionManager: manager, noTools: "all" });
  let navigations = 0, summaries = 0;
  try {
    // Intercept only the nested summary; dispatch and tree navigation are real.
    modelRuntime.streamSimple = (_model, context) => {
      summaries++; const text = JSON.stringify(context.messages);
      assert.match(text, /SDK_ALPHA_DETAIL/); assert.match(text, /SDK_BETA_DETAIL/);
      return { result: async () => assistant("SDK_COLLECTED_RESULTS") };
    };
    await session.bindExtensions({ mode: "rpc", uiContext: fixture().ctx.ui, commandContextActions: {
      waitForIdle: () => session.waitForIdle(),
      navigateTree: async (id, opts) => { navigations++; return session.navigateTree(id, opts); },
    }, onError: (e) => assert.fail(JSON.stringify(e)) });
    await session.prompt("/enum Alpha; Beta");
    assert.equal(readQueue({ sessionManager: manager }).index, 0);
    manager.appendMessage(assistant("SDK_ALPHA_DETAIL")); await session.prompt("/next");
    assert.equal(readQueue({ sessionManager: manager }).index, 1);
    assert.doesNotMatch(JSON.stringify(session.messages), /SDK_ALPHA_DETAIL/);
    assert.ok(JSON.stringify(session.messages).includes(sharedHistory));
    manager.appendMessage(assistant("SDK_BETA_DETAIL")); await session.prompt("/next");
    assert.equal(readQueue({ sessionManager: manager }).phase, "complete");
    assert.equal(navigations, 2); assert.equal(summaries, 1);
    assert.match(JSON.stringify(session.messages), /SDK_COLLECTED_RESULTS/);
    assert.ok(JSON.stringify(session.messages).includes(sharedHistory));
  } finally { session.dispose(); }
});
