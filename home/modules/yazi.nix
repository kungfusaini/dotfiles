{ ... }:

{
  programs.yazi = {
    enable = true;
    keymap = {
      mgr.prepend_keymap = [
        {
          on = "M";
          run = "plugin mount";
          desc = "Open mount manager";
        }
      ];
    };
    plugins.mount = ../config/yazi/plugins/mount.yazi;
  };
}
