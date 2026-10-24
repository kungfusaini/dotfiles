import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { mkdir, readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, extname, join, resolve } from "node:path";

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48) || "image";
}

function expand(path: string, cwd: string): string {
  if (path === "~") return homedir();
  if (path.startsWith("~/")) return join(homedir(), path.slice(2));
  return resolve(cwd, path);
}

function outputPaths(path: string, count: number): string[] {
  if (count === 1) return [path];
  const extension = extname(path) || ".png";
  const stem = basename(path, extension);
  return Array.from({ length: count }, (_, index) =>
    join(resolve(path, ".."), `${stem}-${index + 1}${extension}`),
  );
}

function createTool(pi: ExtensionAPI) {
  return defineTool({
  name: "codex_imagegen",
  label: "Codex ImageGen",
  description: "Generate or edit images with the user's Codex/ChatGPT login. Returns the saved paths and images inline.",
  parameters: Type.Object({
    prompt: Type.String({ description: "A concise image prompt or edit instruction." }),
    images: Type.Optional(Type.Array(Type.String(), {
      maxItems: 5,
      description: "Input image paths. When present, edits these images instead of generating from scratch.",
    })),
    count: Type.Optional(Type.Integer({ minimum: 1, maximum: 4, description: "Number of outputs (default 1)." })),
    size: Type.Optional(Type.String({
      enum: ["auto", "1024x1024", "1536x1024", "1024x1536"],
      description: "Native generation size. Use 1536x1024 for maximum landscape resolution or 1024x1536 for portrait.",
    })),
    quality: Type.Optional(Type.String({
      enum: ["auto", "low", "medium", "high"],
      description: "Generation quality (default high).",
    })),
    output: Type.Optional(Type.String({ description: "Output PNG or WebP path. A timestamped path is used by default." })),
  }),

  async execute(_id, params, signal, onUpdate, ctx) {
    const prompt = params.prompt.trim();
    if (!prompt) throw new Error("prompt is required");

    const inputs = (params.images ?? []).map((path) => expand(path, ctx.cwd));
    const count = params.count ?? 1;
    const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
    const output = params.output
      ? expand(params.output, ctx.cwd)
      : join(homedir(), "Pictures", "codex-imagegen", `${timestamp}-${slug(prompt)}.png`);

    await mkdir(resolve(output, ".."), { recursive: true });
    const mode = inputs.length ? "edit" : "generate";
    const args = [
      mode,
      "--prompt", prompt,
      "--out", output,
      "--n", String(count),
      "--quality", params.quality ?? "high",
      "--force",
    ];
    if (params.size && params.size !== "auto") args.push("--size", params.size);
    for (const image of inputs) args.push("--image", image);

    onUpdate?.({
      content: [{ type: "text", text: `${mode === "edit" ? "Editing" : "Generating"} image…` }],
      details: { output },
    });

    const result = await pi.exec("codex-imagegen", args, {
      cwd: ctx.cwd,
      signal,
      timeout: 10 * 60 * 1000,
    });
    if (result.code !== 0) {
      throw new Error(result.stderr.trim() || result.stdout.trim() || `codex-imagegen exited ${result.code}`);
    }

    const paths = outputPaths(output, count);
    const imageContent = await Promise.all(paths.map(async (path) => ({
      type: "image" as const,
      data: await readFile(path, "base64"),
      mimeType: extname(path).toLowerCase() === ".webp" ? "image/webp" : "image/png",
    })));

    return {
      content: [{ type: "text" as const, text: `Saved:\n${paths.join("\n")}` }, ...imageContent],
      details: { paths },
    };
  },
  });
}

export default function (pi: ExtensionAPI) {
  pi.registerTool(createTool(pi));
}
