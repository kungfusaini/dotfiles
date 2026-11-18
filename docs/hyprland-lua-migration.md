# Hyprland desktop Lua migration

This is a preservation-only migration of the fully merged desktop, not the old
Lua experiment in `home/config/hypr/conf`. Installing these files is not a
backend cutover: a compositor restart and new tablet-shell activation remain
separate, explicitly approved operations.

## Configuration and transition

`home/modules/hypr.nix` now uses Home Manager's native Lua renderer. Project
Object, Pegasus and the existing tablet-workspace module contribute native
settings too. The active entrypoint is generated `hypr/hyprland.lua`; historical
Lua files are not sourced, and hyprgrass remains disabled.

The frozen `home/config/hypr/legacy-transition.conf.nix` retains the complete
pre-migration desktop as `hyprland.conf`, with declarative executable paths.
This is **not** a stale policy dummy or a second maintained desktop. Hyprland
caches its backend/configuration path: deleting that file while an old session
is running makes a later reload regenerate defaults. New sessions prefer Lua
when both files exist. Retire this transition snapshot only after a separately
approved native-session cutover has been accepted. Do not add new features to it.

The obsolete activation action that archived `hyprland.lua` has been removed;
it must not move the new managed entrypoint. Existing historical backups remain
untouched. NixOS/UWSM retains session ownership; Home Manager still has
`systemd.enable = false`, `package = null`, and `portalPackage = null`. Portal
routing, Waybar, normal multi-window behavior and browser profiles are retained.
The NixOS Hyprland module supplies its compositor-paired portal exactly once;
the existing environment-recovery wrapper executes that final portal rather than
an additional unpaired package. `tests/hyprland-portals.nix` checks the count and
wrapper target. A full-system build also verifies generated user-unit collision
freedom; evaluation alone is insufficient.

## Runtime interfaces and narrow compositor extensions

The pinned 0.56.2 Lua backend rejects legacy `dispatch` syntax and `keyword`.
Repository-owned callers use `home/packages/hyprland-control` for their audited
internal operations, or native rule/config calls. This does not replace global
`hyprctl`, interpret arbitrary Hyprlang, import environment state, or patch in a
second configuration engine. Unknown operations and legacy exec-prefix strings
are rejected. Exec placement is supplied as a native rule table, before mapping.
The actual target backend is negotiated with harmless `eval do end`, including
the old-session/new-files transition; an unknown response fails closed.

Two opt-in extensions are packaged on the pinned NixOS compositor:

- `rule:clear_effects()` clears both effect storage and effect membership, returns
  the previous effect count, and rejects enabled or expired rules. Existing
  `hl.window_rule` behavior is unchanged. Owned launchers disable, clear and
  replace one named rule in one callback; matches always use the same keys.
  Existing ownership locks and explicit result-body checks are preserved.
- `hl.monitor({output=..., reset=true, ...})` starts from a fresh monitor rule,
  matching legacy full-rule replacement. The default remains a partial update.
  Full enable/unmirror/recovery operations cannot retain stale disabled, mirror,
  transform, color or optional VRR state. Orientation deliberately does not reset.

Browser, local-file, automation-browser and Steam rules remain exact-class and
launch-scoped. No post-map focus correction substitutes for pre-map safety.
The comms grouping script, picker and agent-aware screen-sleep DPMS calls are
also migrated; zero exit status with a rejected compositor body is not success.

Headless entry reads its expected immutable watcher identity from declarative
`hypr/desktop-policy.json`, retaining PID/executable checks. Tablet guards query
the no-animation contract attached to the actual loaded Lua policy; legacy
sessions retain their original text check. Recovery tokens follow the actual
backend's configuration identity, not whichever file happens to exist. Native
boolean `getoption` replies are normalized to the existing integer lease format.

## Verification

The canonical integration reference is main commit
`2e2e35509dc472214760d255a08170129ac75827`, not a copy of the new settings.
This retains the newer independent Loupe windows and absolute file-link support.
Private tablet-shell prototype/preparation modules are deliberately not promoted;
the desktop gate uses standalone test-only compositor helpers and fixtures.
`tests/hyprland-desktop.nix` accepts the candidate and reference Home Manager
configurations and exposes `unit`, `runner`, `browserRunner`, and `fileRunner`.
For example, from this repository (non-privileged):

