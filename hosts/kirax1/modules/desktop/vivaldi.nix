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
    (_final: prev: {
      vivaldi = prev.vivaldi.override (args: {
        commandLineArgs = lib.concatStringsSep " " (lib.filter (value: value != "") [
          (args.commandLineArgs or "")
          "--ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3"
        ]);
      });
    })
  ];

  # Chromium/Vivaldi managed policy: force Google as the address-bar search engine.
  # Verify after rebuild at: vivaldi://policy
  environment.etc."opt/vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;

  # Some Vivaldi/Linux builds look here instead; harmless if unused.
  environment.etc."vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;
}
