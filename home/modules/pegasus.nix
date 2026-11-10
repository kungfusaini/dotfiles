{ config, pkgs, ... }:

let
  gameOSTheme = pkgs.fetchFromGitHub {
    owner = "PlayingKarrde";
    repo = "gameOS";
    rev = "7a5a5223ff7371d0747a7c5d3a3b8f2f5e36b4f2";
    sha256 = "1mwrk8dk6rbr72nr32bnn524agjq01x1fyih1yxm7m5h8rxlh6hh";
  };
  # All prominent views use full-bleed promotional art, never screenshots or
  # package-shaped covers. Screenshots remain in the optional details gallery.
  curatedGameOS = pkgs.runCommand "gameos-cover-art" { } ''
    cp -r ${gameOSTheme} "$out"
    chmod -R u+w "$out"
    substituteInPlace "$out/Global/DynamicGridItem.qml" \
      --replace-fail 'modelData.assets.screenshots[0] || modelData.assets.background' \
                     'modelData.assets.background'
    substituteInPlace "$out/GridView/GridViewMenu.qml" \
      --replace-fail 'fakebox.paintedHeight / fakebox.paintedWidth' '9 / 16'
    substituteInPlace "$out/Global/BoxArtGridItem.qml" \
      --replace-fail 'source: boxArt(gameData)' \
                     'source: gameData ? gameData.assets.background : ""' \
      --replace-fail 'fillMode: Image.PreserveAspectFit' \
                     'fillMode: Image.PreserveAspectCrop'
    substituteInPlace "$out/GameDetails/GameView.qml" \
      --replace-fail 'source: Utils.boxArt(game);' \
                     'source: ""' \
      --replace-fail '//width: vpx(350)' \
                     'width: 0'
    substituteInPlace "$out/VerticalList/SoftwareListMenu.qml" \
      --replace-fail 'currentGame.assets.screenshots[0] ? currentGame.assets.screenshots[0]' \
                     'currentGame.assets.background ? currentGame.assets.background'
    for view in GameDetails/GameView.qml GameDetails/LaunchGame.qml; do
      substituteInPlace "$out/$view" \
        --replace-fail '(settings.GameBackground === "Screenshot") ? randoScreenshot : Utils.fanArt(game) || randoFanart' \
                       'Utils.fanArt(game) || randoFanart'
    done
  '';
  pegasusArtwork = import ../packages/pegasus-artwork.nix { inherit pkgs; };
  symphonyRecomp = pkgs.callPackage ../packages/symphony-recomp { };
  steamSession = pkgs.callPackage ../packages/steam-session { };
in
{
  home.packages = with pkgs; [
    pcsx2
    pegasus-frontend
    ryubing
    symphonyRecomp
    (pkgs.callPackage ../packages/voyee-controller { })
    steamSession
  ];

  # Human opens opt out of automation for the current client lifetime. Keep
  # Steam's existing desktop actions/URI handler, changing only their launcher.
  home.shellAliases.steam = "${steamSession}/bin/steam-manual";
  xdg.dataFile."applications/steam.desktop".source =
    pkgs.runCommand "steam-manual-desktop" { } ''
      substitute ${pkgs.steam-unwrapped}/share/applications/steam.desktop "$out" \
        --replace-fail 'Exec=steam ' 'Exec=${steamSession}/bin/steam-manual --desktop '
    '';

  # Pegasus reads these as its native configuration. Keep the UI behavior and
  # manually registered games in the repository instead of changing them only
  # through the application settings menu.
  xdg.configFile = {
    # This synchronous hook runs while Pegasus still owns its mapped window.
    # The Steam launcher consumes its PID/start-time-bound context after teardown.
    "pegasus-frontend/scripts/game-start/steam-workspace" = {
      executable = true;
      text = ''
        #!${pkgs.runtimeShell}
        exec ${steamSession}/bin/steam-session --capture-workspace
      '';
    };
    "pegasus-frontend/settings.txt".source = ../config/pegasus/settings.txt;
    "pegasus-frontend/sdl_controllers.txt".source = ../config/pegasus/sdl_controllers.txt;
    "pegasus-frontend/game_dirs.txt".source = ../config/pegasus/game_dirs.txt;
    "pegasus-frontend/metafiles/custom.metadata.pegasus.txt".source =
      ../config/pegasus/custom.metadata.pegasus.txt;
    "pegasus-frontend/metafiles/ps2.metadata.pegasus.txt".source =
      ../config/pegasus/ps2.metadata.pegasus.txt;
    "pegasus-frontend/metafiles/steam.metadata.pegasus.txt".source =
      ../config/pegasus/steam.metadata.pegasus.txt;
    "pegasus-frontend/metafiles/switch.metadata.pegasus.txt".source =
      ../config/pegasus/switch.metadata.pegasus.txt;
    "pegasus-frontend/themes/gameOS".source = curatedGameOS;
    "pegasus-frontend/media".source = pegasusArtwork;
  };

  # Emulator settings stay writable, while firmware, keys, and save data live
  # in the durable emulation data tree rather than only under ~/.config.
  home.file = {
    ".config/PCSX2/bios".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/bios/ps2";
    ".config/PCSX2/memcards".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/saves/ps2/memory-cards";
    ".config/PCSX2/sstates".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/saves/ps2/states";
    ".config/Ryujinx/system".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/bios/switch/system";
    ".config/Ryujinx/bis/system/Contents".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/bios/switch/firmware";
    ".config/Ryujinx/bis/user/save".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/matrix/data/emulation/saves/switch";
  };

  # Reserve durable data roots without putting ROMs, saves, or BIOS files in
  # the repository. Curated launcher artwork is versioned separately in media/.
  home.activation.createPegasusDataRoot = ''
    mkdir -p \
      "$HOME/matrix/data/emulation/bios/ps2" \
      "$HOME/matrix/data/emulation/bios/switch/firmware/registered" \
      "$HOME/matrix/data/emulation/bios/switch/system" \
      "$HOME/matrix/data/emulation/media/ps2" \
      "$HOME/matrix/data/emulation/media/switch" \
      "$HOME/matrix/data/emulation/roms/ps2" \
      "$HOME/matrix/data/emulation/roms/switch" \
      "$HOME/matrix/data/emulation/saves/ps2/memory-cards" \
      "$HOME/matrix/data/emulation/saves/ps2/states" \
      "$HOME/matrix/data/emulation/saves/switch"
  '';

  wayland.windowManager.hyprland.settings = {
    windowrule = [
      "match:class ^(pegasus-fe|org\\.pegasus-frontend\\.)$, fullscreen on"
      # Automated Steam installs a toggleable named rule in the verified
      # workspace launcher. No permanent rule may hide human-opened Steam.
    ];
  };
}
