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
    extraConfig = ''
      # Plain clicks use Kitty's built-in link handling. Shift-click marks the
      # next URL for the persistent project browser before invoking that same
      # handler; ordinary clicks default to a browser beside the terminal.
      mouse_map shift+left click grabbed,ungrabbed combine : launch --type=background project-browser mark-project-click : sleep 0.15 : mouse_handle_click link

      # Also retain conventional Ctrl+click link opening.
      mouse_map ctrl+left release grabbed,ungrabbed mouse_handle_click link
      mouse_map ctrl+left press grabbed discard_event
    '';
  };

  xdg.configFile."kitty/open-actions.conf".text = ''
    protocol http,https
    action launch --type=background project-browser open --mode adjacent -- ''${URL}

    protocol file
    action launch --type=background project-file-open ''${URL}
  '';

  # Keep generated Dank Material files as raw files until/unless we decide to
  # model that theme generator declaratively too.
  xdg.configFile."kitty/dank-tabs.conf".source = ../config/kitty/dank-tabs.conf;
  xdg.configFile."kitty/dank-theme.conf".source = ../config/kitty/dank-theme.conf;
}
