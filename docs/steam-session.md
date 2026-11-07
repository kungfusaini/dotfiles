# Pegasus Steam sessions

All curated Steam entries use `steam-session APPID`, not a bare Steam URI.
The launcher dispatches an independent transient user service,
`pegasus-steam-session.service`, and waits for it. Closing Pegasus or its terminal
only disconnects that waiter; monitoring continues in the service.

The worker:

1. Checks that the exact app is installed. It never purchases, installs, accepts
   a license, or edits game launch options.
2. Captures the invoking Pegasus/terminal workspace, starts Steam silently using
   the verified workspace launcher and continuous Steam-window hider, and waits
   for the current client session to finish login. The shared launcher recognises
   exactly `steam -silent`: it installs a Steam-only hidden-window policy, starts
   the backend on `special:steam-hidden`, and verifies a newly tagged main client
   process. A tray-only client does not need to map a window. Delayed Steam UI
   remains hidden and cannot request focus. Missing placement context is an error,
   not permission to use the globally active workspace.
3. Records the current game-process log position and sends the normal official
   `steam://rungameid/APPID` request through the workspace launcher. Its Steam-URI
   branch requires a new mapped window whose live process/ancestry carries the
   exact requested `SteamAppId` or `SteamGameId`, then silently places and rechecks
   that exact window on the invoking library workspace. Existing/unrelated windows,
   Steam login/settings windows and window titles are not routing guesses. A game
   that discards these identity markers fails closed rather than using a fallback.
4. Requires evidence that the game actually started, then waits for its exit.
   A failed start has a three-minute observation deadline. Very short games
   that start and stop between polls are detected from the new log records.
5. Waits for *all* real Steam gameplay, downloads, installs, shaders, Workshop
   content and cloud transfers to finish, then requires 20 seconds of quiet
   cloud/content logs and requests a guarded graceful shutdown. It verifies
   that the client exited. It never overrides activity or force-kills anything.

Pegasus stays suspended until the worker completes cleanup. An existing running
copy of the same game or another wrapper session is not relaunched or stopped.
The fixed service name plus a nonblocking worker lock prevent competing launches.
Startup/placement failures notify immediately before attempting guarded cleanup,
so a delayed cleanup cannot conceal a failed launch. Protected work can delay shutdown; after
five minutes the worker notifies the user, keeps evidence in the journal, and
continues waiting (up to 24 hours). It does not decide that an unfinished current
transfer is safe to interrupt merely because it is old.

An installed game with a deferred update is not an active download. Old staging
folders and sync records are not a live job queue. Cache-only cloud initialization
finishes on its explicit completion event. Current upload/download phases are
tracked separately, and prior client process/session evidence is excluded.
Steam logs, cloud metadata and saves are never deleted to clear activity status.

## Sources and ownership

`home/packages/steam-session/` is the canonical packaged implementation. It reuses
and promotes the tested Steam organizer helper; its broader library CLI is also
available as `steam-library` for skill operations. The Pegasus launcher never
calls the catalog, account API or credential functions. No runtime dependency on
the repository checkout or Project Object skill directory is allowed.

After deployment, the Machine-owned Steam skill should delegate its
`steamctl.py` entry to the installed `steam-library` implementation instead of
maintaining a second copy. Its download progress display may continue to import
that entry and use the same corrected safeguards.

References:

- [Pegasus Steam exit-detection limitation](https://github.com/mmatyas/pegasus-frontend/issues/442)
- [Steam app-state bitmask](https://github.com/SteamRE/open-steamworks/blob/master/Open%20Steamworks/AppsCommon.h)
- [systemd transient services](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)

## Inspect and test

```sh
systemctl --user status pegasus-steam-session
journalctl --user -u pegasus-steam-session
steam-library status
python3 -m unittest discover -s home/packages/steam-session/tests -v
python3 -m unittest discover -s tests -p '*pegasus.py'
```

The worker writes its app, phase and error status to
`~/.local/state/steam-organizer/session.json`. This is private runtime state, not
configuration to commit. Tests use temporary XDG/state paths and mocked client
operations; they do not touch real accounts, game saves, or desktop input.
Opt-in integration checks also exist:

- `home/packages/steam-session/tests/service_integration.py PACKAGE_PATH` runs a
  real transient user service with synthetic Steam operations, terminates only
  its foreground waiter, and verifies independent guarded cleanup afterward.
- `home/packages/project-object/tests/steam_workspace_integration.py` uses a
  private DBus session, headless labwc/Hyprland and a compiled fake Steam client.
  Pass explicit `--hyprland`, `--hyprctl`, `--labwc`, `--kitty`, and `--cc` paths.
  It checks tray-only process verification, initial placement of delayed Steam UI
  on the hidden workspace, and exact-app game routing without focus theft. It
  never starts real Steam or reads any account/profile/save data.

These checks do not establish physical GPU, audio/controller performance, or a
successful real desktop game launch. Do not surface test windows on the live
session or change the desktop display environment just to run a test.
