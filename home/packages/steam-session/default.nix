{ lib, stdenvNoCC, python3, makeWrapper, systemd, libnotify }:
stdenvNoCC.mkDerivation {
  pname = "steam-session";
  version = "1.0.0";
  src = ./.;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export HOME="$TMPDIR/test-home"
    mkdir -p "$HOME"
    python3 -m unittest discover -s tests -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin" "$out/libexec/steam-session"
    cp scripts/*.py "$out/libexec/steam-session/"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-session" \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/session.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-library" \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/steamctl.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/steam-manual" \
      --prefix PATH : ${lib.makeBinPath [ systemd libnotify ]} \
      --add-flags "$out/libexec/steam-session/manual.py"
    runHook postInstall
  '';
  meta = {
    description = "Pegasus Steam launcher with independent guarded post-game cleanup";
    platforms = lib.platforms.linux;
    mainProgram = "steam-session";
  };
}
