{ ... }:

{
  imports = [
    ./hardware-configuration.nix

    ./hardware/goodhaptic.nix

    ./modules/core/boot.nix
    ./modules/core/locale.nix
    ./modules/core/networking.nix
    ./modules/core/nix.nix
    ./modules/core/development-tools.nix

    ./modules/desktop/apps.nix
    ./modules/desktop/audio.nix
    ./modules/desktop/hyprland.nix

    ./modules/programs/mewtion.nix

    ./modules/hardware/peripherals.nix
    ./modules/hardware/power-profile-sync.nix

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
