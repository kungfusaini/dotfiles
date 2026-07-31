# Pi and Herdr terminal workflow tools

Date: 2026-07-17

## Question

Identify the likely projects behind “Pi” as an alternative to opencode and “herdr” as an alternative to tmux, then compare them against the current stack: kitty, opencode, nvim, tmux. Cover purpose, architecture/workflow model, install/setup, provider or terminal/session semantics, config/extensibility, maturity/activity, license, limitations, migration cost, and whether they are worth trying.

## Executive summary

- **Pi is almost certainly Pi Coding Agent**, official site `https://pi.dev`, repo `earendil-works/pi`, npm package `@earendil-works/pi-coding-agent`. Its own site calls it a “minimal agent harness” with extensions, skills, prompt templates, themes, tree-structured session history, and 15+ providers. It is a direct opencode-class tool, not a terminal multiplexer. Sources: https://pi.dev, https://github.com/earendil-works/pi/tree/main/packages/coding-agent, https://www.npmjs.com/package/@earendil-works/pi-coding-agent
- **Herdr is clearly Herdr**, official site `https://herdr.dev`, repo `ogulcancelik/herdr`. It is an agent-aware terminal multiplexer: persistent PTYs, workspaces/tabs/panes, detach/reattach, SSH remote attach, semantic agent states, plugin/API surface. It is a tmux/Zellij-class replacement only if the main tmux use is persistent agent/session management. Sources: https://herdr.dev, https://github.com/ogulcancelik/herdr, https://herdr.dev/docs/concepts/
- **Recommendation:** try both, but do it without migration. Run Pi beside opencode for a few real tasks. Run Herdr beside tmux for agent-heavy sessions. Do not rewrite config until one tool proves daily value.
- **Main risk:** both are young and moving fast. Pi’s extension-first design skips built-ins opencode already has. Herdr is AGPL/commercial dual-licensed and Windows is beta; its agent state detection can be imperfect.

## Identity and ambiguity

### Pi

Confirmed likely project: **Pi Coding Agent**.

- Official site: https://pi.dev
- Source repo: https://github.com/earendil-works/pi, coding agent under `packages/coding-agent`.
- npm package: https://www.npmjs.com/package/@earendil-works/pi-coding-agent
- Current npm package metadata observed: version `0.80.10`, binary `pi`, Node engine `>=22.19.0`, license MIT. Source: npm package metadata at https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest

Ambiguity notes:

- “Pi” is a generic name and also overlaps with unrelated products such as Inflection’s Pi chatbot and Raspberry Pi tooling. The terminal coding-agent context points to Pi Coding Agent because pi.dev explicitly describes a terminal coding harness and compares itself to other agent harnesses. Source: https://pi.dev
- GitHub search also finds adjacent “Pi” ecosystem packages such as `pi-subagents`, but those appear to extend Pi rather than being the core project. Example: https://github.com/edxeth/pi-subagents

### Herdr

Confirmed project: **Herdr**.

- Official site: https://herdr.dev
- Source repo: https://github.com/ogulcancelik/herdr
- Install/docs: https://herdr.dev/docs/install/

Ambiguity notes:

- The project name is distinctive in the terminal/tmux context. Search results and official docs align on `ogulcancelik/herdr` as “agent multiplexer that lives in your terminal.” Source: https://github.com/ogulcancelik/herdr

## Pi vs current opencode workflow

### Purpose

Pi is a terminal AI coding agent harness. It overlaps directly with opencode’s TUI/CLI coding-agent workflow. Pi’s self-description is “a minimal terminal coding harness” and “adapt pi to your workflows, not the other way around.” Source: https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/README.md

opencode is also an open-source AI coding agent with terminal UI, desktop app, IDE extension, config, providers, agents, MCP, plugins, LSP, permissions, and snapshots. Sources: https://opencode.ai/docs/, https://opencode.ai/docs/config/

### Architecture and workflow model

Pi:

- Four modes: interactive TUI, print/JSON, RPC over stdin/stdout, and SDK embedding. Source: https://pi.dev and README section “Four modes” / “Programmatic Usage”.
- Built-in tools include read, bash, edit, write, grep, find, ls; tools can be allowlisted or disabled from CLI. Source: README CLI reference at https://github.com/earendil-works/pi/tree/main/packages/coding-agent
- Sessions are JSONL trees stored under `~/.pi/agent/sessions/`; `/tree` lets you jump to prior points and branch inside one session file. Source: README “Sessions” and “Branching”.
- Queued steering/follow-up messages can be submitted while the agent is working. Source: README “Message Queue”.

