import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const VERSION = 1;
const SOURCE = "pi-herdr-workspace-sync";

function dataHome() { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function configHome() { return process.env.XDG_CONFIG_HOME || path.join(homedir(), ".config"); }
function registryPath() { return path.join(dataHome(), "herdr-pi", "workspaces.json"); }
function piRegistryPath() { return path.join(dataHome(), "pi", "projects", "registry.json"); }
function herdrSessionPath() { return path.join(configHome(), "herdr", "session.json"); }
function now() { return new Date().toISOString(); }
function slugify(input) { return String(input).replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 80); }
function stableID(root) { return `${slugify(path.basename(root) || "workspace")}--${Buffer.from(root).toString("hex").slice(-12)}`; }
function readJson(file, fallback) { if (!existsSync(file)) return fallback; try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8"); }
function canonicalRoot(value) {
  const resolved = path.resolve(String(value).replace(/^~(?=\/|$)/, homedir()));
  try { return realpathSync.native(resolved); } catch { return resolved; }
}
function fmt(value) { const home = homedir(); return value === home ? "~" : value.startsWith(`${home}/`) ? `~/${value.slice(home.length + 1)}` : value; }
function emptyRegistry() { return { version: VERSION, workspaces: {} }; }
function readShared() { const r = readJson(registryPath(), emptyRegistry()); return { version: r.version || VERSION, updatedAt: r.updatedAt, workspaces: r.workspaces && typeof r.workspaces === "object" ? r.workspaces : {} }; }
function writeShared(registry) { writeJson(registryPath(), { ...registry, version: VERSION, updatedAt: now() }); }

function upsert(registry, rootInput, patch) {
  const root = canonicalRoot(rootInput);
  const existing = registry.workspaces[root];
  const time = now();
  const aliases = [...new Set([root, ...(existing?.aliases || []), ...(patch.aliases || [])].map(canonicalRoot))];
  const next = {
    id: existing?.id || patch.id || stableID(root),
    name: patch.pi || !existing?.pi ? (patch.name || existing?.name || path.basename(root) || root) : existing.name,
    root,
    aliases,
    status: patch.status || existing?.status || "active",
    pi: patch.pi || existing?.pi,
    herdr: patch.herdr || existing?.herdr,
    createdAt: existing?.createdAt || time,
    updatedAt: time,
  };
  registry.workspaces[root] = next;
  return next;
}

function syncPiProjects(registry) {
  const pi = readJson(piRegistryPath(), { projects: {} });
  let count = 0;
  for (const project of Object.values(pi.projects || {})) {
    if (!project?.root || (project.status || "active") !== "active") continue;
    upsert(registry, project.root, {
      id: project.id,
      name: project.name || path.basename(project.root),
      aliases: [project.root, ...(project.aliases || [])],
      status: "active",
      pi: { projectID: project.id, name: project.name, root: project.root, updatedAt: project.updatedAt },
    });
    count += 1;
  }
  return count;
}

function labelMatchesRecord(label, record) {
  return Boolean(label && record && (label === record.name || label === record.pi?.name));
}
function recordMatchingWorkspace(registry, ws, fallbackRoot) {
  const records = Object.values(registry.workspaces || {});
  const tokens = ws?.tokens || {};
  if (tokens.pi_project_id) {
    const byID = records.find((record) => record.pi?.projectID === tokens.pi_project_id || record.id === tokens.pi_project_id);
    if (byID) return byID;
  }
  if (tokens.pi_project) {
    const byName = records.find((record) => record.pi?.name === tokens.pi_project || record.name === tokens.pi_project);
    if (byName) return byName;
  }
  return fallbackRoot ? registry.workspaces[canonicalRoot(fallbackRoot)] : undefined;
}

function syncHerdrSession(registry) {
  const session = readJson(herdrSessionPath(), { workspaces: [] });
  let count = 0;
  for (const ws of session.workspaces || []) {
    const activeTab = ws.tabs?.[ws.active_tab || 0];
    const firstPane = activeTab?.panes ? Object.values(activeTab.panes)[0] : undefined;
    const root = ws.identity_cwd || firstPane?.cwd;
    if (!root) continue;
    const key = canonicalRoot(root);
    const record = registry.workspaces[key];
    const label = ws.custom_name || path.basename(root) || root;
    const activeTabLabel = activeTab?.custom_name || undefined;
    const tabLabels = (ws.tabs || []).map((tab) => tab?.custom_name).filter(Boolean);
    if (!labelMatchesRecord(label, record)) continue;
    if (record?.herdr) { count += 1; continue; }
    upsert(registry, root, {
      name: label,
      aliases: [root],
      herdr: { workspaceID: ws.id, label, identityCwd: root, activeTabLabel, tabLabels, updatedAt: now() },
    });
    count += 1;
  }
  return count;
}

function herdrSnapshot() {
  const herdr = process.env.HERDR_BIN_PATH || "herdr";
  const result = spawnSync(herdr, ["api", "snapshot"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  if ((result.status ?? 1) !== 0 || !result.stdout) return undefined;
  try { return JSON.parse(result.stdout)?.result?.snapshot; } catch { return undefined; }
}

function syncHerdrSnapshot(registry) {
  const snapshot = herdrSnapshot();
  if (!snapshot) return 0;
  const panesByWorkspace = new Map();
  for (const pane of snapshot?.panes || []) {
    if (!panesByWorkspace.has(pane.workspace_id)) panesByWorkspace.set(pane.workspace_id, pane);
  }
  const tabs = snapshot?.tabs || [];
  const tabByID = new Map(tabs.map((tab) => [tab.tab_id, tab]));
  const tabLabelsByWorkspace = new Map();
  for (const tab of tabs) {
    if (!tab.workspace_id || !tab.label || /^\d+$/.test(String(tab.label))) continue;
    if (!tabLabelsByWorkspace.has(tab.workspace_id)) tabLabelsByWorkspace.set(tab.workspace_id, []);
    tabLabelsByWorkspace.get(tab.workspace_id).push(tab.label);
  }
  let count = 0;
  for (const ws of snapshot?.workspaces || []) {
    const pane = panesByWorkspace.get(ws.workspace_id);
    const activeTabLabel = tabByID.get(ws.active_tab_id)?.label;
    const tabLabels = tabLabelsByWorkspace.get(ws.workspace_id) || [];
    const paneRoot = pane?.cwd || pane?.foreground_cwd;
    const record = recordMatchingWorkspace(registry, ws, paneRoot);
    const root = record?.root || paneRoot;
    if (!root) continue;
    const label = ws.label || path.basename(root) || root;
    // Prefer explicit Pi metadata reported on the Herdr workspace; otherwise
    // only auto-link by cwd when the visible Herdr label matches the project.
    // This keeps scratch/unlinked spaces in ~ from making the Home project look open.
    if (!record || (!ws.tokens?.pi_project_id && !ws.tokens?.pi_project && !labelMatchesRecord(label, record))) continue;
    if (record?.herdr) { count += 1; continue; }
    upsert(registry, root, {
      name: record.name || label,
      aliases: [root],
      herdr: { workspaceID: ws.workspace_id, label, identityCwd: paneRoot || root, activeTabLabel, tabLabels, updatedAt: now() },
    });
    count += 1;
  }
  return count;
}

function streamDirForRecord(record) {
  const projectID = record.pi?.projectID || record.id;
  return projectID ? path.join(dataHome(), "pi", "projects", projectID, "streams") : undefined;
}

function loadStreams(record) {
  const dir = streamDirForRecord(record);
  if (!dir || !existsSync(dir)) return [];
  try {
    return readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => readJson(path.join(dir, entry.name, "stream.json"), null))
      .filter((stream) => stream && (stream.status || "active") === "active");
  } catch {
    return [];
  }
}

function streamMatchesLabel(stream, label) {
  return Boolean(label && (label === (stream.name || stream.id) || label === stream.id));
}

function openStreamsForRecord(record) {
  const streams = loadStreams(record);
  const labels = record.herdr?.tabLabels || [];
  return streams.filter((stream) => labels.some((label) => streamMatchesLabel(stream, label)));
}

function activeStreamForRecord(record) {
  const label = record.herdr?.activeTabLabel;
  if (!label || /^\d+$/.test(String(label))) return undefined;
  return loadStreams(record).find((stream) => streamMatchesLabel(stream, label));
}

function reportWorkspaceMetadata(record) {
  const workspaceID = record.herdr?.workspaceID;
  if (!workspaceID) return;
  const herdr = process.env.HERDR_BIN_PATH || "herdr";
  const activeStream = activeStreamForRecord(record);
  const openStreams = openStreamsForRecord(record);
  const openStreamNames = openStreams.map((stream) => stream.name || stream.id);
  const streamLineTokens = openStreamNames.slice(0, 6).map((name, index) => `pi_stream_${index + 1}=↳ ${name}`);
  const tokens = [
    `workspace=${record.name}`,
    record.pi?.projectID ? `pi_project_id=${record.pi.projectID}` : undefined,
    record.pi?.name ? `pi_project=${record.pi.name}` : undefined,
    activeStream ? `pi_stream_id=${activeStream.id}` : undefined,
    activeStream ? `pi_stream=${activeStream.name || activeStream.id}` : undefined,
    openStreams.length > 0 ? `pi_streams=${openStreamNames.join("  •  ")}` : undefined,
    ...streamLineTokens,
    `root=${fmt(record.pi?.root || record.root)}`,
  ].filter(Boolean);
  const clearTokens = [
    ...(activeStream ? [] : ["pi_stream", "pi_stream_id"]),
    ...(openStreams.length > 0 ? [] : ["pi_streams"]),
    ...Array.from({ length: 6 }, (_, index) => `pi_stream_${index + 1}`).filter((_, index) => index >= streamLineTokens.length),
  ];
  const args = [
    "workspace", "report-metadata", workspaceID, "--source", SOURCE,
    ...tokens.flatMap((token) => ["--token", token]),
    ...clearTokens.flatMap((token) => ["--clear-token", token]),
  ];
  spawnSync(herdr, args, { encoding: "utf8", stdio: "ignore" });
}

function cleanAgentTitle(title) {
  let value = String(title || "").trim();
  value = value.replace(/^π\s*-\s*/i, "").trim();
  const parts = value.split(/\s+-\s+/).map((part) => part.trim()).filter(Boolean);
  if (parts.length > 1) value = parts.slice(0, -1).join(" - ");
  return value;
}

function reportPaneMetadata() {
  const snapshot = herdrSnapshot();
  if (!snapshot) return 0;
  const herdr = process.env.HERDR_BIN_PATH || "herdr";
  const workspaceByID = new Map((snapshot.workspaces || []).map((workspace) => [workspace.workspace_id, workspace]));
  const tabByID = new Map((snapshot.tabs || []).map((tab) => [tab.tab_id, tab]));
  let count = 0;
  for (const agent of snapshot.agents || []) {
    if (!agent?.pane_id) continue;
    const workspace = workspaceByID.get(agent.workspace_id);
    const tab = tabByID.get(agent.tab_id);
    const project = workspace?.tokens?.pi_project || workspace?.label;
    const tabLabel = tab?.label && !/^\d+$/.test(String(tab.label)) ? tab.label : undefined;
    const stream = tabLabel || workspace?.tokens?.pi_stream;
    const title = cleanAgentTitle(agent.terminal_title_stripped || agent.terminal_title);
    const tokens = [
      project ? `pi_project=${project}` : undefined,
      stream ? `pi_stream=${stream}` : undefined,
      title ? `pi_title=${title}` : undefined,
    ].filter(Boolean);
    const clearTokens = [
      ...(project ? [] : ["pi_project"]),
      ...(stream ? [] : ["pi_stream"]),
      ...(title ? [] : ["pi_title"]),
    ];
    const args = [
      "pane", "report-metadata", agent.pane_id, "--source", SOURCE,
      ...(title ? ["--title", title] : ["--clear-title"]),
      ...tokens.flatMap((token) => ["--token", token]),
      ...clearTokens.flatMap((token) => ["--clear-token", token]),
    ];
    spawnSync(herdr, args, { encoding: "utf8", stdio: "ignore" });
    count += 1;
  }
  return count;
}

function reconcile(options = {}) {
  const registry = readShared();
  const piCount = syncPiProjects(registry);
  for (const record of Object.values(registry.workspaces)) delete record.herdr;
  const snapshotCount = syncHerdrSnapshot(registry);
  const herdrCount = snapshotCount > 0 ? snapshotCount : syncHerdrSession(registry);
  writeShared(registry);
  let paneCount = 0;
  if (options.reportMetadata !== false) {
    for (const record of Object.values(registry.workspaces)) reportWorkspaceMetadata(record);
    paneCount = reportPaneMetadata();
  }
  return { registry, piCount, herdrCount, paneCount };
}

const mode = process.argv[2] || "run";
const result = reconcile({ reportMetadata: mode !== "picker" });
console.log(JSON.stringify({
  ok: true,
  mode,
  registry: registryPath(),
  records: Object.keys(result.registry.workspaces).length,
  pi_projects: result.piCount,
  herdr_spaces: result.herdrCount,
  panes: result.paneCount,
}, null, 2));
