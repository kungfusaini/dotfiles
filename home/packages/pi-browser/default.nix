{ lib, buildNpmPackage, python3, vivaldi, hyprland, makeWrapper, nodejs }:

buildNpmPackage {
  pname = "pi-browser";
  version = "1.0.0";
  src = lib.cleanSource ./.;
  npmDepsHash = "sha256-STlnsXkwTXAl1IKvGBmrH1JlNDDDUoaf1jBfl32bEog=";
  npmFlags = [ "--ignore-scripts" ];
  dontNpmBuild = true;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 ];
  doCheck = true;
  checkPhase = ''
    PYTHONDONTWRITEBYTECODE=1 ${python3}/bin/python3 -m unittest discover -s tests -v
  '';
  installPhase = ''
    mkdir -p "$out/lib/pi-browser"
    cp -r node_modules "$out/lib/pi-browser/"
    install -m644 browser.py "$out/lib/pi-browser/browser.py"
    substituteInPlace "$out/lib/pi-browser/browser.py" \
      --replace-fail '@CLI@' "$out/lib/pi-browser/node_modules/.bin/playwright-cli" \
      --replace-fail '@BROWSER_EXECUTABLE@' '${vivaldi}/bin/vivaldi' \
      --replace-fail '@NODE@' '${nodejs}/bin/node' \
      --replace-fail '@DAEMON@' "$out/lib/pi-browser/node_modules/playwright-core/lib/entry/cliDaemon.js" \
      --replace-fail '@HYPRCTL@' '${hyprland}/bin/hyprctl'
    makeWrapper ${python3}/bin/python3 "$out/bin/pi-browser" \
      --add-flags "$out/lib/pi-browser/browser.py" \
      --prefix PATH : ${lib.makeBinPath [ python3 vivaldi ]} \
      --set PYTHONDONTWRITEBYTECODE 1
    # Upstream's /usr/bin/env node shebang needs the build's exact Node runtime.
    wrapProgram "$out/lib/pi-browser/node_modules/@playwright/cli/playwright-cli.js" \
      --prefix PATH : ${lib.makeBinPath [ nodejs ]}
    install -Dm644 README.md "$out/share/doc/pi-browser/README.md"
  '';
  meta = {
    description = "Session-scoped Playwright CLI for Pi browser workflows";
    platforms = lib.platforms.linux;
    license = lib.licenses.asl20;
    mainProgram = "pi-browser";
  };
}
