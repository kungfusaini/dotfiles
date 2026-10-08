{ ... }:

{
  # No Home Manager adapter; the system-level NixOS module packages and grants
  # sensor access, while this manages the user preferences file.
  xdg.configFile."mewtion/config.txt".source = ../config/mewtion/config.txt;
}
