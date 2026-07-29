#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const stateHome = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state");
const stateDir = path.join(stateHome, "herdr");
const statePath = path.join(stateDir, "tab-mru.json");
const pidPath = path.join(stateDir, "tab-mru.pid");
const scriptPath = new URL(import.meta.url).pathname;

function now() { return new Date().toISOString(); }
function ensureDir() { fs.mkdirSync(stateDir, { recursive: true }); }
function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
}
function writeJson(file, value) {
  ensureDir();
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n");
}
function runHerdr(args) {
  return spawnSync("herdr", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}
function snapshot() {
  const result = runHerdr(["api", "snapshot"]);
  if ((result.status ?? 1) !== 0) throw new Error(result.stderr || result.stdout || "herdr api snapshot failed");
  return JSON.parse(result.stdout)?.result?.snapshot || {};
}
function currentWorkspaceID(snap = snapshot()) {
  return snap.focused_workspace_id || (snap.workspaces || []).find((workspace) => workspace.focused)?.workspace_id;
}
function currentTabID(snap = snapshot()) {
  return snap.focused_tab_id || (snap.tabs || []).find((tab) => tab.focused)?.tab_id;
}
function liveTabIDsByWorkspace(snap) {
  const map = new Map();
  for (const tab of snap.tabs || []) {
    if (!tab?.workspace_id || !tab?.tab_id) continue;
    if (!map.has(tab.workspace_id)) map.set(tab.workspace_id, new Set());
    map.get(tab.workspace_id).add(tab.tab_id);
  }
  return map;
}
function cleanHistory(history, liveIDs) {
  const out = [];
  for (const id of history || []) {
    if (!id || out.includes(id)) continue;
    if (liveIDs && !liveIDs.has(id)) continue;
    out.push(id);
  }
  return out.slice(0, 12);
}
function cleanState(state, liveByWorkspace) {
  const histories = {};
  for (const [workspaceID, history] of Object.entries(state?.histories || {})) {
    const liveIDs = liveByWorkspace?.get(workspaceID);
    const cleaned = cleanHistory(history, liveIDs);
    if (cleaned.length) histories[workspaceID] = cleaned;
  }
  return { version: 1, updatedAt: now(), histories };
}
function recordFocus(workspaceID, tabID, snap = undefined) {
  if (!workspaceID || !tabID) return readJson(statePath, { histories: {} });
  const liveByWorkspace = snap ? liveTabIDsByWorkspace(snap) : undefined;
  const state = cleanState(readJson(statePath, { histories: {} }), liveByWorkspace);
  const liveIDs = liveByWorkspace?.get(workspaceID);
  const current = state.histories[workspaceID] || [];
  state.histories[workspaceID] = cleanHistory([tabID, ...current.filter((id) => id !== tabID)], liveIDs);
  state.updatedAt = now();
  writeJson(statePath, state);
  return state;
}
function processAlive(pid) {
  if (!pid || pid === process.pid) return false;
  try { process.kill(pid, 0); return true; } catch { return false; }
}
function ensureDaemon() {
  ensureDir();
  const existing = Number(String(fs.existsSync(pidPath) ? fs.readFileSync(pidPath, "utf8") : "").trim());
  if (processAlive(existing)) return;
  const child = spawn(process.execPath, [scriptPath, "track"], {
    detached: true,
    stdio: "ignore",
    env: process.env,
  });
  child.unref();
}
async function track() {
  ensureDir();
  fs.writeFileSync(pidPath, String(process.pid) + "\n");
  process.on("exit", () => { try { if (String(fs.readFileSync(pidPath, "utf8")).trim() === String(process.pid)) fs.rmSync(pidPath); } catch {} });

  let lastSeen;
  for (;;) {
    try {
      const snap = snapshot();
      const workspaceID = currentWorkspaceID(snap);
      const tabID = currentTabID(snap);
      const key = `${workspaceID || ""}:${tabID || ""}`;
      if (workspaceID && tabID && key !== lastSeen) {
        recordFocus(workspaceID, tabID, snap);
        lastSeen = key;
      }
    } catch {
      // Herdr may be restarting. Keep the tracker alive and try again.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}
function focusLast() {
  ensureDaemon();
  const snap = snapshot();
  const workspaceID = currentWorkspaceID(snap);
  const current = currentTabID(snap);
  const liveByWorkspace = liveTabIDsByWorkspace(snap);
  const liveIDs = liveByWorkspace.get(workspaceID) || new Set();
  const state = cleanState(readJson(statePath, { histories: {} }), liveByWorkspace);
  const history = cleanHistory(state.histories[workspaceID] || [], liveIDs);
  const target = history.find((id) => id !== current);

  if (!target) {
    // Seed the tracker so the next focus change is captured, but do not jump to
    // an arbitrary tab when there is no known MRU partner yet.
    recordFocus(workspaceID, current, snap);
    console.error("No previous tab recorded yet");
    process.exit(0);
  }

  const result = runHerdr(["tab", "focus", target]);
  if ((result.status ?? 1) !== 0) {
    console.error(result.stderr || result.stdout || `Failed to focus tab ${target}`);
    process.exit(result.status || 1);
  }

  // Write the intended pair immediately so repeated prefix+l bounces between two
  // tabs even before the polling tracker observes the focus change.
  recordFocus(workspaceID, target, snap);
  const next = readJson(statePath, { histories: {} });
  next.histories ||= {};
  next.histories[workspaceID] = cleanHistory([target, current, ...(next.histories[workspaceID] || [])], liveIDs);
  next.updatedAt = now();
  writeJson(statePath, next);
}

const command = process.argv[2] || "switch";
if (command === "track") await track();
else if (command === "ensure") ensureDaemon();
else if (command === "state") console.log(JSON.stringify(readJson(statePath, { histories: {} }), null, 2));
else focusLast();
