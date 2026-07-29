#!/usr/bin/env node
import { spawnSync } from "node:child_process";

function run(command, args, options = {}) {
  return spawnSync(command, args, { encoding: "utf8", ...options });
}

const listed = run("herdr", ["agent", "list"]);
if ((listed.status ?? 1) !== 0) {
  console.error(listed.stderr || listed.stdout || "Failed to list Herdr agents");
  process.exit(listed.status || 1);
}

let agents = [];
try {
  agents = JSON.parse(listed.stdout)?.result?.agents || [];
} catch (error) {
  console.error(`Failed to parse Herdr agent list: ${error.message}`);
  process.exit(1);
}

if (!agents.length) {
  console.log("No agents found. Press enter to close.");
  try { await new Promise((resolve) => process.stdin.once("data", resolve)); } catch {}
  process.exit(0);
}

const rows = agents.map((agent, index) => {
  const status = agent.agent_status || "unknown";
  const focused = agent.focused ? "*" : " ";
  const project = agent.tokens?.pi_project || agent.workspace_id || "";
  const stream = agent.tokens?.pi_stream ? `/${agent.tokens.pi_stream}` : "";
  const title = agent.title || agent.terminal_title_stripped || agent.agent || agent.pane_id;
  const cwd = agent.foreground_cwd || agent.cwd || "";
  return [agent.pane_id, `${String(index + 1).padStart(2, " ")} ${focused} ${status.padEnd(10)} ${String(project + stream).padEnd(24)} ${title}  ${cwd}`].join("\t");
}).join("\n");

const picked = spawnSync("fzf", [
  "--ansi",
  "--delimiter", "\t",
  "--with-nth", "2..",
  "--height", "100%",
  "--layout", "reverse",
  "--prompt", "Agent> ",
  "--bind", "j:down,k:up,ctrl-j:down,ctrl-k:up",
  "--header", "j/k: move · Enter: focus agent · Esc: cancel",
], { input: rows, encoding: "utf8", stdio: ["pipe", "pipe", "inherit"] });

if ((picked.status ?? 1) !== 0 || !picked.stdout.trim()) process.exit(0);

const paneID = picked.stdout.split("\t", 1)[0]?.trim();
if (!paneID) process.exit(0);

const focused = run("herdr", ["agent", "focus", paneID], { stdio: "inherit" });
process.exit(focused.status || 0);
