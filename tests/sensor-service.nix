# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/sensor-service.nix { inherit config; }'
{ config }:
let
  sensor = config.hardware.sensor.iio.package;
  sessions = config.services.displayManager.sessionData.sessionNames;
in
assert config.hardware.sensor.iio.enable;
assert builtins.elem sensor config.services.dbus.packages;
assert builtins.elem sensor config.services.udev.packages;
assert builtins.elem sensor config.systemd.packages;
assert !config.programs.iio-hyprland.enable;
assert config.programs.hyprland.enable;
assert config.services.displayManager.dms-greeter.enable;
assert !config.services.desktopManager.gnome.enable;
assert !builtins.elem "gnome" sessions;
assert builtins.elem "hyprland-uwsm" sessions;
assert builtins.elem ", preferred, auto, 1.25" config.home-manager.users.sumeet.wayland.windowManager.hyprland.settings.monitor;
assert builtins.elem "eDP-1, preferred, auto, 1.25" config.home-manager.users.sumeet.wayland.windowManager.hyprland.settings.monitor;
assert builtins.elem "intel_hid.enable_sw_tablet_mode=0" config.boot.kernelParams;
{
  sensorPackage = sensor.name;
  orientationController = config.programs.iio-hyprland.enable;
  inherit sessions;
}
