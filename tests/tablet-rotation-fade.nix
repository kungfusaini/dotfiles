# Standalone sandboxed Qt check; no compositor, display rotation or sensor.
{ pkgs }:
pkgs.runCommand "tablet-rotation-fade-tests" { } ''
  export QT_QPA_PLATFORM=offscreen
  export QT_QUICK_BACKEND=software
  export QT_PLUGIN_PATH=${pkgs.qt6.qtbase}/lib/qt-6/plugins
  export QML_IMPORT_PATH=${pkgs.qt6.qtdeclarative}/lib/qt-6/qml
  export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  export XDG_RUNTIME_DIR="$TMPDIR/runtime"
  export HOME="$TMPDIR/home"
  export XDG_CACHE_HOME="$TMPDIR/cache"
  mkdir -m 700 "$XDG_RUNTIME_DIR"
  mkdir -p "$HOME" "$XDG_CACHE_HOME"
  mkdir -p tests/qml home/config/quickshell/tablet-rotation-fade
  cp ${./qml/tst_RotationFade.qml} tests/qml/tst_RotationFade.qml
  cp ${../home/config/quickshell/tablet-rotation-fade/FadeState.qml} home/config/quickshell/tablet-rotation-fade/FadeState.qml
  ${pkgs.qt6.qtdeclarative}/bin/qmltestrunner -input tests/qml
  touch "$out"
''
