{ ... }:

{
  # No Home Manager adapter; manage the app's XDG config directly.
  xdg.configFile."voxtype/config.toml".source = ../config/voxtype/config.toml;
}
