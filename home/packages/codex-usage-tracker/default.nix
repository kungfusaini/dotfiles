{ lib, stdenvNoCC, python3, makeWrapper, systemd, libnotify }:

stdenvNoCC.mkDerivation {
  pname = "codex-usage-tracker";
  version = "1.0.0";
  src = lib.cleanSource ./.;
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm644 codex_usage.py "$out/lib/codex-usage/codex_usage.py"
    install -Dm644 codex_oneshot.py "$out/lib/codex-usage/codex_oneshot.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/codex-usage" \
      --add-flags "$out/lib/codex-usage/codex_usage.py" \
      --prefix PATH : ${lib.makeBinPath [ libnotify ]} \
      --set PYTHONDONTWRITEBYTECODE 1
    makeWrapper ${python3}/bin/python3 "$out/bin/pi-oneshot" \
      --add-flags "-B $out/lib/codex-usage/codex_oneshot.py" \
      --prefix PATH : ${lib.makeBinPath [ systemd ]} \
      --set PYTHONDONTWRITEBYTECODE 1
    install -Dm644 README.md "$out/share/doc/codex-usage-tracker/README.md"
    runHook postInstall
  '';
  meta = {
    description = "Lightweight hourly Codex quota snapshots and incremental Pi model/token reports";
    platforms = lib.platforms.linux;
    mainProgram = "codex-usage";
  };
}
