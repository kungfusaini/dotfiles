#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import readline from "node:readline";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const VERSION = 1;
const PROJECT_REGISTRY_VERSION = 1;
const herdr = process.env.HERDR_BIN_PATH || "herdr";
const scriptPath = fileURLToPath(import.meta.url);
const pluginDir = path.dirname(scriptPath);
const useColor = process.stdout.isTTY && process.env.NO_COLOR !== "1";
const ansi = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
  accent: "\x1b[38;5;245m",
  muted: "\x1b[38;5;245m",
};
function c(style, text) { return useColor ? `${ansi[style]}${text}${ansi.reset}` : text; }
function clip(text, width) { const s = String(text || ""); return s.length > width ? `${s.slice(0, Math.max(0, width - 1))}…` : s; }

function dataHome() { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function registryPath() { return path.join(dataHome(), "herdr-pi", "workspaces.json"); }
function piRegistryPath() { return path.join(dataHome(), "pi", "projects", "registry.json"); }
function now() { return new Date().toISOString(); }
function slugify(input) { return String(input).replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 80); }
function readJson(file, fallback) { if (!existsSync(file)) return fallback; try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8"); }
function statePath() { return process.env.HERDR_PI_PICKER_STATE || path.join(process.env.TMPDIR || "/tmp", `herdr-pi-picker-${process.ppid}.json`); }
function readState() { return readJson(statePath(), { expandedKey: undefined }); }
function writeState(state) { writeJson(statePath(), state); }
function encodePayload(value) { return Buffer.from(JSON.stringify(value), "utf8").toString("base64url"); }
function decodePayload(value) { try { return JSON.parse(Buffer.from(String(value || ""), "base64url").toString("utf8")); } catch { return undefined; } }
function expandHome(value) { const s = String(value || "").trim(); return s === "~" ? homedir() : s.startsWith("~/") ? path.join(homedir(), s.slice(2)) : s; }
function canonicalRoot(value) { const resolved = path.resolve(expandHome(value)); try { return realpathSync.native(resolved); } catch { return resolved; } }
function displayPath(value) { const home = homedir(); const raw = value === home ? "~" : value.startsWith(`${home}/`) ? `~/${value.slice(home.length + 1)}` : value; return raw.replace(/^~\/\.dotfiles\/dot-config(?=\/|$)/, "~/.config"); }
function projectInfo(workdir) {
  const root = canonicalRoot(workdir);
  const hash = createHash("sha256").update(root).digest("hex").slice(0, 12);
  const parent = path.basename(path.dirname(root));
  const leaf = path.basename(root) || "project";
  const base = slugify(parent && parent !== path.sep ? `${parent}-${leaf}` : leaf);
  const id = `${base || "project"}--${hash}`;
  const dir = path.join(dataHome(), "pi", "projects", id);
  return { root, id, dir };
}
function ensurePiProject(rootInput, nameInput) {
  const info = projectInfo(rootInput);
  mkdirSync(info.root, { recursive: true });
  mkdirSync(info.dir, { recursive: true });
  const metaPath = path.join(info.dir, "project.json");
  const existing = readJson(metaPath, null);
  const name = String(nameInput || existing?.name || path.basename(info.root) || info.id).trim();
  const project = {
    v: PROJECT_REGISTRY_VERSION,
    id: info.id,
    name,
    root: info.root,
    dir: info.dir,
    aliases: [...new Set([info.root, ...(existing?.aliases || [])])],
    status: existing?.status || "active",
    pinned: existing?.pinned || false,
    createdAt: existing?.createdAt || now(),
    updatedAt: now(),
  };
  writeJson(metaPath, project);
  const registry = readJson(piRegistryPath(), { v: PROJECT_REGISTRY_VERSION, projects: {} });
  registry.projects ||= {};
  registry.projects[project.id] = { id: project.id, name: project.name, root: project.root, dir: project.dir, aliases: project.aliases, status: project.status, pinned: project.pinned, updatedAt: project.updatedAt };
  writeJson(piRegistryPath(), { ...registry, v: PROJECT_REGISTRY_VERSION, updatedAt: now() });
  return project;
}
function syncRegistryQuietly() {
  // Run the full sync so sidebar Space tokens (pi_stream_1, pi_streams, active
  // pi_stream) are refreshed immediately after picker actions.
  spawnSync(process.execPath, [path.join(pluginDir, "sync.mjs"), "action"], { stdio: "ignore" });
}
function loadLiveHerdrSpaceRecords() {
  const result = spawnSync(herdr, ["api", "snapshot"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  if ((result.status ?? 1) !== 0 || !result.stdout) return [];
  let snapshot;
  try { snapshot = JSON.parse(result.stdout)?.result?.snapshot; } catch { return []; }
  const paneByWorkspace = new Map();
  for (const pane of snapshot?.panes || []) {
    if (!paneByWorkspace.has(pane.workspace_id)) paneByWorkspace.set(pane.workspace_id, pane);
  }
  return (snapshot?.workspaces || [])
    .filter((ws) => ws?.workspace_id)
    .map((ws) => {
      const pane = paneByWorkspace.get(ws.workspace_id);
      const root = pane?.cwd || pane?.foreground_cwd || homedir();
      return {
        id: `herdr:${ws.workspace_id}`,
        name: ws.label || ws.workspace_id,
        root,
        status: "active",
        herdrOnly: true,
        tokens: ws.tokens || {},
        herdr: { workspaceID: ws.workspace_id, label: ws.label || ws.workspace_id, identityCwd: root, updatedAt: now() },
      };
    });
}
function loadRecords() {
  // Durable Pi/shared projects plus currently-open Herdr-only spaces. This makes
  // the picker a complete space navigator while keeping scratch spaces unlinked.
  const registry = readJson(registryPath(), { version: VERSION, workspaces: {} });
  const liveHerdrRecords = loadLiveHerdrSpaceRecords();
  const liveByID = new Map(liveHerdrRecords.map((record) => [record.herdr.workspaceID, record]));
  const openStreamsByProject = new Map();
  function rememberOpenStream(project, stream) {
    if (!project || !stream) return;
    if (!openStreamsByProject.has(project)) openStreamsByProject.set(project, new Set());
    openStreamsByProject.get(project).add(String(stream).replace(/^↳\s*/, ""));
  }
  for (const live of liveHerdrRecords) {
    const project = live.tokens?.pi_project;
    rememberOpenStream(project, live.tokens?.pi_stream);
    for (const [key, value] of Object.entries(live.tokens || {})) {
      if (/^pi_stream_[0-9]+$/.test(key)) rememberOpenStream(project, value);
    }
  }
  const projectRecords = Object.values(registry.workspaces || {})
    .filter((r) => (r.status || "active") === "active")
    .map((record) => {
      const live = (record.herdr?.workspaceID ? liveByID.get(record.herdr.workspaceID) : undefined)
        || liveHerdrRecords.find((candidate) =>
          candidate.tokens?.pi_project_id === record.pi?.projectID
          || candidate.tokens?.pi_project === record.pi?.name
          || candidate.name === record.name);
      const openStream = [...(openStreamsByProject.get(record.name) || []), ...(openStreamsByProject.get(record.pi?.name) || [])][0];
      const base = openStream ? { ...record, openStream } : record;
      if (!live) return { ...base, herdr: undefined };
      return { ...base, herdr: live.herdr };
    });
  const linkedWorkspaceIDs = new Set(projectRecords.map((record) => record.herdr?.workspaceID).filter(Boolean));
  const unlinkedLiveRecords = liveHerdrRecords.filter((record) => !linkedWorkspaceIDs.has(record.herdr.workspaceID));
  return [...projectRecords, ...unlinkedLiveRecords]
    .sort((a, b) => (Number(Boolean(b.herdr?.workspaceID)) - Number(Boolean(a.herdr?.workspaceID))) || String(a.name || "").localeCompare(String(b.name || "")));
}
function streamDirForRecord(record) {
  if (record.herdrOnly) return undefined;
  const projectID = record.pi?.projectID || record.id;
  return projectID ? path.join(dataHome(), "pi", "projects", projectID, "streams") : undefined;
}
function streamID(name) {
  const base = slugify(name) || "stream";
  const hash = createHash("sha256").update(`${name}:${Date.now()}`).digest("hex").slice(0, 6);
  return `${base}--${hash}`;
}
function createPiStream(record, nameInput) {
  const name = String(nameInput || "").trim();
  if (!name || record.herdrOnly) return undefined;
  const projectID = record.pi?.projectID || record.id;
  const projectRoot = canonicalRoot(record.pi?.root || record.root || homedir());
  const id = streamID(name);
  const dir = path.join(dataHome(), "pi", "projects", projectID, "streams", id);
  const stream = {
    v: 1,
    id,
    projectID,
    name,
    status: "active",
    createdAt: now(),
    updatedAt: now(),
    dir,
    workspace: { mode: "shared-workdir", path: projectRoot },
  };
  writeJson(path.join(dir, "stream.json"), stream);
  return stream;
}
function loadStreams(record, status = "active") {
  const dir = streamDirForRecord(record);
  if (!dir || !existsSync(dir)) return [];
  try {
    return readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => readJson(path.join(dir, entry.name, "stream.json"), null))
      .filter((stream) => stream && (status === "all" || (stream.status || "active") === status))
      .sort((a, b) => String(a.name || a.id || "").localeCompare(String(b.name || b.id || "")));
  } catch {
    return [];
  }
}
function streamMetadataPath(record, stream) {
  const dir = streamDirForRecord(record);
  return dir && stream?.id ? path.join(dir, stream.id, "stream.json") : undefined;
}
function updateStream(record, stream, patch) {
  const file = streamMetadataPath(record, stream);
  if (!file) return undefined;
  const current = readJson(file, stream);
  const next = { ...current, ...patch, updatedAt: now() };
  writeJson(file, next);
  return next;
}
function archiveStream(record, stream) {
  return updateStream(record, stream, { status: "archived", pinned: false, archivedAt: now() });
}
function restoreStream(record, stream) {
  return updateStream(record, stream, { status: "active", archivedAt: undefined });
}
function createOrFocus(record) {
  if (record.herdr?.workspaceID) {
    const focused = spawnSync(herdr, ["workspace", "focus", record.herdr.workspaceID], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    if ((focused.status ?? 1) === 0) return record.herdr.workspaceID;
  }
  const root = record.pi?.root || record.root;
  const created = spawnSync(herdr, ["workspace", "create", "--cwd", root, "--label", record.name, "--focus"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if ((created.status ?? 1) !== 0) {
    console.error(created.stderr || created.stdout || `Failed to create Herdr space for ${record.name}`);
    return false;
  }
  syncRegistryQuietly();
  try { return JSON.parse(created.stdout)?.result?.workspace?.workspace_id || true; } catch { return true; }
}
function tabList() {
  const result = spawnSync(herdr, ["tab", "list"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  if ((result.status ?? 1) !== 0 || !result.stdout) return [];
  try { return JSON.parse(result.stdout)?.result?.tabs || []; } catch { return []; }
}
function isDefaultTabLabel(label) { return !label || /^[0-9]+$/.test(String(label)); }
function ensureStreamTab(workspaceID, stream) {
  if (!workspaceID || !stream) return false;
  const label = stream.name || stream.id;
  const cwd = stream.workspace?.path || homedir();
  const tabs = tabList().filter((tab) => tab.workspace_id === workspaceID);
  const existing = tabs.find((tab) => tab.label === label);
  if (existing) {
    spawnSync(herdr, ["tab", "focus", existing.tab_id], { stdio: "ignore" });
    return true;
  }
  const active = tabs.find((tab) => tab.focused) || tabs[0];
  if (active && isDefaultTabLabel(active.label)) {
    const renamed = spawnSync(herdr, ["tab", "rename", active.tab_id, label], { encoding: "utf8", stdio: "ignore" });
    if ((renamed.status ?? 1) === 0) return true;
  }
  const created = spawnSync(herdr, ["tab", "create", "--workspace", workspaceID, "--cwd", cwd, "--label", label, "--focus"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if ((created.status ?? 1) !== 0) console.error(created.stderr || created.stdout || `Failed to create Herdr tab ${label}`);
  return (created.status ?? 1) === 0;
}
function reportStreamMetadata(workspaceID, record, stream) {
  if (!workspaceID || !record?.pi?.projectID || !stream) return;
  const tokens = [
    `workspace=${record.name}`,
    `pi_project_id=${record.pi.projectID}`,
    `pi_project=${record.pi.name || record.name}`,
    `pi_stream_id=${stream.id}`,
    `pi_stream=${stream.name || stream.id}`,
    `root=${record.pi.root || record.root}`,
  ];
  spawnSync(herdr, ["workspace", "report-metadata", workspaceID, "--source", "pi-herdr-workspace-sync", ...tokens.flatMap((token) => ["--token", token])], { stdio: "ignore" });
}
function openStream(record, stream) {
  const workspaceID = createOrFocus(record);
  if (!workspaceID) return false;
  reportStreamMetadata(workspaceID, record, stream);
  ensureStreamTab(workspaceID, stream);
  syncRegistryQuietly();
  return true;
}
function question(query) {
  return new Promise((resolve) => {
    if (process.stdin.isTTY) process.stdin.setRawMode(false);
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(query, (answer) => { rl.close(); if (process.stdin.isTTY) process.stdin.setRawMode(true); resolve(answer); });
  });
}
async function createNewProject() {
  console.clear();
  console.log("Create new shared Pi/Herdr project\n");
  const rootAnswer = await question("Project directory: ");
  if (!rootAnswer.trim()) return false;
  const root = canonicalRoot(rootAnswer);
  if (existsSync(root)) {
    try { if (!statSync(root).isDirectory()) throw new Error("not a directory"); } catch (error) { console.error(`Invalid directory: ${error.message}`); await question("Press enter to close..."); return false; }
  } else {
    const yes = String(await question(`${displayPath(root)} does not exist. Create it? [y/N] `)).trim().toLowerCase();
    if (yes !== "y" && yes !== "yes") return false;
    mkdirSync(root, { recursive: true });
  }
  const defaultName = path.basename(root) || "Project";
  const nameAnswer = await question(`Project name [${defaultName}]: `);
  const project = ensurePiProject(root, nameAnswer.trim() || defaultName);
  return createOrFocus({ name: project.name, root: project.root, pi: { projectID: project.id, name: project.name, root: project.root } });
}
async function createUnlinkedSpace() {
  console.clear();
  console.log("Create unlinked Herdr space\n");
  const nameAnswer = await question("Space name: ");
  const label = nameAnswer.trim();
  if (!label) return false;
  const created = spawnSync(herdr, ["workspace", "create", "--label", label, "--focus"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if ((created.status ?? 1) !== 0) {
    console.error(created.stderr || created.stdout || `Failed to create unlinked Herdr space ${label}`);
    return false;
  }
  // Deliberately do not sync after creating an unlinked space: by definition it
  // should remain Herdr-only until explicitly linked/imported later.
  return true;
}
async function createNewStreamFromPicker(record) {
  console.clear();
  console.log(`Create stream for ${record.name}\n`);
  const nameAnswer = await question("Stream name: ");
  const stream = createPiStream(record, nameAnswer);
  if (!stream) return false;
  return openStream(record, stream);
}
function recordKey(record) { return record.herdrOnly ? record.id : (record.pi?.projectID || record.id || record.root || record.name); }
function pickerItems(records, expandedKey, archiveExpandedKey) {
  const items = [];
  let insertedClosedSeparator = false;
  let sawOpen = false;
  for (const record of records) {
    const isOpen = Boolean(record.herdr?.workspaceID);
    if (isOpen) sawOpen = true;
    if (!isOpen && sawOpen && !insertedClosedSeparator) {
      items.push({ special: "separator" });
      insertedClosedSeparator = true;
    }
    items.push(record);
    if (expandedKey && recordKey(record) === expandedKey && !record.herdrOnly) {
      const keyValue = recordKey(record);
      const streams = loadStreams(record, "active");
      const archivedStreams = loadStreams(record, "archived");
      const archiveExpanded = archiveExpandedKey === keyValue;
      items.push({ special: "project-scope", name: "Project scope", record, hasStreams: streams.length + archivedStreams.length > 0 });
      streams.forEach((stream) => {
        items.push({ special: "stream", name: stream.name || stream.id, stream, record, branch: "├" });
      });
      items.push({ special: "new-stream", name: "Create new stream", record, branch: "├" });
      items.push({ special: "archive-toggle", name: archiveExpanded ? "Archive ▾" : "Archive ▸", record, archivedCount: archivedStreams.length, branch: "└" });
      if (archiveExpanded) {
        archivedStreams.forEach((stream, index) => {
          items.push({ special: "archived-stream", name: stream.name || stream.id, stream, record, branch: index === archivedStreams.length - 1 ? "└" : "├" });
        });
      }
    }
  }
  items.push(
    { special: "new", name: "Create new shared project", root: "" },
    { special: "unlinked", name: "Create unlinked Herdr space", root: "" },
  );
  return items;
}
function commandExists(command) {
  return (spawnSync("sh", ["-lc", `command -v ${command}`], { stdio: "ignore" }).status ?? 1) === 0;
}
const FIELD_SEP = "\x1f";
function plain(text) { return String(text).replace(/\x1b\[[0-9;]*m/g, ""); }
function padAnsi(text, width) { return text + " ".repeat(Math.max(0, width - plain(text).length)); }
function itemPayload(item) {
  if (item.special) return { special: item.special, projectKey: item.record ? recordKey(item.record) : undefined, streamID: item.stream?.id };
  return { projectKey: recordKey(item) };
}
function selectable(item) { return item?.special !== "separator"; }
function fzfLine(item, index) {
  let display;
  if (item.special === "separator") display = "";
  else if (item.special === "new") display = `${c("accent", "+")} ${padAnsi(item.name, 32)} ${c("muted", "project + space")}`;
  else if (item.special === "unlinked") display = `${c("accent", "+")} ${padAnsi(item.name, 32)} ${c("muted", "space only")}`;
  else if (item.special === "project-scope") {
    const prefix = item.hasStreams ? `${c("muted", "│")}  ` : "   ";
    display = `  ${prefix}${c("muted", item.name)}`;
  }
  else if (item.special === "stream") {
    const streamName = item.stream?.name || item.stream?.id || item.name;
    const isOpen = item.record?.openStream === streamName || item.record?.openStream === item.stream?.id;
    const name = isOpen ? streamName : c("muted", streamName);
    const branch = c("muted", `${item.branch || "├"}─`);
    display = `  ${branch} ${name}`;
  }
  else if (item.special === "new-stream") {
    const branch = c("muted", `${item.branch || "└"}─`);
    display = `  ${branch} ${c("muted", "+")} ${c("muted", item.name)}`;
  }
  else if (item.special === "archive-toggle") {
    const branch = c("muted", `${item.branch || "└"}─`);
    const count = Number(item.archivedCount || 0);
    display = `  ${branch} ${c("muted", item.name)} ${c("muted", `(${count})`)}`;
  }
  else if (item.special === "archived-stream") {
    const streamName = item.stream?.name || item.stream?.id || item.name;
    const branch = c("muted", `   ${item.branch || "└"}─`);
    display = `  ${branch} ${c("muted", streamName)}`;
  }
  else {
    const isOpen = Boolean(item.herdr?.workspaceID);
    const isClosedProject = !item.herdrOnly && !isOpen;
    const icon = item.herdrOnly ? " " : (isClosedProject ? c("muted", "") : c("accent", ""));
    const name = isClosedProject ? c("muted", item.name) : item.name;
    display = `${icon} ${padAnsi(name, 28)} ${c("muted", displayPath(item.pi?.root || item.root))}`;
  }
  return `${display}${FIELD_SEP}${encodePayload(itemPayload(item))}`;
}
function dumpForTests(items, title = "Project spaces") {
  console.log(title);
  for (const [index, item] of items.entries()) console.log(plain(fzfLine(item, index).split(FIELD_SEP)[0]));
}
function itemsFromState(records) {
  const state = readState();
  return pickerItems(records, state.expandedKey, state.archiveExpandedKey);
}
function findItem(records, payload) {
  const state = readState();
  const items = pickerItems(records, state.expandedKey, state.archiveExpandedKey);
  return items.find((item) => {
    const p = itemPayload(item);
    return p.special === payload?.special && p.projectKey === payload?.projectKey && p.streamID === payload?.streamID;
  });
}
function printList(records) { process.stdout.write(itemsFromState(records).map(fzfLine).join("\n")); }
function cacheDir() { const dir = path.join(process.env.TMPDIR || "/tmp", `herdr-pi-picker-cache-${process.ppid}`); mkdirSync(dir, { recursive: true }); return dir; }
function prepareFzfCache(records) {
  const dir = cacheDir();
  const state = readState();
  const collapsed = pickerItems(records, undefined, undefined).map(fzfLine).join("\n");
  writeFileSync(path.join(dir, "collapsed"), collapsed, "utf8");
  for (const record of records) {
    const payload = encodePayload({ projectKey: recordKey(record) });
    writeFileSync(path.join(dir, payload), pickerItems(records, recordKey(record), undefined).map(fzfLine).join("\n"), "utf8");
  }
  const expanded = state.expandedKey;
  const archiveExpanded = state.archiveExpandedKey;
  const initial = expanded ? pickerItems(records, expanded, archiveExpanded).map(fzfLine).join("\n") : collapsed;
  writeFileSync(path.join(dir, "current"), initial, "utf8");
  writeFileSync(path.join(dir, "state"), expanded ? encodePayload({ projectKey: expanded }) : "", "utf8");
  return dir;
}
function toggleExpandedFromLine(records, line) {
  const payload = decodePayload(String(line || "").split(FIELD_SEP).at(-1));
  if (!payload?.projectKey) return;
  const state = readState();
  if (payload.special === "archive-toggle") {
    writeState({ ...state, archiveExpandedKey: state.archiveExpandedKey === payload.projectKey ? undefined : payload.projectKey });
    return;
  }
  if (payload.special) return;
  const expandedKey = state.expandedKey === payload.projectKey ? undefined : payload.projectKey;
  const archiveExpandedKey = expandedKey && state.archiveExpandedKey === expandedKey ? state.archiveExpandedKey : undefined;
  writeState({ expandedKey, archiveExpandedKey });
}
function toggleAndPrintList(records, line) {
  toggleExpandedFromLine(records, line);
  printList(records);
}
function shellQuote(value) { return `'${String(value).replace(/'/g, `'\\''`)}'`; }
function displayLine(item) { return fzfLine(item, 0).split(FIELD_SEP)[0]; }
function renderPicker(items, selected) {
  const height = Math.max(10, process.stdout.rows || 18);
  const width = Math.max(50, (process.stdout.columns || 90) - 2);
  const headerLines = 2;
  const footerLines = 1;
  const rows = Math.max(4, height - headerLines - footerLines - 1);
  const start = selected >= rows ? selected - rows + 1 : 0;
  const visible = items.slice(start, start + rows);
  const lines = [];
  lines.push(`${c("muted", "Project space")}`);
  lines.push("");
  visible.forEach((item, offset) => {
    const index = start + offset;
    const pointer = index === selected ? c("muted", "›") : " ";
    const raw = plain(displayLine(item));
    const colored = displayLine(item);
    lines.push(`${pointer} ${colored}${" ".repeat(Math.max(0, width - raw.length - 2))}`);
  });
  while (lines.length < height - footerLines - 1) lines.push("");
  lines.push(c("muted", "↑/↓ j/k move   enter open/create   tab streams/archive   a archive/restore   x close   q cancel"));
  process.stdout.write("\x1b[?25l\x1b[H\x1b[J" + lines.slice(0, height).join("\n"));
}
function readKey() {
  return new Promise((resolve) => {
    const onData = (key) => { process.stdin.off("data", onData); resolve(String(key)); };
    process.stdin.on("data", onData);
  });
}
function recordForItem(item) { return item?.record || (!item?.special ? item : undefined); }
async function closeSpaceForItem(item) {
  const record = recordForItem(item);
  if (!record?.herdr?.workspaceID) {
    console.clear();
    await question("No open Herdr space linked here. Press enter...");
    return false;
  }
  const workspaceID = record.herdr.workspaceID;
  if (item?.stream) return closeStreamForItem(record, item.stream);
  const label = record.herdr.label || record.name;
  console.clear();
  const answer = String(await question(`Close Herdr space '${label}' for project '${record.name}'? [y/N] `)).trim().toLowerCase();
  if (answer !== "y" && answer !== "yes") return false;
  if (process.env.HERDR_PI_PICKER_DRY_CLOSE === "1") return true;
  const closed = spawnSync(herdr, ["workspace", "close", workspaceID], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if ((closed.status ?? 1) !== 0) {
    console.error(closed.stderr || closed.stdout || `Failed to close Herdr space ${label}`);
    await question("Press enter...");
    return false;
  }
  syncRegistryQuietly();
  return true;
}

async function closeStreamForItem(record, stream) {
  const workspaceID = record?.herdr?.workspaceID;
  const label = stream?.name || stream?.id;
  if (!workspaceID || !stream || !label) return false;
  const tabs = tabList().filter((tab) => tab.workspace_id === workspaceID);
  const tab = tabs.find((candidate) => candidate.label === label);
  console.clear();
  const onlyTab = tabs.length <= 1;
  const prompt = onlyTab
    ? `Close stream '${label}' by closing the whole '${record.name}' space? [y/N] `
    : `Close stream tab '${label}' in '${record.name}'? [y/N] `;
  const answer = String(await question(prompt)).trim().toLowerCase();
  if (answer !== "y" && answer !== "yes") return false;
  if (process.env.HERDR_PI_PICKER_DRY_CLOSE === "1") return true;

  if (onlyTab) {
    const closed = spawnSync(herdr, ["workspace", "close", workspaceID], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    if ((closed.status ?? 1) !== 0) {
      console.error(closed.stderr || closed.stdout || `Failed to close Herdr space ${record.name}`);
      await question("Press enter...");
      return false;
    }
  } else if (tab?.tab_id) {
    const closed = spawnSync(herdr, ["tab", "close", tab.tab_id], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    if ((closed.status ?? 1) !== 0) {
      console.error(closed.stderr || closed.stdout || `Failed to close Herdr tab ${label}`);
      await question("Press enter...");
      return false;
    }
  }

  if (!onlyTab) {
    spawnSync(herdr, ["workspace", "report-metadata", workspaceID, "--source", "pi-herdr-workspace-sync", "--clear-token", "pi_stream_id", "--clear-token", "pi_stream"], { stdio: "ignore" });
  }
  syncRegistryQuietly();
  return true;
}
function toggleStreamArchivedForItem(item) {
  if (!item?.record || !item?.stream) return undefined;
  const changed = item.special === "stream"
    ? archiveStream(item.record, item.stream)
    : item.special === "archived-stream"
      ? restoreStream(item.record, item.stream)
      : undefined;
  if (changed) syncRegistryQuietly();
  return changed;
}

async function runInlinePicker(initialRecords) {
  let records = initialRecords;
  const state = readState();
  let expandedKey = state.expandedKey;
  let archiveExpandedKey = state.archiveExpandedKey;
  let items = pickerItems(records, expandedKey, archiveExpandedKey);
  let selected = 0;
  if (process.stdin.isTTY) process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.setEncoding("utf8");
  try {
    while (true) {
      items = pickerItems(records, expandedKey, archiveExpandedKey);
      selected = Math.max(0, Math.min(selected, items.length - 1));
      renderPicker(items, selected);
      const key = await readKey();
      if (key === "\u0003" || key === "q" || key === "\u001b") return undefined;
      if (key === "j" || key === "\u001b[B") {
        do { selected = Math.min(items.length - 1, selected + 1); } while (!selectable(items[selected]) && selected < items.length - 1);
        continue;
      }
      if (key === "k" || key === "\u001b[A") {
        do { selected = Math.max(0, selected - 1); } while (!selectable(items[selected]) && selected > 0);
        continue;
      }
      if (key === "x") {
        const closingItem = items[selected];
        const closed = await closeSpaceForItem(closingItem);
        if (closed) {
          records = loadRecords();
          expandedKey = closingItem?.special === "stream" || closingItem?.special === "archived-stream" ? recordKey(closingItem.record) : undefined;
          archiveExpandedKey = closingItem?.special === "archived-stream" ? expandedKey : undefined;
          writeState({ expandedKey, archiveExpandedKey });
        }
        continue;
      }
      if (key === "\t") {
        const item = items[selected];
        if (item?.special === "archive-toggle" && item.record) {
          const keyValue = recordKey(item.record);
          archiveExpandedKey = archiveExpandedKey === keyValue ? undefined : keyValue;
          writeState({ expandedKey, archiveExpandedKey });
          const nextItems = pickerItems(records, expandedKey, archiveExpandedKey);
          selected = Math.max(0, nextItems.findIndex((candidate) => itemPayload(candidate).special === "archive-toggle" && itemPayload(candidate).projectKey === keyValue));
          continue;
        }
        const targetRecord = item?.record || (!item?.special ? item : undefined);
        if (targetRecord && !targetRecord.herdrOnly) {
          const keyValue = recordKey(targetRecord);
          expandedKey = expandedKey === keyValue ? undefined : keyValue;
          if (expandedKey !== keyValue || archiveExpandedKey !== keyValue) archiveExpandedKey = undefined;
          writeState({ expandedKey, archiveExpandedKey });
          const nextItems = pickerItems(records, expandedKey, archiveExpandedKey);
          const payload = itemPayload(targetRecord);
          selected = Math.max(0, nextItems.findIndex((candidate) => {
            const candidatePayload = itemPayload(candidate);
            return candidatePayload.projectKey === payload.projectKey && !candidatePayload.special;
          }));
        }
        continue;
      }
      if (key === "a") {
        const item = items[selected];
        const previousSelected = selected;
        const changed = toggleStreamArchivedForItem(item);
        if (changed) {
          records = loadRecords();
          expandedKey = recordKey(item.record);
          writeState({ expandedKey, archiveExpandedKey });
          const nextItems = pickerItems(records, expandedKey, archiveExpandedKey);
          if (item.special === "archived-stream") {
            const restoredIndex = nextItems.findIndex((candidate) => itemPayload(candidate).streamID === item.stream.id);
            selected = restoredIndex >= 0 ? restoredIndex : Math.min(previousSelected, nextItems.length - 1);
          } else {
            selected = Math.min(previousSelected, nextItems.length - 1);
          }
        }
        continue;
      }
      if ((key === "\r" || key === "\n") && selectable(items[selected])) return items[selected];
    }
  } finally {
    if (process.stdin.isTTY) process.stdin.setRawMode(false);
    process.stdout.write("\x1b[?25h\x1b[H\x1b[J");
  }
}
async function main() {
  const records = loadRecords();
  if (process.argv[2] === "--list") { printList(records); return; }
  if (process.argv[2] === "--toggle") { toggleExpandedFromLine(records, process.argv.slice(3).join(" ")); return; }
  if (process.argv[2] === "--toggle-list") { toggleAndPrintList(records, process.argv.slice(3).join(" ")); return; }
  const expandInput = process.env.PICKER_EXPAND_PROJECT;
  const expandRecord = expandInput ? records.find((item) => item.name === expandInput || item.pi?.projectID === expandInput || recordKey(item) === expandInput) : undefined;
  const expandedKey = expandRecord ? recordKey(expandRecord) : expandInput || undefined;
  const archiveExpandedKey = process.env.PICKER_EXPAND_ARCHIVE === "1" ? expandedKey : undefined;
  writeState({ expandedKey, archiveExpandedKey });
  const items = pickerItems(records, expandedKey, archiveExpandedKey);
  if (process.env.PICKER_DUMP === "1") { dumpForTests(items); return; }
  if (process.env.PICKER_DUMP_STREAMS) {
    const record = records.find((item) => item.name === process.env.PICKER_DUMP_STREAMS || item.pi?.projectID === process.env.PICKER_DUMP_STREAMS);
    const dumpArchiveExpandedKey = process.env.PICKER_EXPAND_ARCHIVE === "1" && record ? recordKey(record) : undefined;
    dumpForTests(record ? pickerItems([record], recordKey(record), dumpArchiveExpandedKey) : [], `${record?.name || "Project"} expanded`);
    return;
  }
  const item = await runInlinePicker(records);
  if (!item) process.exit(0);
  const ok = item.special === "new"
    ? await createNewProject()
    : item.special === "unlinked"
      ? await createUnlinkedSpace()
      : item.special === "stream"
        ? openStream(item.record, item.stream)
        : item.special === "archived-stream"
          ? openStream(item.record, item.stream)
          : item.special === "new-stream"
          ? await createNewStreamFromPicker(item.record)
          : item.special === "project-scope"
            ? createOrFocus(item.record)
            : createOrFocus(item);
  process.exit(ok ? 0 : 1);
}
main().catch((error) => { console.error(error?.stack || error); process.exit(1); });
