import { closeSync, existsSync, openSync, readFileSync, readSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

const PROJECT_SESSION_FILE = "sessions.json";

function dataHome() { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function stateHome() { return process.env.XDG_STATE_HOME || path.join(homedir(), ".local", "state"); }

function isObject(value) { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }

export function sanitizeText(value) {
  const raw = String(value ?? "");
  return raw
    // Strip 7-bit and 8-bit CSI/OSC control sequences.
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "")
    .replace(/\x1b\][^\x07]*\x07/g, "")
    .replace(/\x9b[0-9;?]*[ -/]*[@-~]/g, "")
    .replace(/\x9d[^\x07]*\x07/g, "")
    .replace(/[\t\r\n]/g, " ")
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function timestampForCompare(value) {
  return String(value || "");
}

function newerEntry(first, second) {
  if (!first) return second;
  const firstTime = timestampForCompare(first.updatedAt || first.createdAt);
  const secondTime = timestampForCompare(second.updatedAt || second.createdAt);
  return secondTime.localeCompare(firstTime) > 0 ? second : first;
}

function readJson(file, fallback) {
  if (!existsSync(file)) return fallback;
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return undefined;
  }
}

function projectPathForRecord(record) {
  const projectID = record?.pi?.projectID || record?.id;
  if (!projectID) return undefined;
  return path.join(dataHome(), "pi", "projects", String(projectID));
}

function sessionsFilePath(basePath, streamID) {
  return streamID ? path.join(basePath, "streams", String(streamID), PROJECT_SESSION_FILE) : path.join(basePath, PROJECT_SESSION_FILE);
}

function extractSessionRecord(rawID, rawEntry, streamID) {
  if (!isObject(rawEntry)) return undefined;
  const id = String(rawEntry.id || rawID || "").trim();
  if (!id) return undefined;
  return {
    id,
    scope: String(rawEntry.scope || (streamID ? "stream" : "project")).trim() || (streamID ? "stream" : "project"),
    projectID: rawEntry.projectID ? String(rawEntry.projectID) : undefined,
    streamID: rawEntry.streamID ? String(rawEntry.streamID) : streamID ? String(streamID) : undefined,
    createdAt: rawEntry.createdAt ? String(rawEntry.createdAt) : undefined,
    updatedAt: rawEntry.updatedAt ? String(rawEntry.updatedAt) : undefined,
    task: typeof rawEntry.task === "string" ? rawEntry.task : undefined,
    source: streamID ? `streams/${streamID}` : "project",
  };
}

function readSessionIndex(file, streamID, warnings, warn = true) {
  const raw = readJson(file);
  if (!raw) {
    if (warn) warnings.push(`Session records unavailable for this scope.`);
    return [];
  }
  if (!isObject(raw.sessions)) {
    if (warn) warnings.push(`Session records are unreadable for this scope.`);
    return [];
  }
  const entries = [];
  for (const [id, candidate] of Object.entries(raw.sessions)) {
    const normalized = extractSessionRecord(id, candidate, streamID);
    if (!normalized) continue;
    entries.push(normalized);
  }
  return entries;
}

function readAllStreamSessionIndexes(basePath, target, warnings) {
  const streamsDir = path.join(basePath, "streams");
  if (!existsSync(streamsDir)) return [];
  const entries = [];
  for (const entry of readdirSync(streamsDir, { withFileTypes: true }).filter((item) => item.isDirectory())) {
    const selected = target.scope === "stream" && entry.name === String(target.streamID);
    entries.push(...readSessionIndex(sessionsFilePath(basePath, entry.name), entry.name, warnings, selected));
  }
  return entries;
}

function projectSessionEntries(projectPath, target, warnings) {
  return readSessionIndex(sessionsFilePath(projectPath), undefined, warnings, target.scope === "project");
}

function textFromSessionContent(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.filter((part) => part?.type === "text" && typeof part.text === "string").map((part) => part.text).join(" ");
}

