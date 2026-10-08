{ ... }:

{
  # Home Manager's Hyprland module generates hyprlang config. This setup uses
  # Hyprland's Lua config, so the faithful declarative representation is still
  # file-based under HM.
  xdg.configFile."hypr".source = ../config/hypr;
}
