# Opt-in real GPU/native-window test. All compositors, browser data, D-Bus,
# input and settings are private. The render node is used only for rendering.
{ pkgs, hyprland }:
let
  python = pkgs.python3.withPackages (p: [ p.pillow ]);
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
  wallpaper = pkgs.writeText "tablet-test-desktop.qml" ''
    import Quickshell
    import Quickshell.Wayland
    ShellRoot {
      PanelWindow {
        screen: Quickshell.screens.find(s => s.name === "eDP-1")
        anchors { top: true; bottom: true; left: true; right: true }
        color: "#ff00ff"; exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Background
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      }
      PanelWindow {
        screen: Quickshell.screens.find(s => s.name === "eDP-1")
        anchors { top: true; left: true; right: true }
        implicitHeight: 12; color: "#ff00ff"; exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      }
    }
  '';
  helper = pkgs.writeShellScript "tablet-window-helper" ''
    exec ${python}/bin/python ${../home/scripts/desktop/tablet-iterate.py} "$@"
  '';
  fakePi = pkgs.writeShellScript "tablet-window-fake-pi" ''
    exec ${python}/bin/python ${./fake_pi_rpc.py} "$@"
  '';
  ui = pkgs.runCommand "tablet-window-test-ui" {} ''
    mkdir -p "$out"
    cp -r ${../home/config/quickshell/tablet-home-preview}/. "$out/"
    chmod u+w "$out/iteration.qml"
    ${python}/bin/python - <<'PY'
import os
from pathlib import Path
path = Path(os.environ['out']) / 'iteration.qml'
text = path.read_text()
path.write_text('import QtQuick.Window\n' + text.rsplit('}', 1)[0] + Path('${./qml/TabletNavigationFixture.qmlinc}').read_text() + '}\n')
PY
  '';
in pkgs.writeShellApplication {
  name = "tablet-window-apps-test";
  runtimeInputs = [ python hyprland pkgs.quickshell pkgs.labwc pkgs.dbus pkgs.wlrctl pkgs.wtype pkgs.grim pkgs.wf-recorder pkgs.ffmpeg pkgs.squeekboard pkgs.glib pkgs.vivaldi ];
  text = ''
    export TABLET_TEST_HYPRLAND=${hyprland}/bin/Hyprland
    export TABLET_TEST_HYPRCTL=${hyprland}/bin/hyprctl
    export TABLET_TEST_VIVALDI=${pkgs.vivaldi}/bin/vivaldi
    export TABLET_TEST_VIVALDI_UNCONFIGURED=${pkgs.vivaldi.override { commandLineArgs = ""; }}/bin/vivaldi
    export TABLET_TEST_QS=${pkgs.quickshell}/bin/quickshell
    export TABLET_TEST_POINTER=${pointer}/bin/tablet-private-pointer
    export TABLET_TEST_WALLPAPER=${wallpaper}
    export TABLET_TEST_UI=${ui}
    export TABLET_ITERATE_BIN=${helper}
    export TABLET_APPS_MODULE=${../home/scripts/desktop/tablet_apps.py}
    export TABLET_TEST_REGISTRY=${../home/config/quickshell/tablet-home-preview/apps.json}
    export TABLET_TEST_CONTROLLER=${../home/scripts/desktop/tablet-iterate.py}
    export TABLET_CHAT_PI=${fakePi}
    export TABLET_CHAT_PROMPT=${../home/config/quickshell/tablet-home-preview/tablet-context.md}
    export TABLET_FRAME_CHECKER=${./check_tablet_frames.py}
    export XKB_CONFIG_ROOT=${pkgs.xkeyboard_config}/share/X11/xkb
    export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:${pkgs.squeekboard}/share
    export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
    exec ${python}/bin/python ${./tablet_window_live.py} "$@"
  '';
}
