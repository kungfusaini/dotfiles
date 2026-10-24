{ ... }:

{
  programs.bash.enable = true;

  programs.yazi = {
    enable = true;
    enableBashIntegration = true;
    # Keep the usual command name while allowing Yazi to change the parent shell's directory.
    shellWrapperName = "yazi";
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
