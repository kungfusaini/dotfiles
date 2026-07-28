import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";

type WorkspaceMode = "current" | "worktree";
type DriverMode = "parent" | "human";
type PermissionMode = "read-only" | "edit";

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
	lastPrompt?: string;
	paneClosed?: boolean;
	closedAt?: string;
	closeError?: string;
	finalOutput?: string;
}

const workers = new Map<string, WorkerRecord>();

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

async function ensureHerdr(ctx: ExtensionContext) {
	if (process.env.HERDR_ENV !== "1") {
		throw new Error("orchestrator requires running Pi inside Herdr (HERDR_ENV=1).");
	}
	if (ctx.mode !== "tui") {
		throw new Error("orchestrator requires Pi TUI mode so child panels are visible.");
	}
}

async function createPane(pi: ExtensionAPI, cwd: string, focus: boolean, signal?: AbortSignal): Promise<string> {
	const args = ["pane", "split", "--current", "--direction", "right", "--cwd", cwd, focus ? "--focus" : "--no-focus"];
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

			let cwd = ctx.cwd;
			let branch: string | undefined;
			let worktreePath: string | undefined;
			if (workspace === "worktree") {
				const created = await createWorktree(pi, ctx, name, params.branch, params.base, params.worktreePath, signal);
				cwd = created.cwd;
				branch = created.branch;
				worktreePath = created.cwd;
			}

			const paneId = await createPane(pi, cwd, params.focus ?? false, signal);
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
}
