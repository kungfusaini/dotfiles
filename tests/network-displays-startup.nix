# Real GTK on a private headless compositor and bus; no media or host devices.
{ pkgs, client ? pkgs.callPackage ../home/packages/gnome-network-displays { }, expectRequest ? false }:
let
  python = pkgs.python3.withPackages (ps: [ ps.dbus-next ]);
in
pkgs.runCommand "network-displays-startup${if expectRequest then "-negative-control" else ""}" { } ''
  export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  ${python}/bin/python3 ${../home/packages/gnome-network-displays/tests/startup_smoke.py} \
    --package ${client} --labwc ${pkgs.labwc}/bin/labwc \
    --dbus-daemon ${pkgs.dbus}/bin/dbus-daemon ${pkgs.lib.optionalString expectRequest "--expect-request"}
  touch "$out"
''
