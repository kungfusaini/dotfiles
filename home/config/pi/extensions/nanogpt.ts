import { Type, type Usage } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFile } from "node:fs/promises";

const DEFAULT_BASE_URL = "https://api.nano-gpt.com/api/subscription/v1";
const DEFAULT_SECRET_FILE = "/run/secrets/nanogpt-api-key";
const WEBSITE_DETAILS_URL = "https://nano-gpt.com/api/explore/text-model-details";
const CACHE_TTL_MS = 15 * 60 * 1000;
const MAX_RESULT_MODELS = 25;

type Capabilities = {
  reasoning: boolean;
  toolCalling: boolean;
  structuredOutput: boolean;
  vision: boolean;
  videoInput: boolean;
  audioInput: boolean;
  pdfUpload: boolean;
};

type CatalogModel = {
  id: string;
  name: string;
  description: string;
  provider: string | null;
  category: string | null;
  contextLength: number | null;
  maxOutputTokens: number | null;
  capabilities: Capabilities;
  pricing: unknown;
};

type ModelMetrics = {
  intelligence: number | null;
  coding: number | null;
  scicode: number | null;
  terminalbench: number | null;
  hle: number | null;
  gpqa: number | null;
  avgTps: number | null;
  avgTtftMs: number | null;
  speedTokensPerSecond: number | null;
  lastUpdated: string | null;
};

type RankedModel = CatalogModel & {
  score: number;
  metrics: ModelMetrics;
  reasons: string[];
};

type CacheEntry<T> = { value: T; expiresAt: number };

let catalogCache: CacheEntry<CatalogModel[]> | undefined;
const metricsCache = new Map<string, CacheEntry<ModelMetrics>>();

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function redact(value: unknown): string {
  return String(value ?? "")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9._:-]{12,}\b/gi, "[redacted-token]")
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi, "[redacted-token]")
    .slice(0, 1200);
}

