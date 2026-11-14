{ lib, python3, runCommand, makeWrapper, stdenv, pkg-config, wayland, wayland-scanner, wayland-protocols, hyprland, systemd }:
let
  python = python3.withPackages (ps: [ ps.dbus-python ps.pygobject3 ]);
in
runCommand "agent-lid-sleep" {
  nativeBuildInputs = [ makeWrapper stdenv.cc pkg-config wayland-scanner ];
  buildInputs = [ wayland ];
  meta.description = "Agent-aware lid and explicitly requested screen-off sleep";
  meta.platforms = lib.platforms.linux;
} ''
  PYTHONPATH=${./.} ${python}/bin/python -m unittest discover -s ${./tests} -v
  mkdir -p "$out/lib" "$out/bin"
  cp ${./agent_lid_sleep.py} "$out/lib/agent_lid_sleep.py"
  cp ${./agent_screen_sleep.py} "$out/lib/agent_screen_sleep.py"
  protocol=${wayland-protocols}/share/wayland-protocols/staging/ext-idle-notify/ext-idle-notify-v1.xml
  wayland-scanner client-header "$protocol" ext-idle-notify-v1-client-protocol.h
  wayland-scanner private-code "$protocol" ext-idle-notify-v1-protocol.c
  $CC -Wall -Wextra -Werror -I. ${./input_activity.c} ext-idle-notify-v1-protocol.c \
    $(pkg-config --cflags --libs wayland-client) -o "$out/lib/input-activity"
  makeWrapper ${python}/bin/python "$out/bin/agent-lid-sleep" \
    --add-flags "$out/lib/agent_lid_sleep.py"
  makeWrapper ${python}/bin/python "$out/bin/agent-screen-sleep" \
    --prefix PATH : ${lib.makeBinPath [ hyprland systemd ]} \
    --add-flags "$out/lib/agent_screen_sleep.py $out/lib/input-activity"
''
