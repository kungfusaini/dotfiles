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
- `name`: optional stable worker name.
- `cwd`: working directory.
- `visibility`: `hidden` or `visible`; defaults to `hidden`.
- `title`: display title when surfaced.
- `env`: extra environment variables. Keys must match `^[A-Za-z_][A-Za-z0-9_]*$`; values are applied to the worker script but not stored in the registry.
- `cols` / `rows`: initial hidden terminal size; defaults to `140x40`.
- `keepAlive`: keep an interactive shell open after the command exits so output remains readable; defaults to `true`.

Examples:

```text
Start a hidden Pi reviewer named auth-reviewer.
```

```text
Start a hidden shell worker that runs npm test and keep the output readable.
```

### `orchestrator_worker_list`

List workers from the shared registry.

### `orchestrator_worker_read`

Read recent output from a hidden or surfaced worker.

### `orchestrator_worker_send`

Send text/input to a worker.

### `orchestrator_worker_surface`

Attach a hidden worker into Herdr and report it in the agents panel.

### `orchestrator_worker_hide`

Detach Herdr clients from a surfaced worker while keeping it alive hidden.

### `orchestrator_worker_close`

Kill the worker and mark it closed.

## Backend

Workers are backed by real terminal processes in an orchestrator-owned tmux server:

```bash
tmux -L pi-orchestrator -f ${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/tmux.conf
```

Each worker gets its own tmux session and registry file under:

```text
${XDG_STATE_HOME:-~/.local/state}/pi/orchestrator/terminals/registry/<name>.json
```

The shared tmux server is global, but worker mutation is owner-scoped: each worker record stores the owning Pi session id. Other orchestrators can list/read the registry, but mutating actions require the owner session unless `force=true` is supplied intentionally.

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
- Automatic blocked/auth detection is not implemented yet.
- Cleanup/reconciliation is basic: listing marks missing live tmux sessions as `done`; full orphan cleanup is still future work.
- Surfacing requires Herdr (`HERDR_ENV=1`) and the `herdr` CLI.
