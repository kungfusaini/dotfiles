import { execFile } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

type OAuthCredential = {
  type: "oauth";
  access: string;
  refresh: string;
  expires: number;
  accountId?: string;
};

type CodexUsageWindow = {
  used_percent?: number;
  reset_at?: number;
  reset_after_seconds?: number;
};

const CODEX_PROVIDER_ID = "openai-codex";
const CODEX_USAGE_REFRESH_MS = 60_000;
const CODEX_TOKEN_REFRESH_SKEW_MS = 60_000;
const OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
const OPENAI_CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token";

let codexUsageText = "Codex usage loading…";
let codexUsageTimer: NodeJS.Timeout | undefined;
let codexUsageInFlight = false;
let activeTui: { requestRender(): void } | undefined;

function piAgentDir(): string {
  return process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
}

function readCodexAuth(): OAuthCredential | undefined {
  const all = JSON.parse(readFileSync(join(piAgentDir(), "auth.json"), "utf8")) as Record<string, unknown>;
  const cred = all[CODEX_PROVIDER_ID] as Partial<OAuthCredential> | undefined;
  if (!cred || cred.type !== "oauth" || typeof cred.access !== "string" || typeof cred.refresh !== "string") return undefined;
  return cred as OAuthCredential;
}

async function refreshCodexAuth(previous: OAuthCredential): Promise<OAuthCredential> {
  const response = await fetch(OPENAI_CODEX_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: previous.refresh,
      client_id: OPENAI_CODEX_CLIENT_ID,
    }),
  });
  if (!response.ok) throw new Error(`token refresh failed: ${response.status}`);
  const json = await response.json() as { access_token?: string; refresh_token?: string; expires_in?: number };
  if (!json.access_token || !json.refresh_token || typeof json.expires_in !== "number") throw new Error("token refresh missing fields");
  const next: OAuthCredential = {
    type: "oauth",
    access: json.access_token,
    refresh: json.refresh_token,
    expires: Date.now() + json.expires_in * 1000,
    accountId: previous.accountId,
  };
  const path = join(piAgentDir(), "auth.json");
  const all = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  all[CODEX_PROVIDER_ID] = next;
  writeFileSync(path, JSON.stringify(all, null, 2) + "\n", "utf8");
  return next;
}

async function freshCodexAuth(): Promise<OAuthCredential | undefined> {
  const cred = readCodexAuth();
  if (!cred) return undefined;
  if (typeof cred.expires !== "number" || Date.now() < cred.expires - CODEX_TOKEN_REFRESH_SKEW_MS) return cred;
  return refreshCodexAuth(cred);
}

function curlGetJson(url: string, headers: Record<string, string>, timeoutSeconds: number): Promise<any> {
  return new Promise((resolve, reject) => {
    const args = ["-fsS", "--max-time", String(timeoutSeconds)];
    for (const [key, value] of Object.entries(headers)) args.push("-H", `${key}: ${value}`);
    args.push(url);
    execFile("curl", args, { timeout: (timeoutSeconds + 2) * 1000, maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr?.trim() || error.message));
        return;
      }
      try { resolve(JSON.parse(stdout)); } catch (parseError) { reject(parseError); }
    });
  });
}

function codexResetSeconds(window: CodexUsageWindow | undefined): number | undefined {
  if (!window) return undefined;
  if (typeof window.reset_after_seconds === "number") return Math.max(0, window.reset_after_seconds);
  if (typeof window.reset_at === "number") return Math.max(0, window.reset_at - Math.floor(Date.now() / 1000));
  return undefined;
}

