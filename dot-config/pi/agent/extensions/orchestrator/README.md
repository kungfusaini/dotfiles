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

The task prompt asks hidden Pi workers to end with an optional final footer:

```text
ORCHESTRATOR_RESULT:
{
  "status": "done | blocked | failed",
  "summary": "...",
  "needs_user": false,
  "next_action": null
}
```

If present, the footer must be valid JSON and final non-whitespace output. `orchestrator_worker_poll`, `orchestrator_worker_read`, and `orchestrator_worker_list` parse and store it on the worker record.

If the parsed result has `status: "blocked"` or `needs_user: true`, the worker is marked blocked/needs-user. If it is hidden, it is surfaced once into a new Herdr tab without focus, using the same handoff behavior as `orchestrator_worker_mark(state: "blocked")`.

```text
Start a hidden shell worker that runs npm test and keep the output readable.
```

### `orchestrator_worker_list`

List workers from the shared registry. Listing performs one full-history poll pass first, so worker states and structured result footers are refreshed before display.

### `orchestrator_worker_poll`

Refresh all workers once without dumping full pane output. Polling:

- refreshes lifecycle/visibility from tmux and registry state;
- captures recent output from active/readable workers;
- parses final `ORCHESTRATOR_RESULT` footers;
- auto-surfaces hidden blocked/needs-user workers once in a new Herdr tab without focus;
- returns a compact changed-workers summary.

By default poll scans `5000` lines per worker, matching the managed tmux history limit. This keeps token usage low because captured output is inspected internally but not returned unless there is a compact state change summary. Callers may pass a smaller `lines` value for cheaper targeted polling.

Use this as the parent orchestration heartbeat until a real event loop/watch mode exists. Since there is intentionally no foreground watch loop yet, parent agents should call poll opportunistically between orchestration steps and before deciding workers are idle.

### `orchestrator_worker_status`

Show a compact parent dashboard after one poll pass. Workers are grouped as:

- needs attention;
- running;
- completed;
- failed / uncertain;
- closed, when `includeClosed=true`.

Status lines include the worker name, lifecycle state, visibility/pane, structured result status, summary, and `next_action` when present. This is the preferred quick parent overview when raw output is not needed.

### `orchestrator_worker_mark`

Manually mark a live worker as `blocked` or `running`.

Use this when a worker needs user/parent attention before automatic auth/prompt detection exists.

Important parameters:

- `name`: worker name.
- `state`: `blocked` or `running`.
- `message`: short status/attention message.
- `needsUser`: defaults to `true` for `blocked`, `false` for `running`.

Blocked workers are shown first in `orchestrator_worker_list`. Marking a worker `blocked` always surfaces it into a new Herdr tab without focusing that tab, and reports the blocked state/message to Herdr. Marking it `running` clears `needsUser`; if the worker is visible, the Herdr state is updated and the surfaced pane is closed while the worker continues hidden.

### `orchestrator_worker_read`

Read recent output from a hidden or surfaced worker.

### `orchestrator_worker_send`

Send text/input to a worker.

### `orchestrator_worker_surface`

Attach a hidden worker into Herdr and report it in the agents panel. Manual surface uses a pane split; blocked handoff via `orchestrator_worker_mark(state: "blocked")` uses a new Herdr tab.

### `orchestrator_worker_hide`

Detach Herdr clients and close the surfaced pane while keeping the worker alive hidden.

### `orchestrator_worker_close`

Kill the worker, close any surfaced pane, and mark it closed.

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
- Automatic auth prompt detection and background watching are not implemented yet; blocked/resumed state is explicit/manual via `orchestrator_worker_mark` or worker-declared via final `ORCHESTRATOR_RESULT` parsed during poll/read/list.
- Cleanup/reconciliation is still basic, but missing sessions without exit metadata are marked `orphaned`, not `exited`.
- Surfacing requires Herdr (`HERDR_ENV=1`) and the `herdr` CLI.
