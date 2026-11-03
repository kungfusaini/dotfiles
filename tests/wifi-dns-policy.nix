# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/wifi-dns-policy.nix { inherit config; }'
{ config }:
let
  service = config.systemd.services.kirax1-wifi-dns-policy;
  timer = config.systemd.timers.kirax1-wifi-dns-policy;
in
assert config.networking.networkmanager.dns == "systemd-resolved";
assert config.services.resolved.enable;
assert config.services.tailscale.enable;
assert config.programs.captive-browser.enable;
assert service.serviceConfig.Type == "oneshot";
assert !(service.serviceConfig.RemainAfterExit or false);
assert service.serviceConfig.TimeoutStartSec == 20;
assert builtins.elem "NetworkManager.service" service.after;
assert builtins.elem "systemd-resolved.service" service.after;
assert timer.timerConfig.OnUnitInactiveSec == "15s";
assert timer.timerConfig.AccuracySec == "1s";
assert builtins.elem "timers.target" timer.wantedBy;
assert config.networking.networkmanager.dispatcherScripts != [];
{
  exec = service.serviceConfig.ExecStart;
  timeout = service.serviceConfig.TimeoutStartSec;
  timer = timer.timerConfig;
  dispatcherCount = builtins.length config.networking.networkmanager.dispatcherScripts;
}
