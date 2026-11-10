# Hyprland-native tablet vertical slice

This is a separately packaged, **manual** proof—not the default fold path and
not a production tablet shell. Hyprland, Project Object, app profiles and the
normal desktop remain in place. There is no second compositor or app process
started by the product. The parked Plasma Mobile session can be stopped without
deleting its account/data; it is not a runtime dependency.

## Contract

Choose one explicit, already-open **native tiled Vivaldi window on eDP-1**.
The controller leases that exact address/PID/start-time/class and compositor
lifetime `stableId`, additionally marking it with its own unique tag, leaves its workspace and tile tree intact and uses Hyprland's native state
pair `internal=2, client=1`: compositor full-display, client maximized. This is
not a floating rectangle and there are no permanent top/bottom shell margins.
A client video request can become `2/2`; leaving video returns to normal client
maximization without repeatedly enforcing size. The same browser process,
profile, tabs and login state continue. The proof never navigates, inspects,
restarts or closes that browser.

Presentation is independent of app rendering:

- One Quickshell overlay has input only at a 144×24 top-right corner and a
  centered 160×14 bottom edge (above the keyboard when it is visible).
- Swipe down at the top-right for a **global** settings panel, including over
  client fullscreen video. Swipe up at the bottom for Home; resume returns to
  the exact same native window, without disturbing its media fullscreen state.
- Outside these zones, app touches/clicks pass through. An initial edge press
  is accepted immediately, rather than waiting for a passive drag threshold
  that can lose motion when it leaves the narrow Wayland input region. Qt
  synthesizes these single-finger interactions for the MouseAreas.
- Home/settings expand the overlay's input region while open. They do not grab
  keyboard focus. No hidden full-screen capture surface, live app screenshot,
  model or agent runs behind the browser.
- The proof reuses the established wallpaper, glass tiles, icons and pill
  sliders. Its Home has only **Resume browser** and **Return to desktop**: no
  simulated app grid or pretend app integrations.
- Volume/mute use `wpctl`; brightness targets only `intel_backlight` through
  `brightnessctl`. Missing backends disable controls, not invented values.
  Volume is capped at100%, brightness cannot go below5%. These intentional
  user changes persist on exit; the proof does not roll them back.
- A task-owned Squeekboard runs for the entire proof, with verified unique D-Bus
  ownership for hide requests. Existing keyboards attached to this display are
  not replaced. IME settings are journaled before changes and restored only if
  still equal to the values the proof applied. There is no synthetic typing in
  the real session and no inspection of input fields or credentials.

## State and recovery

Only the selected internal-display browser is managed. No window is floated,
resized manually, moved between workspaces, or reclaimed by shared browser PID.
The initial fullscreen pair, effective sync policy, origin workspace and
lifetime-identified focus
are journaled before mutation in `$XDG_RUNTIME_DIR/tablet-proof/recovery.json`.
The controller's IPC directory is private0700 and journal0600; no runtime state
is committed to Git.

Native `fullscreenstate` in the pinned hyprlang compositor targets the active
window and toggles when sent the same pair. Every change verifies source
identity/focus and eligible monitor/workspace; identical state is a no-op. This
is a **focus-checked legacy IPC operation, not a compositor-side atomic
conditional transaction**. The proof must not be generalized to arbitrary
background windows or rapid concurrent focus changes without further work.

Returning undoes only the client maximization introduced by the proof; later
user media fullscreen/exit requests are preserved. Configuration reload stops
the proof and removes its sync override instead of replaying an obsolete policy.
Other windows, monitors, desktop rules and processes are not targets.

An independent, sleeping supervisor recovers after backend failure. Verified
frontend/keyboard children are stopped without force. A vanished/replaced app is
not recreated or substituted. If another app takes focus, even within the same
workspace, the proof ends eligibility: overlay and keyboard stop, and a recovery
journal remains rather than stealing focus to perform a legacy fullscreen
operation. Explicit recovery can activate the exact recorded browser, restore
it and return to the recorded origin. Recovery does not restart the compositor.

The first proof intentionally excludes floating, grouped and pinned windows,
other-display windows, toggling the source to floating, modal dialogs that take
focus, and a complete multi-app
switcher. It must not silently widen ownership to handle those cases.

## Build/run without deployment

Build `home/packages/tablet-proof/default.nix` with the same pinned Hyprland
package as the laptop. It returns `{package, ui}`. Run only the resulting Nix
store program, never Python/QML from the checkout:

```sh
.../bin/tablet-proof start --address 0xEXPLICIT_BROWSER_ADDRESS
.../bin/tablet-proof status
.../bin/tablet-proof close
.../bin/tablet-proof recover --activate
```

`start` is singleton and will not replace an existing proof target. Status does
not contain browser titles, URLs or content. A frontend that loses its backend
subscription hides its input surface and exits. There are no global screenshots,
credential captures or browser debugging connections in the live proof.

**Leave the hinge unchanged for this manual test.** Physical folding still runs
the older installed prototype, and wiring the new implementation into folding
is explicitly deferred until this vertical slice passes acceptance. No Hyprland
reload, new shortcut, default service or startup hook is required to run it.

## Evidence and acceptance

- `tests/test_tablet_proof.py`: identity leases, native state idempotence, focus
  refusal, media ownership, real-control validation/unavailability, unique IME
  peer checks, settings restoration, recovery retention and supervisor recovery.
- `tests/tablet-proof-edges.nix`: real Qt synthetic touchscreen and mouse tests
  of corner/bottom gestures, short/wrong-origin rejection, drawer gating and
  keyboard inset.
- `tests/tablet-proof-native.nix`: an explicitly private Labwc→Hyprland test
  runtime, seat, bus, temporary browser profile and headless output; no host
  system-bus connection. The **test fixture**, not the product, launches two
  native Vivaldi windows and an actual local WebM video. It verifies native
  app/media state and output-sized geometry, global settings/Home over video,
  center click-through, real native IME focus/typing, identical original tile
  geometry/window set/state/tag/workspace return, backend SIGKILL recovery and
  same-workspace focus-loss stop with explicit recovery. Audio/backlight tools
  are replaced only in the private test's PATH; real hardware is never changed.

Passing private tests does not establish real touch behavior, YouTube-specific
behavior, arbitrary text fields, portrait rotation, fullscreen games, battery
life or universal dialogs. Physical acceptance requires the existing normal
browser, actual YouTube fullscreen, global gestures, touch typing, Home/resume
and desktop return. Stop if a recovery guard trips; do not launch more overlays
or broaden the target selection to hide a failure.

## Adopt versus build

Reuse Hyprland native window states, Quickshell layer-shell/input masks,
Squeekboard, `wpctl` and `brightnessctl`; build only the scoped tablet lifecycle
and presentation. No full desktop shell or gesture plugin is introduced.
Hyprgrass remains disabled because of its past crashes/ABI coupling. Existing
Hyprland touch workspace gestures alone are not a replacement for these global
corner/bottom controls.

Primary mechanics: [Quickshell window masks](https://quickshell.org/docs/v0.3.0/types/Quickshell/QsWindow/),
[Wayland input regions](https://wayland.freedesktop.org/docs/html/apa.html#protocol-spec-wl_surface),
[layer-shell ordering](https://wayland.app/protocols/wlr-layer-shell-unstable-v1),
and the pinned [legacy dispatchers](https://github.com/hyprwm/Hyprland/blob/efb50993780079460b0cbed1363e2166a2de1d9f/src/config/legacy/DispatcherTranslator.cpp).
