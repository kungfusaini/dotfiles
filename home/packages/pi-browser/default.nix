{ lib, buildNpmPackage, callPackage, writeText, python3, chromium, bitwarden-desktop, hyprland, makeWrapper, nodejs }:

let
  bitwardenExtension = callPackage ./bitwarden-extension.nix { };
  projectExtension = callPackage ../project-object/nix/browser-extension.nix { };
  managedChromium = chromium.override (args: let
    existing = args.commandLineArgs or "";
  in {
    # Preserve the canonical Project Object extension (and any existing load
    # list) rather than replacing it with a second --load-extension switch.
    commandLineArgs = if lib.hasInfix "--load-extension=" existing then
      lib.replaceStrings [ "--load-extension=" ] [ "--load-extension=${bitwardenExtension},${projectExtension}," ] existing
    else existing + " --load-extension=${bitwardenExtension},${projectExtension}";
  });
  bitwardenHost = writeText "pi-browser-bitwarden-native-host.json" (builtins.toJSON {
    name = "com.8bit.bitwarden";
    description = "Bitwarden desktop <-> browser bridge";
    path = "${bitwarden-desktop}/libexec/desktop_proxy";
    type = "stdio";
    allowed_origins = [ "chrome-extension://nngceckbapebfimnlniiiahkandclblb/" ];
  });
in
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
    # Runtime-consent attachment must not auto-snapshot restored credential or
    # inbox pages. The pinned CLI hardcodes full automatic snapshots; override
    # only for our private runtime daemon. Explicit snapshot commands still work.
    substituteInPlace node_modules/playwright-core/lib/coreBundle.js \
      --replace-fail 'snapshotMode: "full"' \
        'snapshotMode: process.env.PI_BROWSER_METADATA_ONLY === "1" ? "none" : "full"'
    # Owned CDP connections keep noDefaults (no emulation/init overrides), but
    # must opt into upstream's normal download events/storage for saveAs().
    # External attachments retain upstream's browser-default download handling.
    substituteInPlace node_modules/playwright-core/lib/coreBundle.js \
      --replace-fail '...options.noDefaults ? { acceptDownloads: "internal-browser-default" } : {}' \
        '...options.noDefaults ? { acceptDownloads: process.env.PI_BROWSER_OWNED_DOWNLOADS === "1" ? "accept" : "internal-browser-default" } : {}'
    cp -r node_modules "$out/lib/pi-browser/"
    install -m644 browser.py "$out/lib/pi-browser/browser.py"
    substituteInPlace "$out/lib/pi-browser/browser.py" \
      --replace-fail '@CLI@' "$out/lib/pi-browser/node_modules/.bin/playwright-cli" \
      --replace-fail '@BROWSER_EXECUTABLE@' '${managedChromium}/bin/chromium' \
      --replace-fail '@BITWARDEN_HOST@' '${bitwardenHost}' \
      --replace-fail '@NODE@' '${nodejs}/bin/node' \
      --replace-fail '@DAEMON@' "$out/lib/pi-browser/node_modules/playwright-core/lib/entry/cliDaemon.js" \
      --replace-fail '@HYPRCTL@' '${hyprland}/bin/hyprctl'
    makeWrapper ${python3}/bin/python3 "$out/bin/pi-browser" \
      --add-flags "$out/lib/pi-browser/browser.py" \
      --prefix PATH : ${lib.makeBinPath [ python3 managedChromium ]} \
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
