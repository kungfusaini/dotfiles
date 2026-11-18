# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/clamshell-mode.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  policy = config.services.logind.settings.Login;
  binds = builtins.filter (bind: if builtins.length bind._args > 2 then (builtins.elemAt bind._args 2).locked or false else false)
    home.wayland.windowManager.hyprland.settings.bind;
  packages = map (package: package.name) home.home.packages;
  matching = key: command: builtins.filter (bind:
    builtins.elemAt bind._args 0 == key && builtins.match command (builtins.elemAt bind._args 1).expr != null
  ) binds;
in
assert policy.HandleLidSwitch == "suspend";
assert policy.HandleLidSwitchExternalPower == "suspend";
assert policy.HandleLidSwitchDocked == "ignore";
assert builtins.elem "clamshell-mode" packages;
assert builtins.elem "headless-mode" packages;
assert builtins.length (matching "switch:on:Lid Switch" ".*/bin/clamshell-mode close.*") == 1;
assert builtins.length (matching "switch:off:Lid Switch" ".*/bin/clamshell-mode open.*") == 1;
{
  inherit policy;
  lidBindings = builtins.filter (bind: builtins.match "switch:.*Lid Switch" (builtins.elemAt bind._args 0) != null) binds;
}
