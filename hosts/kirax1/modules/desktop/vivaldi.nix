{ lib, ... }:

let
  googleSearchPolicy = builtins.toJSON {
    DefaultSearchProviderEnabled = true;
    DefaultSearchProviderName = "Google";
    DefaultSearchProviderKeyword = "google.com";
    DefaultSearchProviderSearchURL = "https://www.google.com/search?q={searchTerms}";
  };
in
{
  # Use Nixpkgs' supported wrapper option for every ordinary entry point,
  # including desktop launchers and Home Manager's shared-profile consumers.
  # These switches only take effect for a newly started browser process;
  # never restart an existing session or override its profile/startup pages.
  nixpkgs.overlays = [
    (_final: prev: let
      extension = prev.callPackage ../../../../home/packages/project-object/nix/browser-extension.nix {};
    in {
      vivaldi = (prev.vivaldi.override (args: {
        commandLineArgs = lib.concatStringsSep " " (lib.filter (value: value != "") [
          (args.commandLineArgs or "")
          "--ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3"
          "--load-extension=${extension}"
        ]);
      })).overrideAttrs (old: {
        # Private UI APIs are intentionally version-gated. Re-run the hidden
        # native-session contract before accepting a browser upgrade.
        postInstall = assert old.version == "8.2.4133.52"; (old.postInstall or "") + ''
          ui="$out/opt/vivaldi/resources/vivaldi"
          test -f "$ui/main.html"
          chmod u+w "$ui" "$ui/main.html"
          cp ${../../../../home/packages/project-object/integrations/browser/adapter.js} "$ui/project-object-adapter.js"
          substituteInPlace "$ui/main.html" \
            --replace-fail '</body>' '<script src="project-object-adapter.js"></script></body>'
        '';
      });
    })
  ];

  # Chromium/Vivaldi managed policy: force Google as the address-bar search engine.
  # Verify after rebuild at: vivaldi://policy
  environment.etc."opt/vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;

  # Some Vivaldi/Linux builds look here instead; harmless if unused.
  environment.etc."vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;
}
