{ pkgs, ... }:

{
  # Steam and Proton still depend on 32-bit graphics libraries for many games.
  hardware.graphics.enable32Bit = true;

  programs = {
    gamemode.enable = true;

    steam = {
      enable = true;
      extraCompatPackages = [ pkgs.proton-ge-bin ];
    };
  };
}
