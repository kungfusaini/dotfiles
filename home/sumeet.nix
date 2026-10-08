{ ... }:

{
  imports = [
    ./modules/hypr.nix
    ./modules/kitty.nix
    ./modules/mako.nix
    ./modules/mewtion.nix
    ./modules/voxtype.nix
    ./modules/waybar.nix
    ./modules/yazi.nix
  ];

  home.username = "sumeet";
  home.homeDirectory = "/home/sumeet";

  # Match the NixOS release used by the host. Do not change casually.
  home.stateVersion = "26.05";

  xdg.enable = true;

  programs.home-manager.enable = true;
}
