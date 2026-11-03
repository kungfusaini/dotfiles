import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";

type ModelMode = {
  id: string;
  label: string;
  description: string;
  provider: string;
  model: string;
  thinkingLevel: ThinkingLevel;
};

type ModelModePolicy = {
  version: number;
  default: string;
  reviewedAt: string;
  reviewedModels?: Record<string, string[]>;
  reviewedCatalogOmissions?: Record<string, string[]>;
  modes: ModelMode[];
};

const POLICY_FILE = "model-modes.json";
const REQUIRED_MODES = ["fast", "normal", "deep", "extreme"];
const THINKING_LEVELS = new Set<ThinkingLevel>([
  "off",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
]);

export function readModelModePolicy(path = join(getAgentDir(), POLICY_FILE)): ModelModePolicy {
  const policy = JSON.parse(readFileSync(path, "utf8")) as Partial<ModelModePolicy>;
  if (policy.version !== 1 || !Array.isArray(policy.modes) || typeof policy.default !== "string") {
    throw new Error("model-modes.json must contain version 1, a default, and a modes array");
  }

  for (const field of ["reviewedModels", "reviewedCatalogOmissions"] as const) {
    const records = policy[field];
    if (records !== undefined && (!records || typeof records !== "object" || Array.isArray(records) ||
        !Object.values(records).every((ids) => Array.isArray(ids) && ids.every((id) =>
          typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$/.test(id))))) {
      throw new Error(`${field} must map providers to arrays of model IDs`);
    }
  }

  const ids = new Set<string>();
  for (const mode of policy.modes) {
    if (
      !mode ||
      typeof mode.id !== "string" ||
      typeof mode.label !== "string" ||
      typeof mode.description !== "string" ||
      typeof mode.provider !== "string" ||
      typeof mode.model !== "string" ||
      !THINKING_LEVELS.has(mode.thinkingLevel)
    ) {
      throw new Error("Every model mode must have an id, label, description, provider, model, and valid thinkingLevel");
    }
    if (ids.has(mode.id)) throw new Error(`Duplicate model mode: ${mode.id}`);
    ids.add(mode.id);
  }

  for (const required of REQUIRED_MODES) {
    if (!ids.has(required)) throw new Error(`Missing required model mode: ${required}`);
  }
  if (!ids.has(policy.default)) throw new Error(`Unknown default model mode: ${policy.default}`);

  return policy as ModelModePolicy;
}

type CatalogModel = { id: string; listed: boolean; supportedInApi: boolean; thinkingLevels: string[] };
export type CatalogReview = { status?: string; details: string };

