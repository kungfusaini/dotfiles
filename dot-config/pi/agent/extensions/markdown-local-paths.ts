import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { existsSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const LOCAL_PATH_CANDIDATE = /(^|[\s([{<])((?:~\/|\.{1,2}\/|\/|[A-Za-z0-9_.@+-]+\/)[^\s<>"'`]+)/g;
const TRAILING_PATH_PUNCTUATION = /[),.;:!?\]]+$/;
const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})/;
const MASKED_MARKDOWN_SEGMENT = /!?\[[^\]\n]*\]\([^\)\n]+\)|`+[^`\n]*`+/g;

function maskMarkdownSegments(line: string): { masked: string; segments: string[] } {
  const segments: string[] = [];
  const masked = line.replace(MASKED_MARKDOWN_SEGMENT, (match) => {
    const index = segments.push(match) - 1;
    return `\uE000${index}\uE001`;
  });
  return { masked, segments };
}

function unmaskMarkdownSegments(line: string, segments: string[]): string {
  return line.replace(/\uE000(\d+)\uE001/g, (_match, index: string) =>
    segments[Number(index)] ?? _match,
  );
}

function expandLocalPath(pathText: string, cwd: string): string {
  if (pathText.startsWith("~/")) return resolve(homedir(), pathText.slice(2));
  return resolve(cwd, pathText);
}

export function localPathToFileUrl(pathText: string, cwd = process.cwd()): string | undefined {
  const absolutePath = expandLocalPath(pathText, cwd);
  try {
    if (!existsSync(absolutePath)) return undefined;
    statSync(absolutePath);
    return pathToFileURL(absolutePath).href;
  } catch {
    return undefined;
  }
}

function splitTrailingPunctuation(pathText: string): { pathText: string; trailing: string } {
  const match = TRAILING_PATH_PUNCTUATION.exec(pathText);
  if (!match) return { pathText, trailing: "" };
  return {
    pathText: pathText.slice(0, -match[0].length),
    trailing: match[0],
  };
}

function linkifyLocalPathsInLine(line: string, cwd: string): string {
  const { masked, segments } = maskMarkdownSegments(line);
  const linkified = masked.replace(LOCAL_PATH_CANDIDATE, (match, prefix: string, candidate: string) => {
    const { pathText, trailing } = splitTrailingPunctuation(candidate);
    if (!pathText.includes("/") || pathText.includes("://")) return match;
    const url = localPathToFileUrl(pathText, cwd);
    if (!url) return match;
    return `${prefix}[${pathText}](${url})${trailing}`;
  });
  return unmaskMarkdownSegments(linkified, segments);
}

export function linkifyLocalPathsInMarkdown(markdown: string, cwd = process.cwd()): string {
  let inFence = false;
  return markdown
    .split("\n")
    .map((line) => {
      if (FENCE_LINE.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) return line;
      return linkifyLocalPathsInLine(line, cwd);
    })
    .join("\n");
}

export default function (_pi: ExtensionAPI) {
  // Helper module for markdown-rendering.ts. Pi auto-discovers extension/*.ts,
  // so this file must also be a valid extension factory when loaded directly.
}
