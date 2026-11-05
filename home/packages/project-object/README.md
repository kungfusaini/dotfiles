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

[`bin/project-picker`](bin/project-picker) is a lightweight toggle client for the preloaded GTK4/libadwaita interface in [`bin/project-picker-gui`](bin/project-picker-gui). It dismisses a visible picker or wakes the persistent hidden process, avoiding both duplicate windows and repeated GTK startup cost. Project creation keeps directory selection inside the picker: type path fragments to filter `fd`-discovered directories, use arrows or `Ctrl+J` / `Ctrl+K`, and press `Enter` to select; exact existing paths are also accepted. Each project is a collapsible, workspace-status-neutral header containing an explicit **Project workspace** row followed by its stream rows. The header omits workspace counts and aggregates live Pi agents in open project/stream workspaces with independent indicators: an animated yellow spinner when any open scope has a working agent and a green dot when an open scope has idle/settled agents and no working agents in that same scope. An idle session in a still-working scope does not contribute a green dot. Both appear when separate working and settled scopes coexist, with the green dot before the spinner; neither appears when no open scope has a live agent. Stream-registry error warnings remain visible on the header. On explicit workspace rows, indicators sit at the right edge: a filled green dot means that exact workspace is open with no actively working attached Pi agent, an animated yellow spinner means that exact scope's attached Pi agent is actively working, and a hollow grey dot means closed. Pressing `Space` opens an instant context inspector beside the list. Agents prepare a validated plain-language **Current** and **Next** brief while they are already working, plus an explicit `review`, `decision`, `action`, or `none` attention state; opening the inspector never invokes a model. `d` reveals the underlying bounded worklog detail, and older events fall back to compact worklog/TODO previews. A collapsed project header previews a scope requesting attention first, then settled or active work, then the most recently recorded project or stream context. Selection only previews, while `Enter` remains the sole workspace-switch action. `n` selects the next open scope with an idle/settled agent and no working agents, moving forward from the current selection and wrapping at the end; it expands the destination project, clears any search hiding the target, and centers the highlighted destination vertically (bounded by the list ends). Closed scopes and worklog attention flags without settled live agents are not next-attention targets. The persistent picker preloads context, refreshes every scope while visible so project and stream briefs do not remain stale, and keeps its open state across daemon replacement. Expansion and selection likewise survive hiding and reopening within the Hyprland session. Refreshes retain unchanged row widgets in place, so expanding or collapsing projects does not restart their working spinners. The active Hyprland workspace uses a slim row-edge marker, independently of the keyboard selection highlight. When shown, the picker is moved to the workspace that was active when requested and remains pinned across workspace changes until dismissed. The UI also provides integrated search, project and stream creation, and focus-independent keyboard navigation. The original curses interface remains available as [`bin/project-picker-tui`](bin/project-picker-tui) for fallback and backend reuse.

Global shortcuts:

- `Super+P` — toggle the project picker
- `Super+X` — from an active project or stream workspace, open the picker’s safe close confirmation for that workspace

Picker controls:

- `j` / `k` or `↑` / `↓` — navigate in normal mode, wrapping between the first and last visible entries
- `gg` / `G` — jump to the first or last visible entry
- `/` — enter search mode and filter projects and streams
- `Ctrl+J` / `Ctrl+K` — navigate while searching, wrapping between the first and last visible entries
- `Tab` — expand or collapse the selected project
- `Space` — show or hide the selected scope's context inspector without switching workspace
- `n` — jump to the next project or stream explicitly requesting review, a decision, or an action; legacy idle agents remain a fallback
- `d` — show or hide detailed worklog evidence inside the open inspector
- `Enter` — expand or collapse a project header, or open/focus the selected project or stream workspace
- `Ctrl+N` — create a project
- `Ctrl+Shift+N` — create a stream under the selected project
- `r` — resume the selected stream’s latest Pi chat
- `x` — safely close the selected explicit workspace row after confirmation
- `a` — from a project header, archive the project after confirmation, safely closing its project and stream workspaces while retaining artifacts and Pi sessions
- `Esc` — leave search or close the picker

### Picker briefing protocol

