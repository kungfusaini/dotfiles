# Pixel-verified layer composition on a private software/headless compositor.
# No host display/socket, input devices, microphone, settings or Pi session.
{ pkgs }:
let
  stub = pkgs.writeShellScript "tablet-iteration-status-stub" ''
    if test "''${1:-}" = agent-state; then
      exec ${pkgs.quickshell}/bin/quickshell ipc --path ${../home/config/quickshell/tablet-home-preview}/agent.qml call tabletAgent snapshot
    fi
    printf '{"running":true,"visible":true,"view":"%s","recording":false,"transcribing":false,"uncertain":false,"ready":false,"error":""}\n' "$TABLET_ITERATION_TEST_VIEW"
  '';
  liveHelper = pkgs.writeShellScript "tablet-native-live-helper" ''
    exec ${pkgs.python3}/bin/python ${../home/scripts/desktop/tablet-iterate.py} "$@"
  '';
  goodUi = pkgs.runCommand "tablet-live-good-ui" {} ''
    mkdir -p "$out/share/tablet-ui"
    cp -r ${../home/config/quickshell/tablet-home-preview}/. "$out/share/tablet-ui/"
    chmod u+w "$out/share/tablet-ui/iteration.qml"
    ${pkgs.python3}/bin/python - <<'PY'
