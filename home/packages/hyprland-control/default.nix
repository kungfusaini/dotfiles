{ lib, pkgs, python3, hyprland }:
let
  source = lib.cleanSourceWith {
    src = ./.;
    filter = path: type: type == "directory" || baseNameOf path == "hyprland_control.py";
  };
  command = pkgs.writeShellApplication {
    name = "hypr-control";
    runtimeInputs = [ python3 hyprland ];
    text = ''exec ${python3}/bin/python ${source}/hyprland_control.py "$@"'';
  };
in command.overrideAttrs (old: { passthru = (old.passthru or { }) // { pythonPath = source; }; })
