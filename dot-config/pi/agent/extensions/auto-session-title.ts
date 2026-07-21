import { complete, type Message } from "@earendil-works/pi-ai/compat";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
  SessionEntry,
} from "@earendil-works/pi-coding-agent";

const TITLE_PROVIDER = "openai-codex";
const TITLE_MODEL = "gpt-5.4-mini";
const MAX_SOURCE_CHARS = 8_000;
const MAX_TITLE_CHARS = 72;

const SYSTEM_PROMPT = `You generate titles for coding-agent conversations.

Return only the title, with no quotes, markdown, label, or explanation.

Rules:
- Use one line and at most ${MAX_TITLE_CHARS} characters.
- Use the same language as the user.
- Capture the main task or question so the conversation is easy to find later.
- Preserve important technical terms, filenames, error codes, and numbers.
- Prefer a natural phrase over a list of keywords.
- Do not answer the request.
- Do not mention tools, agents, title generation, or summarization.
- Never claim that a title cannot be generated.`;

type MessageEntry = Extract<SessionEntry, { type: "message" }>;

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter(
      (part): part is { type: "text"; text: string } =>
        Boolean(part) &&
        typeof part === "object" &&
        (part as { type?: unknown }).type === "text" &&
        typeof (part as { text?: unknown }).text === "string",
    )
    .map((part) => part.text)
    .join("\n");
}

function realUserMessages(entries: SessionEntry[]): MessageEntry[] {
  return entries.filter(
    (entry): entry is MessageEntry =>
      entry.type === "message" &&
      entry.message.role === "user" &&
      textFromContent(entry.message.content).trim().length > 0,
  );
}

function conversationSource(entries: SessionEntry[]): string {
  const sections: string[] = [];
  for (const entry of entries) {
    if (entry.type !== "message") continue;
    if (entry.message.role !== "user" && entry.message.role !== "assistant") continue;
    const text = textFromContent(entry.message.content).trim();
    if (!text) continue;
    sections.push(`${entry.message.role === "user" ? "User" : "Assistant"}: ${text}`);
  }
  return sections.join("\n\n").slice(-MAX_SOURCE_CHARS);
}

function cleanTitle(raw: string): string | undefined {
  const line = raw
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .split(/\r?\n/)
    .map((value) => value.trim())
    .find(Boolean);
  if (!line) return undefined;

  const cleaned = line
    .replace(/^#{1,6}\s*/, "")
    .replace(/^(?:title|thread title|session title)\s*:\s*/i, "")
    .replace(/^[`"'“‘]+|[`"'”’]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return undefined;
  if (cleaned.length <= MAX_TITLE_CHARS) return cleaned;

  const shortened = cleaned.slice(0, MAX_TITLE_CHARS - 1).trimEnd();
  const lastSpace = shortened.lastIndexOf(" ");
  const wordSafe = lastSpace >= Math.floor(MAX_TITLE_CHARS * 0.6) ? shortened.slice(0, lastSpace) : shortened;
  return `${wordSafe}…`;
}

export default function (pi: ExtensionAPI) {
  let attempted = false;
  let generation: AbortController | undefined;

  function stopGeneration(): void {
    generation?.abort();
    generation = undefined;
  }

  async function generateTitle(source: string, ctx: ExtensionContext): Promise<string> {
    const model = ctx.modelRegistry.find(TITLE_PROVIDER, TITLE_MODEL);
    if (!model) throw new Error(`Title model not found: ${TITLE_PROVIDER}/${TITLE_MODEL}`);

    const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
    if (!auth.ok) throw new Error(auth.error);
    if (!auth.apiKey) throw new Error(`No credentials for ${TITLE_PROVIDER}`);

    stopGeneration();
    const controller = new AbortController();
    generation = controller;

    const message: Message = {
      role: "user",
      content: [
        {
          type: "text",
          text: `Generate a title for this conversation:\n\n${source.slice(0, MAX_SOURCE_CHARS)}`,
        },
      ],
      timestamp: Date.now(),
    };

    try {
      const response = await complete(
        model,
        { systemPrompt: SYSTEM_PROMPT, messages: [message] },
        {
          apiKey: auth.apiKey,
          headers: auth.headers,
          env: auth.env,
          signal: controller.signal,
          reasoningEffort: "low",
          maxTokens: 256,
          maxRetries: 1,
        },
      );
      if (controller.signal.aborted || response.stopReason === "aborted") {
        throw new Error("Title generation was cancelled");
      }
      const title = cleanTitle(
        response.content
          .filter((part): part is { type: "text"; text: string } => part.type === "text")
          .map((part) => part.text)
          .join("\n"),
      );
      if (!title) throw new Error("The title model returned an empty title");
      return title;
    } finally {
      if (generation === controller) generation = undefined;
    }
  }

  pi.on("session_start", (_event, ctx) => {
    stopGeneration();
    attempted = pi.getSessionName() !== undefined || realUserMessages(ctx.sessionManager.getBranch()).length > 0;
  });

  pi.on("before_agent_start", (event, ctx) => {
    if (attempted || pi.getSessionName() !== undefined) return;
    if (realUserMessages(ctx.sessionManager.getBranch()).length > 0) {
      attempted = true;
      return;
    }

    const source = event.prompt.trim();
    if (!source) return;
    attempted = true;

    // Run alongside the main request, like OpenCode. Session shutdown aborts the
    // request, and the second name check ensures a manual /name always wins.
    void generateTitle(source, ctx)
      .then((title) => {
        if (pi.getSessionName() === undefined) pi.setSessionName(title);
      })
      .catch(() => {
        // Automatic naming must never interrupt or add noise to the main turn.
      });
  });

  pi.on("session_shutdown", () => {
    stopGeneration();
  });

  pi.registerCommand("retitle", {
    description: `Regenerate the session name with ${TITLE_PROVIDER}/${TITLE_MODEL}`,
    handler: async (_args, ctx: ExtensionCommandContext) => {
      const source = conversationSource(ctx.sessionManager.getBranch());
      if (!source) {
        if (ctx.hasUI) ctx.ui.notify("No conversation text to title", "warning");
        return;
      }

      if (ctx.hasUI) ctx.ui.notify("Generating session title…", "info");
      try {
        const title = await generateTitle(source, ctx);
        pi.setSessionName(title);
        attempted = true;
        if (ctx.hasUI) ctx.ui.notify(`Session named: ${title}`, "info");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (ctx.hasUI) ctx.ui.notify(`Could not generate title: ${message}`, "error");
      }
    },
  });
}
