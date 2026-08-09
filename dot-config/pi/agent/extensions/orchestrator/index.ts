import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type WorkerState = "starting" | "running" | "blocked" | "exited" | "failed" | "closed" | "orphaned" | "unknown";
type WorkerVisibility = "hidden" | "visible" | "unknown";

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
	updatedAt: string;
	state: WorkerState;
	visibility: WorkerVisibility;
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
	lastError?: string;
}

const terminals = new Map<string, TerminalRecord>();
const TMUX_SERVER = "pi-orchestrator";
const TERMINAL_SOURCE = "pi-orchestrator-managed-terminal";

const TerminalNameParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	force: Type.Optional(Type.Boolean({ description: "Allow mutating a worker owned by another orchestrator session. Default false." })),
});

const TerminalReadParams = Type.Object({
	name: Type.String({ description: "Worker name returned by orchestrator_worker_start/list." }),
	lines: Type.Optional(Type.Integer({ minimum: 1, description: "Recent terminal lines to read. Default 80." })),
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

const WorkerStartParams = Type.Object({
	kind: Type.Optional(WorkerKindSchema),
	command: Type.Optional(Type.String({ description: "Shell command to run. Defaults to `pi` when kind=pi; required when kind=shell." })),
	name: Type.Optional(Type.String({ description: "Optional stable worker name." })),
	cwd: Type.Optional(Type.String({ description: "Working directory. Defaults to current Pi cwd." })),
	env: Type.Optional(Type.Record(Type.String(), Type.String(), { description: "Extra environment variables for the worker command." })),
	cols: Type.Optional(Type.Integer({ minimum: 40, description: "Initial hidden terminal width. Default 140." })),
	rows: Type.Optional(Type.Integer({ minimum: 10, description: "Initial hidden terminal height. Default 40." })),
	title: Type.Optional(Type.String({ description: "Display title when surfaced." })),
	keepAlive: Type.Optional(Type.Boolean({ description: "Open an interactive shell after the command exits instead of exiting. Default false; exited panes remain inspectable via tmux." })),
	visibility: Type.Optional(WorkerVisibilitySchema),
	focus: Type.Optional(Type.Boolean({ description: "Focus the surfaced Herdr pane when visibility=visible. Default true." })),
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

function terminalExitPath(name: string): string {
	return path.join(terminalExitDir(), `${validateTerminalName(name)}.json`);
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
	await fs.mkdir(terminalExitDir(), { recursive: true });
	await fs.writeFile(
		terminalTmuxConfPath(),
		[
			"set -g status off",
			"set -g extended-keys-format csi-u",
			'set -g default-terminal "tmux-256color"',
			"set -g history-limit 5000",
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

function applyExitMetadata(record: TerminalRecord, metadata: Partial<TerminalRecord>): boolean {
	if (metadata.startedAt) record.startedAt = metadata.startedAt;
	if (metadata.endedAt) record.endedAt = metadata.endedAt;
	if (typeof metadata.exitCode === "number") record.exitCode = metadata.exitCode;
	if (metadata.exitSignal) record.exitSignal = metadata.exitSignal;
	if (record.endedAt || typeof record.exitCode === "number" || record.exitSignal) {
		record.state = record.exitSignal || (record.exitCode ?? 0) !== 0 ? "failed" : "exited";
		return true;
	}
	return false;
}

async function refreshTerminalRecord(pi: ExtensionAPI, record: TerminalRecord, signal?: AbortSignal): Promise<TerminalRecord> {
	if (!record.exitFile) record.exitFile = terminalExitPath(record.name);
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
			const metadata = await readExitMetadata(record);
			if (metadata) applyExitMetadata(record, metadata);
			if (dead === "1") {
				const code = Number(status);
				if (Number.isFinite(code)) record.exitCode = code;
				if (paneSignal) record.exitSignal = paneSignal;
				if (deadTime && !record.endedAt) record.endedAt = new Date(Number(deadTime) * 1000).toISOString();
				record.state = record.exitSignal || (record.exitCode ?? 0) !== 0 ? "failed" : "exited";
			} else if (!metadata || !applyExitMetadata(record, metadata)) {
				record.state = record.state === "blocked" ? "blocked" : "running";
			}
			record.visibility = record.paneId ? "visible" : "hidden";
			record.updatedAt = new Date().toISOString();
			await saveTerminalRecord(record);
			return record;
		}

		const metadata = await readExitMetadata(record);
		if (metadata && applyExitMetadata(record, metadata)) {
			record.visibility = "hidden";
			record.paneId = undefined;
		} else {
			record.state = "orphaned";
			record.visibility = "unknown";
			record.paneId = undefined;
			record.lastError = textOf(panes) || `tmux session ${record.tmuxSession} is missing`;
		}
	} catch (error) {
		record.state = "unknown";
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

async function startManagedTerminal(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	params: {
		command: string;
		name?: string;
		cwd?: string;
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
	const envLines = Object.entries(extraEnv || {})
		.map(([key, value]) => `export ${key}=${shellQuote(value)}`)
		.join("\n");
	await fs.rm(exitFile, { force: true });
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
		ownerSessionId: ctx.sessionManager.getSessionId(),
		ownerCwd: ctx.cwd,
		tmuxServer: TMUX_SERVER,
		tmuxSession,
		createdAt: now,
		updatedAt: now,
		state: "starting",
		visibility: "hidden",
		title: params.title || name,
		exitFile,
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
		record.updatedAt = new Date().toISOString();
		record.lastError = error instanceof Error ? error.message : String(error);
		await saveTerminalRecord(record);
		throw error;
	}
	record.state = "running";
	record.startedAt = new Date().toISOString();
	record.updatedAt = record.startedAt;
	await saveTerminalRecord(record);
	if (params.surface) await surfaceTerminal(pi, ctx, record, params.focus ?? true, signal);
	return record;
}

export default function orchestratorExtension(pi: ExtensionAPI) {
	pi.registerTool({
		name: "orchestrator_worker_start",
		label: "Start Worker",
		description: "Start a unified orchestrator worker. Workers are managed terminals that may run a Pi subagent or an arbitrary shell command, hidden by default and surfaced into Herdr on demand.",
		promptSnippet: "Use orchestrator_worker_start for subagents or command workers that can be hidden or visible.",
		parameters: WorkerStartParams,
		async execute(_id, params, signal, _onUpdate, ctx) {
			const kind = params.kind ?? "pi";
			const command = params.command ?? (kind === "pi" ? "pi" : undefined);
			if (!command) throw new Error("command is required when kind=shell.");
			const record = await startManagedTerminal(
				pi,
				ctx,
				{
					command,
					name: params.name,
					cwd: params.cwd,
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
			return {
				content: [
					{
						type: "text",
						text: `Started ${kind} worker ${record.name} (${record.paneId ? `visible in Herdr pane ${record.paneId}` : "hidden"}).`,
					},
				],
				details: { worker: record, kind },
			};
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_list",
		label: "List Workers",
		description: "List unified orchestrator workers.",
		parameters: Type.Object({}),
		async execute(_id, _params, signal) {
			const terminalRecords = await loadTerminalRecords();
			const refreshed = [] as TerminalRecord[];
			for (const record of terminalRecords) refreshed.push(await refreshTerminalRecord(pi, record, signal));
			const text = refreshed
				.map((r) => `worker:${r.name}\n  state: ${r.state}\n  visibility: ${r.visibility}${r.paneId ? ` (${r.paneId})` : ""}\n  tmux: ${r.tmuxServer}/${r.tmuxSession}\n  cwd: ${r.cwd}\n  command: ${r.command}${typeof r.exitCode === "number" ? `\n  exitCode: ${r.exitCode}` : ""}${r.lastError ? `\n  lastError: ${r.lastError}` : ""}`)
				.join("\n\n") || "No orchestrator workers recorded.";
			return { content: [{ type: "text", text }], details: { workers: refreshed } };
		},
	});

	pi.registerTool({
		name: "orchestrator_worker_read",
		label: "Read Worker",
		description: "Read recent output from a unified managed worker.",
		parameters: TerminalReadParams,
		async execute(_id, params, signal) {
			const record = await getTerminal(pi, params.name, signal);
			const lines = String(params.lines ?? 80);
			const result = await execChecked(pi, "tmux", tmuxArgs("capture-pane", "-p", "-t", record.tmuxSession, "-S", `-${lines}`), { signal, timeout: 10_000 });
			return { content: [{ type: "text", text: result.stdout.trimEnd() || "(no output)" }], details: { worker: record } };
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
			const detach = await pi.exec("tmux", tmuxArgs("detach-client", "-s", record.tmuxSession), { signal, timeout: 10_000 });
			if (detach.code !== 0) {
				const clients = await pi.exec("tmux", tmuxArgs("list-clients", "-t", record.tmuxSession), { signal, timeout: 5_000 });
				if (clients.code === 0 && clients.stdout.trim()) throw new Error(`Failed to detach ${record.name}: ${textOf(detach)}`);
			}
			record.lastPaneId = record.paneId || record.lastPaneId;
			record.paneId = undefined;
			record.visibility = "hidden";
			record.hiddenAt = new Date().toISOString();
			record.updatedAt = record.hiddenAt;
			await saveTerminalRecord(record);
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
			record.state = "closed";
			record.closedAt = new Date().toISOString();
			record.updatedAt = record.closedAt;
			record.lastPaneId = record.paneId || record.lastPaneId;
			record.paneId = undefined;
			record.visibility = "hidden";
			await saveTerminalRecord(record);
			return { content: [{ type: "text", text: `Closed worker ${record.name}.` }], details: { worker: record } };
		},
	});














}
