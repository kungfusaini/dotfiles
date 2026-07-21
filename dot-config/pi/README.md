# Pi Config

Personal configuration for [Pi Coding Agent](https://github.com/earendil-works/pi-coding-agent), using XDG-compliant paths.

## Contents

- `agent/AGENTS.md` — global agent instructions
- `agent/settings.json` — default model, theme, packages, tree filtering, and session storage
- `agent/keybindings.json` — TUI and model/session shortcuts
- `agent/themes/gruvbox-dark.json` — Gruvbox Dark TUI theme
- `agent/extensions/auto-session-title.ts` — automatic and on-demand session titles
- `agent/extensions/footer.ts` — custom usage footer
- `agent/extensions/pretty-code-blocks.ts` — Markdown code blocks without raw backtick fences
- `agent/extensions/tree-tab-toggle.ts` — Tab-based folding in tree selectors
- `agent/extensions/project-workspaces/` — project/stream scopes, durable plans, plan mode, and live todo workflows
- `agent/extensions/question.ts` — deterministic multiple-choice prompts
- `agent/extensions/chatid.ts` — copy the current chat ID to the clipboard

## Packages

- [`pi-web-access`](https://www.npmjs.com/package/pi-web-access) — web research and content retrieval
- [`pi-vim-flash`](https://pi.dev/packages/pi-vim-flash) — Vim-style prompt editing and Flash-style transcript navigation

## Runtime data

Private and generated files live outside the repository:

- Authentication: `~/.local/state/pi/agent/auth.json`
- Sessions: `~/.local/state/pi/agent/sessions/`
- Downloaded binaries: `~/.cache/pi/agent/bin/`
- Package data: `~/.local/share/pi/agent/npm/`

## Source

This configuration is managed under `dot-config/pi` in the [`kungfusaini/dotfiles`](https://github.com/kungfusaini/dotfiles) repository and exposed at `~/.config/pi`.

Project workspace commands:

```text
/projects         Browse, create, and select projects
/streams          Browse, create, and select streams for the current project
/project-context  Show the current project/stream scope
/plans            List durable plans for the current scope
/plan             Toggle/read-only plan mode
/todo             Show the live session todo list
```

After changing extensions, reload Pi with:

```text
/reload
```
