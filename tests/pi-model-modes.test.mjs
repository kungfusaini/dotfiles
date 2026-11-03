import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

// Only the agent-directory lookup needs a runtime import. Keep unit tests
// independent of the installed Pi package and never access real credentials.
const agentDirectory = fileURLToPath(new URL("../home/config/pi/", import.meta.url));
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "@earendil-works/pi-coding-agent") {
      return {
        url: `data:text/javascript,${encodeURIComponent(`export const getAgentDir = () => ${JSON.stringify(agentDirectory)};`)}`,
        shortCircuit: true,
      };
    }
    return nextResolve(specifier, context);
  },
});
const { default: extension, isExplicitModeKey } = await import("../home/config/pi/extensions/model-modes.ts");

test("Ctrl+M accepts explicit press encodings, never legacy Enter or release/repeat events", () => {
  for (const sequence of ["\x1b[109;5u", "\x1b[109;5:1u", "\x1b[109::57344;5u", "\x1b[109:77:57344;5u", "\x1b[27;5;109~"]) {
    assert.equal(isExplicitModeKey(sequence), true, JSON.stringify(sequence));
  }
  for (const sequence of ["\r", "\n", "\x1b[13u", "\x1b[13;1u", "\x1bOM", "m", "\x1b[109;1u", "\x1b[109;5:2u", "\x1b[109;5:3u", "\x1b[109::57344;5:3u", "\x1b[200~/mode\x1b[201~"]) {
    assert.equal(isExplicitModeKey(sequence), false, JSON.stringify(sequence));
  }
});

test("input hook preserves Enter, opens one picker, and unregisters on session replacement/shutdown", async () => {
  const events = new Map();
  let listener;
  let removals = 0;
  let dialogs = 0;
  let closePicker;
  let command;
  const api = {
    on: (name, handler) => events.set(name, handler),
    registerCommand(_name, definition) { command = definition.handler; },
    registerShortcut() { assert.fail("Do not register Ctrl+M through Pi's legacy shortcut matcher"); },
    getThinkingLevel: () => "medium",
  };
  const ctx = {
    mode: "tui",
    isIdle: () => true,
    ui: {
      setStatus() {},
      theme: { fg: (_color, text) => text },
      notify() {},
      onTerminalInput(handler) {
        listener = handler;
        return () => { removals++; listener = undefined; };
      },
      select(_title, choices) {
        assert.equal(choices.length, 4);
        dialogs++;
        return new Promise((resolve) => { closePicker = resolve; });
      },
    },
  };
  extension(api);
  await events.get("session_start")({}, ctx);
  assert.equal(listener("\r"), undefined);
  assert.equal(dialogs, 0);
  assert.deepEqual(listener("\x1b[109::57344;5u"), { consume: true });
  assert.equal(dialogs, 1);
  assert.equal(listener("\r"), undefined, "Enter must reach the picker");
  listener("\x1b[109;5u");
  assert.equal(dialogs, 1, "No nested pickers");
  closePicker(undefined);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(listener("\r"), undefined, "Enter must still submit after closing");
  const commandPending = command("", ctx);
  assert.equal(dialogs, 2);
  listener("\x1b[109;5u");
  assert.equal(dialogs, 2, "Ctrl+M must not replace the /mode dialog");
  await command("", ctx);
  assert.equal(dialogs, 2, "Repeated /mode must not replace the dialog either");
  closePicker(undefined);
  await commandPending;
  await events.get("session_start")({}, ctx);
  assert.equal(removals, 1);
  await events.get("session_shutdown")();
  assert.equal(removals, 2);
  assert.equal(listener, undefined);
});

test("source never binds Ctrl+M with registerShortcut", () => {
  const source = readFileSync(new URL("../home/config/pi/extensions/model-modes.ts", import.meta.url), "utf8");
  assert.ok(!source.includes("registerShortcut("));
});
