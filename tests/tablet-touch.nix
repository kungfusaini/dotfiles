# Real wl_touch integration gate. No uinput device and no host compositor hooks.
{ pkgs, hyprland, source ? ../., contactHeight ? 56 }:
let
  base = import (source + "/tests/tablet-proof-native.nix") { inherit pkgs hyprland; native = true; };
  originalDriver = builtins.path { path = source + "/tests/tablet_proof_live.py"; };
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
in pkgs.runCommand "tablet-touch-test" { } ''
  mkdir -p "$out/bin" "$out/lib"
  # A reboot may leave /run/headless-mode absent. Mask /run before creating
  # the private posture fixture: never mkdir in the host's bound /run.
  substitute ${source}/tests/tablet_proof_live.py "$out/lib/driver.py" \
    --replace-fail "'--tmpfs','/run/headless-mode'" "'--tmpfs','/run','--ro-bind','/run/opengl-driver','/run/opengl-driver','--tmpfs','/run/headless-mode'" \
    --replace-fail "def click(x,y):move(x,y);pointer_command('down');time.sleep(.06);pointer_command('up')" "def click(x,y):move(x,y);pointer_command('mouse-down');time.sleep(.06);pointer_command('mouse-up')" \
    --replace-fail "rect['height']==52" "rect['height']==${toString contactHeight}"
  cp ${base}/bin/tablet-native-fold-test "$out/bin/tablet-touch-test"
  substituteInPlace "$out/bin/tablet-touch-test" \
    --replace-fail 'export TABLET_TEST_POINTER=' 'export TABLET_TEST_LUA=1; export TABLET_TEST_CONTROLS=${./tablet_touch_controls.py}; export PATH=${pkgs.coreutils}/bin:$PATH; export TABLET_TEST_RECORDER=${pkgs.wf-recorder}/bin/wf-recorder; export TABLET_TEST_TOUCH_PLUGIN=${plugin}/lib/touch.so; export TABLET_TEST_POINTER_ORIGINAL=' \
    --replace-fail 'export TABLET_TEST_VIDEO=' 'export TABLET_TEST_POINTER=${client}; export TABLET_TEST_VIDEO=' \
    --replace-fail '${originalDriver}' "$out/lib/driver.py"
''