// Compare against the current policy, not a cached decision from the checker.
export function catalogReview(policy: ModelModePolicy, data: any, now = Date.now()): CatalogReview {
  const unavailable = { status: "models:check unavailable", details: "No valid catalog result yet. Run pi-model-discovery status or inspect the user service." };
  if (!data || data.version !== 1 || data.provider !== "openai-codex" ||
      !Number.isFinite(data.checkedAt) || data.checkedAt < 0 || data.checkedAt > now + 300000 ||
      !Array.isArray(data.models) || data.models.length > 2000 ||
      !data.models.every((m: any) => m && typeof m.id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$/.test(m.id) &&
        typeof m.listed === "boolean" && typeof m.supportedInApi === "boolean" &&
        Array.isArray(m.thinkingLevels) && m.thinkingLevels.every((v: any) => typeof v === "string" && /^[a-z][a-z0-9_-]{0,31}$/.test(v)))) return unavailable;
  const models = data.models as CatalogModel[];
  const pinned = policy.modes.filter((m) => m.provider === "openai-codex");
  const reviewed = new Set([...(policy.reviewedModels?.["openai-codex"] ?? []), ...pinned.map((m) => m.model)]);
  const candidates = models.filter((m) => m.listed && m.supportedInApi && !reviewed.has(m.id));
  const notListed = [...new Set(pinned.filter((m) => !models.some((c) => c.id === m.model && c.listed && c.supportedInApi)).map((m) => m.model))];
  const acknowledged = new Set(policy.reviewedCatalogOmissions?.["openai-codex"] ?? []);
  // Acknowledgements cover absence only, never explicit hidden/unsupported entries.
  const pendingNotListed = notListed.filter((id) => !acknowledged.has(id) || models.some((m) => m.id === id));
  const reviewedOmissions = notListed.filter((id) => !pendingNotListed.includes(id));
  const effortMismatch = pinned.filter((m) => models.some((c) => c.id === m.model && !c.thinkingLevels.includes(m.thinkingLevel)));
  const unsupported = [...new Set(policy.modes.filter((m) => m.provider !== "openai-codex").map((m) => m.provider))];
  const lines = ["Read-only Codex catalog discovery; candidates are not necessarily newer or better."];
  const success = Number.isFinite(data.lastSuccessAt) && data.lastSuccessAt >= 0 && data.lastSuccessAt <= data.checkedAt;
  lines.push(`Last attempt: ${new Date(data.checkedAt).toISOString()}`);
  if (success) {
    lines.push(`Last successful catalog: ${new Date(data.lastSuccessAt).toISOString()}`);
    if (candidates.length) lines.push(`Unreviewed catalog entries: ${candidates.map((m) => m.id).join(", ")}`);
    if (pendingNotListed.length) lines.push(`Pinned models not listed (not proof of unavailability): ${pendingNotListed.join(", ")}`);
    if (reviewedOmissions.length) lines.push(`Reviewed catalog omissions (availability unverified by discovery): ${reviewedOmissions.join(", ")}`);
    if (effortMismatch.length) lines.push(`Reasoning levels not advertised: ${effortMismatch.map((m) => `${m.id}/${m.thinkingLevel}`).join(", ")}`);
  }
  if (unsupported.length) lines.push(`Discovery not supported for: ${unsupported.join(", ")}`);
  const failed = data.status !== "ok";
  const stale = !success || now - data.lastSuccessAt > 48 * 60 * 60 * 1000;
  if (failed) lines.push("Latest check failed; any entries above are from the last successful catalog. Inspect pi-model-discovery status. Shared auth is never refreshed by the checker.");
  if (stale) lines.push("Catalog is missing or older than 48 hours.");
  const needsReview = success && (candidates.length > 0 || pendingNotListed.length > 0 || effortMismatch.length > 0);
  if (success && !failed && !stale && !needsReview && !unsupported.length) lines.push("Review resolved: no pending findings in this catalog; mode mappings retained.");
  lines.push("Mappings remain unchanged. Review candidates and update the Nix policy explicitly; reviewedModels records reviewed candidates and reviewedCatalogOmissions acknowledges specific catalog gaps, not model availability.");
  return {
    status: failed ? "models:check failed /mode-review" : stale ? "models:stale /mode-review" :
      needsReview ? "models:review /mode-review" : unsupported.length ? "models:partial /mode-review" : undefined,
    details: lines.join("\n"),
  };
}

function readCatalogReview(): CatalogReview {
  try {
    const path = join(process.env.XDG_STATE_HOME || join(homedir(), ".local/state"), "pi-model-discovery/catalog.json");
    const raw = readFileSync(path, "utf8");
    if (raw.length > 4 * 1024 * 1024) throw new Error("Oversized catalog");
    return catalogReview(readModelModePolicy(), JSON.parse(raw));
  } catch {
    return { status: "models:check unavailable", details: "No valid discovery state or policy. Inspect pi-model-discovery status and systemctl --user status pi-model-discovery.service." };
  }
}

function updateCatalogStatus(ctx: ExtensionContext): void {
  const { status } = readCatalogReview();
  ctx.ui.setStatus("model-review", status ? ctx.ui.theme.fg("warning", status) : undefined);
}

function activeMode(policy: ModelModePolicy, ctx: ExtensionContext, thinkingLevel: ThinkingLevel): ModelMode | undefined {
  if (!ctx.model) return undefined;
  return policy.modes.find(
    (mode) =>
      mode.provider === ctx.model?.provider &&
      mode.model === ctx.model.id &&
      mode.thinkingLevel === thinkingLevel,
  );
}

function updateStatus(pi: ExtensionAPI, ctx: ExtensionContext): void {
  try {
    const mode = activeMode(readModelModePolicy(), ctx, pi.getThinkingLevel());
    ctx.ui.setStatus("model-mode", mode ? ctx.ui.theme.fg("accent", `mode:${mode.id}`) : undefined);
  } catch {
    ctx.ui.setStatus("model-mode", undefined);
  }
}

