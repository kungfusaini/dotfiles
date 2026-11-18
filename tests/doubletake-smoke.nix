{ pkgs }:
let
  doubletake = pkgs.callPackage ../home/packages/doubletake { };
in
pkgs.runCommand "doubletake-smoke" {
  nativeBuildInputs = [ pkgs.gst_all_1.gstreamer pkgs.python3 ];
  GST_PLUGIN_SYSTEM_PATH_1_0 = doubletake.pluginPath;
  GST_PLUGIN_PATH_1_0 = doubletake.pluginPath;
} ''
  export HOME="$TMPDIR/home" XDG_RUNTIME_DIR="$TMPDIR/runtime"
  mkdir -m700 -p "$HOME" "$XDG_RUNTIME_DIR"
  unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS PULSE_SERVER

  ${doubletake}/bin/doubletake -version | grep -F 'doubletake v0.6.0'
  ${doubletake}/bin/doubletake-ctl -version | grep -F 'doubletake-ctl v0.6.0'
  ${doubletake}/bin/doubletake -help >help.txt 2>&1
  grep -F -- '-target' help.txt
  grep -F -- '-no-audio' help.txt
  grep -F -- '-test' help.txt

  for element in pipewiresrc pulsesrc x264enc h264parse rtph264pay; do
    gst-inspect-1.0 "$element" > /dev/null
  done
  # Synthetic patterns only: no desktop/audio source and no network sinks.
  gst-launch-1.0 -q videotestsrc num-buffers=5 ! \
    video/x-raw,width=320,height=240,framerate=30/1 ! videoconvert ! \
    x264enc tune=zerolatency ! h264parse ! fakesink

  ${doubletake}/bin/doubletake -daemonize -no-audio \
    -socket "$XDG_RUNTIME_DIR/trial.sock" >daemon.log 2>&1 &
  pid=$!
  trap 'kill "$pid" 2>/dev/null || true' EXIT
  for attempt in $(seq 1 100); do
    test ! -S "$XDG_RUNTIME_DIR/trial.sock" || break
    kill -0 "$pid"
    sleep 0.05
  done
  ${doubletake}/bin/doubletake-ctl -socket "$XDG_RUNTIME_DIR/trial.sock" status >status.json
  python3 - <<'PY'
  import json
  data = json.load(open("status.json"))
  assert data["ok"] is True, data
  assert not data.get("streams"), data
  PY
  kill "$pid"
  wait "$pid"
  trap - EXIT
  test ! -e "$XDG_RUNTIME_DIR/trial.sock"
  mkdir "$out"
  cp status.json daemon.log "$out/"
''
