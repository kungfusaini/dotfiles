import { truncateToWidth, visibleWidth, type Component, type TUI } from "@earendil-works/pi-tui";

type ScrollFlashTarget = { line: number; col: number; label: string };

export class ScrollbackOverlay implements Component {
  private offset = Number.MAX_SAFE_INTEGER;
  private followEnd = true;
  private cachedWidth = -1;
  private cachedLines: string[] | undefined;
  private cursor = { line: 0, col: 0 };
  private selectionAnchor: { line: number; col: number } | undefined;
  private flashTargets: ScrollFlashTarget[] = [];
  private readonly flashLabels = "asdfghjklqwertyuiopzxcvbnmASDFGHJKLQWERTYUIOPZXCVBNM1234567890";

  constructor(private tui: TUI, private components: Component[]) {}

  primeLines(width: number, lines: string[]): void {
    this.cachedWidth = width;
    this.cachedLines = lines;
  }

  setComponents(components: Component[]): void {
    this.components = components;
    if (this.followEnd) this.offset = Number.MAX_SAFE_INTEGER;
    this.cachedWidth = -1;
    this.cachedLines = undefined;
  }

  invalidate(): void {
    this.cachedWidth = -1;
    this.cachedLines = undefined;
    for (const component of this.components) component.invalidate();
  }

  scroll(delta: number): void {
    if (delta < 0) this.followEnd = false;
    this.offset += delta;
    this.cursor.line = Math.max(0, this.cursor.line + delta);
  }

  page(delta: number): void {
    if (delta < 0) this.followEnd = false;
    const rows = scrollbackRows(this.tui);
    this.offset += Math.max(1, Math.floor(rows / 2)) * delta;
  }

  top(): void {
    this.followEnd = false;
    this.offset = 0;
    this.cursor = { line: 0, col: 0 };
  }

  bottom(): void {
    this.followEnd = true;
    this.offset = Number.MAX_SAFE_INTEGER;
    const lines = this.renderedLines(process.stdout.columns || 80);
    this.cursor = { line: Math.max(0, lines.length - 1), col: 0 };
  }

  toggleSelection(): void {
    if (this.selectionAnchor) this.selectionAnchor = undefined;
    else this.selectionAnchor = { ...this.cursor };
    this.flashTargets = [];
  }

  isSelecting(): boolean {
    return Boolean(this.selectionAnchor);
  }

  clearSelection(): void {
    this.selectionAnchor = undefined;
    this.flashTargets = [];
  }

  hasFlashTargets(): boolean {
    return this.flashTargets.length > 0;
  }

  startFlash(query: string): void {
    this.flashTargets = [];
    if (!query || query.length !== 1) return;
    const width = process.stdout.columns || 80;
    const rows = scrollbackRows(this.tui, width);
    const rendered = this.renderedLines(width);
    const maxOffset = Math.max(0, rendered.length - rows);
    this.offset = Math.max(0, Math.min(this.offset, maxOffset));
    if (this.offset === maxOffset) this.followEnd = true;
    const lines = rendered.map((line) => this.stripAnsi(line));
    for (let lineNo = this.offset; lineNo < Math.min(lines.length, this.offset + rows); lineNo++) {
      const line = lines[lineNo] ?? "";
      for (let col = 0; col < line.length; col++) {
        if (line[col] !== query) continue;
        const label = this.flashLabels[this.flashTargets.length];
        if (!label) return;
        this.flashTargets.push({ line: lineNo, col, label });
      }
    }
  }

  chooseFlash(label: string, enterSelection = false): boolean {
    const target = this.flashTargets.find((item) => item.label === label);
    this.flashTargets = [];
    if (!target) return false;
    this.cursor = { line: target.line, col: target.col };
    if (enterSelection) this.selectionAnchor = { ...this.cursor };
    this.followEnd = false;
    return true;
  }

