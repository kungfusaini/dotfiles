# Native tablet touch-navigation gate

The goal is coherent touch interaction, not just successful session startup.
Physical-device acceptance is still required before enabling automatic native
folding. The normal desktop and existing app windows must remain intact.

## Corrections

- A continuous upward swipe goes Home even when it lasts longer than 300 ms.
  Only a genuine pause after sufficient upward travel selects the switcher.
  Previously a deliberate slow swipe was classified as a hold on release.
- The native 180-pixel-wide gesture target reaches the actual bottom edge,
  or the top of the keyboard. The indicator retains its original position.
  The old preview keeps its original target geometry.
- Native Home presentation follows the gesture and holds through the asynchronous
  backend reply. Previously releasing could reset the visual to the app before
  the backend started a second Home fade. An unsuccessful request releases the
  visual/input cover after a bounded timeout. Requesting Home while already Home
  must not block the next app tap.

The real native browser is not a captured texture: this is a progressive Home
reveal, not an iPadOS-style live shrinking browser card. No claim of iPadOS
feature or physical performance equivalence follows from these tests.

## Layers of evidence

`tests/tablet-home-preview.nix` runs Qt component/layout/input tests, including
slow continuous touch, hold, short/downward/cancelled gestures, edge contact in
landscape/portrait/above IME, delayed backend presentation, failure timeout and
Home-on-Home immediately followed by app selection.

`tests/tablet-touch.nix` runs the native workspace on a private Lua Hyprland
inside a hidden Labwc session. Example from a committed checkout:

```sh
nix build --impure --no-link --print-out-paths --expr '
  let f = builtins.getFlake (toString ./.);
      c = f.nixosConfigurations.kirax1;
  in import ./tests/tablet-touch.nix {
    pkgs = c.pkgs;
    hyprland = c.config.programs.hyprland.package;
  }'
# Run the printed store path's bin/tablet-touch-test.
```

The existing nested backend only provides keyboard/pointer input. Its original
virtual-pointer drag suite is therefore not a touchscreen integration test.
The new test-only plugin creates a private `ITouch` and routes contacts through
Hyprland's normal input manager/seat to `wl_touch`. It creates no Linux uinput
device, installs no production plugin and is not loaded in the real compositor.
It refuses initialization without the exact private runtime and an opt-in file.
This is an integration test below libinput calibration, not proof of physical
sensor calibration, pen behavior, pressure or touch-device firmware.

The test client parks the cursor with the existing virtual pointer. Explicit
`mouse-down`/`mouse-up` preserve the original **pointer** passthrough assertions;
gesture contacts, selected UI taps and OSK key taps use the independent touch
path. A read-only native scene IPC reports visible control geometry; it never
invokes UI actions. Recorded backend commands are labelled separately from taps.

Private `/run` masking avoids creating a missing posture directory in the real
root-owned `/run`; only graphics drivers are rebound read-only. Browser profile,
D-Bus, settings, pages, audio/backlight controls, sensor and posture fixtures are
private. Chromium's sandbox stays enabled. No real account, credentials, audio,
brightness, physical input or user-manager environment is changed.

## Interaction matrix

| Interaction | Isolated evidence |
| --- | --- |
| Home/app and fullscreen media | Real Vivaldi window; test page and native/client fullscreen assertions |
| Swipe up / slow swipe / actual edge | Real `wl_touch`; Home visual must not reverse while awaiting backend |
| Swipe-and-hold, switcher, resume | Real touch hold and touch selection of retained browser card |
| Short/downward cancellation | Real touch; must remain in app; component cancellation tests also retained |
| Keyboard and Home above IME | Real Squeekboard, touch on `q`, text-input delivery, touch Home/keyboard dismissal |
| Portrait navigation | Fake sensor drives real rotation; touch only after rotation cover is released |
| Settings | Touch corner swipe, volume/brightness sliders, mute/unmute and close; stateful private hardware stubs |
| Launch and app switching | Touch Vivaldi/Pegasus tiles; game-to-Home/resume and browser/library switching |
| Fold/unfold and return | Simulated posture edges exercise real workspace ownership/resume and exact desktop restoration |
| Games | Real Pegasus with a minimal private fixture theme and dummy game; delayed launch, retained game, failure/retry |
| Failure/recovery | Real backend/cover failures and foreign focus without stealing focus; private apps only |

Not established by this matrix: physical fold/suspend timing, pen alignment,
actual audio/backlight, the user's real game library/theme or authenticated
website behavior. Those are separate device acceptance checks, not hidden passes.

## Recordings and review

Each integration run prints its private artifact root. It contains:

- `touch-interactions.mp4`: complete silent capture, including failed takes;
- `touch-events.jsonl`: timestamped input contacts and pointer actions;
- `touch-routing.log`: private compositor touch focus/coordinate diagnostics;
- `interaction-timeline.jsonl`: backend actions, UI taps and gesture readiness;
- `recording-start.json`: monotonic anchor for video/timeline review;
- screenshots, final client/layer/status snapshots and private process logs.

The recorder requests each compositor frame (`-D`), without forcing a synthetic
60 fps output rate or interpolating frames. A fixed 960×960 padded canvas avoids
stretching content when orientation changes. wlroots screencopy can retain the
output's physical orientation: an upright portrait **review clip** needs a
90-degree transpose. Preserve the raw capture and label this normalization;
never rotate the whole run or change playback speed to make it look smoother.

Review clips should cover every matrix row, including failures, not just the
happy path. Inspect transitions frame-by-frame as well as checking state. A
capture's nominal/average frame rate does not establish physical display latency.
Release-to-ready timing includes backend/animation/test query overhead and is
not a hardware touch-latency measurement. Keep the original trace and timestamps.

Store retained recordings outside Git under `~/matrix/media/design/` and record
which exact source was tested. A passing video review is a prerequisite to a
short supervised physical trial, not a substitute for it.

## References

- [Qt DragHandler grabbing and activation](https://doc.qt.io/qt-6/qml-qtquick-draghandler.html)
- [Qt TestCase touch sequences](https://doc.qt.io/qt-6/qml-qttest-testcase.html)
- [Wayland touch delivery protocol](https://wayland.app/protocols/wayland#wl_touch)
- [Aquamarine Wayland input backend](https://github.com/hyprwm/aquamarine/blob/v0.15.1/src/backend/Wayland.cpp)
- [Pinned Hyprland touch routing](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/managers/input/Touch.cpp)
