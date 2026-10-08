{ ... }:

{
  programs.waybar = {
    enable = true;
    settings.mainBar = builtins.fromJSON (builtins.readFile ../config/waybar/config);
    style = ../config/waybar/style.css;
  };
}
