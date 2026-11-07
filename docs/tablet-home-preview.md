# Tablet home-screen preview

A reversible Tablet Home session, now used by the deployed physical fold path.
Folding the keyboard behind the display opens this Home, not the legacy button
panel. Unfolding closes the supervised session, restores input/settings/orientation,
and returns to the saved desktop workspace without closing desktop applications.
The internal workspace is still named `tablet-trial`; that name is not a different
UI. Manual entry is available from **Tablet workspace** or **Super+Ctrl+T**.
The shortcut toggles the same Home session.
`tablet-home-preview` enters that session **on Home**; there is no standalone
launcher window. Pi, Home, settings and open-app cards belong to the same frontend.
**No dock:** the home screen contains app icons only. A small bottom Home handle
is a navigation affordance, not an app dock: flick upward for Home, or drag up
and pause for horizontally scrollable open-app cards. Pi resumes its live chat;
other cards are explicitly simulations. The same handle is present inside Pi.

## What it does

- Responsive icon grid for Browser, Spotify, Videos, Steam, Games and Reading.
  Icons come from the corresponding installed desktop entries, with letter
  fallbacks when an icon is unavailable.
- Drag down at least 44 pixels starting in the top-right corner (top 28 pixels,
  rightmost 120 pixels, or 25% of narrow windows) to open quick settings.
  Taps, pulls elsewhere along the top, and short pulls do not open the drawer.
  The clock hint is not a button.
- Floating translucent tiles replace the settings form. Volume and brightness
  use tall, thumb-free vertical pills; mute/close and playback are icon-led tiles.
  All values and Wi-Fi/battery status are simulated, with a persistent preview
  label in the cluster header.
  The background content recedes while controls are open.
- **Pi** is the one real app: its first tap starts the lazy
  [native tablet chat](tablet-native-chat.md) backend **inside the existing session**.
  It does not start another Home/frontend, enter another workspace, or restart
  keyboard/input services. Home and the switcher retain the same app history.
  Other app icons remain labelled previews, not real app launches.
- Tap outside quick settings or its close button to dismiss. Escape closes the
  drawer, then returns home, then exits the preview. Close preview also exits.
- Portrait/narrow layouts scroll rather than shrinking touch targets.
- Quick settings slides/scales/fades in with a matching scrim over 220 ms;
  Home recedes over 180 ms; the shared app surface opens over 200 ms. Icon presses have
  110 ms scale/colour feedback. Closing animations finish before hiding surfaces,
  and inactive/fading content cannot receive app taps.

Entry claims the existing `tablet-trial` workspace once, behind a pre-rendered
opaque stage, and starts the shared frontend and reversible keyboard/input lifecycle.
A windowless backend host is ready, but **Pi itself is not started until tapped**.
The same supervisor, frontend, stage and input resources persist through app navigation.
Exit tablet restores the prior workspace/settings; reopening an active session
attaches without rebinding, spawning another frontend or resetting its view.
Settings tiles remain simulated. No changes are deployed to the default fold
watcher, Waybar or disabled Hyprgrass plugin.
[Continuous tablet presentation](tablet-presentation.md) defines the shared
no-desktop launch/handoff contract, stable background/cover ownership and limits.

## Build and run without deployment

```sh
nix build --impure --no-link --print-out-paths --expr '
  let f = builtins.getFlake (toString ./.);
  in builtins.head (builtins.filter (p: p.name == "tablet-home-preview")
    f.nixosConfigurations.kirax1.config.home-manager.users.sumeet.home.packages)'
```

Run the resulting store path's `bin/tablet-home-preview` from the owning project
terminal while that workspace is active on the laptop display. This is a
self-managed **mode controller**, not a normal application window: it owns the
named tablet workspace and layer surfaces, enters Home once, and restores the
previous workspace on exit. It binds that project only for a fresh session.
It runs immutable packaged sources, not the checkout; no deployment is required.

