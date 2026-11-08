{ config, lib, pkgs, osConfig, ... }:
let
  worker = pkgs.callPackage ../packages/agent-techniques-weekly { inherit pi; };
  pi = lib.findFirst (p: (p.pname or "") == "pi-coding-agent")
    (throw "Weekly techniques require the managed Pi package") osConfig.users.users.sumeet.packages;
  library = "${config.home.homeDirectory}/matrix/projects/agent-techniques";
  state = "${config.xdg.stateHome}/agent-techniques-weekly";
  agent = "${config.xdg.configHome}/pi/agent";
  sessions = "${agent}/sessions/--agent-techniques-weekly";
in {
  home.packages = [ worker ];
  xdg.configFile."agent-techniques/weekly.json".text = builtins.toJSON {
    libraryRoot = library;
    stateRoot = state;
    agentDir = agent;
    sessionRoot = sessions;
    sdkPath = "${pi}/lib/node_modules/pi-monorepo/dist/index.js";
    nodeBin = "${pkgs.nodejs}/bin/node";
    model = "gpt-6-luna";
    notifyBin = "${pkgs.libnotify}/bin/notify-send";
    busBin = "${pkgs.systemd}/bin/busctl";
  };
  systemd.user.services.agent-techniques-weekly = {
    Unit.Description = "Discover worthwhile Reddit agent techniques once weekly";
    Service = {
      Type = "oneshot";
      ExecStart = "${worker}/bin/agent-techniques-weekly run";
      ExecStopPost = "-${worker}/bin/agent-techniques-weekly notify";
      Environment = [
        "XDG_CONFIG_HOME=${config.xdg.configHome}"
        "XDG_STATE_HOME=${config.xdg.stateHome}"
        "XDG_DATA_HOME=${config.xdg.dataHome}"
        "PI_CODING_AGENT_DIR=${agent}"
        "PI_OFFLINE=1"
        "PI_TELEMETRY=0"
      ];
      UMask = "0077";
      Nice = 15;
      IOSchedulingClass = "idle";
      MemoryMax = "768M";
      TasksMax = 64;
      TimeoutStartSec = "8min";
      KillMode = "control-group";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      # Only generated weekly candidates, own state, and normal Pi OAuth/session state are writable.
      ReadWritePaths = [ "${library}/weekly" state agent ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    };
  };
  systemd.user.timers.agent-techniques-weekly = {
    Unit.Description = "Weekly agent ideas, Sunday 09:00 London with missed-run catch-up";
    Timer = {
      OnCalendar = "Sun *-*-* 09:00:00 Europe/London";
      Persistent = true;
      WakeSystem = false;
      AccuracySec = "1min";
    };
    Install.WantedBy = [ "timers.target" ];
  };
  systemd.user.tmpfiles.rules = [
    "d ${state} 0700 - - -"
    "d ${library}/weekly 0700 - - -"
    "d ${sessions} 0700 - - -"
  ];
}
