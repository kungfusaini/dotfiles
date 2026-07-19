import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Markdown, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

type MarkdownInstance = {
  theme: {
    codeBlock: (text: string) => string;
    codeBlockBorder: (text: string) => string;
    highlightCode?: (code: string, lang?: string) => string[];
  };
};

type MarkdownToken = {
  type: string;
  text?: string;
  lang?: string;
};

const LANGUAGE_ICONS: Record<string, string> = {
  bash: "",
  sh: "",
  zsh: "",
  fish: "",
  javascript: "",
  js: "",
  typescript: "󰛦",
  ts: "󰛦",
  json: "",
  python: "",
  py: "",
  rust: "",
  rs: "",
  go: "",
  markdown: "",
  md: "",
  text: "󰈙",
};

function normalizeLang(lang: string | undefined): string {
  return (lang ?? "").trim().toLowerCase();
}

function languageLabel(lang: string | undefined): string {
  const normalized = normalizeLang(lang);
  if (!normalized) return "code";
  const icon = LANGUAGE_ICONS[normalized] ?? "󰅩";
  return `${icon} ${normalized}`;
}

function gruvboxOrange(text: string): string {
  return `\x1b[38;2;254;128;25m${text}\x1b[39m`;
}

function gruvboxBlockBg(line: string, width: number): string {
  const blockBg = "\x1b[48;2;60;56;54m";
  const orangeBg = "\x1b[48;2;254;128;25m";
  const resetBg = "\x1b[49m";
  const stripWidth = 1;
  const contentWidth = Math.max(0, width - stripWidth);
  const content = truncateToWidth(line, contentWidth, "");
  const contentWithBgReapplied = content.replace(/\x1b\[0m/g, `\x1b[0m${blockBg}`);
  const padding = " ".repeat(Math.max(0, contentWidth - visibleWidth(content)));
  return `${orangeBg}${" ".repeat(stripWidth)}${blockBg}${contentWithBgReapplied}${padding}${resetBg}`;
}

export default function (_pi: ExtensionAPI) {
  const proto = Markdown.prototype as any;
  if (proto.__piPrettyCodeBlocksPatched) return;

  const originalRenderToken = proto.renderToken;

  proto.renderToken = function (
    this: MarkdownInstance,
    token: MarkdownToken,
    width: number,
    nextTokenType?: string,
    styleContext?: unknown,
  ): string[] {
    if (token.type !== "code") {
      return originalRenderToken.call(this, token, width, nextTokenType, styleContext);
    }

    const header = gruvboxOrange(languageLabel(token.lang));
    const lines: string[] = [gruvboxBlockBg(`  ${header}`, width)];

    const code = token.text ?? "";
    const highlighted = this.theme.highlightCode
      ? this.theme.highlightCode(code, token.lang)
      : code.split("\n").map((line) => this.theme.codeBlock(line));

    for (const line of highlighted) {
      lines.push(gruvboxBlockBg(`  ${line}`, width));
    }

    if (nextTokenType && nextTokenType !== "space") {
      lines.push("");
    }

    return lines;
  };

  proto.__piPrettyCodeBlocksPatched = true;
}