function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined) return "?";
  if (seconds < 60) return "<1m";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  if (hours < 48) return remMinutes ? `${hours}h${remMinutes}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours ? `${days}d${remHours}h` : `${days}d`;
}

function remainingPercent(window: CodexUsageWindow | undefined): string {
  if (typeof window?.used_percent !== "number") return "?%";
  return `${Math.max(0, Math.min(100, Math.round(100 - window.used_percent)))}%`;
}

function formatCodexUsage(payload: any): string {
  const primary = payload?.rate_limit?.primary_window as CodexUsageWindow | undefined;
  const secondary = payload?.rate_limit?.secondary_window as CodexUsageWindow | undefined;
  let text = `Codex ${remainingPercent(primary)} remaining • reset ${formatDuration(codexResetSeconds(primary))}`;
  if (typeof secondary?.used_percent === "number") {
    text += ` • secondary ${remainingPercent(secondary)} remaining reset ${formatDuration(codexResetSeconds(secondary))}`;
  }
  return text;
}

async function refreshCodexUsage(): Promise<void> {
  if (codexUsageInFlight) return;
  codexUsageInFlight = true;
  try {
    const cred = await freshCodexAuth();
    if (!cred) {
      codexUsageText = "Codex usage unavailable";
      return;
    }
    const headers: Record<string, string> = {
      Authorization: `Bearer ${cred.access}`,
      "User-Agent": "codex-cli",
    };
    if (cred.accountId) headers["ChatGPT-Account-Id"] = cred.accountId;
    const payload = await curlGetJson("https://chatgpt.com/backend-api/wham/usage", headers, 8);
    codexUsageText = formatCodexUsage(payload);
  } catch {
    codexUsageText = "Codex usage unavailable";
  } finally {
    codexUsageInFlight = false;
    activeTui?.requestRender();
  }
}

function formatCwdForFooter(cwd: string, home?: string): string {
  if (!home) return cwd;
  const resolvedCwd = resolve(cwd);
  const resolvedHome = resolve(home);
  const relativeToHome = relative(resolvedHome, resolvedCwd);
  const isInsideHome = relativeToHome === "" ||
    (relativeToHome !== ".." && !relativeToHome.startsWith(`..${sep}`) && !isAbsolute(relativeToHome));
  if (!isInsideHome) return cwd;
  return relativeToHome === "" ? "~" : `~${sep}${relativeToHome}`;
}

function sanitizeStatusText(text: string): string {
  return text.replace(/[\r\n\t]/g, " ").replace(/ +/g, " ").trim();
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    void refreshCodexUsage();
    if (!codexUsageTimer) codexUsageTimer = setInterval(refreshCodexUsage, CODEX_USAGE_REFRESH_MS);

    ctx.ui.setFooter((tui, theme, footerData) => {
      activeTui = tui;
      const unsub = footerData.onBranchChange(() => tui.requestRender());
      return {
        dispose: unsub,
        invalidate() {},
        render(width: number): string[] {
          let pwd = formatCwdForFooter(ctx.sessionManager.getCwd(), process.env.HOME || process.env.USERPROFILE);
          const branch = footerData.getGitBranch();
          if (branch) pwd = `${pwd} (${branch})`;
          const sessionName = ctx.sessionManager.getSessionName();
          if (sessionName) pwd = `${pwd} • ${sessionName}`;

          let left = theme.fg("dim", codexUsageText);
          let leftWidth = visibleWidth(left);
          if (leftWidth > width) {
            left = truncateToWidth(left, width, "...");
            leftWidth = visibleWidth(left);
          }

          const model = ctx.model;
          const modelName = model?.id || "no-model";
          let rightText = modelName;
          if (model?.reasoning) {
            const level = pi.getThinkingLevel();
            rightText = level === "off" ? `${modelName} • thinking off` : `${modelName} • ${level}`;
          }
          if (footerData.getAvailableProviderCount() > 1 && model) {
            const withProvider = `(${model.provider}) ${rightText}`;
            if (leftWidth + 2 + visibleWidth(withProvider) <= width) rightText = withProvider;
          }
          const vimMode = footerData.getExtensionStatuses().get("vim-mode");
          if (vimMode) rightText += ` • ${sanitizeStatusText(vimMode)}`;
          const right = theme.fg("dim", rightText);
          const rightWidth = visibleWidth(right);
          const availableLeft = Math.max(0, width - rightWidth - 2);
          const visibleLeft = visibleWidth(left) > availableLeft ? truncateToWidth(left, availableLeft, "") : left;
          const padding = " ".repeat(Math.max(2, width - visibleWidth(visibleLeft) - rightWidth));

          const lines = [
            truncateToWidth(theme.fg("dim", pwd), width, theme.fg("dim", "...")),
            truncateToWidth(visibleLeft + padding + right, width, ""),
          ];

          const statusLine = Array.from(footerData.getExtensionStatuses().entries())
            .filter(([key]) => key !== "vim-mode")
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([, text]) => sanitizeStatusText(text))
            .join(" ");
          if (statusLine) lines.push(truncateToWidth(statusLine, width, theme.fg("dim", "...")));
          return lines;
        },
      };
    });
  });

  pi.on("after_provider_response", (event, ctx) => {
    if (ctx.model?.provider === CODEX_PROVIDER_ID && event.status >= 200 && event.status < 300) void refreshCodexUsage();
  });

  pi.on("session_shutdown", () => {
    if (codexUsageTimer) clearInterval(codexUsageTimer);
    codexUsageTimer = undefined;
    activeTui = undefined;
  });
}
