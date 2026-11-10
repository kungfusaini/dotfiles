{ pkgs, hyprland, native ? false }:
let
  sensor = pkgs.writeShellScriptBin "monitor-sensor" ''
    while true; do
      printf 'Has accelerometer\n    Accelerometer orientation: %s\n    Accelerometer tilt: upright\n' "$(< "$TABLET_TEST_ORIENTATION")"
      sleep .1
    done
  '';
  orientation = pkgs.writeShellApplication {
    name = "tablet-orientation";
    runtimeInputs = [pkgs.python3 hyprland pkgs.quickshell pkgs.coreutils pkgs.procps sensor];
    text = ''
      export TABLET_ORIENTATION_SESSION=native
      export TABLET_ORIENTATION_POLICY=${pkgs.writeText "private-orientation-policy.json" (builtins.toJSON { monitor="eDP-1"; devices=[]; })}
      export TABLET_ROTATION_FADE_QML=${../home/config/quickshell/tablet-rotation-fade}
      exec python3 ${../home/scripts/desktop/tablet-orientation.py} "$@"
    '';
  };
  registry = pkgs.writeText "private-native-apps.json" (builtins.toJSON
    (builtins.filter (app: app.id == "browser")
      (builtins.fromJSON (builtins.readFile ../home/config/quickshell/tablet-home-preview/apps.json))));
  laptop = pkgs.writeText "tablet-laptop-fixture.qml" ''
    import Quickshell
    import QtQuick
    ShellRoot { FloatingWindow { visible: true; width: 400; height: 500; color: "#ff00ff" } }
  '';
  media = pkgs.callPackage ../home/packages/tablet-proof/media {
    inherit hyprland;
    testOrigins = [ "http://127.0.0.1/*" ];
  };
  proof = if native then pkgs.callPackage ../home/packages/tablet-proof/native.nix { inherit hyprland orientation media; }
    else pkgs.callPackage ../home/packages/tablet-proof { inherit hyprland; };
  python = pkgs.python3.withPackages (p:[p.pillow]);
  pointer = pkgs.stdenv.mkDerivation {
    name = "tablet-private-pointer";
    dontUnpack = true;
    nativeBuildInputs = [ pkgs.pkg-config pkgs.wayland-scanner ];
    buildInputs = [ pkgs.wayland ];
    buildPhase = ''
      wayland-scanner client-header ${pkgs.wlr-protocols}/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml virtual-pointer.h
      wayland-scanner private-code ${pkgs.wlr-protocols}/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml virtual-pointer.c
      $CC -Wall -Wextra -Werror -I. ${./tablet_virtual_pointer.c} virtual-pointer.c $(pkg-config --cflags --libs wayland-client) -o tablet-private-pointer
    '';
    installPhase = ''mkdir -p "$out/bin"; cp tablet-private-pointer "$out/bin/"'';
  };
  video = pkgs.runCommand "tablet-proof-test-video" { nativeBuildInputs=[pkgs.ffmpeg]; } ''
    ffmpeg -v error -f lavfi -i 'color=c=0x15b94d:s=960x640:d=2:r=25' -c:v libvpx -b:v 300k -an -f webm "$out"
  '';
  helper = pkgs.writeShellScript "tablet-proof-private-helper" ''
    export TABLET_PROOF_QML=${proof.ui}/shell.qml
    export TABLET_PROOF_BIN="$0"
    export PATH="$TABLET_TEST_FAKE_BIN:$PATH"
    export TABLET_PROOF_SOURCE=${../home/packages/tablet-proof/controller.py}
    export TABLET_MEDIA_CLIENT_SOURCE=${../home/packages/tablet-proof/media/client.py}
    export TABLET_WINDOW_APPS_SOURCE=${../home/scripts/desktop/tablet_apps.py}
    export TABLET_APPS_REGISTRY=${registry}
    export TABLET_STAGE_QML=${proof.ui}/stage.qml
    export TABLET_NATIVE_ORIENTATION_BIN=${orientation}/bin/tablet-orientation
    exec ${python}/bin/python ${if native then ../home/packages/tablet-proof/native.py else ../home/packages/tablet-proof/controller.py} "$@"
  '';
in pkgs.writeShellApplication {
  name = if native then "tablet-native-fold-test" else "tablet-proof-native-test";
  runtimeInputs = [python hyprland pkgs.quickshell pkgs.labwc pkgs.dbus pkgs.glib pkgs.dconf pkgs.wtype pkgs.grim pkgs.squeekboard pkgs.vivaldi];
  text = ''
    export TABLET_TEST_NATIVE_FOLD=${if native then "1" else "0"}
    export TABLET_TEST_NATIVE_SOURCE=${../home/packages/tablet-proof/native.py}
    export TABLET_TEST_LAPTOP_QML=${laptop}
    export TABLET_TEST_MEDIA_EXTENSION=${media.extension}
    export TABLET_TEST_MEDIA_EXTENSION_ID=${media.extensionId}
    export TABLET_TEST_MEDIA_MANIFEST=${media.hostManifest}
    export TABLET_MEDIA_CLIENT_SOURCE=${../home/packages/tablet-proof/media/client.py}
    export TABLET_PROOF_SOURCE=${../home/packages/tablet-proof/controller.py}
    export TABLET_TEST_HYPRLAND=${hyprland}/bin/Hyprland
    export TABLET_TEST_HYPRCTL=${hyprland}/bin/hyprctl
    export TABLET_TEST_VIVALDI=${pkgs.vivaldi}/bin/vivaldi
    export TABLET_TEST_POINTER=${pointer}/bin/tablet-private-pointer
    export TABLET_TEST_VIDEO=${video}
    export TABLET_TEST_CLEANUP=${./tablet_window_live.py}
    export TABLET_PROOF_BIN=${helper}
    export TABLET_TEST_PROOF_QML=${proof.ui}/shell.qml
    export XKB_CONFIG_ROOT=${pkgs.xkeyboard_config}/share/X11/xkb
    export GIO_EXTRA_MODULES=${pkgs.lib.getLib pkgs.dconf}/lib/gio/modules
    export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:${pkgs.squeekboard}/share
    export FONTCONFIG_FILE=${pkgs.makeFontsConf {fontDirectories=[pkgs.dejavu_fonts];}}
    export GTK_THEME=Adwaita:dark
    export G_RESOURCE_OVERLAYS=/sm/puri/squeekboard=${../home/config/squeekboard-preview}/resource
    export SQUEEKBOARD_KEYBOARDSDIR=${../home/config/squeekboard-preview}/keyboards
    exec ${python}/bin/python ${./tablet_proof_live.py}
  '';
}
