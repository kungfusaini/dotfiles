# Upstream shell smoke test on a private virtual compositor, never the host seat.
{ pkgs }:
let
  trial = pkgs.callPackage ../hosts/kirax1/packages/tablet-session-trial.nix {};
  driver = pkgs.writeShellScript "plasma-mobile-headless-driver" ''
    set -eu
    export XDG_RUNTIME_DIR="$TMPDIR/runtime"
    mkdir -m 700 "$XDG_RUNTIME_DIR"
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME/.config"
    cp ${trial.defaults}/* "$HOME/.config/"
    export XDG_DATA_DIRS=${trial.environment}/share
    export XDG_CONFIG_DIRS=${trial.defaults}
    export QML_IMPORT_PATH=${trial.environment}/lib/qt-6/qml
    export NIXPKGS_QT6_QML_IMPORT_PATH=${trial.environment}/lib/qt-6/qml
    export QT_PLUGIN_PATH=${trial.environment}/lib/qt-6/plugins
    export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
    export LANG=C.UTF-8
    export XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=wayland
    export QT_QPA_PLATFORM=wayland QT_QUICK_BACKEND=software
    export LIBGL_ALWAYS_SOFTWARE=1 KWIN_COMPOSE=QPainter
    export PLASMA_DEFAULT_SHELL=org.kde.plasma.mobileshell
    exec dbus-run-session --config-file=${pkgs.dbus}/share/dbus-1/session.conf -- ${pkgs.writeShellScript "plasma-mobile-headless-inner" ''
      set -eu
      kwin_wayland --virtual --width 1280 --height 800 --no-lockscreen \
        --exit-with-session "plasmashell -p org.kde.plasma.mobileshell" > "$TMPDIR/shell.log" 2>&1 &
      compositor=$!
      cleanup() {
        code=$?
        if [ "$code" != 0 ]; then cat "$TMPDIR/shell.log" "$TMPDIR/desktop-count" >&2 || true; fi
        kill "$compositor" 2>/dev/null || true
        wait "$compositor" 2>/dev/null || true
      }
      trap cleanup EXIT
      for i in $(seq 1 100); do
        kill -0 "$compositor"
        if gdbus call --session --dest org.kde.plasmashell --object-path /PlasmaShell \
          --method org.kde.PlasmaShell.evaluateScript 'print(desktops().length)' > "$TMPDIR/desktop-count" 2>/dev/null; then
          if grep -Eq "[1-9]" "$TMPDIR/desktop-count"; then
            sleep 3
            kill -0 "$compositor"
            exit 0
          fi
        fi
        sleep .25
      done
      cat "$TMPDIR/shell.log" >&2
      exit 1
    ''}
  '';
in pkgs.runCommand "plasma-mobile-isolated-smoke" {
  nativeBuildInputs = [ trial.environment pkgs.dbus pkgs.glib pkgs.coreutils ];
} ''
  ${driver}
  mkdir -p "$out"
  cp "$TMPDIR/shell.log" "$out/shell.log"
  cp "$TMPDIR/desktop-count" "$out/desktop-count"
''
