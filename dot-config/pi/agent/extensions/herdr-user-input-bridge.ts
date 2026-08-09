import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const WRAPPED = Symbol.for("sumeet.pi.herdrUserInputBridge.wrapped");

type UiLike = {
	confirm?: (...args: any[]) => Promise<any>;
	select?: (...args: any[]) => Promise<any>;
	input?: (...args: any[]) => Promise<any>;
	editor?: (...args: any[]) => Promise<any>;
	custom?: (...args: any[]) => Promise<any>;
	[WRAPPED]?: boolean;
};

function oneLine(value: unknown): string | undefined {
	if (typeof value !== "string") return undefined;
	const text = value.replace(/\s+/g, " ").trim();
	return text || undefined;
}

function blockedLabel(kind: string, args: any[]): string {
	const title = oneLine(args[0]);
	const detail = oneLine(args[1]);
	const base = title ? `${kind}: ${title}` : `Waiting for Pi ${kind.toLowerCase()} input`;
	return (detail ? `${base} — ${detail}` : base).slice(0, 160);
}

async function withBlocked<T>(pi: ExtensionAPI, label: string, run: () => Promise<T>): Promise<T> {
	pi.events.emit("herdr:blocked", {
		active: true,
		label,
		reason: "awaiting_user_input",
		needsUser: true,
	});
	try {
		return await run();
	} finally {
		pi.events.emit("herdr:blocked", {
			active: false,
			reason: "awaiting_user_input",
			needsUser: false,
		});
	}
}

function wrapAsyncMethod<K extends keyof UiLike>(pi: ExtensionAPI, ui: UiLike, key: K, kind: string): void {
	const original = ui[key];
	if (typeof original !== "function") return;

	(ui as any)[key] = function wrappedUserInputMethod(this: unknown, ...args: any[]) {
		const label = blockedLabel(kind, args);
		return withBlocked(pi, label, () => original.apply(this, args));
	};
}

function wrapUi(pi: ExtensionAPI, ctx: { ui?: UiLike } | undefined): void {
	const ui = ctx?.ui;
	if (!ui || ui[WRAPPED]) return;

	try {
		wrapAsyncMethod(pi, ui, "confirm", "Confirm");
		wrapAsyncMethod(pi, ui, "select", "Select");
		wrapAsyncMethod(pi, ui, "input", "Input");
		wrapAsyncMethod(pi, ui, "editor", "Editor");
		wrapAsyncMethod(pi, ui, "custom", "Interactive prompt");
		ui[WRAPPED] = true;
	} catch {
		// Best-effort bridge only. If a future Pi UI object is immutable, do not break the session.
	}
}

export default function herdrUserInputBridge(pi: ExtensionAPI) {
	const install = (_event: unknown, ctx: any) => wrapUi(pi, ctx);

	pi.on("project_trust", (_event, ctx) => {
		wrapUi(pi, ctx);
		return { trusted: "undecided" as const };
	});
	pi.on("session_start", install);
	pi.on("tool_call", install);
	pi.on("input", install);
	pi.on("session_before_switch", install);
	pi.on("session_before_fork", install);
	pi.on("session_before_tree", install);
	pi.on("session_before_compact", install);
}
