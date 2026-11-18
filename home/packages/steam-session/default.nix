{ lib, stdenvNoCC, python3, makeWrapper, systemd, libnotify, callPackage }:
let control = callPackage ../hyprland-control { }; in
stdenvNoCC.mkDerivation {
  pname = "steam-session";
  version = "1.0.0";
  src = ./.;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 ];
  dontBuild = true;
  doCheck = true;
  doInstallCheck = true;
  checkPhase = ''
    runHook preCheck
    export PYTHONPATH=${control.pythonPath}
    export HYPRLAND_CONTROL_TEST_BACKEND=legacy
    export HOME="$TMPDIR/test-home"
    mkdir -p "$HOME"
    python3 -m unittest discover -s tests -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin" "$out/libexec/steam-session"
    cp scripts/*.py "$out/libexec/steam-session/"
    # The independent systemd worker invokes raw session.py via sys.executable,
    # not an executable wrapper, and intentionally has no inherited PYTHONPATH.
    cp ${control.pythonPath}/hyprland_control.py "$out/libexec/steam-session/"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-session" \
      --prefix PYTHONPATH : ${control.pythonPath} \
      --prefix PATH : "$out/bin" \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/session.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-library" \
      --prefix PYTHONPATH : ${control.pythonPath} \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/steamctl.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-manual" \
      --prefix PYTHONPATH : ${control.pythonPath} \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/manual.py"
    runHook postInstall
  '';
  installCheckPhase = ''
    runHook preInstallCheck
    (
      cd "$out/libexec/steam-session"
      env -i ${python3}/bin/python3 -E -B -c 'import session, steamctl, hyprland_control; assert hyprland_control.__file__.endswith("/libexec/steam-session/hyprland_control.py")'
    )
    runHook postInstallCheck
  '';
  meta = {
    description = "Pegasus Steam launcher with independent guarded post-game cleanup";
    platforms = lib.platforms.linux;
    mainProgram = "steam-session";
  };
}
