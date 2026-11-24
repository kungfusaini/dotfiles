// Verify the actual compiled private Pi variant, not a mock replacement UI.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { existsSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const root = process.env.PI_PRIVATE_TEST_ROOT;
assert.ok(root, "Set PI_PRIVATE_TEST_ROOT to the private Pi lib/node_modules/pi-monorepo path");
const { InteractiveMode } = await import(pathToFileURL(`${root}/dist/modes/interactive/interactive-mode.js`));
const { AgentSession } = await import(pathToFileURL(`${root}/dist/core/agent-session.js`));
const { FooterComponent } = await import(pathToFileURL(`${root}/dist/modes/interactive/components/footer.js`));

function mode() {
  const instance = Object.create(InteractiveMode.prototype);
  instance.warnings = [];
  instance.showWarning = (text) => instance.warnings.push(text);
  return instance;
}

const blocked = ["handleCtrlZ", "cycleThinkingLevel", "cycleModel", "handleOpenExternalEditor",
  "handleRightClickPaste", "handleClipboardPaste", "showSettingsSelector", "showTrustSelector",
  "showModelSelector", "showModelsSelector", "showThinkingSelector", "handleThinkingCommand",
  "handleModelCommand", "handleLoginCommand", "showOAuthSelector", "handleReloadCommand",
  "handleExportCommand", "handleImportCommand", "handleShareCommand", "handleBugCommand",
  "handleDebugCommand", "handleBashCommand", "handleCopyCommand"];

for (const method of blocked) {
  test(`native handler blocks ${method} before any side effect`, async () => {
    const instance = mode();
    await instance[method]();
    assert.equal(instance.warnings.length, 1);
  });
}

test("native shortcut handlers are guarded, not just slash commands", async () => {
  const instance = mode();
  const actions = new Map();
  instance.ui = {};
  instance.defaultEditor = { onAction: (name, handler) => actions.set(name, handler) };
  instance.setupKeyHandlers();
  for (const name of ["app.suspend", "app.thinking.cycle", "app.model.cycleForward",
    "app.model.cycleBackward", "app.model.select", "app.editor.external", "app.message.copy"]) {
    await actions.get(name)();
  }
  instance.defaultEditor.onPasteImage();
  instance.ui.onDebug();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(instance.warnings.length, 9);
});

test("slash autocomplete retains native commands and never enumerates files", async () => {
  const instance = mode();
  instance.privateCommands = new Set(["new", "resume", "name", "session", "hotkeys", "tree", "fork", "clone", "compact", "quit", "image"]);
  Object.defineProperties(instance, {
    sessionManager: { value: { getCwd: () => "/nonexistent-private-fixture" } },
    session: { value: { promptTemplates: [], extensionRunner: { getRegisteredCommands: () => [
      { name: "image", invocationName: "image", description: "Private image" },
      { name: "unsafe", invocationName: "unsafe", description: "Must not be offered" },
    ] } } },
    settingsManager: { value: { getEnableSkillCommands: () => false } },
  });
  instance.skillCommands = new Map();
  const provider = instance.createBaseAutocompleteProvider();
  const options = { signal: new AbortController().signal, force: true };
  const suggestions = await provider.getSuggestions(["/"], 0, 1, options);
  assert.ok(suggestions.items.some((item) => item.value === "resume"));
  assert.ok(suggestions.items.some((item) => item.value === "image"));
  assert.ok(suggestions.items.every((item) => instance.privateCommands.has(item.value)));
  for (const text of ["@/history", "/history/", "/nix/store/", "hello", "/name /history"]) {
    assert.equal(await provider.getSuggestions([text], 0, text.length, options), null);
  }
});

test("native submit rejects shell and unsafe commands without prompting", async () => {
  const instance = mode();
  instance.privateCommands = new Set(["new", "resume", "name", "session", "hotkeys", "tree", "fork", "clone", "compact", "quit", "image"]);
  instance.defaultEditor = {};
  instance.editor = { setText() {} };
  instance.setupEditorSubmitHandler();
  for (const text of ["!touch /history/leak", "!!echo leak", "/share", "/export /history/leak", "/import /history/x", "/model", "/settings", "/login", "/llama", "/reload"]) {
    await instance.defaultEditor.onSubmit(text);
  }
  assert.equal(instance.warnings.length, 10);
});

test("private model and attachment restrictions also live in Pi's session engine", async () => {
  const cloud = { provider: "openai-codex", id: "cloud", baseUrl: "https://example.invalid" };
  assert.throws(() => new AgentSession({ agent: { state: { model: cloud } } }), /pinned local model/);
  await assert.rejects(AgentSession.prototype.setModel.call({}, cloud), /Model switching/);
  await assert.rejects(AgentSession.prototype.prompt.call({}, "hello", { images: [{ data: "synthetic" }] }), /attachments/);
});

