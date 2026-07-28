# Pi Orchestrator MVP

A small Herdr-backed Pi extension for opening child Pi agents in visible panels.

The goal is intentionally simple: make delegation easy without building a giant orchestration framework.

## What it does

- Opens a new Herdr pane in the current tab by splitting the current pane to the right.
- Starts a child `pi` agent in that pane.
- Gives it a compact handoff prompt, or leaves it for you to drive.
- Optionally creates an isolated git worktree first.
- Tracks the children created during the current Pi session.

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

- Requires Herdr (`HERDR_ENV=1`) and the `herdr` CLI.
- Session worker tracking is lightweight and local to this Pi session/reload history.
- Worktree creation uses `git worktree add`; merge/review/removal are intentionally manual for now.
- Partial failures can leave panes, worktrees, or branches behind; cleanup is manual in this MVP.
- Human-driven mode still submits the initial handoff prompt; it just does not wait or keep controlling the child.
