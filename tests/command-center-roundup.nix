# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/command-center-roundup.nix { inherit config; }'
{ config }:
let
  home = config.home-manager.users.sumeet;
  timer = home.systemd.user.timers.command-center-roundup.Timer;
  service = home.systemd.user.services.command-center-roundup.Service;
  # Parse for assertions only; production retains the original store dependencies.
  settings = builtins.fromJSON (builtins.unsafeDiscardStringContext home.xdg.configFile."command-center/roundup.json".text);
  pi = builtins.head (builtins.filter (p: (p.pname or "") == "pi-coding-agent") config.users.users.sumeet.packages);
in
assert timer.OnCalendar == "*-*-* 00:15:00 Europe/London";
assert timer.Persistent && !timer.WakeSystem;
assert timer.OnStartupSec == "2min" && timer.OnUnitInactiveSec == "1h";
assert settings.model == "gpt-6.1-sol";
assert settings.timezone == "Europe/London" && settings.firstDate == "2026-11-03";
assert settings.piBin == "${pi}/bin/pi";
assert service.UMask == "0077" && service.PrivateTmp && service.NoNewPrivileges;
assert service.ProtectSystem == "strict" && service.ProtectHome == "read-only";
assert builtins.elem settings.sourceRoot service.ReadOnlyPaths;
assert service.ReadWritePaths == [ settings.archiveRoot settings.stateRoot settings.agentDir ];
assert builtins.substring 0 11 (builtins.head service.ExecStart) == "/nix/store/";
{
  schedule = timer.OnCalendar;
  persistent = timer.Persistent;
  wakeLaptop = timer.WakeSystem;
  model = settings.model;
  sourceReadOnly = true;
  runtimeFromNixStore = true;
}
