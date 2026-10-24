{ lib, pkgs, ... }:

let
  projectObject = pkgs.callPackage ../packages/project-object { };
in
{
  home.packages = [ projectObject ];

  xdg.configFile."pi/agent/extensions/project-object.ts".source =
    "${projectObject}/share/project-object/pi/project-object.ts";

  wayland.windowManager.hyprland.settings = {
    "$terminal" = lib.mkForce "${projectObject}/bin/project-terminal";
    bind = lib.mkAfter [
      "$mod, P, exec, ${projectObject}/bin/project-picker"
    ];
    exec-once = lib.mkAfter [
      "${projectObject}/bin/project-picker --preload"
    ];
  };
}
