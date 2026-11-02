# Optional GNOME tablet session

GNOME Wayland is offered alongside Hyprland in the existing DMS login screen.
Hyprland (UWSM) remains the configured default. The greeter may remember a
previous manual selection, so check the session chooser before logging in.
GDM is not enabled. Folding does not switch desktops.

This is a separate session, not a nested desktop or a second account: files,
apps and user settings are shared, but open Hyprland windows do not transfer.
Finish/save work before logging out. Do not run both desktops concurrently for
this test: they share user services and the D-Bus environment.

## After an explicitly approved deployment

1. Save work, log out, and select **GNOME** in the existing greeter.
2. Start with GNOME Settings and a native text app. Touch a text field and check
   that the built-in keyboard opens, types, and dismisses correctly. Do not run
   the Hyprland `tablet-osk` script or Squeekboard in GNOME.
3. Fold and rotate through both portrait directions. Check display orientation,
   touchscreen corner accuracy, and pen alignment. Check rotation lock in Quick
   Settings if rotation does not happen.
4. Open an HTTP/HTTPS link from another app; it should open directly in Vivaldi
   without Hyprland workspace routing. Try browser scrolling, overview gestures,
   video playback, and suspend/resume.
   Keyboard behaviour can differ between native Wayland and XWayland apps.
5. Log out and select **Hyprland (UWSM)**. Confirm workspaces, Waybar, file
   dialogs, notifications, and screen sharing still work normally.

The existing kernel option `intel_hid.enable_sw_tablet_mode=0` is deliberately
unchanged: it preserves physical keyboard availability when folded. GNOME may
not detect convertible posture as expected with this policy. Sensor proxy is
enabled, but neither automatic rotation nor automatic keyboard behaviour is
claimed verified until tested physically. If needed, GNOME's Accessibility →
Typing → Screen Keyboard can be tried manually; this is not forced globally.

## Validation (no deployment)

```sh
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/tablet-session.nix { inherit config; }'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

Sources: `hosts/kirax1/modules/desktop/gnome-tablet-test.nix` and the
session-aware portal wrappers in `hosts/kirax1/modules/desktop/hyprland.nix`.
Removing the GNOME test module import and its dedicated module removes this
trial; the portal session guard is safe to retain. Deployment is a separate
approval step and must use `deploy-kirax1` from clean, reviewed `main`.
