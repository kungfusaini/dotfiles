{ ... }:

{
  imports = [
    ./hardware-configuration.nix

    ./hardware/goodhaptic.nix

    ./modules/core/boot.nix
    ./modules/core/deployment.nix
    ./modules/core/locale.nix
    ./modules/core/networking.nix
    ./modules/core/nix.nix
    ./modules/core/development-tools.nix

    ./modules/desktop/apps.nix
    ./modules/desktop/audio.nix
    ./modules/desktop/gaming.nix
    ./modules/desktop/hyprland.nix
    ./modules/desktop/tablet-session-trial.nix
    ./modules/desktop/spicetify.nix
    ./modules/desktop/vivaldi.nix

    ./modules/programs/mewtion.nix
    ./modules/services/backup.nix
    ./modules/services/credential-store.nix
    ./modules/services/pi-secrets.nix

    ./modules/hardware/headless-mode.nix
    ./modules/hardware/input.nix
    ./modules/hardware/peripherals.nix
    ./modules/hardware/sensors.nix
    ./modules/hardware/power

    ./modules/users/sumeet.nix
    ./modules/users/xdg-compliance.nix
  ];

  programs.mewtion = {
    enable = true;
    users = [ "sumeet" ];
  };

  # Do not change this after install without reading the NixOS release notes.
  system.stateVersion = "26.05";
}
