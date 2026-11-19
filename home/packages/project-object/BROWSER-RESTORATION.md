# Guarded browser checkpoints

**Automatic restart restoration remains incomplete.** The guarded release
supports native checkpoints, same-instance restoration and adoption of already
recovered windows. Explicit project Browser-open offers **Restore saved windows /
Cancel** when saved windows are missing after a browser restart. It warns that
late Vivaldi recovery could still create duplicates. Cancel (also Escape/window
close, and the default response) leaves the saved session untouched and produces
no error notification. No restart replay occurs without this per-operation consent.
A quiet inventory, confirmation or fixed delay is not proof of startup completion.

The existing browser process must be restarted normally to load the packaged
adapter and companion extension. Deployment does not close or restart user tabs.
Until the bridge is available, last-scope project closure leaves Browser windows
open and reports a checkpoint error instead of using the old unguarded close.

## Implemented

- Vivaldi 8.2.4133.52 version-gated packaged UI adapter; no debugger, eval,
  HTTP listener, or secret in the Nix store.
- A companion extension with only `nativeMessaging`; only Vivaldi's own UI
  extension may connect. The host exposes a mode-0600 UNIX socket inside the
  private runtime directory and checks peer UID. This is same-user IPC, **not**
  a sandbox against other processes running as the user.
- The browser ancestor's PID/start time and single open History/Web Data
  profile identify the browser. Multiple regular profiles fail closed.
  Chromium rewrites argv as a space-joined process title, so argv is not used
  to discover profile paths.
- Per-window temporary title challenges bind native IDs to exact compositor
  addresses and browser PID. Global focus, title similarity, list order and
  speculative window movement are never ownership evidence.
- Last-scope picker closure first requests `project-browser checkpoint-close
  --project-id UUID`. All project Browser windows must be mapped before save.
  Unknown apps/private windows and Vivaldi internal Workspaces are refused.
- Native named sessions retain tab order, pins, stacks and browser history.
  Each saved binary must become visible in the native index and be stable
  across two reads before an independently fsynced, private backup is created.
  The atomic checkpoint journal precedes any destructive close operation.
- Pinned tabs are removed only after save, avoiding Vivaldi's cross-window
  pinned-tab migration. Known unload handlers and changed inventories refuse
  closure. The journal remains `closing` on interruption; a partial recovered
  window is not silently adopted as intentional user edits.
- Every tab's provenance is checked before ownership mutation. Conflicting
  project provenance is rejected during tag/save/adoption/startup placement.
  Native sessions omit window `vivExtData`, but retain tab `vivExtData`; only
  unanimous tab provenance can recover window ownership.
- Explicit project Browser-open restores the checkpoint in the **same adapter
  instance** and adopts already recovered windows after restart. Missing windows
  across instances require confirmation in a uniquely identified GTK dialog on
  the invoking workspace, without initial focus or activation theft. The restore
  button stays disabled until its PID/class/placement are verified. Consent is
  neither persisted nor reused after another open or adapter change. Restore
  requests carry the expected PID/start-time/profile/adapter identity; the receiving
  native host and adapter reject stale consent before invoking native replay. Fresh
  inventories before each replay adopt recovery that arrives during the prompt;
  the native adapter also rejects a key already present immediately before open.
  A final inventory rejects late duplicates without closing either window. These
  checks reduce races, but cannot exclude recovery arriving after the last check.
  Noninteractive callers and startup reconciliation never prompt or bypass the
  cross-instance guard. Repeated open does not replay an already present key. Split windows with duplicate keys
  are refused before closure. An unresolved `closing` journal cannot be replaced
  by a retry; only explicit fully verified recovery resolves it. A completed
  checkpoint also cannot be replaced while any earlier window key remains
  unrecovered, so a partial restart cannot discard the missing records. Startup
  reconciliation only moves identified recovered windows silently; it does not
  restore or close them.

Private checkpoints live under the existing project data root:

```
projects/UUID/browser/checkpoint.json
projects/UUID/browser/checkpoints/GENERATION/INDEX.bin
```

Native named sessions are also retained in the same browser profile. Both the
private backup and native original must pass SHA-256 verification before replay.
Automatic reimport if a native original is deleted is **not implemented**; the
private backup is retained and replay fails closed. Old generations are not
garbage-collected yet. No URL-only fallback is used.

## Blocking uncertainty

Independent review found that bridge readiness is not proof that normal
startup SessionRestore has finished. A missing window might appear later, making
an immediate replay duplicate it. Unattended replay of missing
keys across adapter instances is therefore still refused. It still adopts already recovered windows without
replaying their older checkpoint.

`vivaldi.utilities.onSessionRecoveryStart/Done` exist, but early listeners in a
fresh profile and subsequent full-process restart observed neither event during
ordinary “last session” startup. Their existence is not evidence of a normal
startup barrier. The [Modders API reference](https://lonmcgregor.github.io/VivaldiModdersAPI/OfficialApi/utilities.html#onSessionRecoveryDone)
only describes session recovery. Chromium's authoritative
[`SessionRestore::IsRestoring`](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/sessions/session_restore.h)
is internal C++, not a public extension API. Do not replace this guard with a
sleep and claim the race is solved.

The user approved the narrower explicitly confirmed recovery flow. Complete
automatic restart restoration remains separate unfinished work: establish an
authoritative barrier in the version-pinned native/UI startup path before enabling
unattended replay. Neither the confirmation nor its warning claims to solve that
race. Backups are retained; no URL-only reconstruction, automatic duplicate
closure, profile replacement, or browser startup-setting change is used.
The additional receiving-host/adapter checks load on the browser's next normal
restart; deployment does not restart existing browser processes. The Python
confirmation flow works with the existing adapter, which ignores the added fields;
newly started packaged browsers enforce the receiving-boundary checks too.

## Verification

From this package directory:

```sh
HYPRLAND_CONTROL_TEST_BACKEND=legacy PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
node tests/browser-adapter.test.cjs
python3 tests/browser_restore_integration.py \
  --vivaldi-package /nix/store/...-vivaldi-8.2.4133.52 \
  --gui-package /nix/store/...-project-object-0.4.0 \
  --labwc /path/to/labwc --hyprland /path/to/Hyprland --hyprctl /path/to/hyprctl
```

The opt-in integration test copies only browser application resources, creates
its own synthetic profile, private DBus and hidden compositor, and uses local
fixture pages. It never accesses the live browser/profile/display or global
input. It checks private native checkpoints, pins/stacks, exact placement,
unchanged Beta tab contents, idempotent same-process restoration, full-process
restart adoption, confirmed missing-window replay, cancellation and recovery
arriving during confirmation. With `--gui-package`, real GTK dialogs exercise
Restore, Cancel, window-close and placement-verification failure without changing
focus. The package supplies its actual Python/GI wrapper environment; response
injection exists only in the isolated test, not production code.
Test artifacts remain in the printed temporary directory. Tests do not prove
ordinary Vivaldi startup completion. Deployment evidence belongs in the worklog.
