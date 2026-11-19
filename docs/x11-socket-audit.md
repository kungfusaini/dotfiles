# X11 socket disappearance diagnostics

Slack intentionally uses XWayland with an explicit 1.25 scale factor: native
Wayland caused huddle-preview rendering problems. On 2026-11-12, new Slack
processes crashed because `/tmp/.X11-unix/X0` was missing while XWayland was
still running. Its alternate `X0_` socket remained usable. A temporary symlink
restored access; the process responsible for that original removal was not captured.

## Confirmed recurrence and prevention (2026-11-19)

At 19:13:15, audit recorded Xvfb PID223507 successfully unlinking
`/tmp/.X11-unix/X0` from a Music-stream headless probe. The probe launched
`Xvfb -displayfd` in the host filesystem/network namespaces. Steam's later
19:48 launch failed after Pressure Vessel reported that the filesystem socket
was missing; `DISPLAY=:0` was correct. Automatic display selection is **not**
namespace isolation: even an unsuccessful display candidate can remove a
socket path. An unused display number or bare `xvfb-run` is not sufficient.
This identifies this recurrence, not necessarily the original November12 event.

Use the installed **`private-x11-run COMMAND [ARG ...]`** for X11 probes:

```sh
private-x11-run python3 /absolute/source/path/gui-probe.py
python3 tests/test_private_x11.py -v
```

The package uses Bubblewrap with private network/PID/IPC namespaces, a private
`/tmp` (sockets **and lock files**), a minimal `/dev`, hidden user/system bus
socket directories, a cleared environment, fresh preferences and a private
D-Bus session. The maintained `xvfb-run` starts Xvfb inside that boundary;
no custom display allocator or unsafe fallback is used. The host filesystem is
read-only except a fresh per-run artifact directory mounted at `/tmp/work`.
Its host location is printed to stderr under `~/.cache/private-x11/`; artifacts
are retained, not automatically deleted. Write screenshots/results there.
Host `/tmp` probe scripts are deliberately unavailable: keep probes in a source
directory. The invoking working directory must also exist outside host `/tmp`.
The default isolated X server is 1600×1000, with no hardware/audio playback.
This is accidental test-isolation protection, not a security sandbox for hostile
programs or authorization to access unrelated data on the read-only host tree.
Tests needing other devices or a compositor require a separately verified
isolated harness; do not weaken this runner to get them working.

The live regression repeats the culprit's `Xvfb -displayfd` startup and cleanup
inside the runner, confirms private filesystem/abstract-socket namespaces and
fresh session state, and checks the host X11 path inodes/symlinks are unchanged.
It never deletes, renames or creates a host X11 socket. An explicit runner build
can be tested with `PRIVATE_X11_RUN=/nix/store/.../bin/private-x11-run`.

For this incident, live access was restored without restarting the desktop:
after confirming `X0` was absent and the same user's alternate `X0_` socket
was listening and accepted a connection, `X0 -> X0_` was created. This is a
session repair, not the permanent prevention mechanism; normal XWayland owns
socket creation on the next desktop session. Never replace an existing socket
or blindly create this link. A real filesystem X11 connection then succeeded;
Steam completed startup/login and subsequently shut down gracefully. No game
was launched as part of that startup check.

The host module `hosts/kirax1/modules/services/x11-socket-audit.nix` enables
Linux Audit and records unlink, rename and rmdir operations within
`/tmp/.X11-unix`, for both 64-bit and 32-bit callers. It does not prevent
removal, recreate sockets, enable abstract sockets, or change Slack settings.
Existing processes may not be fully auditable until the next boot with the
configured `audit=1` kernel parameter; verify live coverage rather than
assuming activation proves coverage.

Inspect matching events as root:

```sh
ausearch -k x11_socket_changes -i
```

Look at the operation, success/exit result, paths, executable, PID, parent PID,
and user IDs. Audit records may contain process command lines; do not paste
raw records into public reports or commit them. Enabling the audit daemon also
collects ordinary kernel/userspace audit events, not just this filesystem rule.
Logs are local under `/var/log/audit` (directory mode 0700), with four rotating
8 MiB log files. Low-space and disk-error actions suspend logging rather than
halting the laptop. Check `auditctl -s` for lost events when diagnosing gaps.

Validate configuration:

```sh
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/x11-socket-audit.nix { inherit config; }'
```

Run `sudo python3 tests/x11-socket-audit-live.py` after deployment for a live
check. It creates a uniquely named disposable regular file within the socket
directory, renames it, then unlinks it, and checks its keyed events. It also
checks an outside-directory negative control and audit loss counters, printing
only a non-sensitive summary. Never delete or rename a live socket for testing.
Do not restart XWayland or the desktop merely to test the rules.

References: [auditctl](https://man7.org/linux/man-pages/man8/auditctl.8.html),
[auditd.conf](https://man7.org/linux/man-pages/man5/auditd.conf.5.html),
[Bubblewrap](https://github.com/containers/bubblewrap),
[X server automatic display selection](https://github.com/mirror/xserver/blob/master/os/connection.c).
