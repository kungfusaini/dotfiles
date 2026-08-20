import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext, SessionEntry } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type WorkerState = "starting" | "running" | "blocked" | "done" | "exited" | "failed" | "closed" | "orphaned" | "unknown";
type ParentWakeState = Extract<WorkerState, "blocked" | "done" | "exited" | "failed">;
type AgentLifecycleState = "starting" | "working" | "blocked" | "done" | "failed" | "unknown";
type AgentLifecycleSource = "orchestrator" | "child" | "manual";
type WorkerVisibility = "hidden" | "visible" | "unknown";
type WorkerWorkspace = "current" | "worktree";
type WorkerScope = "owned" | "all";

interface StructuredResult {
	status: "done" | "blocked" | "failed";
	summary?: string;
	needs_user?: boolean;
	next_action?: unknown;
	[key: string]: unknown;
}


interface AgentLifecycleRecord {
	schemaVersion: 1;
	workerName: string;
	ownerSessionId?: string;
	state: AgentLifecycleState;
	source: AgentLifecycleSource;
	message?: string;
	needsUser?: boolean;
	updatedAt: string;
}

interface TerminalRecord {
	id: string;
	name: string;
	command: string;
	cwd: string;
	workspace?: WorkerWorkspace;
	worktreePath?: string;
	worktreeBranch?: string;
	worktreeBase?: string;
	worktreeRepoRoot?: string;
	cleanupWorktreeOnClose?: boolean;
	worktreeCleanupError?: string;
	worktreeBranchCleanupError?: string;
	ownerSessionId?: string;
	ownerCwd: string;
	tmuxServer: string;
	tmuxSession: string;
	createdAt: string;
	updatedAt: string;
	state: WorkerState;
	visibility: WorkerVisibility;
	needsUser?: boolean;
	statusMessage?: string;
	markedAt?: string;
	blockedSurfacedAt?: string;
	task?: string;
	lastPrompt?: string;
	promptedAt?: string;
	promptReadyAt?: string;
	promptReadyTimedOut?: boolean;
	structuredResult?: StructuredResult;
	structuredResultParseError?: string;
	title?: string;
	paneId?: string;
	lastPaneId?: string;
	surfacedAt?: string;
	hiddenAt?: string;
	closedAt?: string;
	startedAt?: string;
	endedAt?: string;
	exitCode?: number;
	exitSignal?: string;
	exitFile: string;
	lifecycleFile?: string;
	lifecycleState?: AgentLifecycleState;
	lifecycleSource?: AgentLifecycleSource;
	lifecycleUpdatedAt?: string;
	watcherLastObservedAt?: string;
	watcherLastError?: string;
	parentNotificationKey?: string;
	parentNotificationQueuedAt?: string;
	lastError?: string;
	surfaceCloseError?: string;
}

const terminals = new Map<string, TerminalRecord>();
const TMUX_SERVER = "pi-orchestrator";
const TERMINAL_SOURCE = "pi-orchestrator-managed-terminal";
const TMUX_HISTORY_LIMIT = 5000;
const DEFAULT_HANDOFF_MAX_CHARS = 12_000;
const TOOL_SUMMARY_MAX_CHARS = 1_000;

const TerminalNameParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a worker owned by another orchestrator session. Default false." })),
});

const WorkerScopeSchema = StringEnum(["owned", "all"] as const, {
	description: "Scope for worker discovery and inspection. owned limits to the current Pi session; all is an explicit global admin view.",
	default: "owned",
});

const TerminalReadParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to read. Default 80." })),
	scope: Type.Optional(WorkerScopeSchema),
});

const WorkerPollParams = Type.Object({
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to inspect per active worker. Default 5000, matching the managed tmux history limit." })),
	scope: Type.Optional(WorkerScopeSchema),
});

const WorkerStatusParams = Type.Object({
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to inspect per active worker. Default 5000, matching the managed tmux history limit." })),
	scope: Type.Optional(WorkerScopeSchema),
	includeClosed: Type.Optional(Type.Boolean({ description: "Include closed workers in the dashboard. Default false." })),
});

const TerminalSendParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	text: Type.String({ description: "Text to send to the hidden/surfaced worker." }),
	enter: Type.Optional(Type.Boolean({ description: "Press Enter after the text. Default true." })),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a worker owned by another orchestrator session. Default false." })),
});

const TerminalSurfaceParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	focus: Type.Optional(Type.Boolean({ description: "Focus the surfaced Herdr pane. Default true." })),
	force: Type.Optional(Type.Boolean({ description: "Allow surfacing a worker owned by another orchestrator session. Default false." })),
});

const WorkerKindSchema = StringEnum(["pi", "shell"] as const, {
	description: "Worker kind. pi starts a Pi subagent in the managed terminal; shell runs an arbitrary shell command.",
	default: "pi",
});

const WorkerVisibilitySchema = StringEnum(["hidden", "visible"] as const, {
	description: "Whether to keep the worker hidden or immediately surface it into Herdr.",
	default: "hidden",
});

const WorkerWorkspaceSchema = StringEnum(["current", "worktree"] as const, {
	description: "Workspace mode. current runs in the current checkout; worktree creates an isolated git worktree from the current repository.",
	default: "current",
});

const WorkerMarkStateSchema = StringEnum(["blocked", "running"] as const, {
	description: "Manual worker attention state. blocked means the worker needs user/parent attention; running clears that marker.",
});

const WorkerMarkParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	state: WorkerMarkStateSchema,
	message: Type.Optional(Type.String({ description: "Short status/attention message to show in lists and Herdr when surfaced." })),
	needsUser: Type.Optional(Type.Boolean({ description: "Whether this blocked state needs human input. Defaults true when state=blocked, false when state=running." })),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a worker owned by another orchestrator session. Default false." })),
});

const AgentLifecycleStateSchema = StringEnum(["working", "blocked", "done", "failed", "unknown"] as const, {
	description: "Lifecycle state reported by the worker itself. The worker identity is inferred from orchestrator environment variables.",
});

const AgentLifecycleReportParams = Type.Object({
	state: AgentLifecycleStateSchema,
	message: Type.Optional(Type.String({ description: "Short state summary for the parent orchestrator." })),
	needsUser: Type.Optional(Type.Boolean({ description: "Whether this state requires parent/user attention. Defaults true for blocked, false otherwise." })),
});

const WorkerStartParams = Type.Object({
	kind: Type.Optional(WorkerKindSchema),
	command: Type.Optional(Type.String({ description: "Shell command to run. Defaults to `pi` when kind=pi; required when kind=shell." })),
	task: Type.Optional(Type.String({ description: "Task prompt to send after startup. Supported for kind=pi workers." })),
	handoffPrompt: Type.Optional(Type.String({ description: "Optional parent-written context to include in the Pi worker task prompt." })),
	recentInteractions: Type.Optional(Type.Integer({ minimum: 0, description: "Number of recent user/assistant interactions to include in the handoff prompt. Default 0." })),
	includeToolCalls: Type.Optional(Type.Boolean({ description: "Include compact tool call/result summaries in recent interactions. Default false." })),
	handoffMaxChars: Type.Optional(Type.Integer({ minimum: 1000, description: "Maximum characters for the rendered handoff context. Default 12000." })),
	name: Type.Optional(Type.String({ description: "Optional stable worker name." })),
	cwd: Type.Optional(Type.String({ description: "Working directory. Defaults to current Pi cwd. Ignored when workspace=worktree unless worktreePath is also supplied." })),
	workspace: Type.Optional(WorkerWorkspaceSchema),
	branch: Type.Optional(Type.String({ description: "Branch name to create/use for workspace=worktree. Defaults to pi-orch/<worker-name>." })),
	base: Type.Optional(Type.String({ description: "Base ref for git worktree add when workspace=worktree. Defaults to HEAD." })),
	worktreePath: Type.Optional(Type.String({ description: "Checkout path for workspace=worktree. Defaults to <repo-parent>/.worktrees/<repo>/<worker>. Relative paths are resolved from repo root." })),
	cleanupWorktreeOnClose: Type.Optional(Type.Boolean({ description: "Remove orchestrator-created worktree on worker close if clean. Default true for workspace=worktree." })),
	env: Type.Optional(Type.Record(Type.String(), Type.String(), { description: "Extra environment variables for the worker command." })),
	cols: Type.Optional(Type.Integer({ minimum: 40, description: "Initial hidden terminal width. Default 140." })),
	rows: Type.Optional(Type.Integer({ minimum: 10, description: "Initial hidden terminal height. Default 40." })),
	title: Type.Optional(Type.String({ description: "Display title when surfaced." })),
	keepAlive: Type.Optional(Type.Boolean({ description: "Open an interactive shell after the command exits instead of exiting. Default false; exited panes remain inspectable via tmux." })),
	taskPromptTimeoutMs: Type.Optional(Type.Integer({ minimum: 500, description: "Maximum time to wait for a Pi worker prompt/readiness before sending task anyway. Default 8000ms." })),
	visibility: Type.Optional(WorkerVisibilitySchema),
	focus: Type.Optional(Type.Boolean({ description: "Focus the surfaced Herdr pane when visibility=visible. Default true." })),
});

const WorkerStartManyParams = Type.Object({
	workers: Type.Array(WorkerStartParams, { minItems: 1, description: "Workers to start. Each item accepts the same fields as orchestrator_worker_start." }),
	continueOnError: Type.Optional(Type.Boolean({ description: "Continue starting later workers if one fails. Default true." })),
});

function slug(input: string, fallback = "worker"): string {
	let cleaned = input
		.toLowerCase()
		.replace(/[^a-z0-9_-]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 24);
	if (!cleaned) cleaned = fallback;
	if (!/^[a-z]/.test(cleaned)) cleaned = `a-${cleaned}`;
	return cleaned.slice(0, 24);
}

function xdgStateHome(): string {
	return process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state");
}

function terminalRoot(): string {
	return path.join(xdgStateHome(), "pi", "orchestrator", "terminals");
}

function terminalRegistryDir(): string {
	return path.join(terminalRoot(), "registry");
}

function terminalExitDir(): string {
	return path.join(terminalRoot(), "exit");
}

function terminalLifecycleDir(): string {
	return path.join(terminalRoot(), "lifecycle");
}

function terminalExitPath(name: string): string {
	return path.join(terminalExitDir(), `${validateTerminalName(name)}.json`);
}

