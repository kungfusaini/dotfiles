import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { resolveContext } from "./projects.ts";
import { ensureStore, type ProjectContextInfo } from "./store.ts";
import {
	archivePlan,
	clearCurrentPlanRef,
	createPlan,
	formatPlanList,
	listPlans,
	planWorkflowContext,
	resolveCurrentPlan,
	resolvePlan,
	setCurrentPlan,
	updatePlan,
} from "./plans.ts";

const PLAN_MODE_TOOLS = [
	"read",
	"bash",
	"grep",
	"find",
	"ls",
	"question",
	"pi_todo",
	"pi_plan_create",
	"pi_plan_current",
	"pi_plan_list",
	"pi_plan_read",
	"pi_plan_update",
	"pi_plan_archive",
];
const PLAN_MODE_DISABLED_TOOLS = new Set(["edit", "write"]);
const PLAN_MODE_MANAGED_TOOLS = new Set([...PLAN_MODE_TOOLS, "edit", "write"]);
const APPROVAL_OPTIONS = ["Approve and select", "Approve", "Discuss further"];

interface PlanModeState {
	enabled: boolean;
	toolsBeforePlanMode?: string[];
}

type TodoStatus = "pending" | "in_progress" | "done" | "blocked";

interface TodoItem {
	id: string;
	text: string;
	status: TodoStatus;
	note?: string;
	createdAt: string;
	updatedAt: string;
}

interface TodoState {
	items: TodoItem[];
	updatedAt: string;
}

function contextInfo(cwd: string): ProjectContextInfo {
	return ensureStore(resolveContext(cwd));
}

function unique(names: string[]): string[] {
	return [...new Set(names)];
}

function getPlanModeTools(activeToolNames: string[], allToolNames: string[]): string[] {
	const allowed = new Set(allToolNames);
	return unique([
		...activeToolNames.filter((name) => !PLAN_MODE_DISABLED_TOOLS.has(name)),
		...PLAN_MODE_TOOLS,
	]).filter((name) => allowed.has(name));
}

function getNormalModeTools(activeToolNames: string[]): string[] {
	return unique([
		"read",
		"bash",
		"edit",
		"write",
		"pi_todo",
		...activeToolNames.filter((name) => !PLAN_MODE_MANAGED_TOOLS.has(name)),
	]);
}

function textResult(text: string, details: Record<string, unknown> = {}) {
	return { content: [{ type: "text" as const, text }], details };
}

function now(): string {
	return new Date().toISOString();
}

function normalizeTodoStatus(status: unknown): TodoStatus {
	return status === "in_progress" || status === "done" || status === "blocked" ? status : "pending";
}

function todoSummary(items: TodoItem[]): string {
	if (!items.length) return "No active todos.";
	return items.map((item, index) => {
		const marker = item.status === "done" ? "✓" : item.status === "blocked" ? "!" : "○";
		const note = item.note ? ` — ${item.note}` : "";
		return `${index + 1}. ${marker} ${item.text}${note} (${item.id})`;
	}).join("\n");
}

function todoDisplayLines(items: TodoItem[]): string[] {
	if (!items.length) return ["No active todos."];
	return items.map((item, index) => {
		const marker = item.status === "done" ? "✓" : item.status === "blocked" ? "!" : "○";
		return `${marker} ${index + 1}. ${item.text}${item.note ? ` — ${item.note}` : ""}`;
	});
}

function todoProgressLine(items: TodoItem[]): string {
	const doneCount = items.filter((item) => item.status === "done").length;
	return `Todo: ${doneCount}/${items.length}`;
}

function todoPromptContext(items: TodoItem[]): string {
	return [
		"Pi session todo workflow is available through pi_todo.",
		"Todos are session-local execution state. Use them for live checklists on ordinary tasks as well as plan execution; do not edit durable plan files to mark progress.",
		"For any task where you will use tools, inspect files, make edits, or perform multiple actions, use pi_todo so the user has visibility into what you are doing.",
		"Use pi_todo set before starting multi-step work, keep at most one item in_progress, update items promptly as work completes or blocks, and clear when the live checklist is no longer useful.",
		"Use durable plans for intended route changes; use todos for current execution progress.",
		"Current session todos:",
		todoSummary(items),
	].join("\n");
}

