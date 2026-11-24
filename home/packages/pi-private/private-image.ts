import { spawn, type ChildProcess } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { BorderedLoader } from "@earendil-works/pi-coding-agent";
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
				const child = spawn("@python@", ["@imageHelper@"], { stdio: ["pipe", "pipe", "ignore"] });
				active = child;
				let output = "";
				let oversized = false;
				const cancel = () => { child.kill("SIGTERM"); };
				loader.signal.addEventListener("abort", cancel, { once: true });
				// Give Python time to terminate/reap its model server before returning.
				const timer = setTimeout(cancel, preset === "quality" ? 740000 : 380000);
				child.stdout!.setEncoding("utf8");
				child.stdout!.on("data", (data: string) => {
					if (output.length + data.length > 25000) { oversized = true; cancel(); }
					else output += data;
				});
				child.stdin!.on("error", () => {});
				child.stdin!.end(JSON.stringify({ prompt, preset }));
				completion = new Promise<void>((resolve) => {
					const finish = (code: number | null) => {
						clearTimeout(timer);
						loader.signal.removeEventListener("abort", cancel);
						active = undefined;
						let image: PrivateImage | null = null;
						if (code === 0 && !loader.signal.aborted && !oversized && !closing) {
							try { const parsed = JSON.parse(output); if (validImage(parsed) && parsed.preset === preset) image = parsed; } catch {}
						}
						done(image);
						resolve();
					};
					child.once("error", () => { /* close always follows error */ });
					child.once("close", finish);
				});
				return loader;
			});
			if (closing) return;
			if (!result) {
				ctx.ui.notify("Image cancelled or unavailable. Nothing was sent to a cloud service.", "info");
				return;
			}
			pi.sendMessage({ customType: "private-image", display: true, details: result,
				content: `Private image · ${result.preset} · ${result.width}×${result.height} · ${result.seconds}s\n${prompt}\nSaved: ~/.local/state/pi-private/images/${result.filename}` },
				{ triggerTurn: false });
		},
	});
}
