# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/network-displays-config.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  packages = map (p: p.pname or p.name) home.home.packages;
in
assert builtins.elem "gnome-network-displays" packages;
assert builtins.elem "headless-mode" packages;
assert builtins.elem "clamshell-mode" packages;
assert config.networking.networkmanager.enable;
assert config.networking.networkmanager.wifi.backend == "wpa_supplicant";
assert config.services.pipewire.enable;
assert config.xdg.portal.enable;
{
  packageVersion = (builtins.head (builtins.filter (p: (p.pname or p.name) == "gnome-network-displays") home.home.packages)).version;
  discoveryEnabled = config.services.avahi.enable;
}
