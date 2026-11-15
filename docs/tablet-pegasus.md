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
  ID and PID/start lifetime fence subsequent use. XWayland games are allowed;
  floating, pinned, grouped, foreign-workspace and ambiguous windows are not.
- Pegasus hides its window before its launch command runs. Tablet Home covers
  that startup gap; no guessed foreground window is adopted. Unrelated window
  focus is never a reason to follow the user to another workspace.
- Game presentation follows the game's own fullscreen configuration. Tablet mode
  does not send browser fullscreen/media commands to games or force a resolution.
  Exiting the game lets its launch command finish, then Pegasus restores its
  frontend. Browser presentation leases are parked/restored separately, with
  tablet web media paused and gated while switching away.

## Unfold, resume and cleanup

Unfold returns to the recorded laptop workspace and releases tablet UI, keyboard
and rotation ownership. **Games are not closed, signalled, suspended or assumed
pausable.** They may continue rendering and playing audio in `tablet-trial`.
Refolding resumes the exact game if it still exists, otherwise the library.
Home/app intent is separate from the temporary loading cover.

Steam continues to use `steam-session APPID` unchanged: hidden official-client
startup, exact-game routing, observed game lifetime, protected downloads/cloud
activity, settling and graceful shutdown. The tablet wrapper does not compete
with that worker or force Steam to stop. Pegasus may remain hidden while Steam
finishes cloud cleanup. A failed handoff reports an error but still waits for the
existing game/worker rather than terminating it. A worker crash does not grant
permission to kill or relaunch the game. Unresolved launch receipts block another
launch even if the worker died before publishing a window. Inspect the recorded
child/window lifetimes and coordinate explicit recovery; do not delete the receipt
or infer game exit from worker death.

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

The native private compositor proof also launches real Pegasus with a disposable
library and QuickShell game, checks unfold survival/refold resume, game exit and
library return, and switches browser/library both ways. It has no host seat,
real game library, saves, Steam account or system sensor access.

Automatic native routes remain disabled until separate physical acceptance.
Installing these files does not update an already-running temporary watcher;
replace only its verified exact lifetime after coordinated approval.

Pegasus's documented [game-start/game-end hooks](https://pegasus-frontend.org/docs/user-guide/scripting/)
remain available; the existing synchronous Steam workspace capture hook is
preserved. Exact game identity and worker lifetime are handled by the launch
wrapper rather than inferred from a generic hook or launcher process exit.
