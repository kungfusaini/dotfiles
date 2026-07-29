#!/usr/bin/env node
import { spawnSync } from "node:child_process";

function run(command, args, options = {}) {
  return spawnSync(command, args, { encoding: "utf8", ...options });
}

function parseJson(stdout, label) {
  try {
    return JSON.parse(stdout);
  } catch (error) {
    console.error(`Failed to parse ${label}: ${error.message}`);
    process.exit(1);
  }
}

function workspaceOrder(agent) {
  const match = String(agent.workspace_id || "").match(/^w([A-Z]+)$/);
  if (!match) return Number.MAX_SAFE_INTEGER;
  return [...match[1]].reduce((acc, ch) => acc * 26 + (ch.charCodeAt(0) - 64), 0);
}

function paneOrder(agent) {
  const match = String(agent.pane_id || "").match(/:p(\d+)$/);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

function attentionRank(agent) {
  // Herdr priority is an attention queue. `done` means "finished and not yet
  // seen", so it ranks with attention states above ordinary working panes.
  switch (agent.agent_status || "unknown") {
    case "blocked": return 0;
    case "done": return 1;
    case "working": return 2;
    case "idle": return 3;
    default: return 4;
  }
}

const listed = run("herdr", ["agent", "list"]);
if ((listed.status ?? 1) !== 0) {
  console.error(listed.stderr || listed.stdout || "Failed to list Herdr agents");
  process.exit(listed.status || 1);
}

const agents = parseJson(listed.stdout, "Herdr agent list")?.result?.agents || [];
if (!agents.length) process.exit(0);

// The priority sidebar is attention first, then recent state changes. Do not use
// raw `agent list` order, and do not exclude the current pane: prefix+a means
// "go to the top priority row". If already there, focusing it is a harmless no-op
// and avoids accidental cycling between lower rows.
agents.sort((a, b) => {
  return attentionRank(a) - attentionRank(b)
    || Number(b.state_change_seq || 0) - Number(a.state_change_seq || 0)
    || workspaceOrder(a) - workspaceOrder(b)
    || String(a.tab_id || "").localeCompare(String(b.tab_id || ""), undefined, { numeric: true })
    || paneOrder(a) - paneOrder(b)
    || String(a.pane_id || "").localeCompare(String(b.pane_id || ""));
});

const paneID = agents[0]?.pane_id;
if (!paneID) process.exit(0);

const focused = run("herdr", ["agent", "focus", paneID], { stdio: "inherit" });
process.exit(focused.status || 0);
