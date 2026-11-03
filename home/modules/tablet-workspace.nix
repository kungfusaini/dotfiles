{ config, pkgs, lib, osConfig, ... }:

let
  tabletOskPackage = pkgs.writeShellApplication {
    name = "tablet-osk";
    runtimeInputs = with pkgs; [ coreutils procps util-linux libnotify wvkbd wtype python3 osConfig.programs.hyprland.package ];
    text = builtins.readFile ../../hosts/kirax1/scripts/desktop/tablet-osk;
  };
  # Hyprland 0.56's getoption cannot query device-specific values. Preserve
  # declared overrides; only absent keys fall back to the live global option.
  devicePolicy = name: kind:
    let
      entries = builtins.filter (entry: (entry.name or "") == name)
        (config.wayland.windowManager.hyprland.settings.device or [ ]);
      declared = builtins.foldl' (result: entry: result // entry) { } entries;
    in {
      inherit name kind;
      transform = declared.transform or null;
      output = declared.output or null;
    };
  orientationPolicy = pkgs.writeText "tablet-orientation-policy.json" (builtins.toJSON {
    monitor = "eDP-1";
    devices = [
      (devicePolicy "wacom-hid-5430-finger" "touch")
      (devicePolicy "wacom-hid-5430-pen" "pen")
    ];
  });
  tabletOrientation = pkgs.writeShellApplication {
    name = "tablet-orientation";
    runtimeInputs = with pkgs; [ coreutils procps python3 osConfig.hardware.sensor.iio.package osConfig.programs.hyprland.package ];
    text = ''
      export TABLET_ORIENTATION_POLICY=${orientationPolicy}
      exec python3 ${../scripts/desktop/tablet-orientation.py} "$@"
    '';
  };
  tabletWorkspace = pkgs.writeShellApplication {
    name = "tablet-workspace";
    runtimeInputs = with pkgs; [ python3 libnotify vivaldi osConfig.programs.hyprland.package quickshell tabletOskPackage tabletOrientation ];
    text = ''
      export TABLET_PANEL_QML=${../config/quickshell/tablet-workspace/shell.qml}
      exec python3 ${../scripts/desktop/tablet-workspace.py} "$@"
    '';
  };
in
{
  _module.args.tabletOsk = "${tabletOskPackage}/bin/tablet-osk";
  home.packages = [ tabletWorkspace tabletOskPackage tabletOrientation ];
  assertions = [{
    assertion = osConfig.hardware.sensor.iio.enable;
    message = "Tablet orientation requires hardware.sensor.iio.enable.";
  } {
    assertion = builtins.all (name: !(lib.hasInfix name config.wayland.windowManager.hyprland.extraConfig))
      [ "wacom-hid-5430-finger" "wacom-hid-5430-pen" ];
    message = "Declare built-in touch/pen overrides in Hyprland settings.device, not extraConfig, so tablet orientation can restore them.";
  }];

  # A transform-only monitor command is a no-op without a named rule on this
  # Hyprland build. Keep the generic rule for other displays unchanged.
  wayland.windowManager.hyprland.settings.monitor = lib.mkAfter [
    "eDP-1, preferred, auto, 1.25"
  ];

  xdg.desktopEntries.tablet-workspace = {
    name = "Tablet workspace trial";
    comment = "Park your desktop without moving or closing any windows";
    exec = "${tabletWorkspace}/bin/tablet-workspace enter";
    icon = "input-tablet";
    terminal = false;
    categories = [ "Utility" ];
  };

  wayland.windowManager.hyprland.settings.bind = lib.mkAfter [
    "$mod CTRL, T, exec, ${tabletWorkspace}/bin/tablet-workspace toggle"
  ];
}
