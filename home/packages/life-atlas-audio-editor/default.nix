{ lib, stdenvNoCC, python3, makeWrapper, pi }:

stdenvNoCC.mkDerivation {
  pname = "life-atlas-audio-editor";
  version = "0.1.0";
  src = lib.cleanSource ./.;
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    export PYTHONDONTWRITEBYTECODE=1
    python3 -B -m unittest discover -s tests -v
  '';
  installPhase = ''
    install -Dm644 editor.py "$out/lib/life-atlas-audio-editor/editor.py"
    install -m644 policy.txt "$out/lib/life-atlas-audio-editor/policy.txt"
    makeWrapper ${python3}/bin/python3 "$out/bin/life-atlas-audio-editor" \
      --add-flags "$out/lib/life-atlas-audio-editor/editor.py" \
      --set LIFE_ATLAS_PI_BIN ${pi}/bin/pi \
      --set PYTHONDONTWRITEBYTECODE 1
    install -Dm644 README.md "$out/share/doc/life-atlas-audio-editor/README.md"
  '';
  meta = {
    description = "Private tool-free text-only uncertainty-preserving audio transcript editor";
    platforms = lib.platforms.linux;
    mainProgram = "life-atlas-audio-editor";
  };
}
