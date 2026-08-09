# Pi Orchestrator MVP

A small Herdr-backed Pi extension for opening child Pi agents in visible panels.

The goal is intentionally simple: make delegation easy without building a giant orchestration framework.

## What it does

- Opens a new Herdr pane in the current tab by splitting the current pane to the right.
- Starts a child `pi` agent in that pane.
- Gives it a compact handoff prompt, or leaves it for you to drive.
- Optionally creates an isolated git worktree first.
- Tracks the children created during the current Pi session.
- Starts hidden/background terminal workers in a shared orchestrator-managed tmux server, then reads, sends input, surfaces, hides, or closes them on demand.

## Mental model

There are only two big choices.

### Workspace mode

| Mode | Use when | Behavior |
| --- | --- | --- |
| `current` | review/debug/read-only help on the current dirty tree | child starts in the same cwd |
| `worktree` | independent implementation/experiments | child starts in a new git worktree + branch |

A worktree is **not** automatic. For reviewing current uncommitted changes, use `current` so the child can see the exact same working tree.

### Driver

| Driver | Behavior |
| --- | --- |
| `parent` | Pi sends the task, waits for the child to settle, reads recent output, and closes the child pane by default |
| `human` | Pi starts the child and submits the initial handoff without waiting; the panel stays open for you to drive |

## Tools

### `orchestrator_delegate`

Start a child Pi agent.

Important parameters:

- `task`: the child task.
- `name`: optional worker name; defaults to a generated name.
- `workspace`: `current` or `worktree`.
- `driver`: `parent` or `human`.
- `permission`: `read-only` or `edit`; defaults to `read-only` for `current`, `edit` for `worktree`.
- `branch`: optional worktree branch name.
- `worktreePath`: optional worktree checkout path.
- `focus`: focus the new panel after creation.
- `closeOnDone`: for `driver=parent`, close the child pane after reading its output. Defaults to `true`. Set `false` to leave it open for follow-up/debugging.

Examples:

```text
Delegate a read-only review of my current changes to another Pi.
```

```text
Spin up an implementer in a worktree for the parser cleanup. Let me drive it.
```

### `orchestrator_list`

List child agents created by this extension in the current session.

### `orchestrator_focus`

Focus a child agent panel by name.

### `orchestrator_read`

Read recent terminal output from a child agent panel.

### `orchestrator_prompt`

Send a follow-up prompt to a child agent. Can optionally wait for it to settle.

## Hidden managed terminals

The orchestrator can also run real terminal processes hidden in tmux, then attach the same live terminal into Herdr when user attention is needed.

All orchestrator instances share one tmux server:

```bash
tmux -L pi-orchestrator -f ${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/tmux.conf
```

Each worker gets its own tmux session and registry file under:

```text
${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/registry/<name>.json
```

The shared tmux server is global, but worker mutation is owner-scoped: each worker record stores the owning Pi session id. Other orchestrators can list/read the registry, but mutating actions require the owner session unless `force=true` is supplied intentionally.

### `orchestrator_terminal_start`

Start a hidden terminal worker.

Important parameters:

- `command`: shell command to run.
- `name`: optional worker name; it is slugged/validated and made unique if already recorded.
- `cwd`: working directory; defaults to current Pi cwd.
- `env`: extra environment variables. Keys must match `^[A-Za-z_][A-Za-z0-9_]*$`; values are applied to the worker script but not stored in the registry.
- `cols` / `rows`: initial hidden terminal size; defaults to `140x40` to avoid tiny-terminal TUI crashes.
- `keepAlive`: keep an interactive shell open after the command exits so output remains readable; defaults to `true`.
- `surface`: immediately attach the terminal into Herdr.

### `orchestrator_terminal_list`

List managed terminal workers from the shared registry.

### `orchestrator_terminal_read`

Read recent output with `tmux capture-pane` without surfacing the terminal.

### `orchestrator_terminal_send`

Send text/Enter to a hidden or surfaced terminal with `tmux send-keys`.

### `orchestrator_terminal_surface`

Create a Herdr pane, attach the tmux session, and report pane metadata/session/agent state so the surfaced worker appears in Herdr's agents panel.

### `orchestrator_terminal_hide`

Detach Herdr clients from the tmux session while keeping the terminal process alive hidden.

### `orchestrator_terminal_close`

Kill the tmux session and mark its registry record closed.

## Context handoff policy

The handoff prompt is deliberately compact. It includes:

- task
- workspace mode
- cwd/worktree path
- edit permission
- expected output

It does **not** paste the parent conversation, worklog, or loaded instructions by default. Child Pi agents receive normal Pi startup context and can use their own tools to inspect files or fetch worklog recap if needed.

## Safety defaults

- `current` workspace defaults to `read-only`.
- `worktree` workspace defaults to `edit`.
- worktrees are created outside the repo under `${XDG_DATA_HOME:-~/.local/share}/pi/orchestrator/worktrees` unless `worktreePath` is supplied.
- relative `worktreePath` values are resolved against the parent Pi cwd.
- parent-driven delegates close their child pane after completion by default.
- human-driven delegates stay open by default.
- no third-party packages are installed.

Important: `permission` is currently a prompt-level policy, not a sandbox. A `read-only` child is instructed not to edit, but it still runs a normal Pi agent unless you add stronger tool restrictions later.

## Limitations

- Visible child-agent delegation and terminal surfacing require Herdr (`HERDR_ENV=1`) and the `herdr` CLI. Hidden terminal start/read/send/hide/close use `tmux` directly unless surfacing is requested.
- Session worker tracking is lightweight and local to this Pi session/reload history.
- Worktree creation uses `git worktree add`; merge/review/removal are intentionally manual for now.
- Partial failures can leave panes, worktrees, branches, tmux sessions, or terminal registry files behind; cleanup is manual in this MVP.
- Human-driven mode still submits the initial handoff prompt; it just does not wait or keep controlling the child.
