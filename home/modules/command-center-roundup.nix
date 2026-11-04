{ config, lib, pkgs, osConfig, ... }:

let
  roundup = pkgs.callPackage ../packages/command-center-roundup { };
  # Reuse the exact managed Pi package, including the local compatibility patches.
  pi = lib.findFirst (p: (p.pname or "") == "pi-coding-agent")
    (throw "Daily roundups require the managed Pi package")
    osConfig.users.users.sumeet.packages;
  archive = "${config.xdg.dataHome}/command-center/roundups";
  state = "${config.xdg.stateHome}/command-center/roundups";
  agent = "${config.xdg.configHome}/pi/agent";
in
{
  home.packages = [ roundup ];
  xdg.configFile."command-center/roundup.json".text = builtins.toJSON {
    sourceRoot = "${config.xdg.dataHome}/project-object";
    archiveRoot = archive;
    stateRoot = state;
    agentDir = agent;
    piBin = "${pi}/bin/pi";
    notifyBin = "${pkgs.libnotify}/bin/notify-send";
    busBin = "${pkgs.systemd}/bin/busctl";
    timezone = "Europe/London";
    firstDate = "2026-11-03";
    model = "gpt-6.1-sol";
  };

  systemd.user.services.command-center-roundup = {
    Unit.Description = "Write and source-check private daily Codex roundups";
    Service = {
      Type = "oneshot";
      ExecStart = "${roundup}/bin/command-center-roundup run";
      Environment = [
        "XDG_CONFIG_HOME=${config.xdg.configHome}"
        "XDG_DATA_HOME=${config.xdg.dataHome}"
        "XDG_STATE_HOME=${config.xdg.stateHome}"
        "PI_CODING_AGENT_DIR=${agent}"
        "PI_TELEMETRY=0"
        "PI_SKIP_VERSION_CHECK=1"
      ];
      UMask = "0077";
      Nice = 15;
      IOSchedulingClass = "idle";
      MemoryMax = "768M";
      TasksMax = 64;
      TimeoutStartSec = "45min";
      KillMode = "control-group";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      # Pi's normal OAuth refresh uses atomic replacements in its existing auth
      # directory. No credentials are copied or embedded in Nix/store/config.
      ReadWritePaths = [ archive state agent ];
      ReadOnlyPaths = [ "${config.xdg.dataHome}/project-object" ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    };
  };

  systemd.user.timers.command-center-roundup = {
    Unit.Description = "Daily roundup at 00:15 London time, with startup catch-up and pending retries";
    Timer = {
      OnCalendar = "*-*-* 00:15:00 Europe/London";
      OnStartupSec = "2min";
      # Cheap date/state checks only when up to date; no model calls in that case.
      OnUnitInactiveSec = "1h";
      Persistent = true;
      WakeSystem = false;
      AccuracySec = "1min";
    };
    Install.WantedBy = [ "timers.target" ];
  };
  systemd.user.tmpfiles.rules = [
    "d ${archive} 0700 - - -"
    "d ${state} 0700 - - -"
  ];
}