import os
from pathlib import Path
path = Path(os.environ['out']) / 'share/tablet-ui/iteration.qml'
text = path.read_text()
path.write_text('import QtQuick.Window\n' + text.rsplit('}', 1)[0] + Path('${./qml/TabletNavigationFixture.qmlinc}').read_text() + '}\n')
PY
    printf '%s\n' '{"protocol":1,"backend":"fixture"}' > "$out/share/tablet-ui/ui-manifest.json"
  '';
  alternateUi = pkgs.runCommand "tablet-live-alternate-ui" {} ''
    mkdir -p "$out"
    cp -r ${goodUi}/. "$out/"
    printf 'second immutable visual bundle\n' > "$out/visual-version"
  '';
  badUi = pkgs.runCommand "tablet-live-bad-ui" {} ''
    mkdir -p "$out"
    cp -r ${goodUi}/. "$out/"
    chmod u+w "$out/share/tablet-ui/iteration.qml"
    printf 'this is intentionally invalid QML\n' > "$out/share/tablet-ui/iteration.qml"
  '';
  # This Labwc fixture keeps non-Pi scenes mocked. Actual external windows and
  # Hyprland screencopy are exercised by tablet_window_live.py separately.
  mockRegistry = pkgs.writeText "tablet-mock-apps.json" (builtins.toJSON
    (map (app: if app.kind == "window" then app // { kind = "preview"; } else app)
      (builtins.fromJSON (builtins.readFile ../home/config/quickshell/tablet-home-preview/apps.json))));
  python = pkgs.python3.withPackages (p: [ p.pillow ]);
  fakePi = pkgs.writeShellScript "fake-pi-rpc" ''
    exec ${pkgs.python3}/bin/python ${./fake_pi_rpc.py} "$@"
  '';
in pkgs.runCommand "tablet-iteration-shell-smoke" { } ''
  export PATH=${pkgs.quickshell}/bin:${pkgs.wlrctl}/bin:${pkgs.wtype}/bin:${pkgs.squeekboard}/bin:${pkgs.dbus}/bin:${pkgs.lib.getBin pkgs.glib}/bin:${pkgs.wf-recorder}/bin:${pkgs.ffmpeg}/bin:$PATH
  export QT_QPA_PLATFORM=wayland
  export QT_QUICK_BACKEND=software
  export QT_QUICK_CONTROLS_STYLE=Basic
  export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  export HOME="$TMPDIR/home"
  export XDG_RUNTIME_DIR="$TMPDIR/runtime"
  export TABLET_ITERATE_BIN=${stub}
  export TABLET_APPS_REGISTRY=${mockRegistry}
  export WLR_BACKENDS=headless
  export WLR_RENDERER=pixman
  export WLR_LIBINPUT_NO_DEVICES=1
  export XKB_CONFIG_ROOT=${pkgs.xkeyboard_config}/share/X11/xkb
  unset DISPLAY WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE
  mkdir -p "$HOME" "$TMPDIR/labwc"
  mkdir -m 700 "$XDG_RUNTIME_DIR"
  compositor=""; fixture=""; surface=""; agent=""
  cleanup() {
    for pid in "$surface" "$agent" "$fixture" "$compositor"; do
      if test -n "$pid"; then kill "$pid" 2>/dev/null || true; fi
    done
  }
  trap cleanup EXIT
  ${pkgs.labwc}/bin/labwc -C "$TMPDIR/labwc" > compositor.log 2>&1 &
  compositor=$!
  for i in $(seq 1 100); do
    test ! -S "$XDG_RUNTIME_DIR/wayland-0" || break
    sleep 0.05
  done
  test -S "$XDG_RUNTIME_DIR/wayland-0" || { cat compositor.log; exit 1; }
  export WAYLAND_DISPLAY=wayland-0
  ${pkgs.wlr-randr}/bin/wlr-randr --output HEADLESS-1 --custom-mode 800x600@60
  ${pkgs.quickshell}/bin/quickshell --path ${./qml/TabletIterationFixture.qml} > fixture.log 2>&1 &
  fixture=$!
  for view in home pi; do
    export TABLET_ITERATION_TEST_VIEW="$view"
    ${pkgs.quickshell}/bin/quickshell \
      --path ${../home/config/quickshell/tablet-home-preview}/iteration.qml > "$view.log" 2>&1 &
    surface=$!
    for i in $(seq 1 100); do
      if ${pkgs.gnugrep}/bin/grep -q 'Configuration Loaded' "$view.log"; then break; fi
      kill -0 "$surface" || { cat "$view.log"; exit 1; }
      sleep 0.05
    done
    sleep 0.6
    kill -0 "$surface"
    cat "$view.log"
    ! ${pkgs.gnugrep}/bin/grep -E 'ERROR|ReferenceError|TypeError|is not a type|unavailable|Unable to assign' "$view.log"
    ${pkgs.grim}/bin/grim "$view.png"
    kill "$surface"
    wait "$surface" || true
    surface=""
  done
  ${python}/bin/python - <<'PY'
from PIL import Image
for view in ('home', 'pi'):
    image = Image.open(view + '.png').convert('RGB')
    w, h = image.size
    for point in ((20, h//2), (w-20, h-80)):
        r, g, b = image.getpixel(point)
        assert r < 70 and g > 15 and b > 15, (view, 'work wallpaper leaked', point, (r,g,b))
    pixels = list(image.crop((w//2-100, h//2-80, w//2+100, h//2+80)).getdata())
    white = sum(min(p) > 245 for p in pixels) / len(pixels)
    assert (white > .90 if view == 'pi' else white < .20), (view, 'wrong window layering', white)
PY
  export TABLET_NATIVE_CHAT=1
  export TABLET_CHAT_PI=${fakePi}
  export TABLET_CHAT_CWD="$HOME"
  export TABLET_CHAT_SESSIONS="$TMPDIR/sessions"
  export TABLET_CHAT_PROMPT=${../home/config/quickshell/tablet-home-preview}/tablet-context.md
  export TABLET_CHAT_PROVIDER=fake
  export TABLET_CHAT_MODEL=fake
  mkdir -p "$TABLET_CHAT_SESSIONS"
  touch "$TABLET_CHAT_SESSIONS/draft.txt"
  ${pkgs.quickshell}/bin/quickshell --path ${../home/config/quickshell/tablet-home-preview}/agent.qml > native-agent.log 2>&1 &
  agent=$!
  ${pkgs.quickshell}/bin/quickshell --path ${../home/config/quickshell/tablet-home-preview}/iteration.qml > native.log 2>&1 &
  surface=$!
  sleep 1
  kill -0 "$surface" || { cat native.log; exit 1; }
  kill -0 "$agent" || { cat native-agent.log; exit 1; }
  ! ${pkgs.gnugrep}/bin/grep -E 'ERROR|ReferenceError|TypeError|is not a type|Unable to assign' native.log
  ${pkgs.grim}/bin/grim native.png
  kill "$surface"
  wait "$surface" || true
  surface=""
  kill "$agent"
  wait "$agent" || true
  agent=""
  export TABLET_FAKE_CANCEL_NEW=1
  mkdir rpc-fixture
  cp ${../home/config/quickshell/tablet-home-preview}/*.qml rpc-fixture/
  cp --remove-destination ${./qml/TabletRpcFixture.qml} rpc-fixture/shell.qml
  ${pkgs.coreutils}/bin/timeout 8 ${pkgs.quickshell}/bin/quickshell --path "$PWD/rpc-fixture" > rpc.log 2>&1 || { cat rpc.log; exit 1; }
  ! ${pkgs.gnugrep}/bin/grep -E 'ERROR|ReferenceError|TypeError|is not a type|Unable to assign' rpc.log
  export TABLET_ITERATE_BIN=${liveHelper}
  export TABLET_UI_BACKEND=fixture
  export TABLET_AGENT_QML=${../home/config/quickshell/tablet-home-preview}/agent.qml
  export TABLET_ITERATION_QML=${goodUi}/share/tablet-ui/iteration.qml
  export TABLET_STAGE_QML=${../home/config/quickshell/tablet-home-preview}/stage.qml
  export TABLET_STAGE_SCREEN=HEADLESS-1
  export TABLET_FRAME_CHECKER=${./check_tablet_frames.py}
  export TABLET_TEST_GRIM=${pkgs.grim}/bin/grim
  export TABLET_TEST_GOOD_UI=${goodUi}
  export TABLET_TEST_BAD_UI=${badUi}
  export TABLET_TEST_ALTERNATE_UI=${alternateUi}
  export TABLET_RPC_LIVE_TEST=1
  export TABLET_FAKE_RPC_LOG="$TMPDIR/fake-rpc.jsonl"
  export XDG_CONFIG_HOME="$TMPDIR/config"
  export GSETTINGS_BACKEND=keyfile
  export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:${pkgs.squeekboard}/share
  mkdir -p "$XDG_CONFIG_HOME"
  ${pkgs.coreutils}/bin/timeout 120 ${pkgs.dbus}/bin/dbus-run-session --config-file=${pkgs.dbus}/share/dbus-1/session.conf -- ${python}/bin/python ${./tablet_native_live.py} ${../home/scripts/desktop/tablet-iterate.py} > live.log 2>&1 || { cat live.log live-surfaces.log transition-recording.log "$XDG_RUNTIME_DIR/tablet-chat/stage.log"; exit 1; }
  cat live.log
  # Negative control: after explicit trial exit the glaring work desktop MUST
  # be detected, proving the video check isn't passing empty/black recordings.
  wf-recorder --no-dmabuf -D -r 60 -c rawvideo -x rgb24 -m nut -f negative-control.nut > negative-recorder.log 2>&1 &
  negative=$!
  sleep .5
  kill -INT "$negative"
  wait "$negative"
  if ${python}/bin/python ${./check_tablet_frames.py} negative-control.nut negative > negative.log 2>&1; then
    echo 'Desktop detector failed its negative control'; exit 1
  fi
  ${pkgs.gnugrep}/bin/grep -q 'Work desktop visible in transition frame' negative.log
  mkdir -p "$out"
  cp home.png pi.png native.png mock-switcher-home-backdrop.png pi-switcher-home-backdrop.png live.log transition-frames.json transition-contact-sheet.png negative.log "$out"/
''
