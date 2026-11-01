import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const Parameters = {
  type: "object",
  properties: {
    command: {
      type: "string",
      description: "The exact shell command that requires the user's interactive input. Never include credentials or secrets.",
      minLength: 1,
    },
  },
  required: ["command"],
  additionalProperties: false,
} as const;

const DISPLAY_AND_RUN = String.raw`printf '\033[1;36mCommand requiring your attention:\033[0m\n%s\n\n' "$1"
exec bash -lc "$1"`;

export function terminalArguments(command: string, cwd: string, env = process.env): string[] {
  const launcher = env.PROJECT_WORKSPACE_EXEC || "project-workspace-exec";
  const terminal = env.PI_COMMAND_TERMINAL || "kitty";
  return [
    launcher,
    terminal,
    "--hold",
    "--title",
    "Action needed · Pi",
    "--working-directory",
    cwd,
    "bash",
    "-lc",
    DISPLAY_AND_RUN,
    "pi-command-terminal",
    command,
  ];
}

async function launch(arguments_: string[], cwd: string, signal?: AbortSignal): Promise<void> {
  const [executable, ...argumentsList] = arguments_;
  await new Promise<void>((resolve, reject) => {
    const child = spawn(executable, argumentsList, {
      cwd,
      env: process.env,
      stdio: "ignore",
    });
    const abort = () => child.kill();
    signal?.addEventListener("abort", abort, { once: true });
    child.once("error", reject);
    child.once("exit", (code, childSignal) => {
      signal?.removeEventListener("abort", abort);
      if (code === 0) resolve();
      else reject(new Error(childSignal ? `launcher was terminated by ${childSignal}` : `launcher exited with status ${code}`));
    });
  });
}

export default function commandTerminalExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "open_command_terminal",
    label: "Open Command Terminal",
    description:
      "Open an exact command that genuinely requires user interaction, such as a sudo password, in a new terminal beside the invoking Pi window. Use this after approval instead of asking the user to copy a command. Placement fails closed if the invoking workspace cannot be identified.",
    parameters: Parameters,
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      if (typeof params.command !== "string" || !params.command.trim()) throw new Error("command must not be empty");
      const command = params.command;
      if (command.includes("\0")) throw new Error("command must not contain a NUL byte");

      await launch(terminalArguments(command, ctx.cwd), ctx.cwd, signal);
      return {
        content: [{
          type: "text",
          text: "Opened the exact command in a terminal beside this Pi window. The user only needs to complete the interactive prompt there.",
        }],
        details: undefined,
      };
    },
  });
}
