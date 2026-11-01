{ pkgs, ... }:

let
  platformProfileWaybar = pkgs.writeShellApplication {
    name = "platform-profile-waybar";
    runtimeInputs = [ pkgs.coreutils ];
    text = builtins.readFile ../scripts/power/platform-profile-waybar;
  };

  batteryWarningMonitor = pkgs.writeShellApplication {
    name = "battery-warning-monitor";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.libnotify
    ];
    text = ''
      state_file="$XDG_RUNTIME_DIR/kirax1-battery-warning-level"
      previous=0
      if [[ -r "$state_file" ]]; then
        read -r previous < "$state_file" || previous=0
      fi
      [[ "$previous" =~ ^[0-2]$ ]] || previous=0

      while true; do
        current=0
        capacity=0
        bat_dir=""

        for candidate in /sys/class/power_supply/BAT*; do
          if [[ -d "$candidate" ]]; then
            bat_dir="$candidate"
            break
          fi
        done

        if [[ -n "$bat_dir" ]] && [[ "$(<"$bat_dir/status")" == "Discharging" ]]; then
          capacity="$(<"$bat_dir/capacity")"
          if [[ "$capacity" =~ ^[0-9]+$ ]]; then
            if (( capacity <= 5 )); then
              current=2
            elif (( capacity <= 10 )); then
              current=1
            fi
          fi
        fi

        notification_delivered=true
        if (( current > previous )); then
          notification_delivered=false
          if (( current == 2 )); then
            if notify-send --app-name="Power" --urgency=critical \
              "Battery critical: $capacity%" \
              "Connect power now. Automatic hibernation begins at 2%."; then
              notification_delivered=true
            fi
          elif notify-send --app-name="Power" --urgency=normal \
            "Battery low: $capacity%" \
            "Connect power. Automatic hibernation begins at 2%."; then
            notification_delivered=true
          fi
        fi

        if (( current != previous )) && { (( current < previous )) || $notification_delivered; }; then
          printf '%s\n' "$current" > "$state_file"
          previous="$current"
        fi

        sleep 15
      done
    '';
  };
in
{
  _module.args = {
    inherit platformProfileWaybar;
  };

  systemd.user.services.battery-warning-monitor = {
    Unit = {
      Description = "Warn before critical-battery hibernation";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${batteryWarningMonitor}/bin/battery-warning-monitor";
      Restart = "always";
      RestartSec = 5;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
