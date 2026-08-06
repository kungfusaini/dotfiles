import { existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { SessionManager, type ExtensionAPI, type ExtensionCommandContext, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { matchesKey, type SelectItem, SelectList, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import {
	archiveStream,
	createStream,
	ensureProject,
	listProjects,
	listStreams,
	recordSessionOwner,
	renameProject,
	renameStream,
	restoreStream,
	resolveContext,
	resolveSessionOwner,
} from "./projects.ts";
import { ensureStore, type ProjectContextInfo } from "./store.ts";
import {
	WORKLOG_VERSION,
	appendWorklogEntry,
	ensureWorklog,
	readAllEntries,
	validateWorklogEntry,
	withWorklogPath,
	worklogRecap,
	worklogReminder,
	type WorklogEntry,
} from "./worklog.ts";

const WORKSPACE_CONTEXT_EVENT = "pi:workspace-context:resolve";

interface WorkspaceContextRequest {
	cwd?: string;
	sessionID?: string;
	result?: unknown;
}

function contextInfo(cwd: string, sessionID?: string): ProjectContextInfo {
	return ensureStore(resolveContext(cwd, { sessionID }));
}

function contextInfoFromCtx(ctx: ExtensionContext): ProjectContextInfo {
	return contextInfo(ctx.cwd, ctx.sessionManager.getSessionId());
}

function formatHomePath(value: string | undefined): string {
	if (!value) return "";
	const home = process.env.HOME || process.env.USERPROFILE;
	if (!home) return value;
	if (value === home) return "~";
	if (value.startsWith(`${home}/`)) return `~/${value.slice(home.length + 1)}`;
	return value;
}

function expandHomePath(value: string): string {
	const trimmed = value.trim();
	if (trimmed === "~") return process.env.HOME || trimmed;
	if (trimmed.startsWith("~/")) return `${process.env.HOME || ""}/${trimmed.slice(2)}`;
	return trimmed;
}

function workspaceLabel(info: ProjectContextInfo): string {
	const project = info.project?.name || info.project?.id || info.id;
	const stream = info.stream ? ` Stream: ${info.stream.name || info.stream.id}` : "";
	return `Project: ${project}${stream}`;
}

function workspaceDescription(info: ProjectContextInfo): string {
	return [
		`Scope: ${info.scope}`,
		`Project: ${info.project?.name || info.project?.id || info.id}`,
		info.stream ? `Stream: ${info.stream.name || info.stream.id}` : "Stream: Project scope",
		`Root: ${formatHomePath(info.root)}`,
	].join("\n");
}

function worklogInfoFromOwner(owner: any): ProjectContextInfo | undefined {
	if (!owner?.project) return undefined;
	if (owner.scope === "stream" && owner.stream) {
		return ensureStore({
			scope: "stream",
			project: owner.project,
			stream: owner.stream,
			id: `${owner.project.id}/${owner.stream.id}`,
			root: owner.stream.workspace?.path || owner.project.root,
			dir: owner.stream.dir,
		});
	}
	if (owner.scope === "project") {
		return ensureStore({
			scope: "project",
			project: owner.project,
			id: owner.project.id,
			root: owner.project.root,
			dir: owner.project.dir,
		});
	}
	return undefined;
}

function worklogInfoFromCtx(ctx: ExtensionContext): ProjectContextInfo | undefined {
	return worklogInfoFromOwner(resolveSessionOwner(ctx.sessionManager.getSessionId()));
}

function textResult(text: string, details: Record<string, unknown> = {}) {
	return { content: [{ type: "text" as const, text }], details };
}

function shouldRollupStreamEntry(entry: WorklogEntry, projectImpact?: boolean): boolean {
	return projectImpact === true || entry.type === "start" || entry.type === "finish" || entry.type === "mistake";
}

function streamRollupSource(info: ProjectContextInfo, entry: WorklogEntry) {
	return {
		kind: "stream-rollup",
		streamID: info.stream?.id,
		streamName: info.stream?.name,
		streamLog: withWorklogPath(info).log,
		streamEntryTime: entry.time,
		streamEntryType: entry.type,
		streamEntrySummary: entry.summary,
	};
}

function alreadyRolledUp(projectInfo: ProjectContextInfo, source: ReturnType<typeof streamRollupSource>): boolean {
	return readAllEntries(withWorklogPath(projectInfo).log).some((entry) => {
		const existing = entry.source;
		return existing?.kind === source.kind
			&& existing.streamID === source.streamID
			&& existing.streamEntryTime === source.streamEntryTime
			&& existing.streamEntryType === source.streamEntryType
			&& existing.streamEntrySummary === source.streamEntrySummary;
	});
}

function appendStreamRollup(info: ProjectContextInfo, entry: WorklogEntry, projectImpact?: boolean): WorklogEntry | { skipped: true } | undefined {
	if (info.scope !== "stream" || !info.project || !info.stream) return undefined;
	if (!shouldRollupStreamEntry(entry, projectImpact)) return undefined;

	const projectInfo = ensureStore({
		scope: "project" as const,
		project: info.project,
		id: info.project.id,
		root: info.project.root,
		dir: info.project.dir,
	});
	const source = streamRollupSource(info, entry);
	if (alreadyRolledUp(projectInfo, source)) return { skipped: true };

	const streamName = info.stream.name || info.stream.id;
	const rollup: WorklogEntry = {
		v: WORKLOG_VERSION,
		time: new Date().toISOString(),
		session: entry.session,
		project: projectInfo.project?.id || projectInfo.id,
		root: projectInfo.root,
		scope: "project",
		stream: { id: info.stream.id, name: info.stream.name },
		type: entry.type,
		summary: `Stream ${streamName}: ${entry.summary}`,
		task: entry.task,
		next: entry.next,
		reason: entry.reason,
		lesson: entry.lesson,
		blocker: entry.blocker,
		result: entry.result,
		plan: entry.plan,
		files: entry.files,
		source,
	};
	appendWorklogEntry(projectInfo, rollup);
	return rollup;
}

export default function projectWorkspacesExtension(pi: ExtensionAPI) {
	pi.events.on(WORKSPACE_CONTEXT_EVENT, (request: WorkspaceContextRequest) => {
		if (request.result || !request.cwd || !request.sessionID) return;
		const info = resolveContext(request.cwd, { sessionID: request.sessionID });
		request.result = {
			scope: info.scope,
			id: info.id,
			root: info.root,
			dir: info.dir,
			projectID: info.project?.id || info.id,
			streamID: info.stream?.id,
		};
	});

	pi.registerTool({
		name: "worklog_recap",
		label: "Worklog Recap",
		description: "Fetch the current selected Pi project or stream worklog recap on demand. Use for orientation, resume, continue, or current-state questions instead of relying on volatile recap text in the system prompt.",
		promptSnippet: "Fetch scoped project/stream worklog recap on demand",
		promptGuidelines: [
			"Use worklog_recap when the user asks where we are, what the current state is, what we were doing, to resume, or to continue work from durable history.",
			"Do not proactively read parent, sibling, or other project logs unless the user explicitly asks for broader history.",
		],
		parameters: Type.Object({
			limit: Type.Optional(Type.Number({ description: "Maximum recent entries to include in the recap; default 12, max 50" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = worklogInfoFromCtx(ctx);
			if (!info) return textResult("Worklog is not active because this session is not attached to a Pi project or stream.", { active: false });
			const limit = typeof params.limit === "number" ? params.limit : undefined;
			const withLog = ensureWorklog(info);
			return textResult(worklogRecap(info, limit), { active: true, scope: info.scope, path: withLog.log, limit: limit || 12 });
		},
	});

	pi.registerTool({
		name: "worklog_append",
		label: "Append Worklog",
		description: "Append a durable progress, decision, blocker, mistake, finish, next-step, or note event to the current selected Pi project or stream worklog. In stream scope, high-signal entries roll up to the parent project log.",
		promptSnippet: "Append scoped project/stream continuity entries",
		promptGuidelines: [
			"Use worklog_append for meaningful progress, decisions, blockers, mistakes, finishes, or next steps in the active project or stream.",
			"In stream scope, set worklog_append projectImpact=true when an entry affects project-level direction, architecture, release state, workflow, or future agents.",
		],
		parameters: Type.Object({
			type: Type.String({ description: "Event type: start, progress, decision, mistake, stuck, finish, next, or note" }),
			summary: Type.String({ description: "Short summary text" }),
			task: Type.Optional(Type.String({ description: "Optional task context" })),
			next: Type.Optional(Type.String({ description: "Next action or handoff context" })),
			reason: Type.Optional(Type.String({ description: "Reason for a decision or mistake" })),
			lesson: Type.Optional(Type.String({ description: "Lesson learned for a mistake" })),
			blocker: Type.Optional(Type.String({ description: "What is blocking progress" })),
			result: Type.Optional(Type.String({ description: "Result summary" })),
			files: Type.Optional(Type.Array(Type.String(), { description: "Files related to this entry" })),
			plan: Type.Optional(Type.String({ description: "Optional active plan id or path this entry relates to" })),
			session: Type.Optional(Type.String({ description: "Optional session id override" })),
			projectImpact: Type.Optional(Type.Boolean({ description: "Set true when a stream entry should roll up to project memory" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = worklogInfoFromCtx(ctx);
			if (!info) return textResult("Worklog is not active because this session is not attached to a Pi project or stream.", { active: false });

			const type = params.type.trim().toLowerCase();
			const validationError = validateWorklogEntry({ ...params, type });
			if (validationError) return textResult(`❌ ${validationError}`, { active: true, error: validationError });
			const withLog = ensureWorklog(info);
			const entry: WorklogEntry = {
				v: WORKLOG_VERSION,
				time: new Date().toISOString(),
				session: params.session || ctx.sessionManager.getSessionId() || "unknown",
				project: info.project?.id || info.id,
				root: info.root,
				scope: info.scope,
				stream: info.stream ? { id: info.stream.id, name: info.stream.name } : undefined,
				type: type as WorklogEntry["type"],
				summary: params.summary,
				task: params.task,
				next: params.next,
				reason: params.reason,
				lesson: params.lesson,
				blocker: params.blocker,
				result: params.result,
				plan: params.plan,
				projectImpact: params.projectImpact === true ? true : undefined,
				files: params.files,
			};
			appendWorklogEntry(info, entry);
			const rollup = appendStreamRollup(info, entry, params.projectImpact);
			return textResult([
				`${entry.type}: ${entry.summary}`,
				`Worklog: ${withLog.log}`,
				info.scope === "stream" ? `Project rollup: ${rollup && !("skipped" in rollup) ? rollup.summary : (rollup as any)?.skipped ? "already recorded" : "no"}` : undefined,
			].filter(Boolean).join("\n"), { active: true, scope: info.scope, path: withLog.log, rollup });
		},
	});

	function updateStatus(ctx: ExtensionContext): void {
		const owner = resolveSessionOwner(ctx.sessionManager.getSessionId());
		if (owner) {
			const info = contextInfoFromCtx(ctx);
			ctx.ui.setStatus("workspace", ctx.ui.theme.fg("muted", workspaceLabel(info)));
		} else {
			ctx.ui.setStatus("workspace", undefined);
		}
	}

	type ChooseItems = SelectItem[] | (() => SelectItem[]);
	type ChooseFromItemsOptions = {
		renameSelected?: boolean;
		actionSelected?: (item: SelectItem) => string | undefined;
		actionHelp?: string;
		toggleSelected?: (item: SelectItem) => boolean | void;
		toggleHelp?: string;
	};

	async function chooseFromItems(ctx: ExtensionContext, title: string, items: ChooseItems, options: ChooseFromItemsOptions = {}): Promise<string | null> {
		if (ctx.mode !== "tui") return null;
		const selected = await ctx.ui.custom<string | null>((tui, theme, keybindings, done) => {
			let query = "";
			let renameTarget: SelectItem | null = null;
			let renameText = "";
			let selectedValue: string | undefined;

			function allItems(): SelectItem[] {
				return typeof items === "function" ? items() : items;
			}

			function itemMatches(item: SelectItem, filter: string): boolean {
				const normalized = filter.trim().toLowerCase();
				if (!normalized) return true;
				const haystack = [item.label, item.description, item.value].filter(Boolean).join(" ").toLowerCase();
				return normalized.split(/\s+/).every((part) => haystack.includes(part));
			}

			function filteredItems(): SelectItem[] {
				return allItems().filter((item) => itemMatches(item, query));
			}

			function typedQueryValue(): string | undefined {
				const trimmed = query.trim();
				return trimmed ? `__query__:${trimmed}` : undefined;
			}

			function renameValue(item: SelectItem, name: string): string {
				return `__rename__:${JSON.stringify({ value: item.value, name })}`;
			}

			function startRename(): void {
				if (!options.renameSelected) return;
				const selected = list.getSelectedItem();
				if (!selected || selected.value.startsWith("__")) return;
				renameTarget = selected;
				renameText = selected.label.replace(/\s+\(current\)$/i, "").trim();
				tui.requestRender();
			}

			function printableChar(data: string): string | undefined {
				return data.length === 1 && data >= " " && data !== "\x7f" ? data : undefined;
			}

			function makeList(preferredValue = selectedValue): SelectList {
				const currentItems = filteredItems();
				const next = new SelectList(currentItems, Math.min(Math.max(currentItems.length, 1), 14), {
					selectedPrefix: (s: string) => theme.fg("muted", s),
					selectedText: (s: string) => theme.fg("text", s),
					description: (s: string) => theme.fg("muted", s),
					scrollInfo: (s: string) => theme.fg("dim", s),
					noMatch: (s: string) => theme.fg("warning", s),
				});
				if (preferredValue) {
					const index = currentItems.findIndex((item) => item.value === preferredValue);
					if (index >= 0) next.setSelectedIndex(index);
				}
				next.onSelectionChange = (item) => { selectedValue = item.value; };
				next.onSelect = (item) => done(String(item.value));
				next.onCancel = () => done(null);
				return next;
			}

			let list = makeList();
			selectedValue = list.getSelectedItem()?.value;

			function refreshList(preferredValue = list.getSelectedItem()?.value || selectedValue): void {
				selectedValue = preferredValue;
				list = makeList(preferredValue);
				tui.requestRender();
			}

			function panelLine(content: string, innerWidth: number, paddingX = 3): string {
				const contentWidth = Math.max(1, innerWidth - paddingX * 2);
				const clipped = truncateToWidth(content, contentWidth, "…");
				const padding = " ".repeat(Math.max(0, contentWidth - visibleWidth(clipped)));
				return `${theme.fg("borderMuted", "│")}${" ".repeat(paddingX)}${clipped}${padding}${" ".repeat(paddingX)}${theme.fg("borderMuted", "│")}`;
			}

			return {
				render(width: number) {
					const innerWidth = Math.max(26, width - 4);
					const top = theme.fg("borderMuted", `╭${"─".repeat(innerWidth)}╮`);
					const bottom = theme.fg("borderMuted", `╰${"─".repeat(innerWidth)}╯`);
					const empty = panelLine("", innerWidth);
					const listWidth = Math.max(1, innerWidth - 6);
					const listLines = list.render(listWidth).map((line) => panelLine(line, innerWidth));
					const searchText = query ? `Search: ${query}` : "Search: type to filter";
					const promptText = renameTarget
						? `Rename ${renameTarget.label.replace(/\s+\(current\)$/i, "").trim()}: ${renameText}`
						: searchText;
					const helpText = renameTarget
						? "enter save • esc cancel rename"
						: [
							query ? "↑↓ navigate • enter select • esc clear search" : "↑↓ navigate • type filter • enter select • esc cancel",
							options.renameSelected ? "ctrl+r rename" : undefined,
							options.actionHelp,
							options.toggleHelp,
						].filter(Boolean).join(" • ");
					return [
						top,
						empty,
						panelLine(theme.fg("muted", theme.bold(title)), innerWidth),
						panelLine(renameTarget || query ? theme.fg("text", promptText) : theme.fg("dim", promptText), innerWidth),
						empty,
						...listLines,
						empty,
						panelLine(theme.fg("dim", helpText), innerWidth),
						empty,
						bottom,
					];
				},
				invalidate() { list.invalidate(); },
				handleInput(data: string) {
					if (renameTarget) {
						if (keybindings.matches(data, "tui.select.cancel")) {
							renameTarget = null;
							renameText = "";
							tui.requestRender();
							return;
						}
						if (keybindings.matches(data, "tui.select.confirm")) {
							const trimmed = renameText.trim();
							if (trimmed) done(renameValue(renameTarget, trimmed));
							return;
						}
						if (keybindings.matches(data, "tui.editor.deleteCharBackward") || data === "\x7f" || data === "\b") {
							renameText = renameText.slice(0, -1);
							tui.requestRender();
							return;
						}
						const char = printableChar(data);
						if (char) {
							renameText += char;
							tui.requestRender();
						}
						return;
					}
					if (matchesKey(data, "ctrl+r") || data === "\x12") {
						startRename();
						return;
					}
					if (!query && options.toggleSelected && (keybindings.matches(data, "tui.input.tab") || matchesKey(data, "tab") || data === "\t")) {
						const selected = list.getSelectedItem();
						if (selected && options.toggleSelected(selected)) {
							refreshList(selected.value);
							return;
						}
					}
					if (!query && options.actionSelected && data === "a") {
						const selected = list.getSelectedItem();
						const value = selected ? options.actionSelected(selected) : undefined;
						if (value) {
							done(value);
							return;
						}
					}
					if (keybindings.matches(data, "tui.select.cancel") && query) {
						query = "";
						refreshList();
						return;
					}
					if (keybindings.matches(data, "tui.select.confirm") && query && filteredItems().length === 0) {
						const typed = typedQueryValue();
						if (typed) done(typed);
						return;
					}
					if (keybindings.matches(data, "tui.editor.deleteCharBackward") || data === "\x7f" || data === "\b") {
						if (query) {
							query = query.slice(0, -1);
							refreshList();
							return;
						}
					}
					const char = printableChar(data);
					if (char) {
						query += char;
						refreshList();
						return;
					}
					list.handleInput(data);
					tui.requestRender();
				},
			};
		}, { overlay: true, overlayOptions: { width: "80%", maxHeight: "85%", margin: 2 } });
		return selected ?? null;
	}

	function directoryPickerItems(currentPath: string): SelectItem[] {
		const current = path.resolve(currentPath);
		let children: SelectItem[] = [];
		try {
			children = readdirSync(current, { withFileTypes: true })
				.filter((entry) => {
					if (entry.isDirectory()) return true;
					if (!entry.isSymbolicLink()) return false;
					try {
						return statSync(path.join(current, entry.name)).isDirectory();
					} catch {
						return false;
					}
				})
				.map((entry) => {
					const fullPath = path.join(current, entry.name);
					const suffix = entry.isSymbolicLink() ? "/@" : "/";
					return {
						value: fullPath,
						label: `${entry.name}${suffix}`,
						description: entry.isSymbolicLink() ? `${formatHomePath(fullPath)} → symlink` : formatHomePath(fullPath),
					};
				})
				.sort((a, b) => {
					const aHidden = a.label.startsWith(".");
					const bHidden = b.label.startsWith(".");
					if (aHidden !== bHidden) return aHidden ? 1 : -1;
					return a.label.localeCompare(b.label);
				});
		} catch {
			children = [];
		}
		return [
			{ value: "__use__", label: "Use this directory", description: formatHomePath(current) },
			{ value: "__newdir__", label: "New directory here", description: `Create inside ${formatHomePath(current)}` },
			{ value: homedir(), label: "~", description: formatHomePath(homedir()) },
			{ value: path.dirname(current), label: "../", description: formatHomePath(path.dirname(current)) },
			...children,
		];
	}

	async function chooseDirectory(ctx: ExtensionContext, startPath: string): Promise<string | null> {
		let current = path.resolve(expandHomePath(startPath));
		while (true) {
			const selected = await chooseFromItems(ctx, `Choose project directory · ${formatHomePath(current)}`, directoryPickerItems(current));
			if (!selected) return null;
			if (selected === "__use__") return current;
			if (selected === "__newdir__") {
				const name = await ctx.ui.input("New directory name", "my-project");
				const cleanName = name?.trim();
				if (!cleanName) continue;
				if (cleanName.includes("/")) {
					ctx.ui.notify("Directory name must not contain '/'.", "error");
					continue;
				}
				const next = path.join(current, cleanName);
				try {
					mkdirSync(next, { recursive: true });
					current = next;
				} catch (error) {
					ctx.ui.notify(`Failed to create directory: ${error instanceof Error ? error.message : String(error)}`, "error");
				}
				continue;
			}
			if (selected.startsWith("__query__:")) {
				const rawPath = selected.slice("__query__:".length).trim();
				if (!rawPath) continue;
				const expanded = expandHomePath(rawPath);
				const target = path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(current, expanded);
				if (!existsSync(target)) {
					const ok = await ctx.ui.confirm("Create directory?", `${formatHomePath(target)} does not exist. Create it?`);
					if (!ok) continue;
					try {
						mkdirSync(target, { recursive: true });
					} catch (error) {
						ctx.ui.notify(`Failed to create directory: ${error instanceof Error ? error.message : String(error)}`, "error");
						continue;
					}
				}
				try {
					if (!statSync(target).isDirectory()) {
						ctx.ui.notify("Path is not a directory.", "error");
						continue;
					}
				} catch {
					ctx.ui.notify("Path is not accessible.", "error");
					continue;
				}
				return target;
			}
			current = path.resolve(selected);
		}
	}

	function targetWorkspace(project: any, stream?: any): string {
		return path.resolve(stream?.workspace?.path || project.root);
	}

	function sessionTitle(session: any): string {
		return session.name || session.firstMessage || path.basename(session.path) || session.id;
	}

	function sessionPathID(session: any): string | undefined {
		const name = path.basename(session.path || "");
		const match = name.match(/^[^_]+_(.+)\.jsonl$/);
		return match?.[1];
	}

	function sessionIDs(session: any): string[] {
		return [...new Set([session.id, sessionPathID(session)].filter(Boolean))] as string[];
	}

	function sessionOwner(session: any): any {
		for (const id of sessionIDs(session)) {
			const owner = resolveSessionOwner(id);
			if (owner) return owner;
		}
		return undefined;
	}

	function sameOwner(owner: any, project: any, stream?: any): boolean {
		if (!owner) return false;
		if (owner.project?.id !== project.id) return false;
		if (stream) return owner.scope === "stream" && owner.stream?.id === stream.id;
		return owner.scope === "project";
	}

	function sessionCwdMatches(session: any, directory: string): boolean {
		return Boolean(session.cwd) && path.resolve(session.cwd) === path.resolve(directory);
	}

	function rememberSessionOwner(project: any, session: any, stream?: any): void {
		for (const id of sessionIDs(session)) {
			recordSessionOwner(project, id, stream?.id, { scope: stream ? "stream" : "project", projectID: project.id, streamID: stream?.id });
		}
	}

	async function listWorkspaceSessions(ctx: ExtensionCommandContext, project: any, stream: any | undefined, directory: string): Promise<any[]> {
		const byPath = new Map<string, any>();
		const add = (session: any) => {
			if (session?.path) byPath.set(session.path, session);
		};
		try {
			for (const session of await SessionManager.list(directory, ctx.sessionManager.getSessionDir())) add(session);
		} catch {
			// Fall through to listAll below; the caller shows a generic error only if both fail.
		}
		for (const session of await SessionManager.listAll(ctx.sessionManager.getSessionDir())) {
			const owner = sessionOwner(session);
			if (sessionCwdMatches(session, directory) || sameOwner(owner, project, stream)) add(session);
		}
		return [...byPath.values()].sort((a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime());
	}

	async function showSessionPicker(ctx: ExtensionCommandContext, project: any, stream?: any): Promise<void> {
		if (ctx.mode !== "tui") {
			ctx.ui.notify("Session picker requires Pi TUI interactive mode.", "error");
			return;
		}
		const directory = targetWorkspace(project, stream);
		let sessions: any[] = [];
		try {
			sessions = await listWorkspaceSessions(ctx, project, stream, directory);
		} catch (error) {
			ctx.ui.notify(`Failed to list sessions: ${error instanceof Error ? error.message : String(error)}`, "error");
		}
		const items: SelectItem[] = [
			{ value: "__new__", label: "New session", description: formatHomePath(directory) },
			...sessions.map((session) => {
				const owner = sessionOwner(session);
				const ownerText = owner ? (sameOwner(owner, project, stream) ? "owned" : `owned by ${workspaceLabel({ scope: owner.scope, id: owner.project.id, root: owner.project.root, dir: owner.stream?.dir || owner.project.dir, project: owner.project, stream: owner.stream })}`) : "unowned";
				return {
					value: session.path,
					label: sessionTitle(session),
					description: `${ownerText} · ${session.modified ? new Date(session.modified).toLocaleString() : formatHomePath(session.path)}`,
				};
			}),
		];
		const selected = await chooseFromItems(ctx, `Sessions · ${project.name || project.id}${stream ? ` / ${stream.name || stream.id}` : ""}`, items);
		if (!selected) return;
		if (selected === "__new__") {
			const next = SessionManager.create(directory, ctx.sessionManager.getSessionDir());
			const file = next.getSessionFile();
			if (!file) {
				ctx.ui.notify("Failed to create persisted session.", "error");
				return;
			}
			// SessionManager.create computes the target file path but does not write the
			// header until the first assistant response. switchSession(file) treats a
			// missing file as an explicit-path new session and generates a different
			// header id, which breaks our owner index. Seed the header first so the
			// switched session keeps the id we record below.
			if (!existsSync(file)) {
				const header = next.getHeader();
				if (header) writeFileSync(file, `${JSON.stringify(header)}\n`, "utf8");
			}
			recordSessionOwner(project, next.getSessionId(), stream?.id, { scope: stream ? "stream" : "project", projectID: project.id, streamID: stream?.id });
			await ctx.switchSession(file);
			return;
		}
		const session = sessions.find((item) => item.path === selected);
		if (!session) return;
		const owner = sessionOwner(session);
		if (!owner || sameOwner(owner, project, stream)) rememberSessionOwner(project, session, stream);
		else {
			ctx.ui.notify("Opening session with its existing project/stream owner.", "info");
		}
		await ctx.switchSession(selected);
	}

	function parseRenameSelection(selected: string): { value: string; name: string } | undefined {
		if (!selected.startsWith("__rename__:")) return undefined;
		try {
			const parsed = JSON.parse(selected.slice("__rename__:".length));
			if (typeof parsed?.value === "string" && typeof parsed?.name === "string") return parsed;
		} catch {
			return undefined;
		}
		return undefined;
	}

	async function applyProjectRename(ctx: ExtensionCommandContext, project: any, name: string): Promise<void> {
		if (!name.trim()) return;
		try {
			const renamed = renameProject(project.id, name);
			updateStatus(ctx);
			ctx.ui.notify(`Project renamed: ${renamed.name || renamed.id}`, "info");
		} catch (error) {
			ctx.ui.notify(`Failed to rename project: ${error instanceof Error ? error.message : String(error)}`, "error");
		}
	}

	async function applyStreamRename(ctx: ExtensionCommandContext, project: any, stream: any, name: string): Promise<void> {
		if (!name.trim()) return;
		try {
			const renamed = renameStream(project, stream.id, name);
			updateStatus(ctx);
			ctx.ui.notify(`Stream renamed: ${renamed.name || renamed.id}`, "info");
		} catch (error) {
			ctx.ui.notify(`Failed to rename stream: ${error instanceof Error ? error.message : String(error)}`, "error");
		}
	}

	async function showProjectPicker(ctx: ExtensionCommandContext): Promise<void> {
		if (ctx.mode !== "tui") {
			ctx.ui.notify("/projects requires Pi TUI interactive mode.", "error");
			return;
		}
		const current = contextInfoFromCtx(ctx);
		const projects = listProjects("active") as any[];
		const items: SelectItem[] = [
			{ value: "__new__", label: "New project", description: "Register a local directory" },
			...projects.map((project) => ({
				value: project.id,
				label: project.id === current.project?.id ? `${project.name || project.id} (current)` : project.name || project.id,
				description: [project.pinned ? "pinned" : undefined, formatHomePath(project.root)].filter(Boolean).join(" · "),
			})),
		];
		const selected = await chooseFromItems(ctx, "Projects", items, { renameSelected: true });
		if (!selected) return;
		if (selected === "__new__") {
			const projectPath = await chooseDirectory(ctx, ctx.cwd);
			if (!projectPath) return;
			const project = ensureProject(projectPath);
			updateStatus(ctx);
			ctx.ui.notify(`Project selected: ${project.name || project.id}`, "info");
			await showStreamPicker(ctx, project);
			return;
		}
		const projectRename = parseRenameSelection(selected);
		if (projectRename) {
			const project = projects.find((item) => item.id === projectRename.value);
			if (project) await applyProjectRename(ctx, project, projectRename.name);
			await showProjectPicker(ctx);
			return;
		}
		const project = projects.find((item) => item.id === selected);
		if (!project) return;
		updateStatus(ctx);
		ctx.ui.notify(`Project selected: ${project.name || project.id}`, "info");
		await showStreamPicker(ctx, project);
	}

	function streamArchiveToggleValue(streamID: string): string {
		return `__stream_archive__:${streamID}`;
	}

	function parseStreamArchiveToggle(selected: string): string | undefined {
		const prefix = "__stream_archive__:";
		return selected.startsWith(prefix) ? selected.slice(prefix.length) : undefined;
	}

	async function showStreamPicker(ctx: ExtensionCommandContext, projectOverride?: any, pickerOptions: { archiveExpanded?: boolean } = {}): Promise<void> {
		if (ctx.mode !== "tui") {
			ctx.ui.notify("/streams requires Pi TUI interactive mode.", "error");
			return;
		}
		const info = projectOverride ? ensureStore(resolveContext(projectOverride.root, { sessionID: undefined })) : contextInfoFromCtx(ctx);
		const project = projectOverride || info.project || ensureProject(ctx.cwd);
		const streams = listStreams(project, "active") as any[];
		const archivedStreams = listStreams(project, "archived") as any[];
		let archiveExpanded = pickerOptions.archiveExpanded ?? Boolean(info.stream && (info.stream.status || "active") === "archived");
		const archiveRowValue = "__archive__";
		const streamByID = (id: string) => [...streams, ...archivedStreams].find((item) => item.id === id);
		const archivedDescription = () => archivedStreams.length === 0
			? "No archived streams"
			: `${archivedStreams.length} archived stream${archivedStreams.length === 1 ? "" : "s"} · tab ${archiveExpanded ? "collapse" : "expand"}`;
		const streamItems = (): SelectItem[] => [
			{ value: "__project__", label: info.stream ? "Project scope" : "Project scope (current)", description: "Use project-level context" },
			{ value: "__new__", label: "New stream", description: "Create a shared-workdir stream" },
			{ value: archiveRowValue, label: archiveExpanded ? "Archive ▾" : "Archive ▸", description: archivedDescription() },
			...(archiveExpanded ? archivedStreams.map((stream) => ({
				value: stream.id,
				label: `  ${stream.id === info.stream?.id ? `${stream.name || stream.id} (current)` : stream.name || stream.id}`,
				description: ["archived", stream.pinned ? "pinned" : undefined, stream.workspace?.mode, formatHomePath(stream.workspace?.path)].filter(Boolean).join(" · "),
			})) : []),
			...streams.map((stream) => ({
				value: stream.id,
				label: stream.id === info.stream?.id ? `${stream.name || stream.id} (current)` : stream.name || stream.id,
				description: [stream.pinned ? "pinned" : undefined, stream.workspace?.mode, formatHomePath(stream.workspace?.path)].filter(Boolean).join(" · "),
			})),
		];
		const selected = await chooseFromItems(ctx, `Streams · ${project.name || project.id}`, streamItems, {
			renameSelected: true,
			actionHelp: "a archive/restore",
			actionSelected: (item) => streamByID(item.value) ? streamArchiveToggleValue(item.value) : undefined,
			toggleHelp: "tab expand/collapse archive",
			toggleSelected: (item) => {
				if (item.value !== archiveRowValue || archivedStreams.length === 0) return false;
				archiveExpanded = !archiveExpanded;
				return true;
			},
		});
		if (!selected) return;
		if (selected === "__project__") {
			updateStatus(ctx);
			ctx.ui.notify("Project scope selected", "info");
			await showSessionPicker(ctx, project);
			return;
		}
		if (selected === archiveRowValue) {
			await showStreamPicker(ctx, project, { archiveExpanded: archivedStreams.length > 0 ? !archiveExpanded : archiveExpanded });
			return;
		}
		if (selected === "__new__") {
			const name = await ctx.ui.input("New stream name", "feature or task name");
			if (!name?.trim()) return;
			const stream = createStream(project, { name });
			updateStatus(ctx);
			ctx.ui.notify(`Stream selected: ${stream.name || stream.id}`, "info");
			await showSessionPicker(ctx, project, stream);
			return;
		}
		const streamToggleID = parseStreamArchiveToggle(selected);
		if (streamToggleID) {
			const activeStream = streams.find((item) => item.id === streamToggleID);
			const archivedStream = archivedStreams.find((item) => item.id === streamToggleID);
			if (activeStream) {
				const archived = archiveStream(project, activeStream.id);
				if (activeStream.id === info.stream?.id) {
					const sessionID = ctx.sessionManager.getSessionId();
					if (sessionID) recordSessionOwner(project, sessionID, undefined, { scope: "project", projectID: project.id, streamID: undefined });
				}
				updateStatus(ctx);
				ctx.ui.notify(`Stream archived: ${archived.name || archived.id}`, "info");
				await showStreamPicker(ctx, project, { archiveExpanded });
				return;
			}
			if (archivedStream) {
				const restored = restoreStream(project, archivedStream.id);
				updateStatus(ctx);
				ctx.ui.notify(`Stream restored: ${restored.name || restored.id}`, "info");
				await showStreamPicker(ctx, project, { archiveExpanded: true });
				return;
			}
			return;
		}
		const streamRename = parseRenameSelection(selected);
		if (streamRename) {
			const stream = streamByID(streamRename.value);
			if (stream) await applyStreamRename(ctx, project, stream, streamRename.name);
			await showStreamPicker(ctx, project, { archiveExpanded });
			return;
		}
		const stream = streamByID(selected);
		if (!stream) return;
		updateStatus(ctx);
		ctx.ui.notify(`Stream selected: ${stream.name || stream.id}`, "info");
		await showSessionPicker(ctx, project, stream);
	}

	pi.registerCommand("projects", {
		description: "Browse, create, and select Pi projects",
		handler: async (_args, ctx) => showProjectPicker(ctx),
	});

	pi.registerCommand("streams", {
		description: "Browse, create, and select streams for the current Pi project",
		handler: async (_args, ctx) => showStreamPicker(ctx),
	});

	pi.registerCommand("project-context", {
		description: "Show current Pi project/stream context",
		handler: async (_args, ctx) => {
			const info = contextInfoFromCtx(ctx);
			const worklogInfo = worklogInfoFromCtx(ctx);
			const worklogLine = worklogInfo ? `\nWorklog: ${formatHomePath(withWorklogPath(worklogInfo).log)}` : "\nWorklog: inactive (session is not attached to a Pi project or stream)";
			ctx.ui.notify(`${workspaceDescription(info)}${worklogLine}`, "info");
		},
	});

	pi.registerCommand("worklog", {
		description: "Show current scoped project/stream worklog recap",
		handler: async (_args, ctx) => {
			const info = worklogInfoFromCtx(ctx);
			if (!info) {
				ctx.ui.notify("Worklog is inactive because this session is not attached to a Pi project or stream.", "info");
				return;
			}
			ctx.ui.notify(worklogRecap(info), "info");
		},
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const info = worklogInfoFromCtx(ctx);
		if (!info) return;
		return {
			systemPrompt: `${event.systemPrompt}\n\n${worklogReminder(info)}\n\nContinuity behavior: when the user asks where we are, what the current state is, what we were doing, to resume, or to continue, call worklog_recap first for the selected scope. Do not run git status, inspect unrelated files, or read parent/sibling/other project logs unless the user explicitly asks for repo status, another session, another project, project-wide history, or broader investigation. The recent worklog recap is intentionally not injected into this system prompt to keep provider prompt caching stable across worklog appends.`,
		};
	});

	pi.on("session_start", async (_event, ctx) => {
		updateStatus(ctx);
	});
}
