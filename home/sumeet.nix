{ config, lib, pkgs, ... }:

let
  loupeIndependent = pkgs.callPackage ./packages/loupe.nix { };
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
    ./modules/life-atlas-audio.nix
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
        # Loupe supports pinch zoom on both touchpads and touchscreens.
        "image/avif" = "org.gnome.Loupe.desktop";
        "image/bmp" = "org.gnome.Loupe.desktop";
        "image/gif" = "org.gnome.Loupe.desktop";
        "image/heic" = "org.gnome.Loupe.desktop";
        "image/heif" = "org.gnome.Loupe.desktop";
        "image/jpeg" = "org.gnome.Loupe.desktop";
        "image/jxl" = "org.gnome.Loupe.desktop";
        "image/png" = "org.gnome.Loupe.desktop";
        "image/svg+xml" = "org.gnome.Loupe.desktop";
        "image/tiff" = "org.gnome.Loupe.desktop";
        "image/webp" = "org.gnome.Loupe.desktop";
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
    ardour
    brightnessctl
    cli-microsoft365
    loupeIndependent
    nicotine-plus
    nodejs
    poppler-utils
    stremio-linux-shell
  ];

  xdg.configFile."ardour9/templates/Musical Sketch/Musical Sketch.template".source =
    ./config/ardour/musical-sketch.template;

  # Ardour writes this file itself; update only scaling rather than managing a
  # read-only ui_config symlink. Never race a running instance's preferences.
  home.activation.ardourScale = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    if ${pkgs.procps}/bin/pgrep -u "$UID" -x ArdourGUI >/dev/null; then
      echo "Ardour is running; skipping its 125% UI scale preference."
    else
      run ${pkgs.python3}/bin/python3 ${./scripts/ardour-scale.py} \
        "${config.xdg.configHome}/ardour9/ui_config"
      run ${pkgs.python3}/bin/python3 ${./scripts/ardour-sketch.py} \
        "${config.xdg.configHome}/ardour9" \
        "${config.home.homeDirectory}/Music/ardour" \
        ${./config/ardour/musical-sketch.template}
    fi
  '';

  # Prune stale user and Home Manager generations alongside the system policy.
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };

  # Accepted native tablet Home/switcher owns folding and tablet entry.
  programs.tablet-native.automatic = true;

  programs.home-manager.enable = true;
  programs.project-object.enable = true;
}
