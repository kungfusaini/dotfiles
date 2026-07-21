import { copyToClipboard, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function chatIdExtension(pi: ExtensionAPI) {
  pi.registerCommand("chatid", {
    description: "Copy the current chat ID and session path to the clipboard",
    handler: async (_args, ctx) => {
      const id = ctx.sessionManager.getSessionId();
      const path = ctx.sessionManager.getSessionFile() ?? "(ephemeral session)";
      const text = `Chat ID: ${id}\nPath: ${path}`;

      try {
        await copyToClipboard(text);
        ctx.ui.notify("Copied chat ID and path to clipboard", "info");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        ctx.ui.notify(`Could not copy chat ID: ${message}`, "error");
      }
    },
  });
}