function readSessionDisplay(sessionID) {
  const dir = path.join(stateHome(), "pi", "agent", "sessions");
  if (!existsSync(dir)) return {};
  const fileName = readdirSync(dir).find((name) => name.endsWith(`_${sessionID}.jsonl`));
  if (!fileName) return {};
  const file = path.join(dir, fileName);
  let text = "";
  let descriptor;
  try {
    descriptor = openSync(file, "r");
    const buffer = Buffer.alloc(512 * 1024);
    const count = readSync(descriptor, buffer, 0, buffer.length, 0);
    text = buffer.subarray(0, count).toString("utf8");
  } catch {
    return { sessionFile: file };
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
  let name;
  let firstPromptRaw;
  for (const line of text.split("\n")) {
    let entry;
    try { entry = JSON.parse(line); } catch { continue; }
    if (entry?.type === "session_info" && typeof entry.name === "string") name = sanitizeText(entry.name);
    if (!firstPromptRaw && entry?.type === "message" && entry.message?.role === "user") {
      firstPromptRaw = textFromSessionContent(entry.message.content);
    }
  }
  const workerMatch = String(firstPromptRaw || "").match(/^\s*You are a hidden Pi worker started by the parent orchestrator\.\s+Worker:\s*([^\r\n]+)/);
  const workerName = workerMatch ? sanitizeText(workerMatch[1]) : undefined;
  const firstPrompt = sanitizeText(firstPromptRaw);
  return {
    title: name || (workerName ? `Worker: ${workerName}` : firstPrompt),
    sessionFile: file,
    isChildSession: Boolean(workerName),
    workerName,
  };
}

function resolveSessionOwners(projectPath, target, warnings) {
  const all = [];
  all.push(...projectSessionEntries(projectPath, target, warnings));
  all.push(...readAllStreamSessionIndexes(projectPath, target, warnings));

  const newestBySession = new Map();
  for (const entry of all) {
    const existing = newestBySession.get(entry.id);
    newestBySession.set(entry.id, existing ? newerEntry(existing, entry) : entry);
  }

  const filtered = [];
  for (const entry of newestBySession.values()) {
    if (target.projectID && entry.projectID && String(entry.projectID) !== String(target.projectID)) continue;
    if (target.scope === "project") {
      if (entry.scope !== "project") continue;
    } else if (target.scope === "stream") {
      if (entry.scope !== "stream") continue;
      if (target.streamID && entry.streamID !== String(target.streamID)) continue;
    }
    filtered.push({
      ...entry,
      ...readSessionDisplay(entry.id),
      projectID: entry.projectID || target.projectID,
      updatedAt: entry.updatedAt || entry.createdAt,
    });
  }

  return filtered
    .filter((entry) => !entry.projectID || String(entry.projectID) === String(target.projectID))
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
}

function normalizeOwnerSessionId(value) {
  if (!value || typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function readRegistryRecord(file, warnings) {
  const raw = readJson(file);
  if (!raw) {
    warnings.push(`Corrupt orchestrator registry file: ${path.basename(file)}`);
    return undefined;
  }
  return isObject(raw) ? raw : undefined;
}

export function readOrchestratorChildren(ownerSessionIds, options = {}) {
  const warnings = [];
  const ownerSet = new Set(ownerSessionIds.map((id) => String(id)).filter(Boolean));
  const registryDir = options.registryDir || path.join(stateHome(), "pi", "orchestrator", "terminals", "registry");

  if (!existsSync(registryDir)) return { children: [], warnings };

  const children = [];
  const entries = readdirSync(registryDir, { withFileTypes: true }).filter((entry) => entry.isFile() && entry.name.endsWith(".json"));

  for (const entry of entries) {
    const file = path.join(registryDir, entry.name);
    const record = readRegistryRecord(file, warnings);
    if (!record) continue;
    const ownerSessionId = normalizeOwnerSessionId(record.ownerSessionId);
    if (!ownerSessionId || !ownerSet.has(ownerSessionId)) continue;
    children.push({
      file,
      id: entry.name,
      ownerSessionId,
      name: sanitizeText(record.name),
      task: sanitizeText(record.task),
      state: record.state,
      visibility: record.visibility,
      statusMessage: sanitizeText(record.statusMessage),
      lifecycleUpdatedAt: sanitizeText(record.lifecycleUpdatedAt),
      updatedAt: sanitizeText(record.updatedAt),
      worktreeBranch: sanitizeText(record.worktreeBranch),
      structuredResult: isObject(record.structuredResult) ? record.structuredResult : undefined,
    });
  }

  return {
    children: children.sort((a, b) => {
      const aTime = a.lifecycleUpdatedAt || a.updatedAt || "";
      const bTime = b.lifecycleUpdatedAt || b.updatedAt || "";
      return String(bTime).localeCompare(String(aTime));
    }),
    warnings,
  };
}

export function getInspectionTargets(record, item) {
  if (!record || item?.herdrOnly) return undefined;
  if (item?.special === "project-scope") return { projectID: projectPathId(record), scope: "project", record, streamID: undefined };
  if (item?.special === "stream" || item?.special === "archived-stream") {
    const streamID = item.stream?.id;
    if (!streamID) return undefined;
    return { projectID: projectPathId(record), scope: "stream", streamID: String(streamID), record, streamName: item.stream?.name || item.stream?.id };
  }
  return undefined;
}

function projectPathId(record) {
  return String(record?.pi?.projectID || record?.id || "");
}

export function inspectDataForTarget(record, item, options = {}) {
  const warnings = [];
  if (!record) return { warnings: ["No project record provided."], owners: [], children: [] };
  const target = getInspectionTargets(record, item);
  if (!target) return { warnings: ["Unsupported row for inspection."], owners: [], children: [] };
  const projectPath = projectPathForRecord(record);
  if (!projectPath) return { warnings: ["No project identifier available for inspection."], owners: [], children: [] };

  const indexedSessions = resolveSessionOwners(projectPath, target, warnings);
  const result = readOrchestratorChildren(indexedSessions.map((session) => session.id), { registryDir: options.registryDir });
  warnings.push(...result.warnings);

  const childSessionByWorker = new Map(
    indexedSessions
      .filter((session) => session.isChildSession && session.workerName)
      .map((session) => [session.workerName, session]),
  );
  const childrenWithOwners = result.children.map((child) => ({
    ...child,
    owner: indexedSessions.find((session) => session.id === child.ownerSessionId),
    session: childSessionByWorker.get(child.name),
    persisted: true,
    detailsAvailable: Boolean(child.structuredResult || child.task || child.statusMessage || child.worktreeBranch || child.name),
  }));

  return {
    target,
    owners: indexedSessions.filter((session) => !session.isChildSession),
    children: childrenWithOwners,
    warnings,
  };
}

export function truncateLine(text, width) {
  const value = sanitizeText(text);
  if (!Number.isFinite(width) || width <= 0) return "";
  if (value.length <= width) return value;
  if (width <= 1) return value.slice(0, width);
  return `${value.slice(0, width - 1)}…`;
}

export function fitViewportLines(lines, rows) {
  if (!Number.isInteger(rows) || rows <= 0) return [];
  return (lines || []).slice(0, rows).map((line) => String(line));
}
