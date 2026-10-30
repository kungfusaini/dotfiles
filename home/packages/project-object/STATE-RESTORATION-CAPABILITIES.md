# State Restoration Capability Audit

## Status

Initial capability audit, based on the live machine and current upstream documentation. This began as product research rather than an architecture decision. A later snapshot-only implementation now captures validated Hyprland workspace and window metadata without changing compositor state; close and restore remain unimplemented.

Audited: 2026-10-14. Snapshot capture implemented: 2026-10-26.

Application-level findings were subsequently tested in [`RESTORATION-SPIKE.md`](RESTORATION-SPIKE.md). The spike confirmed exact Kitty arrangement restoration, exact Pi session selection, best-effort Vivaldi URL reconstruction, Vim’s unsaved-buffer limitation, and Zathura page restoration. The real Hyprland reconstruction test remains deferred.

No applications were closed, restarted, or reconfigured during this audit.

## Classification

- **Exact:** The relevant state has a supported, deterministic save-and-restore mechanism.
- **Best effort:** Useful reconstruction is possible, but details may be lost, reordered, or dependent on timing.
- **Unsupported:** No safe and practical restoration mechanism is currently available.

A single application can have different classifications for different kinds of state.

## Current environment

Observed relevant software:

| Surface | Installed version or state |
|---|---|
| Hyprland | 0.55.4 |
| Kitty | 0.48.2 |
| Pi | 0.87.1 |
| Vivaldi | 8.2.4133.52 stable |
| Vim | 9.2 with persistent undo and client/server support |
| Zathura | 2026.05.20 |
| tmux | Not currently installed |
| Dedicated notes application | None identified; a current `vim todo.md` window appears to serve this role |

The live desktop also contains Slack, Teams for Linux, Thunderbird, ZapZap, and Spotify. These currently occupy global `comms` and `music` workspaces and are not obvious project-owned resources, so they are not proposed as initial project integrations.

## Summary matrix

| Surface | Observe | Save | Restore | Overall initial classification |
|---|---|---|---|---|
| Project identity and metadata | Exact | Exact | Exact | Exact |
| Hyprland workspace membership and focus | Exact | Exact | Exact | Exact |
| Hyprland floating geometry | Exact | Exact | Best effort to exact | Best effort pending test |
| Hyprland tiled layout and groups | Exact enough to reconstruct | Exact snapshot | Best effort | Best effort |
| Kitty tabs, windows, layout, CWD, commands | Exact | Exact | Arrangement exact; processes reconstructed | Exact / best effort |
| Pi completed conversation | Exact | Automatic | Exact by session path or ID | Exact |
| Pi active generation | Partial | Partial | Cannot resume an interrupted computation | Best effort |
| Pi unsent prompt and queued input | Runtime-only | No documented persistence | No | Unsupported without Pi integration |
| Vivaldi tabs and windows | Exact inside Vivaldi | Native manual session | Native manual restore | Exact manually |
| Automated Vivaldi project session | Partial | Possible via fragile or reduced mechanisms | Best effort | Best effort |
| Vim saved files, windows, tabs, cursor and folds | Exact | Native session | Native session | Exact when invoked cleanly |
| Vim unsaved buffer contents | Observable inside Vim | Not included in normal session files | Swap recovery only | Best effort |
| Zathura document and page | Exact | History/database or explicit page | Exact enough | Exact |
| Declared development services | Exact if explicitly managed | Command/configuration | Relaunch | Exact startup, not memory state |
| Arbitrary inferred processes | Partial | Command/CWD can be recorded | Relaunch only | Best effort |
| Arbitrary process memory | No practical general mechanism | No | No | Unsupported |
| tmux | Not present | Not evaluated locally | Not evaluated locally | Deferred |

## Hyprland

### What can be observed

`hyprctl` exposes JSON for clients, workspaces, monitors, the active workspace, and the active window. On this machine, each client record includes:

- address and stable ID;
- class, initial class, title, and initial title;
- PID;
- workspace and monitor;
- position and size;
- floating, pinned, and fullscreen state;
- group membership;
- focus history;
- swallowing relationship.

This is enough to make a detailed snapshot of the compositor-visible state.

### What can be restored

Hyprland dispatchers can:

