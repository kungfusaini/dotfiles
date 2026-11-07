# Isolated Plasma Mobile session feasibility trial

This is an opt-in experiment, not a replacement desktop or an automatic fold
integration. It tests whether an upstream touch shell can coexist with the
existing Hyprland session and return without logout. Installing the module does
**not** launch a second desktop at boot or during deployment.

## Architecture and scope

- A separate locked-password account, `tablet-trial`, owns
  `/var/lib/tablet-session-trial-home` (0700), a user bus, audio services and fresh
  application profiles. No personal browser profile, cookies or credentials are
  copied. It has no administrative groups and is not an application sandbox.
- A second instance of the already installed **greetd** owns reserved **tty8**.
  Its PAM login registers with logind; it never restarts the laptop's greetd,
  UWSM, compositor or graphical session. Greetd uses a distinct runtime runfile
  and its upstream per-process IPC socket.
- The packaged **Plasma Mobile 6** session uses KWin, the upstream mobile shell,
  Plasma Keyboard and a fresh native-Wayland Chromium profile. The trial uses
  Plasma's supported classic startup path to avoid introducing globally active
  Plasma systemd units into the laptop's user manager.
- Global Plasma Desktop NixOS integration is deliberately **not** enabled:
  existing desktop defaults, portals, greeter and fold behavior are unchanged.
  The trial package supplies its own data/QML/plugin search paths.
- The trial has auto-lock disabled because its account has no unlock password.
  Do not store credentials in it. Laptop locking is never disabled or bypassed;
  returning to a laptop that has independently locked requires normal unlock.
- No process freezing, CPU quotas, download/music/agent pausing or RAM eviction.
  Whether an inactive KWin and its applications idle efficiently is measured,
  not assumed. The switch control and recovery run outside both user sessions.

The design adopts [Plasma Mobile](https://plasma-mobile.org/about/) and the
existing login manager rather than building another touch shell. Separate user
isolation avoids the [shared-service conflicts of same-user graphical sessions](https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md).
The cost is separate application profiles and resident memory. This is the
feasibility question, not a promise of transparent application migration.

## Controls

Run the installed `tablet-session-trial` controller, never scripts from the
checkout. Starting/stopping requires the owner's sudo authorization.

- `tablet-session-trial enter`: from the active, unlocked laptop session, save
  its exact logind identity and start the trial; subsequent entry activates the
  existing session without restart. Entry refuses occupied tty8 or another
  user's foreground desktop.
- **Return to laptop** in the tablet app grid: request a fixed root-owned
  oneshot through a narrowly scoped active/local-user polkit rule. It activates
  only the previously saved, revalidated laptop session; no arbitrary unit,
  command, target or unlock operation is delegated.
- `tablet-session-trial return`: owner/admin equivalent. It leaves the tablet
  session parked and will not steal focus from a third session.
- `tablet-session-trial stop`: return, stop the dedicated greetd and terminate
  only the trial user's remaining processes. It does not delete the account,
  profile, user data or packages.
- `tablet-session-trial status`: read-only session IDs; no sudo needed.
- `tablet-session-trial measure --seconds 120`: read-only JSON with per-user
  CPU deltas, cgroup memory and BAT0 energy/power/status. Outputs remain outside
  Git. `batteryDataUsable` is only a basic charging/session endpoint check, not
  proof that workloads, brightness or all intermediate conditions matched.

On startup failure the service's stop callback restores the saved laptop
session if tty8 is still foreground. The normal laptop remains on its original
VT (initially tty1), accessible with **Ctrl+Alt+F1** if the new shell becomes
unresponsive. No helper guesses or unlocks another session. The original session
record is revalidated at every return. Trial exit also requests return rather
than launching another mobile session in a loop.

Cold readiness checks that the trial has a logind seat/VT session, that its
separate bus owns KWin and Plasma Shell, and that a desktop containment exists.
It also checks the exact trial shell PID's journal for fatal QML/import errors
before acknowledging startup: a live process alone can leave a blank display.
Warm `activationAckSeconds` measures
logind command acknowledgment only, **not** first visible frame or perceived
transition latency. Physical inspection is mandatory.

## Verification and acceptance

1. Unit tests: controller source/target identity, first/warm startup, occupied
   VT rejection, no lock bypass/focus stealing, charging-data qualification.
2. `tests/plasma-mobile-session.nix`: upstream mobile shell and KWin on a
   private software-rendered virtual output, temporary HOME and private D-Bus;
   explicitly start the actual mobile shell, assert a desktop is loaded and
   reject fatal QML/import errors from forced-stderr logs. Do not auto-activate
   a default desktop shell through a readiness query. System bus access is
   disconnected. No host display, global input or personal profile.
   This does not establish DRM switching, audio, battery or touch acceptance.
3. Review and build the exact committed main snapshot non-privileged, then use
   `deploy-kirax1`. Verify the trial remains stopped after deployment.
4. First controlled visible round trip: start, verify actual shell and return;
   confirm original compositor and browser identities survived unchanged.
5. Test warm entry/return, touch navigation, app filling available screen,
   YouTube video fullscreen, settings over apps/video, keyboard and rotation.
   Do not claim all shell features work merely because a bus name appeared.
6. Battery A/B/A: laptop-only baseline, laptop with inactive tablet session,
   then laptop-only again. Match brightness, power profile, radios, workload,
   battery charging/discharging state and settling intervals. Measure CPU,
   resident memory and discharge energy over sufficiently long intervals;
   repeat before calling overhead acceptable. Also measure tablet foreground
   with laptop idle in background. Background useful work must be reported,
   not misattributed as shell overhead. AC measurements cannot prove battery life.

No app/profile/session deletion is automatic cleanup. The trial supplies the PowerDevil battery QML module without autostarting a
second power-management daemon; brightness/idle-power controls are not yet a
complete supported configuration. Folding should not be
rewired to this design until session switching, real touch/media behavior and
inactive power have passed physical acceptance.
