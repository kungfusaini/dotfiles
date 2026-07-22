import { createHash } from "node:crypto";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

function StringEnum<T extends readonly string[]>(values: T, options?: { description?: string; default?: T[number] }) {
  return Type.Unsafe<T[number]>({
    type: "string",
    enum: values as any,
    ...(options?.description ? { description: options.description } : {}),
    ...(options?.default ? { default: options.default } : {}),
  });
}

const MAX_PAYLOADS = 50;
const DEFAULT_MAX_CHARS = 4000;
const MAX_MAX_CHARS = 50_000;

type View =
  | "summary"
  | "system"
  | "messages"
  | "tools"
  | "context_files"
  | "provider_payload"
  | "cache"
  | "cache_diff";

type Truncated<T> = {
  value: T;
  truncated: boolean;
  originalChars: number;
  returnedChars: number;
};

type PromptSnapshot = {
  timestamp: number;
  systemPrompt: string;
  systemPromptOptions: any;
  fingerprint: string;
  length: number;
};

type ContextSnapshot = {
  timestamp: number;
  messages: any[];
  fingerprint: string;
  count: number;
};

type PayloadSnapshot = {
  index: number;
  timestamp: number;
  payload: unknown;
  summary: Record<string, unknown>;
  fingerprint: string;
  componentFingerprints: Record<string, string | null>;
  cacheMarkers: CacheMarkerSummary;
};

type CacheMarkerSummary = {
  count: number;
  locations: string[];
};

const Params = Type.Object({
  view: Type.Optional(StringEnum([
    "summary",
    "system",
    "messages",
    "tools",
    "context_files",
    "provider_payload",
    "cache",
    "cache_diff",
  ] as const, { description: "Which factual context view to return." })),
  includeContent: Type.Optional(Type.Boolean({ description: "Include full or larger raw content where available. Defaults to false." })),
  maxChars: Type.Optional(Type.Number({ description: "Maximum characters per included content field. Defaults to 4000; capped at 50000." })),
  payloadIndex: Type.Optional(Type.Union([
    Type.Number({ description: "1-based provider payload index from this session's in-memory ring buffer." }),
    Type.Literal("latest"),
  ], { description: "Provider payload snapshot to inspect. Defaults to latest." })),
  compareWith: Type.Optional(Type.Union([
    Type.Number({ description: "1-based provider payload index to compare against." }),
    Type.Literal("previous"),
  ], { description: "Provider payload snapshot to compare with for cache_diff. Defaults to previous." })),
});

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? "undefined";
  } catch (error) {
    return `[unserializable: ${error instanceof Error ? error.message : String(error)}]`;
  }
}

function stableStringify(value: unknown): string {
  const seen = new WeakSet<object>();
  const normalize = (item: unknown): unknown => {
    if (item === null || typeof item !== "object") return item;
    if (seen.has(item as object)) return "[Circular]";
    seen.add(item as object);
    if (Array.isArray(item)) return item.map(normalize);
    const record = item as Record<string, unknown>;
    return Object.keys(record).sort().reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = normalize(record[key]);
      return acc;
    }, {});
  };
  try {
    return JSON.stringify(normalize(value)) ?? "undefined";
  } catch {
    return safeJson(value);
  }
}

function fingerprint(value: unknown): string {
  return createHash("sha256").update(stableStringify(value)).digest("hex").slice(0, 16);
}

function clampMaxChars(value: unknown): number {
  const n = typeof value === "number" && Number.isFinite(value) ? Math.floor(value) : DEFAULT_MAX_CHARS;
  return Math.max(0, Math.min(MAX_MAX_CHARS, n));
}

function truncateText(text: string, maxChars: number): Truncated<string> {
  if (text.length <= maxChars) {
    return { value: text, truncated: false, originalChars: text.length, returnedChars: text.length };
  }
  return { value: text.slice(0, maxChars), truncated: true, originalChars: text.length, returnedChars: maxChars };
}

