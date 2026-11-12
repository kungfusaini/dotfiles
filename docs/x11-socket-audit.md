# X11 socket disappearance diagnostics

Slack intentionally uses XWayland with an explicit 1.25 scale factor: native
Wayland caused huddle-preview rendering problems. On 2026-11-12, new Slack
processes crashed because `/tmp/.X11-unix/X0` was missing while XWayland was
still running. Its alternate `X0_` socket remained usable. A temporary symlink
restored access; the process responsible for removing `X0` is not known.

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
[auditd.conf](https://man7.org/linux/man-pages/man5/auditd.conf.5.html).
