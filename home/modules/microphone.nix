{ pkgs, ... }:

let
  # One press toggles mute after a 400 ms double-press window. A second press
  # within that window cancels the mute toggle and switches microphone source.
  micMuteButton = pkgs.writeShellApplication {
    name = "mic-mute-button";
    runtimeInputs = with pkgs; [
      coreutils
      gawk
      procps
      util-linux
      wireplumber
    ];
    text = builtins.readFile ../scripts/microphone/mic-mute-button;
  };

  micStatusWaybar = pkgs.writeShellApplication {
    name = "mic-status-waybar";
    runtimeInputs = with pkgs; [
      coreutils
      gawk
      wireplumber
    ];
    text = builtins.readFile ../scripts/microphone/mic-status-waybar;
  };

  # The Sony/Intel pair currently needs one successful mSBC eSCO cycle on each
  # new ACL before LC3-SWB can establish. Prime that per-connection state, put
  # LC3-SWB back as WirePlumber's preferred call profile, then restore LDAC.
  sonyHeadsetPrime = pkgs.writeShellApplication {
    name = "sony-headset-prime";
    runtimeInputs = with pkgs; [
      bluez
      coreutils
      gawk
      gnugrep
      pipewire
      systemd
      wireplumber
    ];
    text = builtins.readFile ../scripts/microphone/sony-headset-prime;
  };

  # Keep the laptop microphone available even when HDMI/DP monitor audio or
  # Bluetooth headset profile changes make WirePlumber re-evaluate profiles.
  # If the internal card gets left on "off", the built-in mic node disappears;
  # revive the HiFi profile proactively without stealing the default mic while a
  # Bluetooth mic is intentionally selected.
  micDisconnectGuard = pkgs.writeShellScript "mic-source-disconnect-guard" ''
    set -u

    internal_card_id() {
      local line
      line=$(${pkgs.wireplumber}/bin/wpctl status --name 2>/dev/null |
        ${pkgs.gnugrep}/bin/grep -m1 'alsa_card\.pci-0000_00_1f\.3-platform-sof_sdw') || return 1

      if [[ "$line" =~ ([0-9]+)\. ]]; then
        printf '%s\n' "''${BASH_REMATCH[1]}"
      else
        return 1
      fi
    }

    laptop_source_id() {
      local line
      line=$(${pkgs.wireplumber}/bin/wpctl status --name 2>/dev/null |
        ${pkgs.gnugrep}/bin/grep -m1 'alsa_input\.pci-.*HiFi__Mic__source') || return 1

      if [[ "$line" =~ ([0-9]+)\. ]]; then
        printf '%s\n' "''${BASH_REMATCH[1]}"
      else
        return 1
      fi
    }

    bluetooth_mic_present() {
      ${pkgs.wireplumber}/bin/wpctl status --name 2>/dev/null |
        ${pkgs.gnugrep}/bin/grep -q 'bluez_input\.'
    }

    signal_waybar() {
      # Match both native Waybar and Nixpkgs' wrapped executable.
      ${pkgs.procps}/bin/pkill -RTMIN+10 -x waybar 2>/dev/null || true
      ${pkgs.procps}/bin/pkill -RTMIN+10 -x .waybar-wrapped 2>/dev/null || true
    }

    ensure_laptop_mic_available() {
      local card_id attempt
      laptop_source_id >/dev/null && return 0

      card_id=$(internal_card_id) || return 0

      # Profile 2 is the SoundWire HiFi profile that contains [In] Mic plus
      # the laptop/HDMI outputs. Re-selecting it is harmless when already set.
      ${pkgs.wireplumber}/bin/wpctl set-profile "$card_id" 2 2>/dev/null || return 0

      for attempt in {1..10}; do
        laptop_source_id >/dev/null && {
          signal_waybar
          return 0
        }
        sleep 0.1
      done
    }

    select_laptop_mic_if_no_bluetooth() {
      local id
      bluetooth_mic_present && return 0
      ensure_laptop_mic_available
      id=$(laptop_source_id) || return 0
      ${pkgs.wireplumber}/bin/wpctl set-default "$id" || return 0
      signal_waybar
    }

    while true; do
      ensure_laptop_mic_available
      select_laptop_mic_if_no_bluetooth
      sleep 2
    done
  '';
in
{
  _module.args = {
    inherit micMuteButton micStatusWaybar;
  };

  systemd.user.services = {
    mic-source-disconnect-guard = {
      Unit = {
        Description = "Keep laptop microphone available across monitor and Bluetooth changes";
        After = [ "pipewire.service" "wireplumber.service" ];
        Wants = [ "pipewire.service" "wireplumber.service" ];
      };
      Service = {
        ExecStart = micDisconnectGuard;
        Restart = "always";
        RestartSec = 1;
      };
      Install.WantedBy = [ "default.target" ];
    };

    sony-headset-prime = {
      Unit = {
        Description = "Prime Sony WF-1000XM6 for LC3-SWB after each connection";
        After = [ "pipewire.service" "wireplumber.service" ];
        Wants = [ "pipewire.service" "wireplumber.service" ];
      };
      Service = {
        ExecStart = "${sonyHeadsetPrime}/bin/sony-headset-prime";
        Restart = "always";
        RestartSec = 1;
      };
      # Hyprland does not activate graphical-session.target on this host.
      # default.target is always active for the user manager after login.
      Install.WantedBy = [ "default.target" ];
    };
  };
}
