{ pkgs, ... }:
let
  package = pkgs.callPackage ../packages/agent-lid-sleep { };
in
{
  home.packages = [ package ];
  systemd.user.services.agent-lid-sleep = {
    Unit = {
      Description = "Wait for tracked agents before lid-triggered sleep";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${package}/bin/agent-lid-sleep";
      Restart = "on-failure";
      RestartSec = 1;
      UMask = "0077";
      NoNewPrivileges = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      PrivateTmp = true;
      RestrictAddressFamilies = [ "AF_UNIX" ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
