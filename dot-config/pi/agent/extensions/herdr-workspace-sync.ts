import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { hydrateProject, listProjects, listStreams, readStream, recordSessionOwner, resolveContext } from "./project-workspaces/projects.ts";

const REGISTRY_VERSION = 1;
const SOURCE = "pi-herdr-workspace-sync";

type SharedRecord = {
	id: string;
	name: string;
	root: string;
	aliases: string[];
	status: "active" | "archived";
	pi?: { projectID: string; name?: string; root?: string; updatedAt?: string };
	herdr?: { workspaceID: string; label?: string; identityCwd?: string; updatedAt?: string };
	createdAt: string;
	updatedAt: string;
};

type SharedRegistry = { version: number; updatedAt?: string; workspaces: Record<string, SharedRecord> };

function dataHome(): string { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function configHome(): string { return process.env.XDG_CONFIG_HOME || path.join(homedir(), ".config"); }
function registryPath(): string { return path.join(dataHome(), "herdr-pi", "workspaces.json"); }
function piRegistryPath(): string { return path.join(dataHome(), "pi", "projects", "registry.json"); }
function herdrSessionPath(): string { return path.join(configHome(), "herdr", "session.json"); }
function now(): string { return new Date().toISOString(); }
function slugify(input: string): string { return input.replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 80); }
function stableID(root: string): string { return `${slugify(path.basename(root) || "workspace")}--${Buffer.from(root).toString("hex").slice(-12)}`; }
function readJson<T>(file: string, fallback: T): T { if (!existsSync(file)) return fallback; try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file: string, value: unknown): void { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8"); }
function canonicalRoot(value: string): string {
	const resolved = path.resolve(value.replace(/^~(?=\/|$)/, homedir()));
	try { return realpathSync.native(resolved); } catch { return resolved; }
}
function fmt(value: string): string { const home = homedir(); return value === home ? "~" : value.startsWith(`${home}/`) ? `~/${value.slice(home.length + 1)}` : value; }

function emptyRegistry(): SharedRegistry { return { version: REGISTRY_VERSION, workspaces: {} }; }
function readShared(): SharedRegistry {
	const registry = readJson<SharedRegistry>(registryPath(), emptyRegistry());
	return { version: registry.version || REGISTRY_VERSION, updatedAt: registry.updatedAt, workspaces: registry.workspaces && typeof registry.workspaces === "object" ? registry.workspaces : {} };
}
function writeShared(registry: SharedRegistry): void { writeJson(registryPath(), { ...registry, version: REGISTRY_VERSION, updatedAt: now() }); }

function upsert(registry: SharedRegistry, rootInput: string, patch: Partial<SharedRecord>): SharedRecord {
	const root = canonicalRoot(rootInput);
	const existing = registry.workspaces[root];
	const time = now();
	const aliases = [...new Set([root, ...(existing?.aliases || []), ...((patch.aliases || []) as string[])].map(canonicalRoot))];
	const next: SharedRecord = {
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

function syncPiProjects(registry: SharedRegistry): number {
	const pi = readJson<any>(piRegistryPath(), { projects: {} });
	let count = 0;
	for (const project of Object.values(pi.projects || {}) as any[]) {
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

function labelMatchesRecord(label: string | undefined, record: SharedRecord | undefined): boolean {
	return Boolean(label && record && (label === record.name || label === record.pi?.name));
}

function syncHerdrSession(registry: SharedRegistry): number {
	const session = readJson<any>(herdrSessionPath(), { workspaces: [] });
	let count = 0;
	for (const ws of session.workspaces || []) {
		const activeTab = ws.tabs?.[ws.active_tab || 0];
		const firstPane = activeTab?.panes ? (Object.values(activeTab.panes) as any[])[0] : undefined;
		const root = ws.identity_cwd || firstPane?.cwd;
		if (!root) continue;
		const key = canonicalRoot(root);
		const record = registry.workspaces[key];
		const label = ws.custom_name || path.basename(root) || root;
		if (!labelMatchesRecord(label, record)) continue;
		if (record?.herdr) { count += 1; continue; }
		upsert(registry, root, {
			name: label,
			aliases: [root],
			herdr: { workspaceID: ws.id, label, identityCwd: root, updatedAt: now() },
		});
		count += 1;
	}
	return count;
}

function syncHerdrSnapshot(registry: SharedRegistry): number {
	const herdr = process.env.HERDR_BIN_PATH || "herdr";
	const result = spawnSync(herdr, ["api", "snapshot"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
	if ((result.status ?? 1) !== 0 || !result.stdout) return 0;
	let snapshot: any;
	try { snapshot = JSON.parse(result.stdout)?.result?.snapshot; } catch { return 0; }
	const panesByWorkspace = new Map<string, any>();
	for (const pane of snapshot?.panes || []) {
		if (!panesByWorkspace.has(pane.workspace_id)) panesByWorkspace.set(pane.workspace_id, pane);
	}
	let count = 0;
	for (const ws of snapshot?.workspaces || []) {
		const pane = panesByWorkspace.get(ws.workspace_id);
		const root = pane?.cwd || pane?.foreground_cwd;
		if (!root) continue;
		const key = canonicalRoot(root);
		const record = registry.workspaces[key];
		const label = ws.label || path.basename(root) || root;
		if (!labelMatchesRecord(label, record)) continue;
		if (record?.herdr) { count += 1; continue; }
		upsert(registry, root, {
			name: label,
			aliases: [root],
			herdr: { workspaceID: ws.workspace_id, label, identityCwd: root, updatedAt: now() },
		});
		count += 1;
	}
	return count;
}

function currentHerdrWorkspaceID(): string | undefined {
	if (process.env.HERDR_WORKSPACE_ID) return process.env.HERDR_WORKSPACE_ID;
	const pane = process.env.HERDR_PANE_ID;
	const match = pane?.match(/^(w[^:]+):/);
	return match?.[1];
}

function reportMetadata(ctx: ExtensionContext, registry: SharedRegistry): void {
	if (process.env.HERDR_ENV !== "1") return;
	const workspaceID = currentHerdrWorkspaceID();
	if (!workspaceID) return;

	const workspace = currentHerdrWorkspace();
	const existingTokens = workspace?.tokens && typeof workspace.tokens === "object" ? workspace.tokens as Record<string, string> : {};
	const linkedProject = exactProjectByName(workspace?.label) || findProjectByToken(existingTokens);
	const linkedStream = linkedProject ? findStreamByToken(linkedProject, existingTokens, workspace?.label) : undefined;
	// Once a Herdr Space has Pi project/stream identity, keep that identity stable.
	// The pane's shell cwd is only a first-time fallback and must not relink the
	// Space when the user runs `cd` inside the terminal.
	const info = linkedProject
		? {
			scope: linkedStream ? "stream" as const : "project" as const,
			project: linkedProject,
			stream: linkedStream,
			id: linkedStream ? `${linkedProject.id}/${linkedStream.id}` : linkedProject.id,
			root: linkedStream?.workspace?.path || linkedProject.root,
			dir: linkedStream?.dir || linkedProject.dir,
		  }
		: resolveContext(ctx.cwd, { sessionID: ctx.sessionManager.getSessionId() });

	const root = canonicalRoot(info.root);
	const record = registry.workspaces[root] || upsert(registry, root, {
		name: info.project?.name || path.basename(root),
		pi: info.project ? { projectID: info.project.id, name: info.project.name, root: info.project.root, updatedAt: info.project.updatedAt } : undefined,
	});
	const herdr = process.env.HERDR_BIN_PATH || "herdr";
	const tokens = [
		"workspace=" + (workspace?.label || record.name),
		info.project ? "pi_project_id=" + info.project.id : undefined,
		"pi_project=" + (info.project?.name || info.project?.id || record.name),
		"root=" + fmt(info.project?.root || root),
		info.stream ? "pi_stream_id=" + info.stream.id : undefined,
		info.stream ? "pi_stream=" + (info.stream.name || info.stream.id) : undefined,
	].filter(Boolean) as string[];
	const clearStreamTokens = info.stream ? [] : ["--clear-token", "pi_stream_id", "--clear-token", "pi_stream"];
	const args = ["workspace", "report-metadata", workspaceID, "--source", SOURCE, ...tokens.flatMap((token) => ["--token", token]), ...clearStreamTokens];
	spawnSync(herdr, args, { encoding: "utf8", stdio: "ignore" });
}

function cleanAgentTitle(title: string | undefined): string {
	let value = String(title || "").trim();
	value = value.replace(/^π\s*-\s*/i, "").trim();
	const parts = value.split(/\s+-\s+/).map((part) => part.trim()).filter(Boolean);
	if (parts.length > 1) value = parts.slice(0, -1).join(" - ");
	return value;
}

function reportPaneMetadata(): number {
	if (process.env.HERDR_ENV !== "1") return 0;
	const snapshot = herdrSnapshot();
	if (!snapshot) return 0;
	const herdr = process.env.HERDR_BIN_PATH || "herdr";
	const workspaceByID = new Map((snapshot.workspaces || []).map((workspace: any) => [workspace.workspace_id, workspace]));
	const tabByID = new Map((snapshot.tabs || []).map((tab: any) => [tab.tab_id, tab]));
	let count = 0;
	for (const agent of snapshot.agents || []) {
		if (!agent?.pane_id) continue;
		const workspace: any = workspaceByID.get(agent.workspace_id);
		const tab: any = tabByID.get(agent.tab_id);
		const project = workspace?.tokens?.pi_project || workspace?.label;
		const tabLabel = tab?.label && !/^\d+$/.test(String(tab.label)) ? tab.label : undefined;
		const stream = tabLabel || workspace?.tokens?.pi_stream;
		const title = cleanAgentTitle(agent.terminal_title_stripped || agent.terminal_title);
		const tokens = [
			project ? `pi_project=${project}` : undefined,
			stream ? `pi_stream=${stream}` : undefined,
			title ? `pi_title=${title}` : undefined,
		].filter(Boolean) as string[];
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

function reconcile(): { registry: SharedRegistry; piCount: number; herdrCount: number; path: string } {
	const registry = readShared();
	const piCount = syncPiProjects(registry);
	for (const record of Object.values(registry.workspaces)) delete record.herdr;
	const snapshotCount = syncHerdrSnapshot(registry);
	const herdrCount = snapshotCount > 0 ? snapshotCount : syncHerdrSession(registry);
	writeShared(registry);
	return { registry, piCount, herdrCount, path: registryPath() };
}

function herdrSnapshot(): any | undefined {
	const herdr = process.env.HERDR_BIN_PATH || "herdr";
	const result = spawnSync(herdr, ["api", "snapshot"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
	if ((result.status ?? 1) !== 0 || !result.stdout) return undefined;
	try { return JSON.parse(result.stdout)?.result?.snapshot; } catch { return undefined; }
}

function currentHerdrWorkspace(): any | undefined {
	if (process.env.HERDR_ENV !== "1") return undefined;
	const workspaceID = currentHerdrWorkspaceID();
	if (!workspaceID) return undefined;
	const snapshot = herdrSnapshot();
	return (snapshot?.workspaces || []).find((item: any) => item?.workspace_id === workspaceID);
}

function exactProjectByName(name: string | undefined): any | undefined {
	if (!name) return undefined;
	const project = (listProjects("active") as any[]).find((item) => item.name === name || item.id === name);
	return project ? hydrateProject(project.id) || project : undefined;
}

function findProjectByToken(tokens: Record<string, string>): any | undefined {
	const id = tokens.pi_project_id;
	if (id) return hydrateProject(id);
	const root = tokens.root ? canonicalRoot(tokens.root) : undefined;
	if (root) {
		const byRoot = (listProjects("active") as any[]).find((project) => [project.root, ...(project.aliases || [])].filter(Boolean).some((alias: string) => canonicalRoot(alias) === root));
		if (byRoot) return hydrateProject(byRoot.id) || byRoot;
	}
	const name = tokens.pi_project || tokens.workspace;
	if (name) return exactProjectByName(name);
	return undefined;
}

function findStreamByToken(project: any, tokens: Record<string, string>, workspaceLabel?: string): any | undefined {
	const id = tokens.pi_stream_id;
	if (id) return readStream(project, id);
	const streams = listStreams(project, "active") as any[];
	const name = tokens.pi_stream;
	if (name) return streams.find((stream) => stream.id === name || stream.name === name);
	if (workspaceLabel) {
		const byWorkspaceLabel = streams.find((stream) => stream.id === workspaceLabel || stream.name === workspaceLabel);
		if (byWorkspaceLabel) return byWorkspaceLabel;
	}
	// If the project only has one active stream, treat the Herdr Space as linked to
	// that stream. This preserves project-scope only when there is real ambiguity.
	return streams.length === 1 ? streams[0] : undefined;
}

function updateSessionHeaderCwd(ctx: ExtensionContext, targetCwd: string): void {
	const file = ctx.sessionManager.getSessionFile();
	if (!file || !existsSync(file)) return;
	try {
		const lines = readFileSync(file, "utf8").split(/\n/);
		if (!lines[0]?.trim()) return;
		const header = JSON.parse(lines[0]);
		if (header?.type !== "session" || header.cwd === targetCwd) return;
		header.cwd = targetCwd;
		lines[0] = JSON.stringify(header);
		writeFileSync(file, lines.join("\n"), "utf8");
	} catch {
		// Best effort only. Runtime cwd retargeting below is the authoritative piece
		// for the current process; header rewrite preserves future resume behavior.
	}
}

function retargetPiCwd(ctx: ExtensionContext, targetRoot: string | undefined): void {
	if (!targetRoot) return;
	const targetCwd = canonicalRoot(targetRoot);
	if (!existsSync(targetCwd)) return;
	try { process.chdir(targetCwd); } catch { return; }
	try { (ctx.sessionManager as any).cwd = targetCwd; } catch {}
	try { (ctx as any).cwd = targetCwd; } catch {}
	updateSessionHeaderCwd(ctx, targetCwd);
}

function isDefaultTabLabel(label: string | undefined): boolean {
	return !label || /^[0-9]+$/.test(label);
}

function ensureHerdrStreamTab(stream: any): void {
	if (process.env.HERDR_ENV !== "1" || !stream) return;
	const workspaceID = currentHerdrWorkspaceID();
	if (!workspaceID) return;
	const snapshot = herdrSnapshot();
	const workspace = (snapshot?.workspaces || []).find((item: any) => item?.workspace_id === workspaceID);
	const tabs = (snapshot?.tabs || []).filter((tab: any) => tab?.workspace_id === workspaceID);
	const label = stream.name || stream.id;
	if (!label || tabs.some((tab: any) => tab.label === label)) return;

	const herdr = process.env.HERDR_BIN_PATH || "herdr";
	const activeTab = tabs.find((tab: any) => tab.tab_id === workspace?.active_tab_id) || tabs.find((tab: any) => tab.focused);
	if (activeTab && isDefaultTabLabel(activeTab.label)) {
		spawnSync(herdr, ["tab", "rename", activeTab.tab_id, label], { encoding: "utf8", stdio: "ignore" });
		return;
	}
	spawnSync(herdr, ["tab", "create", "--workspace", workspaceID, "--cwd", stream.workspace?.path || process.cwd(), "--label", label, "--no-focus"], { encoding: "utf8", stdio: "ignore" });
}

function attachSessionFromHerdr(ctx: ExtensionContext): { attached: boolean; project?: any; stream?: any } {
	const sessionID = ctx.sessionManager.getSessionId();
	if (!sessionID) return { attached: false };
	const workspace = currentHerdrWorkspace();
	if (!workspace) return { attached: false };
	const tokens = workspace.tokens && typeof workspace.tokens === "object" ? workspace.tokens as Record<string, string> : {};
	// Prefer an exact Herdr Space label match over stale metadata. This lets a Space
	// named "Config" attach to the Pi project named "Config" even if the pane cwd is
	// still ~ or old tokens say Home.
	const project = exactProjectByName(workspace.label) || findProjectByToken(tokens);
	if (!project) return { attached: false };
	const stream = findStreamByToken(project, tokens, workspace.label);
	recordSessionOwner(project, sessionID, stream?.id, { scope: stream ? "stream" : "project", projectID: project.id, streamID: stream?.id });
	retargetPiCwd(ctx, stream?.workspace?.path || project.root);
	ensureHerdrStreamTab(stream);
	return { attached: true, project, stream };
}

export default function herdrWorkspaceSync(pi: ExtensionAPI) {
	pi.registerCommand("workspace-sync", {
		description: "Sync durable Pi projects and Herdr spaces into a shared registry",
		handler: async (_args, ctx) => {
			const result = reconcile();
			reportMetadata(ctx, result.registry);
			const paneCount = reportPaneMetadata();
			ctx.ui.notify(`Workspace sync complete: ${Object.keys(result.registry.workspaces).length} records (${result.piCount} Pi projects, ${result.herdrCount} Herdr spaces, ${paneCount} agent panes).\nRegistry: ${fmt(result.path)}`, "info");
		},
	});

	pi.on("session_start", async (_event, ctx) => {
		attachSessionFromHerdr(ctx);
		const result = reconcile();
		reportMetadata(ctx, result.registry);
		reportPaneMetadata();
	});

	pi.on("agent_start", (_event, ctx) => {
		attachSessionFromHerdr(ctx);
		const result = reconcile();
		reportMetadata(ctx, result.registry);
		reportPaneMetadata();
	});
}
