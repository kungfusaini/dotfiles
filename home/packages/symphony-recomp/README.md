# SymphonyRecomp

Pinned upstream Linux x64 binary release, installed through `home/modules/pegasus.nix`.
This is beta software; upstream warns about game-breaking bugs. The source has no
license grant, so the package is marked unfree. No ROMs or saves enter the Nix store.

- Pegasus: **PlayStation → Castlevania: Symphony of the Night** (PS1/`psx`
  branding, grouped by the original console even though it runs natively).
- No desktop application-menu entry; Pegasus calls `symphony-recomp`.
- Pegasus metadata: `home/config/pegasus/custom.metadata.pegasus.txt`
- Curated artwork: `home/packages/pegasus-artwork.nix` (Konami promotional
  background, original USA cover, transparent logo).
- Disc: `~/matrix/data/emulation/roms/ps1/Castlevania - Symphony of the Night (USA)/`
  containing the USA CUE and its two referenced BIN files.
- Memory cards: `~/matrix/data/emulation/saves/symphony-recomp/`
- Writable settings, logs, packs, translations and mod cache:
  `~/matrix/data/emulation/games/symphony-recomp/`

`SYMPHONY_RECOMP_DATA_ROOT` overrides the emulation root for isolated tests. Settings
are seeded only when absent; existing settings and cards are never replaced.
Bundled mods are individual store-backed links inside a writable mod directory.
User-supplied mod directories are preserved. Upstream's update check is disabled
in the initial settings; use Nix to update the immutable application, not its
in-game updater. The first real launch still displays upstream's beta notice.

The wrapper disables .NET ReadyToRun: with the pinned .NET 10.0.12 runtime, the
release otherwise fails at startup with `BadImageFormatException`. JIT execution
successfully reaches the title screen. Native libraries are patched for NixOS;
the upstream script that downloads an unmanaged .NET runtime is not used.

## Verification

```sh
nix shell --impure --expr \
  '(builtins.getFlake (toString ./.)).nixosConfigurations.kirax1.pkgs.jq' \
  -c python3 tests/test_symphony_recomp.py
nix build --no-link --impure --expr \
  'let f = builtins.getFlake (toString ./.); in f.nixosConfigurations.kirax1.pkgs.callPackage ./home/packages/symphony-recomp {}'
python3 tests/test_symphony_pegasus.py
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

Runtime smoke test: use `xvfb-run` with `DISPLAY` and `WAYLAND_DISPLAY` unset,
`LIBGL_ALWAYS_SOFTWARE=1`, `ALSOFT_DRIVERS=null`, and a temporary data root holding
links to the legally owned disc. Acknowledge the beta notice only in that test
root's settings (`options["notices.SymphonyRecompBetaAck"] = true`). The tested
release loads `SLUS-00067`, compiles the bundled shader mod, and renders the title
screen using llvmpipe. An isolated Pegasus instance also parsed the registration,
resolved its built artwork and successfully launched this command through
`game.launch()`. Only test asset prefixes were redirected to the new artwork
store path; the registered disc and launch command were unchanged. This is not
evidence of physical GPU, sound, controller, long-session stability, or save/load
verification.

Upstream: https://github.com/BlackLabelHQ/SymphonyRecomp
Release: https://github.com/BlackLabelHQ/SymphonyRecomp/releases/tag/v1.1.2p
