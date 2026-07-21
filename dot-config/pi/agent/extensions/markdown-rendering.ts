import {
  DynamicBorder,
  getMarkdownTheme,
  type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import {
  Container,
  Key,
  Markdown,
  matchesKey,
  Text,
} from "@earendil-works/pi-tui";

type MarkdownToken = {
  type: string;
  depth?: number;
};

type MarkdownInstance = {
  theme: {
    heading: (text: string) => string;
    bold: (text: string) => string;
    listBullet: (text: string) => string;
  };
};

type RenderToken = (
  this: MarkdownInstance,
  token: MarkdownToken,
  width: number,
  nextTokenType?: string,
  styleContext?: unknown,
) => string[];

const HEADING_MARKERS: Record<number, string> = {
  1: "▰ ",
  2: "◆ ",
  3: "▸ ",
  4: "› ",
  5: "· ",
  6: "· ",
};

export function enhanceListMarker(marker: string): string {
  if (/^[-+*] \[x\] /i.test(marker)) return "☑ ";
  if (/^[-+*] \[ \] /.test(marker)) return "☐ ";
  return marker.replace(/^[-+*] /, "• ");
}

export function headingMarker(depth: number | undefined): string {
  return HEADING_MARKERS[depth ?? 1] ?? "› ";
}

function installMarkdownPatch(): void {
  const proto = Markdown.prototype as unknown as {
    renderToken: RenderToken;
    __piRichMarkdownPatched?: boolean;
  };

  if (proto.__piRichMarkdownPatched) return;

  const originalRenderToken = proto.renderToken;
  proto.renderToken = function (
    this: MarkdownInstance,
    token: MarkdownToken,
    width: number,
    nextTokenType?: string,
    styleContext?: unknown,
  ): string[] {
    const originalListBullet = this.theme.listBullet;
    this.theme.listBullet = (marker: string) =>
      originalListBullet(enhanceListMarker(marker));

    try {
      const lines = originalRenderToken.call(
        this,
        token,
        width,
        nextTokenType,
        styleContext,
      );

      if (token.type === "heading" && lines.length > 0) {
        const depth = token.depth ?? 1;
        const marker = headingMarker(depth);
        const nativePrefix = depth >= 3 ? `${"#".repeat(depth)} ` : "";
        if (nativePrefix) lines[0] = lines[0].replace(nativePrefix, "");
        lines[0] = this.theme.heading(this.theme.bold(marker)) + lines[0];
      }

      return lines;
    } finally {
      this.theme.listBullet = originalListBullet;
    }
  };

  proto.__piRichMarkdownPatched = true;
}

const HEADING_DEMO = `# Markdown that reads like structure

## Headings now have visible hierarchy

### Third-level section

#### Small subsection

Body copy remains calm while headings are easy to scan.`;

const LIST_DEMO = `# Lists are unmistakably lists

- First-level bullet
- A longer bullet wraps with a clean hanging indent so the structure remains obvious
  - Nested bullet
  - Another nested item
- Final bullet

1. Ordered items keep their numbers
2. Numbering remains aligned

- [x] Completed task
- [ ] Open task`;

const ALL_DEMO = `${HEADING_DEMO}

---

${LIST_DEMO}

> Blockquotes, **bold**, *italic*, \`inline code\`, and [links](https://pi.dev) continue to use Pi's native Markdown renderer.

| Feature | Result |
| --- | --- |
| Headings | Visible hierarchy |
| Bullets | Typographic markers |
| Tasks | Checkbox glyphs |`;

function demoMarkdown(args: string): string {
  switch (args.trim().toLowerCase()) {
    case "headings":
      return HEADING_DEMO;
    case "lists":
      return LIST_DEMO;
    default:
      return ALL_DEMO;
  }
}

export default function (pi: ExtensionAPI) {
  installMarkdownPatch();

  pi.registerCommand("markdown-demo", {
    description: "Preview rich Markdown rendering (headings, lists, or all)",
    handler: async (args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify("The Markdown demo requires interactive TUI mode.", "warning");
        return;
      }

      await ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
        const container = new Container();
        container.addChild(
          new DynamicBorder((text: string) => theme.fg("accent", text)),
        );
        container.addChild(
          new Text(theme.fg("accent", theme.bold(" Rich Markdown preview ")), 1, 0),
        );
        container.addChild(new Markdown(demoMarkdown(args), 2, 1, getMarkdownTheme()));
        container.addChild(
          new Text(theme.fg("dim", " esc or enter to close"), 1, 0),
        );
        container.addChild(
          new DynamicBorder((text: string) => theme.fg("accent", text)),
        );

        return {
          render: (width: number) => container.render(width),
          invalidate: () => container.invalidate(),
          handleInput: (data: string) => {
            if (matchesKey(data, Key.escape) || matchesKey(data, Key.enter)) {
              done();
              return;
            }
            tui.requestRender();
          },
        };
      });
    },
  });
}
