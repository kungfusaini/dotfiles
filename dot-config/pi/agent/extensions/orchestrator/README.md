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

## Review-unit orchestration rule

For multi-unit implementation work, the orchestrator should plan **review units** before launching implementation workers.

A review unit is the smallest thing that should be reviewed and merged independently. It can be:

- an Azure ticket or other tracker ticket;
- a GitHub issue;
- a TODO item;
- an explicit user-requested slice;
- an inferred implementation step when the project has no tracker.

Default rule:

- one review unit → one worker scope;
- one review unit → one branch / PR layer when PRs are being produced;
- related review units form a stream/stack based on real dependency or merge order.

Do not assign a broad stream-level implementation task that bundles multiple review units into one worker unless the user explicitly approves grouping. If a worker discovers that its assigned review unit depends on another unplanned unit, it should block and report that dependency instead of expanding scope.

Do not make duplicate workers for the same task. Inspect, reuse, close, or replace the existing worker instead of launching another worker with the same responsibility.

## Stream scouts

Use a **stream scout** when the parent does not yet have enough compact context to safely define review units, dependencies, likely files, and tests for a related stream of work.

A stream scout is a read-only context condenser for one stream. It turns repo/ticket ambiguity into a compact implementation brief and review-unit plan. It does not implement, create branches, open PRs, or launch workers.

Use a stream scout when:

- there are multiple review units in one area/stream;
- the repo area is unfamiliar or large;
- several review units likely share files or architecture;
- dependencies/stack order are unclear;
- existing branches/worktrees/diffs need inspection before assigning implementation.

Skip a stream scout when the parent already has a recent, reliable brief, when there is only one review unit, or when the change is small/local and the files/tests are obvious.

Required scout output is a compact `STREAM_BRIEF` file written under the current Pi stream storage:

```text
<stream-dir>/research/stream-briefs/<stream-slug>.md
```

Do not rely on long terminal output as the brief. The scout should report the brief path and a concise summary when done. The parent should reference the brief file in worklog entries and pass only relevant excerpts to implementers.

The `STREAM_BRIEF` file must include:

- shared context and key files;
- existing relevant behavior;
- review-unit boundaries;
- dependency/stack recommendation;
- likely files and tests per review unit;
- suggested implementer prompt per review unit;
- risks/unknowns.

Scout stop condition: stop once review units, dependencies, shared context, likely files/tests, and implementer prompts are clear enough for the parent to delegate. Do not exhaustively audit.

## Structured worker results

Prefer structured worker state/results over raw transcript reads. Workers should report concise lifecycle messages and final `ORCHESTRATOR_RESULT` summaries. Parent orchestrators should read raw worker output only when a worker is blocked, failed, produced an unclear result, or the next decision requires details not present in the structured result.

Avoid repeatedly reading large worker transcripts. If detailed handoff content is needed, the worker should write a compact artifact file, report the path, and summarize it.

## Preserve blocked workers

Blocked or failed workers may contain valuable investigative context even when their worktree is clean. Do not close blocked/failed workers that contain task context unless the user explicitly approves, or unless a compact handoff summary/artifact has been captured first.

Model-limit/provider-limit workers are preserved state, not disposable failures. Mark them blocked, keep them alive, and ask or plan recovery: resume, swap models, extract findings, or replace only after handoff capture.

## PR-layer invariant check

Run a local PR-layer invariant check before publishing each new or changed PR. Scope the check to the PR layer being created or modified. Avoid full-stack audits unless topology changed or the user requested them.

For the local layer, verify:

- assigned review unit matches the branch/PR title and body;
- PR claims only that review unit unless grouping was explicitly approved;
- intended base matches the review-unit/stream plan;
- branch name matches the project/review unit and has no obvious wrong-project contamination;
- diff against the intended base does not obviously include unrelated review-unit work;
- relevant tests were run or the skip is explained.

## Responsibility boundaries

- Parent orchestrator owns review units, stream/stack topology, worker launch, PR-layer checks, and user-facing synthesis.
- Stream scouts are read-only context condensers. They write `STREAM_BRIEF` files and do not implement, create branches/PRs, or launch workers.
- Review-unit implementers own exactly one review unit by default, stay within scope, run relevant tests, and report files/tests/blockers.
- Shell/test workers run deterministic commands only and do not edit code.
- All workers stop when their assigned output or decision is clear enough; they do not keep reading or auditing for completeness beyond the task.

## Model routing

- Model routing is the parent orchestrator's decision per worker.
- Keep the parent/current model for review, planning, architecture, final synthesis, and high-stakes judgement unless the user asks otherwise.
- Choose Spark high for smaller scoped orchestrator Pi workers by setting `command: "pi --model openai-codex/gpt-5.3-codex-spark:high"`.
- Spark high is a good fit for focused implementation, bugfixes, tests, repo inspection, first-pass reviews, and parallel subagent work.
- Do not choose Spark high when the task needs image input, very large context beyond Spark's 128K window, deep architectural judgement, or final review.