test("native Markdown keeps styling and emoji but cannot emit injected terminal controls", async () => {
  const { initTheme, getMarkdownTheme } = await import(pathToFileURL(`${root}/dist/modes/interactive/theme/theme.js`));
  const { Markdown, Text } = await import(pathToFileURL(`${root}/node_modules/@earendil-works/pi-tui/dist/index.js`));
  const { AssistantMessageComponent } = await import(pathToFileURL(`${root}/dist/modes/interactive/components/assistant-message.js`));
  initTheme("dark");
  const injected = "**bold** 👩🏽‍💻\n\x1b]52;c;synthetic\x07";
  const markdown = new Markdown(injected, 0, 0, getMarkdownTheme());
  for (const text of [injected, injected + " updated"]) {
    markdown.setText(text);
    const output = markdown.render(120).join("\n");
    assert.ok(!output.includes("\x1b]52;"));
    assert.ok(output.includes("👩🏽‍💻"));
    assert.ok(output.includes("bold") && !output.includes("**bold**"), "Native Markdown parsing remains intact (colors may be disabled headlessly)");
  }
  const notice = new Text("\x1b[31mstyled notice\x1b[0m" + injected, 0, 0).render(120).join("\n");
  assert.ok(!notice.includes("\x1b]52;"));
  assert.ok(notice.includes("\x1b[31m"), "Legitimate native SGR styling is retained");
  for (const reason of ["error", "aborted"]) {
    const component = new AssistantMessageComponent({ role: "assistant", content: [], stopReason: reason, errorMessage: injected });
    assert.ok(!component.render(120).join("\n").includes("\x1b]52;"));
  }
});

test("native mouse selection and explicit selection-copy cannot emit OSC52", async () => {
  const { createInteractiveTui } = await import(pathToFileURL(`${root}/dist/modes/interactive/tui-renderer.js`));
  const { Text } = await import(pathToFileURL(`${root}/node_modules/@earendil-works/pi-tui/dist/index.js`));
  let input;
  const writes = [];
  const terminal = { columns: 20, rows: 4, start(handler) { input = handler; }, stop() {},
    write(text) { writes.push(text); }, moveBy() {}, hideCursor() {}, showCursor() {},
    clearLine() {}, clearFromCursor() {}, clearScreen() {} };
  const tui = createInteractiveTui({ tuiMode: "fullscreen", terminal, showHardwareCursor: false, logDirectory: "/tmp", fullscreenCopyOnSelect: true });
  tui.addChild(new Text("alpha\nbeta\ngamma\ndelta", 0, 0));
  tui.start();
  try {
    await new Promise((resolve) => setTimeout(resolve, 150));
    input("\x1b[<0;1;1M"); input("\x1b[<32;4;2M"); input("\x1b[<0;4;2m");
    await new Promise((resolve) => setTimeout(resolve, 150));
    assert.equal(tui.getCopyOnSelect(), false, "Private renderer ignores unsafe copy-on-select setting");
    assert.equal(tui.hasActiveSelection(), true);
    await tui.copySelectionToClipboard();
    assert.ok(!writes.join("").includes("\x1b]52;"));
  } finally { tui.stop({ preserveScreen: true }); }
});

test("new and existing history is sanitized before the native tree sees it", async () => {
  const { SessionManager, loadEntriesFromFile } = await import(pathToFileURL(`${root}/dist/core/session-manager.js`));
  const { TreeSelectorComponent } = await import(pathToFileURL(`${root}/dist/modes/interactive/components/tree-selector.js`));
  const manager = SessionManager.inMemory("/home/private");
  const injected = "tree sentinel \x1b]52;c;synthetic\x07\x1b[2J";
  manager.appendMessage({ role: "assistant", content: [{ type: "text", text: injected }], stopReason: "stop" });
  manager.appendSessionInfo(injected);
  const selector = new TreeSelectorComponent(manager.getTree(), manager.getLeafId(), 40, () => {}, () => {});
  assert.ok(!selector.render(120).join("\n").includes("\x1b]52;"));
  assert.ok(!selector.render(120).join("\n").includes("\x1b[2J"));
  const directory = mkdtempSync(join(tmpdir(), "pi-private-raw-history-"));
  try {
    const path = join(directory, "fixture.jsonl");
    writeFileSync(path, JSON.stringify(manager.getHeader()) + "\n" + JSON.stringify({ type: "message", id: "fixture", parentId: null, timestamp: new Date().toISOString(), message: { role: "assistant", content: [{ type: "text", text: injected }] } }) + "\n");
    const loaded = loadEntriesFromFile(path);
    assert.ok(!loaded.find((entry) => entry.type === "message").message.content[0].text.includes("\x1b"));
    const reopened = SessionManager.open(path);
    const resumedTree = new TreeSelectorComponent(reopened.getTree(), reopened.getLeafId(), 40, () => {}, () => {});
    assert.ok(!resumedTree.render(120).join("\n").includes("\x1b]52;"));
  } finally { rmSync(directory, { recursive: true }); }
});

test("even fatal transcript-stop requests cannot leave fullscreen with private content", () => {
  const calls = [];
  const instance = mode();
  instance.renderer = { mode: "fullscreen" };
  instance.ui = { stop: (options) => calls.push(options) };
  instance.stopInteractiveTui("transcript");
  assert.deepEqual(calls, [{ preserveScreen: true }]);
});

