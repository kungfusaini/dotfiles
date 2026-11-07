# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/network-displays-config.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  packages = map (p: p.pname or p.name) home.home.packages;
  castingClient = builtins.head (builtins.filter (p: (p.pname or p.name) == "gnome-network-displays") home.home.packages);
  displayBindings = builtins.filter (bind: builtins.match ".*XF86Display.*" bind != null)
    home.wayland.windowManager.hyprland.settings.bind;
  avahi = config.services.avahi;
  firewall = config.networking.firewall;
  permitsMdns = rules:
    builtins.elem 5353 rules.allowedUDPPorts
    || builtins.any (range: range.from <= 5353 && range.to >= 5353) rules.allowedUDPPortRanges;
in
assert builtins.elem "gnome-network-displays" packages;
assert castingClient.receiverFirst or false;
assert builtins.elem "headless-mode" packages;
assert builtins.elem "clamshell-mode" packages;
assert config.networking.networkmanager.enable;
assert config.networking.networkmanager.wifi.backend == "wpa_supplicant";
assert config.services.pipewire.enable;
assert config.xdg.portal.enable;
assert builtins.length displayBindings == 2;
assert builtins.any (bind: builtins.match ", XF86Display, exec, .*/bin/display-key-handler" bind != null) displayBindings;
assert builtins.any (bind: builtins.match "SHIFT, XF86Display, exec, .*/bin/display-layout-open" bind != null) displayBindings;
assert avahi.enable;
assert avahi.allowInterfaces == [ "wlp0s20f3" ];
assert !avahi.openFirewall;
assert !avahi.publish.enable;
assert !avahi.publish.userServices;
assert !avahi.publish.addresses;
assert !avahi.publish.workstation;
assert !avahi.nssmdns4 && !avahi.nssmdns6;
assert !avahi.reflector && !avahi.wideArea && !avahi.allowPointToPoint;
assert !config.services.printing.browsed.enable;
assert !permitsMdns firewall;
assert permitsMdns firewall.interfaces.wlp0s20f3;
assert !(builtins.elem "wlp0s20f3" firewall.trustedInterfaces);
assert builtins.all (name: name == "wlp0s20f3" || !permitsMdns firewall.interfaces.${name})
  (builtins.attrNames firewall.interfaces);
{
  packageVersion = castingClient.version;
  receiverFirst = castingClient.receiverFirst;
  discoveryEnabled = avahi.enable;
  discoveryInterfaces = avahi.allowInterfaces;
  wifiUdpPorts = firewall.interfaces.wlp0s20f3.allowedUDPPorts;
}