function looksMutatingBash(command: string): string | undefined {
	const stripped = command
		.split(/\r?\n/)
		.map((line) => line.replace(/#.*/, "").trim())
		.filter(Boolean)
		.join(" && ");
	const patterns: Array<[RegExp, string]> = [
		[/\b(rm|rmdir|mv|chmod|chown|mkdir|touch|truncate)\b/, "filesystem mutation"],
		[/\b(cp|rsync|scp)\b/, "file copy can mutate workspace"],
		[/\b(git\s+(add|commit|checkout|switch|reset|rebase|merge|cherry-pick|stash|clean|restore|apply|am|pull|push|worktree\s+add|worktree\s+remove))\b/, "git state mutation"],
		[/\b(npm|pnpm|yarn|bun)\s+(install|add|remove|update|upgrade|dedupe|link|unlink|audit\s+fix)\b/, "dependency mutation"],
		[/\b(pip|pip3|poetry|uv|cargo|go)\s+(install|add|remove|update|get|mod\s+tidy)\b/, "dependency mutation"],
		[/\b(npx|pnpm\s+dlx|yarn\s+dlx)\b/, "external command may mutate workspace"],
		[/\b(prettier|eslint|ruff|black|isort|gofmt|rustfmt)\b.*\b(--write|--fix|-w)\b/, "formatter/linter write mode"],
		[/(^|[^<])>\s*[^&]|>>|\btee\b/, "shell redirection writes files"],
	];
	for (const [pattern, reason] of patterns) {
		if (pattern.test(stripped)) return reason;
	}
	return undefined;
}

function latestPlanApproval(ctx: ExtensionContext): "select" | "approve" | "discuss" | undefined {
	for (const entry of [...ctx.sessionManager.getBranch()].reverse()) {
		if (entry.type !== "message") continue;
		const message = entry.message as any;
		if (message.role !== "toolResult") continue;
		if (message.toolName === "pi_plan_create") return undefined;
		if (message.toolName !== "question") continue;
		const details = message.details;
		if (details?.cancelled) return undefined;
		const labels = Array.isArray(details?.options) ? details.options.map((option: any) => option?.label) : [];
		if (labels.length !== APPROVAL_OPTIONS.length) return undefined;
		if (!APPROVAL_OPTIONS.every((label, index) => labels[index] === label)) return undefined;
		const value = String(details.value || details.answer || "");
		if (value === APPROVAL_OPTIONS[0]) return "select";
		if (value === APPROVAL_OPTIONS[1]) return "approve";
		if (value === APPROVAL_OPTIONS[2]) return "discuss";
		return undefined;
	}
	return undefined;
}

function planModePrompt(info: ProjectContextInfo): string {
	return `You are in Pi plan mode. You may inspect, search, and reason, but you must not create, edit, delete, move, format, generate, or otherwise mutate project files. The only write-like exception is Pi's internal project plan storage through pi_plan_* tools after explicit user approval.

Use plan mode to separate research from implementation:
1. Understand the user's goal and constraints.
2. Explore relevant files, commands, docs, and project patterns.
3. Identify the implementation path, risks, edge cases, and verification commands.
4. Present a concrete plan that the user can approve or revise.

Question tool rules:
- Use the question tool for multiple-choice clarification and approval gates. Do not write numbered options in normal chat and wait for a typed reply.
- Ask clarification questions only when the answer materially changes scope, approach, sequencing, risk, or verification.
- If no important ambiguity exists, say you found no blockers and proceed.
- Keep options concise and high-signal, usually 2-4 options plus an option to continue with assumptions when acceptable.

Plan content rules:
- Build a detailed, practical plan, not a checkbox checklist.
- Include: Goal, Context, Recommended approach, Phases, Risks/assumptions/open questions, Verification commands, Files inspected, and Files likely to change.
- Do not include checkbox-style progress tracking in the durable plan.
- Use pi_todo for live session execution tracking. Do not use plan files for checklist progress.

Final approval flow is mandatory before saving:
1. Present the final draft plan in chat.
2. Call question with exactly these three options and allowCustom=false:
   - ${APPROVAL_OPTIONS[0]}
   - ${APPROVAL_OPTIONS[1]}
   - ${APPROVAL_OPTIONS[2]}
3. Do not call pi_plan_create, pi_plan_current, or pi_plan_update until the user selects one of those options through question.
4. If "${APPROVAL_OPTIONS[0]}": call pi_plan_create with select=true and the full plan body, then say "Plan saved and selected."
5. If "${APPROVAL_OPTIONS[1]}": call pi_plan_create with select=false and the full plan body, then say "Plan saved as active but not selected."
6. If "${APPROVAL_OPTIONS[2]}": do not save; continue discussion and refine the draft.

If the user asks to resume, continue, execute, or archive a plan, use pi_plan_read first when a current or single active plan exists. If executing a plan, convert the plan phases into a concise pi_todo checklist before making changes.

${planWorkflowContext(info)}`;
}

export default function projectWorkspacesExtension(pi: ExtensionAPI) {
	let planModeEnabled = false;
	let toolsBeforePlanMode: string[] | undefined;
	let todoItems: TodoItem[] = [];

	function persistState(): void {
		pi.appendEntry("project-workspaces-plan-mode", {
			enabled: planModeEnabled,
			toolsBeforePlanMode,
		} satisfies PlanModeState);
	}

	function persistTodos(): void {
		pi.appendEntry("project-workspaces-todos", { items: todoItems, updatedAt: now() } satisfies TodoState);
	}

	function updateTodoWidget(ctx: ExtensionContext, _showWidget = false): void {
		const active = todoItems.filter((item) => item.status !== "done");
		ctx.ui.setWidget?.("todos", undefined);
		if (!todoItems.length) {
			ctx.ui.setStatus("todos", undefined);
			return;
		}
		ctx.ui.setStatus("todos", ctx.ui.theme.fg(active.length ? "accent" : "success", todoProgressLine(todoItems)));
	}

	function updateStatus(ctx: ExtensionContext): void {
		if (planModeEnabled) ctx.ui.setStatus("plan-mode", ctx.ui.theme.fg("warning", "plan"));
		else ctx.ui.setStatus("plan-mode", undefined);
		updateTodoWidget(ctx);
	}

	function setTodos(ctx: ExtensionContext, items: Array<{ text?: string; id?: string; status?: string; note?: string }>): void {
		const timestamp = now();
		todoItems = items.map((item, index) => ({
			id: item.id?.trim() || `todo-${index + 1}`,
			text: item.text?.trim() || "",
			status: normalizeTodoStatus(item.status),
			note: item.note?.trim() || undefined,
			createdAt: timestamp,
			updatedAt: timestamp,
		})).filter((item) => item.text.length > 0);
		persistTodos();
		updateTodoWidget(ctx, true);
	}

	function enablePlanMode(ctx: ExtensionContext): void {
		if (toolsBeforePlanMode === undefined) toolsBeforePlanMode = pi.getActiveTools();
		const allToolNames = pi.getAllTools().map((tool) => tool.name);
		pi.setActiveTools(getPlanModeTools(toolsBeforePlanMode, allToolNames));
		planModeEnabled = true;
		updateStatus(ctx);
		persistState();
	}

	function disablePlanMode(ctx: ExtensionContext): void {
		pi.setActiveTools(toolsBeforePlanMode ?? getNormalModeTools(pi.getActiveTools()));
		toolsBeforePlanMode = undefined;
		planModeEnabled = false;
		updateStatus(ctx);
		persistState();
	}

	pi.registerCommand("plan", {
		description: "Toggle Pi plan mode, or use /plan <task> to enable plan mode and ask the agent to draft a durable plan",
		handler: async (args, ctx) => {
			const raw = args.trim();
			const action = raw.toLowerCase();
			if (["off", "disable", "disabled", "exit"].includes(action)) {
				disablePlanMode(ctx);
				ctx.ui.notify("Plan mode disabled. Normal tools restored.", "info");
				return;
			}
			if (["on", "enable", "enabled"].includes(action) || !raw) {
				if (planModeEnabled && !raw) {
					disablePlanMode(ctx);
					ctx.ui.notify("Plan mode disabled. Normal tools restored.", "info");
					return;
				}
				enablePlanMode(ctx);
				ctx.ui.notify("Plan mode enabled. Repo write tools disabled; mutating bash is blocked.", "info");
				return;
			}
			enablePlanMode(ctx);
			ctx.ui.notify("Plan mode enabled. Starting planning request.", "info");
			pi.sendUserMessage(raw);
		},
	});

	async function showTodoModal(ctx: ExtensionContext): Promise<void> {
		updateTodoWidget(ctx, false);
		if (ctx.mode !== "tui") {
			ctx.ui.notify(todoSummary(todoItems), "info");
			return;
		}

		await ctx.ui.custom<void>((_tui, theme, keybindings, done) => ({
			render(width: number): string[] {
				const innerWidth = Math.max(12, width - 4);
				const border = theme.fg("accent", `╭${"─".repeat(innerWidth + 2)}╮`);
				const bottom = theme.fg("accent", `╰${"─".repeat(innerWidth + 2)}╯`);
				const empty = `${theme.fg("accent", "│")} ${" ".repeat(innerWidth)} ${theme.fg("accent", "│")}`;
				function row(content = ""): string {
					const clipped = truncateToWidth(content, innerWidth, "…");
					const padding = " ".repeat(Math.max(0, innerWidth - visibleWidth(clipped)));
					return `${theme.fg("accent", "│")} ${clipped}${padding} ${theme.fg("accent", "│")}`;
				}
				const lines = [border, row(theme.fg("accent", theme.bold("Todo"))), empty];
				if (!todoItems.length) {
					lines.push(row(theme.fg("muted", "No active todos.")));
				} else {
					lines.push(row(theme.fg("accent", todoProgressLine(todoItems))));
					lines.push(empty);
					for (const [index, item] of todoItems.entries()) {
						const text = todoDisplayLines([item])[0].replace(/^([✓!○]) 1\./, `$1 ${index + 1}.`);
						const color = item.status === "done" ? "success" : item.status === "blocked" || item.status === "in_progress" ? "warning" : "text";
						lines.push(row(theme.fg(color, text)));
					}
				}
				lines.push(empty, row(theme.fg("dim", "Esc/Enter close")), bottom);
				return lines;
			},
			invalidate() {},
			handleInput(data: string) {
				if (keybindings.matches(data, "tui.select.cancel") || keybindings.matches(data, "tui.select.confirm")) done();
			},
		}), { overlay: true, overlayOptions: { width: "70%", maxHeight: "80%" } });
	}

	pi.registerCommand("todo", {
		description: "Show the current session todo list",
		handler: async (_args, ctx) => showTodoModal(ctx),
	});

	pi.registerCommand("plans", {
		description: "List active Pi project plans",
		handler: async (args, ctx) => {
			const info = contextInfo(ctx.cwd);
			const status = ["active", "archive", "all"].includes(args.trim()) ? args.trim() : "active";
			ctx.ui.notify(formatPlanList(info, listPlans(info, status)), "info");
		},
	});

	pi.on("session_start", async (_event, ctx) => {
		const entries = ctx.sessionManager.getBranch?.() ?? ctx.sessionManager.getEntries();
		const stateEntry = entries
			.filter((entry: { type: string; customType?: string }) => entry.type === "custom" && entry.customType === "project-workspaces-plan-mode")
			.pop() as { data?: PlanModeState } | undefined;
		const todoEntry = entries
			.filter((entry: { type: string; customType?: string }) => entry.type === "custom" && entry.customType === "project-workspaces-todos")
			.pop() as { data?: TodoState } | undefined;
		if (stateEntry?.data) {
			planModeEnabled = Boolean(stateEntry.data.enabled);
			toolsBeforePlanMode = stateEntry.data.toolsBeforePlanMode;
		}
		if (todoEntry?.data?.items) todoItems = todoEntry.data.items.map((item) => ({ ...item, status: normalizeTodoStatus(item.status) }));
		const allToolNames = pi.getAllTools().map((tool) => tool.name);
		if (planModeEnabled) {
			pi.setActiveTools(getPlanModeTools(toolsBeforePlanMode ?? pi.getActiveTools(), allToolNames));
		} else if (allToolNames.includes("pi_todo") && !pi.getActiveTools().includes("pi_todo")) {
			pi.setActiveTools(unique([...pi.getActiveTools(), "pi_todo"]));
		}
		updateStatus(ctx);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const info = contextInfo(ctx.cwd);
		const todoContext = todoPromptContext(todoItems);
		if (planModeEnabled) return { systemPrompt: `${event.systemPrompt}\n\n${planModePrompt(info)}\n\n${todoContext}` };
		return { systemPrompt: `${event.systemPrompt}\n\n${planWorkflowContext(info)}\n\n${todoContext}` };
	});

	pi.on("tool_call", async (event) => {
		if (!planModeEnabled) return;
		if (PLAN_MODE_DISABLED_TOOLS.has(event.toolName)) {
			return { block: true, reason: `Plan mode: ${event.toolName} is disabled. Use /plan off after the plan is approved if you want to implement.` };
		}
		if (event.toolName === "bash") {
			const command = typeof event.input.command === "string" ? event.input.command : "";
			const reason = looksMutatingBash(command);
			if (reason) return { block: true, reason: `Plan mode: blocked mutating bash (${reason}). Command: ${command}` };
		}
	});

	pi.registerTool({
		name: "pi_todo",
		label: "Todo",
		description: "Manage the current Pi session's live todo checklist. Use for execution progress, not durable plan content.",
		promptSnippet: "Create and update a session-local todo checklist for multi-step execution.",
		promptGuidelines: [
			"Use pi_todo for live execution checklists when implementing a plan, handling a multi-step task, or doing tool-based investigation so the user can see what is happening.",
			"When finishing the current pi_todo item, decide what should come next and update both statuses in one pi_todo update call using items, for example mark one done and the chosen next item in_progress.",
			"Do not edit durable plan files to mark progress; use pi_todo for progress and pi_plan_update only for route/scope changes.",
			"Keep at most one pi_todo item in_progress at a time and update items promptly as work completes or blocks.",
		],
		parameters: Type.Object({
			action: Type.String({ description: "set, list, update, append, or clear" }),
			items: Type.Optional(Type.Array(Type.Object({
				id: Type.Optional(Type.String()),
				text: Type.Optional(Type.String()),
				status: Type.Optional(Type.String({ description: "pending, in_progress, done, or blocked" })),
				note: Type.Optional(Type.String()),
			}))),
			id: Type.Optional(Type.String({ description: "Todo id or 1-based item number for update" })),
			status: Type.Optional(Type.String({ description: "pending, in_progress, done, or blocked" })),
			text: Type.Optional(Type.String({ description: "Todo text for append or update" })),
			note: Type.Optional(Type.String()),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const action = params.action.trim().toLowerCase();
			if (action === "list") {
				updateTodoWidget(ctx, true);
				return textResult(todoSummary(todoItems), { items: todoItems });
			}
			if (action === "clear") {
				todoItems = [];
				persistTodos();
				updateTodoWidget(ctx, true);
				return textResult("Todos cleared.", { items: todoItems });
			}
			if (action === "set") {
				setTodos(ctx, params.items || []);
				return textResult(todoSummary(todoItems), { items: todoItems });
			}
			if (action === "append") {
				const itemText = params.text?.trim() || params.items?.[0]?.text?.trim();
				if (!itemText) return textResult("append requires text or items[0].text");
				const timestamp = now();
				const nextIndex = todoItems.length + 1;
				todoItems = [...todoItems, {
					id: params.id?.trim() || `todo-${nextIndex}`,
					text: itemText,
					status: normalizeTodoStatus(params.status),
					note: params.note?.trim() || undefined,
					createdAt: timestamp,
					updatedAt: timestamp,
				}];
				persistTodos();
				updateTodoWidget(ctx, true);
				return textResult(todoSummary(todoItems), { items: todoItems });
			}
			if (action === "update") {
				const updates = params.items?.length ? params.items : [{ id: params.id, text: params.text, status: params.status, note: params.note }];
				if (!updates.length || !updates.some((item) => item.id?.trim())) return textResult("update requires id or items with id");
				const timestamp = now();
				const changed: TodoItem[] = [];
				const missing: string[] = [];
				let nextItems = [...todoItems];
				for (const update of updates) {
					if (!update.id?.trim()) continue;
					const id = update.id.trim();
					const indexFromNumber = /^\d+$/.test(id) ? Number(id) - 1 : -1;
					const index = indexFromNumber >= 0 ? indexFromNumber : nextItems.findIndex((item) => item.id === id);
					if (index < 0 || index >= nextItems.length) {
						missing.push(id);
						continue;
					}
					const nextStatus = update.status ? normalizeTodoStatus(update.status) : nextItems[index].status;
					if (nextStatus === "in_progress") {
						nextItems = nextItems.map((item, itemIndex) => itemIndex !== index && item.status === "in_progress" ? { ...item, status: "pending", updatedAt: timestamp } : item);
					}
					const updated = {
						...nextItems[index],
						text: update.text?.trim() || nextItems[index].text,
						status: nextStatus,
						note: update.note !== undefined ? (update.note.trim() || undefined) : nextItems[index].note,
						updatedAt: timestamp,
					};
					nextItems[index] = updated;
					changed.push(updated);
				}
				if (missing.length) return textResult(`Todo not found: ${missing.join(", ")}`);
				todoItems = nextItems;
				persistTodos();
				updateTodoWidget(ctx, true);
				return textResult(todoSummary(todoItems), { items: todoItems, action: "update", changed });
			}
			return textResult("Invalid pi_todo action. Use set, list, update, append, or clear.");
		},
		renderCall() {
			return new Text("", 0, 0);
		},
		renderResult(result, _options, theme) {
			const details = result.details as any;
			const items = Array.isArray(details?.items) ? details.items as TodoItem[] : undefined;
			if (!items) return new Text(result.content?.[0]?.text || "", 0, 0, (text) => theme.bg("toolSuccessBg", text));
			if (!items.length) return new Text(theme.fg("muted", "Todo: 0/0\nNo active todos."), 0, 0, (text) => theme.bg("toolSuccessBg", text));
			const doneCount = items.filter((item) => item.status === "done").length;
			const lines = [theme.fg("accent", todoProgressLine(items))];
			if (details.action === "update") {
				lines[0] = theme.fg(doneCount === items.length ? "success" : "accent", `${doneCount === items.length ? "Todo complete" : "Todo updated"}: ${doneCount}/${items.length}`);
				for (const [index, item] of items.entries()) {
					const line = todoDisplayLines([item])[0].replace(/^([✓!○]) 1\./, `$1 ${index + 1}.`);
					if (item.status === "done") lines.push(theme.fg("success", line));
					else if (item.status === "blocked" || item.status === "in_progress") lines.push(theme.fg("warning", line));
					else lines.push(theme.fg("muted", line));
				}
				return new Text(lines.join("\n"), 0, 0, (text) => theme.bg("toolSuccessBg", text));
			}
			for (const [index, item] of items.entries()) {
				const line = todoDisplayLines([item])[0].replace(/^([✓!○]) 1\./, `$1 ${index + 1}.`);
				if (item.status === "done") lines.push(theme.fg("success", line));
				else if (item.status === "blocked" || item.status === "in_progress") lines.push(theme.fg("warning", line));
				else lines.push(theme.fg("muted", line));
			}
			return new Text(lines.join("\n"), 0, 0, (text) => theme.bg("toolSuccessBg", text));
		},
	});

	pi.registerTool({
		name: "pi_plan_create",
		label: "Plan Create",
		description: "Create a durable active Pi project plan after the final question approval flow. This tool verifies the latest approval question result; the select parameter is accepted for compatibility but the recorded user answer is authoritative.",
		promptSnippet: "Create a durable project plan after explicit approval.",
		promptGuidelines: [
			"Use pi_plan_create only after asking the final approval question with exactly: Approve and select, Approve, Discuss further.",
			"Do not use pi_plan_create when the user selected Discuss further.",
		],
		parameters: Type.Object({
			title: Type.String({ description: "Short human-readable plan title" }),
			body: Type.String({ description: "Full detailed markdown plan body" }),
			select: Type.Optional(Type.Boolean({ description: "Deprecated compatibility hint. Actual selection is determined from the latest approval question result." })),
			task: Type.Optional(Type.String()),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const approval = latestPlanApproval(ctx);
			if (!approval) return textResult("Refusing to create plan: ask the final approval question first with exactly Approve and select, Approve, Discuss further.");
			if (approval === "discuss") return textResult("Refusing to create plan: user selected Discuss further.");
			const shouldSelect = approval === "select";
			const info = contextInfo(ctx.cwd);
			const plan = createPlan(info, params);
			if (shouldSelect) setCurrentPlan(info, plan.id);
			return textResult(
				[
					shouldSelect ? "Plan saved and selected." : "Plan saved as active but not selected.",
					`Plan: ${plan.title} (${plan.id})`,
					`Path: ${plan.path}`,
				].join("\n"),
				{ plan, selected: shouldSelect },
			);
		},
		renderResult(result, _options, theme) {
			return new Text(theme.fg("success", result.content?.[0]?.text || "Plan saved"), 0, 0);
		},
	});

	pi.registerTool({
		name: "pi_plan_list",
		label: "Plan List",
		description: "List durable Pi project plans for the current project.",
		parameters: Type.Object({ status: Type.Optional(Type.String({ description: "active, archive, or all" })) }),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = contextInfo(ctx.cwd);
			const status = ["active", "archive", "all"].includes(params.status || "") ? params.status! : "active";
			const plans = listPlans(info, status);
			return textResult(formatPlanList(info, plans), { plans, status });
		},
	});

	pi.registerTool({
		name: "pi_plan_current",
		label: "Plan Current",
		description: "Show, set, or clear the current plan pointer for the current Pi project.",
		parameters: Type.Object({
			action: Type.Optional(Type.String({ description: "show, set, or clear" })),
			id: Type.Optional(Type.String({ description: "Plan id/path/title for action=set" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = contextInfo(ctx.cwd);
			const action = (params.action || "show").trim().toLowerCase();
			if (action === "clear") {
				clearCurrentPlanRef(info);
				return textResult("Current plan pointer cleared.");
			}
			if (action === "set") {
				if (!params.id) return textResult("action=set requires id");
				const plan = setCurrentPlan(info, params.id);
				return textResult(`Current plan set to ${plan.title} (${plan.id})\nPath: ${plan.path}`, { plan });
			}
			const current = resolveCurrentPlan(info, "all");
			if (!current) return textResult("No current plan is set.");
			return textResult([`Path: ${current.path}`, "", current.content].join("\n"), { plan: current });
		},
	});

	pi.registerTool({
		name: "pi_plan_read",
		label: "Plan Read",
		description: "Read a durable Pi project plan.",
		parameters: Type.Object({
			id: Type.Optional(Type.String({ description: "Plan id/path/title. If omitted, current or single active plan is used." })),
			status: Type.Optional(Type.String({ description: "active, archive, or all" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			try {
				const info = contextInfo(ctx.cwd);
				const status = ["active", "archive", "all"].includes(params.status || "") ? params.status! : "active";
				const plan = params.id ? resolvePlan(info, params.id, status) : (resolveCurrentPlan(info, status) || resolvePlan(info, undefined, status));
				return textResult([`Path: ${plan.path}`, "", plan.content].join("\n"), { plan });
			} catch (error) {
				return textResult(`❌ ${error instanceof Error ? error.message : String(error)}`);
			}
		},
	});

	pi.registerTool({
		name: "pi_plan_update",
		label: "Plan Update",
		description: "Update an active durable Pi project plan only when intended approach/scope/risks/completion criteria change. Do not use for checklist progress.",
		parameters: Type.Object({
			id: Type.Optional(Type.String()),
			title: Type.Optional(Type.String()),
			body: Type.String(),
			reason: Type.Optional(Type.String()),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = contextInfo(ctx.cwd);
			const plan = updatePlan(info, params);
			return textResult(`Updated active plan: ${plan.title} (${plan.id})\nPath: ${plan.path}`, { plan });
		},
	});

	pi.registerTool({
		name: "pi_plan_archive",
		label: "Plan Archive",
		description: "Archive a completed active Pi project plan.",
		parameters: Type.Object({ id: Type.Optional(Type.String()), result: Type.Optional(Type.String()) }),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const info = contextInfo(ctx.cwd);
			const plan = archivePlan(info, params);
			return textResult(`Archived plan: ${plan.title} (${plan.id})\nPath: ${plan.path}`, { plan });
		},
	});
}
