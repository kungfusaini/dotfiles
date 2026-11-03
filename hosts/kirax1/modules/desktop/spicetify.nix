{ pkgs, unstable, spicetify-nix, ... }:

let
  spicePkgs = spicetify-nix.legacyPackages.${pkgs.stdenv.hostPlatform.system};
  powerSaver = {
    name = "powerSaver.js";
    src = pkgs.writeTextDir "powerSaver.js" (builtins.readFile ./spotify-power-saver.js);
  };
in
{
  programs.spicetify = {
    enable = true;
    spicetifyPackage = unstable.spicetify-cli;

    theme = spicePkgs.themes.catppuccin;
    colorScheme = "mocha";

    enabledExtensions = with spicePkgs.extensions; [
      adblockify
      hidePodcasts
      shuffle
      volumePercentage
    ] ++ [ powerSaver ];

    enabledCustomApps = with spicePkgs.apps; [
      lyricsPlus
    ];
  };
}
