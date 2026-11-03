import { readFileSync } from "node:fs";
import { join } from "node:path";
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
      const selected = await ctx.ui.select("Choose model mode", choices);
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

  pi.on("session_start", async (_event, ctx) => {
    removeInputHandler?.();
    updateStatus(pi, ctx);
    if (ctx.mode !== "tui") return;
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
  });
  pi.on("model_select", async (_event, ctx) => updateStatus(pi, ctx));
  pi.on("thinking_level_select", async (_event, ctx) => updateStatus(pi, ctx));
}
