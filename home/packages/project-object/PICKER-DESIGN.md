# Project Picker — First Vertical Slice

## Status

**Minimal prototype implemented for review.** This narrows the first implementation step to the smallest useful project object and a global Hyprland picker. It does not yet implement application capture, restoration, or project-local role workspaces.

Prototype command:

```text
bin/project-picker
```

## Objective

Make a project feel like something Hyprland knows how to enter:

1. press one global shortcut;
2. type part of a project name;
3. press Enter;
4. arrive at that project's workspace.

The first prototype should also be capable of creating projects and should establish seams for later close, archive, and restoration behavior without attempting all of that immediately.

## Minimum project object

The picker needs only this durable identity:

```text
Project
  id              stable, opaque identity
  name            user-visible name
  mainDirectory   existing absolute directory
  archivedAt      absent or timestamp
  createdAt       timestamp
  updatedAt       timestamp
```

### Meaning

- `id` is the project identity. It does not change when the project is renamed or its directory moves.
- `name` is for people and must be unique case-insensitively.
- `mainDirectory` is the default place from which project tools can later be launched. It does not define project identity and does not need to be unique.
- `archivedAt` controls whether the project appears in the normal picker.
- The timestamps support stable ordering and later migration without expanding the conceptual model.

The first slice does **not** need streams, repositories, applications, windows, agents, tasks, notes, commands, or restoration data inside the core project record.

## Durable, runtime, and observed state

These kinds of state should remain separate.

### Durable project state

Survives Hyprland and machine restarts:

- project identity;
- name;
- main directory;
- archive status;
- later, retained restoration snapshots.

Suggested location:

```text
$XDG_DATA_HOME/project-object/projects.json
```

### Hyprland-session runtime state

Valid only for the current compositor session:

```text
SessionState
  hyprlandInstance
  openProjectIds
```

Suggested location:

```text
$XDG_RUNTIME_DIR/project-object/session.json
```

The runtime record must be discarded or reinitialized when the Hyprland instance signature changes. Projects therefore begin closed after login, as already required.

### Observed compositor state

Read from `hyprctl` when needed:

- active workspace;
- existing workspaces;
- windows assigned to each workspace;
- focused window.

Observed Hyprland state is evidence about the desktop, not the project registry.

## Why open state cannot be inferred from workspaces

Hyprland removes an empty workspace when it is left. A project must not become closed merely because its last window was closed. Therefore:

- **open** means the project ID is in the current session's `openProjectIds`;
- a project's workspace may temporarily be absent when it is open but empty;
- selecting that project recreates or selects its named workspace;
- **close** is an explicit lifecycle action that removes the project from `openProjectIds`, after capture and cleanup are implemented.

This preserves the distinction between switching away and closing.

## Hyprland workspace identity

For the first slice, each project has exactly one ordinary named Hyprland workspace.

For the prototype, the Hyprland workspace name is the human project name:

```text
name:Elijah
```

The stable UUID remains the project identity in the registry and session state; it is not exposed as the workspace label. Waybar remains generic and displays the literal Hyprland workspace name without project-specific translation.

Workspace-name conflicts are user-managed. The system does not reserve global names or add a namespace. It only refuses to create or open a closed project when a live Hyprland workspace with the same visible name already exists, preventing accidental takeover. A future rename action must apply the same live-conflict check and rename an open workspace as part of the operation.

One workspace per project is intentionally narrower than the eventual project-plus-role model. The naming and representation of later role workspaces remain deferred; the initial single workspace should not pretend to solve that model.

## Current project

For the first slice, a project is current when its project workspace is the active Hyprland workspace.

This is deliberately simple. The meaning of “current project” while visiting global workspaces such as `comms`, `music`, or the existing global `browser` remains a later desktop-model decision.

## Picker views

The prototype is one terminal UI hosted in a dedicated floating Kitty window. Project selection, filtering, creation, validation, and errors remain inside that surface rather than exposing a chain of unrelated launchers and dialogs.

Kitty is only the current host for the TUI; it does not define project identity. The directory browser is an explicit replaceable integration.

### Main view

Example:

```text
Projects

Search: eli

STATE      PROJECT
● current  Elijah
○ open     Aether
· closed   Project Object
```

Markers:

- `●` current;
- `○` open;
- `·` closed.

Pressing Enter on a project performs the normal action:

- current: safely remain there;
- open: switch to its workspace;
- closed: mark it open and enter its workspace.

The submitted value should carry the project ID separately from the displayed name, or be resolved against the exact selected registry row. User-entered arbitrary text must never be interpreted as a project ID.

### Create flow

`Ctrl+N` opens a form inside the same TUI with two labelled fields:

