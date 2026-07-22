import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { ProjectContextInfo } from "./store.ts";

export const WORKLOG_VERSION = 1;
export const WORKLOG_ENTRY_TYPES = ["start", "progress", "decision", "mistake", "stuck", "finish", "next", "note"] as const;
export type WorklogEntryType = typeof WORKLOG_ENTRY_TYPES[number];
export const ALLOWED_WORKLOG_TYPES = new Set<string>(WORKLOG_ENTRY_TYPES);

const RECAP_ENTRY_COUNT = 12;

export interface WorklogEntry {
	v: number;
	time: string;
	session: string;
	project: string;
	root: string;
	scope: "project" | "stream";
	stream?: { id: string; name?: string };
	type: WorklogEntryType;
	summary: string;
	task?: string;
	next?: string;
	reason?: string;
	lesson?: string;
	blocker?: string;
	result?: string;
	plan?: string;
	projectImpact?: true;
	files?: string[];
	source?: Record<string, unknown>;
}

export interface WorklogContextInfo extends ProjectContextInfo {
	log: string;
}

export function worklogPath(info: ProjectContextInfo): string {
	return path.join(info.dir, "worklog.jsonl");
}

export function withWorklogPath<T extends ProjectContextInfo>(info: T): T & { log: string } {
	return { ...info, log: worklogPath(info) };
}

function projectLabel(info: ProjectContextInfo): string {
	return info.project?.name || info.project?.id || info.id.replace(/--[a-f0-9]+$/i, "") || path.basename(info.root) || info.id;
}

export function ensureWorklog<T extends ProjectContextInfo>(info: T): T & { log: string } {
	const withLog = withWorklogPath(info);
	mkdirSync(withLog.dir, { recursive: true });
	if (!existsSync(withLog.log)) {
		const first = {
			v: WORKLOG_VERSION,
			time: new Date().toISOString(),
			type: "note",
			summary: `Created worklog file for this ${withLog.scope}.`,
			next: "Append the first start/progress/decision entry when meaningful work begins.",
			project: withLog.project?.id || withLog.id,
			root: withLog.root,
			scope: withLog.scope,
			stream: withLog.stream ? { id: withLog.stream.id, name: withLog.stream.name } : undefined,
		};
		writeFileSync(withLog.log, `${JSON.stringify(first)}\n`, "utf8");
	}
	return withLog;
}

export function parseEntries(text: string): any[] {
	return text
		.split(/\r?\n/)
		.filter(Boolean)
		.map((line) => {
			try {
				return JSON.parse(line);
			} catch {
				return null;
			}
		})
		.filter(Boolean);
}

export function readAllEntries(file: string): any[] {
	if (!existsSync(file)) return [];
	return parseEntries(readFileSync(file, "utf8"));
}

export function appendWorklogEntry(info: ProjectContextInfo, entry: WorklogEntry): void {
	const withLog = ensureWorklog(info);
	appendFileSync(withLog.log, `${JSON.stringify(entry)}\n`, "utf8");
}

export function validateWorklogEntry(input: { type?: string; reason?: string; lesson?: string; blocker?: string; summary?: string }): string | undefined {
	const type = input.type?.trim().toLowerCase();
	if (!type || !ALLOWED_WORKLOG_TYPES.has(type)) return `Invalid worklog type: ${input.type || "missing"}`;
	if (!input.summary?.trim()) return "Worklog summary is required.";
	if (type === "decision" && !input.reason?.trim()) return "decision entries require reason.";
	if (type === "mistake" && !input.lesson?.trim()) return "mistake entries require lesson.";
	if (type === "stuck" && !input.blocker?.trim()) return "stuck entries require blocker.";
	return undefined;
}

function compactEntry(entry: any): string {
	const bits = [`- ${entry.type || "note"}: ${entry.summary || entry.next || entry.result || "update recorded"}`];
	if (entry.task) bits.push(`task=${entry.task}`);
	if (entry.next) bits.push(`next=${entry.next}`);
	if (entry.result) bits.push(`result=${entry.result}`);
	if (entry.blocker) bits.push(`blocker=${entry.blocker}`);
	if (entry.reason) bits.push(`reason=${entry.reason}`);
	if (entry.lesson) bits.push(`lesson=${entry.lesson}`);
	return bits.join(" | ");
}

export function latestSummary(info: ProjectContextInfo): string {
	const withLog = ensureWorklog(info);
	const latest = readAllEntries(withLog.log).at(-1);
	if (!latest) return "No recent worklog summary.";
	return latest.summary || latest.next || latest.result || `${latest.type || "note"} update recorded`;
}

export function worklogRecap(info: ProjectContextInfo, limit = RECAP_ENTRY_COUNT): string {
	const withLog = ensureWorklog(info);
	const entries = readAllEntries(withLog.log);
	const entryLimit = Math.max(1, Math.min(50, Math.floor(Number(limit) || RECAP_ENTRY_COUNT)));
	const recent = entries.slice(-entryLimit);
	const latest = entries.at(-1);
	return [
		`Worklog recap for this ${withLog.scope}.`,
		`Worklog file: ${withLog.log}`,
		`Project: ${projectLabel(withLog)}`,
		withLog.stream ? `Stream: ${withLog.stream.name || withLog.stream.id}` : undefined,
		latest ? `Latest status: ${latest.summary || latest.next || latest.result || "update recorded"}` : "Latest status: none yet",
		"Recent worklog entries:",
		recent.length ? recent.map(compactEntry).join("\n") : "- none yet",
		"Use this recap to orient yourself. Do not dump the raw entries into the user-visible response.",
		"If deeper history is needed later, read the worklog file above only when appropriate.",
	].filter(Boolean).join("\n");
}

export function worklogReminder(info: ProjectContextInfo): string {
	const withLog = ensureWorklog(info);
	const project = projectLabel(withLog);
	if (withLog.scope === "stream" && withLog.stream) {
		return [
			`Worklog tracking is enabled for selected stream: ${project} / ${withLog.stream.name || withLog.stream.id}.`,
			`Use this selected stream worklog as the default continuity source: ${withLog.log}.`,
			"Do not read sibling stream worklogs, the parent project worklog, or other project worklogs by default.",
			"If the user explicitly asks for another stream, parent project history, project-wide history, another project, or another session's worklog, you may read those worklog files using normal tools.",
			"For orientation, resume, continue, or current-state questions, call worklog_recap to fetch recent entries on demand instead of assuming full history is already in context.",
			"For meaningful progress, decisions, blockers, mistakes, finishes, or next steps, append a concise entry with worklog_append; it writes to the selected stream.",
			"Stream start, finish, and mistake entries automatically roll up to the parent project log.",
			"Set projectImpact=true when a stream entry affects project-level direction, architecture, release state, workflow, or future agents and should be visible in project memory.",
			"Decision entries require reason, mistake entries require lesson, and stuck entries require blocker.",
		].join(" ");
	}
	return [
		`Worklog tracking is enabled for project: ${project}.`,
		`Use this project worklog as the default continuity source: ${withLog.log}.`,
		"Do not read stream worklogs or other project worklogs by default from project scope.",
		"If the user explicitly asks for stream-specific history, another project, or another session's worklog, you may read those worklog files using normal tools.",
		"For orientation, resume, continue, or current-state questions, call worklog_recap to fetch recent entries on demand instead of assuming full history is already in context.",
		"For meaningful progress, decisions, blockers, mistakes, finishes, or next steps, append a concise entry with worklog_append.",
	].join(" ");
}
