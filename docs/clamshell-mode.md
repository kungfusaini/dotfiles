# Clamshell and folded-keyboard modes

## Everyday clamshell use

1. With the laptop open, connect an external screen and let it become active.
2. Close the lid. The external screen remains the desktop; the laptop panel
   powers off. This works on battery and AC, with no peripheral-presence check.
3. Open the lid to restore the preceding display geometry, modes, scales,
   rotations, mirroring, workspace placement and monitor focus.

A normal lid close without an external screen still suspends, including on AC.
Systemd-logind owns suspend policy; this feature does not install a lid inhibitor
or replace the power manager. `HandleLidSwitchDocked=ignore` uses logind's native
external-display/dock detection. A hardware-reported dock can also trigger that
policy even without a screen; this is not a custom peripheral detector.

There is no plug-to-wake feature. Hotplug/startup checks recover existing mode
state but do not enter clamshell mode. Connect the screen while the lid is open.
Wireless/streamed displays are not implemented here.

## Separation from folded-keyboard mode

Double F7 still enters/restores the existing explicitly requested folded mode,
with its ISH safeguards, touch/pen inhibition, base keyboard/TrackPoint support,
and external-disconnect restoration. Clamshell never changes ISH or input devices.
Single F7 and Shift F7 remain the normal mirror/layout controls with the lid open.
Open the lid before changing mirror/extended mode or entering folded mode;
these commands refuse to overwrite an active clamshell-owned layout.

The lid helper, folded-mode controller and F7/layout mutations share the existing
`headless-mode/lock`. Synchronous nested display helpers inherit lock ownership
from their caller. Lid handling defers whenever the privileged folded-mode state
is not `off`.

## Implementation and recovery

- `hosts/kirax1/modules/hardware/clamshell-mode.nix` explicitly declares logind's
  lid policy. No charger/peripheral gating is added.
- `home/scripts/display/clamshell-mode.py` handles locked-session-capable
  Hyprland lid bindings. It checks the real ACPI lid state to reject stale events.
- A per-compositor-session journal lives at
  `$XDG_RUNTIME_DIR/clamshell-mode/state.json`. A new compositor discards stale
  session state rather than replaying old workspace commands.
- The panel is disabled in the compositor, leaving no invisible desktop.
  External mirrors are made independent before disabling their original source.
  The existing watcher checks reopening and external loss and keeps saved-layout
  hotplug handling out of clamshell-owned transitions. It tracks connected outputs
  (including disabled/mirrored ones) so queued compositor-enable events cannot
  overwrite restoration with Shift-F7's saved geometry or preferred modes.
- If the last external output disappears, Hyprland can enter an unsafe
  zero-output state in which monitor keywords no longer settle. Only then,
  recovery journals and creates a uniquely named temporary headless output to
  restart output transactions. It enables the real panel first and removes that
  exact task-owned output before completing restoration. An interrupted recovery
  retains the output name for cleanup on retry.
- Restoration returns all surviving workspace assignments, including inactive
  workspaces, before selecting the original visible workspaces and monitor focus.
  Failed transitions retain their journal for retry. IPC commands and settling
  waits are bounded. Recovery errors
  are logged to `$XDG_RUNTIME_DIR/clamshell-mode/recovery.log`.

Manual recovery: open the lid and run `clamshell-mode open` if necessary. No
system-wide sensor or input changes need undoing.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_clamshell_mode.py
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/clamshell-mode.nix { inherit config; }'
```

The opt-in real compositor test runs Hyprland inside a headless labwc on a private
Wayland/DBus session. It never connects to the everyday desktop or uses global
input; only physical lid readings are simulated:

```sh
PYTHONDONTWRITEBYTECODE=1 dbus-run-session -- \
  python3 tests/clamshell_live.py --labwc /path/to/labwc \
    --watcher /path/to/headless-monitor-watch
```

It runs the packaged watcher with private folded-state/lid fixtures and covers
extended and mirrored entry, inactive workspace restoration, non-preferred modes,
stale saved-layout geometry, reopening, watcher-restart recovery, and
external-disconnect recovery through real IPC. Hardware lid/suspend behavior still needs a physical
check after an explicitly approved deployment; isolated tests cannot establish it.

References: [Hyprland switch bindings](https://wiki.hypr.land/configuring/core/binds/switches/),
[logind lid policy](https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html).
