{ pkgs, lib, osConfig, ... }:

let
  tabletOskPackage = pkgs.writeShellApplication {
    name = "tablet-osk";
    runtimeInputs = with pkgs; [ coreutils procps util-linux libnotify wvkbd wtype python3 osConfig.programs.hyprland.package ];
    text = builtins.readFile ../../hosts/kirax1/scripts/desktop/tablet-osk;
  };
  tabletWorkspace = pkgs.writeShellApplication {
    name = "tablet-workspace";
    runtimeInputs = with pkgs; [ python3 libnotify vivaldi osConfig.programs.hyprland.package quickshell tabletOskPackage ];
    text = ''
      export TABLET_PANEL_QML=${../config/quickshell/tablet-workspace/shell.qml}
      exec python3 ${../scripts/desktop/tablet-workspace.py} "$@"
    '';
  };
in
{
  _module.args.tabletOsk = "${tabletOskPackage}/bin/tablet-osk";
  home.packages = [ tabletWorkspace tabletOskPackage ];

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