function includeMaybe(value: unknown, includeContent: boolean, maxChars: number): unknown {
  const text = typeof value === "string" ? value : safeJson(value);
  const truncated = truncateText(text, maxChars);
  if (includeContent) return truncated;
  return {
    preview: truncateText(text, Math.min(500, maxChars)),
    fingerprint: fingerprint(value),
    chars: text.length,
  };
}

function textStats(value: unknown) {
  const text = typeof value === "string" ? value : safeJson(value);
  return {
    chars: text.length,
    lines: text.length ? text.split("\n").length : 0,
    fingerprint: fingerprint(value),
  };
}

function contentSummary(content: unknown, includeContent: boolean, maxChars: number): Record<string, unknown> {
  const out: Record<string, unknown> = {
    kind: Array.isArray(content) ? "blocks" : typeof content,
    fingerprint: fingerprint(content),
    chars: typeof content === "string" ? content.length : safeJson(content).length,
  };
  if (Array.isArray(content)) {
    out.blockTypes = content.map((block: any) => block?.type ?? typeof block);
    out.textChars = content.reduce((sum, block: any) => sum + (block?.type === "text" && typeof block.text === "string" ? block.text.length : 0), 0);
    out.toolCalls = content
      .filter((block: any) => block?.type === "toolCall")
      .map((block: any) => ({ id: block.id, name: block.name, argumentFingerprint: fingerprint(block.arguments) }));
    if (includeContent) out.content = includeMaybe(content, true, maxChars);
  } else if (typeof content === "string") {
    out.text = includeMaybe(content, includeContent, maxChars);
  } else if (includeContent) {
    out.content = includeMaybe(content, true, maxChars);
  }
  return out;
}

function messageSummary(message: any, index: number, includeContent: boolean, maxChars: number) {
  const role = message?.role ?? "unknown";
  const out: Record<string, unknown> = {
    index,
    role,
    timestamp: message?.timestamp,
    fingerprint: fingerprint(message),
  };
  if (role === "assistant") {
    out.provider = message.provider;
    out.model = message.model;
    out.stopReason = message.stopReason;
    out.usage = message.usage;
  }
  if (role === "toolResult") {
    out.toolCallId = message.toolCallId;
    out.toolName = message.toolName;
    out.isError = message.isError;
  }
  if (role === "bashExecution") {
    out.command = includeMaybe(message.command ?? "", includeContent, maxChars);
    out.exitCode = message.exitCode;
    out.cancelled = message.cancelled;
    out.truncated = message.truncated;
    out.excludeFromContext = message.excludeFromContext;
  }
  if ("content" in (message ?? {})) out.content = contentSummary(message.content, includeContent, maxChars);
  if ("summary" in (message ?? {})) out.summary = includeMaybe(message.summary, includeContent, maxChars);
  return out;
}

function countBy<T extends string>(items: T[]): Record<T, number> {
  return items.reduce((acc, item) => {
    acc[item] = (acc[item] ?? 0) + 1;
    return acc;
  }, {} as Record<T, number>);
}

function summarizePayload(payload: any): Record<string, unknown> {
  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  const tools = Array.isArray(payload?.tools) ? payload.tools : Array.isArray(payload?.functions) ? payload.functions : [];
  const system = payload?.system ?? payload?.instructions ?? payload?.developer;
  return {
    topLevelKeys: payload && typeof payload === "object" ? Object.keys(payload).sort() : [],
    model: payload?.model,
    messageCount: messages.length,
    messageRoles: countBy(messages.map((m: any) => String(m?.role ?? "unknown"))),
    toolCount: tools.length,
    toolNames: tools.map((t: any) => t?.name ?? t?.function?.name).filter(Boolean),
    system: system === undefined ? undefined : textStats(system),
    chars: safeJson(payload).length,
  };
}

