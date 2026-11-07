{ config }:
let
  unit = config.systemd.services.tablet-session-trial;
  user = config.users.users.tablet-trial;
in
assert !config.services.desktopManager.plasma6.enable;
assert !config.services.desktopManager.gnome.enable;
assert config.programs.hyprland.withUWSM;
assert config.services.displayManager.dms-greeter.enable;
assert unit.wantedBy == [];
assert unit.conflicts == [];
assert !unit.restartIfChanged;
assert unit.serviceConfig.Restart == "no";
assert user.home == "/var/lib/tablet-session-trial-home";
assert user.homeMode == "0700";
assert user.hashedPassword == "!";
assert user.extraGroups == [];
{
  home = user.home;
  service = unit.serviceConfig.ExecStart;
  startup = unit.wantedBy;
  desktopUnchanged = config.services.displayManager.defaultSession == null;
}
