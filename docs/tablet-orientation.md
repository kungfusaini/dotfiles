# Tablet-workspace-only orientation

This controller is prepared for the existing Hyprland **hyprlang** session, not
Lua. It uses the already verified iio-sensor-proxy through upstream
`monitor-sensor --accel`; it does not read stale HID raw sysfs channels itself.
It does not enter a workspace, fold the device, launch a tablet desktop, close
apps, change keyboard appearance, or alter the dock.

**No physical rotation or live-transform test is implied by simulated tests.**
Do not launch tablet mode or apply rotations during agent validation unless
Sumeet explicitly requests that live test.

## Activation and scope

After approved deployment, workspace entry (manual or automatic folding entry)
starts one `tablet-orientation daemon`. The fold watcher, not the orientation
controller, owns posture transitions; see [tablet-workspace-trial.md](tablet-workspace-trial.md).
Readings are claimed only when all of these hold:

- The workspace ownership record is enabled for the same compositor instance.
- `tablet-trial` is the focused workspace on `eDP-1`.
- The internal panel is enabled and awake, with no special workspace over it.
- Headless mode is off and Mewtion is not using the buffered accelerometer.
- Both configured built-in Wacom touch/pen devices are present.

**Tablet mode means the enabled foreground workspace**, not the hinge flag by
itself. The fold watcher enters that workspace when safe; folding in headless
mode does not. External displays and other input devices are not IPC targets.
Their positions, modes, scale and transforms are not rewritten.

The daemon stays idle, with no sensor claim, after leaving. Unknown/flat sensor
readings hold the last orientation. Changes must settle for 150 ms. Sensor
failure releases the claim, restores the baseline and retries with backoff.
A long scheduling/suspend gap invalidates cached readings and reclaims the
sensor. A vanished/asleep/headless internal panel defers restoration until it
returns; the recovery record is retained.

## Controller responsiveness

The controller adds a 150 ms stability check after the sensor service reports
an orientation, not the original 800 ms wait. It waits on `monitor-sensor`'s
readable pipe or the pending stability deadline, so new events/deadlines do not
have to wait for another fixed polling interval. Stable operation and inactive
mode keep the existing 200 ms safety-gate cadence; this is not continuous 50 ms
desktop polling. Every wake still rechecks the full tablet/headless/device
conditions before any change, and normal exit/recovery deadlines are unchanged.

This does not alter iio-sensor-proxy's own buffered-reading cadence (700 ms in
the pinned version), hardware sampling or the fade/resize settle hold. The
reduction in controller waiting is tested with simulated timing; end-to-end
physical response still needs user feedback rather than an assumed speed claim.

## Transform ownership and recovery

The controller snapshots the current monitor transform. It composes the normal,
left-up, bottom-up and right-up readings as relative rotations 0, 1, 2 and 3.
Those physical directions still need checking on the actual device.

Only `device[wacom-hid-5430-finger]` and `device[wacom-hid-5430-pen]` receive
input changes. While rotating, they are bound to `eDP-1`. Saved output mappings
and effective transforms are restored on exit. No global touch/tablet transform
is written. Reflected transforms are deliberately refused.

Hyprland 0.56 cannot query per-device options with `getoption`. The packaged
policy therefore takes per-device baseline values from Home Manager's structured
`settings.device` entries; absent values are read from the live global options
at entry. Built-in overrides in handwritten `extraConfig` are rejected. Do not
combine this controller with ad hoc per-device runtime overrides or a second
rotation helper: it cannot discover those overrides. Restoration makes the saved
effective values explicit until the next config reload; it does not recreate
an inherited/unset flag that Hyprland's IPC cannot expose.

A named `eDP-1, preferred, auto, 1.25` rule matches the existing generic policy.
This is required because this Hyprland version's transform-only command silently
does nothing without a named rule. Rotation updates only the transform on that
rule; it does not replace resolution, refresh rate, position or scale.

The runtime `tablet-orientation.json` journal is saved before any mutation.
Explicit workspace exit disables rotation, restores under the shared workspace
lock, then returns to the laptop workspace. Manual workspace switches are caught
by the 200 ms watcher. Rollback failures retain the journal and block explicit
return rather than falsely reporting success. The Back control stays visible
with rotation disabled; retrying Back (or `tablet-workspace leave`) completes
restoration and return without re-entering tablet mode. `tablet-orientation
restore` can also retry only the pending transform restoration. Stale compositor records
are discarded without applying them to a new session. A changed configuration is
authoritative: old overrides are not replayed over a new deployment, and a fresh
controller starts on the next explicit entry. If that entry races the old
daemon's shutdown, startup waits for the obsolete owner without holding the
workspace lock; a healthy current owner is simply reused.

Log: `$XDG_RUNTIME_DIR/tablet-orientation.log`.

## Rotation fade

Only a real display-transform change starts a disposable Quickshell overlay on
`eDP-1`, including restoring landscape on exit. Repeated sensor readings and
normal entry without a transform change do not flash the screen. The keyboard,
dock, global animation settings and external monitors are unchanged.

The overlay fades to black in 120 ms, acknowledges full opacity after it is
mapped plus a 34 ms render guard, then permits the existing transform transaction.
It stays opaque through monitor verification and the inherited windowsMove /
windows animation duration (current configuration: about 529 ms), then fades out
in 160 ms. The settle hold is bounded to 1 second, with a 550 ms fallback if the
animation query is unavailable. Unusually long custom animations or slow client
repaints may need tuning after physical testing.

Only the overlay namespace has Hyprland `no_anim` enabled so compositor layer
animations cannot double-animate its opacity. It reserves no workspace space,
does not capture screenshots or keyboard focus, and intercepts taps only while
covering the internal display. IPC selects the exact owned process PID, not a
shared/default Quickshell instance.

A missing cover acknowledgment cancels the change before the IPC transaction;
mode/headless/panel gates are rechecked after fading. A conservative 2.6-second
cover deadline bounds those IPC queries and reserves layout/reveal time; the
owned cover is rechecked immediately before any mutating request. A failed reveal clears its
owned surface without undoing a valid completed rotation. The Python driver
always terminates the disposable process, while QML independently clears/exits
after 3 seconds if its driver crashes or IPC is lost. A hidden startup instance
also expires automatically. No overlay remains resident between rotations.

QML/IPC validation may load an invisible instance and query status, but must not
call cover, reveal, or rotate the real compositor without an explicit live-test
request. Simulated tests supply fake Quickshell IPC in addition to the fake
sensor and Hyprland commands. `FadeState.qml` is a non-visual component so the
real Qt animation completion, mapped acknowledgment and timeout paths can also
run under `qmltestrunner` with the offscreen/software platform in a Nix sandbox.
Its animations must be standalone: Qt does not emit `finished` for animations
inside a Behavior or Transition, which would break the handshake.

## Non-live validation

```sh
python -B -m unittest discover -s tests -p 'test_tablet_*.py' -v
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/tablet-orientation.nix { inherit config; }'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
nix build --no-link --impure --expr \
  'let f = builtins.getFlake (toString ./.); in import ./tests/tablet-rotation-fade.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```

The subprocess integration test uses fake `hyprctl`, `monitor-sensor` and
`pgrep` executables and a temporary config/state directory. It never connects to
the real compositor or claims a real sensor. Later live verification needs a
separate explicit request: check both portrait directions, touch corners, pen
alignment, exit restoration, suspend/resume and external-monitor behaviour.