function componentFingerprints(payload: any): Record<string, string | null> {
  const messages = Array.isArray(payload?.messages) ? payload.messages : null;
  const prefixMessages = messages ? messages.slice(0, Math.max(0, messages.length - 1)) : null;
  return {
    full: fingerprint(payload),
    system: payload?.system !== undefined ? fingerprint(payload.system) : payload?.instructions !== undefined ? fingerprint(payload.instructions) : null,
    tools: payload?.tools !== undefined ? fingerprint(payload.tools) : payload?.functions !== undefined ? fingerprint(payload.functions) : null,
    messages: messages ? fingerprint(messages) : null,
    messagePrefix: prefixMessages ? fingerprint(prefixMessages) : null,
  };
}

function findCacheMarkers(value: unknown, path = "$", found: string[] = []): string[] {
  if (value === null || typeof value !== "object") return found;
  if (Array.isArray(value)) {
    value.forEach((item, index) => findCacheMarkers(item, `${path}[${index}]`, found));
    return found;
  }
  const record = value as Record<string, unknown>;
  for (const [key, child] of Object.entries(record)) {
    const childPath = `${path}.${key}`;
    if (key === "cache_control" || key === "prompt_cache_retention" || key === "cacheControl") found.push(childPath);
    findCacheMarkers(child, childPath, found);
  }
  return found;
}

function cacheMarkers(value: unknown): CacheMarkerSummary {
  const locations = findCacheMarkers(value);
  return { count: locations.length, locations: locations.slice(0, 100) };
}

function usageOf(message: any) {
  const usage = message?.usage;
  if (!usage || typeof usage !== "object") return undefined;
  const input = Number(usage.input ?? 0);
  const output = Number(usage.output ?? 0);
  const cacheRead = Number(usage.cacheRead ?? 0);
  const cacheWrite = Number(usage.cacheWrite ?? 0);
  const denominator = input + cacheRead;
  return {
    input,
    output,
    cacheRead,
    cacheWrite,
    totalTokens: Number(usage.totalTokens ?? input + output + cacheRead + cacheWrite),
    cost: usage.cost,
    cacheHitRate: denominator > 0 ? cacheRead / denominator : null,
  };
}

function cacheHistory(ctx: ExtensionContext, payloads: PayloadSnapshot[]) {
  const branch = ctx.sessionManager.getBranch();
  const assistantMessages = branch
    .map((entry: any) => entry?.message)
    .filter((message: any) => message?.role === "assistant" && usageOf(message));
  const calls = assistantMessages.map((message: any, index: number) => ({
    index: index + 1,
    timestamp: message.timestamp,
    provider: message.provider,
    model: message.model,
    stopReason: message.stopReason,
    usage: usageOf(message),
    payloadIndex: payloads[index]?.index ?? null,
    payloadFingerprint: payloads[index]?.fingerprint ?? null,
  }));
  const totals = calls.reduce((acc, call: any) => {
    const usage = call.usage;
    acc.input += usage.input;
    acc.output += usage.output;
    acc.cacheRead += usage.cacheRead;
    acc.cacheWrite += usage.cacheWrite;
    acc.totalTokens += usage.totalTokens;
    return acc;
  }, { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0 });
  return { calls, totals, latest: calls[calls.length - 1] ?? null };
}

function resolvePayload(payloads: PayloadSnapshot[], selector: unknown): PayloadSnapshot | undefined {
  if (!payloads.length) return undefined;
  if (selector === undefined || selector === "latest") return payloads[payloads.length - 1];
  if (typeof selector === "number" && Number.isInteger(selector)) return payloads.find(p => p.index === selector) ?? payloads[selector - 1];
  return undefined;
}

function payloadLengths(payload: any) {
  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  const tools = Array.isArray(payload?.tools) ? payload.tools : Array.isArray(payload?.functions) ? payload.functions : [];
  const system = payload?.system ?? payload?.instructions ?? payload?.developer;
  return {
    systemChars: system === undefined ? 0 : safeJson(system).length,
    toolCount: tools.length,
    toolsChars: safeJson(tools).length,
    messageCount: messages.length,
    messagesChars: safeJson(messages).length,
    fullChars: safeJson(payload).length,
  };
}

