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
    export XDG_CONFIG_DIRS=${trial.defaults}:${trial.environment}/etc/xdg
    export XDG_MENU_PREFIX=plasma-
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.pipewire ]}
    export QML_IMPORT_PATH=${trial.environment}/lib/qt-6/qml
    export NIXPKGS_QT6_QML_IMPORT_PATH=${trial.environment}/lib/qt-6/qml
    export QT_PLUGIN_PATH=${trial.environment}/lib/qt-6/plugins
    export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
    export LANG=C.UTF-8
    export XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=wayland
    export DBUS_SYSTEM_BUS_ADDRESS="unix:path=$TMPDIR/no-system-bus"
    export QT_FORCE_STDERR_LOGGING=1
    export QT_QPA_PLATFORM=wayland QT_QUICK_BACKEND=software
    export LIBGL_ALWAYS_SOFTWARE=1 KWIN_COMPOSE=QPainter
    export PLASMA_DEFAULT_SHELL=org.kde.plasma.mobileshell
    exec dbus-run-session --config-file=${pkgs.dbus}/share/dbus-1/session.conf -- ${pkgs.writeShellScript "plasma-mobile-headless-inner" ''
      set -eu
      export WAYLAND_DISPLAY=tablet-mobile-test
      kwin_wayland --virtual --width 1280 --height 800 --no-lockscreen \
        --socket "$WAYLAND_DISPLAY" > "$TMPDIR/compositor.log" 2>&1 &
      compositor=$!
      shellpid=""
      cleanup() {
        code=$?
        if [ "$code" != 0 ]; then cat "$TMPDIR/compositor.log" "$TMPDIR/shell.log" "$TMPDIR/desktop-count" >&2 || true; fi
        if [ -n "$shellpid" ]; then kill "$shellpid" 2>/dev/null || true; wait "$shellpid" 2>/dev/null || true; fi
        kill "$compositor" 2>/dev/null || true
        wait "$compositor" 2>/dev/null || true
      }
      trap cleanup EXIT
      for i in $(seq 1 100); do
        kill -0 "$compositor"
        if [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then break; fi
        sleep .1
      done
      # Start the actual mobile shell explicitly and capture its QML errors.
      # KWin's --exit-with-session child output is not this shell's log.
      dbus-update-activation-environment WAYLAND_DISPLAY
      plasmashell --no-respawn -p org.kde.plasma.mobileshell > "$TMPDIR/shell.log" 2>&1 &
      shellpid=$!
      for i in $(seq 1 100); do
        kill -0 "$shellpid"
        kill -0 "$compositor"
        # Never D-Bus-activate a default desktop shell as a test side effect.
        if ! gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
          --method org.freedesktop.DBus.NameHasOwner org.kde.plasmashell | grep -q true; then
          sleep .25
          continue
        fi
        if gdbus call --session --dest org.kde.plasmashell --object-path /PlasmaShell \
          --method org.kde.PlasmaShell.evaluateScript 'print(desktops().length)' > "$TMPDIR/desktop-count" 2>/dev/null; then
          if grep -Eq "[1-9]" "$TMPDIR/desktop-count"; then
            sleep 5
            kill -0 "$compositor"
            kill -0 "$shellpid"
            if grep -Eq 'Error loading QML file|QQmlComponent: Component is not ready|module .* is not installed|error when loading applet' "$TMPDIR/shell.log"; then
              exit 1
            fi
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
  cp "$TMPDIR/compositor.log" "$out/compositor.log"
  cp "$TMPDIR/desktop-count" "$out/desktop-count"
''
