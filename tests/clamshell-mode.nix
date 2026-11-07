# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/clamshell-mode.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  policy = config.services.logind.settings.Login;
  binds = home.wayland.windowManager.hyprland.settings.bindl;
  packages = map (package: package.name) home.home.packages;
  matching = pattern: builtins.filter (bind: builtins.match pattern bind != null) binds;
in
assert policy.HandleLidSwitch == "suspend";
assert policy.HandleLidSwitchExternalPower == "suspend";
assert policy.HandleLidSwitchDocked == "ignore";
assert builtins.elem "clamshell-mode" packages;
assert builtins.elem "headless-mode" packages;
assert builtins.length (matching ".*switch:on:Lid Switch, exec, .*/bin/clamshell-mode close") == 1;
assert builtins.length (matching ".*switch:off:Lid Switch, exec, .*/bin/clamshell-mode open") == 1;
{
  inherit policy;
  lidBindings = matching ".*switch:.*Lid Switch.*";
}
