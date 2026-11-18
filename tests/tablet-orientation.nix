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
assert builtins.elem { output = ""; mode = "preferred"; position = "auto"; scale = 1.25; } settings.monitor;
assert builtins.elem { output = "eDP-1"; mode = "preferred"; position = "auto"; scale = 1.25; } settings.monitor;
assert builtins.elem { match.namespace = "^tablet-rotation-fade$"; no_anim = true; } settings.layer_rule;
assert !(builtins.any (hook: builtins.match ".*tablet-orientation.*" (builtins.toJSON hook) != null) settings.on);
assert builtins.elem "intel_hid.enable_sw_tablet_mode=0" config.boot.kernelParams;
{
  namedMonitorRules = settings.monitor;
  loginOrientationAutostart = false;
  sensorService = config.hardware.sensor.iio.enable;
}