  moveCursor(direction: "h" | "j" | "k" | "l" | "w" | "b" | "e" | "0" | "$"): void {
    const width = process.stdout.columns || 80;
    const rows = scrollbackRows(this.tui, width);
    const lines = this.renderedLines(width).map((line) => this.stripAnsi(line).trimEnd());
    if (!lines.length) return;

    const currentLine = () => lines[this.cursor.line] ?? "";
    const isWord = (char: string | undefined) => Boolean(char && /[A-Za-z0-9_]/.test(char));
    const nextLineStart = () => {
      if (this.cursor.line < lines.length - 1) {
        this.cursor.line++;
        this.cursor.col = 0;
        return true;
      }
      return false;
    };
    const prevLineEnd = () => {
      if (this.cursor.line > 0) {
        this.cursor.line--;
        this.cursor.col = Math.max(0, (lines[this.cursor.line] ?? "").length - 1);
        return true;
      }
      return false;
    };

    if (direction === "h") this.cursor.col--;
    else if (direction === "l") this.cursor.col++;
    else if (direction === "j") this.cursor.line++;
    else if (direction === "k") this.cursor.line--;
    else if (direction === "0") this.cursor.col = 0;
    else if (direction === "$") this.cursor.col = Math.max(0, currentLine().length - 1);
    else if (direction === "w") {
      let line = currentLine();
      let i = this.cursor.col;
      if (isWord(line[i])) while (i < line.length && isWord(line[i])) i++;
      while (i < line.length && !isWord(line[i])) i++;
      if (i < line.length) this.cursor.col = i;
      else if (nextLineStart()) {
        line = currentLine();
        i = 0;
        while (i < line.length && !isWord(line[i])) i++;
        this.cursor.col = Math.min(i, Math.max(0, line.length - 1));
      }
    } else if (direction === "e") {
      let line = currentLine();
      let i = Math.min(this.cursor.col + 1, line.length - 1);
      while (i < line.length && !isWord(line[i])) i++;
      if (i >= line.length) {
        if (!nextLineStart()) return;
        line = currentLine();
        i = 0;
        while (i < line.length && !isWord(line[i])) i++;
      }
      while (i < line.length && isWord(line[i])) i++;
      this.cursor.col = Math.max(0, i - 1);
    } else if (direction === "b") {
      let line = currentLine();
      let i = this.cursor.col - 1;
      while (i >= 0 && !isWord(line[i])) i--;
      if (i < 0) {
        if (!prevLineEnd()) return;
        line = currentLine();
        i = this.cursor.col;
        while (i >= 0 && !isWord(line[i])) i--;
      }
      while (i > 0 && isWord(line[i - 1])) i--;
      this.cursor.col = Math.max(0, i);
    }

    this.cursor.line = Math.max(0, Math.min(this.cursor.line, lines.length - 1));
    const maxCol = Math.max(0, (lines[this.cursor.line] ?? "").length - 1);
    this.cursor.col = Math.max(0, Math.min(this.cursor.col, maxCol));

    this.followEnd = false;
    if (this.cursor.line < this.offset) this.offset = this.cursor.line;
    if (this.cursor.line >= this.offset + rows) this.offset = Math.max(0, this.cursor.line - rows + 1);
  }

  selectedText(): string {
    if (!this.selectionAnchor) return "";
    const width = process.stdout.columns || 80;
    const lines = this.renderedLines(width).map((line) => this.stripAnsi(line).trimEnd());
    let start = this.selectionAnchor;
    let end = this.cursor;
    if (start.line > end.line || (start.line === end.line && start.col > end.col)) [start, end] = [end, start];
    if (start.line === end.line) return (lines[start.line] ?? "").slice(start.col, end.col + 1);
    const selected: string[] = [];
    selected.push((lines[start.line] ?? "").slice(start.col));
    for (let line = start.line + 1; line < end.line; line++) selected.push(lines[line] ?? "");
    selected.push((lines[end.line] ?? "").slice(0, end.col + 1));
    return selected.join("\n");
  }

  isFollowingEnd(): boolean {
    return this.followEnd;
  }

  private renderedLines(width: number): string[] {
    if (!this.cachedLines || this.cachedWidth !== width) {
      this.cachedWidth = width;
      this.cachedLines = renderComponents(this.components, width);
    }

    return this.cachedLines;
  }

