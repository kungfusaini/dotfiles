# OpenCode instruction/config discovery and ways to hide repository instructions

Date: 2026-06-22

## Question
How does OpenCode discover and read `AGENTS.md` and other agent-related instruction/config files, and how can a user prevent OpenCode from reading or seeing those files without modifying the target repository or creating a branch?

## Executive summary
- Confirmed: OpenCode loads global and project instruction files automatically. Docs name `AGENTS.md`, `CLAUDE.md`, global `~/.config/opencode/AGENTS.md`, and custom `instructions`; source also includes deprecated `CONTEXT.md` for project discovery.
- Confirmed: no documented narrow `--no-agents` / `disable instructions` option was found.
- Confirmed from source, not the CLI env-var table: `OPENCODE_DISABLE_PROJECT_CONFIG=1` disables project config scanning and project-level automatic instruction discovery, but not global instructions.
- Best practical options without repo changes: use `OPENCODE_DISABLE_PROJECT_CONFIG=1`; or run against an isolated copy/overlay that hides instruction/config files; or use a narrower worktree/boundary where possible.

## Sources
- Rules docs: https://opencode.ai/docs/rules/
- Config docs: https://opencode.ai/docs/config/
- CLI docs: https://opencode.ai/docs/cli/
- Permissions docs: https://opencode.ai/docs/permissions/
- Agents docs: https://opencode.ai/docs/agents/
- Instruction source: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/instruction.ts
- Config source: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/config/config.ts
- Paths source: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/config/paths.ts
- Flags source: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/core/src/flag/flag.ts
- Project context source: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/project/project.ts and https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/project/instance-context.ts
- Issue #31697: https://github.com/anomalyco/opencode/issues/31697
- Issue #30233: https://github.com/anomalyco/opencode/issues/30233
- Issue #6479: https://github.com/anomalyco/opencode/issues/6479

## Detailed notes

### Automatic instruction loading
Confirmed from docs: `AGENTS.md` provides project rules; project rules apply in that directory and subdirectories; global rules can live at `~/.config/opencode/AGENTS.md`; Claude Code compatibility supports project `CLAUDE.md`, global `~/.claude/CLAUDE.md`, and `.claude/skills`; `OPENCODE_DISABLE_CLAUDE_CODE`, `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT`, and `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` disable Claude compatibility only. https://opencode.ai/docs/rules/

Confirmed from source: `session/instruction.ts` defines global files as `~/.config/opencode/AGENTS.md` then `~/.claude/CLAUDE.md` unless Claude prompt compatibility is disabled. It defines project instruction files as `AGENTS.md`, `CLAUDE.md` unless disabled, and deprecated `CONTEXT.md`. For project-level system instructions it uses `findUp(file, ctx.directory, ctx.worktree)` and the first file type with matches wins. https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/instruction.ts

Confirmed from source/docs: `config.instructions` can add local globs or remote URLs. Remote instructions are fetched with a 5-second timeout. https://opencode.ai/docs/rules/ and https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/instruction.ts

Confirmed from source: when the agent reads a file, `Instruction.resolve()` walks upward from the read file toward the session root and can attach nearby instruction files not already loaded as system instructions. Nested `AGENTS.md` files can therefore appear later during file reads. https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/instruction.ts

### Config and agent-related discovery
Confirmed from docs: config precedence is remote `.well-known/opencode`, global config, `OPENCODE_CONFIG`, project `opencode.json`, `.opencode` directories, `OPENCODE_CONFIG_CONTENT`, managed config, and macOS managed preferences. Config files are merged, not replaced. `OPENCODE_CONFIG_DIR` adds a custom config directory for agents/commands/modes/plugins and is loaded after global and `.opencode` directories, so it can override settings. https://opencode.ai/docs/config/

