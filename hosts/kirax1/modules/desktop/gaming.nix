{ pkgs, ... }:

{
  # Steam and Proton still depend on 32-bit graphics libraries for many games.
  hardware.graphics.enable32Bit = true;

  # Combine only Ashlyn's Joy-Cons; stock joycond also intercepts Pro Controllers
  # and would change the identity used by their custom Steam Input mappings.
  services.joycond = {
    enable = true;
    package = pkgs.callPackage ../../packages/ashlyn-joycond { };
  };

  programs = {
    gamemode.enable = true;

    steam = {
      enable = true;
      extraCompatPackages = [ pkgs.proton-ge-bin ];
    };
  };
}
