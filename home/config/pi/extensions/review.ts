import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const REVIEWER_SYSTEM_PROMPT = `You are an independent senior code reviewer.

Your job is to find concrete defects in the work selected for review. Prioritize:

- Incorrect behavior and regressions
- Security or privacy problems
- Data loss or corruption
- Race conditions and state-management errors
- Missing error handling
- Broken assumptions at system boundaries
- Important missing tests

Independently inspect the repository, the selected changes, and enough surrounding
code to understand their behavior. Treat the parent agent's description as context,
not as proof that the implementation is correct.

Do not modify files. Use shell commands only for read-only inspection, such as
\`git status\`, \`git diff\`, \`git log\`, \`git show\`, and test-result inspection. Do
not run commands that alter the repository or environment.

Report only actionable findings. Do not report personal style preferences, minor
formatting issues, or speculative concerns without a plausible failure mode.

For each finding, include:

- Severity: critical, high, medium, or low
- File path and line number
- What is wrong
- When or how it fails
- The likely impact
- A concise suggested direction for fixing it

Order findings by severity. If you find no actionable defects, say so explicitly.
Do not implement fixes.`;

const COORDINATOR_PROMPT = (focus: string) => `An independent review was requested with /review.

Act as the review coordinator. Use your knowledge of this conversation and the
current repository to decide what work should be reviewed. Do not ask the user to
manually assemble the scope when you can infer it yourself.

Call the review_agent tool exactly once. Give it a precise review target, intended
behavior, relevant context and constraints, and validation already performed. Do
not paste the full conversation or large source files: the reviewer can inspect the
working tree independently. Treat the user's optional text as review emphasis, not
as the complete scope.

After the reviewer returns, present its findings clearly. You may add brief context
or identify uncertain claims, but do not silently discard findings. Do not modify
files unless the user separately asks you to address the review.

User focus: ${focus || "No additional focus was requested."}`;

const ReviewParameters = Type.Object({
  reviewTarget: Type.String({
    description:
      "Precisely identify the working-tree changes, staged changes, commit range, files, or named work to review.",
  }),
  intendedBehavior: Type.String({
    description: "What the selected implementation should accomplish and its important acceptance criteria.",
  }),
  userFocus: Type.String({
    description: 'Optional user emphasis, or "No additional focus was requested."',
  }),
  relevantContext: Type.String({
    description: "Only the constraints, architectural decisions, compatibility requirements, and known risks needed for review.",
  }),
  validationPerformed: Type.String({
    description: 'Tests, builds, or checks already run and their results; use "Unknown" when not established.',
  }),
});

type ReviewParameters = {
  reviewTarget: string;
  intendedBehavior: string;
  userFocus: string;
  relevantContext: string;
  validationPerformed: string;
};

type Usage = {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
};

type ReviewDetails = {
  task: string;
  model?: string;
  exitCode: number;
  stderr?: string;
};

function buildReviewTask(params: ReviewParameters): string {
  return `## Review target

${params.reviewTarget}

## Intended behavior

${params.intendedBehavior}

## User focus

${params.userFocus}

## Relevant context

${params.relevantContext}

## Validation already performed

${params.validationPerformed}

## Instructions

Inspect the selected work directly in the repository. Verify the parent agent's
summary rather than assuming it is accurate. Review the changed code and enough
surrounding code to identify integration problems.

Stay within the selected review target unless an adjacent issue is directly caused
by the change. Return actionable findings using your required review format.`;
}

function getPiInvocation(args: string[]): { command: string; args: string[] } {
  const currentScript = process.argv[1];
  const isBunVirtualScript = currentScript?.startsWith("/$bunfs/root/");
  if (currentScript && !isBunVirtualScript && fs.existsSync(currentScript)) {
    return { command: process.execPath, args: [currentScript, ...args] };
  }

  const executable = path.basename(process.execPath).toLowerCase();
  if (!/^(node|bun)(\.exe)?$/.test(executable)) {
    return { command: process.execPath, args };
  }

  return { command: "pi", args };
}

function emptyUsage(): Usage {
  return {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: 0,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
  };
}

function addUsage(total: Usage, usage: any): void {
  total.input += usage?.input ?? 0;
  total.output += usage?.output ?? 0;
  total.cacheRead += usage?.cacheRead ?? 0;
  total.cacheWrite += usage?.cacheWrite ?? 0;
  total.totalTokens += usage?.totalTokens ?? 0;
  total.cost.input += usage?.cost?.input ?? 0;
  total.cost.output += usage?.cost?.output ?? 0;
  total.cost.cacheRead += usage?.cost?.cacheRead ?? 0;
  total.cost.cacheWrite += usage?.cost?.cacheWrite ?? 0;
  total.cost.total += usage?.cost?.total ?? 0;
}

