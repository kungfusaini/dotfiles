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

    xdg.configFile."vivaldi/NativeMessagingHosts/org.project_object.browser.json".text = builtins.toJSON {
      name = "org.project_object.browser";
      description = "Private Project Object native-session bridge";
      path = "${package}/bin/project-browser-host";
      type = "stdio";
      allowed_origins = [ "chrome-extension://gkagbidkbfggbfholmeainnbjjbcapfo/" ];
    };

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

    # A compact navigation label, independent of ordinary notification styling.
    services.mako.settings."app-name=\"Project Workspace\"" = {
      anchor = "top-center";
      layer = "overlay";
      format = "%s";
      markup = false;
      icons = false;
      history = false;
      "text-alignment" = "center";
      font = "sans-serif 16";
      width = 640;
      height = 80;
      padding = "14,24";
      margin = "48,12";
      "border-radius" = 12;
      "background-color" = "#181825ee";
      "border-color" = "#45475aff";
      "default-timeout" = 1500;
      "ignore-timeout" = true;
    };

    # Visibility is owned by the central notification registry, including the
    # navigation-feedback exception in DND. This module owns presentation only.

    wayland.windowManager.hyprland.settings = lib.mkIf cfg.enableHyprlandBinding (if config.wayland.windowManager.hyprland.configType == "lua" then {
      terminal._var = lib.mkForce "${package}/bin/project-terminal";
      bind = lib.mkAfter (map (entry: {
        _args = [ (builtins.elemAt entry 0)
          (lib.generators.mkLuaInline "hl.dsp.exec_cmd(${lib.generators.toLua { } (builtins.elemAt entry 1)})") ];
      }) [
        [ "SUPER + P" "${package}/bin/project-picker" ]
        [ "SUPER + X" "${package}/bin/project-picker --close-active-workspace" ]
        [ "SUPER + n" "${package}/bin/project-picker --next-attention" ]
        [ "SUPER + SHIFT + n" "${package}/bin/project-picker --previous-attention" ]
      ]);
      on = lib.mkAfter [{ _args = [ "hyprland.start" (lib.generators.mkLuaInline ''function()
        hl.exec_cmd(${lib.generators.toLua { } "${package}/bin/project-picker --preload"})
      end'') ]; }];
      window_rule = lib.mkAfter (map (effects: {
        match.class = "^(dev.project_object.Picker|project-picker)$";
      } // effects) [ { float = true; } { center = true; } { size = "760 570"; } ]);
    } else {
      "$terminal" = lib.mkForce "${package}/bin/project-terminal";
      bind = lib.mkAfter [
        "$mod, P, exec, ${package}/bin/project-picker"
        "$mod, X, exec, ${package}/bin/project-picker --close-active-workspace"
        "$mod, n, exec, ${package}/bin/project-picker --next-attention"
        "$mod SHIFT, n, exec, ${package}/bin/project-picker --previous-attention"
      ];
      exec-once = lib.mkAfter [ "${package}/bin/project-picker --preload" ];
      windowrule = lib.mkAfter [
        "match:class ^(dev.project_object.Picker|project-picker)$, float on"
        "match:class ^(dev.project_object.Picker|project-picker)$, center on"
        "match:class ^(dev.project_object.Picker|project-picker)$, size 760 570"
      ];
    });
  };
}
