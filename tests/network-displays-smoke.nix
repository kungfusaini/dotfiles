# nix build --impure --no-link --expr \
#   'let f = builtins.getFlake (toString ./.); in import ./tests/network-displays-smoke.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
{ pkgs }:
let
  networkDisplays = pkgs.callPackage ../home/packages/gnome-network-displays { };
in
pkgs.runCommand "network-displays-smoke" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"
  python3 ${./network-displays-smoke.py} \
    --package ${networkDisplays} \
    --gstreamer ${pkgs.gst_all_1.gstreamer.bin}
  touch "$out"
''
