# Pegasus and tablet-local games

Native tablet Home offers Vivaldi and Pegasus. Pegasus is a real frontend,
not the legacy preview tile. Laptop applications are never adopted or moved.
The existing desktop Pegasus configuration, curated gameOS theme and game
catalog remain authoritative; tablet mode does not maintain another library.

## Ownership and handoff

- Open Pegasus from tablet Home. A new instance is launched on `tablet-trial`
  with a private nonce; its exact executable, PID/start lifetime, environment
  nonce, mapped window and compositor identity must agree before presentation.
  If desktop Pegasus is open, close it before starting the tablet instance.
- Curated launch commands use `tablet-game-launch -- COMMAND ...`. Outside the
  exact registered tablet Pegasus ancestry this is an `exec` passthrough with
  unchanged arguments. No tablet game receipt or worker is created.
- Tablet launches use `project-workspace-exec` to start an independent worker
  on the invoking library workspace. This survives frontend/backend teardown.
  A receipt records the compositor, Pegasus nonce, launch request and worker
  lifetime. Only a new tablet-local mapped window can become the game target:
  native/emulator windows require launch-process ancestry; Steam windows require
  the exact requested App ID in their live process environment. A stable window
  ID and PID/start lifetime fence subsequent use. XWayland and floating games
  are allowed only after those identity checks; pinned, grouped,
  foreign-workspace and ambiguous windows remain ineligible. Pegasus itself
  must still be a regular non-floating window.
- The native adapter launches an immutable tablet Pegasus variant using an
  absolute store path. With its private tablet nonce, this variant retains the
  actual frontend and nonblocking Qt event loop during a game command. gameOS
  displays its own game-specific launch view, blocks duplicate launch input,
  distinguishes launch/cleanup/attention states, and returns to its previous
  library view afterward. The normal desktop package is unchanged; even the
  variant retains upstream teardown behavior without the tablet nonce.
  Tablet Home is never substituted for Pegasus's loading scene.
- A verified game receives a reversible, journaled fullscreen presentation
  lease, including a floating game such as native Slay the Spire. Its first
  handoff waits for full-output geometry. There is no fixed resolution or
  repeated enforcement after presentation. Original internal/client modes
  are restored on unfold, switching adapters or explicit covered recovery.
  Live but ineligible windows retain restoration evidence rather than being
  mistaken for destroyed windows. No game is closed as presentation cleanup.
  Browser presentation leases remain separate, with tablet web media paused
  and gated while switching away.

## Unfold, resume and cleanup

Unfold returns to the recorded laptop workspace and releases tablet UI, keyboard
and rotation ownership. **Games are not closed, signalled, suspended or assumed
pausable.** They may continue rendering and playing audio in `tablet-trial`.
Refolding resumes the exact game if it still exists, otherwise the library.
Home/app intent is separate from the temporary loading cover.

Steam continues to use `steam-session APPID` unchanged: hidden official-client
startup, exact-game routing, observed game lifetime, protected downloads/cloud
activity, settling and graceful shutdown. The tablet wrapper does not compete
with that worker or force Steam to stop. Pegasus retains its window while Steam
finishes cloud cleanup, showing a finishing-session state rather than Home.
A failed handoff reports an error but still waits for the
existing game/worker rather than terminating it. A worker crash does not grant
permission to kill or relaunch the game. Unresolved launch receipts block another
launch even if the worker died before publishing a window. Inspect the recorded
child/window lifetimes and coordinate explicit recovery; do not delete the receipt
or infer game exit from worker death. A missing notification executable cannot
interrupt confirmed child cleanup or leave its receipt unresolved.

For an explicitly approved failed Steam attempt, the installed recovery command
can archive (not erase) the stale receipt:

```sh
tablet-game-launch --recover-failed APPID --approved
```

It requires the exact failed command hash, no recorded live caller/worker/child,
no game identity, Steam confirmed stopped with no protected activity, and no
remaining readable Steam-tagged processes. Unreadable possible descendants are
hard blockers; protected services predating the request cannot be its descendants.
Unknown, live or malformed state is retained.
Archives stay private under `$XDG_STATE_HOME/tablet-native/recovered-launch-receipts`.
This is an explicit recovery operation, never an automatic worker-death timeout.

A single uniquely verified game window is supported per tablet launch. Games
with multiple simultaneous primary windows, launchers that discard lineage,
recycled/recreated windows or nonstandard Steam processes can fail closed; this
is not a claim of universal compatibility. No real game is launched for agent
verification without title-specific permission.

## Verification and activation

`tests/test_tablet_gaming.py` covers identity fences, desktop passthrough,
ambiguity and non-destructive worker waiting. Native lifecycle tests cover
browser parking, launch gaps, pause-failure cover release, handoff and unfold.
`tests/tablet-gaming-install.nix` executes the packaged launcher using the exact
metadata argv shape without Steam or a compositor.

The focused `gamingOnly = true` variant of `tests/tablet-proof-native.nix`
packages `tests/tablet_gaming_live.py`. It launches the actual patched Pegasus
with a disposable loading theme, verifies that the same mapped window and
loading pixels persist during a delayed launch (no Home fallback), presents a
floating QuickShell game screen-filling, checks original mode/geometry restore
on unfold and game survival/resume, then confirms failure return and retry.
The broader native compositor proof includes those game transitions alongside
browser/media/IME, rotation and recovery scenarios. It has no host seat,
real game library, saves, Steam account or system sensor access.

Automatic native routes remain disabled until separate physical acceptance.
Installing these files does not update an already-running temporary watcher;
replace only its verified exact lifetime after coordinated approval.

Pegasus's documented [game-start/game-end hooks](https://pegasus-frontend.org/docs/user-guide/scripting/)
remain available; the existing synchronous Steam workspace capture hook is
preserved. Upstream's [launch API behavior](https://pegasus-frontend.org/docs/themes/api/)
backgrounds the frontend; the small package patch is necessary to retain the
real loading window rather than imitate it with a second shell. Exact game identity and worker lifetime are handled by the launch
wrapper rather than inferred from a generic hook or launcher process exit.
