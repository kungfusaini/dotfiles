{ pkgs, hyprland ? pkgs.hyprland, preloadedTestOrigins ? [] }:
let
  extensionId = "cfepbdnljmjhpbaoephifiehkdahpgll";
  original = builtins.fromJSON (builtins.readFile ./manifest.json);
  manifest = original // {
    # Fixture documents must still prove the explicit helper injection path.
    # Tests can only exclude declarative injection, never grant extra access.
    content_scripts = map (script: if builtins.elem "media.js" script.js then
      script // { exclude_matches = (script.exclude_matches or []) ++ preloadedTestOrigins; }
      else script) original.content_scripts;
  };
  extension = pkgs.runCommand "tablet-media-extension" {} ''
    mkdir -p "$out"
    cp ${pkgs.writeText "manifest.json" (builtins.toJSON manifest)} "$out/manifest.json"
    cp ${./background.js} "$out/background.js"
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