Agents add `brief` to a `project_worklog_append` event when a start, meaningful progress update, decision, blocker, or finish changes the picker-facing state. `brief.current` and optional `brief.next` are each limited to one plain-language sentence of at most 160 characters. `brief.attention` is `review` only for a deliverable awaiting review, `decision` for an explicit choice, `action` for a manual user step, and `none` while work is progressing or merely settled. Detailed evidence stays in `summary`, `result`, `reason`, `lesson`, or `blocker`. The newest event drives the card; live working activity temporarily takes status priority, and the next meaningful event clears or changes prior attention. Legacy events remain readable through deterministic compact fallbacks.

Projects can contain independently openable streams. Each stream receives its own literal Hyprland workspace (`Project · Stream`), inherited project instructions and skills, isolated notes, tasks, plans, local skills and artifacts, stream-scoped worklogs, and a separate Pi session directory. Git-backed streams also receive a shared stream-specific branch and worktree. Registration is immediate; the checkout is prepared on first open. Multi-repository projects require choosing the repository, while explicitly non-code streams can inherit the project directory. Preparation failures never fall back to a shared checkout. The recorded generated branch is the creation default, not the stream's identity: switching or renaming branches in an existing managed worktree does not block entry. Detached HEAD opens with a warning; opening never switches, resets, or renames your branch. The picker still verifies the managed directory and repository identity.