## Tools

### `orchestrator_worker_start`

Start a worker. Workers are hidden by default.

Important parameters:

- `kind`: `pi` or `shell`; defaults to `pi`.
- `command`: command to run. Defaults to `pi` for `kind=pi`; required for `kind=shell`.
- `task`: task prompt to send after startup. Supported for `kind=pi` workers.
- `handoffPrompt`: optional parent-written context included in the hidden Pi task prompt.
- `recentInteractions`: number of recent user/assistant interactions to include in the handoff bundle; defaults to `0`.
- `includeToolCalls`: include compact tool call/result summaries in recent interactions; defaults to `false`.
- `handoffMaxChars`: maximum rendered handoff context size; defaults to `12000`.
- `name`: optional stable worker name.
- `workspace`: `current` or `worktree`; defaults to `current`.
- `branch`: branch name for `workspace=worktree`; defaults to `pi-orch/<worker-name>`.
- `base`: base ref for `workspace=worktree`; defaults to `HEAD`.
- `worktreePath`: checkout path for `workspace=worktree`; defaults to `<repo-parent>/.worktrees/<repo>/<worker>`.
- `cleanupWorktreeOnClose`: remove orchestrator-created worktree on close if clean; defaults to `true` for worktree workers.
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

For implementation work that spans multiple review units, prepare the review-unit/stack plan before calling this tool. A single worker should normally receive one review unit only, with the branch/base/expected PR layer named in the task.

Optional handoff fields let the parent pass only text context: an explicit `handoffPrompt`, plus the last `recentInteractions` user/assistant messages. Tool calls/results are omitted by default; when `includeToolCalls=true`, only compact summaries are included, bounded by `handoffMaxChars`.

For `workspace=worktree`, the worker is still based on the current git repository. The orchestrator creates an adjacent checkout by default under `<repo-parent>/.worktrees/<repo>/<worker>`, starts the worker there, and records the source repo, branch, base, and path. `orchestrator_worker_close` attempts `git worktree remove`; if the worktree is dirty or removal fails, it is preserved and the cleanup error is stored on the worker record. After a clean worktree removal, close also tries safe branch cleanup with `git branch -d`; unmerged branches are preserved and reported instead of force-deleted.

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

### `orchestrator_worker_start_many`

Start multiple workers in one tool call. This is intentionally simple: `workers` is an array of normal `orchestrator_worker_start` inputs, so each worker can have distinct `task`, `command`, `workspace`, `handoffPrompt`, branch, and cleanup settings.

Before launching multiple implementation workers, define the review units and stream/stack order. Each worker should own exactly one review unit by default, and each review unit should map to one branch/PR layer when PRs are expected. Use multiple workers to parallelize independent review units, not to create broad workers that each bundle a whole stream. Do not make duplicate workers for the same task.

Example shape:

```json
{
  "workers": [
    { "name": "api", "kind": "pi", "task": "Inspect API changes", "workspace": "worktree" },
    { "name": "tests", "kind": "shell", "command": "npm test", "workspace": "worktree" }
  ]
}
```

Starts are attempted in order. By default later workers still start if one fails; set `continueOnError: false` to stop on the first failure.

### `orchestrator_report_state`

Report lifecycle state from inside an orchestrator-created worker without reading or writing terminal transcript content. Worker identity is inferred from orchestrator-injected environment variables, so a child worker cannot report state for sibling workers.

Supported states:

- `working`: worker is actively handling the delegated task.
- `blocked`: worker needs parent/user attention; `needsUser` defaults to `true`.
- `done`: worker has semantically completed, even if the Pi process remains alive at a prompt.
- `failed`: worker failed or cannot continue.
- `unknown`: worker cannot determine its own state.

Hidden Pi task prompts ask subagents to call this tool when blocking, resuming, and finishing. The older `ORCHESTRATOR_RESULT` footer remains a manual poll/read fallback.

### `orchestrator_worker_list`

List workers from the shared registry. By default this is session-scoped and only shows workers owned by the current Pi session. Pass `scope=all` for an explicit global admin view. Listing performs one poll pass first, so worker states and structured result footers are refreshed before display.

### `orchestrator_worker_poll`

Refresh workers once without dumping full pane output. Polling:

- refreshes lifecycle/visibility from tmux and registry state;
- captures recent output from active/readable workers;
- parses final `ORCHESTRATOR_RESULT` footers;
- auto-surfaces hidden blocked/needs-user workers once in a new Herdr tab without focus;
- returns a compact changed-workers summary.

