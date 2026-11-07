# Pure Qt layout/input tests: no compositor, app launch or live settings access.
{ pkgs }:
pkgs.runCommand "tablet-home-preview-tests" { } ''
  export QT_QPA_PLATFORM=offscreen
  export QT_QUICK_BACKEND=software
  export QT_QUICK_CONTROLS_STYLE=Basic
  export QT_PLUGIN_PATH=${pkgs.qt6.qtbase}/lib/qt-6/plugins
  export QML_IMPORT_PATH=${pkgs.qt6.qtdeclarative}/lib/qt-6/qml
  export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  export XDG_RUNTIME_DIR="$TMPDIR/runtime"
  export HOME="$TMPDIR/home"
  export XDG_CACHE_HOME="$TMPDIR/cache"
  mkdir -m 700 "$XDG_RUNTIME_DIR"
  mkdir -p "$HOME" "$XDG_CACHE_HOME" tests/qml home/config/quickshell/tablet-home-preview
  cp ${./qml/tst_TabletHome.qml} tests/qml/tst_TabletHome.qml
  cp ${./qml/tst_TabletChat.qml} tests/qml/tst_TabletChat.qml
  cp ${./qml/tst_TabletNavigation.qml} tests/qml/tst_TabletNavigation.qml
  cp ${../home/config/quickshell/tablet-home-preview}/*.qml home/config/quickshell/tablet-home-preview/
  ${pkgs.qt6.qtdeclarative}/bin/qmltestrunner -input tests/qml
  mkdir -p "$out"
  cp landscape.png portrait.png settings.png narrow-settings.png switcher.png "$out"/
''
