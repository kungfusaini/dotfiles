{ config, lib, pkgs, ... }:

let
  cfg = config.programs.project-object;
  package = cfg.package;
in
{
  options.programs.project-object = {
    enable = lib.mkEnableOption "the system-wide project picker";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../. { };
      description = "Project Object package to install.";
    };
    enableHyprlandBinding = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Add Super+P and use the project-aware terminal in Hyprland.";
    };
    installPiExtension = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Install the Project Object Pi extension.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ package ];

    xdg.configFile."pi/agent/extensions/project-object.ts" = lib.mkIf cfg.installPiExtension {
      source = "${package}/share/project-object/pi/project-object.ts";
    };
    xdg.configFile."project-object/init" = lib.mkIf cfg.installPiExtension {
      source = "${package}/share/project-object/pi/skills/init";
      recursive = true;
    };
    xdg.desktopEntries.project-browser = {
      name = "Project Browser";
      comment = "Open web links in the active Project Object context";
      exec = "${package}/bin/project-browser open --mode adjacent %U";
      icon = "vivaldi";
      terminal = false;
      type = "Application";
      mimeType = [ "x-scheme-handler/http" "x-scheme-handler/https" ];
      noDisplay = true;
    };

    wayland.windowManager.hyprland.settings = lib.mkIf cfg.enableHyprlandBinding {
      "$terminal" = lib.mkForce "${package}/bin/project-terminal";
      bind = lib.mkAfter [
        "$mod, P, exec, ${package}/bin/project-picker"
        "$mod, X, exec, ${package}/bin/project-picker --close-active-workspace"
      ];
      exec-once = lib.mkAfter [ "${package}/bin/project-picker --preload" ];
      windowrule = lib.mkAfter [
        "match:class ^(dev.project_object.Picker|project-picker)$, float on"
        "match:class ^(dev.project_object.Picker|project-picker)$, center on"
        "match:class ^(dev.project_object.Picker|project-picker)$, size 760 570"
      ];
    };
  };
}
