# Streams

## Decision

A stream is a durable, independently openable scope of work inside a project. Each open stream has its own ordinary named Hyprland workspace, terminal environment, Pi sessions, context, tasks, plans, worklog, and restoration state.

Projects and streams use UUIDs for identity. Human names are mutable labels. A stream workspace is represented literally as:

```text
<Project name> · <Stream name>
```

For example:

```text
Elijah · Forecast Bench
```

Waybar remains generic and displays the literal Hyprland workspace name.

Old-system stream migration is explicitly deferred.

## Scope boundary

The governing rule is:

> Project context flows downward by inheritance. Stream detail flows upward only through summaries or deliberate promotion.

Project context is shared authority. Stream context is local elaboration. A stream must not silently contradict a project constraint.

Information is never synchronized by copying same-named files between scopes.

### Downward inheritance

A stream-scoped agent receives, in order:

1. project `AGENTS.md`;
2. stream `AGENTS.md`;
3. stream-local skills followed by inherited project skills;
4. up to ten newest stream worklog events within an 8 KiB rendered limit;
5. normal repository-local instructions and skills discovered by the coding agent.

Older worklog history, notes, tasks, plans, and repository facts remain available on demand. Project worklogs are not copied into stream context.

### Upward visibility

The project may automatically present a bounded overview of each stream using its lifecycle state, current `TODO.md`, recent meaningful worklog activity, blockers, and next action. This is a derived view, not a project-level copy of stream artifacts.

### Upward promotion

Detailed stream information is not automatically rolled into project artifacts. A project-relevant stream event may request attention and later be deliberately promoted. A promoted project event is a concise project-level statement with a stable reference to its source stream event; it is not a duplicate of the source entry.

Automatic worklog roll-up is out of scope for the first implementation because the previous `projectImpact` mechanism produced both noise and omissions.

## Stream home

The canonical stream home is derived from project and stream UUIDs:

```text
$XDG_DATA_HOME/project-object/projects/<project-id>/streams/<stream-id>/
```

Each stream has the same basic artifact capabilities:

```text
AGENTS.md
NOTES.md
TODO.md
plans/
skills/
worklogs/
snapshots/
```

- `AGENTS.md` contains concise stable scope, context, and instructions loaded into every attached session.
- `NOTES.md` is an informal scratchpad for rough, changing, or unverified material.
- `TODO.md` is the authoritative current task list for the stream, organized around now, next, and waiting work.
- `plans/` contains stream-owned detailed plans when they are useful.
- `skills/` contains Project Object-owned Pi skills as `<skill-name>/SKILL.md`; stream sessions load these before inherited project skills.
- `worklogs/` contains append-only stream history, decisions, blockers, and outcomes.
- `snapshots/` contains system-managed workspace restoration evidence.

Mutable operational facts remain authoritative in the repository or application. Completed work leaves `TODO.md` and is retained in the worklog. A separate context or status file is not created by default because it would duplicate always-loaded guidance, current tasks, or recent history.

The canonical Pi session directory is:

```text
$XDG_STATE_HOME/project-object/projects/<project-id>/streams/<stream-id>/pi-sessions/
```

A stream may override its working directory. Git-backed streams bind to a repository at creation and record a dedicated branch and managed working directory. The worktree is prepared lazily on first open, so registration remains fast; every agent in that stream shares it. A single-repository project is detected automatically, while a multi-repository project requires choosing the repository. Explicitly non-code streams may disable worktree isolation and inherit the project main directory.

Managed worktrees live under `$XDG_DATA_HOME/project-object/worktrees/<project-id>/<stream-id>/`. Opening fails closed if repository discovery, preparation, or identity verification fails; it never falls back to a shared checkout. Archiving preserves both the worktree and its branch because automatic deletion cannot exclude races with background writers. Explicit, separately confirmed garbage collection is deferred.

## Tasks and plans

A task has one owning scope. Project tasks describe cross-stream outcomes; stream tasks describe work owned by that stream. A project task may reference an owning stream, but duplicated TODO entries are not synchronized.

Plans follow the same rule. A stream plan remains local unless it is deliberately replaced or summarized by a project-level plan.

## Workspace lifecycle

The project workspace and each stream workspace can be opened and closed independently. Opening a project does not reopen all streams.

A stream may be initialized once with `/init [optional goal]`. Initialization creates only the minimum durable orientation state and records `.project-object-initialized.json` in the stream home. Existing artifacts and worklog entries are preserved and incorporated; only the completed marker blocks another `/init`. Initialization does not begin substantive work, perform remote operations, or edit project-level artifacts.

Opening a stream creates or focuses its derived named workspace and launches a stream-aware terminal or Pi session. Closing a stream must preserve artifacts and session history, capture restoration evidence, and avoid silently terminating active work.

Renaming an open project or stream must conflict-check and rename its live workspace as part of one operation.

## Deferred work

The first stream implementation does not include:

- importing old stream records or historical chats;
- recursive substreams;
- automatic project-level worklog roll-up;
- full restoration of arbitrary graphical applications;
- cross-machine synchronization.