opencode:

- Terminal-based interface plus desktop app and IDE extension. Source: https://opencode.ai/docs/
- Has built-in `build` and `plan` agents, plus subagent support. Source: opencode README, https://raw.githubusercontent.com/sst/opencode/dev/README.md
- Has snapshots for undo/revert of file changes, enabled by default. Source: https://opencode.ai/docs/config/#snapshot

Interpretation: Pi is more of a programmable harness; opencode is more batteries-included. If your opencode setup already relies on global/project agents, MCP, permissions, LSP, and opencode-specific worklog/subagents, Pi will need extension or package equivalents.

### Install/setup

Pi install options:

- `curl -fsSL https://pi.dev/install.sh | sh`
- `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`
- pnpm/bun equivalents. Source: https://pi.dev and README quick start.
- Requires Node `>=22.19.0` when installed from npm. Source: npm package metadata https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest

opencode install options include install script, npm/bun/pnpm/yarn, Homebrew tap, Arch packages, Windows package managers, Docker, mise, and Nix. Source: https://opencode.ai/docs/

Migration cost: low to try, medium/high to switch. Pi uses `~/.pi/agent` and `.pi/` instead of opencode’s `~/.config/opencode` and `.opencode/`. Existing opencode agents/commands/skills/plugins are not drop-in compatible even though both understand AGENTS.md-style instructions.

### Model/provider support

Pi:

- Built-in subscriptions: Anthropic Claude Pro/Max, OpenAI ChatGPT Plus/Pro, GitHub Copilot. Source: README “Providers & Models”.
- API-key providers include Anthropic, OpenAI, Azure OpenAI, Bedrock, Mistral, Groq, Cerebras, xAI, OpenRouter, Vercel AI Gateway, Hugging Face, Fireworks, Together AI, Kimi, MiniMax, Xiaomi MiMo, OpenCode Zen/Go, and others. Source: README “Providers & Models”.
- Custom providers can be added with `~/.pi/agent/models.json` if they speak supported OpenAI/Anthropic/Google APIs; custom APIs or OAuth require extensions. Source: README “Custom providers & models”.

opencode:

- Uses AI SDK and Models.dev to support 75+ providers and local models. Source: https://opencode.ai/docs/providers/
- Supports OpenCode Zen/Go, many provider integrations, local backends such as Ollama/LM Studio/llama.cpp via OpenAI-compatible configs, and custom provider definitions. Source: https://opencode.ai/docs/providers/

Interpretation: both are broad enough for your likely providers. opencode’s provider directory appears larger and more documented; Pi’s subscription support and custom provider hooks are still strong.

### Config/extensibility

Pi:

- Global config under `~/.pi/agent/settings.json`; project config in `.pi/settings.json`. Source: README “Settings”.
- Loads `AGENTS.md` or `CLAUDE.md` from global and parent/current directories; supports `SYSTEM.md` and `APPEND_SYSTEM.md`. Source: README “Context Files”.
- Extensibility primitives: TypeScript extensions, skills following Agent Skills standard, prompt templates, themes, and Pi packages from npm/git. Source: README “Customization”.
- Extensions can register tools, commands, keyboard shortcuts, event handlers, UI components, providers, compaction, permission gates, sandboxing, MCP integration, etc. Source: README “Extensions”.
- Security caveat: Pi packages run with full system access. Source: README “Pi Packages”.

opencode:

- JSON/JSONC config, merged across remote, global, project, custom, `.opencode`, inline, and managed config locations. Source: https://opencode.ai/docs/config/
- Supports agents, custom commands, tools, themes, keybinds, LSP, MCP servers, plugins, policies, permissions, formatter config, instructions, and config variables. Source: https://opencode.ai/docs/config/

Interpretation: Pi is likely nicer if you want to hack the harness itself. opencode is likely nicer if you want stable declarative config without writing TypeScript extensions.

### Maturity/activity/license

Confirmed facts:

- Pi repo `earendil-works/pi`: created 2025-08-09, pushed 2026-07-17, TypeScript, MIT, high GitHub activity/star count in API results. Source: https://api.github.com/repos/earendil-works/pi
- npm package current observed version: `0.80.10`, published through GitHub Actions trusted publisher metadata. Source: https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest
- Pi README warns new issues and PRs from new contributors are auto-closed by default, with maintainer review. Source: https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/README.md

Interpretation: Pi is active and popular, but still pre-1.0 and philosophy-driven. Expect churn.