Confirmed from source: project config loading is gated by `!Flag.OPENCODE_DISABLE_PROJECT_CONFIG`; OpenCode finds `opencode.json/jsonc` by walking up from the instance directory to `ctx.worktree`. `.opencode` directory discovery is also skipped when the flag is set, while global config and `OPENCODE_CONFIG_DIR` still load. https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/config/config.ts and https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/config/paths.ts

### Mechanisms assessed
- `OPENCODE_DISABLE_PROJECT_CONFIG=1`: source-confirmed. Suppresses project `AGENTS.md`/`CLAUDE.md`/`CONTEXT.md`, project `opencode.json`, and project `.opencode` directories. Does not suppress global `~/.config/opencode/AGENTS.md`, remote/managed config, or explicit instructions from non-project config. Sources: `flag.ts`, `config.ts`, `paths.ts`, `session/instruction.ts`.
- `OPENCODE_DISABLE_CLAUDE_CODE*`: documented. Disables Claude compatibility only, not `AGENTS.md`. https://opencode.ai/docs/rules/
- `--pure`: documented as “Run without external plugins”; not an instruction-disable switch. https://opencode.ai/docs/cli/
- Permissions (`read`, `glob`, `grep`, `external_directory`): useful for tool calls, not reliable for automatic instruction ingestion. In #6479, `external_directory: deny` did not stop parent `AGENTS.md` loading. https://github.com/anomalyco/opencode/issues/6479 and https://opencode.ai/docs/permissions/
- `watcher.ignore`: affects watching noisy paths, not instruction discovery. https://opencode.ai/docs/config/
- Agent `disable`, `hidden`, `permission`, `permission.task`: controls agents/subagents/tools, not repository instruction loading. https://opencode.ai/docs/agents/

## Tradeoffs
- `OPENCODE_DISABLE_PROJECT_CONFIG=1` is the cleanest built-in switch found, but it is broad: it disables project `opencode.json`, `.opencode/agents`, commands/plugins/modes, and project instruction files together.
- Running from a subdirectory helps only if OpenCode’s worktree boundary excludes the unwanted file. Inside the same git repo, source indicates discovery walks to the git worktree boundary, so root `AGENTS.md` usually remains visible.
- Copy/overlay/sandbox approaches avoid repo changes but can affect paths, symlinks, file watching, and write-back.
- Custom config paths are additive/overriding; they do not replace all project discovery because configs are merged.

## Recommendations
1. For a session that should not read project instruction/config files, prefer:

   ```sh
   OPENCODE_DISABLE_PROJECT_CONFIG=1 opencode /path/to/repo
   OPENCODE_DISABLE_PROJECT_CONFIG=1 opencode run --dir /path/to/repo "..."
   ```

   Add `OPENCODE_CONFIG` or `OPENCODE_CONFIG_CONTENT` for model/permission settings if needed, but avoid project-relative `instructions` in that combination; #30233 reports they can silently fail to resolve. https://github.com/anomalyco/opencode/issues/30233

2. If only Claude compatibility is unwanted, use:

   ```sh
   OPENCODE_DISABLE_CLAUDE_CODE=1 opencode /path/to/repo
   ```

   This still reads `AGENTS.md`.

3. If you need project config but not repo `AGENTS.md`, no official narrow switch was found. Use filesystem isolation: copy/rsync to a temp directory excluding `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `.opencode/`, and possibly `opencode.json`; or use an overlay/bind/sandbox that hides those names. Also hide nested instruction files if needed.

4. Do not rely on permissions or watcher ignore rules to block automatic instruction loading.

## Open questions
- `OPENCODE_DISABLE_PROJECT_CONFIG` exists in source but is not listed in the official CLI env-var table; treat it as less stable than documented options.
- No implemented narrow “disable only AGENTS.md” switch was found. Issue #31697 requested one but was auto-closed; a bot mentioned duplicate #17990, not retrieved in this pass.
- Filesystem overlay recommendations are inferred from source behavior, not documented OpenCode features.
