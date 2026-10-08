{ ... }:

{
  programs.kitty = {
    enable = true;
    settings = {
      # Touch/touchscreen scrolling.
      pixel_scroll = true;
      touch_scroll_multiplier = 1.0;
      momentum_scroll = 0.96;
      scrollback_lines = 10000;
    };
  };

  # Keep generated Dank Material files as raw files until/unless we decide to
  # model that theme generator declaratively too.
  xdg.configFile."kitty/dank-tabs.conf".source = ../config/kitty/dank-tabs.conf;
  xdg.configFile."kitty/dank-theme.conf".source = ../config/kitty/dank-theme.conf;
}