function terminalLifecyclePath(name: string): string {
	return path.join(terminalLifecycleDir(), `${validateTerminalName(name)}.json`);
}

function terminalTmuxConfPath(): string {
	return path.join(terminalRoot(), "tmux.conf");
}

function validateTerminalName(name: string): string {
	if (!/^[a-z][a-z0-9_-]{0,31}$/.test(name)) {
		throw new Error(`Invalid terminal worker name ${JSON.stringify(name)}. Use 1-32 chars matching /^[a-z][a-z0-9_-]*$/i after slugging.`);
	}
	return name;
}

function validateEnv(env: Record<string, string> | undefined): Record<string, string> | undefined {
	if (!env) return undefined;
	const validated: Record<string, string> = {};
	for (const [key, value] of Object.entries(env)) {
		if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
			throw new Error(`Invalid environment variable name ${JSON.stringify(key)}. Use /^[A-Za-z_][A-Za-z0-9_]*$/.`);
		}
		validated[key] = value;
	}
	return validated;
}

function terminalRecordPath(name: string): string {
	return path.join(terminalRegistryDir(), `${validateTerminalName(name)}.json`);
}

function terminalRecordLockPath(name: string): string {
	return `${terminalRecordPath(name)}.lock`;
}

async function withTerminalRecordLock<T>(name: string, fn: () => Promise<T>): Promise<T> {
	await ensureTerminalStore();
	const lockPath = terminalRecordLockPath(name);
	const started = Date.now();
	while (true) {
		try {
			await fs.mkdir(lockPath, { mode: 0o700 });
			break;
		} catch (error: any) {
			if (error?.code !== "EEXIST") throw error;
			const stat = await fs.stat(lockPath).catch(() => undefined);
			if (stat && Date.now() - stat.mtimeMs > 30_000) {
				await fs.rm(lockPath, { recursive: true, force: true });
				continue;
			}
			if (Date.now() - started > 5_000) throw new Error(`Timed out waiting for orchestrator registry lock for ${name}.`);
			await delay(50);
		}
	}
	try {
		return await fn();
	} finally {
		await fs.rm(lockPath, { recursive: true, force: true }).catch(() => undefined);
	}
}

function tmuxArgs(...args: string[]): string[] {
	return ["-L", TMUX_SERVER, "-f", terminalTmuxConfPath(), ...args];
}

