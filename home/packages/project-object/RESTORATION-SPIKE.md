# Isolated State-Restoration Spike

## Status

Completed initial application-level spike on 2026-10-15.

The spike used disposable files, profiles, session directories, runtime sockets, and a headless Weston compositor under:

```text
/tmp/project-object-spike-1792060380
```

No live Kitty window, Pi session, Vivaldi profile, Vim buffer, Zathura history, project file, or Hyprland configuration was modified.

All isolated spike processes were stopped afterward. The live Hyprland process remained PID `23841` with its original instance signature and responded normally after cleanup.

## Isolation design

The spike created:

- a temporary `XDG_RUNTIME_DIR`;
- a headless Weston 15.0.1 compositor with its own Wayland socket;
- temporary home, config, data, and cache directories;
- a separate Kitty remote-control socket;
- a separate Vivaldi user-data directory and debugging port;
- a separate Pi session directory;
- disposable Vim files and sessions;
- a generated three-page PDF and separate Zathura database.

Network model requests were not used for the Pi test.

## Results summary

| Surface | Result | Revised classification |
|---|---|---|
| Hyprland | Real compositor reconstruction test deferred; nested startup failed safely | Still best effort pending isolated/live test |
| Kitty | Complete normalized session structure restored exactly | Exact arrangement; processes reconstructed |
| Pi | Exact session IDs selected the correct same-directory sessions | Exact for persisted session identity and content |
| Vivaldi native last-session restoration | Test tabs did not return in isolated headless mode | Not reliable for automated project restore |
| Vivaldi CDP reconstruction | Captured file-URL set reconstructed exactly | Best effort; URLs only |
| Vim session | CWD, buffers, tabs, and splits restored | Exact for supported saved session state |
| Vim unsaved text | Deliberately unsaved line did not return | Unsupported by `:mksession`; recovery only |
| Zathura | Page-two history survived close and reopen | Exact enough |
| Foreground process | Kitty relaunched `sleep 300` from its command | Command reconstruction, not process continuation |

## Hyprland

### Attempt

A second Hyprland 0.55.4 instance was started inside an isolated headless Weston compositor. This would have provided a fully separate compositor, output, Wayland socket, and window set without displaying anything on the live desktop.

### Result

Weston started successfully, but nested Hyprland could not initialize its Wayland backend because the headless Weston backend did not expose the buffer/allocator protocols Aquamarine required. Hyprland aborted with:

```text
Wayland backend cannot start: Missing protocols
Cannot open backend: no allocator available
```

One orphaned process from the failed attempt was found during cleanup and terminated. It used the temporary config path and runtime environment, not the live Hyprland instance.

### Decision

Do not fall back to a visible nested Hyprland window while the user is working. The real compositor test remains deferred until either:

- the live desktop is available for a disposable test workspace; or
- a suitable isolated compositor/GPU environment is available.

The existing evidence from `hyprctl`, `hypr-persist`, and `hyprflow` still supports best-effort layout restoration, but this spike does not upgrade that classification.

## Kitty

### Test arrangement

The isolated Kitty instance contained:

- two OS windows;
- one ordinary shell window in the first OS window;
- an `alpha` tab using the `splits` layout;
- two windows in `alpha`, with different working directories;
- one shell and one `sleep 300` foreground command;
- a `beta` tab using the `stack` layout;
- one shell in a third working directory;
- explicit tab and window titles.

The extra first OS window resulted from placing `new_os_window` at the beginning of the hand-written input session. It was harmless and useful: the exported session reproduced it too.

### Capture

Kitty remote control exported the live tree with:

```text
kitten @ ls --output-format=session
```

The first Kitty process was terminated. A second Kitty process then opened the exported session.

### Comparison

The comparison normalized away runtime IDs and PIDs, then compared:

- OS-window count;
- tab count and ordering;
- tab titles;
- layouts;
- window titles;
- working directories;
- command lines.

Result:

```text
NORMALIZED_EQUAL: True
```

### Interpretation

Kitty’s own arrangement is an exact restoration mechanism for the tested fields. The `sleep 300` process was launched again; it did not continue as the original process. Application-specific state must therefore layer on top of Kitty’s process reconstruction.

## Pi

### Test

Two synthetic but valid Pi version-3 session files were created:

- session ID `alpha`;
- session ID `beta`.

