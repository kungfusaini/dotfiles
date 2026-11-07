# Legacy tablet workspace controller

The deployed physical fold path, app-menu entry and **Super+Ctrl+T** now open
[new Tablet Home](tablet-home-preview.md), not this legacy button panel.
This page documents the underlying workspace/orientation controller and its
explicit `tablet-workspace enter` diagnostic interface. Its old `watch` command
must not run alongside the new `tablet-fold-watch`; they share a singleton lock.

This is one Hyprland session, not GNOME, Plasma, a second login or a suspended
session. Existing apps continue running. Entering creates/selects the dedicated
`tablet-trial` workspace without moving, closing or resizing existing windows.
Tablet apps remain parked there when you return to the laptop workspace.

## Controls (after explicitly approved deployment)

- Fold the ThinkPad to enter automatically; unfold to restore orientation and
  return to your previous workspace. The existing ThinkPad ACPI posture signal
  is checked every 500 ms; no input-device disabling or new sensor service.
- Open **Tablet workspace** from the app menu, run `tablet-workspace enter`,
  or press **Super+Ctrl+T** for manual entry.
- Large panel buttons: **New browser**, **Keyboard**, **Next app**, and
  **Back to laptop**. The panel is shown only on the focused trial workspace.
- **Super+Ctrl+T** or `tablet-workspace leave` returns to the workspace you left.
  It does not close tablet apps. If that workspace has disappeared, the command
  refuses to create a replacement; select a workspace with Waybar instead.
- Waybar and all normal desktop shortcuts remain available. You can also switch
  workspaces normally; the tablet panel hides when you do. One lightweight
  panel process stays alive while parked so rapid re-entry cannot lose the
  controls; it is not another desktop or login session.
- Browser creates a new Vivaldi window, sharing your existing browser profile.
  It does not move your current browser window. App-provided dialogs/links can
  still reuse existing windows: this is visual organization, not isolation.

The keyboard is manually toggled with **Keyboard**, including in laptop posture.
Returning to the laptop dismisses it without sending Escape into your work.
The old keyboard-only fold watcher is replaced, not run alongside the workspace
watcher. Both tools are packaged through Home Manager, not run from the checkout.

## Folding policy

One singleton `tablet-workspace watch` starts from Hyprland's session environment.
It uses the same action lock as manual entry/exit and orientation restoration.
Manual Back/shortcut exit is respected until the next unfold/fold cycle. No app
is launched automatically. Starting a session already folded also enters.

Entry waits for the internal `eDP-1` display to be awake, focused and not showing
an active special workspace. A retained tablet workspace on an external monitor
must be moved back manually; folding never moves apps or focuses that output. Unknown/unreadable posture never means unfolded.
Headless mode dismisses the keyboard and blocks transitions; a fold observed during headless use is consumed
so leaving headless does not unexpectedly switch workspaces. Unfold/refold to
enter afterward. Sensor/device/headless rotation safety checks remain unchanged.

Automatic exit restores orientation and dismisses the keyboard even if the saved
return workspace has disappeared; in that case select another workspace with
Waybar. If you already switched elsewhere, unfolding does not steal focus.
Restoration failures retain pending-exit state and are retried by the watcher;
manual Back/leave can also retry. A restarted watcher can finish an automatically
owned exit while unfolded. Explicit manual entry while unfolded is left alone.
Log: `$XDG_RUNTIME_DIR/tablet-fold-watch.log`.

## Deliberate limits

No touchscreen gestures, changed monitor scale, desktop-wide layout changes,
or automatic app maximization. Tablet-only rotation
is prepared separately in [tablet-orientation.md](tablet-orientation.md); its
simulated tests are not a substitute for an explicitly requested physical test.
This tests whether a separate workspace and touch controls feel useful before
investing in deeper tablet integration. It is not a claim of native tablet UX.
No browser or app is automatically started when entering the trial.

The unused GNOME session module and its trial documentation/tests were removed.
Reviewed desktop-aware portal/browser fixes remain. Pre-existing keyboard
packages and `~/matrix/projects/x1-tablet-mode` are not removed. Old Nix store
outputs/generations are left for the normal garbage-collection policy, not
manually deleted.

## Verification

```sh
python -m unittest discover -s tests -p 'test_tablet_workspace.py' -v
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/tablet-workspace.nix { inherit config; }'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

Live verification must record existing client addresses/workspaces, enter and
leave without launching/closing user apps, and confirm they are unchanged.
Check panel rendering, keyboard toggle, browser placement and portrait sizing
with the user. On the first deployment, retire only the existing `tablet-osk daemon`
process and launch the deployed `tablet-workspace watch` through
Hyprland's environment; `exec-once` is not rerun by a config reload. Confirm one
watcher and no old keyboard daemon remain. Later watcher upgrades also require
replacing the running watcher with the new packaged version. Do not restart
Hyprland, greetd or the user session. Deployment and live switching require approval.