function diffPayloads(left: PayloadSnapshot, right: PayloadSnapshot) {
  const leftLengths = payloadLengths(left.payload as any);
  const rightLengths = payloadLengths(right.payload as any);
  const lengthDelta = Object.fromEntries(Object.keys(rightLengths).map((key) => [
    key,
    (rightLengths as any)[key] - (leftLengths as any)[key],
  ]));
  return {
    from: { index: left.index, timestamp: left.timestamp, fingerprint: left.fingerprint, componentFingerprints: left.componentFingerprints, lengths: leftLengths, cacheMarkers: left.cacheMarkers },
    to: { index: right.index, timestamp: right.timestamp, fingerprint: right.fingerprint, componentFingerprints: right.componentFingerprints, lengths: rightLengths, cacheMarkers: right.cacheMarkers },
    changed: {
      full: left.fingerprint !== right.fingerprint,
      system: left.componentFingerprints.system !== right.componentFingerprints.system,
      tools: left.componentFingerprints.tools !== right.componentFingerprints.tools,
      messages: left.componentFingerprints.messages !== right.componentFingerprints.messages,
      messagePrefix: left.componentFingerprints.messagePrefix !== right.componentFingerprints.messagePrefix,
    },
    lengthDelta,
  };
}

function contextFilesFromOptions(options: any, includeContent: boolean, maxChars: number) {
  return (options?.contextFiles ?? []).map((file: any) => ({
    path: file.path,
    ...textStats(file.content ?? ""),
    content: includeContent ? includeMaybe(file.content ?? "", true, maxChars) : undefined,
  }));
}

function skillsFromOptions(options: any, includeContent: boolean, maxChars: number) {
  return (options?.skills ?? []).map((skill: any) => {
    const body = skill.content ?? skill.body ?? skill.text ?? "";
    return {
      name: skill.name,
      path: skill.path,
      disableModelInvocation: skill.disableModelInvocation,
      ...textStats(body),
      content: includeContent ? includeMaybe(body, true, maxChars) : undefined,
    };
  });
}

