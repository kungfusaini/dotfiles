---
description: Inspect the current repo and propose or create a project-local opencode setup.
agent: normal
---

Set up opencode for this project using the user's preferred global/local split. Arguments: `$ARGUMENTS`.

Purpose:

- Create or update project-local opencode configuration only when it helps this repo.
- Avoid duplicating global configuration.
- Keep context and tool surface small by enabling MCPs and LSPs locally only when useful.
- Preserve existing project files and ask before writing.

Workflow:

1. Inspect the current project enough to classify it. Look for files such as:
   - `package.json`, lockfiles, framework config, `vite.config.*`, `next.config.*`, `astro.config.*`, `svelte.config.*`, `vue.config.*`
   - `pyproject.toml`, `requirements*.txt`, `uv.lock`, `poetry.lock`
   - `Cargo.toml`, `go.mod`, `deno.json`, `tsconfig.json`, `jsconfig.json`
   - existing `AGENTS.md`, `CLAUDE.md`, `.opencode/opencode.json`, `.opencode/skills/`, `.opencode/commands/`
2. Check whether `.opencode/opencode.json` already exists.
3. Recommend a small project-local config based on the repo:
   - Minimal/default: only `$schema`, or no file if no local config is needed.
   - Typed codebase that benefits from language-server diagnostics: enable `"lsp": true`.
   - Frontend/browser app where browser debugging is useful: enable the globally-defined `chrome-devtools` MCP locally.
   - Avoid adding MCP servers that are not already defined globally unless the user explicitly asks for that server.
4. If project instructions are missing or weak, recommend using built-in `/init` for `AGENTS.md` rather than duplicating that behavior here.
5. If project-specific reusable behavior is needed, propose a project skill under `.opencode/skills/<name>/SKILL.md`, but do not create one unless the user approves.
6. Show the proposed file contents or merge diff before writing.
7. Ask for approval before creating or modifying files. Do not write immediately just because this command was invoked.
8. If approved, create or update the smallest set of files and validate `opencode debug config` from the project root.

Preferred project-local snippets:

Minimal `.opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json"
}
```

LSP-enabled project:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": true
}
```

Frontend/browser project using globally-defined Chrome DevTools MCP:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": true,
  "mcp": {
    "chrome-devtools": {
      "enabled": true
    }
  }
}
```

Guidelines:

- Global config is for reusable personal defaults, agents, commands, reusable skills, and MCP server definitions.
- Project config is for enabling repo-specific capabilities and adding repo-specific instructions or skills.
- Prefer globally defining MCP command details once, disabled by default, then enabling by name in project config.
- Prefer LSP per project. LSP is useful for diagnostics in some repos but lint/typecheck/test commands may be better.
- Prefer global skills for generic workflows and project skills for repo/domain-specific procedures.
- Keep generated project config concise and easy to commit.
