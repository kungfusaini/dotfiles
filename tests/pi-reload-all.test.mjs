import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import reloadAllExtension, {
  readReloadAllToken,
  reloadAllDirectory,
  writeReloadAllToken,
} from "../home/config/pi/extensions/reload-all.ts";

function fakePi() {
  const commands = new Map();
  const handlers = new Map();
  const tools = new Map();
  const sent = [];
  return {
    api: {
      on(event, handler) {
        handlers.set(event, handler);
      },
      registerCommand(name, definition) {
        commands.set(name, definition);
      },
      registerTool(definition) {
        tools.set(definition.name, definition);
      },
      sendUserMessage(message, options) {
        sent.push({ message, options });
      },
    },
    commands,
    handlers,
    tools,
    sent,
  };
}

function fakeContext(onReload = async () => {}) {
  const notifications = [];
  let reloads = 0;
  let idleWaits = 0;
  let releaseIdle;
  const idle = new Promise((resolve) => {
    releaseIdle = resolve;
  });
  return {
    context: {
      hasUI: false,
      ui: {
        notify(message, level) {
          notifications.push({ message, level });
        },
      },
      async waitForIdle() {
        idleWaits += 1;
        await idle;
      },
      async reload() {
        reloads += 1;
        await onReload();
      },
    },
    notifications,
    releaseIdle,
    get idleWaits() {
      return idleWaits;
    },
    get reloads() {
      return reloads;
    },
  };
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

test("/reload-all reloads its caller and queues reloads in other running sessions", async () => {
  const oldRuntimeDirectory = process.env.XDG_RUNTIME_DIR;
  const runtimeDirectory = mkdtempSync(join(tmpdir(), "pi-reload-all-test-"));
  process.env.XDG_RUNTIME_DIR = runtimeDirectory;

  const first = fakePi();
  const second = fakePi();
  const firstContext = fakeContext();
  const secondContext = fakeContext();

  try {
    assert.equal(readReloadAllToken(), undefined);
    const initialToken = writeReloadAllToken();
    assert.equal(readReloadAllToken(), initialToken);
    assert.equal(readFileSync(join(reloadAllDirectory(), "generation"), "utf8"), `${initialToken}\n`);
    assert.equal(statSync(reloadAllDirectory()).mode & 0o777, 0o700);

    reloadAllExtension(first.api);
    reloadAllExtension(second.api);
    first.handlers.get("session_start")({}, firstContext.context);
    second.handlers.get("session_start")({}, secondContext.context);

    const callerReload = first.commands.get("reload-all").handler("", firstContext.context);
    await wait(0);
    assert.equal(firstContext.idleWaits, 1);
    assert.equal(firstContext.reloads, 0);
    assert.match(firstContext.notifications.at(-1).message, /Reloading all running Pi sessions/);
    firstContext.releaseIdle();
    await callerReload;
    assert.equal(firstContext.reloads, 1);
    first.handlers.get("session_shutdown")();

    await wait(450);
    assert.deepEqual(first.sent, []);
    assert.deepEqual(second.sent, [{
      message: "/reload-all --apply",
      options: { deliverAs: "followUp", expandPromptTemplates: true },
    }]);

    writeReloadAllToken();
    await wait(450);
    assert.equal(second.sent.length, 1, "busy sessions coalesce repeated broadcasts into one reload");

    const apply = second.commands.get("reload-all").handler("--apply", secondContext.context);
    await wait(0);
    assert.equal(secondContext.idleWaits, 1);
    assert.equal(secondContext.reloads, 0);
    secondContext.releaseIdle();
    await apply;
    assert.equal(secondContext.reloads, 1);
  } finally {
    first.handlers.get("session_shutdown")?.();
    second.handlers.get("session_shutdown")?.();
    if (oldRuntimeDirectory === undefined) delete process.env.XDG_RUNTIME_DIR;
    else process.env.XDG_RUNTIME_DIR = oldRuntimeDirectory;
    rmSync(runtimeDirectory, { recursive: true, force: true });
  }
});

test("reload_all_sessions broadcasts and reloads each session only after idle", async () => {
  const oldRuntimeDirectory = process.env.XDG_RUNTIME_DIR;
  const runtimeDirectory = mkdtempSync(join(tmpdir(), "pi-reload-all-tool-test-"));
  process.env.XDG_RUNTIME_DIR = runtimeDirectory;

  const caller = fakePi();
  const receiver = fakePi();
  const callerContext = fakeContext();
  const receiverContext = fakeContext();

  try {
    reloadAllExtension(caller.api);
    reloadAllExtension(receiver.api);
    caller.handlers.get("session_start")({ reason: "startup" }, callerContext.context);
    receiver.handlers.get("session_start")({ reason: "startup" }, receiverContext.context);

    const result = await caller.tools.get("reload_all_sessions").execute();
    assert.match(result.content[0].text, /Broadcast the resource reload/);
    assert.deepEqual(caller.sent, [{
      message: "/reload-all --apply",
      options: { deliverAs: "followUp", expandPromptTemplates: true },
    }]);

    const callerApply = caller.commands.get("reload-all").handler("--apply", callerContext.context);
    await wait(0);
    assert.equal(callerContext.idleWaits, 1);
    assert.equal(callerContext.reloads, 0);

    await wait(450);
    assert.deepEqual(receiver.sent, [{
      message: "/reload-all --apply",
      options: { deliverAs: "followUp", expandPromptTemplates: true },
    }]);
    const receiverApply = receiver.commands.get("reload-all").handler("--apply", receiverContext.context);
    await wait(0);
    assert.equal(receiverContext.idleWaits, 1);
    assert.equal(receiverContext.reloads, 0);

    callerContext.releaseIdle();
    receiverContext.releaseIdle();
    await Promise.all([callerApply, receiverApply]);
    assert.equal(callerContext.reloads, 1);
    assert.equal(receiverContext.reloads, 1);
  } finally {
    caller.handlers.get("session_shutdown")?.();
    receiver.handlers.get("session_shutdown")?.();
    if (oldRuntimeDirectory === undefined) delete process.env.XDG_RUNTIME_DIR;
    else process.env.XDG_RUNTIME_DIR = oldRuntimeDirectory;
    rmSync(runtimeDirectory, { recursive: true, force: true });
  }
});

test("a generation written during reload triggers one follow-up reload", async () => {
  const oldRuntimeDirectory = process.env.XDG_RUNTIME_DIR;
  const runtimeDirectory = mkdtempSync(join(tmpdir(), "pi-reload-all-race-test-"));
  process.env.XDG_RUNTIME_DIR = runtimeDirectory;

  const original = fakePi();
  const replacement = fakePi();
  const replacementContext = fakeContext();
  const originalContext = fakeContext(async () => {
    writeReloadAllToken();
    reloadAllExtension(replacement.api);
    replacement.handlers.get("session_start")({ reason: "reload" }, replacementContext.context);
    assert.deepEqual(replacement.sent, [], "replacement reload must not nest inside the active reload");
  });

  try {
    reloadAllExtension(original.api);
    original.handlers.get("session_start")({ reason: "startup" }, originalContext.context);
    const reload = original.commands.get("reload-all").handler("", originalContext.context);
    originalContext.releaseIdle();
    await reload;
    await wait(250);

    assert.deepEqual(replacement.sent, [{
      message: "/reload-all --apply",
      options: { deliverAs: "followUp", expandPromptTemplates: true },
    }]);
  } finally {
    original.handlers.get("session_shutdown")?.();
    replacement.handlers.get("session_shutdown")?.();
    if (oldRuntimeDirectory === undefined) delete process.env.XDG_RUNTIME_DIR;
    else process.env.XDG_RUNTIME_DIR = oldRuntimeDirectory;
    rmSync(runtimeDirectory, { recursive: true, force: true });
  }
});

test("Pi loads the extension and exposes only the public /reload-all command", () => {
  const repository = dirname(dirname(fileURLToPath(import.meta.url)));
  const extension = join(repository, "home/config/pi/extensions/reload-all.ts");
  const runtimeDirectory = mkdtempSync(join(tmpdir(), "pi-reload-all-rpc-test-"));
  try {
    const result = spawnSync("pi", ["--mode", "rpc", "--no-session", "--no-extensions", "--extension", extension], {
      cwd: repository,
      env: { ...process.env, XDG_RUNTIME_DIR: runtimeDirectory },
      input: '{"id":"commands","type":"get_commands"}\n',
      encoding: "utf8",
      timeout: 15_000,
    });
    assert.equal(result.status, 0, result.stderr);
    const response = result.stdout
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line))
      .find((record) => record.id === "commands");
    assert.equal(response.success, true);
    const commands = response.data.commands.map(({ name }) => name);
    assert.ok(commands.includes("reload-all"));
    assert.ok(!commands.includes("reload-all-apply"));
  } finally {
    rmSync(runtimeDirectory, { recursive: true, force: true });
  }
});
