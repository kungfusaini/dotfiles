import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";

type WorkspaceMode = "current" | "worktree";
type DriverMode = "parent" | "human";
type PermissionMode = "read-only" | "edit";

const WORKSPACE_CONTEXT_EVENT = "pi:workspace-context:resolve";

interface WorkspaceContextResult {
	projectID?: string;
	streamID?: string;
}

interface WorkerRecord {
	name: string;
	task: string;
	workspace: WorkspaceMode;
	driver: DriverMode;
	permission: PermissionMode;
	cwd: string;
	paneId: string;
	branch?: string;
	worktreePath?: string;
	createdAt: string;
	inheritedStreamID?: string;
	lastPrompt?: string;
	paneClosed?: boolean;
	closedAt?: string;
	closeError?: string;
	finalOutput?: string;
}

interface TerminalRecord {
	id: string;
	name: string;
	command: string;
	cwd: string;
	ownerSessionId?: string;
	ownerCwd: string;
	tmuxServer: string;
	tmuxSession: string;
	createdAt: string;
	state: "starting" | "running" | "blocked" | "done" | "failed" | "closed";
	title?: string;
	paneId?: string;
	surfacedAt?: string;
	closedAt?: string;
	lastError?: string;
}

const workers = new Map<string, WorkerRecord>();
const terminals = new Map<string, TerminalRecord>();
const TMUX_SERVER = "pi-orchestrator";
const TERMINAL_SOURCE = "pi-orchestrator-managed-terminal";

const WorkspaceSchema = StringEnum(["current", "worktree"] as const, {
	description: "Where to start the child: current cwd or a fresh git worktree.",
	default: "current",
});
const DriverSchema = StringEnum(["parent", "human"] as const, {
	description: "Who drives the child after startup. parent waits for completion; human leaves it visible for manual driving.",
	default: "parent",
});
const PermissionSchema = StringEnum(["read-only", "edit"] as const, {
	description: "Whether the child may edit. Defaults to read-only in current mode and edit in worktree mode.",
});

const DelegateParams = Type.Object({
	task: Type.String({ description: "Task to hand to the child Pi agent." }),
	name: Type.Optional(Type.String({ description: "Optional short child agent name. Will be slugged and made unique if needed." })),
	workspace: Type.Optional(WorkspaceSchema),
	driver: Type.Optional(DriverSchema),
	permission: Type.Optional(PermissionSchema),
	branch: Type.Optional(Type.String({ description: "Optional git branch name when workspace=worktree." })),
	base: Type.Optional(Type.String({ description: "Optional base ref for git worktree add. Defaults to HEAD." })),
	worktreePath: Type.Optional(Type.String({ description: "Optional checkout path for workspace=worktree." })),
	focus: Type.Optional(Type.Boolean({ description: "Focus the new pane after creation. Default false." })),
	inheritStream: Type.Optional(Type.Boolean({ description: "Explicitly pass the parent stream to the child. Defaults true; set false to force project scope." })),
	closeOnDone: Type.Optional(Type.Boolean({ description: "When driver=parent, read final output and close the child pane after it settles. Default true for parent, false for human." })),
	waitTimeoutMs: Type.Optional(Type.Integer({ minimum: 1, description: "Parent driver wait timeout in ms. Omit for Herdr default/indefinite." })),
});

const WorkerNameParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_delegate or orchestrator_list." }),
});

const ReadParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_delegate or orchestrator_list." }),
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to read. Default 80." })),
});

const PromptParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_delegate or orchestrator_list." }),
	prompt: Type.String({ description: "Follow-up prompt to submit to the child." }),
	wait: Type.Optional(Type.Boolean({ description: "Wait for the child to settle after prompting. Default false." })),
	timeoutMs: Type.Optional(Type.Integer({ minimum: 1, description: "Optional wait timeout in milliseconds." })),
});

