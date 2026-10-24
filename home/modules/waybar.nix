{ micStatusWaybar, pkgs, platformProfileWaybar, ... }:

let
  baseWaybarConfig = builtins.fromJSON (builtins.readFile ../config/waybar/config);
  waybarConfig = baseWaybarConfig // {
    "custom/mic-status" = baseWaybarConfig."custom/mic-status" // {
      exec = "${micStatusWaybar}/bin/mic-status-waybar";
    };
    "custom/platform-profile" = baseWaybarConfig."custom/platform-profile" // {
      exec = "${platformProfileWaybar}/bin/platform-profile-waybar";
    };
  };

  # Mirror the platform-profile design: subscribe to state-change events in a
  # background service, then signal a short-lived Waybar status command.
  # Ignore pw-dump's initial graph and react only to subsequent mute changes;
  # this avoids treating status-query clients as state changes.
  micWaybarMonitor = pkgs.writeShellScript "mic-waybar-monitor" ''
    initial_dump=true
    ${pkgs.coreutils}/bin/stdbuf -oL ${pkgs.pipewire}/bin/pw-dump -m -N 2>/dev/null |
      while IFS= read -r line; do
        if $initial_dump; then
          if [[ "$line" == "]" ]]; then
            initial_dump=false
          fi
          continue
        fi

        case "$line" in
          *'"mute":'*|*'"softMute":'*)
            # RTMIN+10 reruns only Waybar's custom/mic-status module.
            ${pkgs.procps}/bin/pkill -RTMIN+10 -x waybar 2>/dev/null || true
            ${pkgs.procps}/bin/pkill -RTMIN+10 -x .waybar-wrapped 2>/dev/null || true
            ;;
        esac
      done
  '';
in
{
  programs.waybar = {
    enable = true;
    settings.mainBar = waybarConfig;
    style = ../config/waybar/style.css;
  };

  systemd.user.services.mic-waybar-monitor = {
    Unit = {
      Description = "Signal Waybar when PipeWire microphone state changes";
      PartOf = [ "graphical-session.target" ];
      After = [ "pipewire.service" ];
    };
    Service = {
      ExecStart = micWaybarMonitor;
      Restart = "always";
      RestartSec = 1;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
