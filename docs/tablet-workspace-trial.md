# Reversible tablet-workspace UX trial

This is one Hyprland session, not GNOME, Plasma, a second login or a suspended
session. Existing apps continue running. Entering creates/selects the dedicated
`tablet-trial` workspace without moving, closing or resizing existing windows.
Tablet apps remain parked there when you return to the laptop workspace.

## Controls (after explicitly approved deployment)

- Open **Tablet workspace trial** from the app menu, run `tablet-workspace enter`,
  or press **Super+Ctrl+T**.
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

The keyboard is manually toggled during this trial, even in laptop posture.
Returning to the laptop dismisses it without sending Escape into your work.
The original fold/headless keyboard policy is otherwise preserved. The OSK is
now packaged through Home Manager instead of launched from the checkout.

## Deliberate limits

No automatic folding transition, touchscreen gestures, changed monitor scale,
desktop-wide layout changes, or automatic app maximization. Tablet-only rotation
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
with the user. Before testing the keyboard, retire only the old checkout-based
`tablet-osk daemon` and start the deployed packaged watcher; an existing daemon
retains its old function definitions until restarted. Do not restart Hyprland,
greetd or the user session. Deployment and live switching require approval.
