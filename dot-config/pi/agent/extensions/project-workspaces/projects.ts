import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { projectInfo, type ProjectContextInfo } from "./store.ts";

const PROJECT_REGISTRY_VERSION = 1;
const STREAM_VERSION = 1;

function dataHome(): string { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function stateHome(): string { return process.env.XDG_STATE_HOME || path.join(homedir(), ".local", "state"); }
function now(): string { return new Date().toISOString(); }
function slugify(input: string): string { return input.replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 80); }
function readJson<T>(file: string, fallback: T): T { if (!existsSync(file)) return fallback; try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file: string, value: unknown): void { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8"); }
function isWithin(candidate: string, root: string): boolean { const rel = path.relative(root, candidate); return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel)); }

export function registryPath() { const dir = path.join(dataHome(), "pi", "projects"); return { dir, file: path.join(dir, "registry.json") }; }
export function readRegistry() { const { file } = registryPath(); const registry = readJson<any>(file, { v: PROJECT_REGISTRY_VERSION, projects: {} }); return { v: registry.v || PROJECT_REGISTRY_VERSION, projects: registry.projects && typeof registry.projects === "object" ? registry.projects : {} }; }
export function writeRegistry(registry: any) { writeJson(registryPath().file, { ...registry, v: PROJECT_REGISTRY_VERSION, updatedAt: now() }); }
export function projectMetadataPath(project: any) { return path.join(project.dir, "project.json"); }

function projectRecordFromInfo(info: ReturnType<typeof projectInfo>, input: any = {}) {
  const name = input.name?.trim?.() || path.basename(info.root) || info.id;
  return { v: PROJECT_REGISTRY_VERSION, id: info.id, name, root: info.root, dir: info.dir, aliases: [info.root], status: input.status || "active", pinned: Boolean(input.pinned), createdAt: input.createdAt || now(), updatedAt: now() };
}

export function ensureProject(workdir: string, input: any = {}) {
  const info = projectInfo(workdir);
  mkdirSync(info.dir, { recursive: true });
  const existing = readJson<any>(projectMetadataPath(info), null);
  const project = {
    ...projectRecordFromInfo(info, { ...input, createdAt: existing?.createdAt }),
    ...(existing && typeof existing === "object" ? existing : {}),
    ...(input.name ? { name: input.name } : {}),
    status: input.status || existing?.status || "active",
    pinned: input.pinned ?? existing?.pinned ?? false,
    aliases: [...new Set([info.root, ...((existing?.aliases && Array.isArray(existing.aliases)) ? existing.aliases : []), ...((input.aliases && Array.isArray(input.aliases)) ? input.aliases : [])].map((item) => path.resolve(item)))],
    updatedAt: now(),
  };
  writeJson(projectMetadataPath(info), project);
  const registry = readRegistry();
  registry.projects[project.id] = { id: project.id, name: project.name, root: project.root, dir: project.dir, aliases: project.aliases, status: project.status, pinned: project.pinned, archivedAt: project.archivedAt, updatedAt: project.updatedAt };
  writeRegistry(registry);
  return project;
}

export function hydrateProject(projectID: string) { const record = readRegistry().projects[projectID]; if (!record) return undefined; return readJson(path.join(record.dir, "project.json"), record); }
export function listProjects(status = "active") { return Object.values(readRegistry().projects).filter((p: any) => status === "all" || (p.status || "active") === status).sort((a: any, b: any) => (Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))) || String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")) || String(a.name || a.id).localeCompare(String(b.name || b.id))); }
export function updateProject(projectID: string, patch: any) { const project: any = hydrateProject(projectID); if (!project) throw new Error(`Project not found: ${projectID}`); const next = { ...project, ...patch, updatedAt: now() }; writeJson(projectMetadataPath(next), next); const registry = readRegistry(); registry.projects[next.id] = { id: next.id, name: next.name, root: next.root, dir: next.dir, aliases: next.aliases, status: next.status, pinned: Boolean(next.pinned), archivedAt: next.archivedAt, updatedAt: next.updatedAt }; writeRegistry(registry); return next; }
export function archiveProject(projectID: string) { return updateProject(projectID, { status: "archived", pinned: false, archivedAt: now() }); }
export function restoreProject(projectID: string) { return updateProject(projectID, { status: "active", archivedAt: undefined }); }
export function deleteArchivedProject(projectID: string) { const project: any = hydrateProject(projectID); if (!project) throw new Error(`Project not found: ${projectID}`); if (project.status !== "archived") throw new Error("Only archived projects can be deleted"); const registry = readRegistry(); delete registry.projects[projectID]; writeRegistry(registry); if (project.dir) rmSync(project.dir, { recursive: true, force: true }); }

