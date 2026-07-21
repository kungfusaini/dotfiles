/**
 * Question Tool
 *
 * A deterministic multiple-choice question tool for Pi agents.
 * Intended for plan-mode clarification and approval gates.
 *
 * Design notes:
 * - Includes a "Type custom answer" option by default. Set allowCustom=false only
 *   for strict approval gates where free text would be invalid.
 * - Supports number-key selection in addition to arrow/enter selection.
 * - Returns the selected label/value/index in details for durable session replay.
 * - Uses sequential execution so questions do not race with other tool calls.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Editor, type EditorTheme, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { Type } from "typebox";

interface QuestionOption {
	label: string;
	value?: string;
	description?: string;
}

type DisplayOption = QuestionOption & { isCustom?: boolean };

interface QuestionDetails {
	question: string;
	options: QuestionOption[];
	answer: string | null;
	value: string | null;
	index: number | null;
	wasCustom: boolean;
	cancelled: boolean;
}

const OptionSchema = Type.Object({
	label: Type.String({ description: "Display label for this option" }),
	value: Type.Optional(Type.String({ description: "Optional machine-readable value. Defaults to label." })),
	description: Type.Optional(Type.String({ description: "Optional secondary text shown under the option" })),
});

const QuestionParams = Type.Object({
	question: Type.String({ description: "The question to ask the user" }),
	options: Type.Array(OptionSchema, { description: "Multiple-choice options. Keep these concise and high-signal." }),
	allowCustom: Type.Optional(Type.Boolean({ description: "If false, hide the default 'Type custom answer' option." })),
});

function normalizeOptions(options: QuestionOption[]): QuestionOption[] {
	return options
		.map((option) => ({
			label: String(option.label || "").trim(),
			value: typeof option.value === "string" && option.value.trim() ? option.value.trim() : undefined,
			description:
				typeof option.description === "string" && option.description.trim() ? option.description.trim() : undefined,
		}))
		.filter((option) => option.label.length > 0);
}

function textFromContent(result: { content?: Array<{ type: string; text?: string }> }): string {
	const first = result.content?.[0];
	return first?.type === "text" ? first.text || "" : "";
}

export default function questionExtension(pi: ExtensionAPI) {
	pi.registerTool({
		name: "question",
		label: "Question",
		description:
			"Ask the user a deterministic multiple-choice question and return the selected option. Use this for plan-mode ambiguity resolution and approval gates.",
		promptSnippet: "Ask the user to choose from explicit multiple-choice options.",
		promptGuidelines: [
			"Use question for multiple-choice clarification or approval instead of writing numbered options in chat and waiting for a typed reply.",
			"When using question, include only options whose answers materially affect the plan, implementation, sequencing, risk, or verification.",
		],
		parameters: QuestionParams,
		executionMode: "sequential",

		prepareArguments(args) {
			if (!args || typeof args !== "object") return args;
			const input = args as { options?: unknown[] };
			if (!Array.isArray(input.options)) return args;

			// Compatibility/convenience: allow older or hand-written calls with string[] options.
			return {
				...args,
				options: input.options.map((option) => {
					if (typeof option === "string") return { label: option };
					return option;
				}),
			};
		},

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const options = normalizeOptions(params.options);

			if (options.length === 0) {
				return {
					content: [{ type: "text", text: "Error: question requires at least one non-empty option." }],
					details: {
						question: params.question,
						options: [],
						answer: null,
						value: null,
						index: null,
						wasCustom: false,
						cancelled: true,
					} satisfies QuestionDetails,
				};
			}

			if (ctx.mode !== "tui") {
				return {
					content: [{ type: "text", text: "Error: question requires Pi TUI interactive mode." }],
					details: {
						question: params.question,
						options,
						answer: null,
						value: null,
						index: null,
						wasCustom: false,
						cancelled: true,
					} satisfies QuestionDetails,
				};
			}

			const displayOptions: DisplayOption[] = params.allowCustom === false
				? options
				: [...options, { label: "Type custom answer", value: "__custom__", isCustom: true }];

			const result = await ctx.ui.custom<{
				answer: string;
				value: string;
				index: number | null;
				wasCustom: boolean;
			} | null>((tui, theme, keybindings, done) => {
				let selectedIndex = 0;
				let inputMode = false;
				let cachedLines: string[] | undefined;

				const editorTheme: EditorTheme = {
					borderColor: (s: string) => theme.fg("accent", s),
					selectList: {
						selectedPrefix: (s: string) => theme.fg("accent", s),
						selectedText: (s: string) => theme.fg("accent", s),
						description: (s: string) => theme.fg("muted", s),
						scrollInfo: (s: string) => theme.fg("dim", s),
						noMatch: (s: string) => theme.fg("warning", s),
					},
				};
				const editor = new Editor(tui, editorTheme);

				function refresh(): void {
					cachedLines = undefined;
					tui.requestRender();
				}

				editor.onSubmit = (value) => {
					const trimmed = value.trim();
					if (!trimmed) {
						inputMode = false;
						editor.setText("");
						refresh();
						return;
					}
					done({ answer: trimmed, value: trimmed, index: null, wasCustom: true });
				};

				function selectCurrent(): void {
					const selected = displayOptions[selectedIndex];
					if (!selected) return;
					if (selected.isCustom) {
						inputMode = true;
						refresh();
						return;
					}
					done({
						answer: selected.label,
						value: selected.value || selected.label,
						index: selectedIndex + 1,
						wasCustom: false,
					});
				}

				function selectByNumberKey(data: string): boolean {
					if (!/^\d$/.test(data)) return false;
					const optionNumber = data === "0" ? 10 : Number(data);
					if (!Number.isInteger(optionNumber) || optionNumber < 1 || optionNumber > displayOptions.length) return false;
					selectedIndex = optionNumber - 1;
					selectCurrent();
					return true;
				}

				function handleInput(data: string): void {
					if (inputMode) {
						if (keybindings.matches(data, "tui.select.cancel")) {
							inputMode = false;
							editor.setText("");
							refresh();
							return;
						}
						editor.handleInput(data);
						refresh();
						return;
					}

					if (selectByNumberKey(data)) return;

					if (keybindings.matches(data, "tui.select.up")) {
						selectedIndex = Math.max(0, selectedIndex - 1);
						refresh();
						return;
					}
					if (keybindings.matches(data, "tui.select.down")) {
						selectedIndex = Math.min(displayOptions.length - 1, selectedIndex + 1);
						refresh();
						return;
					}
					if (keybindings.matches(data, "tui.select.confirm")) {
						selectCurrent();
						return;
					}
					if (keybindings.matches(data, "tui.select.cancel")) {
						done(null);
					}
				}

				function render(width: number): string[] {
					if (cachedLines) return cachedLines;
					const renderWidth = Math.max(1, width);
					const lines: string[] = [];

					function addWrapped(text: string): void {
						lines.push(...wrapTextWithAnsi(text, renderWidth));
					}

					function addWrappedWithPrefix(prefix: string, text: string): void {
						const prefixWidth = visibleWidth(prefix);
						if (prefixWidth >= renderWidth) {
							addWrapped(prefix + text);
							return;
						}
						const wrapped = wrapTextWithAnsi(text, renderWidth - prefixWidth);
						const continuation = " ".repeat(prefixWidth);
						for (let index = 0; index < wrapped.length; index++) {
							lines.push(`${index === 0 ? prefix : continuation}${wrapped[index]}`);
						}
					}

					lines.push(theme.fg("accent", "─".repeat(renderWidth)));
					addWrappedWithPrefix(" ", theme.fg("text", params.question));
					lines.push("");

					for (let index = 0; index < displayOptions.length; index++) {
						const option = displayOptions[index];
						const selected = index === selectedIndex;
						const prefix = selected ? theme.fg("accent", "> ") : "  ";
						const label = `${index + 1}. ${option.label}${option.isCustom && inputMode ? " ✎" : ""}`;
						addWrappedWithPrefix(prefix, theme.fg(selected ? "accent" : "text", label));
						if (option.description) addWrappedWithPrefix("     ", theme.fg("muted", option.description));
					}

					if (inputMode) {
						lines.push("");
						addWrappedWithPrefix(" ", theme.fg("muted", "Custom answer:"));
						for (const line of editor.render(Math.max(1, renderWidth - 2))) lines.push(` ${line}`);
					}

					lines.push("");
					addWrappedWithPrefix(
						" ",
						theme.fg("dim", inputMode ? "Enter submit • Esc back" : "↑↓/number navigate • Enter select • Esc cancel"),
					);
					lines.push(theme.fg("accent", "─".repeat(renderWidth)));

					cachedLines = lines;
					return lines;
				}

				return {
					render,
					invalidate() {
						cachedLines = undefined;
					},
					handleInput,
				};
			});

			if (!result) {
				return {
					content: [{ type: "text", text: "User cancelled the question." }],
					details: {
						question: params.question,
						options,
						answer: null,
						value: null,
						index: null,
						wasCustom: false,
						cancelled: true,
					} satisfies QuestionDetails,
				};
			}

			return {
				content: [
					{
						type: "text",
						text: result.wasCustom
							? `User wrote: ${result.answer}`
							: `User selected: ${result.index}. ${result.answer}`,
					},
				],
				details: {
					question: params.question,
					options,
					answer: result.answer,
					value: result.value,
					index: result.index,
					wasCustom: result.wasCustom,
					cancelled: false,
				} satisfies QuestionDetails,
			};
		},

		renderCall(args, theme) {
			const question = typeof args.question === "string" ? args.question : "";
			const options = Array.isArray(args.options) ? args.options : [];
			const labels = options.map((option: QuestionOption | string, index: number) => {
				if (typeof option === "string") return `${index + 1}. ${option}`;
				return `${index + 1}. ${option.label}`;
			});
			if (args.allowCustom !== false) labels.push(`${labels.length + 1}. Type custom answer`);
			let text = theme.fg("toolTitle", theme.bold("question ")) + theme.fg("muted", question);
			if (labels.length) text += `\n${theme.fg("dim", `  Options: ${labels.join(", ")}`)}`;
			return new Text(text, 0, 0);
		},

		renderResult(result, _options, theme) {
			const details = result.details as QuestionDetails | undefined;
			if (!details) return new Text(textFromContent(result), 0, 0);
			if (details.cancelled || details.answer === null) return new Text(theme.fg("warning", "Cancelled"), 0, 0);
			if (details.wasCustom) {
				return new Text(theme.fg("success", "✓ ") + theme.fg("muted", "(wrote) ") + theme.fg("accent", details.answer), 0, 0);
			}
			const label = details.index ? `${details.index}. ${details.answer}` : details.answer;
			return new Text(theme.fg("success", "✓ ") + theme.fg("accent", label), 0, 0);
		},
	});
}
