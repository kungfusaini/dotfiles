# Opt-in, non-deploying migration gates. baselineHome must come from the exact
# pre-migration Git revision, not a second copy of the candidate settings.
{ pkgs, hyprland, homeConfig, baselineHome }:
let
  lib = pkgs.lib;
  control = pkgs.callPackage ../home/packages/hyprland-control { inherit hyprland; };
  python = pkgs.python3.withPackages (p: [ p.pillow p.pygobject3 ]);
  screenSleep = pkgs.callPackage ../home/packages/agent-lid-sleep { inherit hyprland; };
  project = pkgs.callPackage ../home/packages/project-object { };
  projectTests = lib.cleanSource ../home/packages/project-object/tests;
  candidate = pkgs.writeText "hyprland-desktop.lua" homeConfig.xdg.configFile."hypr/hyprland.lua".text;
  baseline = pkgs.writeText "hyprland-desktop-baseline.json" (builtins.toJSON {
    settings = baselineHome.wayland.windowManager.hyprland.settings;
    extraConfig = baselineHome.wayland.windowManager.hyprland.extraConfig;
    config = baselineHome.xdg.configFile."hypr/hyprland.conf".text;
  });
  transition = pkgs.writeText "hyprland-desktop-transition.conf" homeConfig.xdg.configFile."hypr/hyprland.conf".text;
  legacy = pkgs.writeText "hyprland-desktop-baseline.conf" baselineHome.xdg.configFile."hypr/hyprland.conf".text;
  pointer = pkgs.stdenv.mkDerivation {
    name = "hyprland-desktop-private-pointer";
    dontUnpack = true;
    nativeBuildInputs = [ pkgs.pkg-config pkgs.wayland-scanner ];
    buildInputs = [ pkgs.wayland ];
    buildPhase = ''
      wayland-scanner client-header ${pkgs.wlr-protocols}/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml virtual-pointer.h
      wayland-scanner private-code ${pkgs.wlr-protocols}/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml virtual-pointer.c
      $CC -Wall -Wextra -Werror -I. ${./tablet_virtual_pointer.c} virtual-pointer.c $(pkg-config --cflags --libs wayland-client) -o hyprland-desktop-private-pointer
    '';
    installPhase = ''mkdir -p "$out/bin"; cp hyprland-desktop-private-pointer "$out/bin/"'';
  };
  unit = pkgs.runCommand "hyprland-desktop-parity" { nativeBuildInputs = [ pkgs.lua pkgs.python3 ]; } ''
    export PYTHONPATH=${control.pythonPath} PYTHONDONTWRITEBYTECODE=1 LUA=${pkgs.lua}/bin/lua
    lua ${./hyprland_desktop_capture.lua} ${candidate} > capture.json
    python ${./hyprland_desktop_parity.py} ${baseline} capture.json --transition ${transition}
    python ${./test_hyprland_control.py}
    cp capture.json "$out"
  '';
  environment = ''
    export PYTHONPATH=${control.pythonPath}:${projectTests}:"''${PYTHONPATH:-}"
    export PYTHONDONTWRITEBYTECODE=1
    unset HYPRLAND_CONTROL_TEST_BACKEND
    export XKB_CONFIG_ROOT=${pkgs.xkeyboard_config}/share/X11/xkb
    export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
  '';
  runner = pkgs.writeShellApplication {
    name = "hyprland-desktop-test";
    runtimeInputs = [ python hyprland control pkgs.nodejs pkgs.labwc pkgs.bubblewrap pkgs.dbus pkgs.wtype pkgs.glib ];
    text = environment + ''
      export MIGRATION_PRIVATE_DRIVER=${./hyprland_desktop_private.py}
      export MIGRATION_LEGACY_CONFIG=${legacy}
      export MIGRATION_TRANSITION_CONFIG=${transition}
      export MIGRATION_CONTROL=${control}/bin/hypr-control
      export MIGRATION_SCREEN_SLEEP_SOURCE=${screenSleep}/lib/agent_screen_sleep.py
      export MIGRATION_PROJECT_PACKAGE=${project}
      export MIGRATION_COMMS_SCRIPT=${../home/config/hypr/scripts/hypr-comms-workspace-launch}
      export MIGRATION_LUA_CONFIG=${candidate}
      export MIGRATION_FIXTURE=${./hyprland_desktop_fixture.py}
      export TABLET_TEST_HYPRLAND=${hyprland}/bin/Hyprland
      export TABLET_TEST_HYPRCTL=${hyprland}/bin/hyprctl
      export TABLET_TEST_POINTER=${pointer}/bin/hyprland-desktop-private-pointer
      export TABLET_TEST_CLEANUP=${./tablet_window_live.py}
      export GI_TYPELIB_PATH=${lib.makeSearchPath "lib/girepository-1.0" [ pkgs.gobject-introspection pkgs.glib.out pkgs.gtk3 pkgs.pango.out pkgs.harfbuzz pkgs.atk pkgs.gdk-pixbuf ]}
      export XDG_DATA_DIRS=${pkgs.hicolor-icon-theme}/share
      export GIO_USE_VFS=local
      exec ${python}/bin/python ${./hyprland_desktop_live.py}
    '';
  };
  browserRunner = pkgs.writeShellApplication {
    name = "hyprland-desktop-browser-test";
    runtimeInputs = [ python hyprland pkgs.labwc pkgs.dbus pkgs.kitty pkgs.vivaldi ];
    text = environment + ''
      exec ${python}/bin/python ${projectTests}/agent_browser_integration.py --lua \
        --hyprland ${hyprland}/bin/Hyprland --hyprctl ${hyprland}/bin/hyprctl \
        --labwc ${pkgs.labwc}/bin/labwc --kitty ${pkgs.kitty}/bin/kitty --vivaldi ${pkgs.vivaldi}/bin/vivaldi \
        --helper ${project}/bin/project-workspace-exec --router ${project}/bin/project-browser
    '';
  };
  fileRunner = pkgs.writeShellApplication {
    name = "hyprland-desktop-file-test";
    runtimeInputs = [ python hyprland pkgs.labwc pkgs.dbus pkgs.kitty pkgs.vivaldi pkgs.swayimg pkgs.grim ];
    text = environment + ''
      exec ${python}/bin/python ${projectTests}/file_open_integration.py --lua \
        --hyprland ${hyprland}/bin/Hyprland --hyprctl ${hyprland}/bin/hyprctl \
        --labwc ${pkgs.labwc}/bin/labwc --kitty ${pkgs.kitty}/bin/kitty --vivaldi ${pkgs.vivaldi}/bin/vivaldi \
        --swayimg ${pkgs.swayimg}/bin/swayimg --loupe ${(pkgs.callPackage ../home/packages/loupe.nix { })}/bin/loupe \
        --grim ${pkgs.grim}/bin/grim --opener ${project}/bin/project-file-open
    '';
  };
in { inherit unit runner browserRunner fileRunner pointer project control; }