test("actual uncaught-crash cleanup cannot spill the private renderer document", async () => {
  const { createInteractiveTui } = await import(pathToFileURL(`${root}/dist/modes/interactive/tui-renderer.js`));
  const { Text } = await import(pathToFileURL(`${root}/node_modules/@earendil-works/pi-tui/dist/index.js`));
  const writes = [];
  const terminal = { columns: 60, rows: 4, start() {}, stop() {}, write(text) { writes.push(text); },
    moveBy() {}, hideCursor() {}, showCursor() {}, clearLine() {}, clearFromCursor() {}, clearScreen() {} };
  const tui = createInteractiveTui({ tuiMode: "fullscreen", terminal, showHardwareCursor: false, logDirectory: "/tmp" });
  tui.addChild(new Text("PRIVATE_UNCAUGHT_CRASH_SENTINEL", 0, 0));
  tui.start();
  await new Promise((resolve) => setTimeout(resolve, 150));
  const instance = mode();
  instance.ui = tui;
  instance.unregisterSignalHandlers = () => {};
  instance.getCrashExtensionHint = () => undefined;
  instance.recordCrash = () => false;
  const exit = process.exit;
  const error = console.error;
  const stopped = new Error("synthetic exit trap");
  process.exit = () => { throw stopped; };
  console.error = () => {};
  try {
    assert.throws(() => instance.uncaughtCrash(new Error("synthetic private crash")), (value) => value === stopped);
    const output = writes.join("");
    assert.ok(output.includes("\x1b[?1049l"));
    assert.ok(!output.split("\x1b[?1049l").at(-1).includes("PRIVATE_UNCAUGHT_CRASH_SENTINEL"));
  } finally {
    process.exit = exit;
    console.error = error;
    tui.stop({ preserveScreen: true });
  }
});

test("image-only sessions persist and branch without a chat-model response", async () => {
  const { SessionManager, loadEntriesFromFile } = await import(pathToFileURL(`${root}/dist/core/session-manager.js`));
  const directory = mkdtempSync(join(tmpdir(), "pi-private-image-history-"));
  try {
    const manager = SessionManager.create("/home/private", directory);
    const leaf = manager.appendCustomMessageEntry("private-image", "Synthetic local image", true, { filename: "fixture.png" });
    assert.ok(existsSync(manager.getSessionFile()));
    assert.ok(loadEntriesFromFile(manager.getSessionFile()).some((e) => e.type === "custom_message"));
    const branch = manager.createBranchedSession(leaf);
    assert.ok(existsSync(branch));
    manager.appendSessionInfo("Image-only fixture");
    const entries = loadEntriesFromFile(branch);
    assert.equal(entries.filter((e) => e.type === "session").length, 1);
    assert.ok(entries.some((e) => e.type === "session_info"));
  } finally { rmSync(directory, { recursive: true }); }
});

test("pinned image extension renders bounded pixel-only previews", async () => {
  const extension = process.env.PI_PRIVATE_IMAGE_EXTENSION;
  assert.ok(extension, "Set PI_PRIVATE_IMAGE_EXTENSION to the packaged private-image.ts");
  const { createJiti } = await import(pathToFileURL(`${root}/node_modules/jiti/lib/jiti.mjs`));
  const jiti = createJiti(import.meta.url, { fsCache: false, moduleCache: false, alias: {
    "@earendil-works/pi-coding-agent": `${root}/dist/index.js`,
    "@earendil-works/pi-tui": `${root}/node_modules/@earendil-works/pi-tui/dist/index.js`,
  } });
  const image = await jiti.import(extension);
  const fixture = { filename: "a".repeat(32) + ".png", width: 512, height: 512,
    seconds: 1, preview: Buffer.alloc(64 * 64 * 3, 127).toString("base64") };
  assert.equal(image.validImage(fixture), true);
  for (const value of [{ ...fixture, filename: "../../leak.png" }, { ...fixture, preview: "\\x1b]52;c;no" },
    { ...fixture, width: 8192 }, { ...fixture, seconds: NaN }, { ...fixture, preview: "A".repeat(20000) }]) {
    assert.equal(image.validImage(value), false);
    assert.throws(() => new image.PixelPreview(value));
  }
  const preview = new image.PixelPreview(fixture);
  for (const width of [1, 2, 16, 80]) {
    for (const line of preview.render(width)) {
      const pixels = line.replace(/\x1b\[[0-9;]*m/g, "");
      assert.ok(/^▀+$/.test(pixels));
      assert.ok(pixels.length <= width);
    }
  }
  const commands = new Map();
  image.default({ on() {}, registerMessageRenderer() {}, registerCommand(name, spec) { commands.set(name, spec); } });
  assert.deepEqual([...commands.keys()], ["image"]);
  const notices = [];
  await commands.get("image").handler("", { mode: "tui", hasUI: true, ui: { notify: (text) => notices.push(text) } });
  assert.match(notices[0], /Usage: \/image/);
  assert.ok(!readFileSync(extension, "utf8").includes("registerTool("));
});

test("private banner is part of the native footer renderer", () => {
  assert.match(FooterComponent.prototype.render.toString(), /PRIVATE · LOCAL ONLY · chat \+ \/image/);
});
