import { spawnSync } from "node:child_process";
import {
  CustomEditor,
  type ExtensionAPI,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { matchesKey, truncateToWidth, visibleWidth, type OverlayHandle, type TUI } from "@earendil-works/pi-tui";
import { ScrollbackOverlay, nativeTranscriptComponents, renderComponents, scrollbackRows } from "./comfy-vim-parts/scrollback";
import type { CursorPos, FlashTarget, Mode } from "./comfy-vim-parts/types";

let currentCtx: ExtensionContext | undefined;
let currentTui: TUI | undefined;
let scrollback: ScrollbackOverlay | undefined;
let scrollHandle: OverlayHandle | undefined;
let scrollActive = false;
let currentMode: Mode = "insert";
let lineCacheWidth = -1;
let lineCache: string[] | undefined;
let lineCacheEntryCount = 0;
let liveRefreshTimer: ReturnType<typeof setTimeout> | undefined;
let prewarmTimer: ReturnType<typeof setTimeout> | undefined;
let scrollRenderTimer: ReturnType<typeof setTimeout> | undefined;
let cursorBlinkTimer: ReturnType<typeof setInterval> | undefined;
let cursorBlinkVisible = true;
let lastCursorInputAt = Date.now();

function modeStatusText(mode: Mode): string {
  if (mode === "normal") return "NORMAL";
  if (mode === "visual") return "VISUAL";
  if (mode === "visualLine") return "VISUAL LINE";
  return "INSERT";
}

function setCurrentMode(mode: Mode): void {
  currentMode = mode;
  currentCtx?.ui.setStatus("vim-mode", modeStatusText(mode));
}

function sessionEntries(ctx: ExtensionContext): any[] {
  return (ctx.sessionManager.getBranch?.() ?? ctx.sessionManager.getEntries?.() ?? []) as any[];
}

function prewarmScrollback(): void {
  if (!currentTui) return;
  lineCacheEntryCount = currentCtx ? sessionEntries(currentCtx).length : 0;
  const components = nativeTranscriptComponents(currentTui);
  lineCacheWidth = process.stdout.columns || 80;
  lineCache = renderComponents(components, lineCacheWidth);
}

function schedulePrewarm(delay = 500): void {
  if (scrollback) return;
  if (prewarmTimer) clearTimeout(prewarmTimer);
  prewarmTimer = setTimeout(() => {
    prewarmTimer = undefined;
    if (!scrollback) prewarmScrollback();
  }, delay);
}

function markRenderedCacheStale(): void {
  // Keep the old rendered lines in memory for possible debugging/inspection,
  // but mark them unusable for scrollback entry. Reusing stale lines after a
  // submit/finalize can hide new messages or show pre-final assistant output.
  lineCacheEntryCount = -1;
}

function refreshLiveScrollback(): void {
  if (!currentCtx || !currentTui || !scrollback) return;
  // Use Pi's actual live transcript components so scrollback stays visually
  // aligned with native Pi while the overlay is open.
  scrollback.setComponents(nativeTranscriptComponents(currentTui));
  currentTui.requestRender();
}

function requestScrollRender(tui: TUI): void {
  if (scrollRenderTimer) return;
  scrollRenderTimer = setTimeout(() => {
    scrollRenderTimer = undefined;
    tui.requestRender();
  }, 16);
}

function startCursorBlink(tui: TUI): void {
  if (cursorBlinkTimer) return;
  cursorBlinkTimer = setInterval(() => {
    if (currentMode !== "insert") {
      cursorBlinkVisible = true;
      return;
    }
    // Don't blink while actively typing; keep the cursor solid until the user
    // has paused briefly.
    if (Date.now() - lastCursorInputAt < 900) {
      if (!cursorBlinkVisible) {
        cursorBlinkVisible = true;
        tui.requestRender();
      }
      return;
    }
    cursorBlinkVisible = !cursorBlinkVisible;
    tui.requestRender();
  }, 550);
}

function hideInsertCursor(lines: string[]): string[] {
  const cursorMarker = "\x1b_pi:c\x07";
  return lines.map((line) => {
    const markerIndex = line.indexOf(cursorMarker);
    if (markerIndex === -1) return line;
    const before = line.slice(0, markerIndex + cursorMarker.length);
    const after = line.slice(markerIndex + cursorMarker.length);
    return before + after.replace(/\x1b\[7m([\s\S]*?)\x1b\[(?:0|27)m/, "$1");
  });
}

function scheduleLiveRefresh(): void {
  // While scrollback is open, re-render Pi's native transcript components at a
  // modest cadence. This keeps visuals 1:1 without a rebuild per token.
  if (!scrollback) return;
  if (liveRefreshTimer) return;
  liveRefreshTimer = setTimeout(() => {
    liveRefreshTimer = undefined;
    refreshLiveScrollback();
  }, 100);
}

function ensureScrollback(ctx: ExtensionContext, tui: TUI): void {
  if (ctx.mode !== "tui") return;
  scrollActive = true;
  if (scrollback && scrollHandle) return;

  currentTui = tui;
  const nativeComponents = nativeTranscriptComponents(tui);
  scrollback = new ScrollbackOverlay(tui, nativeComponents);
  const currentEntryCount = sessionEntries(ctx).length;
  const cacheIsFresh = Boolean(lineCache && lineCacheWidth > 0 && lineCacheEntryCount === currentEntryCount);
  if (cacheIsFresh && lineCache) {
    scrollback.primeLines(lineCacheWidth, lineCache);
  } else {
    // Don't use a stale rendered cache after submit: it can hide the just-added
    // user message until the assistant updates. Render native components once
    // so scrollback matches the live Pi transcript.
    lineCache = undefined;
    lineCacheWidth = -1;
    lineCacheEntryCount = currentEntryCount;
    schedulePrewarm(800);
  }
  scrollHandle = tui.showOverlay(scrollback, {
    row: 0,
    col: 0,
    width: "100%",
    maxHeight: scrollbackRows(tui),
    nonCapturing: true,
  });
}

function refreshScrollback(): void {
  if (!currentCtx || !currentTui) return;
  if (scrollback) {
    refreshLiveScrollback();
    return;
  }
  markRenderedCacheStale();
  schedulePrewarm(800);
}

function leaveScrollback(): void {
  scrollActive = false;
  scrollHandle?.hide();
  scrollHandle = undefined;
  scrollback = undefined;
}

function removeScrollback(): void {
  leaveScrollback();
}

class ScrollEditor extends CustomEditor {
  private mode: Mode = "insert";
  private pendingG = false;
  private pendingOperator: "d" | "c" | undefined;
  private visualAnchor: CursorPos | undefined;
  private flashAwaitingChar = false;
  private flashTargets: FlashTarget[] = [];
  private scrollFlashAwaitingChar = false;
  private readonly flashLabels = "asdfghjklqwertyuiopzxcvbnmASDFGHJKLQWERTYUIOPZXCVBNM1234567890";

  private setMode(mode: Mode): void {
    const enteringVisual = (mode === "visual" || mode === "visualLine") && this.mode !== "visual" && this.mode !== "visualLine";
    if (enteringVisual) {
      this.visualAnchor = { ...this.getCursor() };
    } else if (mode !== "visual" && mode !== "visualLine") {
      this.visualAnchor = undefined;
    }
    if (mode !== "normal") {
      this.pendingOperator = undefined;
      this.clearFlash();
    }
    if (this.mode === mode) return;
    this.mode = mode;
    setCurrentMode(mode);
    this.tui.requestRender();
  }

  private activateScrollback(): boolean {
    if (!currentCtx) return false;
    ensureScrollback(currentCtx, this.tui);
    return Boolean(scrollback);
  }

  private isAtStartOfBuffer(): boolean {
    const cursor = this.getCursor();
    return cursor.line === 0 && cursor.col === 0;
  }

  private comparePos(a: CursorPos, b: CursorPos): number {
    if (a.line !== b.line) return a.line - b.line;
    return a.col - b.col;
  }

  private posToIndex(pos: CursorPos): number {
    const lines = this.getText().split("\n");
    let index = 0;
    for (let line = 0; line < Math.min(pos.line, lines.length); line++) {
      index += (lines[line]?.length ?? 0) + 1;
    }
    return index + Math.min(pos.col, lines[pos.line]?.length ?? 0);
  }

  private visualRange(width = process.stdout.columns || 80): {
    start: CursorPos;
    end: CursorPos;
    startIndex: number;
    endIndex: number;
    visualStart?: number;
    visualEnd?: number;
  } | undefined {
    if (!this.visualAnchor) return undefined;
    const cursor = this.getCursor();
    const text = this.getText();

    if (this.mode === "visualLine") {
      const visualLines = this.visualLineMap(width);
      const findVisualLine = (pos: CursorPos): number => {
        const found = (this as any).findVisualLineAt?.(visualLines, pos.line, pos.col);
        return typeof found === "number" ? found : 0;
      };
      const anchorVisual = findVisualLine(this.visualAnchor);
      const cursorVisual = findVisualLine(cursor);
      const visualStart = Math.min(anchorVisual, cursorVisual);
      const visualEnd = Math.max(anchorVisual, cursorVisual);
      const first = visualLines[visualStart];
      const last = visualLines[visualEnd];
      if (!first || !last) return undefined;

      const start = { line: first.logicalLine, col: first.startCol };
      const end = { line: last.logicalLine, col: last.startCol + last.length };
      return {
        start,
        end,
        startIndex: this.posToIndex(start),
        endIndex: this.posToIndex(end),
        visualStart,
        visualEnd,
      };
    }

    const anchorFirst = this.comparePos(this.visualAnchor, cursor) <= 0;
    const start = anchorFirst ? this.visualAnchor : cursor;
    const end = anchorFirst ? cursor : this.visualAnchor;
    const startIndex = this.posToIndex(start);
    // Vim characterwise visual mode is inclusive. Clamp so selecting at EOF is safe.
    const endIndex = Math.min(text.length, this.posToIndex(end) + 1);
    return { start, end, startIndex, endIndex };
  }

  private selectedText(): string {
    const range = this.visualRange();
    return range ? this.getText().slice(range.startIndex, range.endIndex) : "";
  }

  private copyText(text: string): void {
    if (!text) return;
    if (process.platform === "darwin") {
      spawnSync("pbcopy", { input: text });
    }
  }

  private clipboardText(): string {
    if (process.platform === "darwin") {
      const result = spawnSync("pbpaste", { encoding: "utf8" });
      return result.status === 0 ? result.stdout : "";
    }
    for (const command of [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-out"], ["xsel", "--clipboard", "--output"]]) {
      const result = spawnSync(command[0]!, command.slice(1), { encoding: "utf8" });
      if (result.status === 0) return result.stdout;
    }
    return "";
  }

  private pasteClipboardAfterCursor(): void {
    const text = this.clipboardText();
    if (!text) return;
    if (this.getText().length > 0) super.handleInput("\x1b[C");
    this.insertTextAtCursor(text);
    this.tui.requestRender();
  }

  private setCursor(pos: CursorPos): void {
    const state = (this as any).state;
    if (state) {
      state.cursorLine = pos.line;
      state.cursorCol = pos.col;
    }
  }

  private clearFlash(): void {
    this.flashAwaitingChar = false;
    this.flashTargets = [];
  }

  private startFlash(query: string): void {
    this.flashAwaitingChar = false;
    this.flashTargets = [];
    if (!query || query.length !== 1) return;

    const cursor = this.getCursor();
    const lines = this.getText().split("\n");
    for (let line = 0; line < lines.length; line++) {
      const text = lines[line] ?? "";
      for (let col = 0; col < text.length; col++) {
        if (text[col] !== query) continue;
        if (line === cursor.line && col === cursor.col) continue;
        const label = this.flashLabels[this.flashTargets.length];
        if (!label) break;
        this.flashTargets.push({ line, col, label });
      }
      if (this.flashTargets.length >= this.flashLabels.length) break;
    }

    if (this.flashTargets.length === 1) {
      this.setCursor(this.flashTargets[0]!);
      this.clearFlash();
    }
    this.tui.requestRender();
  }

  private handleFlashInput(data: string): boolean {
    if (this.flashAwaitingChar) {
      if (data.length === 1 && data.charCodeAt(0) >= 32) {
        this.startFlash(data);
        return true;
      }
      this.clearFlash();
      return false;
    }

    if (!this.flashTargets.length) return false;
    const target = this.flashTargets.find((item) => item.label === data);
    if (target) this.setCursor(target);
    this.clearFlash();
    this.tui.requestRender();
    return true;
  }

  private replaceVisibleCell(line: string, targetCol: number, label: string): string {
    const index = this.indexAtVisibleCol(line, targetCol);
    if (index >= line.length) return line;
    let end = index;
    if (line[end] === "\x1b") {
      const match = /^\x1b\[[0-?]*[ -/]*[@-~]/.exec(line.slice(end));
      if (match) end += match[0].length;
    }
    const next = line[end] ?? "";
    end += next ? next.length : 0;
    return line.slice(0, index) + "\x1b[7m" + label + "\x1b[0m" + line.slice(end);
  }

  private renderFlashTargets(rendered: string[], width: number): string[] {
    if (!this.flashTargets.length) return rendered;
    const visualLines = this.visualLineMap(width);
    const scrollOffset = Math.max(0, (this as any).scrollOffset ?? 0);
    const next = [...rendered];

    for (const target of this.flashTargets) {
      const visualIndex = visualLines.findIndex((line) =>
        line.logicalLine === target.line &&
        target.col >= line.startCol &&
        target.col < line.startCol + Math.max(1, line.length)
      );
      if (visualIndex < scrollOffset) continue;
      const row = 1 + visualIndex - scrollOffset;
      if (row <= 0 || row >= next.length || !next[row]) continue;
      const visualCol = target.col - (visualLines[visualIndex]?.startCol ?? 0);
      next[row] = truncateToWidth(this.replaceVisibleCell(next[row]!, visualCol, target.label), width, "");
    }

    return next;
  }

  private deleteRange(startIndex: number, endIndex: number): CursorPos {
    const text = this.getText();
    const start = Math.max(0, Math.min(startIndex, endIndex));
    const end = Math.max(0, Math.max(startIndex, endIndex));
    const before = text.slice(0, start);
    const cursor: CursorPos = {
      line: before.split("\n").length - 1,
      col: before.length - before.lastIndexOf("\n") - 1,
    };
    this.setText(text.slice(0, start) + text.slice(end));
    this.setCursor(cursor);
    return cursor;
  }

  private deleteVisualSelection(): void {
    const range = this.visualRange();
    if (!range) return;
    this.deleteRange(range.startIndex, range.endIndex);
  }

  private applyOperatorMotion(operator: "d" | "c", motion: string): boolean {
    const start = this.getCursor();
    const startIndex = this.posToIndex(start);

    if (motion === operator) {
      const lines = this.getText().split("\n");
      const line = Math.max(0, Math.min(start.line, lines.length - 1));
      const deleteStart = this.posToIndex({ line, col: 0 });
      const deleteEnd = line < lines.length - 1 ? this.posToIndex({ line: line + 1, col: 0 }) : this.getText().length;
      this.deleteRange(deleteStart, deleteEnd);
      if (operator === "c") this.setMode("insert");
      return true;
    }

    switch (motion) {
      case "w":
        super.handleInput("\x1bf");
        break;
      case "b":
        super.handleInput("\x1bb");
        break;
      case "0":
        super.handleInput("\x01");
        break;
      case "$":
        super.handleInput("\x05");
        break;
      default:
        return false;
    }

    const endIndex = this.posToIndex(this.getCursor());
    if (endIndex !== startIndex) this.deleteRange(startIndex, endIndex);
    else this.setCursor(start);
    if (operator === "c") this.setMode("insert");
    else this.tui.requestRender();
    return true;
  }

  private handleVisualMovement(data: string): boolean {
    switch (data) {
      case "h":
        super.handleInput("\x1b[D");
        return true;
      case "l":
        super.handleInput("\x1b[C");
        return true;
      case "j":
        super.handleInput("\x1b[B");
        return true;
      case "k":
        // Avoid native Up history recall while extending a visual selection from
        // the very start of the prompt.
        if (!this.isAtStartOfBuffer()) super.handleInput("\x1b[A");
        return true;
      case "0":
        super.handleInput("\x01");
        return true;
      case "$":
        super.handleInput("\x05");
        return true;
      case "w":
        super.handleInput("\x1bf");
        return true;
      case "b":
        super.handleInput("\x1bb");
        return true;
      default:
        return false;
    }
  }

  private indexAtVisibleCol(line: string, targetCol: number): number {
    let visibleCol = 0;
    for (let i = 0; i < line.length;) {
      if (line[i] === "\x1b") {
        const match = /^\x1b\[[0-?]*[ -/]*[@-~]/.exec(line.slice(i));
        if (match) {
          i += match[0].length;
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

  private visualLineMap(width: number): Array<{ logicalLine: number; startCol: number; length: number }> {
    const paddingX = Math.min(this.getPaddingX(), Math.max(0, Math.floor((width - 1) / 2)));
    const contentWidth = Math.max(1, width - paddingX * 2);
    const layoutWidth = Math.max(1, contentWidth - (paddingX ? 0 : 1));
    return (((this as any).buildVisualLineMap?.(layoutWidth) ?? []) as Array<{
      logicalLine: number;
      startCol: number;
      length: number;
    }>);
  }

  private highlightVisibleRange(line: string, startCol: number, endColExclusive: number): string {
    if (endColExclusive <= startCol) return line;

    let visibleCol = 0;
    let startIndex: number | undefined;
    let endIndex: number | undefined;

    for (let i = 0; i < line.length;) {
      if (line[i] === "\x1b") {
        const match = /^\x1b\[[0-?]*[ -/]*[@-~]/.exec(line.slice(i));
        if (match) {
          i += match[0].length;
          continue;
        }
      }

      if (startIndex === undefined && visibleCol >= startCol) startIndex = i;
      const char = line[i] ?? "";
      visibleCol += Math.max(1, visibleWidth(char));
      i += char.length;
      if (endIndex === undefined && visibleCol >= endColExclusive) {
        endIndex = i;
        break;
      }
    }

    startIndex ??= line.length;
    endIndex ??= line.length;
    // The editor may already contain ANSI for the fake cursor. If that cursor
    // reset lands inside our selection, immediately re-enable inverse video so
    // the rest of the visual selection stays painted.
    const selected = line.slice(startIndex, endIndex).replace(/\x1b\[0m/g, "\x1b[0m\x1b[7m");
    return line.slice(0, startIndex) + "\x1b[7m" + selected + "\x1b[0m" + line.slice(endIndex);
  }

  private handleVisualBufferInput(data: string): boolean {
    if (data === "v") {
      this.setMode(this.mode === "visual" ? "normal" : "visual");
      return true;
    }

    if (data === "V") {
      this.setMode(this.mode === "visualLine" ? "normal" : "visualLine");
      return true;
    }

    if (data === "y") {
      this.copyText(this.selectedText());
      this.setMode("normal");
      return true;
    }

    if (data === "d" || data === "x") {
      this.deleteVisualSelection();
      this.setMode("normal");
      return true;
    }

    if (data === "c") {
      this.deleteVisualSelection();
      this.setMode("insert");
      return true;
    }

    if (data === "s") {
      this.flashAwaitingChar = true;
      this.flashTargets = [];
      this.tui.requestRender();
      return true;
    }

    if (this.handleVisualMovement(data)) {
      this.tui.requestRender();
      return true;
    }

    return true;
  }

  render(width: number): string[] {
    let rendered = super.render(width);
    if (this.mode === "insert" && !cursorBlinkVisible) rendered = hideInsertCursor(rendered);
    const range = this.mode === "visual" || this.mode === "visualLine" ? this.visualRange(width) : undefined;
    if (!range) return this.renderFlashTargets(rendered, width);

    const visualLines = this.visualLineMap(width);
    const scrollOffset = Math.max(0, (this as any).scrollOffset ?? 0);
    let contentRow = 0;
    const highlighted = rendered.map((line, row) => {
      // The editor renders a border row, then visible prompt layout rows, then
      // border rows / autocomplete. Use Pi's own visual-line map so wrapped
      // lines and logical lines stay in sync.
      if (row === 0) return line;
      const visualLine = visualLines[scrollOffset + contentRow];
      if (!visualLine) return line;
      contentRow++;
      if (this.mode === "visualLine") {
        if (range.visualStart === undefined || range.visualEnd === undefined) return line;
        if (scrollOffset + contentRow - 1 < range.visualStart || scrollOffset + contentRow - 1 > range.visualEnd) return line;
      } else if (visualLine.logicalLine < range.start.line || visualLine.logicalLine > range.end.line) {
        return line;
      }

      let startCol = 0;
      let endColExclusive = width;
      if (this.mode !== "visualLine") {
        const segmentStart = visualLine.startCol;
        const segmentEnd = visualLine.startCol + visualLine.length;
        const selectedStart = visualLine.logicalLine === range.start.line ? Math.max(range.start.col, segmentStart) : segmentStart;
        const selectedEnd = visualLine.logicalLine === range.end.line ? Math.min(range.end.col + 1, segmentEnd) : segmentEnd;
        startCol = Math.max(0, selectedStart - segmentStart);
        endColExclusive = Math.max(0, selectedEnd - segmentStart);
      }
      if (endColExclusive <= startCol) return line;

      const cursorMarker = "\x1b_pi:c\x07";
      const markerIndex = line.indexOf(cursorMarker);
      const markerCol = markerIndex === -1 ? undefined : visibleWidth(line.slice(0, markerIndex));
      const lineWithoutMarker = markerIndex === -1
        ? line
        : line.slice(0, markerIndex) + line.slice(markerIndex + cursorMarker.length);
      let highlighted = truncateToWidth(this.highlightVisibleRange(lineWithoutMarker, startCol, endColExclusive), width, "");
      if (markerCol !== undefined && markerCol <= width) {
        const insertAt = this.indexAtVisibleCol(highlighted, markerCol);
        highlighted = highlighted.slice(0, insertAt) + cursorMarker + highlighted.slice(insertAt);
      }
      return highlighted;
    });
    return this.renderFlashTargets(highlighted, width);
  }

  private handleScrollbackInput(data: string): boolean {
    if (!scrollActive) return false;

    if (this.scrollFlashAwaitingChar) {
      this.scrollFlashAwaitingChar = false;
      if (data.length === 1 && data.charCodeAt(0) >= 32) {
        scrollback?.startFlash(data);
        requestScrollRender(this.tui);
        return true;
      }
    }

    if (scrollback?.hasFlashTargets()) {
      // Flash in scrollback is the entry point into visual selection: jump to
      // the selected label, anchor there, then vim motions extend selection.
      scrollback.chooseFlash(data, true);
      setCurrentMode("visual");
      requestScrollRender(this.tui);
      return true;
    }

    if (data === "v") {
      scrollback?.toggleSelection();
      setCurrentMode(scrollback?.isSelecting() ? "visual" : "normal");
      requestScrollRender(this.tui);
      return true;
    }

    if (scrollback?.isSelecting() && (data === "h" || data === "j" || data === "k" || data === "l" || data === "w" || data === "b" || data === "e" || data === "0" || data === "$")) {
      scrollback.moveCursor(data);
      requestScrollRender(this.tui);
      return true;
    }

    if (data === "s") {
      this.scrollFlashAwaitingChar = true;
      return true;
    }

    if (data === "y" && scrollback?.isSelecting()) {
      this.copyText(scrollback.selectedText());
      scrollback.clearSelection();
      setCurrentMode("normal");
      currentCtx?.ui.notify("Copied scrollback selection", "info");
      requestScrollRender(this.tui);
      return true;
    }

    if (data === "j" && scrollback?.isFollowingEnd()) {
      leaveScrollback();
      this.tui.requestRender();
      return true;
    }

    if (this.pendingG) {
      this.pendingG = false;
      if (data === "g") {
        scrollback?.top();
        requestScrollRender(this.tui);
        return true;
      }
    }

    if (data === "g") {
      this.pendingG = true;
      return true;
    }

    if (data === "G") {
      scrollback?.setComponents(nativeTranscriptComponents(this.tui));
      scrollback?.bottom();
      requestScrollRender(this.tui);
      return true;
    }

    if (data === "k" || data === "j") {
      scrollback?.scroll(data === "k" ? -1 : 1);
      requestScrollRender(this.tui);
      return true;
    }

    if (matchesKey(data, "ctrl+u") || matchesKey(data, "pageUp")) {
      scrollback?.page(-1);
      requestScrollRender(this.tui);
      return true;
    }

    if (matchesKey(data, "ctrl+d") || matchesKey(data, "pageDown")) {
      scrollback?.page(1);
      requestScrollRender(this.tui);
      return true;
    }

    if (data === "q") {
      this.scrollFlashAwaitingChar = false;
      scrollback?.clearSelection();
      setCurrentMode("normal");
      leaveScrollback();
      this.tui.requestRender();
      return true;
    }

    if (data === "i" || data === "a") {
      this.pendingG = false;
      leaveScrollback();
      this.setMode("insert");
      return true;
    }

    return true;
  }

  private handleNormalBufferInput(data: string): boolean {
    if (this.pendingOperator) {
      const operator = this.pendingOperator;
      this.pendingOperator = undefined;
      if (this.applyOperatorMotion(operator, data)) return true;
      return data.length === 1;
    }

    switch (data) {
      case "s":
        this.flashAwaitingChar = true;
        this.flashTargets = [];
        this.tui.requestRender();
        return true;
      case "v":
        this.setMode("visual");
        return true;
      case "V":
        this.setMode("visualLine");
        return true;
      case "i":
        this.setMode("insert");
        return true;
      case "a":
        super.handleInput("\x1b[C");
        this.setMode("insert");
        return true;
      case "I":
        super.handleInput("\x01");
        this.setMode("insert");
        return true;
      case "A":
        super.handleInput("\x05");
        this.setMode("insert");
        return true;
      case "o":
        super.handleInput("\x05");
        super.handleInput("\n");
        this.setMode("insert");
        return true;
      case "O":
        super.handleInput("\x01");
        super.handleInput("\n");
        super.handleInput("\x1b[A");
        this.setMode("insert");
        return true;
      case "h":
        super.handleInput("\x1b[D");
        return true;
      case "l":
        super.handleInput("\x1b[C");
        return true;
      case "j":
        super.handleInput("\x1b[B");
        return true;
      case "k": {
        // In Pi's editor, Up at the very start of the prompt recalls prompt
        // history. Only intercept that exact case. Everywhere else, let native
        // Up handle multi-line / wrapped-line movement.
        if (!this.isAtStartOfBuffer()) {
          super.handleInput("\x1b[A");
          return true;
        }

        if (this.activateScrollback()) {
          scrollback?.scroll(-1);
          requestScrollRender(this.tui);
        }
        return true;
      }
      case "0":
        super.handleInput("\x01");
        return true;
      case "$":
        super.handleInput("\x05");
        return true;
      case "w":
        super.handleInput("\x1bf");
        return true;
      case "b":
        super.handleInput("\x1bb");
        return true;
      case "p":
        this.pasteClipboardAfterCursor();
        return true;
      case "x":
        super.handleInput("\x1b[3~");
        return true;
      case "d":
        this.pendingOperator = "d";
        return true;
      case "c":
        this.pendingOperator = "c";
        return true;
      case "D":
        super.handleInput("\x0b");
        return true;
      case "C":
        super.handleInput("\x0b");
        this.setMode("insert");
        return true;
      case "u":
        super.handleInput("\x1f");
        return true;
      default:
        return false;
    }
  }

  handleInput(data: string): void {
    lastCursorInputAt = Date.now();
    cursorBlinkVisible = true;
    // Some terminals/tests can deliver a fast Escape+key as one Alt-style chunk
    // (for example "\x1bs"). Treat that as Escape followed by the key so
    // leaving insert mode and immediately starting a normal-mode motion works.
    if (data.length > 1 && data.startsWith("\x1b") && !data.startsWith("\x1b[") && !data.startsWith("\x1bO")) {
      this.handleInput("\x1b");
      for (const char of data.slice(1)) this.handleInput(char);
      return;
    }

    if (matchesKey(data, "escape")) {
      if (scrollActive) {
        this.scrollFlashAwaitingChar = false;
        scrollback?.clearSelection();
        setCurrentMode("normal");
        leaveScrollback();
        this.tui.requestRender();
        return;
      }
      if (this.flashAwaitingChar || this.flashTargets.length) {
        this.clearFlash();
        this.tui.requestRender();
        return;
      }
      if (this.mode === "visual" || this.mode === "visualLine") {
        this.setMode("normal");
        return;
      }
      if (this.mode === "insert" && !this.isShowingAutocomplete()) {
        this.setMode("normal");
        return;
      }
      super.handleInput(data);
      return;
    }

    if (this.mode === "insert") {
      if (matchesKey(data, "enter")) {
        removeScrollback();
      }
      super.handleInput(data);
      return;
    }

    if (this.handleFlashInput(data)) return;

    if (this.mode === "visual" || this.mode === "visualLine") {
      this.handleVisualBufferInput(data);
      return;
    }

    if (this.handleScrollbackInput(data)) return;

    // Main-chat flash: with an empty prompt, `s` opens flash over the chat
    // scrollback. Plain j/k are intentionally left alone here so scrollback
    // mode keeps its original scrolling behavior until a flash target is chosen.
    if (this.getText().length === 0 && data === "s") {
      if (this.activateScrollback()) {
        this.handleScrollbackInput(data);
      }
      return;
    }

    if (this.pendingG) {
      this.pendingG = false;
      if (data === "g") {
        if (this.activateScrollback()) {
          scrollback?.top();
          requestScrollRender(this.tui);
        }
        return;
      }
    }

    if (data === "g") {
      this.pendingG = true;
      return;
    }

    if (data === "G") {
      if (this.activateScrollback()) {
        scrollback?.setComponents(nativeTranscriptComponents(this.tui));
        scrollback?.bottom();
        requestScrollRender(this.tui);
      }
      return;
    }

    if (matchesKey(data, "ctrl+u") || matchesKey(data, "pageUp")) {
      if (this.activateScrollback()) {
        scrollback?.page(-1);
        requestScrollRender(this.tui);
      }
      return;
    }

    if (matchesKey(data, "ctrl+d") || matchesKey(data, "pageDown")) {
      if (this.activateScrollback()) {
        scrollback?.page(1);
        requestScrollRender(this.tui);
      }
      return;
    }

    this.pendingG = false;
    if (this.handleNormalBufferInput(data)) return;
    if (data.length === 1 && data.charCodeAt(0) >= 32) return;
    super.handleInput(data);
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    currentCtx = ctx;
    if (ctx.mode !== "tui") return;
    ctx.ui.setEditorComponent((tui, theme, keybindings) => {
      currentTui = tui;
      startCursorBlink(tui);
      setTimeout(() => prewarmScrollback(), 0);
      setCurrentMode("insert");
      return new ScrollEditor(tui, theme, keybindings);
    });
  });

  pi.on("message_start", () => {
    scheduleLiveRefresh();
  });

  pi.on("message_update", () => {
    scheduleLiveRefresh();
  });

  pi.on("message_end", (event) => {
    // Avoid a full overlay rebuild at the exact moment Pi finalizes the
    // assistant message; native Pi also redraws then, and doing both causes a
    // visible flash. Streaming updates already kept the visible text current.
    if (scrollback && event.message?.role === "assistant") {
      markRenderedCacheStale();
      return;
    }
    refreshScrollback();
  });

  pi.on("tool_execution_start", () => {
    scheduleLiveRefresh();
  });

  pi.on("tool_execution_update", () => {
    scheduleLiveRefresh();
  });

  pi.on("tool_execution_end", () => {
    refreshScrollback();
  });

  pi.on("model_select", () => {
    currentTui?.requestRender();
  });

  pi.on("thinking_level_select", () => {
    currentTui?.requestRender();
  });

  pi.on("agent_settled", () => {
    // Don't force a final overlay repaint while the user is in scrollback; it
    // looks like a screen flash. Cache will refresh after closing/reopening.
    if (scrollback) markRenderedCacheStale();
    else schedulePrewarm(800);
  });

  pi.on("session_shutdown", () => {
    if (liveRefreshTimer) clearTimeout(liveRefreshTimer);
    if (prewarmTimer) clearTimeout(prewarmTimer);
    if (scrollRenderTimer) clearTimeout(scrollRenderTimer);
    if (cursorBlinkTimer) clearInterval(cursorBlinkTimer);
    liveRefreshTimer = undefined;
    prewarmTimer = undefined;
    scrollRenderTimer = undefined;
    cursorBlinkTimer = undefined;
    cursorBlinkVisible = true;
    lastCursorInputAt = Date.now();
    removeScrollback();
    currentCtx?.ui.setStatus("vim-mode", undefined);
    lineCache = undefined;
    lineCacheWidth = -1;
    lineCacheEntryCount = 0;
    currentTui = undefined;
    currentCtx = undefined;
  });
}