### Known limitations

Pi intentionally does not include some features:

- No MCP in core, no sub-agents, no permission popups, no plan mode, no built-in todos, no background bash. Its docs say to build/install extensions or use tmux. Source: https://pi.dev “What we didn't build” and README “Philosophy”.
- Install/update telemetry exists unless disabled; `PI_TELEMETRY=0`, `enableInstallTelemetry=false`, `PI_SKIP_VERSION_CHECK=1`, or `PI_OFFLINE=1` control related startup network behavior. Source: README “Telemetry and update checks”.

For this stack, those omissions matter because opencode already has built-in plan/build agents, permissions, MCP, subagents, snapshots, and managed config. Source: https://opencode.ai/docs/config/

### Is Pi worth trying?

Yes, as a side-by-side experiment. Use it when you want:

- A minimal, programmable harness.
- Tree-structured session branching.
- Easy custom extensions/packages.
- Subscription auth options across Claude/OpenAI/Copilot.

Do not replace opencode immediately if you depend on:

- opencode MCP/LSP/permissions/snapshots/subagents.
- Existing `.opencode` and `~/.config/opencode` workflow.
- Stable team/project config.

Minimal trial plan: install Pi, run it in one non-critical repo, disable telemetry/offline if desired, and do 2–3 real tasks comparing output quality, intervention burden, and config friction.

## Herdr vs current tmux/kitty/nvim workflow

### Purpose

Herdr is an agent-aware terminal multiplexer and workspace manager. It keeps real terminal processes running, adds structure, and tracks agent state. Source: https://herdr.dev and https://herdr.dev/docs/concepts/

It does not replace kitty as the terminal emulator. Herdr’s site says “Ghostty, Kitty, iTerm, Alacritty: your terminal stays.” Source: https://herdr.dev

It may replace tmux for some workflows, especially persistent remote agent sessions. It is not a Neovim replacement.

### Architecture and workflow model

Core model:

- Workspaces contain tabs; tabs contain panes; panes are real terminals. Source: https://herdr.dev/docs/concepts/
- Herdr runs as a background server plus one or more clients. The server owns panes/processes; the client is the UI. Detach with `ctrl+b q`; panes keep running. Source: https://herdr.dev/docs/concepts/ and https://herdr.dev/docs/persistence-remote/
- Named sessions are separate server namespaces with their own panes, tabs, workspaces, sockets, and runtime state. Source: https://herdr.dev/docs/persistence-remote/
- Modes include terminal mode, prefix mode, and navigate mode; default prefix is `ctrl+b`, similar to tmux. Source: https://herdr.dev/docs/concepts/

Agent-aware semantics:

- Agent states are `blocked`, `working`, `done`, `idle`, and `unknown`; sidebar state rolls up to tabs/workspaces. Source: https://herdr.dev/docs/concepts/ and https://herdr.dev/docs/agents/
- Supports many agents including Pi, OpenCode, Claude Code, Codex, Cursor Agent CLI, Amp, Gemini CLI partially, etc. Source: https://herdr.dev/docs/agents/
- Integrations add richer state/session restore; unsupported agents still run as normal terminals. Source: https://herdr.dev/docs/agents/

Compared to tmux:

- tmux gives durable terminal sessions and mature scripting.
- Herdr gives durable sessions plus agent state, clickable panes, plugin/API surface, remote attach, direct agent attach, and agent-oriented waits/reads. Source: https://herdr.dev and https://herdr.dev/docs/socket-api/

### Install/setup

Herdr install options:

- Linux/macOS stable install script: `curl -fsSL https://herdr.dev/install.sh | sh`. Source: https://herdr.dev/docs/install/
- Homebrew: `brew install herdr`. Source: https://herdr.dev/docs/install/
- mise: `mise use -g herdr`. Source: https://herdr.dev/docs/install/
- Nix flake: `nix run github:ogulcancelik/herdr/v0.x.y`, release tags recommended. Source: https://herdr.dev/docs/install/
- Manual binaries from GitHub releases. Source: https://herdr.dev/docs/install/
- Windows is preview-only beta. Source: https://herdr.dev/docs/install/

For the current stack: using kitty on macOS is compatible; Herdr runs inside kitty. If Nix-managed dotfiles are preferred, the flake route is likely the cleanest trial.

### Terminal/session semantics

Confirmed semantics:

