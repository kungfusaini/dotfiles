{ pkgs }:
pkgs.runCommand "tablet-proof-edge-touch-tests" {} ''
  export QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software
  export QT_PLUGIN_PATH=${pkgs.qt6.qtbase}/lib/qt-6/plugins
  export QML_IMPORT_PATH=${pkgs.qt6.qtdeclarative}/lib/qt-6/qml
  export FONTCONFIG_FILE=${pkgs.makeFontsConf {fontDirectories=[pkgs.dejavu_fonts];}}
  export XDG_RUNTIME_DIR="$TMPDIR/runtime" HOME="$TMPDIR/home"
  mkdir -m 700 "$XDG_RUNTIME_DIR"
  mkdir -p "$HOME" tests/qml home/packages/tablet-proof
  cp ${./qml/tst_TabletProofEdges.qml} tests/qml/tst_TabletProofEdges.qml
  cp ${../home/packages/tablet-proof/EdgeGestures.qml} home/packages/tablet-proof/EdgeGestures.qml
  ${pkgs.qt6.qtdeclarative}/bin/qmltestrunner -input tests/qml
  touch "$out"
''
