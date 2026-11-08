{ config, lib, pkgs, osConfig, ... }:

let
  tracker = pkgs.callPackage ../packages/codex-usage-tracker { };
  policy = builtins.fromJSON (builtins.readFile ../config/pi/model-modes.json);
  mode = lib.findFirst (m: m.id == policy.default && m.provider == "openai-codex")
    (throw "One-shot sessions require a Codex default model mode") policy.modes;
  pi = lib.findFirst (p: (p.pname or "") == "pi-coding-agent")
    (throw "One-shot sessions require the managed Pi package")
    osConfig.users.users.sumeet.packages;
in
{
  home.packages = [ tracker ];
  xdg.configFile."command-center/oneshot.json".text = builtins.toJSON {
    piBin = "${pi}/bin/pi";
    model = mode.model;
    thinking = mode.thinkingLevel;
  };

  systemd.user.services.codex-usage = {
    Unit.Description = "Record Codex quota and incrementally import Pi usage metadata";
    Service = {
      Type = "oneshot";
      ExecStart = "${tracker}/bin/codex-usage collect";
      Environment = [
        "XDG_CONFIG_HOME=${config.xdg.configHome}"
        "XDG_DATA_HOME=${config.xdg.dataHome}"
        "XDG_STATE_HOME=${config.xdg.stateHome}"
        "PI_CODING_AGENT_DIR=${config.xdg.configHome}/pi/agent"
      ];
      UMask = "0077";
      Nice = 19;
      IOSchedulingClass = "idle";
      CPUQuota = "10%";
      MemoryMax = "128M";
      TasksMax = 8;
      TimeoutStartSec = 120;
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      ReadWritePaths = [ "${config.xdg.dataHome}/codex-usage-tracker" ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    };
  };

  # Fresh collections also deliver deduplicated 24h/4h reset reminders.
  # No persistent process, high-frequency wakeups, or waking the laptop from sleep.
  systemd.user.timers.codex-usage = {
    Unit.Description = "Measure Codex subscription usage hourly";
    Timer = {
      OnCalendar = "hourly";
      Persistent = true;
      RandomizedDelaySec = 60;
      AccuracySec = 60;
      WakeSystem = false;
    };
    Install.WantedBy = [ "timers.target" ];
  };

  # The sandbox permits writes only to this private, pre-created state directory.
  systemd.user.tmpfiles.rules = [
    "d ${config.xdg.dataHome}/codex-usage-tracker 0700 - - -"
  ];
}
