{ lib, stdenvNoCC, python3, makeWrapper, codex }:

stdenvNoCC.mkDerivation {
  pname = "pi-model-discovery";
  version = "1.0.0";
  src = lib.cleanSource ./.;
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  postPatch = ''
    substituteInPlace discovery.py --replace-fail '@CODEX_VERSION@' '${codex.version}'
  '';
  doCheck = true;
  checkPhase = ''
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
  '';
  installPhase = ''
    install -Dm644 discovery.py "$out/lib/pi-model-discovery/discovery.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/pi-model-discovery" \
      --add-flags "$out/lib/pi-model-discovery/discovery.py" \
      --set PYTHONDONTWRITEBYTECODE 1
    install -Dm644 README.md "$out/share/doc/pi-model-discovery/README.md"
  '';
  meta = {
    description = "Read-only daily Codex model catalog discovery for Pi";
    platforms = lib.platforms.linux;
    mainProgram = "pi-model-discovery";
  };
}