function buildDetails(pi: ExtensionAPI, ctx: ExtensionContext, view: View, includeContent: boolean, maxChars: number, payloadIndex: unknown, compareWith: unknown, state: {
  prompt?: PromptSnapshot;
  context?: ContextSnapshot;
  payloads: PayloadSnapshot[];
}) {
  const model = ctx.model;
  const usage = ctx.getContextUsage();
  const activeToolNames = new Set(pi.getActiveTools());
  const allTools = pi.getAllTools();
  const activeTools = allTools.filter(tool => activeToolNames.has(tool.name));
  const branch = ctx.sessionManager.getBranch();
  const contextEntries = ctx.sessionManager.buildContextEntries();
  const sessionContext = ctx.sessionManager.buildSessionContext?.();
  const messages = state.context?.messages ?? sessionContext?.messages ?? [];
  const prompt = state.prompt;

  if (view === "summary") {
    const roles = messages.map((m: any) => String(m?.role ?? "unknown"));
    const entryTypes = contextEntries.map((e: any) => String(e?.type ?? "unknown"));
    return {
      view,
      cwd: ctx.cwd,
      session: { id: ctx.sessionManager.getSessionId(), file: ctx.sessionManager.getSessionFile(), leafId: ctx.sessionManager.getLeafId() },
      model: model ? { provider: model.provider, id: model.id, contextWindow: model.contextWindow, maxTokens: model.maxTokens, reasoning: model.reasoning } : null,
      contextUsage: usage ?? null,
      contextEntries: { count: contextEntries.length, byType: countBy(entryTypes) },
      messages: { count: messages.length, byRole: countBy(roles), latestFingerprint: state.context?.fingerprint ?? fingerprint(messages) },
      system: prompt ? { timestamp: prompt.timestamp, chars: prompt.length, fingerprint: prompt.fingerprint } : null,
      contextFiles: contextFilesFromOptions(prompt?.systemPromptOptions, false, maxChars).map((f: any) => ({ path: f.path, chars: f.chars, fingerprint: f.fingerprint })),
      skills: skillsFromOptions(prompt?.systemPromptOptions, false, maxChars).map((s: any) => ({ name: s.name, path: s.path, chars: s.chars, fingerprint: s.fingerprint })),
      activeTools: activeTools.map(tool => tool.name),
      providerPayloads: { buffered: state.payloads.length, max: MAX_PAYLOADS, latest: state.payloads[state.payloads.length - 1] ? { index: state.payloads[state.payloads.length - 1].index, fingerprint: state.payloads[state.payloads.length - 1].fingerprint, componentFingerprints: state.payloads[state.payloads.length - 1].componentFingerprints, cacheMarkers: state.payloads[state.payloads.length - 1].cacheMarkers } : null },
      cache: cacheHistory(ctx, state.payloads),
    };
  }

  if (view === "system") {
    return {
      view,
      captured: prompt ? { timestamp: prompt.timestamp, chars: prompt.length, fingerprint: prompt.fingerprint } : null,
      systemPrompt: prompt ? includeMaybe(prompt.systemPrompt, includeContent, maxChars) : null,
      options: prompt ? {
        cwd: prompt.systemPromptOptions?.cwd,
        customPrompt: prompt.systemPromptOptions?.customPrompt ? includeMaybe(prompt.systemPromptOptions.customPrompt, includeContent, maxChars) : null,
        appendSystemPrompt: prompt.systemPromptOptions?.appendSystemPrompt ? includeMaybe(prompt.systemPromptOptions.appendSystemPrompt, includeContent, maxChars) : null,
        contextFileCount: prompt.systemPromptOptions?.contextFiles?.length ?? 0,
        skillCount: prompt.systemPromptOptions?.skills?.length ?? 0,
        selectedTools: prompt.systemPromptOptions?.selectedTools,
        toolSnippetCount: Array.isArray(prompt.systemPromptOptions?.toolSnippets) ? prompt.systemPromptOptions.toolSnippets.length : undefined,
        promptGuidelineCount: Array.isArray(prompt.systemPromptOptions?.promptGuidelines) ? prompt.systemPromptOptions.promptGuidelines.length : undefined,
      } : null,
      contextFiles: contextFilesFromOptions(prompt?.systemPromptOptions, includeContent, maxChars),
      skills: skillsFromOptions(prompt?.systemPromptOptions, includeContent, maxChars),
    };
  }

  if (view === "messages") {
    return {
      view,
      source: state.context ? "context-event" : "sessionManager.buildSessionContext",
      count: messages.length,
      messages: messages.map((message: any, index: number) => messageSummary(message, index, includeContent, maxChars)),
    };
  }

  if (view === "tools") {
    return {
      view,
      activeToolCount: activeToolNames.size,
      allToolCount: allTools.length,
      tools: allTools.map((tool: any) => ({
        name: tool.name,
        label: tool.label,
        active: activeToolNames.has(tool.name),
        description: tool.description,
        promptSnippet: tool.promptSnippet,
        promptGuidelines: tool.promptGuidelines,
        parameters: includeContent ? includeMaybe(tool.parameters, true, maxChars) : { fingerprint: fingerprint(tool.parameters), topLevelKeys: tool.parameters && typeof tool.parameters === "object" ? Object.keys(tool.parameters) : [] },
      })),
    };
  }

  if (view === "context_files") {
    return { view, count: prompt?.systemPromptOptions?.contextFiles?.length ?? 0, contextFiles: contextFilesFromOptions(prompt?.systemPromptOptions, includeContent, maxChars) };
  }

  if (view === "provider_payload") {
    const selected = resolvePayload(state.payloads, payloadIndex);
    return {
      view,
      buffered: state.payloads.length,
      selected: selected ? {
        index: selected.index,
        timestamp: selected.timestamp,
        fingerprint: selected.fingerprint,
        componentFingerprints: selected.componentFingerprints,
        summary: selected.summary,
        cacheMarkers: selected.cacheMarkers,
        payload: includeMaybe(selected.payload, includeContent, maxChars),
      } : null,
    };
  }

  if (view === "cache") {
    return { view, providerPayloads: state.payloads.map(p => ({ index: p.index, timestamp: p.timestamp, fingerprint: p.fingerprint, componentFingerprints: p.componentFingerprints, summary: p.summary, cacheMarkers: p.cacheMarkers })), ...cacheHistory(ctx, state.payloads) };
  }

  if (view === "cache_diff") {
    const right = resolvePayload(state.payloads, payloadIndex);
    const left = compareWith === undefined || compareWith === "previous"
      ? state.payloads[state.payloads.findIndex(p => p.index === right?.index) - 1]
      : resolvePayload(state.payloads, compareWith);
    return { view, diff: left && right ? diffPayloads(left, right) : null, buffered: state.payloads.length };
  }

  return { view, error: "unknown view" };
}