const TerminalStartParams = Type.Object({
	command: Type.String({ description: "Shell command to run in the hidden managed terminal." }),
	name: Type.Optional(Type.String({ description: "Optional stable terminal worker name." })),
	cwd: Type.Optional(Type.String({ description: "Working directory. Defaults to current Pi cwd." })),
	env: Type.Optional(Type.Record(Type.String(), Type.String(), { description: "Extra environment variables for the terminal command." })),
	cols: Type.Optional(Type.Integer({ minimum: 40, description: "Initial hidden terminal width. Default 140." })),
	rows: Type.Optional(Type.Integer({ minimum: 10, description: "Initial hidden terminal height. Default 40." })),
	title: Type.Optional(Type.String({ description: "Display title when surfaced." })),
	keepAlive: Type.Optional(Type.Boolean({ description: "Keep an interactive shell alive after the command exits so output remains readable. Default true." })),
	surface: Type.Optional(Type.Boolean({ description: "Immediately surface the terminal into Herdr after it starts. Default false." })),
	focus: Type.Optional(Type.Boolean({ description: "Focus the surfaced Herdr pane when surface=true. Default true." })),
});

const TerminalNameParams = Type.Object({
	name: Type.String({ description: "Terminal worker name returned by orchestrator_terminal_start/list." }),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a terminal owned by another orchestrator session. Default false." })),
});

const TerminalReadParams = Type.Object({
	name: Type.String({ description: "Terminal worker name returned by orchestrator_terminal_start/list." }),
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to read. Default 80." })),
});

const TerminalSendParams = Type.Object({
	name: Type.String({ description: "Terminal worker name returned by orchestrator_terminal_start/list." }),
	text: Type.String({ description: "Text to send to the hidden/surfaced terminal." }),
	enter: Type.Optional(Type.Boolean({ description: "Press Enter after the text. Default true." })),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a terminal owned by another orchestrator session. Default false." })),
});

