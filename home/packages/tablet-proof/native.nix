{ pkgs, lib, hyprland ? pkgs.hyprland, orientation,
  media ? pkgs.callPackage ./media { inherit hyprland; } }:
let
  registry = pkgs.writeText "tablet-native-apps.json" (builtins.toJSON
    (builtins.filter (app: app.id == "browser")
      (builtins.fromJSON (builtins.readFile ../../config/quickshell/tablet-home-preview/apps.json))));
  ui = pkgs.runCommand "tablet-native-ui" {} ''
    mkdir -p "$out"
    cp ${../../config/quickshell/tablet-home-preview}/*.qml "$out/"
    cp ${./native.qml} "$out/shell.qml"
    cp ${./EdgeGestures.qml} "$out/EdgeGestures.qml"
  '';
  package = pkgs.writeShellApplication {
    name = "tablet-native";
    runtimeInputs = with pkgs; [ python3 quickshell coreutils glib dconf squeekboard wireplumber brightnessctl libnotify vivaldi hyprland ];
    text = ''
      export TABLET_PROOF_QML=${ui}/shell.qml
      export TABLET_PROOF_SOURCE=${./controller.py}
      export TABLET_MEDIA_CLIENT_SOURCE=${./media/client.py}
      export TABLET_WINDOW_APPS_SOURCE=${../../scripts/desktop/tablet_apps.py}
      export TABLET_APPS_REGISTRY=${registry}
      export TABLET_STAGE_QML=${ui}/stage.qml
      export TABLET_NATIVE_ORIENTATION_BIN=${orientation}/bin/tablet-orientation
      export TABLET_PROOF_BIN
      TABLET_PROOF_BIN="$(readlink -f "$0")"
      export QT_QUICK_CONTROLS_STYLE=Basic
      export GTK_THEME=Adwaita:dark
      export G_RESOURCE_OVERLAYS=/sm/puri/squeekboard=${../../config/squeekboard-preview}/resource
      export SQUEEKBOARD_KEYBOARDSDIR=${../../config/squeekboard-preview}/keyboards
      export GIO_EXTRA_MODULES=${lib.getLib pkgs.dconf}/lib/gio/modules
      export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:"''${XDG_DATA_DIRS:-/run/current-system/sw/share}"
      exec python3 ${./native.py} "$@"
    '';
  };
in { inherit package ui media; }
