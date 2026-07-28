import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HELPER = `${process.env.HOME}/.local/share/pi/voice-parakeet/bin/pi-parakeet-rs`;
const ORT_DIR = `${process.env.HOME}/.local/share/pi/voice-parakeet/lib`;
const MIC_DEVICE = "0";
const DEFAULT_SECONDS = 8;

type Pending = {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
};

let daemon: ChildProcessWithoutNullStreams | undefined;
let readyPromise: Promise<void> | undefined;
let readyResolve: (() => void) | undefined;
let readyReject: ((error: Error) => void) | undefined;
let pending: Pending[] = [];
let stdoutBuffer = "";
let stderrTail = "";

function appendStderr(text: string) {
  stderrTail = (stderrTail + text).slice(-4000);
}

function stopDaemon() {
  if (!daemon) return;
  try {
    daemon.stdin.write(JSON.stringify({ cmd: "shutdown" }) + "\n");
  } catch {}
  try {
    daemon.kill("SIGTERM");
  } catch {}
  daemon = undefined;
  readyPromise = undefined;
  readyResolve = undefined;
  readyReject = undefined;
  pending.splice(0).forEach((p) => p.reject(new Error("Parakeet daemon stopped")));
}

function handleLine(line: string) {
  if (!line.trim()) return;
  let msg: any;
  try {
    msg = JSON.parse(line);
  } catch {
    appendStderr(`\n[bad-json stdout] ${line}`);
    return;
  }

  if (msg.event === "ready") {
    readyResolve?.();
    readyResolve = undefined;
    readyReject = undefined;
    return;
  }

  const next = pending.shift();
  if (!next) return;
  if (msg.ok) next.resolve(msg);
  else next.reject(new Error(msg.error ?? "Parakeet daemon request failed"));
}

async function ensureDaemon(ctx: ExtensionCommandContext) {
  if (!existsSync(HELPER)) {
    throw new Error(`Parakeet helper not found at ${HELPER}. Build the prototype first.`);
  }
  if (daemon && !daemon.killed) {
    await readyPromise;
    return daemon;
  }

  stderrTail = "";
  readyPromise = new Promise<void>((resolve, reject) => {
    readyResolve = resolve;
    readyReject = reject;
  });

  daemon = spawn(HELPER, ["--daemon"], {
    env: {
      ...process.env,
      DYLD_LIBRARY_PATH: [ORT_DIR, process.env.DYLD_LIBRARY_PATH].filter(Boolean).join(":"),
    },
  });

  daemon.stdout.on("data", (chunk) => {
    stdoutBuffer += chunk.toString("utf8");
    while (true) {
      const idx = stdoutBuffer.indexOf("\n");
      if (idx === -1) break;
      const line = stdoutBuffer.slice(0, idx);
      stdoutBuffer = stdoutBuffer.slice(idx + 1);
      handleLine(line);
    }
  });
  daemon.stderr.on("data", (chunk) => appendStderr(chunk.toString("utf8")));
  daemon.on("exit", (code, signal) => {
    const err = new Error(`Parakeet daemon exited code=${code} signal=${signal}. ${stderrTail}`);
    readyReject?.(err);
    pending.splice(0).forEach((p) => p.reject(err));
    daemon = undefined;
    readyPromise = undefined;
  });

  ctx.ui.setStatus("voice-parakeet", "loading voice model…");
  await readyPromise;
  ctx.ui.setStatus("voice-parakeet", "voice ready");
  return daemon;
}

async function transcribe(wav: string, ctx: ExtensionCommandContext): Promise<any> {
  const proc = await ensureDaemon(ctx);
  return new Promise((resolve, reject) => {
    pending.push({ resolve, reject });
    proc.stdin.write(JSON.stringify({ cmd: "transcribe", wav }) + "\n");
  });
}

function parseSeconds(args: string): number {
  const n = Number(args.trim());
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_SECONDS;
  return Math.max(1, Math.min(60, n));
}

export default function voiceParakeet(pi: ExtensionAPI) {
  pi.registerCommand("voice", {
    description: "Record a local Parakeet voice prompt, transcribe it, and submit it to Pi",
    handler: async (args, ctx) => {
      const seconds = parseSeconds(args ?? "");
      const dir = await mkdtemp(join(tmpdir(), "pi-voice-"));
      const wav = join(dir, "prompt.wav");

      try {
        ctx.ui.setStatus("voice-parakeet", `recording ${seconds}s…`);
        ctx.ui.notify(`Recording voice prompt for ${seconds}s…`, "info");
        const record = await pi.exec(
          "ffmpeg",
          [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "avfoundation",
            "-i",
            `:${MIC_DEVICE}`,
            "-t",
            String(seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            wav,
          ],
          { timeout: (seconds + 5) * 1000 },
        );
        if (record.code !== 0) {
          throw new Error(`ffmpeg failed: ${record.stderr || record.stdout}`);
        }

        ctx.ui.setStatus("voice-parakeet", "transcribing…");
        const result = await transcribe(wav, ctx);
        const text = String(result.text ?? "").trim();
        if (!text) {
          ctx.ui.notify("No speech transcription produced.", "warning");
          return;
        }

        ctx.ui.setStatus("voice-parakeet", undefined);
        ctx.ui.notify(`Voice prompt submitted (${Math.round((result.transcribe_ms ?? 0) / 100) / 10}s).`, "info");
        pi.sendUserMessage(text);
      } catch (error) {
        ctx.ui.setStatus("voice-parakeet", undefined);
        ctx.ui.notify(`Voice prompt failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("voice-stop", {
    description: "Stop the warm Parakeet voice helper daemon",
    handler: async (_args, ctx) => {
      stopDaemon();
      ctx.ui.setStatus("voice-parakeet", undefined);
      ctx.ui.notify("Stopped Parakeet voice helper.", "info");
    },
  });

  pi.on("session_shutdown", () => {
    stopDaemon();
  });
}