function shellQuote(value: string): string {
	return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function textOf(result: { stdout?: string; stderr?: string; code?: number }): string {
	return [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
}

function delay(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

type MessageEntry = Extract<SessionEntry, { type: "message" }>;

function truncateMiddle(value: string, maxChars: number): string {
	if (value.length <= maxChars) return value;
	const head = Math.floor(maxChars * 0.65);
	const tail = Math.max(0, maxChars - head - 32);
	return `${value.slice(0, head).trimEnd()}\n…[truncated ${value.length - head - tail} chars]…\n${value.slice(-tail).trimStart()}`;
}

function safeJson(value: unknown): string {
	try {
		return JSON.stringify(value) ?? String(value);
	} catch {
		return String(value);
	}
}

function textFromContent(content: unknown, includeToolCalls: boolean): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	const sections: string[] = [];
	for (const part of content) {
		if (!part || typeof part !== "object") continue;
		const typed = part as Record<string, unknown>;
		if (typed.type === "text" && typeof typed.text === "string") sections.push(typed.text);
		else if (includeToolCalls && typed.type === "toolCall") {
			const name = typeof typed.name === "string" ? typed.name : "tool";
			const args = typed.arguments === undefined ? "" : ` ${truncateMiddle(safeJson(typed.arguments), TOOL_SUMMARY_MAX_CHARS)}`;
			sections.push(`[tool call: ${name}${args}]`);
		} else if (includeToolCalls && typed.type === "toolResult") {
			const text = typeof typed.text === "string" ? typed.text : safeJson(typed);
			sections.push(`[tool result: ${truncateMiddle(text, TOOL_SUMMARY_MAX_CHARS)}]`);
		}
	}
	return sections.join("\n");
}

function roleLabel(role: string): string | undefined {
	if (role === "user") return "User";
	if (role === "assistant") return "Assistant";
	if (role === "tool" || role === "toolResult") return "Tool";
	return undefined;
}

function renderRecentInteractions(entries: SessionEntry[], count: number, includeToolCalls: boolean, maxChars: number): string | undefined {
	if (count <= 0) return undefined;
	const selected: MessageEntry[] = [];
	let interactions = 0;
	for (let i = entries.length - 1; i >= 0; i--) {
		const entry = entries[i];
		if (entry.type !== "message") continue;
		const role = String(entry.message.role ?? "");
		const isInteraction = role === "user" || role === "assistant";
		const isTool = role === "tool" || role === "toolResult";
		if (!isInteraction && !(includeToolCalls && isTool)) continue;
		if (isInteraction) interactions++;
		selected.push(entry as MessageEntry);
		if (interactions >= count) break;
	}
	selected.reverse();
	const rendered = selected
		.map((entry) => {
			const role = String(entry.message.role ?? "");
			const label = roleLabel(role);
			if (!label) return undefined;
			const text = textFromContent(entry.message.content, includeToolCalls).trim();
			if (!text) return undefined;
			return `${label}: ${text}`;
		})
		.filter(Boolean)
		.join("\n\n");
	if (!rendered.trim()) return undefined;
	return truncateMiddle(rendered, maxChars);
}

function buildHandoffContext(ctx: ExtensionContext, params: { handoffPrompt?: string; recentInteractions?: number; includeToolCalls?: boolean; handoffMaxChars?: number }): string | undefined {
	const sections: string[] = [];
	if (params.handoffPrompt?.trim()) sections.push(`Parent handoff prompt:\n${params.handoffPrompt.trim()}`);
	const recent = renderRecentInteractions(ctx.sessionManager.getBranch(), params.recentInteractions ?? 0, params.includeToolCalls ?? false, params.handoffMaxChars ?? DEFAULT_HANDOFF_MAX_CHARS);
	if (recent) sections.push(`Recent conversation excerpt (${params.recentInteractions} user/assistant interactions${params.includeToolCalls ? ", with compact tool summaries" : ", no tool calls"}):\n${recent}`);
	if (!sections.length) return undefined;
	return truncateMiddle(sections.join("\n\n---\n\n"), params.handoffMaxChars ?? DEFAULT_HANDOFF_MAX_CHARS);
}

function extractJsonObject(text: string): { text: string; end: number } | undefined {
	const start = text.indexOf("{");
	if (start < 0) return undefined;
	let depth = 0;
	let inString = false;
	let escaped = false;
	for (let i = start; i < text.length; i++) {
		const char = text[i];
		if (inString) {
			if (escaped) escaped = false;
			else if (char === "\\") escaped = true;
			else if (char === '"') inString = false;
			continue;
		}
		if (char === '"') inString = true;
		else if (char === "{") depth++;
		else if (char === "}") {
			depth--;
			if (depth === 0) return { text: text.slice(start, i + 1), end: i + 1 };
		}
	}
	return undefined;
}

function parseStructuredResult(output: string): { result?: StructuredResult; error?: string } {
	const marker = "ORCHESTRATOR_RESULT:";
	const markerIndex = output.lastIndexOf(marker);
	if (markerIndex < 0) return {};
	const afterMarker = output.slice(markerIndex + marker.length);
	const json = extractJsonObject(afterMarker);
	if (!json) return { error: "ORCHESTRATOR_RESULT marker found but no complete JSON object followed it." };
	if (afterMarker.slice(json.end).trim().length > 0) return { error: "ORCHESTRATOR_RESULT footer must be the final non-whitespace content." };
	try {
		const parsed = JSON.parse(json.text);
		if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return { error: "ORCHESTRATOR_RESULT JSON is not an object." };
		const status = (parsed as StructuredResult).status;
		if (status !== "done" && status !== "blocked" && status !== "failed") return { error: 'ORCHESTRATOR_RESULT status must be one of "done", "blocked", or "failed".' };
		return { result: parsed as StructuredResult };
	} catch (error) {
		return { error: error instanceof Error ? error.message : String(error) };
	}
}

function applyStructuredResult(record: TerminalRecord, output: string): boolean {
	const parsed = parseStructuredResult(output);
	if (parsed.result) {
		record.structuredResult = parsed.result;
		record.structuredResultParseError = undefined;
		if (parsed.result.status === "blocked" || parsed.result.needs_user === true) {
			record.state = "blocked";
			record.needsUser = parsed.result.needs_user ?? true;
		} else if (parsed.result.status === "failed") {
			record.state = "failed";
		} else if (parsed.result.status === "done" && (record.state === "running" || record.state === "blocked")) {
			record.state = "done";
			record.needsUser = false;
		}
		if (typeof parsed.result.summary === "string") record.statusMessage = parsed.result.summary;
		record.updatedAt = new Date().toISOString();
		return true;
	}
	if (parsed.error) {
		record.structuredResultParseError = parsed.error;
		record.updatedAt = new Date().toISOString();
		return true;
	}
	return false;
}

async function execChecked(pi: ExtensionAPI, command: string, args: string[], options: { cwd?: string; signal?: AbortSignal; timeout?: number } = {}) {
	const result = await pi.exec(command, args, { cwd: options.cwd, signal: options.signal, timeout: options.timeout });
	if (result.code !== 0) {
		throw new Error(`${command} ${args.join(" ")} failed (${result.code})\n${textOf(result)}`.trim());
	}
	return result;
}

async function ensureTerminalStore() {
	await fs.mkdir(terminalRegistryDir(), { recursive: true });
	await fs.mkdir(terminalExitDir(), { recursive: true });
	await fs.mkdir(terminalLifecycleDir(), { recursive: true });
	await fs.writeFile(
		terminalTmuxConfPath(),
		[
			"set -g status off",
			"set -g extended-keys-format csi-u",
			'set -g default-terminal "tmux-256color"',
			`set -g history-limit ${TMUX_HISTORY_LIMIT}`,
			"set -g exit-empty off",
			"set -g detach-on-destroy off",
			"set -g remain-on-exit on",
			"set -g set-titles on",
			'run-shell -b "true"',
			"",
		].join("\n"),
		{ mode: 0o600 },
	);
}

async function saveTerminalRecord(record: TerminalRecord) {
	validateTerminalName(record.name);
	if (!record.lifecycleFile) record.lifecycleFile = terminalLifecyclePath(record.name);
	await withTerminalRecordLock(record.name, async () => {
		const file = terminalRecordPath(record.name);
		const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
		await fs.writeFile(tmp, `${JSON.stringify(record, null, 2)}\n`, { mode: 0o600 });
		await fs.rename(tmp, file);
		terminals.set(record.name, record);
	});
}

async function loadTerminalRecord(name: string): Promise<TerminalRecord | undefined> {
	validateTerminalName(name);
	try {
		const parsed = JSON.parse(await fs.readFile(terminalRecordPath(name), "utf8")) as TerminalRecord;
		if (parsed?.name !== name) throw new Error(`Terminal registry name mismatch for ${name}: ${parsed?.name || "missing"}`);
		terminals.set(parsed.name, parsed);
		return parsed;
	} catch (error: any) {
		if (error?.code === "ENOENT") return undefined;
		throw error;
	}
}

async function loadTerminalRecords(): Promise<TerminalRecord[]> {
	await ensureTerminalStore();
	const names = await fs.readdir(terminalRegistryDir()).catch(() => [] as string[]);
	const records: TerminalRecord[] = [];
	for (const file of names) {
		if (!file.endsWith(".json")) continue;
		try {
			const parsed = JSON.parse(await fs.readFile(path.join(terminalRegistryDir(), file), "utf8")) as TerminalRecord;
			const expectedName = file.slice(0, -".json".length);
			if (parsed?.name === expectedName) {
				validateTerminalName(parsed.name);
				terminals.set(parsed.name, parsed);
				records.push(parsed);
			}
		} catch {
			// Ignore malformed stale records in list output.
		}
	}
	return records.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

async function uniqueTerminalName(requested: string | undefined, command: string): Promise<string> {
	const base = slug(requested || command.split(/\s+/).slice(0, 4).join("-"), "terminal").slice(0, 28);
	for (let i = 0; i < 100; i++) {
		const candidate = i === 0 ? base : `${base.slice(0, 24)}-${i + 1}`;
		if (!(await loadTerminalRecord(candidate))) return candidate;
	}
	return `${base.slice(0, 20)}-${randomUUID().slice(0, 8)}`;
}

function validateBranchName(branch: string): string {
	if (!branch || branch.startsWith("-") || /[\0\s~^:?*\[\\]/.test(branch) || branch.includes("..") || branch.endsWith(".") || branch.includes("@{")) {
		throw new Error(`Invalid git branch name ${JSON.stringify(branch)}.`);
	}
	return branch;
}

async function gitOutput(pi: ExtensionAPI, cwd: string, args: string[], signal?: AbortSignal): Promise<string> {
	const result = await execChecked(pi, "git", ["-C", cwd, ...args], { signal, timeout: 15_000 });
	return result.stdout.trim();
}

async function createWorkerWorktree(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	params: { name: string; cwd?: string; branch?: string; base?: string; worktreePath?: string; cleanupWorktreeOnClose?: boolean },
	signal?: AbortSignal,
): Promise<Pick<TerminalRecord, "cwd" | "workspace" | "worktreePath" | "worktreeBranch" | "worktreeBase" | "worktreeRepoRoot" | "cleanupWorktreeOnClose">> {
	const sourceCwd = path.resolve(params.cwd ? (path.isAbsolute(params.cwd) ? params.cwd : path.join(ctx.cwd, params.cwd)) : ctx.cwd);
	const repoRoot = await gitOutput(pi, sourceCwd, ["rev-parse", "--show-toplevel"], signal);
	const repoName = path.basename(repoRoot);
	const worktreePath = path.resolve(params.worktreePath ? (path.isAbsolute(params.worktreePath) ? params.worktreePath : path.join(repoRoot, params.worktreePath)) : path.join(path.dirname(repoRoot), ".worktrees", repoName, params.name));
	const branch = validateBranchName(params.branch || `pi-orch/${params.name}`);
	const base = params.base || "HEAD";
	await fs.mkdir(path.dirname(worktreePath), { recursive: true });
	await execChecked(pi, "git", ["-C", repoRoot, "worktree", "add", "-b", branch, worktreePath, base], { signal, timeout: 60_000 });
	return {
		cwd: worktreePath,
		workspace: "worktree",
		worktreePath,
		worktreeBranch: branch,
		worktreeBase: base,
		worktreeRepoRoot: repoRoot,
		cleanupWorktreeOnClose: params.cleanupWorktreeOnClose ?? true,
	};
}

async function cleanupWorkerWorktree(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<string | undefined> {
	if (record.workspace !== "worktree" || !record.worktreePath || !record.worktreeRepoRoot || record.cleanupWorktreeOnClose === false) return undefined;
	const removed = await pi.exec("git", ["-C", record.worktreeRepoRoot, "worktree", "remove", record.worktreePath], { signal, timeout: 60_000 });
	if (removed.code !== 0) {
		record.worktreeCleanupError = textOf(removed) || `Failed to remove worktree ${record.worktreePath}`;
		return `\nKept worktree ${record.worktreePath}: ${record.worktreeCleanupError}`;
	}
	record.worktreeCleanupError = undefined;
	let note = `\nRemoved clean worktree ${record.worktreePath}.`;
	if (record.worktreeBranch) {
		const deleted = await pi.exec("git", ["-C", record.worktreeRepoRoot, "branch", "-d", record.worktreeBranch], { signal, timeout: 30_000 });
		if (deleted.code === 0) {
			record.worktreeBranchCleanupError = undefined;
			note += `\nDeleted merged worktree branch ${record.worktreeBranch}.`;
		} else {
			record.worktreeBranchCleanupError = textOf(deleted) || `Failed to delete branch ${record.worktreeBranch}`;
			note += `\nKept branch ${record.worktreeBranch}: ${record.worktreeBranchCleanupError}`;
		}
	}
	return note;
}

function assertTerminalOwner(record: TerminalRecord, ctx: ExtensionContext, force?: boolean) {
	if (force) return;
	const current = ctx.sessionManager.getSessionId();
	if (record.ownerSessionId && current && record.ownerSessionId !== current) {
		throw new Error(
			`Terminal ${record.name} is owned by another orchestrator session (${record.ownerSessionId}). Use force=true only if you intentionally want to take over.`,
		);
	}
}

async function terminalExists(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<boolean> {
	await ensureTerminalStore();
	const result = await pi.exec("tmux", tmuxArgs("has-session", "-t", record.tmuxSession), { signal, timeout: 5_000 });
	return result.code === 0;
}

async function readExitMetadata(record: TerminalRecord): Promise<Partial<TerminalRecord> | undefined> {
	try {
		const parsed = JSON.parse(await fs.readFile(record.exitFile || terminalExitPath(record.name), "utf8"));
		return {
			startedAt: typeof parsed.startedAt === "string" ? parsed.startedAt : undefined,
			endedAt: typeof parsed.endedAt === "string" ? parsed.endedAt : undefined,
			exitCode: typeof parsed.exitCode === "number" ? parsed.exitCode : undefined,
			exitSignal: typeof parsed.exitSignal === "string" ? parsed.exitSignal : undefined,
		};
	} catch (error: any) {
		if (error?.code === "ENOENT") return undefined;
		throw error;
	}
}

async function readLifecycleRecord(record: TerminalRecord): Promise<AgentLifecycleRecord | undefined> {
	try {
		const parsed = JSON.parse(await fs.readFile(record.lifecycleFile || terminalLifecyclePath(record.name), "utf8"));
		if (parsed?.schemaVersion !== 1) return undefined;
		if (parsed.workerName !== record.name) return undefined;
		if (record.ownerSessionId && parsed.ownerSessionId && parsed.ownerSessionId !== record.ownerSessionId) return undefined;
		if (!["starting", "working", "blocked", "done", "failed", "unknown"].includes(parsed.state)) return undefined;
		return parsed as AgentLifecycleRecord;
	} catch (error: any) {
		if (error?.code === "ENOENT") return undefined;
		throw error;
	}
}

async function writeLifecycleRecord(record: TerminalRecord, update: { state: AgentLifecycleState; source: AgentLifecycleSource; message?: string; needsUser?: boolean; updatedAt?: string }): Promise<AgentLifecycleRecord> {
	await ensureTerminalStore();
	record.lifecycleFile = record.lifecycleFile || terminalLifecyclePath(record.name);
	const lifecycle: AgentLifecycleRecord = {
		schemaVersion: 1,
		workerName: record.name,
		ownerSessionId: record.ownerSessionId,
		state: update.state,
		source: update.source,
		message: update.message,
		needsUser: update.needsUser,
		updatedAt: update.updatedAt || new Date().toISOString(),
	};
	const tmp = `${record.lifecycleFile}.${process.pid}.${Date.now()}.tmp`;
	await fs.writeFile(tmp, `${JSON.stringify(lifecycle, null, 2)}\n`, { mode: 0o600 });
	await fs.rename(tmp, record.lifecycleFile);
	return lifecycle;
}

function applyLifecycleRecord(record: TerminalRecord, lifecycle: AgentLifecycleRecord | undefined): boolean {
	if (!lifecycle) return false;
	const manualWins = record.markedAt && lifecycle.source !== "manual" && lifecycle.updatedAt <= record.markedAt;
	if (manualWins) return false;
	const before = JSON.stringify({ state: record.state, needsUser: record.needsUser, statusMessage: record.statusMessage, lifecycleState: record.lifecycleState, lifecycleUpdatedAt: record.lifecycleUpdatedAt });
	record.lifecycleState = lifecycle.state;
	record.lifecycleSource = lifecycle.source;
	record.lifecycleUpdatedAt = lifecycle.updatedAt;
	if (lifecycle.state === "blocked") {
		record.state = "blocked";
		record.needsUser = lifecycle.needsUser ?? true;
	} else if (lifecycle.state === "working") {
		if (record.state !== "failed" && record.state !== "exited" && record.state !== "closed") record.state = "running";
		record.needsUser = false;
		record.blockedSurfacedAt = undefined;
	} else if (lifecycle.state === "done") {
		record.state = "done";
		record.needsUser = false;
	} else if (lifecycle.state === "failed") {
		record.state = "failed";
		record.needsUser = lifecycle.needsUser ?? false;
	} else if (lifecycle.state === "unknown" && record.state !== "closed") {
		record.state = "unknown";
	}
	if (typeof lifecycle.message === "string") record.statusMessage = lifecycle.message;
	return before !== JSON.stringify({ state: record.state, needsUser: record.needsUser, statusMessage: record.statusMessage, lifecycleState: record.lifecycleState, lifecycleUpdatedAt: record.lifecycleUpdatedAt });
}

function applyExitMetadata(record: TerminalRecord, metadata: Partial<TerminalRecord>): boolean {
	if (metadata.startedAt) record.startedAt = metadata.startedAt;
	if (metadata.endedAt) record.endedAt = metadata.endedAt;
	if (typeof metadata.exitCode === "number") record.exitCode = metadata.exitCode;
	if (metadata.exitSignal) record.exitSignal = metadata.exitSignal;
	if (record.endedAt || typeof record.exitCode === "number" || record.exitSignal) {
		if (record.exitSignal || (record.exitCode ?? 0) !== 0) {
			record.state = "failed";
			if (record.lifecycleState !== "failed") {
				record.statusMessage = record.exitSignal
					? `Worker ${record.name} exited from signal ${record.exitSignal}.`
					: `Worker ${record.name} exited with code ${record.exitCode ?? "unknown"}.`;
			}
		} else {
			record.state = record.lifecycleState === "done" ? "done" : "exited";
			if (record.state === "exited") record.statusMessage = `Worker ${record.name} exited successfully.`;
		}
		return true;
	}
	return false;
}

async function refreshTerminalRecord(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<TerminalRecord> {
	if (!record.exitFile) record.exitFile = terminalExitPath(record.name);
	if (!record.lifecycleFile) record.lifecycleFile = terminalLifecyclePath(record.name);
	if (!record.visibility) record.visibility = record.paneId ? "visible" : "hidden";
	if (record.state === "closed") return record;
	if (record.state === "failed" && record.lastError && !record.startedAt) return record;

	try {
		const panes = await pi.exec(
			"tmux",
			tmuxArgs("list-panes", "-t", record.tmuxSession, "-F", "#{pane_dead}\t#{pane_dead_status}\t#{pane_dead_signal}\t#{pane_dead_time}"),
			{ signal, timeout: 5_000 },
		);
		if (panes.code === 0) {
			const [dead, status, paneSignal, deadTime] = panes.stdout.trim().split("\t");
			const lifecycle = await readLifecycleRecord(record);
			const metadata = await readExitMetadata(record);
			const hadExitMetadata = metadata ? applyExitMetadata(record, metadata) : false;
			if (dead === "1") {
				const code = Number(status);
				if (Number.isFinite(code)) record.exitCode = code;
				if (paneSignal) record.exitSignal = paneSignal;
				if (deadTime && !record.endedAt) record.endedAt = new Date(Number(deadTime) * 1000).toISOString();
				applyLifecycleRecord(record, lifecycle);
				applyExitMetadata(record, {});
			} else if (hadExitMetadata) {
				applyLifecycleRecord(record, lifecycle);
				applyExitMetadata(record, {});
			} else {
				record.state = record.state === "blocked" || record.state === "done" ? record.state : "running";
				applyLifecycleRecord(record, lifecycle);
			}
			record.visibility = record.paneId ? "visible" : "hidden";
			record.updatedAt = new Date().toISOString();
			await saveTerminalRecord(record);
			return record;
		}

		const metadata = await readExitMetadata(record);
		if (metadata && applyExitMetadata(record, metadata)) {
			applyLifecycleRecord(record, await readLifecycleRecord(record));
			applyExitMetadata(record, {});
			record.visibility = "hidden";
			record.paneId = undefined;
		} else {
			record.state = "orphaned";
			record.visibility = "unknown";
			record.paneId = undefined;
			record.lastError = textOf(panes) || `tmux session ${record.tmuxSession} is missing`;
		}
	} catch (error) {
		if (!applyLifecycleRecord(record, await readLifecycleRecord(record).catch(() => undefined))) record.state = "unknown";
		record.visibility = "unknown";
		record.lastError = error instanceof Error ? error.message : String(error);
	}
	record.updatedAt = new Date().toISOString();
	await saveTerminalRecord(record);
	return record;
}

async function getTerminal(pi: ExtensionAPI, name: string, signal?: AbortSignal): Promise<TerminalRecord> {
	const record = await loadTerminalRecord(name);
	if (!record) throw new Error(`Unknown worker: ${name}`);
	return refreshTerminalRecord(pi, record, signal);
}

function normalizeCapturedOutput(output: string): string {
	const lines = output.trimEnd().split("\n");
	while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
	if (/^Pane is dead \(/.test(lines[lines.length - 1] || "")) lines.pop();
	while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
	if (/^\[orchestrator\] command exited with code \d+/.test(lines[lines.length - 1] || "")) lines.pop();
	return lines.join("\n").trimEnd();
}

async function captureWorkerOutput(pi: ExtensionAPI, record: TerminalRecord, lines: number, signal?: AbortSignal): Promise<string> {
	const result = await execChecked(pi, "tmux", tmuxArgs("capture-pane", "-p", "-J", "-t", record.tmuxSession, "-S", `-${lines}`), { signal, timeout: 10_000 });
	const output = normalizeCapturedOutput(result.stdout);
	if (applyStructuredResult(record, output)) await saveTerminalRecord(record);
	return output;
}

async function autoSurfaceBlockedWorker(pi: ExtensionAPI, ctx: ExtensionContext, record: TerminalRecord, signal?: AbortSignal): Promise<boolean> {
	if (record.state !== "blocked" || record.needsUser !== true) return false;
	if (record.visibility === "visible" || record.paneId) return false;
	if (record.blockedSurfacedAt) return false;
	await surfaceTerminal(pi, ctx, record, false, signal, "tab");
	record.blockedSurfacedAt = new Date().toISOString();
	record.updatedAt = record.blockedSurfacedAt;
	await saveTerminalRecord(record);
	return true;
}

type WorkerPollEvent = {
	name: string;
	beforeState?: WorkerState;
	afterState: WorkerState;
	beforeVisibility?: WorkerVisibility;
	afterVisibility: WorkerVisibility;
	structuredStatus?: StructuredResult["status"];
	message?: string;
	surfaced?: boolean;
	error?: string;
};

function shouldInspectOutput(record: TerminalRecord): boolean {
	return record.state === "running" || record.state === "blocked" || record.state === "exited" || record.state === "failed";
}

function isOwnedWorker(record: TerminalRecord, ownerSessionId: string | undefined): boolean {
	return Boolean(ownerSessionId) && record.ownerSessionId === ownerSessionId;
}

function workerScope(records: TerminalRecord[], ctx: ExtensionContext, scope: WorkerScope): TerminalRecord[] {
	if (scope === "all") return records;
	const currentSessionId = ctx.sessionManager.getSessionId();
	return records.filter((record) => isOwnedWorker(record, currentSessionId));
}

function assertWorkerReadable(record: TerminalRecord, ctx: ExtensionContext, scope: WorkerScope) {
	if (scope === "all") return;
	const currentSessionId = ctx.sessionManager.getSessionId();
	if (!isOwnedWorker(record, currentSessionId)) {
		throw new Error(`Worker ${record.name} is owned by another orchestrator session (${record.ownerSessionId || "unknown"}). Use scope=all for explicit global inspection.`);
	}
}

async function pollWorkersOnce(pi: ExtensionAPI, ctx: ExtensionContext, lines: number, signal?: AbortSignal, scope: WorkerScope = "owned"): Promise<{ workers: TerminalRecord[]; events: WorkerPollEvent[] }> {
	const terminalRecords = workerScope(await loadTerminalRecords(), ctx, scope);
	const refreshed: TerminalRecord[] = [];
	const events: WorkerPollEvent[] = [];
	for (const record of terminalRecords) {
		const beforeState = record.state;
		const beforeVisibility = record.visibility;
		const beforeResult = record.structuredResult ? JSON.stringify(record.structuredResult) : undefined;
		const beforePaneId = record.paneId;
		const current = await refreshTerminalRecord(pi, record, signal);
		let error: string | undefined;
		let surfaced = false;
		if (shouldInspectOutput(current)) {
			await captureWorkerOutput(pi, current, lines, signal).catch((caught) => {
				error = caught instanceof Error ? caught.message : String(caught);
				current.lastError = error;
			});
			await autoSurfaceBlockedWorker(pi, ctx, current, signal).then((didSurface) => {
				surfaced = didSurface;
			}).catch((caught) => {
				error = caught instanceof Error ? caught.message : String(caught);
				current.lastError = error;
			});
		}
		const afterResult = current.structuredResult ? JSON.stringify(current.structuredResult) : undefined;
		const changed = beforeState !== current.state || beforeVisibility !== current.visibility || beforeResult !== afterResult || beforePaneId !== current.paneId || surfaced || error;
		if (changed) {
			events.push({
				name: current.name,
				beforeState,
				afterState: current.state,
				beforeVisibility,
				afterVisibility: current.visibility,
				structuredStatus: current.structuredResult?.status,
				message: current.statusMessage,
				surfaced,
				error,
			});
		}
		refreshed.push(current);
	}
	return { workers: refreshed, events };
}

function compactValue(value: unknown): string | undefined {
	if (value === undefined || value === null || value === false) return undefined;
	if (typeof value === "string") return value;
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
}

function formatWorkerStatusLine(record: TerminalRecord): string {
	const flags = [record.needsUser ? "needs-user" : undefined, record.visibility === "visible" && record.paneId ? `pane:${record.paneId}` : record.visibility].filter(Boolean).join(", ");
	const workspace = record.workspace === "worktree" && record.worktreeBranch ? ` branch:${record.worktreeBranch}` : "";
	const result = record.structuredResult?.status ? ` result:${record.structuredResult.status}` : "";
	const summary = record.statusMessage || record.structuredResult?.summary;
	const next = compactValue(record.structuredResult?.next_action);
	return `- ${record.name}: ${record.state}${flags ? ` (${flags})` : ""}${workspace}${result}${summary ? ` — ${summary}` : ""}${next ? ` | next: ${next}` : ""}`;
}

function formatWorkerDashboard(workers: TerminalRecord[], includeClosed: boolean): string {
	const visibleWorkers = includeClosed ? workers : workers.filter((worker) => worker.state !== "closed");
	const groups: Array<[string, (worker: TerminalRecord) => boolean]> = [
		["Needs attention", (worker) => worker.state === "blocked" || worker.needsUser === true],
		["Running", (worker) => worker.state === "running" || worker.state === "starting"],
		["Completed", (worker) => worker.state === "done" || worker.state === "exited"],
		["Failed / uncertain", (worker) => worker.state === "failed" || worker.state === "orphaned" || worker.state === "unknown"],
		["Closed", (worker) => worker.state === "closed"],
	];
	const counts = {
		total: visibleWorkers.length,
		attention: visibleWorkers.filter((worker) => worker.state === "blocked" || worker.needsUser === true).length,
		running: visibleWorkers.filter((worker) => worker.state === "running" || worker.state === "starting").length,
		completed: visibleWorkers.filter((worker) => worker.state === "done" || worker.state === "exited").length,
		failed: visibleWorkers.filter((worker) => worker.state === "failed" || worker.state === "orphaned" || worker.state === "unknown").length,
	};
	const sections = groups
		.map(([label, predicate]) => {
			const records = visibleWorkers.filter(predicate).sort((a, b) => (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt));
			if (!records.length) return undefined;
			return `## ${label}\n${records.map(formatWorkerStatusLine).join("\n")}`;
		})
		.filter(Boolean);
	return [`Workers: ${counts.total} total, ${counts.attention} attention, ${counts.running} running, ${counts.completed} completed, ${counts.failed} failed/uncertain.`, sections.join("\n\n") || "No active workers."].join("\n\n");
}

async function reportSurfacedTerminal(pi: ExtensionAPI, record: TerminalRecord, paneId: string, signal?: AbortSignal) {
	const title = record.title || record.name;
	await execChecked(pi, "herdr", ["pane", "rename", paneId, title], { signal, timeout: 10_000 });
	await execChecked(
		pi,
		"herdr",
		[
			"pane",
			"report-metadata",
			paneId,
			"--source",
			TERMINAL_SOURCE,
			"--display-agent",
			record.name,
			"--title",
			title,
			"--token",
			"orchestrator_worker=true",
			"--token",
			"orchestrator_backend=managed_tmux",
			"--token",
			"orchestrator_hidden=surfaced",
			"--ttl-ms",
			"600000",
		],
		{ signal, timeout: 10_000 },
	);
	await execChecked(
		pi,
		"herdr",
		[
			"pane",
			"report-agent-session",
			paneId,
			"--source",
			TERMINAL_SOURCE,
			"--agent",
			record.name,
			"--agent-session-id",
			record.tmuxSession,
			"--agent-session-path",
			`tmux://${TMUX_SERVER}/${record.tmuxSession}`,
			"--session-start-source",
			"pi-orchestrator",
		],
		{ signal, timeout: 10_000 },
	);
	await execChecked(
		pi,
		"herdr",
		[
			"pane",
			"report-agent",
			paneId,
			"--source",
			TERMINAL_SOURCE,
			"--agent",
			record.name,
			"--state",
			record.state === "blocked" ? "blocked" : record.state === "running" || record.state === "starting" ? "working" : record.state === "failed" || record.state === "orphaned" || record.state === "unknown" ? "blocked" : "idle",
			"--message",
			record.statusMessage || `Managed tmux worker ${record.name}`,
		],
		{ signal, timeout: 10_000 },
	);
}

async function surfaceTerminal(pi: ExtensionAPI, ctx: ExtensionContext, record: TerminalRecord, focus: boolean, signal?: AbortSignal, placement: "split" | "tab" = "split"): Promise<TerminalRecord> {
	await ensureHerdr(ctx, false);
	const paneId = placement === "tab" ? await createTabPane(pi, record.cwd, record.title || record.name, focus, signal) : await createPane(pi, record.cwd, focus, {}, signal);
	// A newly split pane can occasionally inherit pending line-editor text from shell startup/hooks.
	// Clear it before injecting the tmux attach command so we do not accidentally run e.g. "fooenv".
	await pi.exec("herdr", ["pane", "send-keys", paneId, "ctrl+c"], { signal, timeout: 5_000 });
	record.paneId = paneId;
	record.lastPaneId = paneId;
	record.visibility = "visible";
	record.surfacedAt = new Date().toISOString();
	record.updatedAt = record.surfacedAt;
	await reportSurfacedTerminal(pi, record, paneId, signal);
	await execChecked(
		pi,
		"herdr",
		[
			"pane",
			"run",
			paneId,
			`env -u TMUX tmux -L ${shellQuote(TMUX_SERVER)} -f ${shellQuote(terminalTmuxConfPath())} attach-session -t ${shellQuote(record.tmuxSession)}; code=$?; if [ $code -eq 0 ]; then exit; fi; echo '[orchestrator] tmux attach failed with code' $code; exec bash -i`,
		],
		{ signal, timeout: 10_000 },
	);
	await saveTerminalRecord(record);
	return record;
}

async function findSurfacePaneIds(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<string[]> {
	const result = await pi.exec("herdr", ["pane", "list"], { signal, timeout: 10_000 });
	if (result.code !== 0) return [];
	try {
		const parsed = parseFirstJsonObject(textOf(result));
		const panes = Array.isArray(parsed?.result?.panes) ? parsed.result.panes : [];
		return panes
			.filter((pane: any) => {
				const paneId = pane?.pane_id;
				if (typeof paneId !== "string" || !paneId) return false;
				if (paneId === record.paneId) return true;
				const tokens = pane?.tokens || {};
				const isOrchestratorPane = tokens.orchestrator_worker === "true" || tokens.orchestrator_backend === "managed_tmux";
				const matchesWorker = pane.agent === record.name || pane.display_agent === record.name || pane.label === record.name;
				return isOrchestratorPane && matchesWorker;
			})
			.map((pane: any) => pane.pane_id as string);
	} catch {
		return [];
	}
}

async function closeSurfacePane(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<void> {
	const paneIds = new Set<string>();
	if (record.paneId) paneIds.add(record.paneId);
	for (const paneId of await findSurfacePaneIds(pi, record, signal)) paneIds.add(paneId);
	if (!paneIds.size) {
		record.surfaceCloseError = undefined;
		return;
	}
	const errors: string[] = [];
	for (const paneId of paneIds) {
		const closed = await pi.exec("herdr", ["pane", "close", paneId], { signal, timeout: 10_000 });
		if (closed.code !== 0) {
			const output = textOf(closed);
			if (!/not found|unknown pane|pane .* not found/i.test(output)) errors.push(`${paneId}: ${output || "failed to close"}`);
		}
	}
	record.surfaceCloseError = errors.length ? errors.join("; ") : undefined;
}

async function hideTerminal(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<TerminalRecord> {
	const detach = await pi.exec("tmux", tmuxArgs("detach-client", "-s", record.tmuxSession), { signal, timeout: 10_000 });
	if (detach.code !== 0) {
		const clients = await pi.exec("tmux", tmuxArgs("list-clients", "-t", record.tmuxSession), { signal, timeout: 5_000 });
		if (clients.code === 0 && clients.stdout.trim()) throw new Error(`Failed to detach ${record.name}: ${textOf(detach)}`);
	}
	await closeSurfacePane(pi, record, signal);
	record.lastPaneId = record.paneId || record.lastPaneId;
	record.paneId = undefined;
	record.visibility = "hidden";
	record.hiddenAt = new Date().toISOString();
	record.updatedAt = record.hiddenAt;
	await saveTerminalRecord(record);
	return record;
}

function parseFirstJsonObject(output: string): any {
	for (const line of output.split("\n")) {
		const trimmed = line.trim();
		if (!trimmed.startsWith("{")) continue;
		try {
			return JSON.parse(trimmed);
		} catch {
			// keep looking
		}
	}
	throw new Error(`Could not parse Herdr JSON output:\n${output}`);
}

async function ensureHerdr(ctx: ExtensionContext, requireTui = true) {
	if (process.env.HERDR_ENV !== "1") {
		throw new Error("orchestrator requires running Pi inside Herdr (HERDR_ENV=1).");
	}
	if (requireTui && ctx.mode !== "tui") {
		throw new Error("orchestrator requires Pi TUI mode so child panels are visible.");
	}
}

function parsePaneIdFromHerdrOutput(output: string): string {
	const parsed = parseFirstJsonObject(output);
	const paneId = parsed?.result?.pane?.pane_id || parsed?.result?.root_pane?.pane_id || parsed?.result?.rootPane?.pane_id || parsed?.pane?.pane_id || parsed?.root_pane?.pane_id || parsed?.rootPane?.pane_id || parsed?.pane_id;
	if (typeof paneId !== "string" || !paneId) throw new Error(`Herdr did not return a pane id:\n${output}`);
	return paneId;
}

async function createPane(pi: ExtensionAPI, cwd: string, focus: boolean, env: Record<string, string | undefined> = {}, signal?: AbortSignal): Promise<string> {
	const envArgs = Object.entries(env)
		.filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].length > 0)
		.flatMap(([key, value]) => ["--env", `${key}=${value}`]);
	const args = ["pane", "split", "--current", "--direction", "right", "--cwd", cwd, ...envArgs, focus ? "--focus" : "--no-focus"];
	const result = await execChecked(pi, "herdr", args, { signal, timeout: 15_000 });
	return parsePaneIdFromHerdrOutput(textOf(result));
}

async function createTabPane(pi: ExtensionAPI, cwd: string, label: string, focus: boolean, signal?: AbortSignal): Promise<string> {
	const result = await execChecked(pi, "herdr", ["tab", "create", "--cwd", cwd, "--label", label, focus ? "--focus" : "--no-focus"], { signal, timeout: 15_000 });
	return parsePaneIdFromHerdrOutput(textOf(result));
}

function buildPiTaskPrompt(record: TerminalRecord, task: string, handoffContext?: string): string {
	return [
		"You are a hidden Pi worker started by the parent orchestrator.",
		"",
		`Worker: ${record.name}`,
		`CWD: ${record.cwd}`,
		"",
		"Task:",
		task,
		...(handoffContext ? ["", "Context handoff bundle:", handoffContext] : []),
		"",
		"Expectations:",
		"- Work independently in this terminal.",
		"- Keep changes and tool usage focused on the task.",
		"- If you need user/parent input, call orchestrator_report_state with state=blocked, explain exactly what is needed, then wait.",
		"- When actively working again after a block, call orchestrator_report_state with state=working.",
		"- When done, call orchestrator_report_state with state=done and a concise summary with files changed, verification run, and follow-up needed.",
		"- End with a final structured footer as the last non-whitespace output:",
		"  ORCHESTRATOR_RESULT:",
		"  {",
		'    "status": "done | blocked | failed",',
		'    "summary": "...",',
		'    "needs_user": false,',
		'    "next_action": null',
		"  }",
		"- The footer must be valid JSON and must be final if present.",
	].join("\n");
}

async function sendWorkerText(pi: ExtensionAPI, record: TerminalRecord, text: string, signal?: AbortSignal) {
	await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "-l", "--", text), { signal, timeout: 10_000 });
	await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "Enter"), { signal, timeout: 10_000 });
}

function looksPromptReady(output: string): boolean {
	const trimmed = output.trimEnd();
	if (!trimmed) return false;
	if (/\bREADY\b/i.test(trimmed)) return true;
	const lines = trimmed.split("\n").map((line) => line.trim()).filter(Boolean);
	const last = lines.at(-1) || "";
	return /(?:^|\s)(?:[>$#❯➜])\s*$/.test(last) || /(?:Codex|Pi).*?(?:remaining|NORMAL|thinking off)/i.test(trimmed);
}

async function waitForWorkerPromptReady(pi: ExtensionAPI, record: TerminalRecord, timeoutMs: number, signal?: AbortSignal): Promise<boolean> {
	const started = Date.now();
	let lastOutput = "";
	let stableSince = 0;
	while (Date.now() - started < timeoutMs) {
		const capture = await pi.exec("tmux", tmuxArgs("capture-pane", "-p", "-t", record.tmuxSession, "-S", "-40"), { signal, timeout: 5_000 });
		const output = capture.stdout || "";
		if (capture.code === 0 && looksPromptReady(output)) return true;
		if (output.trim() && output === lastOutput) {
			stableSince += 300;
			if (stableSince >= 900) return true;
		} else {
			lastOutput = output;
			stableSince = 0;
		}
		await delay(300);
	}
	return false;
}

async function startManagedTerminal(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	params: {
		command: string;
		name?: string;
		cwd?: string;
		workspace?: WorkerWorkspace;
		worktreePath?: string;
		worktreeBranch?: string;
		worktreeBase?: string;
		worktreeRepoRoot?: string;
		cleanupWorktreeOnClose?: boolean;
		env?: Record<string, string>;
		cols?: number;
		rows?: number;
		title?: string;
		keepAlive?: boolean;
		surface?: boolean;
		focus?: boolean;
	},
	signal?: AbortSignal,
): Promise<TerminalRecord> {
	await ensureTerminalStore();
	const name = await uniqueTerminalName(params.name, params.command);
	const cwd = path.resolve(params.cwd ? (path.isAbsolute(params.cwd) ? params.cwd : path.join(ctx.cwd, params.cwd)) : ctx.cwd);
	const extraEnv = validateEnv(params.env);
	const tmuxSession = `pi-orch-${name}`;
	const scriptsDir = path.join(terminalRoot(), "scripts");
	await fs.mkdir(scriptsDir, { recursive: true });
	const scriptPath = path.join(scriptsDir, `${name}.sh`);
	const exitFile = terminalExitPath(name);
	const lifecycleFile = terminalLifecyclePath(name);
	const ownerSessionId = ctx.sessionManager.getSessionId();
	const orchestratorEnv = {
		...(extraEnv || {}),
		PI_ORCHESTRATOR_WORKER_NAME: name,
		PI_ORCHESTRATOR_OWNER_SESSION_ID: ownerSessionId || "",
		PI_ORCHESTRATOR_STATE_FILE: lifecycleFile,
	};
	const envLines = Object.entries(orchestratorEnv)
		.map(([key, value]) => `export ${key}=${shellQuote(value)}`)
		.join("\n");
	await fs.rm(exitFile, { force: true });
	await fs.rm(lifecycleFile, { force: true });
	await fs.writeFile(
		scriptPath,
		[
			"#!/usr/bin/env bash",
			"set -uo pipefail",
			"tmux set-option -w remain-on-exit on 2>/dev/null || true",
			`printf '%s' ${shellQuote(`\u001b]0;${(params.title || name).replace(/[\u0000-\u001f\u007f]/g, "")}\u0007`)} || true`,
			`EXIT_FILE=${shellQuote(exitFile)}`,
			"STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
			envLines,
			"set +e",
			`bash -lc ${shellQuote(params.command)}`,
			"code=$?",
			"set -e",
			"ENDED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
			'printf \'{"startedAt":"%s","endedAt":"%s","exitCode":%s,"reason":"command_exit"}\\n\' "$STARTED_AT" "$ENDED_AT" "$code" > "$EXIT_FILE"',
			'echo ""',
			'echo "[orchestrator] command exited with code $code"',
			params.keepAlive === true ? 'exec bash -i' : 'exit "$code"',
			"",
		].join("\n"),
		{ mode: 0o700 },
	);
	const now = new Date().toISOString();
	const record: TerminalRecord = {
		id: randomUUID(),
		name,
		command: params.command,
		cwd,
		ownerSessionId,
		ownerCwd: ctx.cwd,
		tmuxServer: TMUX_SERVER,
		tmuxSession,
		createdAt: now,
		updatedAt: now,
		state: "starting",
		visibility: "hidden",
		workspace: params.workspace || "current",
		worktreePath: params.worktreePath,
		worktreeBranch: params.worktreeBranch,
		worktreeBase: params.worktreeBase,
		worktreeRepoRoot: params.worktreeRepoRoot,
		cleanupWorktreeOnClose: params.cleanupWorktreeOnClose,
		title: params.title || name,
		exitFile,
		lifecycleFile,
	};
	await writeLifecycleRecord(record, { state: "starting", source: "orchestrator", message: `Starting worker ${name}`, needsUser: false, updatedAt: now });
	applyLifecycleRecord(record, await readLifecycleRecord(record));
	await saveTerminalRecord(record);
	try {
		await execChecked(
			pi,
			"tmux",
			tmuxArgs("new-session", "-d", "-x", String(params.cols ?? 140), "-y", String(params.rows ?? 40), "-s", tmuxSession, "-c", cwd, scriptPath),
			{ signal, timeout: 15_000 },
		);
	} catch (error) {
		record.state = "failed";
		record.updatedAt = new Date().toISOString();
		record.lastError = error instanceof Error ? error.message : String(error);
		await saveTerminalRecord(record);
		throw error;
	}
	record.state = "running";
	record.startedAt = new Date().toISOString();
	record.updatedAt = record.startedAt;
	await writeLifecycleRecord(record, { state: "working", source: "orchestrator", message: `Worker ${name} is running`, needsUser: false, updatedAt: record.startedAt });
	applyLifecycleRecord(record, await readLifecycleRecord(record));
	await saveTerminalRecord(record);
	if (params.surface) await surfaceTerminal(pi, ctx, record, params.focus ?? true, signal);
	return record;
}

async function startWorkerFromParams(pi: ExtensionAPI, ctx: ExtensionContext, params: any, signal?: AbortSignal): Promise<{ record: TerminalRecord; kind: "pi" | "shell" }> {
	const kind = params.kind ?? "pi";
	if (params.task && kind !== "pi") throw new Error("task is only supported for kind=pi workers.");
	const command = params.command ?? (kind === "pi" ? "pi" : undefined);
	if (!command) throw new Error("command is required when kind=shell.");
	const name = await uniqueTerminalName(params.name, command);
	const workspace = params.workspace ?? "current";
	const workspaceRecord = workspace === "worktree" ? await createWorkerWorktree(pi, ctx, { name, cwd: params.cwd, branch: params.branch, base: params.base, worktreePath: params.worktreePath, cleanupWorktreeOnClose: params.cleanupWorktreeOnClose }, signal) : { cwd: params.cwd, workspace: "current" as const };
	let record: TerminalRecord;
	try {
		record = await startManagedTerminal(
			pi,
			ctx,
			{
				command,
				name,
				cwd: workspaceRecord.cwd,
				workspace: workspaceRecord.workspace,
				worktreePath: workspaceRecord.worktreePath,
				worktreeBranch: workspaceRecord.worktreeBranch,
				worktreeBase: workspaceRecord.worktreeBase,
				worktreeRepoRoot: workspaceRecord.worktreeRepoRoot,
				cleanupWorktreeOnClose: workspaceRecord.cleanupWorktreeOnClose,
				env: params.env,
				cols: params.cols,
				rows: params.rows,
				title: params.title || params.name || (kind === "pi" ? "pi-worker" : undefined),
				keepAlive: params.keepAlive,
				surface: (params.visibility ?? "hidden") === "visible",
				focus: params.focus,
			},
			signal,
		);
	} catch (error) {
		if (workspaceRecord.workspace === "worktree") {
			await cleanupWorkerWorktree(pi, { id: "", name, command, cwd: workspaceRecord.cwd || ctx.cwd, ownerCwd: ctx.cwd, tmuxServer: TMUX_SERVER, tmuxSession: "", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), state: "failed", visibility: "hidden", exitFile: terminalExitPath(name), ...workspaceRecord }, signal).catch(() => undefined);
		}
		throw error;
	}
	if (params.task && kind === "pi") {
		record.task = params.task;
		const handoffContext = buildHandoffContext(ctx, {
			handoffPrompt: params.handoffPrompt,
			recentInteractions: params.recentInteractions,
			includeToolCalls: params.includeToolCalls,
			handoffMaxChars: params.handoffMaxChars,
		});
		const prompt = buildPiTaskPrompt(record, params.task, handoffContext);
		record.lastPrompt = prompt;
		await saveTerminalRecord(record);
		const ready = await waitForWorkerPromptReady(pi, record, params.taskPromptTimeoutMs ?? 8000, signal);
		record.promptReadyTimedOut = !ready;
		if (ready) record.promptReadyAt = new Date().toISOString();
		await sendWorkerText(pi, record, prompt, signal);
		record.promptedAt = new Date().toISOString();
		record.updatedAt = record.promptedAt;
		await saveTerminalRecord(record);
	}
	return { record, kind };
}

function startedWorkerText(record: TerminalRecord, kind: "pi" | "shell"): string {
	return `Started ${kind} worker ${record.name} (${record.paneId ? `visible in Herdr pane ${record.paneId}` : "hidden"})${record.task ? " and sent task prompt" : ""}${record.workspace === "worktree" ? ` in worktree ${record.worktreePath}` : ""}.`;
}

function isActiveForWatcher(record: TerminalRecord): boolean {
	return record.state === "starting" || record.state === "running" || record.state === "blocked" || record.state === "unknown" || record.state === "orphaned";
}

function isParentWakeState(state: WorkerState): state is ParentWakeState {
	return state === "blocked" || state === "done" || state === "exited" || state === "failed";
}

function parentWakeEventKey(record: TerminalRecord): string | undefined {
	if (!isParentWakeState(record.state)) return undefined;
	const matchingLifecycle =
		(record.state === "blocked" && record.lifecycleState === "blocked") ||
		(record.state === "done" && record.lifecycleState === "done") ||
		(record.state === "failed" && record.lifecycleState === "failed");
	if (matchingLifecycle && record.lifecycleUpdatedAt) return `${record.state}:lifecycle:${record.lifecycleUpdatedAt}`;
	if ((record.state === "exited" || record.state === "failed") && record.endedAt) {
		return `${record.state}:exit:${record.endedAt}:${record.exitCode ?? ""}:${record.exitSignal ?? ""}`;
	}
	if (record.structuredResult) return `${record.state}:result:${JSON.stringify(record.structuredResult)}`;
	return `${record.state}:state`;
}

function watcherEnabled(): boolean {
	return !/^(0|false|off|no)$/i.test(process.env.PI_ORCHESTRATOR_WATCH || "");
}

function watcherIntervalMs(): number {
	const parsed = Number(process.env.PI_ORCHESTRATOR_WATCH_INTERVAL_MS || "2500");
	return Number.isFinite(parsed) ? Math.max(1_000, Math.min(parsed, 30_000)) : 2_500;
}

export default function orchestratorExtension(pi: ExtensionAPI) {
	let watcherTimer: ReturnType<typeof setTimeout> | undefined;
	let watcherRunning = false;
	let watcherShuttingDown = false;
	let watcherStartedAt: string | undefined;
	let watcherLastTickAt: string | undefined;
	let watcherLastStopAt: string | undefined;
	let watcherLastError: string | undefined;

	async function notifyParentOfWorkerUpdates(records: TerminalRecord[]): Promise<void> {
		const pending: Array<{ record: TerminalRecord; eventKey: string }> = [];
		for (const record of records) {
			const eventKey = parentWakeEventKey(record);
			if (eventKey && record.parentNotificationKey !== eventKey) pending.push({ record, eventKey });
		}
		if (!pending.length) return;

		pi.sendMessage(
			{
				customType: "orchestrator-worker-update",
				content: [
					"Orchestrator worker state update:",
					...pending.map(({ record }) => formatWorkerStatusLine(record)),
					"",
					"Handle these updates now. Inspect worker output or status when needed. If the broader task requires more work, continue autonomously and dispatch follow-up workers when appropriate. If the task is complete, or the user needs an update or decision, send the user a concise message. Do not ask the user to poll for worker completion.",
				].join("\n"),
				display: false,
				details: {
					workers: pending.map(({ record }) => ({
						name: record.name,
						state: record.state,
						message: record.statusMessage || record.structuredResult?.summary,
						needsUser: record.needsUser,
						branch: record.worktreeBranch,
					})),
				},
			},
			{ deliverAs: "followUp", triggerTurn: true },
		);

		const queuedAt = new Date().toISOString();
		for (const { record: notified, eventKey } of pending) {
			const current = (await loadTerminalRecord(notified.name)) || notified;
			if (parentWakeEventKey(current) !== eventKey) continue;
			current.parentNotificationKey = eventKey;
			current.parentNotificationQueuedAt = queuedAt;
			current.updatedAt = queuedAt;
			await saveTerminalRecord(current);
		}
	}

	async function refreshOwnedWorkersStateOnly(ctx: ExtensionContext, signal?: AbortSignal): Promise<TerminalRecord[]> {
		const currentSessionId = ctx.sessionManager.getSessionId();
		const records = (await loadTerminalRecords()).filter((record) => record.ownerSessionId === currentSessionId && record.state !== "closed");
		const refreshed: TerminalRecord[] = [];
		for (const record of records) {
			try {
				const current = await refreshTerminalRecord(pi, record, signal);
				current.watcherLastObservedAt = new Date().toISOString();
				current.watcherLastError = undefined;
				await saveTerminalRecord(current);
				if (current.paneId && current.visibility === "visible") await reportSurfacedTerminal(pi, current, current.paneId, signal).catch(async (error) => {
					current.watcherLastError = error instanceof Error ? error.message : String(error);
					await saveTerminalRecord(current).catch(() => undefined);
				});
				refreshed.push(current);
			} catch (error) {
				record.watcherLastObservedAt = new Date().toISOString();
				record.watcherLastError = error instanceof Error ? error.message : String(error);
				await saveTerminalRecord(record).catch(() => undefined);
				refreshed.push(record);
			}
		}
		return refreshed;
	}

	function ensureWatcherStarted(ctx: ExtensionContext) {
		if (!watcherEnabled() || watcherTimer || watcherRunning) return;
		watcherShuttingDown = false;
		watcherStartedAt = new Date().toISOString();
		const tick = async () => {
			watcherTimer = undefined;
			watcherRunning = true;
			try {
				watcherLastTickAt = new Date().toISOString();
				const refreshed = await refreshOwnedWorkersStateOnly(ctx);
				await notifyParentOfWorkerUpdates(refreshed);
				watcherLastError = undefined;
				if (!watcherShuttingDown && refreshed.some(isActiveForWatcher)) {
					watcherTimer = setTimeout(tick, watcherIntervalMs());
				} else {
					watcherLastStopAt = new Date().toISOString();
				}
			} catch (error) {
				watcherLastError = error instanceof Error ? error.message : String(error);
				if (!watcherShuttingDown) watcherTimer = setTimeout(tick, watcherIntervalMs());
			} finally {
				watcherRunning = false;
			}
		};
		watcherTimer = setTimeout(tick, watcherIntervalMs());
	}

	pi.on("session_shutdown", async () => {
		watcherShuttingDown = true;
		if (watcherTimer) clearTimeout(watcherTimer);
		watcherTimer = undefined;
		watcherLastStopAt = new Date().toISOString();
	});

	pi.registerTool({
		name: "orchestrator_report_state",
		label: "Report Orchestrator Worker State",
		description: "Report this worker's lifecycle state to its parent orchestrator without writing or reading terminal transcript content.",
		promptSnippet: "Use orchestrator_report_state from inside an orchestrator-created worker to report working, blocked, done, or failed.",
		parameters: AgentLifecycleReportParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const name = process.env.PI_ORCHESTRATOR_WORKER_NAME;
			const ownerSessionId = process.env.PI_ORCHESTRATOR_OWNER_SESSION_ID;
			const stateFile = process.env.PI_ORCHESTRATOR_STATE_FILE;
			if (!name || !stateFile) throw new Error("orchestrator_report_state is only available inside an orchestrator-created worker.");
			const record = await loadTerminalRecord(name);
			if (!record) throw new Error(`Unknown orchestrator worker from environment: ${name}`);
			if (record.ownerSessionId && ownerSessionId !== record.ownerSessionId) throw new Error("Worker owner session mismatch; refusing to report state.");
			if (path.resolve(stateFile) !== path.resolve(record.lifecycleFile || terminalLifecyclePath(record.name))) throw new Error("Worker lifecycle state file mismatch; refusing to report state.");
			const updatedAt = new Date().toISOString();
			const lifecycle = await writeLifecycleRecord(record, {
				state: params.state,
				source: "child",
				message: params.message,
				needsUser: params.needsUser ?? params.state === "blocked",
				updatedAt,
			});
			applyLifecycleRecord(record, lifecycle);
			record.updatedAt = updatedAt;
			await saveTerminalRecord(record);
			if (record.paneId && record.visibility === "visible") await reportSurfacedTerminal(pi, record, record.paneId, signal);
			return { content: [{ type: "text", text: `Reported ${record.name} ${params.state}${record.needsUser ? " (needs user)" : ""}.${params.message ? `\n${params.message}` : ""}` }], details: { worker: record, lifecycle } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_start",
		label: "Start Worker",
		description: "Start a unified orchestrator worker. Workers are managed terminals that may run a Pi subagent or an arbitrary shell command, hidden by default and surfaced into Herdr on demand.",
		promptSnippet: "Use orchestrator_worker_start for subagents or command workers that can be hidden or visible. Model routing is the parent orchestrator's decision per worker: keep the parent/current model for review, planning, architecture, final synthesis, and high-stakes judgement; choose Spark high for smaller scoped Pi workers by setting command to `pi --model openai-codex/gpt-5.3-codex-spark:high`. Spark high is a good fit for focused implementation, bugfixes, tests, repo inspection, first-pass reviews, and parallel subagent work. Do not choose Spark high when the task needs image input, very large context beyond Spark's 128K window, deep architectural judgement, or final review.",
		parameters: WorkerStartParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const { record, kind } = await startWorkerFromParams(pi, ctx, params, signal);
			ensureWatcherStarted(ctx);
			return { content: [{ type: "text", text: startedWorkerText(record, kind) }], details: { worker: record, kind } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_start_many",
		label: "Start Many Workers",
		description: "Start multiple orchestrator workers. Each array item accepts the same fields as orchestrator_worker_start.",
		promptSnippet: "Use orchestrator_worker_start_many when launching several independent workers with distinct tasks/instructions. Model routing is the parent orchestrator's decision per worker: keep the parent/current model for review, planning, architecture, final synthesis, and high-stakes judgement; choose Spark high for smaller scoped Pi workers by setting each Pi worker command to `pi --model openai-codex/gpt-5.3-codex-spark:high`. Spark high is a good fit for focused implementation, bugfixes, tests, repo inspection, first-pass reviews, and parallel subagent work. Do not choose Spark high when the task needs image input, very large context beyond Spark's 128K window, deep architectural judgement, or final review.",
		parameters: WorkerStartManyParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const started: Array<{ record: TerminalRecord; kind: "pi" | "shell" }> = [];
			const failed: Array<{ index: number; name?: string; error: string }> = [];
			for (let index = 0; index < params.workers.length; index++) {
				const workerParams = params.workers[index];
				try {
					started.push(await startWorkerFromParams(pi, ctx, workerParams, signal));
				} catch (error) {
					failed.push({ index, name: workerParams.name, error: error instanceof Error ? error.message : String(error) });
					if (params.continueOnError === false) break;
				}
			}
			if (started.length) ensureWatcherStarted(ctx);
			const lines = [
				`Started ${started.length}/${params.workers.length} workers${failed.length ? `; ${failed.length} failed` : ""}.`,
				...started.map(({ record, kind }) => `- ${record.name}: ${kind}, ${record.workspace || "current"}${record.worktreePath ? `, ${record.worktreePath}` : ""}`),
				...failed.map((failure) => `- failed[${failure.index}]${failure.name ? ` ${failure.name}` : ""}: ${failure.error}`),
			];
			return { content: [{ type: "text", text: lines.join("\n") }], details: { started: started.map((item) => item.record), failed } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_list",
		label: "List Workers",
		description: "List unified orchestrator workers.",
		parameters: Type.Object({
			scope: Type.Optional(WorkerScopeSchema),
		}),
		async execute(_id, params, signal, _onUpdate, ctx) {
			const { workers } = await pollWorkersOnce(pi, ctx, TMUX_HISTORY_LIMIT, signal, params.scope ?? "owned");
			const sorted = workers.sort((a, b) => (a.state === "blocked" ? 0 : 1) - (b.state === "blocked" ? 0 : 1) || (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt));
			const text = sorted
				.map((r) => `worker:${r.name}\n  state: ${r.state}${r.needsUser ? " (needs user)" : ""}\n  visibility: ${r.visibility}${r.paneId ? ` (${r.paneId})` : ""}\n  workspace: ${r.workspace || "current"}${r.worktreeBranch ? ` (${r.worktreeBranch})` : ""}\n  tmux: ${r.tmuxServer}/${r.tmuxSession}\n  cwd: ${r.cwd}\n  command: ${r.command}${r.task ? `\n  task: ${r.task}` : ""}${r.lifecycleState ? `\n  lifecycle: ${r.lifecycleState}${r.lifecycleSource ? ` (${r.lifecycleSource})` : ""}` : ""}${r.statusMessage ? `\n  message: ${r.statusMessage}` : ""}${r.structuredResult ? `\n  result: ${r.structuredResult.status}` : ""}${r.structuredResultParseError ? `\n  resultParseNote: ${r.structuredResultParseError}` : ""}${typeof r.exitCode === "number" ? `\n  exitCode: ${r.exitCode}` : ""}${r.worktreeCleanupError ? `\n  worktreeCleanupError: ${r.worktreeCleanupError}` : ""}${r.worktreeBranchCleanupError ? `\n  worktreeBranchCleanupError: ${r.worktreeBranchCleanupError}` : ""}${r.lastError ? `\n  lastError: ${r.lastError}` : ""}`)
				.join("\n\n") || "No orchestrator workers recorded.";
			return { content: [{ type: "text", text }], details: { workers } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_poll",
		label: "Poll Workers",
		description: "Refresh all workers once, parse structured results, and auto-surface hidden blocked workers without dumping full output.",
		parameters: WorkerPollParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const { workers, events } = await pollWorkersOnce(pi, ctx, params.lines ?? TMUX_HISTORY_LIMIT, signal, params.scope ?? "owned");
			const active = workers.filter((worker) => worker.state !== "closed").length;
			const blocked = workers.filter((worker) => worker.state === "blocked").length;
			const text = events.length
				? events.map((event) => `worker:${event.name}\n  state: ${event.beforeState} -> ${event.afterState}\n  visibility: ${event.beforeVisibility} -> ${event.afterVisibility}${event.surfaced ? "\n  surfaced: true" : ""}${event.structuredStatus ? `\n  result: ${event.structuredStatus}` : ""}${event.message ? `\n  message: ${event.message}` : ""}${event.error ? `\n  error: ${event.error}` : ""}`).join("\n\n")
				: "No worker changes detected.";
			return { content: [{ type: "text", text: `Polled ${workers.length} workers (${active} active, ${blocked} blocked).\n\n${text}` }], details: { workers, events } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_status",
		label: "Worker Status",
		description: "Show a compact grouped dashboard of orchestrator workers after one poll pass.",
		parameters: WorkerStatusParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			ensureWatcherStarted(ctx);
			const { workers, events } = await pollWorkersOnce(pi, ctx, params.lines ?? TMUX_HISTORY_LIMIT, signal, params.scope ?? "owned");
			const text = formatWorkerDashboard(workers, params.includeClosed ?? false);
			const eventNote = events.length ? `\n\nRecent changes: ${events.map((event) => `${event.name}:${event.beforeState}->${event.afterState}${event.surfaced ? ":surfaced" : ""}`).join(", ")}` : "";
			const watcherNote = `\n\nWatcher: ${watcherEnabled() ? (watcherTimer || watcherRunning ? "running" : "idle") : "disabled"}${watcherLastTickAt ? `, last tick ${watcherLastTickAt}` : ""}${watcherLastError ? `, last error: ${watcherLastError}` : ""}`;
			return { content: [{ type: "text", text: `${text}${eventNote}${watcherNote}` }], details: { workers, events, watcher: { enabled: watcherEnabled(), running: Boolean(watcherTimer || watcherRunning), startedAt: watcherStartedAt, lastTickAt: watcherLastTickAt, lastStopAt: watcherLastStopAt, lastError: watcherLastError } } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_mark",
		label: "Mark Worker State",
		description: "Manually mark a worker as blocked/needs-user or running. This is the explicit handoff primitive before automatic prompt/auth detection exists.",
		parameters: WorkerMarkParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			if (!["running", "blocked"].includes(record.state)) {
				throw new Error(`Cannot mark ${record.name} as ${params.state} because current state is ${record.state}.`);
			}
			record.state = params.state;
			record.needsUser = params.needsUser ?? params.state === "blocked";
			record.statusMessage = params.state === "blocked" ? params.message || "Worker needs user/parent attention." : params.message;
			record.markedAt = new Date().toISOString();
			record.updatedAt = record.markedAt;
			await writeLifecycleRecord(record, {
				state: params.state === "blocked" ? "blocked" : "working",
				source: "manual",
				message: record.statusMessage,
				needsUser: record.needsUser,
				updatedAt: record.markedAt,
			});
			applyLifecycleRecord(record, await readLifecycleRecord(record));
			if (params.state === "running") {
				record.needsUser = false;
				record.blockedSurfacedAt = undefined;
				if (!params.message) record.statusMessage = undefined;
			}
			await saveTerminalRecord(record);
			let surfaceNote = "";
			let hideNote = "";
			if (params.state === "blocked" && record.visibility !== "visible") {
				await surfaceTerminal(pi, ctx, record, false, signal, "tab");
				surfaceNote = `\nSurfaced in Herdr pane ${record.paneId}.`;
			} else if (params.state === "running" && record.visibility === "visible") {
				await reportSurfacedTerminal(pi, record, record.paneId!, signal);
				await hideTerminal(pi, record, signal);
				hideNote = "\nHidden again after resuming.";
			} else if (record.paneId) {
				await reportSurfacedTerminal(pi, record, record.paneId, signal);
			}
			return { content: [{ type: "text", text: `Marked ${record.name} ${record.state}${record.needsUser ? " (needs user)" : ""}.${surfaceNote}${hideNote}${record.statusMessage ? `\n${record.statusMessage}` : ""}` }], details: { worker: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_read",
		label: "Read Worker",
		description: "Read recent output from a unified managed worker.",
		parameters: TerminalReadParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertWorkerReadable(record, ctx, params.scope ?? "owned");
			const output = await captureWorkerOutput(pi, record, params.lines ?? 80, signal);
			const surfaced = params.scope === "all" ? false : await autoSurfaceBlockedWorker(pi, ctx, record, signal);
			const resultNote = record.structuredResult ? `\n\nParsed ORCHESTRATOR_RESULT:\n${JSON.stringify(record.structuredResult, null, 2)}` : record.structuredResultParseError ? `\n\nResult footer parse note: ${record.structuredResultParseError}` : "";
			const surfaceNote = surfaced ? `\n\nBlocked worker surfaced in Herdr pane ${record.paneId}.` : "";
			return { content: [{ type: "text", text: `${output || "(no output)"}${resultNote}${surfaceNote}` }], details: { worker: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_send",
		label: "Send Worker Input",
		description: "Send text/input to a unified managed worker. By default only the owner orchestrator session may mutate it.",
		parameters: TerminalSendParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "-l", "--", params.text), { signal, timeout: 10_000 });
			if (params.enter ?? true) await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "Enter"), { signal, timeout: 10_000 });
			return { content: [{ type: "text", text: `Sent input to ${record.name}.` }], details: { worker: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_surface",
		label: "Surface Worker",
		description: "Attach a unified managed worker into a Herdr pane.",
		parameters: TerminalSurfaceParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			await surfaceTerminal(pi, ctx, record, params.focus ?? true, signal);
			return { content: [{ type: "text", text: `Surfaced ${record.name} in Herdr pane ${record.paneId}.` }], details: { worker: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_hide",
		label: "Hide Worker",
		description: "Detach Herdr clients from a unified managed worker while keeping it alive hidden.",
		parameters: TerminalNameParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			await hideTerminal(pi, record, signal);
			return { content: [{ type: "text", text: `Detached/sent ${record.name} back to hidden.` }], details: { worker: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_close",
		label: "Close Worker",
		description: "Kill a unified managed worker and mark its registry record closed. By default only the owner orchestrator session may close it.",
		parameters: TerminalNameParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			const killed = await pi.exec("tmux", tmuxArgs("kill-session", "-t", record.tmuxSession), { signal, timeout: 10_000 });
			if (killed.code !== 0 && (await terminalExists(pi, record, signal))) throw new Error(`Failed to close ${record.name}: ${textOf(killed)}`);
			await closeSurfacePane(pi, record, signal);
			const worktreeNote = await cleanupWorkerWorktree(pi, record, signal);
			record.state = "closed";
			record.closedAt = new Date().toISOString();
			record.updatedAt = record.closedAt;
			record.lastPaneId = record.paneId || record.lastPaneId;
			record.paneId = undefined;
			record.visibility = "hidden";
			await saveTerminalRecord(record);
			return { content: [{ type: "text", text: `Closed worker ${record.name}.${worktreeNote || ""}` }], details: { worker: record } };
		},
	});














}
