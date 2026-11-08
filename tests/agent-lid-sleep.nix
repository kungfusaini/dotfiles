# Evaluate against the pinned committed flake's config before deployment.
{ config }:
let
  home = config.home-manager.users.sumeet;
  service = home.systemd.user.services.agent-lid-sleep;
  policy = config.services.logind.settings.Login;
in
assert policy.HandleLidSwitch == "suspend";
assert policy.HandleLidSwitchExternalPower == "suspend";
assert policy.HandleLidSwitchDocked == "ignore";
assert config.services.upower.criticalPowerAction == "Hibernate";
assert service.Service.Restart == "on-failure";
assert service.Install.WantedBy == [ "graphical-session.target" ];
assert service.Unit.PartOf == [ "graphical-session.target" ];
{
  inherit policy;
  executable = service.Service.ExecStart;
  criticalPowerAction = config.services.upower.criticalPowerAction;
}
