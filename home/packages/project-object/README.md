# System-wide Project Object

## Starting idea

A project should exist as a system-wide object rather than separately inside each application or tool.

## What is a project?

_To define together._

## What belongs to a project?

_To define together._

## Surfaces

Places where a project might appear or be used:

- Desktop
- Terminal
- Agents
- Notes
- Other applications

## Current implementation

The working slice is a native, keyboard-first Hyprland project picker:

```text
Super+P
```

[`bin/project-picker`](bin/project-picker) is a lightweight client for the preloaded GTK4/libadwaita interface in [`bin/project-picker-gui`](bin/project-picker-gui). It focuses an existing window or wakes the persistent hidden process, avoiding both duplicate windows and repeated GTK startup cost. Project creation keeps directory selection inside the picker: type path fragments to filter `fd`-discovered directories, use arrows or `Ctrl+J` / `Ctrl+K`, and press `Enter` to select; exact existing paths are also accepted. Each project is a collapsible, workspace-status-neutral header containing an explicit **Project workspace** row followed by its stream rows. The header summarizes open and total workspaces without inheriting a child workspace state. A separate small header badge aggregates live Pi agents across the project: green takes priority when any agent is idle or settled and may need attention, yellow means agents are working with none waiting, and no badge means no live agent is attached. On explicit workspace rows, a filled green dot means that exact workspace is open with no actively working attached Pi agent, yellow means that exact scope's attached Pi agent is actively working, and a hollow grey dot means closed. Expansion and selection survive hiding, reopening, and daemon replacement within the Hyprland session. The active Hyprland workspace uses a slim row-edge marker, independently of the keyboard selection highlight. When shown, the picker is moved to the workspace that was active when requested and remains pinned across workspace changes until dismissed. The UI also provides integrated search, project and stream creation, and focus-independent keyboard navigation. The original curses interface remains available as [`bin/project-picker-tui`](bin/project-picker-tui) for fallback and backend reuse.

Keyboard controls:

- `j` / `k` or `↑` / `↓` — navigate in normal mode
- `gg` / `G` — jump to the first or last visible entry
- `/` — enter search mode and filter projects and streams
- `Ctrl+J` / `Ctrl+K` — navigate while searching
- `Tab` — expand or collapse the selected project
- `Enter` — expand or collapse a project header, or open/focus the selected project or stream workspace
- `Ctrl+N` — create a project
- `Ctrl+Shift+N` — create a stream under the selected project
- `r` — resume the selected stream’s latest Pi chat
- `x` — safely close the selected explicit workspace row after confirmation
- `a` — from a project header, archive the project after confirmation, safely closing its project and stream workspaces while retaining artifacts and Pi sessions
- `Esc` — leave search or close the picker

Projects can contain independently openable streams. Each stream receives its own literal Hyprland workspace (`Project · Stream`), inherited project instructions, isolated notes, tasks, plans and artifacts, stream-scoped worklogs, and a separate Pi session directory. Git-backed streams also receive a shared stream-specific branch and worktree. Registration is immediate; the checkout is prepared on first open. Multi-repository projects require choosing the repository, while explicitly non-code streams can inherit the project directory. Preparation failures never fall back to a shared checkout. The scope boundary and artifact model are defined in [`STREAMS-DESIGN.md`](STREAMS-DESIGN.md).

An attached stream agent can use `project_stream_archive` after its finish worklog as its final tool operation. Once the final response settles, a detached lifecycle process snapshots and closes the stream workspace—including the invoking Pi session—and marks the stream archived only after closure succeeds. Managed worktrees and branches are retained to avoid racing background writers and discarding data; cleanup is a separate future lifecycle. The parent project, sibling streams, artifacts, worklogs, and session history remain intact.

Web links are project-aware. In Kitty, a normal click opens or reuses a companion Vivaldi window beside the current project or stream terminal; Shift-click opens the link in the parent project's persistent `Project · Browser` workspace. `Super+B` toggles between the persistent project browser and the live project or stream workspace it was opened from, and falls back to the global `browser` workspace outside Project Object. Browser windows use the normal Vivaldi profile, while runtime window addresses are recorded only to route later links to the intended project window.

Agents launch other graphical applications with `project-workspace-exec COMMAND [ARG ...]`. It identifies the Hyprland workspace containing the invoking terminal from process ancestry, falls back to the exact workspace recorded by `project-terminal`, and applies a silent one-shot Hyprland exec rule so the new window opens beside the agent even if another workspace is currently focused. It refuses to guess from the globally active workspace.

Inside a project or stream, `/init [optional goal]` performs a one-time low-ceremony setup of concise stable scope in `AGENTS.md`, immediate tasks in `TODO.md`, any essential operational guardrail, and a start worklog entry when one is not already present. Existing artifacts and worklog events are preserved and incorporated rather than blocking initialization. Only the completed initialization marker prevents another `/init`. Initialization never begins substantive work or external operations.

