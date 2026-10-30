# Iteration One — Global Project Picker

## Status

**Draft for review.** This document defines user-visible behavior and acceptance criteria only. It does not choose an architecture, storage format, language, launcher, or Hyprland workspace strategy.

## Goal

Provide one fast, system-wide way to create, find, enter, leave, archive, and restore explicitly declared projects.

The iteration succeeds when project switching feels like an operating-system action rather than an action performed inside a terminal or a particular application.

## Scope

Iteration one supports:

- opening the picker from anywhere in Hyprland;
- listing non-archived projects;
- creating a project;
- opening a closed project;
- switching to an already-open project;
- closing an open project while retaining its restorable state;
- archiving a project;
- viewing and restoring archived projects.

Iteration one does not support:

- streams or substreams;
- agent discovery, status, attention, or navigation;
- worktrees;
- worklogs or catch-up briefings;
- project or stream task lists;
- cross-machine synchronization;
- automatic project inference;
- permanent deletion;
- deleting project files or repositories;
- tool-specific project identity;
- a final terminal, tmux, Kitty, browser, or notes model.

Iteration one may still integrate with current applications for state capture and restoration. Those integrations must remain replaceable and must not define project identity.

## Terms

To avoid overloading the word “active,” this draft uses four distinct concepts:

- **Current project:** the project the user is presently working in. At most one project is current.
- **Open project:** a project whose live workspace exists. Open projects continue running when another project becomes current.
- **Closed project:** a known project with no live workspace. Its retained state can be used when it is opened again.
- **Archived project:** a project hidden from the normal picker. Archiving does not delete its record, retained state, directories, repositories, or files.

A project can be open without being current. “Non-archived project” is used where earlier notes used the ambiguous phrase “active project.”

## Global picker

### Opening

- A global Hyprland shortcut opens the picker regardless of the focused application.
- The picker does not require an existing terminal.
- Invoking the shortcut again should not create duplicate picker instances.
- Cancelling the picker returns the user to the unchanged current context.

The exact shortcut and picker UI are not specified here.

### Normal view

- The default view lists every non-archived project.
- Archived projects are excluded from the default view.
- The current project is visibly distinguishable.
- Open and closed projects are visibly distinguishable.
- A project can be found by typing part of its name.
- Rows remain concise.

For iteration one, a row needs only:

- project name;
- lifecycle state: current, open, or closed.

Agent attention and current-stream information are deferred because their underlying concepts are outside this iteration.

### Interaction

- Keyboard-only operation is sufficient for every required flow.
- The normal action on a selected project opens it if closed or switches to it if already open.
- Create, close, archive, and archived-project actions are available deliberately and are harder to trigger accidentally than opening or switching.
- A failed action leaves the project registry and current desktop context in a coherent state and reports a useful error.

## Project creation

### Minimum

Creating a project asks for:

1. a project name;
2. a main directory.

The system does not infer projects by scanning directories, repositories, windows, or running processes.

On successful creation:

- one new non-archived project exists;
- creating the project does not alter or take ownership of the directory’s contents;
- the project can immediately be selected from the normal picker;
- the project is opened and made current.

Creation can be cancelled without leaving a partial project.

### Validation

- The main directory must already exist.
- Project names must be unique using a case-insensitive comparison.
- Multiple projects may use the same main directory because project identity is not directory identity.

## Open and switch

### Opening a closed project

Selecting a closed project:

1. creates or reconstructs its live project workspace;
2. makes it the current project;
3. takes the user to its last-used project location when one has been retained;
4. does not automatically close the previously current project.

### Switching to an open project

Selecting an already-open project:

1. makes it current;
2. takes the user to its last-used project location;
3. leaves the project being switched away from open;
4. leaves that project’s applications and processes running.

Selecting the already-current project is safe and idempotent.

## Close

Closing is different from switching away.

Closing a project should:

1. capture as much restorable state as the relevant applications and system surfaces expose;
2. report capture failures before destroying live state and allow the user to cancel when practical;
3. remove its live project workspace;
4. stop project-owned processes that this system knows about and manages;
5. mark the project closed;
6. keep it in the normal picker;
7. preserve its identity and references;
8. never delete its underlying directories, repositories, or files.

If the current project is closed, the system returns the user to the Home workspace. Iteration one only requires Home to provide this stable fallback location; richer Home/global-space semantics remain deferred.

Closing should require confirmation when it will stop managed processes or close windows.

