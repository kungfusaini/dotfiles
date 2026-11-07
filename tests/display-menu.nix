# nix build --impure --no-link --print-build-logs --expr \
#   'let f = builtins.getFlake (toString ./.); in import ./tests/display-menu.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
{ pkgs }:
pkgs.runCommand "display-menu-tests" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  export QT_QPA_PLATFORM=offscreen
  export QT_QUICK_BACKEND=software
  export QT_QUICK_CONTROLS_STYLE=Basic
  export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  export DISPLAY_MENU_QUICKSHELL=${pkgs.quickshell}/bin/quickshell
  export PYTHONDONTWRITEBYTECODE=1
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME" tests home/scripts/display home/config/quickshell/display-layout
  cp ${./test_display_menu.py} tests/test_display_menu.py
  cp ${../home/scripts/display/display-layout-open} home/scripts/display/display-layout-open
  cp ${../home/config/quickshell/display-layout/shell.qml} home/config/quickshell/display-layout/shell.qml
  python3 -m unittest discover -s tests -p test_display_menu.py -v
  touch "$out"
''