1. `Project name`;
2. `Main directory`.

Selecting the directory field opens a directory-browser view inside the same TUI. It deliberately uses a small Yazi-like interaction without handing control to another process:

- Up and Down select a row;
- Right enters the highlighted directory;
- Left returns to the parent directory;
- typing filters the visible directories;
- Enter chooses either the highlighted directory or the explicit `Use this directory` row;
- Escape returns to the creation form without choosing.

Keeping this browser inside the picker gives the project flow one visual and keyboard model. External terminal file-manager adapters can be reconsidered later if they expose a sufficiently reliable chooser protocol.

Validation occurs before writing anything:

- non-empty name;
- case-insensitively unique name;
- absolute existing directory;
- cancellation at either step leaves no project record.

After one atomic registry write, the project is marked open and its workspace becomes active.

### Manage flow

Destructive or lifecycle-changing actions should not share the normal Enter path. A deliberate second-level view can remain inside the TUI:

1. choose `Manage projects`;
2. choose a project;
3. choose an action such as Rename, Change directory, Close, or Archive;
4. confirm actions that remove live state.

Only Rename and Change directory are needed to exercise the project object itself. Close and Archive can be exposed as disabled or explicitly unimplemented until their semantics are wired safely.

### Archived view

The archived view lists only archived projects. Selecting one should offer Restore rather than opening it. Restoration clears `archivedAt` and returns the project to the normal picker; it does not open it.

This view can wait until archive behavior is implemented, but the main picker should reserve a clear route to it.

## System wiring

The current system already defines:

```text
Super+Space -> wofi --show drun
```

Current binding path:

```text
Hyprland shortcut -> floating Kitty -> project-picker TUI -> Hyprland/project backend
```

The launcher command should use a non-blocking lock under `$XDG_RUNTIME_DIR` so pressing the shortcut twice does not create duplicate pickers.

The chosen shortcut is:

```text
Super+P -> project picker
```

This replaces the previous `Super+P` pseudo-layout binding. `Super+Space` remains the application launcher.

The source-of-truth Hyprland configuration is:

```text
/home/sumeet/.config/nixos/home/modules/hypr.nix
```

The generated live configuration is:

```text
/home/sumeet/.config/hypr/hyprland.conf
```

Implementation should change the Nix source, not hand-edit the generated file.

## Backend boundary

Even if the prototype is one script, its internal boundary should behave like a small command/backend rather than coupling project behavior to terminal rendering:

```text
project list [--archived]
project create --name NAME --directory PATH
project open ID
project current
project status ID
project rename ID NAME
project set-directory ID PATH
project picker
```

Later commands can be added without changing the picker contract:

```text
project close ID
project archive ID
project restore ID
project capture ID
```

The backend owns validation, locking, atomic writes, session-state checks, and Hyprland dispatch. The picker owns only display and user selection.

## First prototype boundary

The first runnable prototype should do only this:

1. load a small registry containing real or disposable projects;
2. open globally through a manually invoked command first;
3. show current, open, and closed projects in one terminal UI;
4. filter by project name;
5. open or switch to a stable named Hyprland workspace;
6. create a project with name and existing directory;
7. avoid duplicate picker instances;
8. survive malformed state with a useful error rather than overwriting it.

It should **not yet**:

- move existing windows;
- infer project membership from windows or directories;
- capture or restore application state;
- close windows or processes;
- implement project-local browser, terminal, notes, or agent roles.

## Prototype success test

The vertical slice is successful when:

1. the picker opens globally in one consistent floating terminal surface;
2. selecting a closed project enters the human-named project workspace and marks it open for this Hyprland session;
3. switching elsewhere and selecting it again returns to the same workspace;
4. selecting another project leaves the first project's windows running;
5. a project with no remaining windows still appears open until explicitly closed or Hyprland restarts;
6. creating a project validates its name and directory and then enters it;
7. cancelling leaves both durable and runtime state unchanged;
8. repeated shortcut presses focus the existing picker rather than intentionally creating another picker.

## Current prototype choices

These choices are intentionally provisional and should be judged by using the prototype:

1. `Super+P` opens one floating Kitty-hosted TUI.
2. Typing filters projects; arrow keys navigate; Enter opens; `Ctrl+N` creates; Escape clears the search or closes the picker.
3. Project creation and directory navigation both remain inside the same TUI.
4. Opening a closed, new, or otherwise not-open-this-session project enters its workspace and launches Kitty in `mainDirectory`.
5. Switching to an already-open project does not launch another Kitty window.
6. The registry begins empty; projects are created explicitly through the picker.
7. Close, archive, restore, rename, and directory editing are not exposed yet.