A read-only workspace snapshot can be captured without dispatching, focusing, moving, or closing windows:

```text
project-snapshot --project-id <project-uuid>
```

It writes validated compositor metadata for the project’s live named workspace to `snapshots/workspace.json` inside the Project Object home. This is capture evidence only; close and restore actions are not implemented yet.

The hardened implementation also includes:

- strict registry and canonical UUID validation;
- derived, containment-checked XDG project and Pi-session paths;
- private `0700` directories and `0600` state files;
- rollback-aware project creation and workspace opening;
- bounded, error-handled Pi `AGENTS.md` injection;
- a private append-only project worklog with a validated Pi append tool, size-bounded recent-event injection at session start, and deeper on-demand `/catchup` retrieval;
- private, atomic, read-only capture of project workspace and window metadata;
- a Nix package and Home Manager module;
- isolated automated tests and a compositor-free demo harness.

Run the checks with:

```text
./scripts/test
./scripts/run-isolated-demo
```

Build the package directly with:

```text
nix-build --no-out-link -E 'with import <nixpkgs> {}; callPackage ./default.nix {}'
```

## Shared API connections (initial slice)

`project-api` stores one API definition per account in a private SQLite catalog at `$PROJECT_OBJECT_DATA_DIR/apis.sqlite` (normally `~/.local/share/project-object/apis.sqlite`). The credential is stored **once** in the desktop Secret Service via `secret-tool`; access rows enable that same connection globally or for selected projects. No API keys go in project repositories or the catalog.

```sh
project-api freeagent-login freeagent --client-id <client-id> \
  --redirect-uri http://127.0.0.1:8765/callback # prompts for app client secret; opens browser
project-api enable freeagent --project-id <project-uuid>
project-api enable freeagent --project-id <another-uuid> # same credential
# or: project-api enable freeagent --global
```

First register an app in the [FreeAgent Developer Dashboard](https://dev.freeagent.com/) and set its redirect URI **exactly** to `http://127.0.0.1:8765/callback` (choose another available port if needed). The login command binds only to loopback, validates OAuth state, exchanges the authorization code, and stores the app secret and rotating tokens in Secret Service. Tokens refresh automatically when needed. To use a test account, add `--sandbox` at login; sandbox and production are different connections. For a second project, run only `project-api enable freeagent --project-id <other-project-uuid>`—do not log in again.

In a Project Object terminal, agents can use `project-api list`, `project-api describe freeagent`, and `project-api request freeagent GET /v2/contacts` (add `--json '{...}'` for JSON writes). Only enabled APIs appear in these commands. Other APIs with static bearer tokens or header keys use `project-api add <id> --base-url https://... --auth bearer`, followed by `project-api credential <id>` and `project-api enable`. Existing CLIs like `gh` stay separate.

OAuth 2.0 authorization-code APIs can reuse `project-api oauth-login <id> --base-url https://api.example.com --authorize-url https://auth.example.com/authorize --token-url https://auth.example.com/token --client-id <id> --redirect-uri http://127.0.0.1:8765/callback` (see `--help` for scopes, PKCE, and client authentication choices). The reusable core handles browser authorization, state/PKCE, token storage, and refresh; FreeAgent only supplies its endpoint settings. Providers that do not issue refresh tokens or use other OAuth flows need separate support.

**Security boundary:** The catalog is private from other Unix users, not from processes running as the same user. An agent with unrestricted shell access can read the SQLite catalog or call Secret Service directly; this scoped CLI is a discoverability/convenience boundary, **not** enforced isolation against such an agent. Genuine project-to-project secret isolation requires process sandboxing or a separate trusted broker. Do not enable sensitive APIs for untrusted agents until that boundary exists.

## Planning documents

- [`ITERATION-ONE.md`](ITERATION-ONE.md) — intended first-iteration behavior and acceptance criteria
- [`PICKER-DESIGN.md`](PICKER-DESIGN.md) — minimum project object and current picker prototype
- [`PROJECT-CONTEXT-INTEGRATION.md`](PROJECT-CONTEXT-INTEGRATION.md) — XDG project homes, project-aware terminals, Pi injection, and demo evidence
- [`STREAMS-DESIGN.md`](STREAMS-DESIGN.md) — stream workspaces, artifacts, inheritance, summaries, and deliberate promotion
- [`HARDENING-REVIEW.md`](HARDENING-REVIEW.md) — resolved review findings, accepted workspace-name risk, and final verification
- [`INTERVIEW-RESPONSES.md`](INTERVIEW-RESPONSES.md) — broader product vision and requirements
- [`STATE-RESTORATION-CAPABILITIES.md`](STATE-RESTORATION-CAPABILITIES.md) — restoration capability audit
- [`RESTORATION-SPIKE.md`](RESTORATION-SPIKE.md) — isolated restoration experiments

## Questions

_To collect and discuss together._