- create or select named workspaces;
- move a matched window to a workspace;
- focus a window;
- move and resize windows;
- toggle fullscreen and floating state;
- construct and navigate window groups;
- send layout messages.

Existing tools demonstrate the feasible boundary:

- [`hypr-persist`](https://github.com/ngamber/hypr-persist) resolves launch commands, restores workspaces and floating geometry, and reconstructs dwindle/master tiling layouts from saved geometry.
- [`hyprflow`](https://github.com/isorensen/hyprflow) captures `hyprctl clients -j`, relaunches applications, waits for new windows, and repositions them using Hyprland dispatchers.

### Limits

- Hyprland can describe a window but does not own the application’s internal state.
- Window addresses and PIDs change after relaunch.
- A relaunched application may create windows asynchronously or in a different order.
- Exact reconstruction of a tiled tree is indirect: it must be inferred and replayed through layout behavior.
- Group ordering and the active member need explicit reconstruction and testing.
- A compositor snapshot cannot by itself determine a reliable relaunch command for every application.

### Classification

- Workspace membership, last active workspace, and last focused window: **Exact**.
- Floating position and size: **Best effort, likely close to exact**.
- Tiled layout, group membership, and group order: **Best effort**.
- Application contents: delegated to the relevant application integration.

## Kitty

### Native capabilities

Kitty session files can represent:

- OS windows;
- tabs;
- terminal windows;
- layouts and split sizes;
- active windows and tabs;
- working directories;
- titles and window classes;
- commands to launch;
- normal, fullscreen, maximized, or minimized OS-window state.

Kitty’s `save_as_session` action saves open OS windows, tabs, windows, working directories, layouts, and running foreground programs. A saved session can be reopened with:

```text
kitty --session <session-file>
```

Kitty remote control can list the live tree as JSON or session-file syntax, launch and close windows, and target windows by IDs, titles, PIDs, working directories, command lines, or session membership.

Sources:

- [Kitty sessions](https://sw.kovidgoyal.net/kitty/sessions/)
- [Kitty remote control](https://sw.kovidgoyal.net/kitty/remote-control/)

### Current-machine finding

No `allow_remote_control`, `listen_on`, or startup-session setting was found in the managed Kitty configuration. External automated capture is therefore not currently available through a configured control socket.

### Limits

A Kitty session reconstructs processes by launching commands. It does not checkpoint their memory. Whether the restored terminal appears exact depends on the foreground program:

- a shell can reopen in the correct directory but loses its transient shell state;
- Pi can reopen its persisted conversation when given the correct session;
- Vim requires its own session or recovery mechanism;
- an ordinary running command starts again rather than continuing at the same CPU/process state.

### Classification

- Kitty window/tab/layout/CWD arrangement: **Exact** using native session support.
- Foreground command identity: **Exact**.
- Foreground process state: **Best effort**, delegated to that process.

## Pi

### Native capabilities

Pi automatically stores sessions as JSONL, grouped by working directory. It supports:

- resuming the most recent session for a working directory with `--continue`;
- selecting a session with `--resume`;
- opening an exact session by path or ID with `--session`;
- assigning a deterministic session ID with `--session-id`;
- assigning a human-readable name with `--name`.

The session file contains the conversation tree, model and thinking-level changes, compactions, branch summaries, extension state, labels, and session metadata.

Sources:

- [Pi sessions and context](https://github.com/earendil-works/pi/blob/main/docs/sessions.md)
- Local Pi 0.87.1 documentation: `docs/sessions.md`, `docs/session-format.md`, and `docs/cli.md`

### Current-machine finding

Pi sessions are present under:

```text
~/.config/pi/agent/sessions/
```

Sessions exist for the home directory and project directories including Elijah and Arcane Codex. Current Pi processes were launched simply as `pi`; their exact session IDs are not present in their command lines, and Pi does not keep the JSONL file continuously open. An external desktop snapshot therefore cannot reliably distinguish multiple concurrent Pi sessions having the same working directory.

### Limits

- Completed conversation state is durable.
- An in-progress model request cannot continue from the exact point of interruption after its process is killed.
- The interactive editor’s unsent prompt is not part of the documented session format.
- Queued steering and follow-up messages are runtime session state and are not documented as durable JSONL entries before delivery.
- Abrupt termination may lose an incomplete streamed response.

### Classification

- Completed conversation and branch state: **Exact** when the exact session path or ID is known.
- Current model/thinking/session metadata: **Exact**.
- In-progress agent work: **Best effort**; close should preferably wait for settlement or stop it deliberately.
- Unsent prompt text: **Unsupported by normal session persistence**.
- Reliable association between a project window and a Pi session: **Best effort today**, but can become exact if future launches record or assign the session ID.

## Vivaldi

### Native capabilities

Vivaldi can save selected tabs or all open tabs as a named session. A native session can include:

- tabs from one or multiple windows;
- all windows;
- optionally, Vivaldi Workspaces.

The Sessions Panel can inspect and edit saved sessions and create hourly automatic backups. Vivaldi can also reopen its overall last browser session at startup.

Sources:

- [Saved Sessions](https://help.vivaldi.com/desktop/tabs/session-management/)
- [Sessions Panel](https://help.vivaldi.com/desktop/panels/sessions-panel/)
- [Startup Options](https://help.vivaldi.com/desktop/appearance-customization/starting-vivaldi/)

The local profile contains Chromium/Vivaldi session files under:

```text
~/.config/vivaldi/Default/Sessions/
```

### Automation boundary

Vivaldi does not document a supported external command-line interface for “save this window as named session” or “open this named session.” Native save and restore are user-interface actions.

A Chromium-family browser can expose the Chrome DevTools Protocol when launched with remote debugging enabled. CDP can enumerate page targets, create or close tabs, and inspect browser-window bounds. This could reconstruct URLs and broad window placement, but it is not equivalent to a Vivaldi session.

CDP source:

- [Chrome DevTools Protocol — Target](https://chromedevtools.github.io/devtools-protocol/tot/Target/)
- [Chrome DevTools Protocol — Browser](https://chromedevtools.github.io/devtools-protocol/tot/Browser/)

### Limits

An automated URL-based reconstruction may lose or alter:

- tab stacks and ordering details;
- Vivaldi Workspace membership;
- tab hibernation state;
- back/forward history;
- scroll positions;
- partially completed forms;
- page-local transient state;
- which project owns a browser window when several projects share one browser process.

Copying or manipulating live Chromium session files while the browser runs is fragile and should not be considered a supported interface.

### Classification

- Manual native Vivaldi session save and restore: **Exact for the state Vivaldi includes**.
- Fully automated per-project native session capture: **Unsupported through a documented public interface**.
- Automated tab URL and window reconstruction through CDP: **Best effort**.
- Browser profile data such as cookies and login state: persisted by Vivaldi independently, not project-specific.

Vivaldi is the largest restoration gap in the initial application set.

## Vim and project notes

### Native capabilities

The installed Vim has:

- `+clientserver`;
- `+persistent_undo`;
- session support through `:mksession` and `vim -S`;
- persistent undo configured under the user state directory.

The current `sessionoptions` value is:

```text
blank,buffers,curdir,folds,help,options,tabpages,winsize,terminal
```

A Vim session can therefore preserve loaded buffers, current directory, folds, options, tabs, window sizes, and terminal windows. Views also preserve cursor and scroll positions.

Source:

- [Vim help — Views and Sessions](https://vimhelp.org/starting.txt.html)

### Current-machine finding

A live Vim process is editing `todo.md`, making Vim/plain Markdown the only observed notes surface. It was not observed as a named Vim server, so an external tool cannot currently ask that running instance to write a session through the client/server interface.

### Limits

- `:mksession` references buffers and files; it does not make unsaved modified buffer text durable.
- Swap files may allow recovery, but recovery is not deterministic enough to count as exact state restoration.
- Exact automated capture requires a controlled way to ask the running Vim instance to save its session before closing.

### Classification

- Saved files, tabs, window layout, cursor position, folds, and options: **Exact** when a Vim session is created successfully.
- Persistent undo: **Exact for saved-file history covered by Vim’s undo files**.
- Unsaved buffer contents: **Best effort via swap recovery**, not exact.
- Plain Markdown notes already saved to disk: **Exact**.

## Zathura

Zathura can be launched with a document and explicit page number using `--page`. It also keeps document history in its data database. The local installation has:

```text
~/.local/share/zathura/bookmarks.sqlite
```

The current project-related Zathura process exposes both its PDF path and source working directory in `/proc`.

Source:

- [Zathura manual](https://manpages.debian.org/testing/zathura/zathura.1.en.html)

### Classification

- Document path: **Exact**.
- Page or bookmark: **Exact enough** using explicit launch arguments or Zathura history.
- Search, selection, and transient UI state: **Unsupported or unnecessary for the initial milestone**.

## Project processes and development services

### Explicitly managed processes

A process whose startup definition is known can be stopped and reconstructed using:

- executable and arguments;
- working directory;
- selected environment or configuration;
- dependency order;
- readiness checks.

This is exact reconstruction of the process definition, not of its memory.

### Inferred arbitrary processes

For a same-user Linux process, `/proc` often exposes:

- executable;
- command line;
- working directory;
- environment;
- parent/child relationship;
- open file descriptors.

That is enough to attempt a relaunch, but inference is unsafe as a general promise:

- command lines may contain temporary values or secrets;
- the process may depend on a parent shell, pipe, socket, namespace, or temporary file;
- relaunching may duplicate side effects;
- an open port may still be held by a surviving child;
- process state may depend on external services.

General checkpoint/restore is not a practical desktop solution. Wayland and application state also live outside the process, including in the compositor and other services.

### Classification

- Explicitly declared managed services: **Exact startup reconstruction**.
- Automatically inferred arbitrary processes: **Best effort and potentially unsafe**.
- In-memory continuation: **Unsupported**.

## tmux

tmux is not currently installed and no tmux sessions exist, so it is not required for the first local integration.

If introduced later, a running tmux server naturally preserves sessions, windows, panes, and child processes while graphical terminal windows come and go. Once the tmux server itself is stopped, tmux does not natively checkpoint the memory of pane processes. Tools such as tmux-resurrect reconstruct commands, paths, and layouts rather than continuing arbitrary process memory.

Classification for later review:

- While tmux remains running: likely **Exact** for terminal arrangement and live processes.
- After stopping the tmux server: **Best effort** reconstruction.

## Proposed first-iteration restoration promise

The initial implementation should aim to include:

1. **Exact project metadata and lifecycle state.**
2. **Exact Hyprland project workspace identity, last location, and window membership.**
3. **Best-effort Hyprland layout, geometry, fullscreen, and group reconstruction.**
4. **Native Kitty session capture and restoration.**
5. **Exact resumption of settled Pi conversations by recorded session ID.**
6. **A deliberate close policy for running Pi turns rather than abruptly killing them.**
7. **Best-effort automated Vivaldi tab/window reconstruction, unless a reliable native-session trigger is found in a proof of concept.**
8. **Native Vim sessions for notes or editor windows, with a warning for unsaved buffers.**
9. **Exact Zathura document/page reconstruction.**
10. **Relaunch of explicitly managed development processes, without promising memory continuation.**

Closing must present a warning when any detected state is unsupported or capture fails. The user should be able to cancel rather than discard that live state.

## Proofs of concept required before architecture

These tests should use disposable windows and sessions, not current work:

1. **Hyprland:** snapshot and reconstruct a named test workspace containing tiled, floating, fullscreen, and grouped windows; measure ordering and geometry drift.
2. **Kitty:** enable a temporary isolated control socket, export a test session, close it, and restore tabs, splits, CWDs, and foreground commands.
3. **Pi:** start two named sessions in the same directory, associate each with a different Kitty window, close them cleanly, and restore the exact conversations.
4. **Pi active state:** test settled, generating, queued-follow-up, and unsent-editor cases to confirm precisely what survives graceful and forced termination.
5. **Vivaldi:** use a disposable browser profile to compare native session restoration with CDP URL/window reconstruction, including multiple windows, Workspaces, and tab stacks.
6. **Vim:** use a disposable named Vim server to save and restore a session, then separately test the warning/recovery path for an unsaved buffer.
7. **Zathura:** restore a disposable document to a known page and verify history behavior after clean and forced close.
8. **Processes:** relaunch harmless test services with working directories, ports, and child processes; define which cases must be explicitly declared rather than inferred.

These experiments determine reliability. They should precede storage-schema and implementation decisions.
