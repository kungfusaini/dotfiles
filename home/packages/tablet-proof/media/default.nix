{ pkgs, hyprland ? pkgs.hyprland, testOrigins ? [] }:
let
  extensionId = "cfepbdnljmjhpbaoephifiehkdahpgll";
  original = builtins.fromJSON (builtins.readFile ./manifest.json);
  manifest = original // {
    host_permissions = original.host_permissions ++ testOrigins;
    # Deliberately do not add fixture content scripts: those already-loaded
    # pages must acquire the autoplay gate through the explicit injection path.
    content_scripts = original.content_scripts;
  };
  # Test-origin prefixes are explicit build inputs, never a runtime bypass.
  prefixes = map (origin: if origin == "http://127.0.0.1/*" then "http://127.0.0.1:" else throw "Unsupported private fixture origin") testOrigins;
  script = pkgs.writeText "tablet-media-background.js" (builtins.replaceStrings
    [ "const TEST_ORIGINS = [];" ]
    [ ("const TEST_ORIGINS = " + builtins.toJSON prefixes + ";") ]
    (builtins.readFile ./background.js));
  extension = pkgs.runCommand "tablet-media-extension" {} ''
    mkdir -p "$out"
    cp ${pkgs.writeText "manifest.json" (builtins.toJSON manifest)} "$out/manifest.json"
    cp ${script} "$out/background.js"
    cp ${./media.js} "$out/media.js"
    cp ${./register.js} "$out/register.js"
    cp ${./pair.html} "$out/pair.html"
    cp ${./pair.js} "$out/pair.js"
  '';
  host = pkgs.writeShellApplication {
    name = "tablet-media-host";
    runtimeInputs = [ pkgs.python3 hyprland ];
    text = ''
      # Vivaldi injects its private C++ library path into native hosts. Keep
      # packaged Python/hyprctl on their own Nix RPATHs, not Chromium's ABI.
      unset LD_LIBRARY_PATH LD_PRELOAD
      export TABLET_PROOF_SOURCE=${../controller.py}
      export TABLET_MEDIA_EXTENSION_ID=${extensionId}
      exec python3 ${./host.py} "$@"
    '';
  };
  hostManifest = pkgs.writeText "org.machine.tablet_media.json" (builtins.toJSON {
    name = "org.machine.tablet_media";
    description = "Window-scoped tablet media pause";
    path = "${host}/bin/tablet-media-host";
    type = "stdio";
    allowed_origins = [ "chrome-extension://${extensionId}/" ];
  });
in { inherit extensionId extension host hostManifest; }