- Panes are real PTYs; Herdr renders output, sends input, and preserves panes across detach. Source: https://herdr.dev/docs/concepts/
- Remote attach can work by SSHing and running Herdr remotely, or via `herdr --remote workbox` as a local thin client to a remote Herdr server. Source: https://herdr.dev/docs/persistence-remote/
- `herdr --remote` uses OpenSSH auth, can install a matching remote binary interactively, bridges local clipboard/image paste, and can use local keybindings. Source: https://herdr.dev/docs/persistence-remote/
- Direct attach can open one agent/terminal instead of the full UI. Source: https://herdr.dev/docs/persistence-remote/ and https://herdr.dev/docs/agents/
- Herdr can run inside tmux as the outer terminal, but if a Herdr pane itself auto-enters tmux, Herdr sees `tmux` rather than the hidden agent process. Source: https://herdr.dev/docs/agents/

Implication: Avoid nesting tmux inside Herdr for agent panes if you want agent detection. For trial, run Herdr either outside tmux or with tmux only outside as a temporary safety net.

### Config/extensibility

Config:

- Config file at `~/.config/herdr/config.toml` on Linux/macOS and `%APPDATA%\herdr\config.toml` on Windows. Source: https://herdr.dev/docs/configuration/
- Works without config; `herdr --default-config` prints full defaults. Source: https://herdr.dev/docs/configuration/
- Configurable shell, cwd policy, worktree directory, remote SSH behavior, keybindings, themes, sidebar rows, notifications, sound, kitty graphics, agent session restore, IME behavior, env vars, logs. Source: https://herdr.dev/docs/configuration/

Extensibility:

- CLI and socket API can create/list/focus/rename/close workspaces/tabs, split/focus/read/send panes, control agents, report state, subscribe to events, install integrations, stop/reload server. Source: https://herdr.dev/docs/socket-api/
- Raw socket API is newline-delimited JSON over Unix socket / Windows named pipe. Source: https://herdr.dev/docs/socket-api/
- Plugins are manifest-based workflow tools with actions, event hooks, pane entrypoints, and link handlers. Source: https://herdr.dev/docs/socket-api/#plugin-apis
- Marketplace claims 150+ community plugins, auto-discovered from GitHub topic `herdr-plugin`. Source: https://herdr.dev and https://herdr.dev/plugins/

nvim integration:

- There is a community `vim-herdr-navigation` plugin described as Ctrl+h/j/k/l navigation across Herdr panes and Vim/Neovim splits. Source: GitHub search result https://github.com/paulbkim-dev/vim-herdr-navigation
- Treat this as supporting evidence, not core maturity proof.

kitty integration:

- Herdr explicitly supports running inside kitty as the terminal stays. Source: https://herdr.dev
- Experimental kitty graphics rendering exists and is disabled by default. Source: https://herdr.dev/docs/configuration/#kitty-graphics

### Maturity/activity/license

Confirmed facts:

- Herdr repo `ogulcancelik/herdr`: created 2026-03-27, pushed 2026-07-17, Rust, active issues/discussions, high GitHub activity/star count in API results. Source: https://api.github.com/repos/ogulcancelik/herdr
- README says stable Linux/macOS, Windows beta, one Rust binary, no Electron. Source: https://github.com/ogulcancelik/herdr
- License is dual: AGPL-3.0-or-later for open source, commercial licenses available. Source: https://github.com/ogulcancelik/herdr README license section. GitHub API shows SPDX `NOASSERTION`, so use README/license files as the clearer source.

Interpretation: impressive momentum but very young. tmux remains far more proven.

### Known limitations

- Windows native support is preview-only beta. Source: https://herdr.dev/docs/install/
- Agent blocked detection is deliberately strict; unusual/new agent prompts may show as `idle` instead of `blocked` until manifests are updated. Source: https://herdr.dev/docs/agents/#blocked-state
- Unsupported agents still run, but may not get rich state unless integration/reporting is added. Source: https://herdr.dev/docs/agents/
- If tmux is launched inside a Herdr pane, Herdr sees `tmux` as the foreground process instead of the agent. Source: https://herdr.dev/docs/agents/#detection-manifests
- Updating can require stopping old servers when protocol changes; stopping exits pane processes unless live handoff applies. Source: https://herdr.dev/docs/install/#update
- License matters: AGPL may be fine for personal dotfiles/use, but organizations embedding/modifying/network-serving it should review obligations or use commercial license. Source: README license section https://github.com/ogulcancelik/herdr

### Migration cost from tmux

Low to try, medium to adopt, high to replace fully.