async function applyMode(pi: ExtensionAPI, ctx: ExtensionContext, mode: ModelMode): Promise<boolean> {
  const model = ctx.modelRegistry.find(mode.provider, mode.model);
  if (!model) {
    ctx.ui.notify(`${mode.label}: ${mode.provider}/${mode.model} is not available`, "error");
    return false;
  }

  const previousModel = ctx.model;
  const previousThinkingLevel = pi.getThinkingLevel();
  const authenticated = await pi.setModel(model);
  if (!authenticated) {
    ctx.ui.notify(`${mode.label}: ${mode.provider}/${mode.model} is not authenticated`, "error");
    return false;
  }

  pi.setThinkingLevel(mode.thinkingLevel);
  if (pi.getThinkingLevel() !== mode.thinkingLevel) {
    if (previousModel) await pi.setModel(previousModel);
    pi.setThinkingLevel(previousThinkingLevel);
    ctx.ui.notify(`${mode.label}: ${mode.thinkingLevel} reasoning is not supported`, "error");
    updateStatus(pi, ctx);
    return false;
  }

  updateStatus(pi, ctx);
  ctx.ui.notify(`${mode.label} · ${model.name} · ${mode.thinkingLevel}`, "info");
  return true;
}

// Never accept the legacy Ctrl+M byte (\r): it is also ordinary Enter.
// Accept only explicit Kitty/CSI-u press events or xterm modifyOtherKeys.
export function isExplicitModeKey(data: string): boolean {
  return /^\x1b\[109(?::\d*(?::\d*)?)?;5(?::1)?u$/.test(data) || data === "\x1b[27;5;109~";
}

export default function modelModesExtension(pi: ExtensionAPI) {
  let removeInputHandler: (() => void) | undefined;
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let pickerOpen = false;

  async function chooseMode(args: string, ctx: ExtensionContext): Promise<void> {
    if (pickerOpen) return;
    pickerOpen = true;
    try {
      await chooseModeInner(args, ctx);
    } finally {
      pickerOpen = false;
    }
  }

  async function chooseModeInner(args: string, ctx: ExtensionContext): Promise<void> {
    let policy: ModelModePolicy;
    try {
      policy = readModelModePolicy();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      ctx.ui.notify(`Cannot load model modes: ${message}`, "error");
      return;
    }

    let selectedId = args.trim().toLowerCase();
    if (!selectedId) {
      const current = activeMode(policy, ctx, pi.getThinkingLevel());
      const choices = policy.modes.map((mode) => {
        const marker = mode.id === current?.id ? " ✓" : "";
        return `${mode.label}${marker} — ${mode.description} · ${mode.model} / ${mode.thinkingLevel}`;
      });
      const initialIndex = Math.max(0, policy.modes.findIndex((mode) => mode.id === current?.id));
      const selected = await ctx.ui.select("Choose model mode", choices, { initialIndex });
      if (!selected) return;
      selectedId = policy.modes[choices.indexOf(selected)]?.id ?? "";
    }

    const mode = policy.modes.find((candidate) => candidate.id === selectedId);
    if (!mode) {
      ctx.ui.notify(`Unknown mode "${selectedId}". Choose: ${policy.modes.map(({ id }) => id).join(", ")}`, "error");
      return;
    }

    await applyMode(pi, ctx, mode);
  }

  pi.registerCommand("mode", {
    description: "Choose Fast, Normal, Deep, or Extreme model mode",
    getArgumentCompletions: (prefix) => {
      try {
        const normalized = prefix.toLowerCase();
        const matches = readModelModePolicy().modes.filter((mode) => mode.id.startsWith(normalized));
        return matches.length ? matches.map((mode) => ({ value: mode.id, label: mode.label })) : null;
      } catch {
        return null;
      }
    },
    handler: chooseMode,
  });

  pi.registerCommand("mode-review", {
    description: "Show read-only model discovery results and review warnings",
    handler: async (_args, ctx) => {
      updateCatalogStatus(ctx);
      ctx.ui.notify(readCatalogReview().details, "info");
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    removeInputHandler?.();
    clearInterval(refreshTimer);
    updateStatus(pi, ctx);
    updateCatalogStatus(ctx);
    if (ctx.mode !== "tui") return;
    // Local state reads only: network discovery belongs to the systemd timer.
    refreshTimer = setInterval(() => updateCatalogStatus(ctx), 60000);
    refreshTimer.unref();
    removeInputHandler = ctx.ui.onTerminalInput((data) => {
      if (!isExplicitModeKey(data)) return;
      if (!pickerOpen && ctx.isIdle()) {
        void chooseMode("", ctx)
          .catch(() => ctx.ui.notify("Could not open model modes. Use /mode to retry.", "error"));
      }
      return { consume: true };
    });
  });
  pi.on("session_shutdown", async () => {
    removeInputHandler?.();
    removeInputHandler = undefined;
    clearInterval(refreshTimer);
    refreshTimer = undefined;
  });
  pi.on("model_select", async (_event, ctx) => updateStatus(pi, ctx));
  pi.on("thinking_level_select", async (_event, ctx) => updateStatus(pi, ctx));
}
