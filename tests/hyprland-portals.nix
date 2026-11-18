# Check the final module-applied portal, not the unpaired package input.
{ pkgs, config }:
let
  lib = pkgs.lib;
  portal = config.programs.hyprland.portalPackage;
  implementations = builtins.filter
    (package: (package.pname or "") == "xdg-desktop-portal-hyprland")
    config.xdg.portal.extraPortals;
  commands = builtins.filter (command: command != "")
    config.systemd.user.services.xdg-desktop-portal-hyprland.serviceConfig.ExecStart;
  wrapper = builtins.head commands;
in
assert builtins.length implementations == 1;
assert toString (builtins.head implementations) == toString portal;
assert builtins.length commands == 1;
pkgs.runCommand "hyprland-portals-contract" { } ''
  ${pkgs.gnugrep}/bin/grep -F -- 'exec ${portal}/libexec/xdg-desktop-portal-hyprland' ${wrapper} >/dev/null
  ${pkgs.gnugrep}/bin/grep -F -- 'export HYPRLAND_INSTANCE_SIGNATURE="$chosen_sig"' ${wrapper} >/dev/null
  ${pkgs.gnugrep}/bin/grep -F -- 'export WAYLAND_DISPLAY="$chosen_wl"' ${wrapper} >/dev/null
  touch "$out"
''
