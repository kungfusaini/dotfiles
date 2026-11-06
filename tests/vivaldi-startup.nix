# Ordinary browser package contract. No browser/display/profile is opened.
{ pkgs }:
let
  module = import ../hosts/kirax1/modules/desktop/vivaldi.nix { inherit (pkgs) lib; };
  overlay = builtins.head module.nixpkgs.overlays;
  extension = pkgs.callPackage ../home/packages/project-object/nix/browser-extension.nix {};
  required = "--ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3 --load-extension=${extension}";
  probe = args: (overlay {} {
    inherit (pkgs) callPackage;
    vivaldi.override = change: (change args) // { overrideAttrs = _: change args; };
  }).vivaldi.commandLineArgs;
  expectedSearch = builtins.toJSON {
    DefaultSearchProviderEnabled = true;
    DefaultSearchProviderName = "Google";
    DefaultSearchProviderKeyword = "google.com";
    DefaultSearchProviderSearchURL = "https://www.google.com/search?q={searchTerms}";
  };
in
assert probe {} == required;
assert probe { commandLineArgs = "--existing-argument"; } == "--existing-argument " + required;
assert module.environment.etc."opt/vivaldi/policies/managed/default-search.json".text == expectedSearch;
assert module.environment.etc."vivaldi/policies/managed/default-search.json".text == expectedSearch;
pkgs.runCommand "vivaldi-startup-contract" {} ''
  wrapper=${pkgs.vivaldi}/bin/vivaldi
  for flag in --ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3; do
    ${pkgs.gnugrep}/bin/grep -aFq -- "$flag" "$wrapper"
  done
  # The ordinary launcher, new-window and private-window actions must all use
  # this exact configured package, not an unconfigured browser elsewhere.
  desktop=${pkgs.vivaldi}/share/applications/vivaldi-stable.desktop
  ${pkgs.gnugrep}/bin/grep -Fq "Exec=$wrapper %U" "$desktop"
  ${pkgs.gnugrep}/bin/grep -Fq "Exec=$wrapper --new-window" "$desktop"
  ${pkgs.gnugrep}/bin/grep -Fq "Exec=$wrapper --incognito" "$desktop"
  ${pkgs.gnugrep}/bin/grep -Fq -- '--load-extension=${extension}' "$wrapper"
  ui=${pkgs.vivaldi}/opt/vivaldi/resources/vivaldi
  ${pkgs.gnugrep}/bin/grep -Fq 'project-object-adapter.js' "$ui/main.html"
  cmp ${../home/packages/project-object/integrations/browser/adapter.js} "$ui/project-object-adapter.js"
  touch "$out"
''
