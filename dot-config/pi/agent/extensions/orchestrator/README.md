# Pi Orchestrator MVP

A small Pi extension for running orchestrator workers/subagents that can be hidden or surfaced in Herdr.

The goal is intentionally simple: make delegation easy without building a giant orchestration framework. A Herdr pane is only a visibility surface; the worker itself lives in the orchestrator-managed terminal backend.

## Mental model

There is one public concept: a **worker**.

A worker can be:

- a Pi subagent (`kind: pi`);
- a shell command/process (`kind: shell`).

A worker can be:

- hidden in the managed backend;
- surfaced into a Herdr pane;
- hidden again;
- read, sent input, or closed.

Herdr panes and tmux sessions are implementation details, not separate user-facing worker types.

## Tools

### `orchestrator_worker_start`

Start a worker. Workers are hidden by default.

Important parameters:

- `kind`: `pi` or `shell`; defaults to `pi`.
- `command`: command to run. Defaults to `pi` for `kind=pi`; required for `kind=shell`.
- `task`: task prompt to send after startup. Supported for `kind=pi` workers.
- `name`: optional stable worker name.
- `cwd`: working directory.
- `visibility`: `hidden` or `visible`; defaults to `hidden`.
- `title`: display title when surfaced.
- `env`: extra environment variables. Keys must match `^[A-Za-z_][A-Za-z0-9_]*$`; values are applied to the worker script but not stored in the registry.
- `cols` / `rows`: initial hidden terminal size; defaults to `140x40`.
- `keepAlive`: after command exit, open an interactive shell instead of exiting; defaults to `false`. Completed output remains readable because tmux keeps exited panes inspectable.
- `taskPromptTimeoutMs`: for `kind=pi` plus `task`, maximum time to wait for prompt/readiness before sending the task anyway; defaults to `8000`.

Examples:

```text
Start a hidden Pi reviewer named auth-reviewer with task "Review the current diff".
```

For `kind=pi` plus `task`, the orchestrator starts `pi`, polls the hidden terminal for prompt/readiness, then sends a compact task prompt. If readiness is not detected before `taskPromptTimeoutMs`, it sends the task anyway and records `promptReadyTimedOut` on the worker.

```text
Start a hidden shell worker that runs npm test and keep the output readable.
```

### `orchestrator_worker_list`

List workers from the shared registry.

### `orchestrator_worker_mark`

Manually mark a live worker as `blocked` or `running`.

Use this when a worker needs user/parent attention before automatic auth/prompt detection exists.

Important parameters:

- `name`: worker name.
- `state`: `blocked` or `running`.
- `message`: short status/attention message.
- `needsUser`: defaults to `true` for `blocked`, `false` for `running`.

Blocked workers are shown first in `orchestrator_worker_list`. Marking a worker `blocked` always surfaces it into a new Herdr tab without focusing that tab, and reports the blocked state/message to Herdr. Marking it `running` clears `needsUser`; if the worker is visible, the Herdr state is updated and the worker is hidden again without killing it.

### `orchestrator_worker_read`

Read recent output from a hidden or surfaced worker.

### `orchestrator_worker_send`

Send text/input to a worker.

### `orchestrator_worker_surface`

Attach a hidden worker into Herdr and report it in the agents panel. Manual surface uses a pane split; blocked handoff via `orchestrator_worker_mark(state: "blocked")` uses a new Herdr tab.

### `orchestrator_worker_hide`

Detach Herdr clients from a surfaced worker while keeping it alive hidden.

### `orchestrator_worker_close`

Kill the worker and mark it closed.

## Backend

Workers are backed by real terminal processes in an orchestrator-owned tmux server:

```bash
tmux -L pi-orchestrator -f ${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/tmux.conf
```

Each worker gets its own tmux session, registry file, and exit metadata file under:

```text
${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/registry/<name>.json
${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/exit/<name>.json
```

The shared tmux server is global, but worker mutation is owner-scoped: each worker record stores the owning Pi session id. Other orchestrators can list/read the registry, but mutating actions require the owner session unless `force=true` is supplied intentionally.

## State model

Worker lifecycle state is separate from visibility.

Lifecycle states:

- `starting`: registry created and tmux launch in progress.
- `running`: worker process appears alive.
- `blocked`: worker is known to need user/parent attention. Currently set explicitly with `orchestrator_worker_mark`; automatic detection is future work.
- `exited`: command exited with status `0`.
- `failed`: command exited nonzero, exited by signal, or failed to start.
- `closed`: orchestrator explicitly closed the worker.
- `orphaned`: registry exists but the backend tmux session is missing and no exit metadata proves a normal exit.
- `unknown`: refresh could not determine state.

Visibility states:

- `hidden`: no current Herdr pane is attached.
- `visible`: surfaced into a Herdr pane.
- `unknown`: visibility could not be determined.

`orchestrator_worker_list` refreshes worker records before displaying them. Missing tmux sessions are **not** treated as done unless exit metadata or tmux pane status proves the command exited.

## Current cutover state

The public API is `orchestrator_worker_*` only.

Removed public APIs:

- `orchestrator_delegate`
- `orchestrator_list`
- `orchestrator_focus`
- `orchestrator_read`
- `orchestrator_prompt`
- `orchestrator_terminal_start`
- `orchestrator_terminal_list`
- `orchestrator_terminal_read`
- `orchestrator_terminal_send`
- `orchestrator_terminal_surface`
- `orchestrator_terminal_hide`
- `orchestrator_terminal_close`

The old managed terminal implementation remains internally as the worker backend.

## Limitations

- `kind=pi` currently starts `pi` in the managed terminal; hidden Pi control is still raw terminal read/send until surfaced.
- Worktree creation is not part of the worker API yet.
- Automatic blocked/auth detection is not implemented yet; blocked/resumed state is explicit/manual via `orchestrator_worker_mark`.
- Cleanup/reconciliation is still basic, but missing sessions without exit metadata are marked `orphaned`, not `exited`.
- Surfacing requires Herdr (`HERDR_ENV=1`) and the `herdr` CLI.
