# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/tablet-workspace.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  sessions = config.services.displayManager.sessionData.sessionNames;
in
assert !config.services.desktopManager.gnome.enable;
assert !config.services.displayManager.gdm.enable;
assert !config.services.displayManager.sddm.enable;
assert config.services.displayManager.dms-greeter.enable;
assert !builtins.elem "gnome" sessions;
assert builtins.elem "hyprland-uwsm" sessions;
assert builtins.length config.xdg.portal.configPackages == 1;
assert home.wayland.windowManager.hyprland.plugins == [ ];
assert builtins.hasAttr "tablet-workspace" home.xdg.desktopEntries;
assert builtins.elem "intel_hid.enable_sw_tablet_mode=0" config.boot.kernelParams;
{
  inherit sessions;
  launcher = home.xdg.desktopEntries.tablet-workspace.exec;
  packages = map (package: package.name) home.home.packages;
}
