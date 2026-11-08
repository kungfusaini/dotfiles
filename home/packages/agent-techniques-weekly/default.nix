{ lib, python3, nodejs, pi, makeWrapper, stdenvNoCC }:
stdenvNoCC.mkDerivation {
  pname = "agent-techniques-weekly";
  version = "0.1.0";
  src = ./.;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 nodejs ];
  doCheck = true;
  checkPhase = ''
    PYTHONDONTWRITEBYTECODE=1 ${python3}/bin/python3 -m unittest discover -s tests -v
    PI_WEEKLY_SDK=${pi}/lib/node_modules/pi-monorepo/dist/index.js ${nodejs}/bin/node --test tests/*.test.mjs
  '';
  installPhase = ''
    install -Dm644 weekly.py "$out/lib/agent-techniques-weekly/weekly.py"
    install -m644 model.mjs "$out/lib/agent-techniques-weekly/model.mjs"
    makeWrapper ${python3}/bin/python3 "$out/bin/agent-techniques-weekly" \
      --add-flags "$out/lib/agent-techniques-weekly/weekly.py"
    install -Dm644 README.md "$out/share/doc/agent-techniques-weekly/README.md"
  '';
  meta = {
    description = "Bounded weekly Reddit technique discovery with logged tool-free Pi inference";
    license = lib.licenses.mit;
    mainProgram = "agent-techniques-weekly";
    platforms = lib.platforms.linux;
  };
}