export function resolveProject(workdir: string) {
  const cwd = path.resolve(workdir);
  const matches = Object.values(readRegistry().projects).filter((p: any) => (p.status || "active") === "active").flatMap((project: any) => {
    const aliases = [project.root, ...(project.aliases || [])].filter(Boolean).map((item) => path.resolve(item));
    return aliases.filter((alias) => isWithin(cwd, alias)).map((alias) => ({ project, score: alias.length }));
  }).sort((a, b) => b.score - a.score);
  if (matches[0]) return hydrateProject((matches[0].project as any).id) || matches[0].project;
  return ensureProject(cwd);
}

export function streamID(name: string) { const base = slugify(name) || "stream"; const hash = createHash("sha256").update(`${name}:${Date.now()}`).digest("hex").slice(0, 6); return `${base}--${hash}`; }
export function streamDir(project: any, id: string) { return path.join(project.dir, "streams", id); }
export function streamMetadataPath(project: any, id: string) { return path.join(streamDir(project, id), "stream.json"); }
export function createStream(project: any, input: any) { const id = input.id || streamID(input.name); const dir = streamDir(project, id); mkdirSync(path.join(dir, "plans", "active"), { recursive: true }); mkdirSync(path.join(dir, "plans", "archive"), { recursive: true }); const stream = { v: STREAM_VERSION, id, projectID: project.id, name: input.name.trim(), purpose: input.purpose, status: "active", createdAt: now(), updatedAt: now(), dir, workspace: { mode: "shared-workdir", path: project.root } }; writeJson(streamMetadataPath(project, id), stream); return stream; }
export function listStreams(project: any, status = "active") { const root = path.join(project.dir, "streams"); if (!existsSync(root)) return []; return readdirSync(root, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => readStream(project, e.name)).filter(Boolean).filter((s: any) => status === "all" || s.status === status).sort((a: any, b: any) => (Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))) || String(b.updatedAt || "").localeCompare(String(a.updatedAt || ""))); }
export function readStream(project: any, id: string) { return readJson(streamMetadataPath(project, id), undefined); }
export function updateStream(project: any, id: string, patch: any) { const stream: any = readStream(project, id); if (!stream) throw new Error(`Stream not found: ${id}`); const next = { ...stream, ...patch, updatedAt: now() }; writeJson(streamMetadataPath(project, id), next); return next; }
export function archiveStream(project: any, id: string) { return updateStream(project, id, { status: "archived", pinned: false, archivedAt: now() }); }

export function selectionPath() { const dir = path.join(stateHome(), "pi", "projects"); return { dir, file: path.join(dir, "selection.json") }; }
export function readSelection() { return readJson<any>(selectionPath().file, { projectID: undefined, streamID: undefined }); }
export function writeSelection(selection: any) { writeJson(selectionPath().file, { ...selection, updatedAt: now() }); }
export function selectProject(projectID: string) { writeSelection({ projectID, streamID: undefined }); }
export function selectStream(projectID: string, streamID: string) { writeSelection({ projectID, streamID }); }
export function clearStreamSelection() { const s = readSelection(); writeSelection({ projectID: s.projectID, streamID: undefined }); }

export function resolveContext(workdir: string): ProjectContextInfo {
  const selection = readSelection();
  const selectedProject = selection.projectID ? hydrateProject(selection.projectID) : undefined;
  const baseProject = selectedProject || resolveProject(workdir);
  const stream = selection.projectID === baseProject.id && selection.streamID ? readStream(baseProject, selection.streamID) : undefined;
  if (stream && stream.status === "active") return { scope: "stream", project: baseProject, stream, id: `${baseProject.id}/${stream.id}`, root: stream.workspace?.path || baseProject.root, dir: stream.dir, plans: path.join(stream.dir, "plans") };
  return { scope: "project", project: baseProject, id: baseProject.id, root: baseProject.root, dir: baseProject.dir, plans: path.join(baseProject.dir, "plans") };
}
