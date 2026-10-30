{ pkgs, ... }:

let
  cli-microsoft365 = pkgs.buildNpmPackage {
    pname = "cli-microsoft365";
    version = "11.11.0";

    src = pkgs.fetchurl {
      url = "https://registry.npmjs.org/@pnp/cli-microsoft365/-/cli-microsoft365-11.11.0.tgz";
      hash = "sha256-RdtTd3szeKVXSqNqLRRMuHKsyoPFYJt4q1mBBR59LRc=";
    };

    postPatch = ''
      rm npm-shrinkwrap.json
      cp ${../packages/cli-microsoft365-package-lock.json} package-lock.json
    '';

    npmDepsHash = "sha256-FUwuRUpd/rH8Ut4VFrNTihwvDjQxHMbBRT2mqT5bbk8=";
    dontNpmBuild = true;
  };
in
{
  imports = [
    ./modules/display.nix
    ./modules/hypr.nix
    ./modules/kitty.nix
    ./modules/mako.nix
    ./modules/mewtion.nix
    ./modules/microphone.nix
    ./modules/pi.nix
    ./packages/project-object/nix/home-manager-module.nix
    ./modules/power-status.nix
    ./modules/vim.nix
    ./modules/voxtype.nix
    ./modules/waybar.nix
    ./modules/yazi.nix
  ];

  home.username = "sumeet";
  home.homeDirectory = "/home/sumeet";

  # Match the NixOS release used by the host. Do not change casually.
  home.stateVersion = "26.05";

  xdg = {
    enable = true;
    mimeApps = {
      enable = true;
      defaultApplications = {
        "text/html" = "vivaldi-stable.desktop";
        "x-scheme-handler/http" = "vivaldi-stable.desktop";
        "x-scheme-handler/https" = "vivaldi-stable.desktop";
      };
    };
  };

  # User-session tools used by Home Manager managed scripts/keybindings.
  home.packages = with pkgs; [
    brightnessctl
    cli-microsoft365
    nodejs
  ];

  programs.home-manager.enable = true;
  programs.project-object.enable = true;
}
