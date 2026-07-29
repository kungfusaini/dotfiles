#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const herdr = process.env.HERDR_BIN_PATH || "herdr";
const stateHome = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state");
const stateDir = path.join(stateHome, "herdr");
const statePath = path.join(stateDir, "spotify-player-toggle.json");
const workspaceLabel = "Spotify";
const paneLabel = "spotify-player";
const cwd = os.homedir();

function call(args, options = {}) {
  return execFileSync(herdr, args, {
    encoding: "utf8",
    stdio: options.stdio || ["ignore", "pipe", "pipe"],
  });
}

function jsonCall(args) {
  return JSON.parse(call(args));
}

function ensureStateDir() {
  fs.mkdirSync(stateDir, { recursive: true });
}

function readState() {
  try { return JSON.parse(fs.readFileSync(statePath, "utf8")); } catch { return {}; }
}

function writeState(state) {
  ensureStateDir();
  fs.writeFileSync(statePath, JSON.stringify({ version: 1, updatedAt: new Date().toISOString(), ...state }, null, 2) + "\n");
}

function findSpotifyWorkspace(snapshot) {
  return (snapshot.workspaces || []).find((workspace) => workspace.label === workspaceLabel);
}

function findSpotifyPane(snapshot, workspaceId) {
  const panes = (snapshot.panes || []).filter((pane) => pane.workspace_id === workspaceId);
  return panes.find((pane) => pane.label === paneLabel || pane.title === paneLabel || pane.name === paneLabel) || panes[0];
}

function paneRunsSpotify(paneId) {
  try {
    const info = jsonCall(["pane", "process-info", "--pane", paneId])?.result?.process_info;
    return (info?.foreground_processes || []).some((proc) =>
      String(proc.name || "").includes("spotify_player") ||
      String(proc.argv0 || "").includes("spotify_player")
    );
  } catch {
    return false;
  }
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function startSpotifyPlayer(paneId) {
  // If a previous attempted launch left the shell at a prompt or continuation
  // prompt, cancel it before submitting the command.
  try { call(["pane", "send-keys", paneId, "ctrl+c"], { stdio: "ignore" }); } catch {}
  sleep(100);
  call(["pane", "run", paneId, "spotify_player"], { stdio: "ignore" });
}

function liveLocation(snapshot, location) {
  if (!location?.workspaceId) return undefined;
  const workspace = (snapshot.workspaces || []).find((item) => item.workspace_id === location.workspaceId);
  if (!workspace) return undefined;
  const tab = location.tabId && (snapshot.tabs || []).find((item) => item.tab_id === location.tabId);
  return { workspaceId: workspace.workspace_id, tabId: tab?.tab_id };
}

function focusLocation(location) {
  call(["workspace", "focus", location.workspaceId], { stdio: "ignore" });
  if (location.tabId) {
    try { call(["tab", "focus", location.tabId], { stdio: "ignore" }); } catch {}
  }
}

function currentLocation(snapshot) {
  return {
    workspaceId: snapshot.focused_workspace_id,
    tabId: snapshot.focused_tab_id,
    paneId: snapshot.focused_pane_id,
  };
}

function fallbackReturnLocation(snapshot, spotifyWorkspaceId) {
  const workspace = (snapshot.workspaces || []).find((item) => item.workspace_id !== spotifyWorkspaceId && !item.focused);
  if (!workspace) return undefined;
  return { workspaceId: workspace.workspace_id, tabId: workspace.active_tab_id };
}

function ensureSpotify(snapshot) {
  let workspace = findSpotifyWorkspace(snapshot);
  let pane;

  if (!workspace) {
    const created = jsonCall(["workspace", "create", "--label", workspaceLabel, "--cwd", cwd, "--focus"]).result;
    workspace = created.workspace;
    pane = created.root_pane;
    try { call(["tab", "rename", created.tab.tab_id, "Music"], { stdio: "ignore" }); } catch {}
  } else {
    call(["workspace", "focus", workspace.workspace_id], { stdio: "ignore" });
    if (workspace.active_tab_id) {
      try { call(["tab", "focus", workspace.active_tab_id], { stdio: "ignore" }); } catch {}
    }
    snapshot = jsonCall(["api", "snapshot"]).result.snapshot;
    pane = findSpotifyPane(snapshot, workspace.workspace_id);
  }

  if (!pane) {
    snapshot = jsonCall(["api", "snapshot"]).result.snapshot;
    pane = findSpotifyPane(snapshot, workspace.workspace_id);
  }

  if (!pane) throw new Error("Could not find or create a Spotify pane");

  try { call(["pane", "rename", pane.pane_id, paneLabel], { stdio: "ignore" }); } catch {}
  if (!paneRunsSpotify(pane.pane_id)) {
    startSpotifyPlayer(pane.pane_id);
  }
  try { call(["pane", "zoom", "--pane", pane.pane_id, "--on"], { stdio: "ignore" }); } catch {}

  return { workspaceId: workspace.workspace_id, tabId: pane.tab_id, paneId: pane.pane_id };
}

function main() {
  const snapshot = jsonCall(["api", "snapshot"]).result.snapshot;
  const spotifyWorkspace = findSpotifyWorkspace(snapshot);
  const focusedWorkspaceId = snapshot.focused_workspace_id;
  const state = readState();

  if (spotifyWorkspace && focusedWorkspaceId === spotifyWorkspace.workspace_id) {
    const target = liveLocation(snapshot, state.returnLocation) || fallbackReturnLocation(snapshot, spotifyWorkspace.workspace_id);
    if (!target) return;
    focusLocation(target);
    return;
  }

  const here = currentLocation(snapshot);
  writeState({ returnLocation: here });
  ensureSpotify(snapshot);
}

try {
  main();
} catch (error) {
  console.error(`[herdr spotify] ${error?.message || error}`);
  process.exit(1);
}