function assistantText(message: any): string {
  if (message?.role !== "assistant" || !Array.isArray(message.content)) return "";
  return message.content
    .filter((part: any) => part?.type === "text" && typeof part.text === "string")
    .map((part: any) => part.text)
    .join("\n");
}

async function runReviewer(
  cwd: string,
  model: string,
  thinkingLevel: string | undefined,
  task: string,
  signal: AbortSignal | undefined,
  onUpdate: ((update: any) => void) | undefined,
): Promise<{ output: string; exitCode: number; stderr: string; usage: Usage }> {
  const tempDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), "pi-review-"));
  const promptPath = path.join(tempDir, "reviewer.md");
  await fs.promises.writeFile(promptPath, REVIEWER_SYSTEM_PROMPT, { encoding: "utf8", mode: 0o600 });

  const args = [
    "--mode",
    "json",
    "--no-session",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--tools",
    "read,grep,find,ls,bash",
    "--model",
    model,
  ];
  if (thinkingLevel) args.push("--thinking", thinkingLevel);
  args.push("--append-system-prompt", promptPath, `Task: ${task}`);

  let output = "";
  let stderr = "";
  const usage = emptyUsage();

  try {
    const exitCode = await new Promise<number>((resolve, reject) => {
      const invocation = getPiInvocation(args);
      const child = spawn(invocation.command, invocation.args, {
        cwd,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let buffer = "";
      let aborted = false;

      const processLine = (line: string) => {
        if (!line.trim()) return;
        let event: any;
        try {
          event = JSON.parse(line);
        } catch {
          return;
        }
        if (event.type !== "message_end" || event.message?.role !== "assistant") return;

        const text = assistantText(event.message);
        if (text) output = text;
        addUsage(usage, event.message.usage);
        onUpdate?.({
          content: [{ type: "text", text: output || "Reviewer is inspecting the selected work..." }],
          details: { task, model, exitCode: -1 } satisfies ReviewDetails,
        });
      };

      child.stdout.on("data", (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) processLine(line);
      });
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (buffer.trim()) processLine(buffer);
        if (aborted) reject(new Error("Review was aborted"));
        else resolve(code ?? 1);
      });

      const abort = () => {
        aborted = true;
        child.kill("SIGTERM");
        setTimeout(() => {
          if (child.exitCode === null) child.kill("SIGKILL");
        }, 5000).unref();
      };
      if (signal?.aborted) abort();
      else signal?.addEventListener("abort", abort, { once: true });
    });

    return { output, exitCode, stderr: stderr.trim(), usage };
  } finally {
    await fs.promises.rm(tempDir, { recursive: true, force: true });
  }
}

export default function reviewExtension(pi: ExtensionAPI) {
  pi.registerCommand("review", {
    description: "Have the main agent scope work for an independent reviewer",
    handler: async (args, ctx) => {
      const prompt = COORDINATOR_PROMPT(args.trim());
      if (ctx.isIdle()) {
        pi.sendUserMessage(prompt);
      } else {
        pi.sendUserMessage(prompt, { deliverAs: "followUp" });
        ctx.ui.notify("Review queued", "info");
      }
    },
  });

  pi.registerTool({
    name: "review_agent",
    label: "Independent reviewer",
    description:
      "Delegate a review scope you selected to a fresh, independent, read-only reviewer. The reviewer inherits the active model and thinking level, can inspect the current repository, and does not receive the parent transcript. Use this when coordinating /review.",
    parameters: ReviewParameters,
    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      if (!ctx.model) {
        return {
          content: [{ type: "text", text: "Cannot start reviewer: no active model is selected." }],
          details: { task: "", exitCode: 1 } satisfies ReviewDetails,
        };
      }

      const task = buildReviewTask(params as ReviewParameters);
      const model = `${ctx.model.provider}/${ctx.model.id}`;

      try {
        const result = await runReviewer(ctx.cwd, model, ctx.thinkingLevel, task, signal, onUpdate);
        const details: ReviewDetails = {
          task,
          model,
          exitCode: result.exitCode,
          ...(result.stderr ? { stderr: result.stderr } : {}),
        };

        if (result.exitCode !== 0 || !result.output) {
          const diagnostic = result.stderr || result.output || "Reviewer exited without producing a report.";
          return {
            content: [{ type: "text", text: `Independent review failed: ${diagnostic}` }],
            details,
            usage: result.usage,
          };
        }

        return {
          content: [{ type: "text", text: result.output }],
          details,
          usage: result.usage,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          content: [{ type: "text", text: `Independent review failed: ${message}` }],
          details: { task, model, exitCode: 1, stderr: message } satisfies ReviewDetails,
        };
      }
    },
  });
}
