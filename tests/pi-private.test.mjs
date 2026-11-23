import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { EventEmitter } from "node:events";
import test from "node:test";

registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "node:child_process" && context.parentURL?.endsWith("/extensions/private.ts")) {
      return {
        url: `data:text/javascript,${encodeURIComponent("export const spawn = (...args) => globalThis.__privateSpawn(...args);")}`,
        shortCircuit: true,
      };
    }
    return next(specifier, context);
  },
});
const { default: extension } = await import("../home/config/pi/extensions/private.ts");

function fixture(mode = "tui", idle = true) {
  let handler;
  const events = [];
  const hooks = new Map();
  extension({ on(name, handler) { hooks.set(name, handler); }, registerCommand(name, command) {
    assert.equal(name, "private");
    handler = command.handler;
  } });
  const ctx = {
    mode,
    isIdle: () => idle,
    shutdown: () => events.push(["shutdown"]),
    // Any accidental parent-context inspection is a regression.
    get sessionManager() { assert.fail("Do not read normal chat history"); },
    ui: {
      notify: (message, level) => events.push(["notify", message, level]),
      custom: async (factory) => {
        await factory({
          stop: () => events.push(["stop"]),
          start: () => events.push(["start"]),
          requestRender: (force) => events.push(["render", force]),
        }, null, null, () => events.push(["done"]));
      },
    },
  };
  return { handler, ctx, events, hooks };
}

for (const result of [{ status: 0 }, { status: 1 }, { status: null, error: new Error("synthetic") }]) {
  test(`terminal handoff and restoration: ${JSON.stringify(result)}`, async () => {
    const { handler, ctx, events } = fixture();
    globalThis.__privateSpawn = (command, args, options) => {
      assert.equal(command, "@privateChat@/bin/pi-private");
      assert.equal(options.stdio, "inherit");
      assert.equal(options.env.PI_PRIVATE_PARENT_PID, String(process.pid));
      if (args[0] === "--flush-input") {
        events.push(["flush"]);
        const child = new EventEmitter();
        queueMicrotask(() => child.emit("close", 0));
        return child;
      }
      events.push(["spawn"]);
      assert.deepEqual(args, []);
      assert.ok(process.listenerCount("SIGINT") > 0);
      const child = new EventEmitter();
      queueMicrotask(() => result.error ? child.emit("error", result.error) : child.emit("close", result.status));
      return child;
    };
    const write = process.stdout.write;
    let output = "";
    process.stdout.write = (text) => { output += text; return true; };
    try {
      await handler("must not become private context", ctx);
    } finally {
      process.stdout.write = write;
      delete globalThis.__privateSpawn;
    }
    assert.deepEqual(events.slice(0, 6), [["stop"], ["spawn"], ["flush"], ["start"], ["render", true], ["done"]]);
    assert.match(output, /\x1b\[\?1049h/);
    assert.match(output, /\x1b\[\?1049l$/);
    assert.equal(output.includes("must not become private context"), false);
    assert.equal(events.some((e) => e[0] === "notify"), result.status !== 0);
  });
}

test("flush failure shuts down instead of resuming normal input", async () => {
  const { handler, ctx, events } = fixture();
  globalThis.__privateSpawn = (_command, args) => {
    const child = new EventEmitter();
    queueMicrotask(() => child.emit("close", args[0] === "--flush-input" ? 1 : 0));
    return child;
  };
  const write = process.stdout.write;
  process.stdout.write = () => true;
  try { await handler("", ctx); } finally {
    process.stdout.write = write;
    delete globalThis.__privateSpawn;
  }
  assert.ok(events.some((e) => e[0] === "shutdown"));
  assert.ok(!events.some((e) => e[0] === "start"));
});

test("session shutdown terminates and reaps the active launcher", async () => {
  const { handler, ctx, events, hooks } = fixture();
  globalThis.__privateSpawn = (_command, args) => {
    const child = new EventEmitter();
    child.kill = (signal) => {
      events.push(["kill", signal]);
      queueMicrotask(() => child.emit("close", 143));
    };
    if (args[0] === "--flush-input") queueMicrotask(() => child.emit("close", 0));
    return child;
  };
  const write = process.stdout.write;
  process.stdout.write = () => true;
  try {
    const command = handler("", ctx);
    await hooks.get("session_shutdown")();
    await command;
  } finally {
    process.stdout.write = write;
    delete globalThis.__privateSpawn;
  }
  assert.ok(events.some((e) => e[0] === "kill" && e[1] === "SIGTERM"));
  assert.ok(!events.some((e) => e[0] === "start"));
});

test("nonterminal or active sessions never launch", async () => {
  globalThis.__privateSpawn = () => assert.fail("must not spawn");
  try {
    for (const [mode, idle] of [["rpc", true], ["tui", false]]) {
      const { handler, ctx, events } = fixture(mode, idle);
      await handler("", ctx);
      assert.equal(events.length, 1);
      assert.equal(events[0][0], "notify");
    }
  } finally {
    delete globalThis.__privateSpawn;
  }
});
