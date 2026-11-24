import { spawn, type ChildProcess } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { BorderedLoader, defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "@earendil-works/pi-ai";
import { Container, Text } from "@earendil-works/pi-tui";

export type ImagePreset = "fast" | "quality";

export function parseImageArgs(args: string): { prompt: string; preset: ImagePreset } {
	let prompt = args.trim();
	let preset: ImagePreset = "quality";
	const flag = /^--(fast|quality)(?:\s+|$)/.exec(prompt);
	if (flag) {
		preset = flag[1] as ImagePreset;
		prompt = prompt.slice(flag[0].length).trim();
	}
	if (!prompt || prompt.length > 4000 || prompt.startsWith("--")) {
		throw new Error("Usage: /image [--quality|--fast] <description, up to 4000 characters>");
	}
	return { prompt, preset };
}

export interface PrivateImage {
	filename: string;
	preset?: ImagePreset;
	width: number;
	height: number;
	preview: string;
	seconds: number;
}

export function validImage(value: unknown): value is PrivateImage {
	if (!value || typeof value !== "object") return false;
	const image = value as PrivateImage;
	return typeof image.filename === "string" && /^[a-f0-9]{32}\.png$/.test(image.filename)
		&& (((image.preset === undefined || image.preset === "fast") && image.width === 512 && image.height === 512)
			|| (image.preset === "quality" && image.width === 1024 && image.height === 1024))
		&& typeof image.preview === "string" && /^[A-Za-z0-9+/]{16384}$/.test(image.preview)
		&& Number.isFinite(image.seconds) && image.seconds >= 0;
}

// A pixel-only, width-aware preview: no terminal image protocols, arbitrary
// escapes, file reads, browser launch, hyperlinks, clipboard or external viewer.
export class PixelPreview {
	private pixels: Buffer;
	constructor(image: PrivateImage) {
		if (!validImage(image)) throw new Error("Invalid private image preview");
		this.pixels = Buffer.from(image.preview, "base64");
	}
	invalidate() {}
	render(width: number): string[] {
		const columns = Math.max(1, Math.min(64, Math.floor(width)));
		const rows = Math.ceil(columns / 2);
		const lines: string[] = [];
		for (let y = 0; y < rows; y++) {
			let line = "";
			for (let x = 0; x < columns; x++) {
				const sx = Math.min(63, Math.floor(x * 64 / columns));
				const top = (Math.min(63, Math.floor(y * 2 * 64 / columns)) * 64 + sx) * 3;
				const bottom = (Math.min(63, Math.floor((y * 2 + 1) * 64 / columns)) * 64 + sx) * 3;
				line += `\x1b[38;2;${this.pixels[top]};${this.pixels[top + 1]};${this.pixels[top + 2]};48;2;${this.pixels[bottom]};${this.pixels[bottom + 1]};${this.pixels[bottom + 2]}m▀`;
			}
			lines.push(line + "\x1b[0m");
		}
		return lines;
	}
}

export default function (pi: ExtensionAPI) {
	let active: ChildProcess | undefined;
	let completion: Promise<void> | undefined;
	let closing = false;
	let requestedThisTurn = false;
	pi.on("before_agent_start", () => { requestedThisTurn = false; });
	pi.on("tool_call", (event) => {
		if (event.toolName !== "generate_image") return;
		if (requestedThisTurn || active || closing) {
			return { block: true, reason: "Only one private image request is allowed per run; no automatic retries.", terminate: true };
		}
		requestedThisTurn = true;
	});

	function runImage(prompt: string, preset: ImagePreset, signal?: AbortSignal): Promise<PrivateImage | null> {
		if (active || closing || signal?.aborted) return Promise.resolve(null);
		const request = new Promise<PrivateImage | null>((resolve) => {
			const child = spawn("@python@", ["@imageHelper@"], { stdio: ["pipe", "pipe", "ignore"] });
			active = child;
			let output = "";
			let oversized = false;
			const cancel = () => { child.kill("SIGTERM"); };
			signal?.addEventListener("abort", cancel, { once: true });
			const timer = setTimeout(cancel, preset === "quality" ? 740000 : 380000);
			child.stdout!.setEncoding("utf8");
			child.stdout!.on("data", (data: string) => {
				if (output.length + data.length > 25000) { oversized = true; cancel(); }
				else output += data;
			});
			child.stdin!.on("error", () => {});
			child.stdin!.end(JSON.stringify({ prompt, preset }));
			child.once("error", () => { /* close always follows error */ });
			child.once("close", (code) => {
				clearTimeout(timer);
				signal?.removeEventListener("abort", cancel);
				active = undefined;
				let image: PrivateImage | null = null;
				if (code === 0 && !signal?.aborted && !oversized && !closing) {
					try { const parsed = JSON.parse(output); if (validImage(parsed) && parsed.preset === preset) image = parsed; } catch {}
				}
				resolve(image);
			});
		});
		completion = request.then(() => {}, () => {});
		return request;
	}

	function caption(image: PrivateImage, prompt: string): string {
		return `Private image · ${image.preset} · ${image.width}×${image.height} · ${image.seconds}s\n${prompt}\nSaved: ~/.local/state/pi-private/images/${image.filename}`;
	}

	pi.on("session_shutdown", async () => {
		closing = true;
		active?.kill("SIGTERM");
		await completion;
	});
	pi.registerMessageRenderer<PrivateImage>("private-image", (message) => {
		const box = new Container();
		if (validImage(message.details)) box.addChild(new PixelPreview(message.details));
		box.addChild(new Text(typeof message.content === "string" ? message.content : "Private image", 0, 1));
		return box;
	});
	pi.registerTool(defineTool({
		name: "generate_image",
		label: "Generate private image",
		description: "Generate one image locally on the GPU, only when the user explicitly asks for an image. Use quality by default, or fast when the user requests speed. No uploads, external network, file reading or image analysis. Do not automatically retry.",
		parameters: Type.Object({
			prompt: Type.String({ minLength: 1, maxLength: 4000, description: "The image description requested by the user" }),
			preset: Type.Optional(Type.Union([Type.Literal("quality"), Type.Literal("fast")])),
		}, { additionalProperties: false }),
		executionMode: "sequential",
		async execute(_id, params, signal) {
			if (active || closing) throw new Error("Wait for the active private image request to finish.");
			const prompt = params.prompt.trim();
			const preset = params.preset ?? "quality";
			if (!prompt || prompt.length > 4000 || (preset !== "quality" && preset !== "fast")) {
				throw new Error("An image description and a supported named preset are required.");
			}
			const image = await runImage(prompt, preset, signal);
			if (!image) throw new Error("Private image cancelled or unavailable. Nothing was sent to a cloud service.");
			return { content: [{ type: "text", text: caption(image, prompt) }], details: image, terminate: true };
		},
		renderCall(args) {
			return new Text(`Generating private image · ${args?.preset === "fast" ? "fast" : "quality (allow several minutes)"} · GPU`, 0, 0);
		},
		renderResult(result) {
			const box = new Container();
			if (validImage(result.details)) box.addChild(new PixelPreview(result.details));
			const text = result.content.filter((part) => part.type === "text").map((part) => part.text).join("\n");
			box.addChild(new Text(text, 0, 1));
			return box;
		},
	}));
	pi.registerCommand("image", {
		description: "Generate a private image (quality default): /image [--fast|--quality] <description>",
		handler: async (args, ctx) => {
			if (ctx.mode !== "tui" || !ctx.hasUI) return;
			let prompt: string;
			let preset: ImagePreset;
			try { ({ prompt, preset } = parseImageArgs(args)); }
			catch {
				ctx.ui.notify("Usage: /image [--quality|--fast] <description, up to 4000 characters>", "warning");
				return;
			}
			if (active || closing || !ctx.isIdle()) {
				ctx.ui.notify("Wait for the current response or image to finish.", "warning");
				return;
			}
			const result = await ctx.ui.custom<PrivateImage | null>((tui, theme, _kb, done) => {
				const settings = preset === "quality" ? "quality: 1024×1024, 35 steps" : "fast: 512×512, 20 steps";
				const loader = new BorderedLoader(tui, theme, `Generating private local image (${settings})…`);
				runImage(prompt, preset, loader.signal).then(done).catch(() => done(null));
				return loader;
			});
			if (closing) return;
			if (!result) {
				ctx.ui.notify("Image cancelled or unavailable. Nothing was sent to a cloud service.", "info");
				return;
			}
			pi.sendMessage({ customType: "private-image", display: true, details: result,
				content: caption(result, prompt) },
				{ triggerTurn: false });
		},
	});
}
