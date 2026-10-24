{ pkgs, ... }:

let
  platformProfileWaybar = pkgs.writeShellApplication {
    name = "platform-profile-waybar";
    runtimeInputs = [ pkgs.coreutils ];
    text = builtins.readFile ../scripts/power/platform-profile-waybar;
  };
in
{
  _module.args = {
    inherit platformProfileWaybar;
  };
}
