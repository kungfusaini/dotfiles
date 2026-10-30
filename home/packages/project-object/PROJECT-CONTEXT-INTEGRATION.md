# Project Context and Pi Integration

## Status

A minimal project-context vertical slice is implemented and tested.

## Project home

Canonical project-owned artifacts live under XDG data:

```text
$XDG_DATA_HOME/project-object/projects/<project-id>/
```

Every project is initialized with:

```text
AGENTS.md
NOTES.md
TODO.md
plans/
snapshots/
worklogs/
```

`AGENTS.md` holds concise stable scope and guidance, `NOTES.md` is an informal scratchpad, and `TODO.md` is the current task list. Mutable operational facts remain authoritative in the repository or application; completed history belongs in the append-only worklog. Separate context and status files are intentionally not created because they duplicate these roles.

The registry stores only the durable UUID and project metadata. `projectHome` is always derived from the validated UUID and current XDG data root. A legacy absolute `projectHome` is accepted only when it exactly equals that canonical path, then removed when the picker next writes the registry. Existing files are never overwritten.

Operational and application state remains separate:

```text
$XDG_STATE_HOME/project-object/projects/<project-id>/
$XDG_RUNTIME_DIR/project-object/
```

## Project-aware terminals

`bin/project-terminal` resolves a project from either:

1. an explicit `--project-id`; or
2. the active human-named Hyprland workspace.

A project terminal inherits:

```text
PROJECT_OBJECT_ID
PROJECT_OBJECT_NAME
PROJECT_OBJECT_HOME
PROJECT_OBJECT_MAIN_DIRECTORY
PI_CODING_AGENT_SESSION_DIR
```

The Pi session directory is project-specific so projects that share a working directory do not share Pi session lookup.

The picker uses this launcher when it opens a closed project. The Hyprland source configuration also uses it for ordinary terminal and Pi shortcuts.

## Pi extension

The canonical extension implementation is committed with the project at:

```text
integrations/pi/project-object.ts
```

The Nix package installs the extension in the immutable store and the Home Manager integration links Pi directly to that packaged file. Hyprland likewise invokes packaged picker and terminal executables rather than mutable checkout paths.

At Pi session start, the extension:

- resolves `PROJECT_OBJECT_ID`, with active-workspace fallback;
- displays `Project: <name>` in Pi's status area;
- exposes `/project` to show the resolved project paths;
- exposes `project_worklog_append` for validated, private, append-only continuity events at `worklogs/events.jsonl`;
- exposes `/catchup [optional focus]` to ask Pi for a concise account of recent work, the stopping point, and the next action using that worklog, the current TODO, relevant notes, and Git evidence.

At session start, the extension securely reads the project-owned `AGENTS.md`, the stream `AGENTS.md` when attached, and up to ten newest events from the attached scope worklog. The instructions are limited to 64 KiB each; the rendered worklog is capped at 8 KiB and omits IDs, file lists, and other structural metadata. Files must be regular, non-symlinked, singly linked where applicable, and contained beneath the canonical UUID scope home. Registry and read failures are surfaced without injecting untrusted content. Repository-local instructions continue loading through Pi's normal discovery.

The bounded startup context is reused for the session rather than regenerated on every message. Older worklog contents, TODOs, notes, plans, Git state, and repository facts remain available on demand through tools or `/catchup`. Pi receives a short instruction to record durable conversational facts and meaningful work when they become clear, without logging casual conversation or secrets.

## Automated tests and isolated harness

`./scripts/test` runs Python compilation, 36 automated tests, Nix evaluation/build checks, and whitespace checks. Coverage includes malformed registries, UUID and uniqueness validation, path escape attempts, legacy migration, archived explicit IDs, private permissions, separate sessions for projects sharing a directory, creation/open rollback, stale picker locks, compositor-instance reset, missing/oversized/symlinked Pi instructions, and private validated worklog appends with symlink rejection.

`./scripts/run-isolated-demo` creates disposable XDG roots and uses a fake Kitty executable. It demonstrates terminal environment propagation plus Pi extension resolution and instruction loading without connecting to the live compositor or user data.

## Earlier manual tests

### Project terminal environment

A fake Kitty executable confirmed that the launcher supplies:

- the exact project ID and name;
- the project home and main directory;
- a project-specific Pi session directory;
- the main directory as Kitty's working directory.

### Pi context injection

A non-interactive Pi run was launched from Elijah's main directory with only the environment supplied by the project terminal. The prompt asked Pi to identify project details from automatically supplied context.

Result:

```text
PROJECT=Elijah; HOME=/home/sumeet/.local/share/project-object/projects/71717bd1-0e66-4fb6-8757-12042fcb2a2a; TODO=TODO.md
```

### Headless video demo

The final demo ran entirely in an isolated Xvfb display with:

- a separate Openbox window manager;
- copied project registry/data;
- separate runtime and state directories;
- a fake isolated compositor-control command;
- X11-only Kitty windows;
- no connection to the live Wayland display or Hyprland socket.

The demo shows:

1. selecting Elijah in the picker;
2. the project terminal's inherited environment;
3. launching ordinary `pi` with no project-specific arguments;
4. Pi displaying `Project context loaded: Elijah` and `Project: Elijah`;
5. `/project` showing the main directory, project home, and agent instructions;
6. the model identifying Elijah, its project home, and `TODO.md` from injected context without reading files.

Video:

```text
/home/sumeet/Videos/project-object/project-context-pi-integration-headless-demo.mp4
```

Preview and review contact sheet:

```text
/home/sumeet/Videos/project-object/project-context-pi-integration-headless-demo.png
/home/sumeet/Videos/project-object/project-context-pi-integration-headless-demo-contact-sheet.png
```

Duration: 77.6 seconds.

## Current limitations

- The final video uses an isolated X display and fake compositor dispatch because a second headless Hyprland instance is not supported by the currently available nested/headless compositor path.
- The real picker and terminal use live `hyprctl`; compositor dispatch itself was not exercised in the headless video.
- A terminal that was launched outside a project and later moved into a project workspace does not retroactively gain project environment variables. The Pi extension can fall back to the active workspace, but project-specific session-directory selection must occur before Pi starts.
- Worklog browsing and editing UI is not implemented; entries are currently written by the Pi tool and consumed on demand by `/catchup`.
