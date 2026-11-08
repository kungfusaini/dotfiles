# Clamshell and folded-keyboard modes

## Everyday clamshell use

1. With the laptop open, connect an external screen and let it become active.
2. Close the lid. The external screen remains the desktop; the laptop panel
   powers off. This works on battery and AC, with no peripheral-presence check.
3. Open the lid to restore the preceding display geometry, modes, scales,
   rotations, mirroring, workspace placement and monitor focus.

Without an external screen, closing the lid blanks the panel without disabling
its render output. It normally suspends, including on AC, but working tracked
agents now defer lid-triggered sleep (see below).
Systemd-logind still owns suspend policy. `HandleLidSwitchDocked=ignore` uses
logind's native external-display/dock detection. A hardware-reported dock can also trigger that
policy even without a screen; this is not a custom peripheral detector.

There is no plug-to-wake feature. Hotplug/startup checks recover existing mode
state but do not enter clamshell mode. Connect the screen while the lid is open.
Wireless/streamed displays are not implemented here.

## Wait for agents before sleeping

`agent-lid-sleep.service` watches Project Object's Pi activity records across all
projects and streams. While any live tracked agent is `working`, it holds a
logind **`handle-lid-switch` block inhibitor**, not a `sleep` inhibitor. After all
agents are idle (finished or awaiting input) for five seconds, it releases the
inhibitor. Logind rechecks a still-closed lid and applies its existing policy.
Opening the lid removes the pending lid action naturally. Reading replies is
not required. Manual sleep and UPower's critical-battery hibernation are not
blocked. No explicit suspend command or deferred sleep queue is created.

The user service belongs to the graphical session. It scans every 250 ms, so
allow a moment after starting an agent before closing the lid. Records must
match a live PID's process birth time; exited/zombie processes and stale PID
reuse cannot keep the laptop awake. Long tool calls do not expire by timestamp.
This covers only agents publishing Project Object activity, not arbitrary jobs
or untracked agents. A genuinely stuck working agent keeps lid sleep deferred;
manual sleep still works. To disable deferral for the current session:

```sh
systemctl --user stop agent-lid-sleep.service
```

Stopping the service releases its inhibitor immediately; if the lid is closed,
normal lid sleep may happen then. Start it again with `systemctl --user start
agent-lid-sleep.service`. Inspect its state using `systemd-inhibit --list` and
`journalctl --user -u agent-lid-sleep.service`.

Keep the laptop ventilated while agents run; a closed lid does not mean it is
safe to put in a bag. This feature does not introduce an automatic screen lock.

Implementation: `home/modules/agent-lid-sleep.nix` and the self-tested
`home/packages/agent-lid-sleep/` package. The inhibitor intentionally leaves the
host's power policies untouched. Logind's
[closed-lid recheck implementation](https://github.com/systemd/systemd/blob/v260.4/src/login/logind-button.c) handles
release/reopen; [low-level inhibitors](https://systemd.io/INHIBITOR_LOCKS/) are
independent of high-level sleep inhibitors.

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

The agent package runs its activity/lifecycle unit tests during its Nix build.
Check wiring with `tests/agent-lid-sleep.nix` in the same way as the clamshell
expression above. An opt-in real-logind test uses private activity fixtures,
requires the physical lid to remain open, and never requests sleep:

```sh
python3 tests/agent_lid_sleep_live.py --binary /nix/store/...-agent-lid-sleep/bin/agent-lid-sleep
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
external-disconnect recovery and panel-only DPMS blank/reopen through real IPC. Hardware lid/suspend behavior still needs a physical
check after an explicitly approved deployment; isolated tests cannot establish it.

References: [Hyprland switch bindings](https://wiki.hypr.land/configuring/core/binds/switches/),
[logind lid policy](https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html).
