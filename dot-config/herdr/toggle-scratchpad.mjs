#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const herdr = process.env.HERDR_BIN_PATH || "herdr";
const scratchPath = path.join(os.homedir(), "codex", "scratch.md");
const paneTitle = "scratchpad";

function call(args, options = {}) {
  return execFileSync(herdr, args, {
    encoding: "utf8",
    stdio: options.stdio || ["ignore", "pipe", "pipe"],
  });
}

function jsonCall(args) {
  return JSON.parse(call(args));
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'\\''`)}'`;
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function saveNvimBuffer(paneId) {
  // Leave insert/visual/command mode, write the scratch buffer, then give nvim
  // a moment to flush before Herdr closes the pane.
  call(["pane", "send-keys", paneId, "esc"], { stdio: "ignore" });
  call(["pane", "send-text", paneId, ":silent! update\n"], { stdio: "ignore" });
  sleep(200);
}

function main() {
  const snapshot = jsonCall(["api", "snapshot"]).result.snapshot;
  const focusedPaneId = snapshot.focused_pane_id;
  const focusedTabId = snapshot.focused_tab_id;

  if (!focusedPaneId || !focusedTabId) {
    throw new Error("Could not determine the focused Herdr pane/tab");
  }

  const scratchPanes = (snapshot.panes || []).filter((pane) => {
    if (pane.label === paneTitle) return true;
    if (pane.title === paneTitle) return true;
    if (pane.name === paneTitle) return true;
    if (pane.terminal_title === paneTitle || pane.terminal_title_stripped === paneTitle) return true;
    return false;
  });

  if (scratchPanes.length > 0) {
    for (const pane of scratchPanes) {
      saveNvimBuffer(pane.pane_id);
      call(["pane", "close", pane.pane_id], { stdio: "ignore" });
    }
    return;
  }

  fs.mkdirSync(path.dirname(scratchPath), { recursive: true });
  if (!fs.existsSync(scratchPath)) {
    fs.writeFileSync(scratchPath, "# Scratch\n\n## Todo\n- [ ] \n", "utf8");
  }

  // ratio is the original/left pane size. 0.7 leaves the new right pane at ~30%.
  const split = jsonCall([
    "pane",
    "split",
    focusedPaneId,
    "--direction",
    "right",
    "--ratio",
    "0.7",
    "--cwd",
    path.dirname(scratchPath),
    "--focus",
  ]);

  const newPane =
    split?.result?.pane?.pane_id ||
    split?.result?.pane_id ||
    split?.result?.new_pane_id ||
    split?.result?.created_pane_id;

  if (!newPane) {
    throw new Error(`Could not determine new scratch pane id from: ${JSON.stringify(split)}`);
  }

  call(["pane", "rename", newPane, paneTitle], { stdio: "ignore" });
  call([
    "pane",
    "run",
    newPane,
    `nvim ${shellQuote(scratchPath)}`,
  ], { stdio: "ignore" });
}

try {
  main();
} catch (error) {
  console.error(`[herdr scratchpad] ${error?.message || error}`);
  process.exit(1);
}