Both declared the same working directory. Each contained a distinct marker and session name.

Pi 0.87.1 was launched in a pseudo-terminal twice using:

```text
--session-dir <isolated-directory> --session <exact-id>
```

### Result

- Resuming `alpha` displayed only `SYNTHETIC-ALPHA-MARKER` and `Spike alpha`.
- Resuming `beta` displayed only `SYNTHETIC-BETA-MARKER` and `Spike beta`.
- Neither transcript contained the other session’s marker.

### Interpretation

Exact persisted Pi sessions can be selected reliably even when they share a working directory. A project integration should record the exact session ID or path rather than rely on `--continue`.

This test deliberately did not call a model. It did not test:

- interruption during generation;
- queued steering or follow-up messages;
- unsent editor text;
- graceful shutdown of a live agent.

Those remain separate Pi-integration questions.

## Vivaldi

### Isolated profile

Vivaldi ran headlessly with:

- a disposable `--user-data-dir`;
- a localhost-only remote-debugging port;
- two local HTML files as test tabs;
- no access to the user’s live Vivaldi process or profile.

### Native last-session result

The initial browser contained the two local test pages. It was terminated cleanly and relaunched with the same profile and `--restore-last-session`.

The test pages did not return. The relaunched browser contained only Vivaldi’s start page.

This headless result does not prove the interactive browser’s native UI session feature is broken. It does prove that command-line last-session behavior is not a reliable basis for automated project restoration.

### CDP reconstruction result

The two local page URLs were captured through the Chrome DevTools Protocol, then recreated in the relaunched browser.

Result:

```text
URL_SET_EQUAL: True
```

### Interpretation

CDP can reliably reconstruct the tested URL set. This remains only best effort because the test did not preserve:

- Vivaldi Workspaces;
- tab stacks;
- full tab ordering semantics;
- back/forward history;
- scroll positions;
- forms and page-local transient state;
- ownership of windows within a shared browser process.

A supported automated trigger for Vivaldi’s native named sessions was not found.

## Vim

### Saved-session result

A disposable Vim session was created with:

- two files;
- two tabs;
- two split windows in the first tab;
- a known working directory.

After exiting and sourcing the generated session, Vim reported:

```text
tabs=2
windows_tab1=2
buffers=a.txt,b.txt
cwd=/tmp/project-object-spike-1792060380/vim
```

The session restored the expected current file as well. Cursor restoration was not measured rigorously enough in this headless script to make an additional claim beyond Vim’s documented support.

### Unsaved-buffer result

A line was added to a buffer without writing the file. `:mksession` was then created and Vim exited without saving. After restoring the session, the line was absent and the original disk line appeared:

```text
alpha two
```

### Interpretation

Vim sessions are suitable for saved editor arrangement and file state. They do not preserve unsaved buffer contents. Closing must detect modified buffers and warn, save them deliberately, or leave recovery to Vim swap files without claiming exactness.

## Zathura

### Test

A disposable three-page PDF was generated. Zathura opened it at page 2 using a separate data directory, then closed cleanly.

Its `fileinfo` database stored page index `1`, corresponding to page 2. Zathura was then reopened without an explicit page argument and closed again.

Result:

```text
PAGE_2_RETAINED: True
```

### Interpretation

Document identity and last page are sufficiently restorable through Zathura’s own history. Explicit `--page` restoration remains available if project state should override global history.

## Consequences for iteration one

1. Use native Kitty sessions rather than trying to infer terminal layouts independently.
2. Record exact Pi session IDs or paths; do not use working directory as session identity.
3. Treat Vivaldi as best effort unless a supported native automation mechanism is discovered.
4. Warn before closing a Vim instance with modified buffers.
5. Use Zathura’s document path and page/history directly.
6. Describe process restoration as relaunch, not continuation.
7. Keep Hyprland layout restoration classified as best effort until tested on a real Hyprland workspace.
8. A close operation must report partial capture and allow cancellation.

## Remaining experiments

- Real Hyprland workspace reconstruction when it can be tested without disrupting active work.
- Graceful Pi behavior during active generation, queued input, and unsent prompt text.
- Interactive Vivaldi native named-session automation, if a supported control surface can be found.
- Vim modified-buffer detection through a controlled live instance.
- Explicit project development-service stop/start behavior.
