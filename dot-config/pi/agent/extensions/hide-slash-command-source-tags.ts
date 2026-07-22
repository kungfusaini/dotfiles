// Hide Pi's source/plugin tags in slash-command autocomplete descriptions.
// Example: "[u:npm:foo] Run foo" -> "Run foo".

function stripSourceTag(description: string | undefined): string | undefined {
  if (!description) return description;

  const stripped = description
    // Tags at the start of the description.
    .replace(/^\[[^\]]+\]\s*/u, "")
    // Tags after an argument hint: "<arg> — [u] description".
    .replace(/(—\s*)\[[^\]]+\]\s*/u, "$1")
    .trim();

  return stripped || undefined;
}

export default function hideSlashCommandSourceTags(pi: any) {
  pi.on("session_start", (_event: any, ctx: any) => {
    ctx.ui.addAutocompleteProvider((current: any) => ({
      triggerCharacters: current.triggerCharacters,

      async getSuggestions(lines: string[], cursorLine: number, cursorCol: number, options: any) {
        const suggestions = await current.getSuggestions(lines, cursorLine, cursorCol, options);
        if (!suggestions || !suggestions.prefix?.startsWith("/")) {
          return suggestions;
        }

        return {
          ...suggestions,
          items: suggestions.items.map((item: any) => ({
            ...item,
            description: stripSourceTag(item.description),
          })),
        };
      },

      applyCompletion(lines: string[], cursorLine: number, cursorCol: number, item: any, prefix: string) {
        return current.applyCompletion(lines, cursorLine, cursorCol, item, prefix);
      },

      shouldTriggerFileCompletion(lines: string[], cursorLine: number, cursorCol: number) {
        return current.shouldTriggerFileCompletion?.(lines, cursorLine, cursorCol) ?? true;
      },
    }));
  });
}
