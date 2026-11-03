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
const { default: extension, isExplicitModeKey, catalogReview } = await import("../home/config/pi/extensions/model-modes.ts");

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
    registerCommand(name, definition) { if (name === "mode") command = definition.handler; },
    registerShortcut() { assert.fail("Do not register Ctrl+M through Pi's legacy shortcut matcher"); },
    getThinkingLevel: () => "medium",
  };
  const ctx = {
    model: { provider: "openai-codex", id: "gpt-6.1-sol" },
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
      select(_title, choices, options) {
        assert.equal(choices.length, 4);
        assert.equal(options.initialIndex, 1, "Normal must be initially highlighted");
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

test("catalog review reports candidates, omissions, effort changes, and reviewed entries without changing policy", () => {
  const now = Date.now();
  const policy = { modes: [{ id: "normal", provider: "openai-codex", model: "pinned", thinkingLevel: "medium" }] };
  const catalog = {
    version: 1, provider: "openai-codex", status: "ok", checkedAt: now, lastSuccessAt: now,
    models: [{ id: "pinned", listed: true, supportedInApi: true, thinkingLevels: ["medium"] }],
  };
  catalog.models[0].thinkingLevels.push("ultra");
  assert.equal(catalogReview(policy, catalog, now).status, undefined, "Unknown safe provider efforts remain metadata only");
  const before = JSON.stringify(policy);
  catalog.models.push({ id: "candidate", listed: true, supportedInApi: true, thinkingLevels: ["high"] });
  assert.equal(catalogReview(policy, catalog, now).status, "models:review /mode-review");
  assert.match(catalogReview(policy, catalog, now).details, /Unreviewed catalog entries: candidate/);
  assert.equal(JSON.stringify(policy), before);
  const reviewedPolicy = { ...policy, reviewedModels: { "openai-codex": ["candidate"] } };
  assert.equal(catalogReview(reviewedPolicy, catalog, now).status, undefined);
  catalog.models[1].listed = false;
  assert.equal(catalogReview(policy, catalog, now).status, undefined);
  catalog.models[0].thinkingLevels = ["low"];
  assert.match(catalogReview(policy, catalog, now).details, /Reasoning levels not advertised: normal\/medium/);
  catalog.models = [];
  assert.match(catalogReview(policy, catalog, now).details, /not proof of unavailability/);
});

test("catalog checks fail visibly, retain stale evidence, and reject unsafe display data", () => {
  const now = Date.now();
  const policy = { modes: [] };
  const data = { version: 1, provider: "openai-codex", status: "ok", checkedAt: now, lastSuccessAt: now, models: [] };
  assert.equal(catalogReview(policy, undefined, now).status, "models:check unavailable");
  assert.equal(catalogReview(policy, { ...data, lastSuccessAt: now - 49 * 3600000 }, now).status, "models:stale /mode-review");
  assert.equal(catalogReview(policy, { ...data, status: "auth_expired", lastSuccessAt: null }, now).status, "models:check failed /mode-review");
  assert.equal(catalogReview(policy, { ...data, models: [{ id: "bad\x1b[31m" }] }, now).status, "models:check unavailable");
  assert.equal(catalogReview(policy, { ...data, checkedAt: now + 600000 }, now).status, "models:check unavailable");
  assert.match(catalogReview(policy, { ...data, status: "network_error" }, now).details, /Latest check failed/);
  assert.equal(catalogReview({ modes: [{ provider: "other" }] }, data, now).status, "models:partial /mode-review");
});

test("source never binds Ctrl+M with registerShortcut", () => {
  const source = readFileSync(new URL("../home/config/pi/extensions/model-modes.ts", import.meta.url), "utf8");
  assert.ok(!source.includes("registerShortcut("));
});
