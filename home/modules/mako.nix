{ lib, ... }:
let
  # Single registry for approved notification sources. New sources are hidden
  # until registered here. Website notifications must be registered narrowly;
  # never allow Vivaldi or the generic notify-send identity wholesale.
  app = name: { app-name = name; };
  desktop = name: { desktop-entry = name; };
  registry = [
    { category = "people"; matches = [
      (app "Slack") (app "slack") (desktop "slack")
      (app "Microsoft Teams") (app "teams-for-linux") (desktop "teams-for-linux")
      (app "ZapZap") (desktop "com.rtosta.zapzap")
    ]; }
    { category = "task-results"; matches = map app [
      "Pi" "Command Center" "Agent Techniques" "Codex One-shot"
      "Screenshots" "Kirax1 Backup"
    ]; }
    { category = "system-tools"; matches = (map app [
      "Sony headphones" "Bluetooth controls" "Tablet workspace" "Tablet voice"
      "Tablet playback" "Tablet game" "On-screen keyboard" "Project browser"
      "Project terminal" "Project picker" "Project restoration" "Project file open"
      "Longshot" "Steam session" "Notification mode"
    ]) ++ [
      { app-name = "Power"; urgency = "normal"; }
      (desktop "blueman") (desktop "blueman-manager")
      (desktop "nordvpn-gui")
    ]; }
    { category = "media"; matches = [
      (app "Spotify") (desktop "spotify") (app "VLC media player") (desktop "vlc")
      # Steam can also send social alerts; conservatively treat the whole client
      # as People until its individual notification types can be distinguished.
    ]; }
    { category = "people"; matches = [
      (app "Steam") (desktop "steam")
      (app "Nicotine+") (desktop "org.nicotine_plus.Nicotine")
    ]; }
    { category = "device-safety"; matches = [ { app-name = "Power"; urgency = "critical"; } ]; }
    { category = "navigation"; matches = [ (app "Project Workspace") ]; }
    { category = "muted"; matches = [ (app "Thunderbird") (app "thunderbird") (desktop "thunderbird") ]; }
  ];
  modes = {
    all = [ "people" "task-results" "system-tools" "media" "device-safety" "navigation" ];
    no-contact = [ "task-results" "system-tools" "media" "device-safety" "navigation" ];
    do-not-disturb = [ "device-safety" "navigation" ];
  };
in
{
  services.mako = {
    enable = true;
    settings = {
      default-timeout = 5000;
      ignore-timeout = true;
      # Prevent second-pass group visibility rules bypassing the registry.
      group-by = "none";
    };
    # extraConfig is ordered, unlike settings' alphabetically sorted sections.
    extraConfig = import ../lib/notification-policy.nix { inherit lib registry modes; };
  };
}
