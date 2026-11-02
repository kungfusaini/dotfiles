# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/tablet-session.nix { inherit config; }'
{ config }:

assert config.services.desktopManager.gnome.enable;
assert config.hardware.sensor.iio.enable;
assert config.programs.hyprland.enable;
assert config.programs.hyprland.withUWSM;
assert config.services.displayManager.dms-greeter.enable;
assert !config.services.displayManager.gdm.enable;
assert !config.services.displayManager.sddm.enable;
assert config.services.displayManager.defaultSession == "hyprland-uwsm";
assert builtins.elem "gnome" config.services.displayManager.sessionData.sessionNames;
assert builtins.elem "hyprland-uwsm" config.services.displayManager.sessionData.sessionNames;
assert builtins.length config.xdg.portal.configPackages == 2;
assert config.home-manager.users.sumeet.wayland.windowManager.hyprland.plugins == [ ];
assert builtins.elem "intel_hid.enable_sw_tablet_mode=0" config.boot.kernelParams;
{
  sessions = config.services.displayManager.sessionData.sessionNames;
  defaultSession = config.services.displayManager.defaultSession;
  sensorProxy = config.hardware.sensor.iio.enable;
  portalConfigs = map toString config.xdg.portal.configPackages;
}
