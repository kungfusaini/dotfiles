{ lib, stdenvNoCC, python3, makeWrapper, tzdata }:

stdenvNoCC.mkDerivation {
  pname = "command-center-roundup";
  version = "1.1.0";
  src = lib.cleanSource ./.;
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    export PYTHONDONTWRITEBYTECODE=1 TZDIR=${tzdata}/share/zoneinfo
    python3 -m unittest discover -s tests -v
  '';
  installPhase = ''
    install -Dm644 roundup.py "$out/lib/command-center-roundup/roundup.py"
    install -m644 draft.txt review.txt "$out/lib/command-center-roundup/"
    makeWrapper ${python3}/bin/python3 "$out/bin/command-center-roundup" \
      --add-flags "$out/lib/command-center-roundup/roundup.py" \
      --set TZDIR ${tzdata}/share/zoneinfo \
      --set PYTHONDONTWRITEBYTECODE 1
    install -Dm644 README.md "$out/share/doc/command-center-roundup/README.md"
  '';
  meta = {
    description = "Private Codex-only daily project roundups with source review and catch-up";
    platforms = lib.platforms.linux;
    mainProgram = "command-center-roundup";
  };
}
