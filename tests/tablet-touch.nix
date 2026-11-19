# Real wl_touch integration gate. No uinput device and no host compositor hooks.
{ pkgs, hyprland, source ? ../., contactHeight ? 56, stremioOnly ? false, notificationProbe ? false, gameBackend ? "wayland" }:
assert builtins.elem gameBackend [ "wayland" "x11" ];
assert !(notificationProbe && stremioOnly);
let
  base = import (source + "/tests/tablet-proof-native.nix") { inherit pkgs hyprland; native = true; inherit stremioOnly; };
  originalDriver = builtins.path { path = source + "/tests/tablet_proof_live.py"; };
  inputGame = pkgs.runCommand "tablet-notification-input-game" {
    nativeBuildInputs = [ pkgs.pkg-config pkgs.stdenv.cc ];
    buildInputs = [ pkgs.SDL2 ];
  } ''
    mkdir -p "$out/bin"
    $CC -Wall -Wextra -Werror ${./tablet_notification_game.c} $(pkg-config --cflags --libs sdl2) -o "$out/bin/tablet-notification-game"
  '';
  plugin = pkgs.stdenv.mkDerivation {
    name = "tablet-private-touch-plugin";
    dontUnpack = true;
    nativeBuildInputs = [ pkgs.pkg-config ];
    buildInputs = [ hyprland.dev ] ++ hyprland.buildInputs;
    buildPhase = ''
      $CXX -std=c++23 -shared -fPIC -Wall -Wextra -Werror \
        $(pkg-config --cflags hyprland) ${./tablet_touch_plugin.cpp} -o touch.so
    '';
    installPhase = ''mkdir -p "$out/lib"; cp touch.so "$out/lib/"'';
  };
  client = pkgs.writeShellScript "tablet-private-touch" ''
    exec ${pkgs.python3}/bin/python ${./tablet_touch_client.py}
  '';
  executable = if stremioOnly then "tablet-stremio-test" else "tablet-native-fold-test";
  resultName = if notificationProbe then "tablet-notification-touch-test" else if stremioOnly then "tablet-stremio-touch-test" else "tablet-touch-test";
in pkgs.runCommand resultName { } ''
  mkdir -p "$out/bin" "$out/lib"
  # A reboot may leave /run/headless-mode absent. Mask /run before creating
  # the private posture fixture: never mkdir in the host's bound /run.
  substitute ${source}/tests/tablet_proof_live.py "$out/lib/driver.py" \
    --replace-fail "'--tmpfs','/run/headless-mode'" "'--tmpfs','/run','--ro-bind','/run/opengl-driver','/run/opengl-driver','--tmpfs','/run/headless-mode'" \
    --replace-fail "def click(x,y):move(x,y);pointer_command('down');time.sleep(.06);pointer_command('up')" "def click(x,y):move(x,y);pointer_command('mouse-down');time.sleep(.06);pointer_command('mouse-up')" \
    --replace-fail "rect['height']==52" "rect['height']==${toString contactHeight}"
  cp ${base}/bin/${executable} "$out/bin/${resultName}"
  ${pkgs.lib.optionalString notificationProbe ''
    substituteInPlace "$out/bin/${resultName}" \
      --replace-fail 'export TABLET_TEST_NATIVE_FOLD=' 'export TABLET_TEST_NOTIFICATION_GAME=${inputGame}/bin/tablet-notification-game; export TABLET_TEST_NOTIFICATION_BACKEND=${gameBackend}; export TABLET_TEST_MAKO=${pkgs.mako}/bin/mako; export TABLET_TEST_NOTIFY=${pkgs.libnotify}/bin/notify-send; export PATH=${pkgs.xwayland}/bin:$PATH; export TABLET_TEST_NATIVE_FOLD='
  ''}
  substituteInPlace "$out/bin/${resultName}" \
    --replace-fail 'export TABLET_TEST_POINTER=' 'export TABLET_TEST_LUA=1; export TABLET_TEST_CONTROLS=${./tablet_touch_controls.py}; export PATH=${pkgs.coreutils}/bin:$PATH; export TABLET_TEST_RECORDER=${pkgs.wf-recorder}/bin/wf-recorder; export TABLET_TEST_TOUCH_PLUGIN=${plugin}/lib/touch.so; export TABLET_TEST_POINTER_ORIGINAL=' \
    --replace-fail 'export TABLET_TEST_VIDEO=' 'export TABLET_TEST_POINTER=${client}; export TABLET_TEST_VIDEO=' \
    --replace-fail '${originalDriver}' "$out/lib/driver.py"
''
