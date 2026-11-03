# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/tablet-orientation.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  settings = home.wayland.windowManager.hyprland.settings;
  packageNames = map (package: package.name) home.home.packages;
in
assert config.hardware.sensor.iio.enable;
assert !config.programs.iio-hyprland.enable;
assert builtins.elem "tablet-orientation" packageNames;
assert builtins.elem ", preferred, auto, 1.25" settings.monitor;
assert builtins.elem "eDP-1, preferred, auto, 1.25" settings.monitor;
assert !(builtins.any (command: builtins.match ".*tablet-orientation.*" command != null) settings.exec-once);
assert builtins.elem "intel_hid.enable_sw_tablet_mode=0" config.boot.kernelParams;
{
  namedMonitorRules = settings.monitor;
  loginOrientationAutostart = false;
  sensorService = config.hardware.sensor.iio.enable;
}
