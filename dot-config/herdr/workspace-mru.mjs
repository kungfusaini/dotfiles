#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const stateHome = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state");
const stateDir = path.join(stateHome, "herdr");
const statePath = path.join(stateDir, "workspace-mru.json");
const pidPath = path.join(stateDir, "workspace-mru.pid");
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
function isIgnoredWorkspace(workspace) {
  return workspace?.label === "Spotify";
}
function liveWorkspaceIDs(snap) {
  return new Set((snap.workspaces || [])
    .filter((workspace) => !isIgnoredWorkspace(workspace))
    .map((workspace) => workspace.workspace_id)
    .filter(Boolean));
}
function currentWorkspaceID(snap = snapshot()) {
  return snap.focused_workspace_id || (snap.workspaces || []).find((workspace) => workspace.focused)?.workspace_id;
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
function recordFocus(workspaceID, snap = undefined) {
  if (!workspaceID) return readJson(statePath, { history: [] });
  if (snap) {
    const workspace = (snap.workspaces || []).find((item) => item.workspace_id === workspaceID);
    if (isIgnoredWorkspace(workspace)) return readJson(statePath, { history: [] });
  }
  const liveIDs = snap ? liveWorkspaceIDs(snap) : undefined;
  const state = readJson(statePath, { history: [] });
  const history = cleanHistory([workspaceID, ...(state.history || []).filter((id) => id !== workspaceID)], liveIDs);
  const next = { version: 1, updatedAt: now(), history };
  writeJson(statePath, next);
  return next;
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
      const current = currentWorkspaceID(snap);
      if (current && current !== lastSeen) {
        recordFocus(current, snap);
        lastSeen = current;
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
  const current = currentWorkspaceID(snap);
  const liveIDs = liveWorkspaceIDs(snap);
  const state = readJson(statePath, { history: [] });
  const history = cleanHistory(state.history || [], liveIDs);
  const target = history.find((id) => id !== current);

  if (!target) {
    // Seed the tracker so the next focus change is captured, but do not jump to
    // an arbitrary workspace when there is no known MRU partner yet.
    recordFocus(current, snap);
    console.error("No previous workspace recorded yet");
    process.exit(0);
  }

  const result = runHerdr(["workspace", "focus", target]);
  if ((result.status ?? 1) !== 0) {
    console.error(result.stderr || result.stdout || `Failed to focus workspace ${target}`);
    process.exit(result.status || 1);
  }

  // Write the intended pair immediately so repeated prefix+L bounces between two
  // spaces even before the polling tracker observes the focus change.
  recordFocus(target, snap);
  const next = readJson(statePath, { history: [] });
  next.history = cleanHistory([target, current, ...(next.history || [])], liveIDs);
  next.updatedAt = now();
  writeJson(statePath, next);
}

const command = process.argv[2] || "switch";
if (command === "track") await track();
else if (command === "ensure") ensureDaemon();
else if (command === "state") console.log(JSON.stringify(readJson(statePath, { history: [] }), null, 2));
else focusLast();
