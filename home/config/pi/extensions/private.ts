import { spawn, type ChildProcess } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  let active: ChildProcess | undefined;
  let pending: Promise<number | null> | undefined;
  let shuttingDown = false;

  function launch(args: string[]): Promise<number | null> {
    const child = spawn("@privateChat@/bin/pi-private", args, {
      stdio: "inherit", env: { ...process.env, PI_PRIVATE_PARENT_PID: String(process.pid) },
    });
    active = child;
    pending = new Promise((resolve) => {
      child.once("error", () => resolve(1));
      child.once("close", (code) => {
        if (active === child) active = undefined;
        resolve(code);
      });
    });
    return pending;
  }

  pi.on("session_shutdown", async () => {
    shuttingDown = true;
    const child = active;
    if (child) {
      child.kill("SIGTERM");
      const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
      try { await pending; } finally { clearTimeout(timer); }
    }
  });
  pi.registerCommand("private", {
    description: "Open a separately saved, isolated, local-only chat; exit to return here",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify("Private chat requires an interactive terminal.", "error");
        return;
      }
      if (!ctx.isIdle()) {
        ctx.ui.notify("Wait for this conversation to finish before entering private chat.", "warning");
        return;
      }
      await ctx.ui.custom<void>(async (tui, _theme, _keys, done) => {
        const ignoreInterrupt = () => {};
        // Cooked terminal Ctrl-C targets the foreground process group, which
        // still contains normal Pi. Shield it while the launcher reaps its child.
        process.on("SIGINT", ignoreInterrupt);
        tui.stop();
        let error: string | undefined;
        try {
          // Private text never enters Pi's UI, events, transcript, or worklogs.
          // Alternate-screen output is cleared before returning to normal Pi.
          process.stdout.write("\x1b[?1049h\x1b[2J\x1b[H");
          const status = await launch([]);
          if (status !== 0) {
            error = "Private chat failed or was interrupted; no cloud fallback was used.";
          }
        } finally {
          // tcflush drops private keystrokes queued during startup, generation,
          // failure or exit before the ordinary Pi input reader is resumed.
          const flushed = await launch(["--flush-input"]);
          process.stdout.write("\x1b[2J\x1b[H\x1b[?1049l");
          if (flushed === 0 && !shuttingDown) {
            tui.start();
            tui.requestRender(true);
          } else if (!shuttingDown) {
            // Do not hand an unflushed input queue to a normal/cloud session.
            ctx.shutdown();
          }
          done();
          // Let Node consume any queued SIGINT before restoring its disposition.
          setImmediate(() => process.removeListener("SIGINT", ignoreInterrupt));
        }
        if (error) ctx.ui.notify(error, "error");
        return { render: () => [], invalidate: () => {} };
      });
    },
  });
}