- Key prefix defaults to `ctrl+b`, so basic muscle memory overlaps with tmux. Source: https://herdr.dev/docs/concepts/
- tmux config/plugins/statusline/session restore scripts will not transfer directly.
- nvim pane navigation needs a Herdr-compatible plugin or custom keybindings.
- Existing tmux scripts should be rewritten using Herdr CLI/socket API only after Herdr proves itself.
- If your tmux usage is mainly “keep agents alive and reattach over SSH,” Herdr maps well. If it is deep tmux scripting/status/plugin workflows, keep tmux.

### Is Herdr worth trying?

Yes, especially for parallel AI agents and remote sessions. It is probably not worth replacing tmux globally yet.

Best trial:

- Install Herdr without touching tmux config.
- Run one agent-heavy session in kitty outside tmux: one workspace with opencode/Pi/Claude/Codex panes plus logs/tests.
- Test detach/reattach, agent state accuracy, nvim navigation, remote attach if relevant.
- Keep tmux as fallback until Herdr survives a week of real sessions.

## Side-by-side summary

| Area | Current stack | Pi | Herdr |
|---|---|---|---|
| Primary role | opencode = AI coding agent; tmux = multiplexer; kitty = emulator; nvim = editor | Replaces/augments opencode | Replaces/augments tmux |
| Runs in kitty | Yes | Yes, terminal TUI | Yes, explicitly keeps terminal emulator |
| nvim relationship | opencode/tmux external to nvim | External agent; can edit files | Multiplexer around nvim panes; community nav plugin exists |
| Persistence | opencode sessions; tmux panes survive detach | JSONL tree sessions; no background bash, recommends tmux | Persistent PTY server; detach/reattach; named sessions |
| Providers | opencode 75+ providers via AI SDK/Models.dev | 15+ providers plus subscriptions/custom | Not an LLM provider; runs agents as terminals |
| Extensibility | opencode JSONC, agents, MCP, LSP, plugins, skills | TypeScript extensions, skills, prompts, themes, packages | TOML config, CLI/socket API, plugins/integrations |
| Maturity | opencode active and already configured | Active, MIT, pre-1.0 package | Active, young, AGPL/commercial, Windows beta |
| Migration cost | Already paid | Medium/high to replace opencode config | Medium/high to replace tmux config |
| Worth trying? | Baseline | Yes, side-by-side | Yes, agent-heavy side-by-side |

## Recommendations

1. **Try Pi as a challenger, not a replacement.** Its biggest advantage is hackability. Its biggest cost is rebuilding opencode conveniences through extensions/packages.
2. **Try Herdr for exactly the workflow tmux is weak at: many AI agents.** It is designed around semantic agent states and persistent PTYs.
3. **Do not migrate config yet.** Install/run manually or through a temporary Nix shell/profile. Only add dotfile config after repeated use.
4. **Keep tmux for stable remote work until Herdr proves reliable.** Herdr’s velocity is good, but tmux is battle-tested.

## Open questions

- Does Pi support every provider/auth route currently used in your opencode config, especially NanoGPT/OpenRouter custom routes, without a custom extension?
- How well does Herdr’s OpenCode integration detect your specific opencode version and permission/blocking UI?
- Does Herdr fit your nvim navigation muscle memory well enough, or would it require custom key work?
- Are AGPL obligations acceptable for your intended Herdr usage outside personal local use?

## Sources

- Pi official site: https://pi.dev
- Pi coding-agent README: https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/README.md
- Pi repo API metadata: https://api.github.com/repos/earendil-works/pi
- Pi npm package metadata: https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest
- Pi subagents adjacent project: https://github.com/edxeth/pi-subagents
- Herdr official site: https://herdr.dev
- Herdr README: https://raw.githubusercontent.com/ogulcancelik/herdr/master/README.md
- Herdr repo API metadata: https://api.github.com/repos/ogulcancelik/herdr
- Herdr install docs: https://herdr.dev/docs/install/
- Herdr concepts: https://herdr.dev/docs/concepts/
- Herdr agents: https://herdr.dev/docs/agents/
- Herdr persistence/remote: https://herdr.dev/docs/persistence-remote/
- Herdr configuration: https://herdr.dev/docs/configuration/
- Herdr socket API/plugins: https://herdr.dev/docs/socket-api/
- opencode intro: https://opencode.ai/docs/
- opencode config: https://opencode.ai/docs/config/
- opencode providers: https://opencode.ai/docs/providers/
- opencode README: https://raw.githubusercontent.com/sst/opencode/dev/README.md
