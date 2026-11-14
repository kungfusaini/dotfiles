# Agent-aware sleep

`agent-lid-sleep` retains the normal lid policy, inhibiting only lid handling
while live, tracked Pi agents work.

`agent-screen-sleep` is an explicit, one-shot request, bound to
**Super + Shift + Escape**:

- After a 250 ms input-settle grace (so shortcut releases can finish), turn all
  displays off without locking. No work is suspended at this point.
- Wait until all tracked agents have been idle continuously for five seconds,
  then request normal system suspend without bypassing inhibitors.
- Keyboard or pointer activity while waiting restores displays and permanently
  cancels this request. A later idle period does not re-arm it.
- After submission, retain the request through logind's sleep/resume signals;
  restore displays on resume. No password-lock policy is added.
- Ignore duplicate requests. Cancel on external sleep, logind/bus loss, or
  activity-monitor failure. Do not persist requests across logout or reboot.

Tracking is exactly the existing `project-object/pi-activity` protocol, with
process birth-time validation. Untracked agents, downloads and arbitrary jobs
are **not** covered. Starting new work resets the five-second settle period.

The small Wayland helper uses [ext-idle-notify v2](https://wayland.app/protocols/ext-idle-notify-v1)
input notifications (not key contents) and intentionally ignores media idle
inhibitors for this explicitly requested action. A positive timeout is required:
Hyprland 0.56.2's zero-ms notification does not emit resumed events. A separate
helper is used instead of [swayidle](https://github.com/swaywm/swayidle), whose
normal timeout configuration uses whole seconds and obeys idle inhibitors.

The package build runs the tracker/state-machine tests and real-GLib integration
tests using fake activity and power/display commands; they do not blank or
suspend the test host. Compile the helper with warnings treated as errors.
Actual suspend/resume and physical input cancellation require a separately
controlled live test.
