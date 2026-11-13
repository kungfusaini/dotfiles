{ config, pkgs, ... }:

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
    ./modules/codex-usage.nix
    ./modules/command-center-roundup.nix
    ./modules/agent-techniques-weekly.nix
    ./modules/display.nix
    ./modules/hypr.nix
    ./modules/kitty.nix
    ./modules/mako.nix
    ./modules/mewtion.nix
    ./modules/microphone.nix
    ./modules/pegasus.nix
    ./modules/pi.nix
    ./packages/project-object/nix/home-manager-module.nix
    ./modules/power-status.nix
    ./modules/agent-lid-sleep.nix
    ./modules/tablet-workspace.nix
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
    userDirs = {
      enable = true;
      createDirectories = true;
      projects = "${config.home.homeDirectory}/matrix/projects";
    };
    mimeApps = {
      enable = true;
      defaultApplications = {
        # Use a lightweight Wayland viewer rather than an editor/PDF fallback.
        "image/avif" = "swayimg.desktop";
        "image/bmp" = "swayimg.desktop";
        "image/gif" = "swayimg.desktop";
        "image/heif" = "swayimg.desktop";
        "image/jpeg" = "swayimg.desktop";
        "image/jxl" = "swayimg.desktop";
        "image/png" = "swayimg.desktop";
        "image/svg+xml" = "swayimg.desktop";
        "image/tiff" = "swayimg.desktop";
        "image/webp" = "swayimg.desktop";
        "x-scheme-handler/mailto" = "thunderbird.desktop";
        "x-scheme-handler/mid" = "thunderbird.desktop";
        "message/rfc822" = "thunderbird.desktop";
        "text/calendar" = "thunderbird.desktop";
        "application/x-extension-ics" = "thunderbird.desktop";
        "text/html" = "vivaldi-stable.desktop";
        "x-scheme-handler/http" = "project-browser.desktop";
        "x-scheme-handler/https" = "project-browser.desktop";
      };
    };
  };

  # User-session tools used by Home Manager managed scripts/keybindings.
  home.packages = with pkgs; [
    brightnessctl
    cli-microsoft365
    nicotine-plus
    nodejs
    poppler-utils
    swayimg
  ];

  # Prune stale user and Home Manager generations alongside the system policy.
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };

  programs.home-manager.enable = true;
  programs.project-object.enable = true;
}
