import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const ASCII_LOGO = [
	"██████╗ ██╗",
	"██╔══██╗██║",
	"██████╔╝██║",
	"██╔═══╝ ██║",
	"██║     ██║",
	"╚═╝     ╚═╝",
];

export default function piAsciiHeader(pi: ExtensionAPI): void {
	function installHeader(ctx: ExtensionContext): void {
		if (ctx.mode !== "tui") return;

		ctx.ui.setHeader((_tui, theme) => ({
			invalidate() {},
			render(width: number): string[] {
				const logoLines = ASCII_LOGO.map((line, index) => {
					const logo = theme.bold(theme.fg("accent", line));
					if (index !== 2 || width < 42) return logo;

					return logo + theme.fg("text", "  pi") + theme.fg("dim", "  minimal terminal coding harness");
				});

				const help =
					width >= 74
						? [
								theme.fg("accent", "Esc") + theme.fg("dim", " interrupt"),
								theme.fg("accent", "Ctrl+C") + theme.fg("dim", " clear/exit"),
								theme.fg("accent", "/") + theme.fg("dim", " commands"),
								theme.fg("accent", "!") + theme.fg("dim", " bash"),
								theme.fg("accent", "Ctrl+O") + theme.fg("dim", " more"),
								theme.fg("accent", "/hotkeys") + theme.fg("dim", " all keys"),
							].join(theme.fg("muted", " · "))
						: theme.fg("accent", "/hotkeys") + theme.fg("dim", " for shortcuts") + theme.fg("muted", " · ") + theme.fg("accent", "/") + theme.fg("dim", " commands");

				const onboarding =
					width >= 74
						? theme.fg("dim", "Loaded context, skills, prompts, extensions, and themes are shown below as usual.")
						: theme.fg("dim", "Loaded resources are shown below as usual.");

				return ["", ...logoLines, "", help, onboarding];
			},
		}));
	}

	pi.on("session_start", async (_event, ctx) => {
		installHeader(ctx);
	});
}