Broken stream records appear as named error rows beneath their project (and an error count on collapsed headers), without preventing healthy projects and streams from opening. Discovery quarantines invalid or ambiguous records without rewriting the registry; registry mutations remain strict, and unreadable stream scopes are retained during session reconciliation rather than silently forgotten. Explicit terminal/Pi attachment can resolve a healthy stream despite an unrelated broken sibling; ambiguous IDs or names remain blocked. Automatic terminal discovery also tolerates unrelated errors, but refuses attachment when the workspace could belong to a quarantined record (including an unreadable project's stream namespace).

The scope boundary and artifact model are defined in [`STREAMS-DESIGN.md`](STREAMS-DESIGN.md).

Only an explicit user request authorizes an agent to call `project_stream_archive`; completing the work does not. When asked to archive its attached stream, the agent writes its finish worklog and uses the archive tool as its final operation. Once the final response settles, a detached lifecycle process snapshots and closes the stream workspace—including the invoking Pi session—and marks the stream archived only after closure succeeds. Managed worktrees and branches are retained to avoid racing background writers and discarding data; cleanup is a separate future lifecycle. The parent project, sibling streams, artifacts, worklogs, and session history remain intact.

Web links are project-aware. In Kitty, a normal click opens or reuses a companion Vivaldi window beside the current project or stream terminal; Shift-click opens the link in the parent project's persistent `Project · Browser` workspace. `Super+B` toggles between the persistent project browser and the live project or stream workspace it was opened from, and falls back to the global `browser` workspace outside Project Object. Browser windows use the normal Vivaldi profile, while runtime window addresses are recorded only to route later links to the intended project window.

Agents open web pages with `project-workspace-exec project-browser open URL [URL ...]`. This always creates one **app-style page window per URL beside the invoking agent**, without switching the user's workspace or taking focus, even if `--mode project` was supplied. It shares the normal Vivaldi process/profile and login state; it does not create per-workspace browser instances. Direct `project-browser open` calls with Pi's agent environment are routed through the same helper. Agent-context `focus` requests are refused. Interactive Kitty links and `Super+B` retain their existing behavior and never reuse agent app windows.

A capability-bound, short-lived loopback redirect gives each app window a unique native app identity, including existing-browser handoffs. Before launching, a narrow named Hyprland rule matches only that identity and requests silent placement plus initial/activation-focus suppression. Launch success requires the specific new mapped window on the invoking workspace and delivery of the redirect, not successful loading/authentication at the destination website. URLs are HTTP(S)-only; the loopback endpoint checks the random path and exact Host, disables caching/referrers, logs neither paths nor targets, and closes after verification or a 15-second timeout. The reusable rule is disabled on exit; no per-launch rule list accumulates. Browser children do not retain Pi or launch context. No debugger or extension is installed. App windows omit normal tabs/address bar; popups and later windows created by the site are not covered by the launch verification. A failed/timed-out launch may leave a window running. Non-Hyprland agent launches fail closed.

The hidden shared-browser regression is `tests/agent_browser_integration.py --hyprland /path/to/Hyprland --hyprctl /path/to/hyprctl --labwc /path/to/labwc --kitty /path/to/kitty --vivaldi /path/to/vivaldi [--helper /path/to/project-workspace-exec] [--router /path/to/project-browser]`. It uses a disposable profile, local test pages/cookies and private headless compositors/DBus, never the live desktop or account data. It checks cold/shared-process launches, a normal tabbed window in that process, same-workspace focus, wrapped/direct Pi calls, multiple URLs, initial-map workspace and transient focus via compositor events. PID and synthetic-cookie assertions establish process/session sharing, not a memory benchmark or real-account OAuth verification.

Agents launch other graphical applications with `project-workspace-exec COMMAND [ARG ...]`. It identifies the Hyprland workspace containing the invoking terminal from process ancestry, falls back to the exact workspace recorded by `project-terminal` (also when one terminal-server PID spans multiple workspaces), and refuses to guess from the globally active workspace. A silent one-shot Hyprland exec rule requests placement beside the agent, even if another workspace is focused. Dispatch success alone is not considered success: a unique inherited launch marker associates a newly mapped window with the launch, including through a waiting Python/shell parent when a sandboxed browser's own environment is unreadable. If necessary, the helper moves that specific window silently and rechecks its actual workspace before returning success. It verifies the first associated new window, not every future window an application might create. Correction happens after mapping, so this is not a guarantee against a transient appearance on the wrong workspace when native placement fails.

The helper waits up to 15 seconds for verified placement. On timeout or a placement error it returns nonzero; the application may still be running. Except for the capability-identified agent browser route above, existing-instance handoffs, environment-stripping applications without a marked ancestor, and applications that do not create a window cannot be verified, and unrelated windows are never moved as a guess. Use an application's fresh-instance option where needed; do not create per-workspace browser profiles as a workaround.

The opt-in real-browser regression is `tests/workspace_exec_integration.py --hyprland /path/to/Hyprland --hyprctl /path/to/hyprctl --labwc /path/to/labwc --kitty /path/to/kitty --chromium /path/to/chromium [--helper /path/to/project-workspace-exec]`. It requires an accessible DRM render node (default `/dev/dri/renderD128`), runs labwc headlessly with a GLES2 allocator, and nests Hyprland with a separate headless test output. All compositor sockets, profiles, and DBus activation are isolated; tests never use the live desktop or global input. It checks real invoking-Kitty ancestry against a stale recorded workspace, a different focused workspace, a wrapped Chromium launch, and recovery after deliberate removal of native launch tokens. The old helper fails the wrapped-browser target assertion under these conditions. Logs remain in the printed temporary directory.

Inside a project or stream, `/init [optional goal]` performs a one-time low-ceremony setup of concise stable scope in `AGENTS.md`, immediate tasks in `TODO.md`, any essential operational guardrail, and a start worklog entry when one is not already present. Existing artifacts and worklog events are preserved and incorporated rather than blocking initialization. Only the completed initialization marker prevents another `/init`. Initialization never begins substantive work or external operations.

Project Object-owned Pi skills live in `skills/<skill-name>/SKILL.md` under the project or stream home, alongside the other durable scope artifacts rather than in a repository. Project sessions load project skills; stream sessions load stream skills first and then inherit project skills. Supporting scripts, references, and assets stay inside the same skill directory. Run Pi's `/reload` after adding or changing a skill. Discovery accepts only direct `SKILL.md` files and singly linked regular supporting files in non-symlinked skill directories contained by the canonical private scope home. Pi loads a private, size-bounded runtime snapshot, while the Project Object directory remains the editable source of truth.

A read-only workspace snapshot can be captured without dispatching, focusing, moving, or closing windows:

```text
project-snapshot --project-id <project-uuid>
```

It writes validated compositor metadata for the project’s live named workspace to `snapshots/workspace.json` inside the Project Object home. For every Project Object-managed Kitty window, the snapshot records each independently identified settled Pi session. Reopening a closed workspace launches every valid captured conversation in deterministic window order with `pi --session`; there is no fixed session-count limit. Closing is refused while any attached Pi agent is working. Unsupported or stale items are skipped and reported without preventing supported Pi sessions from reopening. Kitty geometry and tab/split topology, arbitrary applications, terminal scrollback, unsent editor text, and process memory are not restored yet; multiple sessions from one Kitty window therefore reopen as separate Kitty windows for now.

The hardened implementation also includes:

- strict registry and canonical UUID validation;
- derived, containment-checked XDG project and Pi-session paths;
- private `0700` directories and `0600` state files;
- rollback-aware project creation and workspace opening;
- bounded, error-handled Pi `AGENTS.md` injection;
- canonical, containment-checked project and stream Pi skill discovery;
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