const TerminalSurfaceParams = Type.Object({
	name: Type.String({ description: "Terminal worker name returned by orchestrator_terminal_start/list." }),
	focus: Type.Optional(Type.Boolean({ description: "Focus the surfaced Herdr pane. Default true." })),
	force: Type.Optional(Type.Boolean({ description: "Allow surfacing a terminal owned by another orchestrator session. Default false." })),
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

function uniqueName(requested: string | undefined, task: string): string {
	const base = slug(requested || task.split(/\s+/).slice(0, 4).join("-"));
	if (!workers.has(base)) return base;
	for (let i = 2; i < 100; i++) {
		const candidate = `${base}-${i}`.slice(0, 32);
		if (!workers.has(candidate)) return candidate;
	}
	return `${base.slice(0, 20)}-${Date.now().toString(36)}`.slice(0, 32);
}

function xdgDataHome(): string {
	return process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local", "share");
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

function tmuxArgs(...args: string[]): string[] {
	return ["-L", TMUX_SERVER, "-f", terminalTmuxConfPath(), ...args];
}

function shellQuote(value: string): string {
	return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function textOf(result: { stdout?: string; stderr?: string; code?: number }): string {
	return [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
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
	await fs.writeFile(
		terminalTmuxConfPath(),
		[
			"set -g status off",
			"set -g extended-keys-format csi-u",
			'set -g default-terminal "tmux-256color"',
			"set -g history-limit 5000",
			"set -g exit-empty off",
			"set -g detach-on-destroy off",
			"set -g set-titles on",
			'run-shell -b "true"',
			"",
		].join("\n"),
		{ mode: 0o600 },
	);
}

async function saveTerminalRecord(record: TerminalRecord) {
	validateTerminalName(record.name);
	await ensureTerminalStore();
	const file = terminalRecordPath(record.name);
	const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
	await fs.writeFile(tmp, `${JSON.stringify(record, null, 2)}\n`, { mode: 0o600 });
	await fs.rename(tmp, file);
	terminals.set(record.name, record);
}

async function loadTerminalRecord(name: string): Promise<TerminalRecord | undefined> {
	validateTerminalName(name);
	const cached = terminals.get(name);
	if (cached) return cached;
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

async function getTerminal(pi: ExtensionAPI, name: string, signal?: AbortSignal): Promise<TerminalRecord> {
	const record = await loadTerminalRecord(name);
	if (!record) throw new Error(`Unknown terminal worker: ${name}`);
	if (!(await terminalExists(pi, record, signal)) && record.state !== "closed" && record.state !== "failed") {
		record.state = "done";
		await saveTerminalRecord(record);
	}
	return record;
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
			record.state === "blocked" ? "blocked" : record.state === "running" || record.state === "starting" ? "working" : "idle",
			"--message",
			`Managed tmux terminal ${record.name}`,
		],
		{ signal, timeout: 10_000 },
	);
}

async function surfaceTerminal(pi: ExtensionAPI, ctx: ExtensionContext, record: TerminalRecord, focus: boolean, signal?: AbortSignal): Promise<TerminalRecord> {
	await ensureHerdr(ctx, false);
	const paneId = await createPane(pi, record.cwd, focus, {}, signal);
	// A newly split pane can occasionally inherit pending line-editor text from shell startup/hooks.
	// Clear it before injecting the tmux attach command so we do not accidentally run e.g. "fooenv".
	await pi.exec("herdr", ["pane", "send-keys", paneId, "ctrl+c"], { signal, timeout: 5_000 });
	record.paneId = paneId;
	record.surfacedAt = new Date().toISOString();
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

async function createPane(pi: ExtensionAPI, cwd: string, focus: boolean, env: Record<string, string | undefined> = {}, signal?: AbortSignal): Promise<string> {
	const envArgs = Object.entries(env)
		.filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].length > 0)
		.flatMap(([key, value]) => ["--env", `${key}=${value}`]);
	const args = ["pane", "split", "--current", "--direction", "right", "--cwd", cwd, ...envArgs, focus ? "--focus" : "--no-focus"];
	const result = await execChecked(pi, "herdr", args, { signal, timeout: 15_000 });
	const parsed = parseFirstJsonObject(textOf(result));
	const paneId = parsed?.result?.pane?.pane_id || parsed?.pane?.pane_id || parsed?.pane_id;
	if (typeof paneId !== "string" || !paneId) throw new Error(`Herdr did not return a pane id:\n${textOf(result)}`);
	return paneId;
}

async function gitRoot(pi: ExtensionAPI, cwd: string, signal?: AbortSignal): Promise<string> {
	const result = await execChecked(pi, "git", ["rev-parse", "--show-toplevel"], { cwd, signal, timeout: 10_000 });
	return result.stdout.trim();
}

function resolveWorkspaceContext(pi: ExtensionAPI, ctx: ExtensionContext): WorkspaceContextResult | undefined {
	const request: { cwd: string; sessionID?: string; result?: WorkspaceContextResult } = {
		cwd: ctx.cwd,
		sessionID: ctx.sessionManager.getSessionId(),
	};
	pi.events.emit(WORKSPACE_CONTEXT_EVENT, request);
	return request.result;
}

async function createWorktree(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	name: string,
	branch: string | undefined,
	base: string | undefined,
	worktreePath: string | undefined,
	signal?: AbortSignal,
): Promise<{ cwd: string; branch: string }> {
	const root = await gitRoot(pi, ctx.cwd, signal);
	const repoName = path.basename(root) || "repo";
	const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
	const actualBranch = branch || `agent/${name}-${stamp}`;
	const defaultPath = path.join(xdgDataHome(), "pi", "orchestrator", "worktrees", `${repoName}-${name}-${stamp}`);
	const actualPath = worktreePath
		? path.resolve(path.isAbsolute(worktreePath) ? worktreePath : path.join(ctx.cwd, worktreePath))
		: defaultPath;
	await fs.mkdir(path.dirname(actualPath), { recursive: true });
	await execChecked(pi, "git", ["worktree", "add", "-b", actualBranch, actualPath, base || "HEAD"], {
		cwd: root,
		signal,
		timeout: 60_000,
	});
	return { cwd: actualPath, branch: actualBranch };
}

function buildHandoff(worker: WorkerRecord): string {
	const lines = [
		"You are a child Pi agent opened by a parent Pi orchestrator.",
		"",
		`Task: ${worker.task}`,
		"",
		"Workspace:",
		`- mode: ${worker.workspace}`,
		`- cwd: ${worker.cwd}`,
	];
	if (worker.branch) lines.push(`- branch: ${worker.branch}`);
	if (worker.worktreePath) lines.push(`- worktree path: ${worker.worktreePath}`);
	lines.push(
		"",
		"Permissions:",
		worker.permission === "read-only"
			? "- Do not edit files. Inspect, run safe read/test commands if useful, and report findings only."
			: "- You may edit files in this workspace for the assigned task. Keep changes focused.",
		"",
		"Context policy:",
		"- Do not assume you have the parent conversation.",
		"- Use your own tools to inspect files, git status/diff, and docs as needed.",
		"- Do not ask the parent to paste worklog/project instructions unless genuinely needed; Pi may already provide normal startup context and worklog tools.",
		"",
		"Output expected:",
		worker.permission === "read-only"
			? "- Concise report with summary, important findings, and suggested next steps."
			: "- Summary of changes, files touched, verification run, and any follow-up needed.",
	);
	return lines.join("\n");
}

function summarizeWorker(worker: WorkerRecord): string {
	return [
		`${worker.name}`,
		`  pane: ${worker.paneId}`,
		`  cwd: ${worker.cwd}`,
		`  workspace: ${worker.workspace}`,
		`  driver: ${worker.driver}`,
		`  permission: ${worker.permission}`,
		worker.branch ? `  branch: ${worker.branch}` : undefined,
		worker.inheritedStreamID ? `  stream: ${worker.inheritedStreamID}` : undefined,
		worker.paneClosed ? `  paneClosed: true${worker.closedAt ? ` (${worker.closedAt})` : ""}` : undefined,
		worker.closeError ? `  closeError: ${worker.closeError}` : undefined,
		`  task: ${worker.task}`,
	]
		.filter(Boolean)
		.join("\n");
}

export default function orchestratorExtension(pi: ExtensionAPI) {
	pi.on("session_start", (_event, ctx) => {
		workers.clear();
		for (const entry of ctx.sessionManager.getEntries()) {
			if (entry.type === "custom" && entry.customType === "orchestrator-worker") {
				const worker = entry.data as WorkerRecord;
				if (worker?.name && worker?.paneId) workers.set(worker.name, worker);
			}
		}
	});

	pi.registerTool({
		name: "orchestrator_delegate",
		label: "Delegate Pi",
		description: "Open a visible child Pi agent in Herdr, optionally in a new git worktree, and hand it a compact task prompt.",
		promptSnippet: "Open a visible child Pi agent in Herdr for delegated review, debugging, or implementation tasks.",
		promptGuidelines: [
			"Use orchestrator_delegate when the user explicitly asks to spin up, open, delegate to, or drive another Pi agent/panel.",
			"For reviewing current uncommitted changes, call orchestrator_delegate with workspace=current and permission=read-only rather than creating a worktree.",
			"For independent implementation or experiments, prefer orchestrator_delegate with workspace=worktree.",
		],
		parameters: DelegateParams,
		executionMode: "sequential",
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			await ensureHerdr(ctx);
			const workspace = params.workspace ?? "current";
			const driver = params.driver ?? "parent";
			const permission = params.permission ?? (workspace === "worktree" ? "edit" : "read-only");
			const closeOnDone = params.closeOnDone ?? driver === "parent";
			const name = uniqueName(params.name, params.task);
			const parentWorkspace = resolveWorkspaceContext(pi, ctx);
			const inheritedStreamID = params.inheritStream === false ? undefined : parentWorkspace?.streamID;

			let cwd = ctx.cwd;
			let branch: string | undefined;
			let worktreePath: string | undefined;
			if (workspace === "worktree") {
				const created = await createWorktree(pi, ctx, name, params.branch, params.base, params.worktreePath, signal);
				cwd = created.cwd;
				branch = created.branch;
				worktreePath = created.cwd;
			}

			const paneId = await createPane(pi, cwd, params.focus ?? false, {
				PI_PROJECT_WORKSPACE_PROJECT_ID: parentWorkspace?.projectID,
				PI_PROJECT_WORKSPACE_STREAM_ID: params.inheritStream === false ? "__project__" : inheritedStreamID,
			}, signal);
			const worker: WorkerRecord = {
				name,
				task: params.task,
				workspace,
				driver,
				permission,
				cwd,
				paneId,
				branch,
				worktreePath,
				createdAt: new Date().toISOString(),
				inheritedStreamID,
			};

			await execChecked(pi, "herdr", ["agent", "start", name, "--kind", "pi", "--pane", paneId], {
				signal,
				timeout: 45_000,
			});

			const handoff = buildHandoff(worker);
			worker.lastPrompt = handoff;
			workers.set(name, worker);
			pi.appendEntry("orchestrator-worker", worker);

			const promptArgs = ["agent", "prompt", name, handoff];
			if (driver === "parent") {
				promptArgs.push("--wait");
				if (params.waitTimeoutMs) promptArgs.push("--timeout", String(params.waitTimeoutMs));
			}
			await execChecked(pi, "herdr", promptArgs, { signal, timeout: driver === "parent" ? params.waitTimeoutMs : 15_000 });

			if (driver === "parent") {
				try {
					const readResult = await execChecked(pi, "herdr", ["agent", "read", name, "--lines", "200"], {
						signal,
						timeout: 10_000,
					});
					worker.finalOutput = textOf(readResult) || undefined;
				} catch (error) {
					worker.finalOutput = `Could not read child output before cleanup: ${error instanceof Error ? error.message : String(error)}`;
				}
			}

			if (driver === "parent" && closeOnDone) {
				try {
					await execChecked(pi, "herdr", ["pane", "close", paneId], { signal, timeout: 10_000 });
					worker.paneClosed = true;
					worker.closedAt = new Date().toISOString();
				} catch (error) {
					worker.closeError = error instanceof Error ? error.message : String(error);
				}
				pi.appendEntry("orchestrator-worker", worker);
			}

			return {
				content: [
					{
						type: "text",
						text: `Started child Pi agent ${name}.\n${summarizeWorker(worker)}${
							driver === "human" ? "\n\nHuman driver mode: initial handoff submitted; not waiting." : ""
						}${worker.finalOutput ? `\n\nChild output:\n${worker.finalOutput}` : ""}`,
					},
				],
				details: { worker },
			};
		},
		renderCall(args, theme) {
			const workspace = args.workspace ?? "current";
			const driver = args.driver ?? "parent";
			const name = args.name || "new child";
			return new Text(
				theme.fg("toolTitle", theme.bold("orchestrator ")) +
					theme.fg("accent", String(name)) +
					theme.fg("muted", ` ${workspace}/${driver}`) +
					`\n  ${theme.fg("dim", String(args.task || ""))}`,
				0,
				0,
			);
		},
		renderResult(result, _options, theme) {
			const worker = (result.details as { worker?: WorkerRecord } | undefined)?.worker;
			if (!worker) {
				const first = result.content?.[0];
				return new Text(first?.type === "text" ? first.text : "", 0, 0);
			}
			return new Text(
				theme.fg("success", "✓ ") +
					theme.fg("accent", worker.name) +
					theme.fg("dim", worker.paneClosed ? ` pane ${worker.paneId} closed` : ` pane ${worker.paneId}`),
				0,
				0,
			);
		},
	});

	pi.registerTool({
		name: "orchestrator_list",
		label: "List Pi Children",
		description: "List child Pi agents opened by orchestrator_delegate in this session.",
		parameters: Type.Object({}),
		async execute() {
			const all = Array.from(workers.values());
			return {
				content: [{ type: "text", text: all.length ? all.map(summarizeWorker).join("\n\n") : "No orchestrator child agents recorded." }],
				details: { workers: all },
			};
		},
	});

	pi.registerTool({
		name: "orchestrator_focus",
		label: "Focus Pi Child",
		description: "Focus a child Pi agent panel by orchestrator worker name.",
		parameters: WorkerNameParams,
		async execute(_id, params, signal) {
			const worker = workers.get(params.name);
			if (!worker) return { content: [{ type: "text", text: `Unknown worker: ${params.name}` }], details: { found: false } };
			await execChecked(pi, "herdr", ["agent", "focus", worker.name], { signal, timeout: 10_000 });
			return { content: [{ type: "text", text: `Focused ${worker.name}.` }], details: { worker } };
		},
	});

	pi.registerTool({
		name: "orchestrator_read",
		label: "Read Pi Child",
		description: "Read recent terminal output from a child Pi agent panel.",
		parameters: ReadParams,
		async execute(_id, params, signal) {
			const worker = workers.get(params.name);
			if (!worker) return { content: [{ type: "text", text: `Unknown worker: ${params.name}` }], details: { found: false } };
			const result = await execChecked(pi, "herdr", ["agent", "read", worker.name, "--lines", String(params.lines ?? 80)], {
				signal,
				timeout: 10_000,
			});
			return { content: [{ type: "text", text: textOf(result) || "(no output)" }], details: { worker } };
		},
	});

	pi.registerTool({
		name: "orchestrator_prompt",
		label: "Prompt Pi Child",
		description: "Send a follow-up prompt to a child Pi agent by orchestrator worker name.",
		parameters: PromptParams,
		async execute(_id, params, signal) {
			const worker = workers.get(params.name);
			if (!worker) return { content: [{ type: "text", text: `Unknown worker: ${params.name}` }], details: { found: false } };
			const args = ["agent", "prompt", worker.name, params.prompt];
			if (params.wait) {
				args.push("--wait");
				if (params.timeoutMs) args.push("--timeout", String(params.timeoutMs));
			}
			await execChecked(pi, "herdr", args, { signal, timeout: params.timeoutMs || (params.wait ? undefined : 15_000) });
			worker.lastPrompt = params.prompt;
			return { content: [{ type: "text", text: `Prompt sent to ${worker.name}${params.wait ? " and settled" : ""}.` }], details: { worker } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_start",
		label: "Start Hidden Terminal",
		description: "Start a hidden managed tmux terminal in the shared pi-orchestrator tmux server. The terminal can later be read, sent input, surfaced into Herdr, hidden, or closed.",
		promptSnippet: "Use orchestrator_terminal_start for hidden/background terminal work that may later need to be surfaced into Herdr.",
		parameters: TerminalStartParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			await ensureTerminalStore();
			const name = await uniqueTerminalName(params.name, params.command);
			const cwd = path.resolve(params.cwd ? (path.isAbsolute(params.cwd) ? params.cwd : path.join(ctx.cwd, params.cwd)) : ctx.cwd);
			const extraEnv = validateEnv(params.env);
			const tmuxSession = `pi-orch-${name}`;
			const scriptsDir = path.join(terminalRoot(), "scripts");
			await fs.mkdir(scriptsDir, { recursive: true });
			const scriptPath = path.join(scriptsDir, `${name}.sh`);
			const envLines = Object.entries(extraEnv || {})
				.map(([key, value]) => `export ${key}=${shellQuote(value)}`)
				.join("\n");
			await fs.writeFile(
				scriptPath,
				[
					"#!/usr/bin/env bash",
					"set -uo pipefail",
					`printf '%s' ${shellQuote(`\u001b]0;${(params.title || name).replace(/[\u0000-\u001f\u007f]/g, "")}\u0007`)} || true`,
					envLines,
					"set +e",
					`bash -lc ${shellQuote(params.command)}`,
					"code=$?",
					"set -e",
					'echo ""',
					'echo "[orchestrator] command exited with code $code"',
					params.keepAlive === false ? 'exit "$code"' : 'exec bash -i',
					"",
				].join("\n"),
				{ mode: 0o700 },
			);
			const record: TerminalRecord = {
				id: randomUUID(),
				name,
				command: params.command,
				cwd,
				ownerSessionId: ctx.sessionManager.getSessionId(),
				ownerCwd: ctx.cwd,
				tmuxServer: TMUX_SERVER,
				tmuxSession,
				createdAt: new Date().toISOString(),
				state: "starting",
				title: params.title || name,
			};
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
				record.lastError = error instanceof Error ? error.message : String(error);
				await saveTerminalRecord(record);
				throw error;
			}
			record.state = "running";
			await saveTerminalRecord(record);
			if (params.surface) await surfaceTerminal(pi, ctx, record, params.focus ?? true, signal);
			return {
				content: [{ type: "text", text: `Started hidden terminal ${name} in shared tmux server ${TMUX_SERVER}.${record.paneId ? `\nSurfaced in Herdr pane ${record.paneId}.` : ""}` }],
				details: { terminal: record },
			};
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_list",
		label: "List Hidden Terminals",
		description: "List managed hidden terminals from the shared pi-orchestrator tmux server registry.",
		parameters: Type.Object({}),
		async execute(_id, _params, signal) {
			const records = await loadTerminalRecords();
			for (const record of records) {
				if (!(await terminalExists(pi, record, signal)) && record.state !== "closed" && record.state !== "failed") {
					record.state = "done";
					record.paneId = undefined;
					await saveTerminalRecord(record);
				}
			}
			const text = records.length
				? records
						.map((r) => `${r.name}\n  state: ${r.state}\n  owner: ${r.ownerSessionId || "unknown"}\n  tmux: ${r.tmuxServer}/${r.tmuxSession}\n  cwd: ${r.cwd}\n  pane: ${r.paneId || "(hidden)"}\n  command: ${r.command}`)
						.join("\n\n")
				: "No managed terminals recorded.";
			return { content: [{ type: "text", text }], details: { terminals: records } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_read",
		label: "Read Hidden Terminal",
		description: "Read recent output from a managed hidden/surfaced tmux terminal.",
		parameters: TerminalReadParams,
		async execute(_id, params, signal) {
			const record = await getTerminal(pi, params.name, signal);
			const lines = String(params.lines ?? 80);
			const result = await execChecked(pi, "tmux", tmuxArgs("capture-pane", "-p", "-t", record.tmuxSession, "-S", `-${lines}`), { signal, timeout: 10_000 });
			return { content: [{ type: "text", text: result.stdout.trimEnd() || "(no output)" }], details: { terminal: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_send",
		label: "Send Hidden Terminal Input",
		description: "Send text/input to a managed terminal. By default only the owner orchestrator session may mutate it.",
		parameters: TerminalSendParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "-l", "--", params.text), { signal, timeout: 10_000 });
			if (params.enter ?? true) {
				await execChecked(pi, "tmux", tmuxArgs("send-keys", "-t", record.tmuxSession, "Enter"), { signal, timeout: 10_000 });
			}
			return { content: [{ type: "text", text: `Sent input to ${record.name}.` }], details: { terminal: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_surface",
		label: "Surface Hidden Terminal",
		description: "Attach a managed hidden terminal into a Herdr pane and report it in the Herdr agents panel.",
		parameters: TerminalSurfaceParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			await surfaceTerminal(pi, ctx, record, params.focus ?? true, signal);
			return { content: [{ type: "text", text: `Surfaced ${record.name} in Herdr pane ${record.paneId}.` }], details: { terminal: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_hide",
		label: "Hide Surfaced Terminal",
		description: "Detach Herdr clients from a managed tmux terminal while keeping the terminal alive hidden.",
		parameters: TerminalNameParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			const detach = await pi.exec("tmux", tmuxArgs("detach-client", "-s", record.tmuxSession), { signal, timeout: 10_000 });
			if (detach.code !== 0) {
				const clients = await pi.exec("tmux", tmuxArgs("list-clients", "-t", record.tmuxSession), { signal, timeout: 5_000 });
				if (clients.code === 0 && clients.stdout.trim()) {
					throw new Error(`Failed to detach ${record.name}: ${textOf(detach)}`);
				}
			}
			record.paneId = undefined;
			await saveTerminalRecord(record);
			return { content: [{ type: "text", text: `Detached/sent ${record.name} back to hidden tmux.` }], details: { terminal: record } };
		},
	});

	pi.registerTool({
		name: "orchestrator_terminal_close",
		label: "Close Hidden Terminal",
		description: "Kill a managed terminal session and mark its registry record closed. By default only the owner orchestrator session may close it.",
		parameters: TerminalNameParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const record = await getTerminal(pi, params.name, signal);
			assertTerminalOwner(record, ctx, params.force);
			const killed = await pi.exec("tmux", tmuxArgs("kill-session", "-t", record.tmuxSession), { signal, timeout: 10_000 });
			if (killed.code !== 0 && (await terminalExists(pi, record, signal))) {
				throw new Error(`Failed to close ${record.name}: ${textOf(killed)}`);
			}
			record.state = "closed";
			record.closedAt = new Date().toISOString();
			record.paneId = undefined;
			await saveTerminalRecord(record);
			return { content: [{ type: "text", text: `Closed terminal ${record.name}.` }], details: { terminal: record } };
		},
	});
}
