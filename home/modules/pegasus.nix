{ config, pkgs, ... }:

{
  home.packages = with pkgs; [
    pcsx2
    pegasus-frontend
  ];

  # Pegasus reads these as its native configuration. Keep the UI behavior and
  # manually registered games in the repository instead of changing them only
  # through the application settings menu.
  xdg.configFile = {
    "pegasus-frontend/settings.txt".source = ../config/pegasus/settings.txt;
    "pegasus-frontend/game_dirs.txt".source = ../config/pegasus/game_dirs.txt;
    "pegasus-frontend/metafiles/custom.metadata.pegasus.txt".source =
      ../config/pegasus/custom.metadata.pegasus.txt;
    "pegasus-frontend/metafiles/ps2.metadata.pegasus.txt".source =
      ../config/pegasus/ps2.metadata.pegasus.txt;
  };

  # PCSX2 owns its writable settings, while firmware and save data live in the
  # durable emulation data tree rather than under ~/.config.
  home.file = {
    ".config/PCSX2/bios".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/bios/ps2";
    ".config/PCSX2/memcards".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/saves/ps2/memory-cards";
    ".config/PCSX2/sstates".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/saves/ps2/states";
  };

  # Reserve the durable data roots without putting ROMs, saves, BIOS files, or
  # downloaded artwork in the Nix repository.
  home.activation.createPegasusDataRoot = ''
    mkdir -p \
      "$HOME/matrix/data/emulation/bios/ps2" \
      "$HOME/matrix/data/emulation/media/ps2" \
      "$HOME/matrix/data/emulation/roms/ps2" \
      "$HOME/matrix/data/emulation/saves/ps2/memory-cards" \
      "$HOME/matrix/data/emulation/saves/ps2/states"
  '';

  wayland.windowManager.hyprland.settings = {
    windowrule = [
      "match:class ^(pegasus-fe|org\\.pegasus-frontend\\.)$, fullscreen on"
    ];
  };
}
