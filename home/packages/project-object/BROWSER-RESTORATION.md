# Guarded browser checkpoints

**This is not complete restart restoration.** The guarded release supports
native checkpoints, same-instance restoration and adoption of already recovered
windows. Replaying a missing window after a browser restart is deliberately
blocked until startup recovery completion can be proved. A quiet inventory or
fixed delay is not such proof.

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
  instance** and adopts already recovered windows after restart. Repeated open
  does not replay an already present key. Split windows with duplicate keys
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
an immediate replay duplicate it. The draft therefore refuses replay of missing
keys across adapter instances. It still adopts already recovered windows without
replaying their older checkpoint.

`vivaldi.utilities.onSessionRecoveryStart/Done` exist, but early listeners in a
fresh profile and subsequent full-process restart observed neither event during
ordinary “last session” startup. Their existence is not evidence of a normal
startup barrier. The [Modders API reference](https://lonmcgregor.github.io/VivaldiModdersAPI/OfficialApi/utilities.html#onSessionRecoveryDone)
only describes session recovery. Chromium's authoritative
[`SessionRestore::IsRestoring`](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/sessions/session_restore.h)
is internal C++, not a public extension API. Do not replace this guard with a
sleep and claim the race is solved.

The user approved deployment of this limited, fail-closed release. Complete
restart restoration remains separate unfinished work: establish an authoritative
barrier in the version-pinned native/UI startup path, or agree a narrower
explicitly confirmed recovery flow. Add delayed-recovery regression coverage
and independent review before enabling missing-window replay across restarts.

## Verification

From this package directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
node tests/browser-adapter.test.cjs
python3 tests/browser_restore_integration.py \
  --vivaldi-package /nix/store/...-vivaldi-8.2.4133.52 \
  --labwc /path/to/labwc --hyprland /path/to/Hyprland --hyprctl /path/to/hyprctl
```

The opt-in integration test copies only browser application resources, creates
its own synthetic profile, private DBus and hidden compositor, and uses local
fixture pages. It never accesses the live browser/profile/display or global
input. It checks private native checkpoints, pins/stacks, exact placement,
unchanged Beta tab contents, idempotent same-process restoration and full
process restart adoption (or the deliberately fail-closed missing-window case).
Test artifacts remain in the printed temporary directory. It does not claim
that absent windows can currently be replayed safely after restart.

At the latest run: 225 Python tests and Node conflicting-provenance/partial-pin
failure injection passed; the maintained hidden integration passed; Nix builds
of project-object, patched Vivaldi and `tests/vivaldi-startup.nix` passed. These
checks used disposable profiles only. Live deployment/activation status is
recorded in the Surface worklog, not inferred from these isolated tests.