```bash
nix build --impure --no-link --expr '
  let
    f = builtins.getFlake (toString ./.);
    b = builtins.getFlake ("git+file://" + toString ./.
      + "?rev=2e2e35509dc472214760d255a08170129ac75827");
    c = f.nixosConfigurations.kirax1.config;
    t = import ./tests/hyprland-desktop.nix {
      pkgs = f.nixosConfigurations.kirax1.pkgs;
      hyprland = c.programs.hyprland.package;
      homeConfig = c.home-manager.users.sumeet;
      baselineHome = b.nixosConfigurations.kirax1.config.home-manager.users.sumeet;
    };
  in t.unit'
```

- Inert native-API capture independently accounts for all 77 bindings and their
  semantic flags/order, 25 window rules, eight startup commands, 50 explicit
  settings, five curves, 17 animations, monitor/device/layer/gesture/environment
  declarations, plus every executable line of the frozen transition config.
- The real hidden legacy/Lua gate compares 353 effective options/defaults, binding
  flags/order and animations; checks representative mapped-window rule outcomes;
  exercises old-session activation/reload, typed setting restoration, actual
  DPMS, monitor mirror/extended/disable/restore and partial rotation, mixed
  internal/client fullscreen pairs, real four-app comms grouping and tab-preserving
  reentry without swallowing Teams auxiliaries or relaunching existing apps,
  actual persistent picker show/dismiss/move, and one native rule with three effects after
  100 updates. Enabled-rule clearing must fail without losing existing policy.
- Actual Super+left drag and Super+right resize/release are checked on both
  backends. Native mouse dispatchers intentionally use `__lua`/`releasePending`
  instead of the legacy `mouse` flag. The test retains raw snapshots and proves
  behavior rather than pretending the flags are byte-identical. Only the exact
  disposable wtype device is calibrated to use its synthetic keymap symbols and
  no shared physical master, after comparing the unmodified GB/shared-state
  settings. This is not physical-keyboard acceptance.
- Lua-backed real Vivaldi tests cover fresh/shared-process/same-workspace/wrapped/
  multi-URL/direct/raw/background launches, shared synthetic cookies, correct
  initial-map workspace and no transient focus theft. Lua file-action tests
  cover repeated HTML/image/PDF/folder/editor opens, absolute hrefs, special
  filenames, independent Loupe instances and actual decoded image pixels.
  Profiles, pages, DBus, input and compositors are disposable/private; Chromium's
  sandbox is retained. No real account or browser session is used.
- Existing Project Object, Steam, automation-browser, display and tablet unit
  contracts remain checked. `home/packages/project-object/scripts/test` still
  works. Mocked legacy transport is explicit; those unit tests alone are not
  evidence of native behavior. Steam also installs the transport module beside
  its raw independent worker, with a clean-environment install check: the worker
  must not depend on wrapper-only `PYTHONPATH` surviving systemd activation.

Pinned upstream has two native `getoption` font-weight type-reporting gaps.
The differential gate reads their actual values with `hl.get_config` instead
of skipping them; both equal the old values. This diagnostic representation
limitation is recorded, not a desktop-setting discrepancy.

A live login/cutover, physical monitor hotplug, real lid/suspend, touch/pen/hinge
and OSK acceptance remain separate. No test here imports a private compositor
into the real user-manager environment or executes the eight real startup
commands. Do not claim untested hardware or live-session equivalence.

## Upstream references

- [Lua migration and backend selection](https://hypr.land/news/26_lua/)
- [Pinned IPC behavior](https://github.com/hyprwm/Hyprland/blob/efb50993780079460b0cbed1363e2166a2de1d9f/src/debug/HyprCtl.cpp)
- [Pinned native rules and monitor updates](https://github.com/hyprwm/Hyprland/blob/efb50993780079460b0cbed1363e2166a2de1d9f/src/config/lua/bindings/LuaBindingsConfigRules.cpp)