## Fold lifecycle

One `tablet-fold-watch` replaces the legacy `tablet-workspace watch` autostart.
It reuses the same posture reader, singleton lock, headless/display gates and
edge policy. Manual exit is respected until the next unfold/fold cycle.
The Home controller, not the watcher, acquires the workspace action lock: holding
it while waiting for Home would deadlock entry and cleanup. No agent, recording,
browser or model request starts merely because the laptop folds.

Fold entry retains the previously registered Pi project context. On first use
without one, Pi defaults to the user's home directory, not a checkout or the
background watcher's cwd. The app-menu/shortcut entry uses that same context;
`tablet-home-preview` remains an explicit project-context binding entry point.
Automatic sessions have no one-hour trial expiry. Cleanup is acknowledged only
after the supervisor has restored its resources; failures retain recovery state
rather than running the old panel's exit underneath a live Home session.

Physical acceptance must still check fold → new Home, touch typing in Vivaldi,
portrait rotation/touch/pen alignment, then unfold → original desktop. Headless
and private-compositor tests do not establish those hardware outcomes.

## Checks

```sh
nix build --impure --no-link --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-home-preview.nix {
    pkgs = f.nixosConfigurations.kirax1.pkgs;
  }'
python -B -m unittest discover -s tests -p 'test_tablet_*.py'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

The sandboxed Qt tests exercise actual mouse and synthetic top-right touch swipes,
reject taps and non-corner drags, check animation progression/reversal and exercise
icon activation, drawer dismissal, Home navigation, Escape handling, simulated
controls, pill endpoints and synthetic vertical touch drags (without accidental
panel scrolling), and portrait/narrow bounds. The test output contains reproducible
landscape, portrait and settings PNGs for visual review without capturing any
other desktop windows. Private compositor tests begin at the actual native Home
with Pi still stopped, visit preview apps, tap Pi, and assert the frontend,
stage and backend-host PIDs and app history are unchanged. Pi starts exactly once.
They also verify idle-before-Pi shutdown, streaming replies, frontend handoff,
voice/draft/storage protection and frame-by-frame continuous coverage.

## Deliberate limits

Physical folding now starts this Home and unfolding tears it down. The guarded
native Pi and Vivaldi adapters are included; this does not make the simulated
settings or other app cards real. Further integrations need separate approval: general app
placement/Home navigation, live audio/backlight/media integration, a
workspace-scoped replacement for Waybar, edge input regions over real apps,
external-app fullscreen/placement behavior and physical touch/rotation checks. The prototype's edge
handlers are only inside its own window; no system-wide gesture is claimed.

## Visual reference

The control cluster is informed by [Apple's iPad Control Center guide](https://support.apple.com/en-gb/guide/ipad/ipade572ca56/ipados)
and its [reference screenshots](https://ipcdn-web.apple.com/assets/v2/web/44253dd5-74a2-4501-84e0-7a7c770374bd):
separate rounded modules, paired vertical sliders and compact media controls.
The geometry is adapted to the few controls this preview actually supports;
there are no fake AirDrop, Focus or airplane-mode toggles. Icons are original
local Canvas artwork, not Apple SF Symbols, fonts or copied screenshot assets.
Glass-style tints/highlights are simple Qt gradients and alpha blending, not
live backdrop blur or a claim to reproduce Apple's Liquid Glass renderer.

## Why reuse Quickshell

The existing tablet panel already uses Quickshell. Its
[icon lookup](https://quickshell.org/docs/v0.3.0/types/Quickshell/Quickshell/)
provides local icons, while the existing guarded layer surfaces provide one
reversible tablet session without replacing the desktop. Qt Quick handles touch
inside the same Home/Pi/card scene. No additional dependency, service, network API or
compositor plugin is introduced; Hyprgrass remains disabled because of the
previous compositor crashes. Adopting a complete desktop shell would introduce
unrelated session/bar policies for a much smaller tablet-only requirement.
