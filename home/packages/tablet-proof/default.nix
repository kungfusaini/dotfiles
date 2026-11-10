{ pkgs, lib, hyprland ? pkgs.hyprland }:
let
  visuals = ../../config/quickshell/tablet-home-preview;
  keyboardLayout = ../../config/squeekboard-preview;
  ui = pkgs.runCommand "tablet-native-proof-ui" {} ''
    mkdir -p "$out"
    cp ${./proof.qml} "$out/shell.qml"
    cp ${./EdgeGestures.qml} "$out/EdgeGestures.qml"
    for file in TabletWallpaper GlassTile PillSlider ControlIcon FrameWitness; do
      cp "${visuals}/$file.qml" "$out/"
    done
  '';
  package = pkgs.writeShellApplication {
    name = "tablet-proof";
    runtimeInputs = with pkgs; [ python3 quickshell coreutils glib dconf squeekboard wireplumber brightnessctl hyprland ];
    text = ''
      export TABLET_PROOF_QML=${ui}/shell.qml
      export TABLET_PROOF_BIN
      TABLET_PROOF_BIN="$(readlink -f "$0")"
      export QT_QUICK_CONTROLS_STYLE=Basic
      export GTK_THEME=Adwaita:dark
      export G_RESOURCE_OVERLAYS=/sm/puri/squeekboard=${keyboardLayout}/resource
      export SQUEEKBOARD_KEYBOARDSDIR=${keyboardLayout}/keyboards
      export GIO_EXTRA_MODULES=${lib.getLib pkgs.dconf}/lib/gio/modules
      export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:"''${XDG_DATA_DIRS:-/run/current-system/sw/share}"
      exec python3 ${./controller.py} "$@"
    '';
  };
in { inherit package ui; }