function baseUrl(): string {
  return (process.env.NANOGPT_SUBSCRIPTION_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");
}

function apiV1BaseUrl(): string {
  if (process.env.NANOGPT_API_BASE_URL) return process.env.NANOGPT_API_BASE_URL.replace(/\/+$/, "");
  return baseUrl().replace(/\/subscription\/v1$/, "/v1");
}

async function apiKey(): Promise<string> {
  const fromEnvironment = process.env.NANOGPT_API_KEY?.trim();
  if (fromEnvironment) return validateApiKey(fromEnvironment);

  const secretFile = process.env.NANOGPT_API_KEY_FILE || DEFAULT_SECRET_FILE;
  try {
    return validateApiKey((await readFile(secretFile, "utf8")).trim());
  } catch (error) {
    throw new Error(
      `NanoGPT API key is unavailable. Configure the sops-nix secret at ${secretFile}. ${redact(error)}`,
    );
  }
}

function validateApiKey(key: string): string {
  if (!key || key === "REPLACE_ME" || key === "CHANGE_ME") {
    throw new Error("NanoGPT API key has not been configured yet");
  }
  if (!(key.startsWith("sk-nano-") || /^[0-9a-f-]{32,}$/i.test(key))) {
    throw new Error("NanoGPT API key has an unexpected format");
  }
  return key;
}

function requestSignal(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

async function fetchJson(
  url: string,
  key: string,
  signal: AbortSignal | undefined,
  init: RequestInit = {},
  timeoutMs = 30_000,
): Promise<any> {
  const response = await fetch(url, {
    ...init,
    signal: requestSignal(signal, timeoutMs),
    headers: {
      Authorization: `Bearer ${key}`,
      Accept: "application/json",
      "User-Agent": "pi-nanogpt/1.0",
      ...init.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`NanoGPT HTTP ${response.status}: ${redact(body)}`);
  }
  return response.json();
}

function normalizeModel(raw: any): CatalogModel | undefined {
  if (!raw || typeof raw.id !== "string" || !raw.id) return undefined;
  const capabilities = raw.capabilities || {};
  return {
    id: raw.id,
    name: typeof raw.name === "string" && raw.name ? raw.name : raw.id,
    description: typeof raw.description === "string" ? raw.description : "",
    provider: typeof raw.owned_by === "string" ? raw.owned_by : null,
    category: typeof raw.category === "string" ? raw.category : null,
    contextLength: finite(raw.context_length),
    maxOutputTokens: finite(raw.max_output_tokens),
    capabilities: {
      reasoning: Boolean(capabilities.reasoning),
      toolCalling: Boolean(capabilities.tool_calling || capabilities.parallel_tool_calls),
      structuredOutput: Boolean(capabilities.structured_output),
      vision: Boolean(capabilities.vision),
      videoInput: Boolean(capabilities.video_input),
      audioInput: Boolean(capabilities.audio_input),
      pdfUpload: Boolean(capabilities.pdf_upload),
    },
    pricing: raw.pricing ?? null,
  };
}

async function getCatalog(key: string, signal?: AbortSignal, force = false): Promise<CatalogModel[]> {
  if (!force && catalogCache && catalogCache.expiresAt > Date.now()) return catalogCache.value;
  const payload = await fetchJson(`${baseUrl()}/models?detailed=true`, key, signal);
  const models = (Array.isArray(payload?.data) ? payload.data : [])
    .map(normalizeModel)
    .filter((model: CatalogModel | undefined): model is CatalogModel => Boolean(model));
  if (!models.length) throw new Error("NanoGPT returned an empty subscription model catalogue");
  catalogCache = { value: models, expiresAt: Date.now() + CACHE_TTL_MS };
  return models;
}

function emptyMetrics(): ModelMetrics {
  return {
    intelligence: null,
    coding: null,
    scicode: null,
    terminalbench: null,
    hle: null,
    gpqa: null,
    avgTps: null,
    avgTtftMs: null,
    speedTokensPerSecond: null,
    lastUpdated: null,
  };
}

function normalizeMetrics(raw: any): ModelMetrics {
  const benchmark = raw?.benchmarkData || {};
  return {
    intelligence: finite(benchmark.intelligence),
    coding: finite(benchmark.coding),
    scicode: finite(benchmark.scicode),
    terminalbench: finite(benchmark.terminalbenchV4 ?? benchmark.terminalbenchHard),
    hle: finite(benchmark.hle),
    gpqa: finite(benchmark.gpqa),
    avgTps: finite(raw?.avgTps),
    avgTtftMs: finite(raw?.avgTtftMs),
    speedTokensPerSecond: finite(benchmark.speedTokensPerSecond),
    lastUpdated: typeof benchmark.lastUpdated === "string" ? benchmark.lastUpdated : null,
  };
}

async function getMetrics(ids: string[], key: string, signal?: AbortSignal): Promise<Map<string, ModelMetrics>> {
  const result = new Map<string, ModelMetrics>();
  const missing: string[] = [];
  for (const id of ids) {
    const cached = metricsCache.get(id);
    if (cached && cached.expiresAt > Date.now()) result.set(id, cached.value);
    else missing.push(id);
  }

  for (let index = 0; index < missing.length; index += 50) {
    const batch = missing.slice(index, index + 50);
    const params = new URLSearchParams({ model_ids: batch.join(",") });
    try {
      const payload = await fetchJson(`${WEBSITE_DETAILS_URL}?${params}`, key, signal);
      for (const id of batch) {
        const metrics = normalizeMetrics(payload?.models?.[id]);
        metricsCache.set(id, { value: metrics, expiresAt: Date.now() + CACHE_TTL_MS });
        result.set(id, metrics);
      }
    } catch {
      // Website metrics are an optional, undocumented enrichment. Capability-only
      // ranking remains available when this endpoint changes or is unavailable.
      for (const id of batch) {
        const metrics = emptyMetrics();
        metricsCache.set(id, { value: metrics, expiresAt: Date.now() + 60_000 });
        result.set(id, metrics);
      }
    }
  }
  return result;
}

function isDecisionModel(model: CatalogModel): boolean {
  return model.category?.toLowerCase() === "decisions";
}

function supportsPlainChat(model: CatalogModel): boolean {
  return model.maxOutputTokens !== 0 && !isDecisionModel(model);
}

function matchesRequirements(model: CatalogModel, params: any): boolean {
  if (params.requireReasoning && !model.capabilities.reasoning) return false;
  if (params.requireTools && !model.capabilities.toolCalling) return false;
  if (params.requireVision && !model.capabilities.vision) return false;
  if (params.requireStructuredOutput && !model.capabilities.structuredOutput) return false;
  if (params.minContext && (model.contextLength ?? 0) < params.minContext) return false;
  if (params.query) {
    const query = String(params.query).toLowerCase();
    const haystack = `${model.id} ${model.name} ${model.provider ?? ""} ${model.description}`.toLowerCase();
    if (!query.split(/\s+/).every((term) => haystack.includes(term))) return false;
  }
  return true;
}

function normalize(values: Array<number | null>, value: number | null, invert = false): number | null {
  if (value === null) return null;
  const present = values.filter((item): item is number => item !== null);
  if (!present.length) return null;
  const min = Math.min(...present);
  const max = Math.max(...present);
  const normalized = max === min ? 0.5 : (value - min) / (max - min);
  return invert ? 1 - normalized : normalized;
}

function rankModels(models: CatalogModel[], metrics: Map<string, ModelMetrics>, profile: string, task: string): RankedModel[] {
  const allMetrics = models.map((model) => metrics.get(model.id) ?? emptyMetrics());
  const taskTerms = task.toLowerCase().split(/[^a-z0-9]+/).filter((term) => term.length >= 4);

  return models.map((model, index) => {
    const metric = allMetrics[index];
    const components: Array<{ value: number | null; weight: number; reason: string }> = [];
    const field = (name: keyof ModelMetrics, weight: number, reason: string, invert = false) => {
      components.push({
        value: normalize(allMetrics.map((item) => typeof item[name] === "number" ? item[name] as number : null), typeof metric[name] === "number" ? metric[name] as number : null, invert),
        weight,
        reason,
      });
    };

    if (profile === "coding") {
      field("coding", 0.4, "coding benchmark");
      field("terminalbench", 0.25, "terminal benchmark");
      field("scicode", 0.2, "scientific coding benchmark");
      field("intelligence", 0.15, "general intelligence");
    } else if (profile === "speed") {
      field("avgTps", 0.55, "observed throughput");
      field("avgTtftMs", 0.3, "low startup latency", true);
      field("speedTokensPerSecond", 0.15, "benchmark speed");
    } else if (profile === "context") {
      components.push({
        value: normalize(models.map((item) => item.contextLength), model.contextLength),
        weight: 0.8,
        reason: "large context window",
      });
      field("intelligence", 0.2, "general intelligence");
    } else if (profile === "reasoning") {
      field("intelligence", 0.55, "general intelligence");
      field("hle", 0.2, "hard reasoning benchmark");
      field("gpqa", 0.15, "graduate reasoning benchmark");
      components.push({ value: model.capabilities.reasoning ? 1 : 0, weight: 0.1, reason: "reasoning support" });
    } else if (profile === "decision") {
      field("avgTtftMs", 0.4, "low decision latency", true);
      field("avgTps", 0.25, "observed throughput");
      components.push({
        value: normalize(models.map((item) => item.contextLength), model.contextLength),
        weight: 0.35,
        reason: "decision context capacity",
      });
    } else {
      field("intelligence", 0.6, "general intelligence");
      field("coding", 0.15, "coding benchmark");
      field("avgTps", 0.1, "observed throughput");
      components.push({ value: model.capabilities.reasoning ? 1 : 0.4, weight: 0.15, reason: "reasoning capability" });
    }

    const available = components.filter((component) => component.value !== null);
    const totalWeight = available.reduce((sum, component) => sum + component.weight, 0);
    let score = totalWeight ? available.reduce((sum, component) => sum + component.value! * component.weight, 0) / totalWeight : 0;
    const haystack = `${model.id} ${model.name} ${model.description}`.toLowerCase();
    const matches = taskTerms.filter((term) => haystack.includes(term)).length;
    score = Math.min(1, score + Math.min(0.12, matches * 0.02));

    const reasons = available
      .sort((left, right) => (right.value! * right.weight) - (left.value! * left.weight))
      .slice(0, 3)
      .map((component) => component.reason);
    if (matches) reasons.push(`matches ${matches} task keyword${matches === 1 ? "" : "s"}`);

    return { ...model, score: Math.round(score * 1000) / 10, metrics: metric, reasons };
  }).sort((left, right) => right.score - left.score || left.name.localeCompare(right.name));
}

function modelSummary(model: CatalogModel, metrics?: ModelMetrics): Record<string, unknown> {
  return {
    id: model.id,
    name: model.name,
    provider: model.provider,
    category: model.category,
    description: model.description,
    contextLength: model.contextLength,
    maxOutputTokens: model.maxOutputTokens,
    capabilities: model.capabilities,
    ...(metrics ? { metrics } : {}),
  };
}

async function subscriptionUsage(key: string, signal?: AbortSignal): Promise<any> {
  return fetchJson(`${baseUrl()}/usage`, key, signal);
}

function assertSubscriptionRouting(usage: any): void {
  const mode = usage?.routing?.recommendedMode;
  if (mode !== "subscription") {
    const reason = redact(usage?.routing?.reason || "No subscription routing approval was returned");
    throw new Error(`NanoGPT subscription call blocked: recommended mode is ${mode ?? "unknown"}. ${reason}`);
  }
}

function toPiUsage(raw: any): Usage | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const input = finite(raw.prompt_tokens ?? raw.input_tokens) ?? 0;
  const output = finite(raw.completion_tokens ?? raw.output_tokens) ?? 0;
  const totalTokens = finite(raw.total_tokens) ?? input + output;
  const costValue = typeof raw.cost === "number" ? raw.cost : finite(raw.cost?.total);
  return {
    input,
    output,
    cacheRead: finite(raw.prompt_tokens_details?.cached_tokens ?? raw.cache_read_tokens) ?? 0,
    cacheWrite: finite(raw.cache_write_tokens) ?? 0,
    reasoning: finite(raw.completion_tokens_details?.reasoning_tokens ?? raw.reasoning_tokens) ?? undefined,
    totalTokens,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: costValue ?? 0 },
  };
}

function validateDecisionQuestions(questions: Record<string, any>): void {
  const entries = Object.entries(questions || {});
  if (!entries.length || entries.length > 128) throw new Error("Decision requests need between 1 and 128 named questions");

  for (const [name, question] of entries) {
    if (!question || typeof question !== "object" || Array.isArray(question)) {
      throw new Error(`Decision question ${name} must be an object`);
    }
    if (!["choice", "score", "noul"].includes(question.type)) {
      throw new Error(`Decision question ${name} has unsupported type ${String(question.type)}`);
    }
    if (typeof question.instructions !== "string" || !question.instructions.trim()) {
      throw new Error(`Decision question ${name} requires non-empty instructions`);
    }
    if (question.type === "choice") {
      const criteria = question.criteria;
      if (!criteria || typeof criteria !== "object" || Array.isArray(criteria) || Object.keys(criteria).length < 2) {
        throw new Error(`Choice question ${name} requires at least two named criteria`);
      }
    }
    if (question.type === "score") {
      if (!Array.isArray(question.criteria) || question.criteria.length < 2 || question.criteria.length > 10) {
        throw new Error(`Score question ${name} requires 2 to 10 ordered criteria`);
      }
    }
    if (question.type === "noul" && question.criteria !== undefined) {
      const criteria = question.criteria;
      if (!criteria || typeof criteria !== "object" || Array.isArray(criteria)) {
        throw new Error(`Noul question ${name} criteria must describe true and false outcomes`);
      }
    }
  }
}

const requirementProperties = {
  requireReasoning: Type.Optional(Type.Boolean({ description: "Require explicit reasoning support." })),
  requireTools: Type.Optional(Type.Boolean({ description: "Require function/tool calling support." })),
  requireVision: Type.Optional(Type.Boolean({ description: "Require image input support." })),
  requireStructuredOutput: Type.Optional(Type.Boolean({ description: "Require structured/JSON output support." })),
  minContext: Type.Optional(Type.Integer({ minimum: 1, description: "Minimum context window in tokens." })),
};

export default function nanogptExtension(pi: ExtensionAPI) {
  pi.registerTool(defineTool({
    name: "nanogpt_models",
    label: "NanoGPT Models",
    description: "Search and filter the live NanoGPT subscription-only model catalogue. Returns exact callable model IDs and capabilities.",
    parameters: Type.Object({
      query: Type.Optional(Type.String({ description: "Words that must occur in the model ID, name, provider, or description." })),
      ...requirementProperties,
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_RESULT_MODELS, description: "Maximum results (default 10)." })),
      refresh: Type.Optional(Type.Boolean({ description: "Bypass the short in-memory catalogue cache." })),
    }),
    async execute(_id, params, signal) {
      const key = await apiKey();
      const models = (await getCatalog(key, signal, params.refresh ?? false)).filter((model) => matchesRequirements(model, params));
      const selected = models.slice(0, params.limit ?? 10);
      return {
        content: [{ type: "text", text: JSON.stringify({ count: models.length, models: selected.map((model) => modelSummary(model)) }, null, 2) }],
        details: { count: models.length, models: selected },
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "nanogpt_rank_models",
    label: "NanoGPT Rank Models",
    description: "Rank live subscription chat-generation models for a task using hard capability filters plus best-effort benchmark, speed, latency, and context metadata. Use before choosing a NanoGPT model.",
    parameters: Type.Object({
      task: Type.String({ description: "A concise description of the work the delegated model must perform." }),
      profile: Type.Optional(Type.String({ enum: ["general", "coding", "reasoning", "speed", "context", "decision"], description: "Primary ranking profile (default general). Use decision for classification, scoring, routing, or calibrated yes/no tasks." })),
      ...requirementProperties,
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 15, description: "Maximum ranked candidates (default 5)." })),
    }),
    async execute(_id, params, signal) {
      const key = await apiKey();
      const profile = params.profile ?? "general";
      const candidates = (await getCatalog(key, signal))
        .filter((model) => profile === "decision" ? isDecisionModel(model) : supportsPlainChat(model))
        .filter((model) => matchesRequirements(model, params));
      if (!candidates.length) throw new Error("No subscription models meet the requested hard requirements");
      const metrics = await getMetrics(candidates.map((model) => model.id), key, signal);
      const ranked = rankModels(candidates, metrics, profile, params.task).slice(0, params.limit ?? 5);
      const output = ranked.map((model) => ({
        score: model.score,
        reasons: model.reasons,
        ...modelSummary(model, model.metrics),
      }));
      return {
        content: [{ type: "text", text: JSON.stringify({ profile, caveat: "Heuristic ranking; benchmark coverage is incomplete.", models: output }, null, 2) }],
        details: { profile, models: output },
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "nanogpt_usage",
    label: "NanoGPT Usage",
    description: "Check NanoGPT subscription quota and billing-routing advice without running a model.",
    parameters: Type.Object({}),
    async execute(_id, _params, signal) {
      const key = await apiKey();
      const usage = await subscriptionUsage(key, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(usage, null, 2) }],
        details: usage,
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "nanogpt_decide",
    label: "NanoGPT Decide",
    description: "Use a subscription decision model for calibrated choice, score, and yes/no (noul) answers. Returns typed answers and probabilities rather than prose.",
    parameters: Type.Object({
      model: Type.String({ description: "Exact Decisions-category model ID returned by nanogpt_models or nanogpt_rank_models with profile decision." }),
      state: Type.Unknown({ description: "Text or JSON application state for the model to evaluate." }),
      questions: Type.Record(Type.String(), Type.Unknown(), { description: "Named choice, score, or noul questions following NanoGPT's Decisions API shape." }),
    }),
    async execute(_id, params, signal, onUpdate) {
      const key = await apiKey();
      const usageStatus = await subscriptionUsage(key, signal);
      assertSubscriptionRouting(usageStatus);

      const model = (await getCatalog(key, signal)).find((candidate) => candidate.id === params.model);
      if (!model) throw new Error("Requested model is not an exact ID in the current subscription catalogue");
      if (!isDecisionModel(model)) throw new Error("Requested model is not a Decisions-category model");
      validateDecisionQuestions(params.questions as Record<string, any>);

      onUpdate?.({
        content: [{ type: "text", text: `Evaluating ${Object.keys(params.questions).length} question(s) with ${model.name}…` }],
        details: { model: model.id },
      });

      const payload = await fetchJson(
        `${apiV1BaseUrl()}/decisions`,
        key,
        signal,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: model.id,
            state: params.state,
            questions: params.questions,
            include_usage: true,
          }),
        },
        2 * 60 * 1000,
      );
      if (!payload?.answers || typeof payload.answers !== "object") {
        throw new Error("NanoGPT returned no typed decision answers");
      }

      return {
        content: [{ type: "text", text: JSON.stringify({ model: payload.model ?? model.id, answers: payload.answers }, null, 2) }],
        details: { model: payload.model ?? model.id, requestId: payload.id ?? null, answers: payload.answers, usage: payload.usage ?? null },
        usage: toPiUsage(payload.usage),
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "nanogpt_chat",
    label: "NanoGPT Chat",
    description: "Delegate a self-contained text task to an exact model from the live NanoGPT subscription catalogue. Checks subscription routing first and refuses pay-as-you-go fallback.",
    parameters: Type.Object({
      model: Type.String({ description: "Exact model ID returned by nanogpt_models or nanogpt_rank_models. The ID is never modified with routing suffixes." }),
      prompt: Type.String({ description: "Self-contained task and context for the delegated model." }),
      system: Type.Optional(Type.String({ description: "Optional system instruction." })),
      maxTokens: Type.Optional(Type.Integer({ minimum: 1, maximum: 16384, description: "Maximum output tokens (default 4096)." })),
    }),
    async execute(_id, params, signal, onUpdate) {
      const key = await apiKey();
      const usageStatus = await subscriptionUsage(key, signal);
      assertSubscriptionRouting(usageStatus);

      const model = (await getCatalog(key, signal)).find((candidate) => candidate.id === params.model);
      if (!model) throw new Error("Requested model is not an exact ID in the current subscription catalogue");
      if (!supportsPlainChat(model)) {
        throw new Error("Requested model is a decision/special-purpose model and cannot produce ordinary delegated chat text");
      }

      onUpdate?.({
        content: [{ type: "text", text: `Consulting ${model.name} through the NanoGPT subscription…` }],
        details: { model: model.id },
      });

      const messages = [];
      if (params.system?.trim()) messages.push({ role: "system", content: params.system.trim() });
      messages.push({ role: "user", content: params.prompt });
      const payload = await fetchJson(
        `${baseUrl()}/chat/completions`,
        key,
        signal,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: model.id,
            messages,
            stream: false,
            max_tokens: params.maxTokens ?? 4096,
            include_usage: true,
          }),
        },
        10 * 60 * 1000,
      );

      const content = payload?.choices?.[0]?.message?.content;
      const text = typeof content === "string"
        ? content
        : Array.isArray(content)
          ? content.map((part: any) => typeof part === "string" ? part : part?.text || "").join("")
          : "";
      if (!text) throw new Error("NanoGPT returned no assistant text");

      return {
        content: [{ type: "text", text }],
        details: { model: model.id, requestId: payload?.id ?? null, usage: payload?.usage ?? null },
        usage: toPiUsage(payload?.usage),
      };
    },
  }));
}
