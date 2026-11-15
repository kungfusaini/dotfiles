# Exercise the actual packaged metadata argv shape without launching any game.
{ pkgs, homeConfig }:
let
  launcher = builtins.head (builtins.filter (p: p.name == "tablet-game-launch") homeConfig.home.packages);
  fixture = pkgs.writeShellScript "tablet-game-argv-fixture" ''
    test "$(umask)" = 0022
    test "$#" -eq 2
    test "$1" = 'argument with spaces'
    test "$2" = '--fullscreen'
    printf 'desktop passthrough verified\n'
  '';
in pkgs.runCommand "tablet-gaming-install-contract" { } ''
  export XDG_RUNTIME_DIR="$TMPDIR/runtime"
  mkdir -m 700 "$XDG_RUNTIME_DIR"
  export HYPRLAND_INSTANCE_SIGNATURE=private-contract
  umask 0022
  ${launcher}/bin/tablet-game-launch -- ${fixture} 'argument with spaces' --fullscreen > "$out"
  ${pkgs.gnugrep}/bin/grep -Fxq 'desktop passthrough verified' "$out"
  mkdir -p "$XDG_RUNTIME_DIR/tablet-games"
  printf '%s\n' '{"instance":"private-contract","pid":1}' > "$XDG_RUNTIME_DIR/tablet-games/pegasus.json"
  unset HYPRLAND_INSTANCE_SIGNATURE
  ${launcher}/bin/tablet-game-launch -- ${fixture} 'argument with spaces' --fullscreen > second
  cmp "$out" second
''
