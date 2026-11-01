{ pkgs, ... }:

{
  home.packages = [ pkgs.pegasus-frontend ];

  # Pegasus reads these as its native configuration. Keep the UI behavior and
  # manually registered games in the repository instead of changing them only
  # through the application settings menu.
  xdg.configFile = {
    "pegasus-frontend/settings.txt".source = ../config/pegasus/settings.txt;
    "pegasus-frontend/game_dirs.txt".source = ../config/pegasus/game_dirs.txt;
    "pegasus-frontend/metafiles/custom.metadata.pegasus.txt".source =
      ../config/pegasus/custom.metadata.pegasus.txt;
  };

  # Reserve the durable data root without putting ROMs, saves, or BIOS files in
  # the Nix repository.
  home.activation.createPegasusDataRoot = ''
    mkdir -p "$HOME/matrix/data/emulation"
  '';

  wayland.windowManager.hyprland.settings = {
    bind = [ "$mod, P, exec, pegasus-fe" ];
    windowrule = [
      "match:class ^(pegasus-fe|org\\.pegasus-frontend\\.)$, fullscreen on"
    ];
  };
}
