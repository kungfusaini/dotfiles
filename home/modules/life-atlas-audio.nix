{ config, lib, pkgs, osConfig, ... }:

let
  pi = lib.findFirst (p: (p.pname or "") == "pi-coding-agent")
    (throw "Audio transcript editing requires the managed Pi package")
    osConfig.users.users.sumeet.packages;
  worker = pkgs.callPackage ../packages/life-atlas-audio-editor { inherit pi; };
  state = "${config.xdg.stateHome}/life-atlas-audio";
  agent = "${config.xdg.configHome}/pi/agent";
in
{
  home.packages = [ worker pkgs.openssh ];
  systemd.user.tmpfiles.rules = [ "d ${state} 0700 - - -" ];
  systemd.user.services.life-atlas-audio-review = {
    Unit = {
      Description = "Private selected-log transcript review queue (text only)";
      After = [ "network-online.target" ];
    };
    Service = {
      Type = "oneshot";
      ExecStart = "${worker}/bin/life-atlas-audio-bridge";
      Environment = [
        "PATH=${pkgs.openssh}/bin:${pkgs.coreutils}/bin"
        "LIFE_ATLAS_AUDIO_STATE=${state}"
        "PI_CODING_AGENT_DIR=${agent}"
        "PI_TELEMETRY=0"
        "PI_SKIP_VERSION_CHECK=1"
      ];
      UMask = "0077";
      Nice = 15;
      IOSchedulingClass = "idle";
      MemoryMax = "1G";
      TasksMax = 128;
      TimeoutStartSec = "8h";
      KillMode = "control-group";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      # Existing SSH agent/key access is read-only. Pi may atomically refresh its
      # existing local login; no credentials move to Aether.
      ReadWritePaths = [ state agent ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    };
  };
  systemd.user.timers.life-atlas-audio-review = {
    Unit.Description = "Check selected transcript queue; no phone upload or model call when empty";
    Timer = {
      OnStartupSec = "2min";
      OnUnitInactiveSec = "2min";
      AccuracySec = "15s";
      WakeSystem = false;
    };
    Install.WantedBy = [ "timers.target" ];
  };
}