function textResult(details: unknown) {
  const text = safeJson(details);
  return {
    content: [{ type: "text" as const, text: text.length > 12_000 ? `${text.slice(0, 12_000)}\n…(tool text truncated; inspect details for full structured result)` : text }],
    details,
  };
}

export default function inspectContextExtension(pi: ExtensionAPI) {
  const state: { prompt?: PromptSnapshot; context?: ContextSnapshot; payloads: PayloadSnapshot[]; nextPayloadIndex: number } = {
    payloads: [],
    nextPayloadIndex: 1,
  };

  function resetSessionState() {
    state.prompt = undefined;
    state.context = undefined;
    state.payloads = [];
    state.nextPayloadIndex = 1;
  }

  pi.on("session_start", () => resetSessionState());
  pi.on("session_tree", () => {
    state.context = undefined;
  });

  pi.on("before_agent_start", (event) => {
    state.prompt = {
      timestamp: Date.now(),
      systemPrompt: event.systemPrompt,
      systemPromptOptions: event.systemPromptOptions,
      fingerprint: fingerprint(event.systemPrompt),
      length: event.systemPrompt.length,
    };
  });

  pi.on("context", (event) => {
    state.context = {
      timestamp: Date.now(),
      messages: event.messages,
      fingerprint: fingerprint(event.messages),
      count: event.messages.length,
    };
  });

  pi.on("before_provider_request", (event) => {
    const payload = event.payload;
    const snapshot: PayloadSnapshot = {
      index: state.nextPayloadIndex++,
      timestamp: Date.now(),
      payload,
      summary: summarizePayload(payload as any),
      fingerprint: fingerprint(payload),
      componentFingerprints: componentFingerprints(payload as any),
      cacheMarkers: cacheMarkers(payload),
    };
    state.payloads.push(snapshot);
    if (state.payloads.length > MAX_PAYLOADS) state.payloads.shift();
    // Intentionally return nothing: this extension must never mutate provider payloads.
  });

  pi.registerTool({
    name: "inspect_context",
    label: "Inspect Context",
    description: "Inspect the current model context and prompt-cache evidence as factual structured data. This can expose sensitive prompt, message, and tool-result data to the agent. It does not mutate files or provider requests.",
    promptSnippet: "Inspect current model context and prompt-cache evidence as factual structured data.",
    promptGuidelines: [
      "Use inspect_context when you need factual visibility into the current model context, loaded instructions, active tools, provider payload shape, or prompt-cache usage evidence.",
      "inspect_context is read-only and returns data without judging quality; decide what to do with the data yourself.",
      "Prefer inspect_context summary first, then request narrower views such as system, messages, provider_payload, cache, or cache_diff when needed.",
    ],
    parameters: Params,
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const view = (params.view ?? "summary") as View;
      const includeContent = params.includeContent === true;
      const maxChars = clampMaxChars(params.maxChars);
      const details = buildDetails(pi, ctx, view, includeContent, maxChars, params.payloadIndex, params.compareWith, state);
      return textResult(details);
    },
  });
}