  private stripAnsi(line: string): string {
    return line.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b\][^\x07]*\x07/g, "");
  }

  private indexAtVisibleCol(line: string, targetCol: number): number {
    let visibleCol = 0;
    for (let i = 0; i < line.length;) {
      if (line[i] === "\x1b") {
        const sgr = /^\x1b\[[0-?]*[ -/]*[@-~]/.exec(line.slice(i));
        if (sgr) {
          i += sgr[0].length;
          continue;
        }
        const osc = /^\x1b\][^\x07]*\x07/.exec(line.slice(i));
        if (osc) {
          i += osc[0].length;
          continue;
        }
      }
      if (visibleCol >= targetCol) return i;
      const char = line[i] ?? "";
      visibleCol += Math.max(1, visibleWidth(char));
      i += char.length;
    }
    return line.length;
  }

  private replaceVisibleCell(line: string, targetCol: number, label: string): string {
    const start = this.indexAtVisibleCol(line, targetCol);
    if (start >= line.length) return line;
    let end = start;
    if (line[end] === "\x1b") {
      const sgr = /^\x1b\[[0-?]*[ -/]*[@-~]/.exec(line.slice(end));
      if (sgr) end += sgr[0].length;
      const osc = /^\x1b\][^\x07]*\x07/.exec(line.slice(end));
      if (osc) end += osc[0].length;
    }
    const char = line[end] ?? "";
    if (char) end += char.length;
    // Use 27m (inverse off), not 0m (full reset). That keeps whatever Pi's
    // renderer had active for the rest of the line: markdown colors, code block
    // syntax colors, muted tool text, etc.
    return line.slice(0, start) + "\x1b[7m" + label + "\x1b[27m" + line.slice(end);
  }

  private highlightVisibleRange(line: string, startCol: number, endColExclusive: number): string {
    if (endColExclusive <= startCol) return line;
    const start = this.indexAtVisibleCol(line, startCol);
    const end = this.indexAtVisibleCol(line, endColExclusive);
    // Same trick: inverse on/off only, no SGR reset, so existing colors survive
    // both inside and after the highlighted selection.
    return line.slice(0, start) + "\x1b[7m" + line.slice(start, end) + "\x1b[27m" + line.slice(end);
  }

  private decorateLine(line: string, absoluteLine: number, width: number): string {
    const base = visibleWidth(line) > width ? truncateToWidth(line, width, "") : line;
    const paddedBase = base + " ".repeat(Math.max(0, width - visibleWidth(base)));

    const flash = this.flashTargets.filter((target) => target.line === absoluteLine).sort((a, b) => b.col - a.col);
    const isSelectionLine = (() => {
      if (!this.selectionAnchor) return false;
      let start = this.selectionAnchor;
      let end = this.cursor;
      if (start.line > end.line || (start.line === end.line && start.col > end.col)) [start, end] = [end, start];
      return absoluteLine >= start.line && absoluteLine <= end.line;
    })();

    // Preserve Pi's native message/tool/markdown colors unless we actually need
    // to paint flash labels or a visual selection on this line. The first
    // selection implementation stripped ANSI for every scrollback line, which
    // made scrollback look monochrome.
    if (!flash.length && !isSelectionLine) return paddedBase;

    if (flash.length && !isSelectionLine) {
      let flashed = paddedBase;
      for (const target of flash) {
        flashed = this.replaceVisibleCell(flashed, target.col, target.label);
      }
      const truncated = truncateToWidth(flashed, width, "");
      return truncated + " ".repeat(Math.max(0, width - visibleWidth(truncated)));
    }

    let decorated = paddedBase;
    for (const target of flash) {
      decorated = this.replaceVisibleCell(decorated, target.col, target.label);
    }

    if (this.selectionAnchor && !flash.length) {
      let start = this.selectionAnchor;
      let end = this.cursor;
      if (start.line > end.line || (start.line === end.line && start.col > end.col)) [start, end] = [end, start];
      const selectionStart = absoluteLine === start.line ? start.col : 0;
      const selectionEnd = absoluteLine === end.line ? end.col + 1 : this.stripAnsi(decorated).length;
      decorated = this.highlightVisibleRange(decorated, selectionStart, Math.max(selectionStart, selectionEnd));
    }

    const truncated = truncateToWidth(decorated, width, "");
    return truncated + " ".repeat(Math.max(0, width - visibleWidth(truncated)));
  }

  render(width: number): string[] {
    // Overlay, not widget: do not participate in Pi layout. Compute the same
    // bottom area Pi is using for the real editor/footer instead of guessing.
    const rows = scrollbackRows(this.tui, width);
    const lines = this.renderedLines(width);
    const maxOffset = Math.max(0, lines.length - rows);
    this.offset = Math.max(0, Math.min(this.offset, maxOffset));
    if (this.offset === maxOffset) this.followEnd = true;
    this.cursor.line = Math.max(0, Math.min(this.cursor.line, Math.max(0, lines.length - 1)));
    const visible = lines
      .slice(this.offset, this.offset + rows)
      // Fully cover the underlying native transcript. If overlay lines are
      // shorter/transparent, old Pi output can show through and look duplicated.
      .map((line, index) => this.decorateLine(line, this.offset + index, width));
    if (visible.length < rows) {
      return [...Array(rows - visible.length).fill(" ".repeat(Math.max(1, width))), ...visible];
    }
    return visible;
  }
}

export function renderComponents(components: Component[], width: number): string[] {
  const lines: string[] = [];
  for (const component of components) {
    const rendered = component.render(width);
    if (!rendered.length) continue;
    lines.push(...rendered);
  }
  return lines.length ? lines : [""];
}

export function nativeTranscriptComponents(tui: TUI): Component[] {
  // Pi's root layout is:
  // 0 header, 1 loaded resources, 2 chat, 3 pending messages, 4 status,
  // 5 widgets above editor, 6 editor, 7 widgets below, 8 footer.
  // Use the actual native components instead of reconstructing messages from
  // session state. This is the only way for scrollback to be visually 1:1.
  const children = ((tui as any).children ?? []) as Component[];
  return children.slice(1, 5).filter(Boolean);
}

export function scrollbackRows(tui?: TUI, width = process.stdout.columns || 80): number {
  const terminalRows = process.stdout.rows || 30;
  const children = ((tui as any)?.children ?? []) as Component[];
  // Pi root layout: 6 editor, 7 widgets below editor, 8 footer. Measure them so
  // the overlay stops exactly above Pi's real input/footer area.
  const reserved = children
    .slice(6, 9)
    .reduce((rows, component) => rows + Math.max(0, component?.render(width)?.length ?? 0), 0);
  return Math.max(1, terminalRows - Math.max(3, reserved));
}

