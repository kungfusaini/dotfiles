# Stremio on the laptop and in tablet mode

Home Manager installs the pinned `stremio-linux-shell` (currently shell 1.2.0),
with its normal desktop launcher and icon. This is the GTK4/WebKit/MPV Linux
client, not the removed Qt5 WebEngine `stremio` package. No Flatpak service,
account, add-on, firewall, startup service or profile configuration is added.

The native tablet Home offers a Stremio tile alongside Vivaldi and Pegasus.
A cold launch creates a native Wayland window directly on `tablet-trial`.
The tile resumes only that exact window, identified by compositor instance,
address, stable lifetime ID, PID/start time and a private launch token.
It never moves or adopts a laptop window. Because Stremio is single-instance,
quit desktop Stremio, including its tray instance, before opening the tablet tile.
The error is intentional; a second independent account/profile is not created.
A moved/pinned/live-ineligible registered window keeps its cached card, but
cannot be captured, resumed or closed from the switcher.

`home/packages/stremio.nix` adds a narrow registration guard to the pinned upstream
package. Only a launch carrying `TABLET_STREMIO_TOKEN` registers GApplication
before starting the streaming server and refuses remote activation if another
singleton wins. This closes the race left by an advisory D-Bus/process check.
Ordinary desktop launches retain upstream activation behavior. The patch fails
closed at build time if upstream changes the expected source.

Stremio's own normal close request **hides its window to the tray**. Card swipe
uses that normal request, never a process kill. The Home tile can reopen only an
exact tablet-owned hidden/tray instance. It uses one Gio bus connection to
resolve the unique owner, checks PID/start time and launch token, rechecks the
internal workspace and absence of mapped/moved own windows, then activates that
unique destination. A desktop singleton is never activated this way. A remapped
window gets fresh admission; stale card descriptors cannot resume or close its
replacement. Temporarily hidden cards remain unavailable: only the explicit
launcher action can request this owned-tray restoration.

A private, locked runtime receipt precedes compositor exec. The spawn helper
records its PID/start time before exec; expired/replaced queued tokens cannot
start later. Failed launches can be retried once the deadline has passed and
neither the exact owner nor any token-bearing process survives. Ambiguous windows
remain unclaimed until the app is quit; no guessed window is closed. Receipts
live under `$XDG_RUNTIME_DIR/tablet-stremio`, never in Git or the persistent account
profile. The spawn command explicitly carries the packaged Stremio executable:
Hyprland does not inherit environment exports made by the native controller.
The private test keeps the compositor's executable override empty to exercise
this real boundary rather than accidentally supplying it through the fixture.

Tablet presentation reuses the existing reversible fullscreen lease. The normal
Home/switcher/bottom handle and control drawer remain available. Polling never
reclaims foreign or modal focus. Unfold/exit/controller recovery restores the
presentation and desktop interaction settings without closing Stremio. The
window remains in the tablet workspace for the next fold. Playback is not
controlled through Vivaldi's media companion: pause/stop Stremio before unfolding
if you do not want it to continue playing. No automatic playback claim is made.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_tablet_*.py'
nix build --impure --no-link --print-out-paths --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-touch.nix {
    pkgs = f.nixosConfigurations.kirax1.pkgs;
    hyprland = f.nixosConfigurations.kirax1.config.programs.hyprland.package;
    stremioOnly = true;
  }'
# Run the returned path's bin/tablet-stremio-touch-test.
```

The real-app test runs in private headless Labwc/Hyprland with a disposable HOME,
D-Bus, PID/proc and network namespace. Stremio loads a local HTML fixture, with a rendered
pixel assertion rather than mere process/window presence. It exercises native
touch tile launch, fullscreen, actual window preview pixels, real bottom swipe,
same-window resume, normal close/hide and owned-tray reopen without a new process,
stale descriptor rejection after remap, unfold, crash recovery, and refusal to
activate/adopt an existing desktop singleton. It uses no personal
account, host display/input or media. It does not establish streaming-provider,
codec, physical-touch, pen, OSK or rotation acceptance on the laptop.
The fixture uses an explicit shared MIME database so WebKit renders local HTML,
rather than accidentally showing its source as plain text.

The browser companion does not control this native client. No profile, account,
add-on or playback setting is modified by the integration. Real streaming and
automatic playback handling need separate acceptance.

Upstream: [Linux client](https://github.com/Stremio/stremio-linux-shell),
[Stremio Linux v5 announcement](https://blog.stremio.com/stremio-tech-update-81-stremio-v5-released-for-linux/).
Registration semantics: [GApplication.register](https://docs.gtk.org/gio/method.Application.register.html).
Normal close behavior: [pinned upstream window implementation](https://github.com/Stremio/stremio-linux-shell/blob/v1.2.0/src/app/window/imp.rs).
