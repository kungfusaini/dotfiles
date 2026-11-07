# Keyboard-only visual preview

These assets are packaged only for the explicit, reversible
[tablet iteration trial](../../../docs/tablet-iteration-trial.md), not deployed
as global keyboard resources or login autostart. They do not change the default
keyboard or dock. They are a landscape preview for Squeekboard 1.43.1 on kirax1.
Automatic input-method show/hide uses the same backend as the successful trial.

- `keyboards/gb_wide.yaml`: four-row UK-labelled touch layout with directly
  accessible £, UK shifted-number punctuation, Shift, erase and Return. This is
  not a physical 105-key UK map. Portrait and specialised input-purpose layouts
  are intentionally not replaced yet.
- `resource/style.css`: dark keys, restrained active-state contrast, teal Return.
- `resource/style-Adwaita:dark.css`: symlink so the installed Adwaita dark
  resource path selects the same preview stylesheet.

## Preview isolation

Copy the directory into the store before running; do not make the running
keyboard depend on a Git checkout:

```sh
nix-store --add ./home/config/squeekboard-preview
```

For **only the Squeekboard process**, use:

```text
GTK_THEME=Adwaita:dark
G_RESOURCE_OVERLAYS=/sm/puri/squeekboard=<store-copy>/resource
SQUEEKBOARD_KEYBOARDSDIR=<store-copy>/keyboards
```

GLib resource overlays let this preview replace keyboard CSS without a rebuild,
without changing the global GTK theme, and without editing Nix-store files.
The installed source's `src/style.rs` loads these resource paths. Layout
selection is documented in Squeekboard's `doc/layouts.md`.

The supervised temporary trial also sets these Squeekboard preferences:

```text
scale-in-horizontal-screen-orientation = 1.45
layout-shape-changes-to-fit-panel = true
```

Capture and restore their original values when the trial exits, alongside the
original `screen-keyboard-enabled` value. Do not restart the main browser, alter
input-source settings, launch a second input-method keyboard or modify the dock.
The original temporary trial supervisor stopped/restored on workspace exit or a
10-minute timeout. The packaged iteration trial now provides scoped lifecycle
management and a one-hour safety timeout; it is still explicit session-only
tooling, not the default deployed tablet launcher.

The wide layout's aspect ratio is deliberate: Squeekboard caps wide-layout
stretching at 1.4, and otherwise falls back to uniform scaling. Wider key
outlines plus a moderate panel height avoid that phone-width fallback.

## Checks

```sh
squeekboard-test-layout home/config/squeekboard-preview/keyboards/gb_wide.yaml
python -B -m unittest discover -s tests -p 'test_keyboard_preview.py' -v
```

Also inspect an actual screenshot and confirm focus-driven show/hide in a
native entry and Vivaldi. Physical touch/typing comfort, active Shift styling,
all symbol views and portrait behaviour need user testing before promotion.
No permanent deployment is implied by accepting this source-only preview.
