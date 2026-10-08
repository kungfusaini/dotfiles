{ config, pkgs, ... }:

{
  home.username = "sumeet";
  home.homeDirectory = "/home/sumeet";

  # Match the NixOS release used by the host. Do not change casually.
  home.stateVersion = "26.05";

  xdg.enable = true;

  # Start Home Manager in conservative "file manager" mode: keep the current
  # working configs byte-for-byte, then later replace individual files with
  # typed HM modules when that buys us something.
  xdg.configFile = {
    "hypr".source = ./config/hypr;
    "waybar".source = ./config/waybar;
    "kitty".source = ./config/kitty;
    "mako".source = ./config/mako;
    "yazi".source = ./config/yazi;
    "voxtype".source = ./config/voxtype;
    "mewtion".source = ./config/mewtion;
  };

  programs.home-manager.enable = true;
}
