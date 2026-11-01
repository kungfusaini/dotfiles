import { randomUUID } from "node:crypto";
import { chmodSync, lstatSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";

const POLL_INTERVAL_MS = 200;
const LOCAL_RELOAD_ARGUMENT = "--apply";
const LOCAL_RELOAD_COMMAND = `/reload-all ${LOCAL_RELOAD_ARGUMENT}`;
const EMPTY_PARAMETERS = {
  type: "object",
  properties: {},
  additionalProperties: false,
} as const;

interface ReloadAllProcessState {
  appliedToken?: string;
  applyingToken?: string;
  reloadInProgress?: boolean;
}

function processState(): ReloadAllProcessState {
  const globals = globalThis as typeof globalThis & { __piReloadAllProcessState?: ReloadAllProcessState };
  globals.__piReloadAllProcessState ??= {};
  return globals.__piReloadAllProcessState;
}

export function reloadAllDirectory(env: NodeJS.ProcessEnv = process.env): string {
  if (env.XDG_RUNTIME_DIR) return join(env.XDG_RUNTIME_DIR, "pi-reload-all");
  return join(tmpdir(), `pi-reload-all-${process.getuid()}`);
}

function ensurePrivateDirectory(directory: string): void {
  const parent = dirname(directory);
  const parentStat = lstatSync(parent);
  const usingSharedTemporaryRoot = parent === tmpdir();
  const unsafeParent = !parentStat.isDirectory()
    || parentStat.isSymbolicLink()
    || (usingSharedTemporaryRoot
      ? (parentStat.mode & 0o002) !== 0 && (parentStat.mode & 0o1000) === 0
      : parentStat.uid !== process.getuid() || (parentStat.mode & 0o077) !== 0);
  if (unsafeParent) throw new Error(`Reload coordination parent is not private: ${parent}`);

  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const stat = lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`Reload coordination path is not a directory: ${directory}`);
  }
  if (stat.uid !== process.getuid()) {
    throw new Error(`Reload coordination directory is not owned by the current user: ${directory}`);
  }
  chmodSync(directory, 0o700);
}

export function readReloadAllToken(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const path = join(reloadAllDirectory(env), "generation");
  try {
    const stat = lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.uid !== process.getuid() || stat.size > 128) return undefined;
    const token = readFileSync(path, "utf8").trim();
    return token || undefined;
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return undefined;
    throw error;
  }
}

export function writeReloadAllToken(env: NodeJS.ProcessEnv = process.env): string {
  const directory = reloadAllDirectory(env);
  ensurePrivateDirectory(directory);
  const token = randomUUID();
  const target = join(directory, "generation");
  const temporary = join(directory, `.generation-${process.pid}-${randomUUID()}`);
  try {
    writeFileSync(temporary, `${token}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
    renameSync(temporary, target);
  } finally {
    rmSync(temporary, { force: true });
  }
  return token;
}

export default function reloadAllExtension(pi: ExtensionAPI) {
  let poll: ReturnType<typeof setInterval> | undefined;
  let lastSeenToken: string | undefined;
  let pendingToken: string | undefined;
  let reloadPending = false;

  const stopPolling = () => {
    if (poll) clearInterval(poll);
    poll = undefined;
  };

  const queueReload = (token: string) => {
    pendingToken = token;
    if (reloadPending) return;
    reloadPending = true;
    pi.sendUserMessage(LOCAL_RELOAD_COMMAND, {
      deliverAs: "followUp",
      expandPromptTemplates: true,
    });
  };

  const reloadWhenIdle = async (ctx: ExtensionCommandContext) => {
    let attemptedToken: string | undefined;
    try {
      await ctx.waitForIdle();
      const state = processState();
      attemptedToken = pendingToken ?? lastSeenToken;
      state.applyingToken = attemptedToken;
      state.reloadInProgress = true;
      try {
        await ctx.reload();
      } finally {
        state.reloadInProgress = false;
      }
    } catch (error) {
      const state = processState();
      state.applyingToken = undefined;
      reloadPending = false;
      pendingToken = undefined;
      lastSeenToken = state.appliedToken;
      throw error;
    }
  };

  pi.on("session_start", (event, ctx) => {
    stopPolling();
    reloadPending = false;
    pendingToken = undefined;
    try {
      lastSeenToken = readReloadAllToken();
      const state = processState();
      if (event.reason === "reload") {
        if (state.applyingToken) state.appliedToken = state.applyingToken;
        else state.appliedToken ??= lastSeenToken;
      } else {
        state.appliedToken = lastSeenToken;
      }
      state.applyingToken = undefined;
      if (lastSeenToken && lastSeenToken !== state.appliedToken) {
        if (state.reloadInProgress) lastSeenToken = state.appliedToken;
        else queueReload(lastSeenToken);
      }
    } catch (error) {
      lastSeenToken = undefined;
      if (ctx.hasUI) ctx.ui.notify(`Global reload watcher disabled: ${(error as Error).message}`, "error");
      return;
    }

    poll = setInterval(() => {
      try {
        if (processState().reloadInProgress) return;
        const token = readReloadAllToken();
        if (!token || token === lastSeenToken) return;
        lastSeenToken = token;
        queueReload(token);
      } catch (error) {
        stopPolling();
        if (ctx.hasUI) ctx.ui.notify(`Global reload watcher disabled: ${(error as Error).message}`, "error");
      }
    }, POLL_INTERVAL_MS);
    poll.unref();
  });

  pi.on("session_shutdown", stopPolling);

  pi.registerTool({
    name: "reload_all_sessions",
    label: "Reload All Pi Sessions",
    description: "Reload Pi resources in every running session after deployed guidance, extensions, skills, or settings change. Does not restart Pi processes.",
    parameters: EMPTY_PARAMETERS,
    async execute() {
      const token = writeReloadAllToken();
      lastSeenToken = token;
      queueReload(token);
      return {
        content: [{
          type: "text",
          text: "Broadcast the resource reload. Every running Pi session will reload after it becomes idle.",
        }],
        details: undefined,
      };
    },
  });

  pi.registerCommand("reload-all", {
    description: "Reload resources in every running Pi session",
    handler: async (args, ctx) => {
      if (args.trim() === LOCAL_RELOAD_ARGUMENT) {
        await reloadWhenIdle(ctx);
        return;
      }
      if (args.trim()) {
        ctx.ui.notify("Usage: /reload-all", "error");
        return;
      }
      try {
        lastSeenToken = writeReloadAllToken();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        ctx.ui.notify(`Could not broadcast reload: ${message}`, "error");
        return;
      }
      ctx.ui.notify("Reloading all running Pi sessions", "info");
      pendingToken = lastSeenToken;
      if (reloadPending) return;
      reloadPending = true;
      await reloadWhenIdle(ctx);
    },
  });
}
