{ config, pkgs, ... }:

let
  gameOSTheme = pkgs.fetchFromGitHub {
    owner = "PlayingKarrde";
    repo = "gameOS";
    rev = "7a5a5223ff7371d0747a7c5d3a3b8f2f5e36b4f2";
    sha256 = "1mwrk8dk6rbr72nr32bnn524agjq01x1fyih1yxm7m5h8rxlh6hh";
  };

  marioKartCover = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/9/9b/MK8_Deluxe_-_Box_NA.png";
    sha256 = "1nhrbll1wr0xwhya69i6frrdlafsr7ygrg285mfnk6i711waf2a3";
  };
  marioKartBackground = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/4/48/MK8DX_Nintendo_Wallpaper_1.jpg";
    sha256 = "1ghxnp8wlxq5lanznk8qkj2pd3q3g9az2fbbl204ry9aw7nss72k";
  };
  marioKartLogo = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/7/78/Mario_Kart_8_Deluxe_logo.png";
    sha256 = "1h1cdkzbnmiwcidlxvk39izi1ssvnj35ws8bf3x1k7kak5k8bfwy";
  };

  smashCover = pkgs.fetchurl {
    url = "https://www.ssbwiki.com/images/1/15/Super_Smash_Bros_Ultimate_Box_Art.png";
    sha256 = "1w4rgc5xqx5p0ifjz3scmzvs4wakfa5jdbij5q5jf762jazcfsg4";
  };
  smashBackground = pkgs.fetchurl {
    url = "https://www.ssbwiki.com/images/0/0e/SSBUBattlefieldWallpaper.jpg";
    sha256 = "040c0pgk40jxjbvl9vwhfzqy0p0b474hid9h2d8z79hhd5bd4kqp";
  };

  mario3dWorldCover = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/3/30/SM3DWBF_Box_NA_Final.png";
    sha256 = "14zdmk9nirvsani3p9nzghdgvbc14rs6j5pd00wls0ffrjlknm02";
  };
  mario3dWorldBackground = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/f/f0/SM3DW_BF_My_Nintendo_wallpaper_A_desktop.jpg";
    sha256 = "0pqnf364xiw306rslqxrgly5zwl43f8wsj1n3b5kr3gw3zihs2ri";
  };
  mario3dWorldLogo = pkgs.fetchurl {
    url = "https://www.mariowiki.com/images/1/18/SM3DW%2BBF_logo_alt.png";
    sha256 = "120lk20nf79zn09q8mrcvyd1g9jg4737qfdxr5xqdcx9kvqwvjkp";
  };

  crazyTaxiCover = pkgs.fetchurl {
    url = "https://psxdatacenter.com/psx2/images2/covers/SLES-50215/SLES-50215-F-S.jpg";
    sha256 = "0zy2r0wxncdqigfs6c7fhc1sq55qnzd2q54ngghl6c715xj3b4rb";
  };

  pegasusArtwork = pkgs.runCommand "pegasus-curated-artwork" {
    nativeBuildInputs = [ pkgs.imagemagick ];
  } ''
    mkdir -p \
      "$out/switch/mario-kart-8-deluxe" \
      "$out/switch/super-smash-bros-ultimate" \
      "$out/switch/super-mario-3d-world-bowsers-fury" \
      "$out/ps2/crazy-taxi"

    magick ${marioKartCover} -resize '900x1457>' -strip -quality 90 \
      "$out/switch/mario-kart-8-deluxe/boxFront.jpg"
    magick ${marioKartBackground} -resize '1920x1080^' -gravity center \
      -extent 1920x1080 -strip -quality 90 \
      "$out/switch/mario-kart-8-deluxe/background.jpg"
    magick ${marioKartLogo} -resize '1200x600>' -strip \
      "$out/switch/mario-kart-8-deluxe/logo.png"

    magick ${smashCover} -resize '900x1457>' -strip -quality 90 \
      "$out/switch/super-smash-bros-ultimate/boxFront.jpg"
    magick ${smashBackground} -resize '1920x1080^' -gravity center \
      -extent 1920x1080 -strip -quality 90 \
      "$out/switch/super-smash-bros-ultimate/background.jpg"

    magick ${mario3dWorldCover} -resize '900x1457>' -strip -quality 90 \
      "$out/switch/super-mario-3d-world-bowsers-fury/boxFront.jpg"
    magick ${mario3dWorldBackground} -resize '1920x1080^' -gravity center \
      -extent 1920x1080 -strip -quality 90 \
      "$out/switch/super-mario-3d-world-bowsers-fury/background.jpg"
    magick ${mario3dWorldLogo} -resize '1200x600>' -strip \
      "$out/switch/super-mario-3d-world-bowsers-fury/logo.png"

    magick ${crazyTaxiCover} -crop '836x1187+930+0' +repage \
      -resize '900x1275>' -strip -quality 90 \
      "$out/ps2/crazy-taxi/boxFront.jpg"
    magick ${crazyTaxiCover} -resize '1920x1080^' -gravity center \
      -extent 1920x1080 -blur 0x30 -fill black -colorize 38% \
      -strip -quality 90 "$out/ps2/crazy-taxi/background.jpg"
  '';
in
{
  home.packages = with pkgs; [
    pcsx2
    pegasus-frontend
    ryubing
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
    "pegasus-frontend/metafiles/switch.metadata.pegasus.txt".source =
      ../config/pegasus/switch.metadata.pegasus.txt;
    "pegasus-frontend/themes/gameOS".source = gameOSTheme;
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

  # Reserve the durable data roots without putting ROMs, saves, BIOS files, or
  # downloaded artwork in the Nix repository.
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
    ];
  };
}