By default poll scans `5000` lines per worker, matching the managed tmux history limit. This keeps token usage low because captured output is inspected internally but not returned unless there is a compact state change summary. Callers may pass a smaller `lines` value for cheaper targeted polling.

Polling remains available as an explicit transcript-inspection fallback. It is no longer the only heartbeat: the extension also starts a lightweight background watcher for workers owned by the current Pi session.

### `orchestrator_worker_status`

Show a compact parent dashboard after one poll pass. By default this is session-scoped; pass `scope=all` for global inspection. Workers are grouped as:

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

Read recent output from a hidden or surfaced worker. By default this only allows workers owned by the current Pi session; pass `scope=all` for explicit global inspection.

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

The shared tmux server is global, but worker mutation is owner-scoped: each worker record stores the owning Pi session id. Default list/read/status/poll behavior is also owner-scoped; pass `scope=all` for explicit global inspection. Mutating actions still require the owner session unless `force=true` is supplied intentionally.

Do not use `scope=all` for normal task management. Use global inspection only when the user explicitly asks to inspect global, orphaned, or other-session workers, or when debugging orchestrator infrastructure. Normal orchestration should stay scoped to the current parent/session so unrelated workers do not pollute status, planning, or follow-up decisions.

## State model

Worker lifecycle state is separate from visibility.

Lifecycle states:

- `starting`: registry created and tmux launch in progress.
- `running`: worker process appears alive.
- `blocked`: worker is known to need user/parent attention. Set explicitly with `orchestrator_worker_mark`, worker-declared through `orchestrator_report_state`, or parsed from a structured footer during explicit poll/read.
- `done`: worker reported semantic completion through `orchestrator_report_state` or a parsed structured footer, even if the process remains alive.
- `exited`: command exited with status `0` without an explicit semantic `done` report.
- `failed`: command exited nonzero, exited by signal, failed to start, or reported `failed`.
- `closed`: orchestrator explicitly closed the worker.
- `orphaned`: registry exists but the backend tmux session is missing and no exit metadata proves a normal exit.
- `unknown`: refresh could not determine state.

Visibility states:

- `hidden`: no current Herdr pane is attached.
- `visible`: surfaced into a Herdr pane.
- `unknown`: visibility could not be determined.

`orchestrator_worker_list` refreshes worker records before displaying them. Missing tmux sessions are **not** treated as done unless exit metadata or tmux pane status proves the command exited. Default worker discovery only includes workers owned by the current Pi session.

## Background watcher

When `PI_ORCHESTRATOR_WATCH` is not `0`/`false`/`off`/`no`, the parent extension starts one in-process watcher after this Pi session creates an active worker. The watcher is extension-owned but session-scoped:

- it only observes records whose `ownerSessionId` matches the current Pi session;
- default list/read/status/poll calls only observe records whose `ownerSessionId` matches the current Pi session, unless `scope=all` is used explicitly;
- it stops once that session has no active delegated workers (`starting`, `running`, `blocked`, `unknown`, or `orphaned`);
- it refreshes tmux liveness and the per-worker lifecycle state file;
- it updates the registry and Herdr agent state for already-surfaced panes;
- when an owned worker first enters `blocked`, `done`, `exited`, or `failed`, it queues a hidden `followUp` message with `triggerTurn: true` so the parent agent handles the result immediately;
- the parent agent decides whether to inspect more output, continue the workflow or dispatch follow-up workers, or send the user a final/update message;
- each actionable lifecycle event is persisted as handled so watcher ticks do not trigger duplicate parent turns, while a later transition back into `blocked` can wake the parent again;
- it does **not** capture pane output, parse transcripts, auto-surface hidden workers, or clean worktrees.

The parent Pi process must remain running for automatic follow-up turns. Managed workers may continue in tmux after Pi exits, but no live parent chat exists to notify until a later session explicitly inspects them.

The watch interval defaults to `2500ms` and can be bounded with `PI_ORCHESTRATOR_WATCH_INTERVAL_MS` (`1000ms` minimum, `30000ms` maximum). Registry writes use per-worker lock directories plus atomic renames so multiple Pi processes do not write the same worker record concurrently. Ownership filtering prevents one Pi session's watcher from mutating another session's delegated workers.

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
- Automatic auth prompt detection is not implemented yet; blocked/resumed state is explicit/manual via `orchestrator_worker_mark`, worker-declared via `orchestrator_report_state`, or worker-declared via final `ORCHESTRATOR_RESULT` parsed during explicit poll/read/list.
- Cleanup/reconciliation is still basic, but missing sessions without exit metadata are marked `orphaned`, not `exited`.
- Surfacing requires Herdr (`HERDR_ENV=1`) and the `herdr` CLI.