## Saved-state behavior

Closing and reopening should preserve **as much state as is practically available** from each relevant application and system surface. The boundary should be discovered by examining what those tools can reliably capture and restore, rather than by excluding application state in advance.

The target includes:

- project identity and metadata;
- main-directory association;
- lifecycle state;
- Hyprland workspaces, windows, and placement;
- the last-used location within the project;
- terminal windows and their working directories;
- tmux sessions, windows, and panes where used;
- running project processes where they can be identified and reconstructed safely;
- browser windows and tabs where the browser exposes usable session control;
- editor state;
- agent conversations and unfinished prompts;
- project notes;
- other application state found during the capability review.

### Capability classification

Initial findings are recorded in [`STATE-RESTORATION-CAPABILITIES.md`](STATE-RESTORATION-CAPABILITIES.md), with experimental results in [`RESTORATION-SPIKE.md`](RESTORATION-SPIKE.md).

Each current application or surface is classified as one of:

- **Exact:** the relevant state can be captured and restored reliably.
- **Best effort:** useful state can be reconstructed, but some details may be lost or differ.
- **Unsupported:** no safe or practical restoration mechanism is currently available.

The mapping should record separately:

- what state can be observed;
- what state can be saved;
- what state can be restored;
- whether restoration requires the application to remain running;
- whether the mechanism uses a supported interface or a fragile workaround;
- what failure or data-loss risks exist.

The picker must not imply that restoration is exact when an integration is best-effort or unsupported. Unsupported state should not block the whole project from being closed, but the user should receive a clear warning before live state is discarded.

The core project model must remain usable even when an application has no integration.

## Archive and restore

### Archive

Archiving a project:

- removes it from the normal picker;
- preserves its record and retained state;
- does not delete or modify underlying files;
- does not provide a permanent-delete operation.

An open project must be closed before it can be archived. The UI may offer a deliberate “close and archive” action, but should not silently destroy a live workspace.

### Browse archived projects

- The picker provides an explicit archived-project view or mode.
- Archived projects are searchable there.
- The archived state is clearly visible.

### Restore

Restoring an archived project:

- returns it to the normal picker;
- does not automatically open it;
- preserves its retained state and references.

The user can then open it through the normal flow.

## Restart behavior

- Registered projects survive a restart.
- Archived status survives a restart.
- Projects do not all reopen automatically after login or reboot.
- The user explicitly opens a project when it is needed.
- A project that was open before shutdown may therefore appear closed after restart while retaining whatever state iteration one promises to restore.

## Acceptance criteria

Iteration one is complete when all of the following are demonstrably true:

1. From any ordinary Hyprland workspace, the user can invoke one global project picker without first opening a terminal.
2. The normal picker lists all and only non-archived projects.
3. The current, open, and closed states are understandable at a glance.
4. The user can filter projects by typing part of a name.
5. The user can create a project through the picker using the agreed minimum fields.
6. Cancelling creation leaves no partial project behind.
7. Selecting a closed project opens it and makes it current.
8. Selecting an open project switches to it without closing the previous project.
9. Switching away leaves the previous project’s live applications and processes running.
10. Selecting the current project causes no duplicate workspace or harmful side effect.
11. Closing a project removes its live workspace without deleting project files.
12. Reopening a closed project restores all state classified as exact, attempts all state classified as best-effort, and clearly reports anything that could not be restored.
13. The user can archive a project without deleting its files or retained state.
14. Archived projects do not appear in the normal picker.
15. The user can browse archived projects and restore one.
16. A restored project returns to the normal picker and can be opened.
17. Projects do not all reopen automatically after reboot.
18. Picker cancellation and failed actions do not corrupt project state or unexpectedly change the current project.
19. All required flows can be completed with the keyboard.
20. No required behavior depends conceptually on Kitty, tmux, Pi, Vivaldi, or another replaceable application.

## Decisions needed before implementation

1. Approve the exact set of application integrations required for iteration one. The current recommendation is Hyprland, Kitty, Pi, Vivaldi, Vim, Zathura, and explicitly managed project processes.
2. Choose the global shortcut when integrating with Hyprland.
3. Run the deferred real-Hyprland restoration experiment when it can be done without disrupting active work.

The remaining creation, closing, Home fallback, archive, and restore behavior is settled for this iteration. Architecture, storage, technology, and workspace implementation should be chosen only after the integration scope is approved.
