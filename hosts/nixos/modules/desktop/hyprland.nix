{ pkgs, unstable, ... }:

let
  # hyprgrass is tightly coupled to Hyprland internals. The nixpkgs copy is
  # currently ahead of Hyprland 0.55.4 and fails to build, so pin hyprgrass to
  # the upstream commit listed for Hyprland a0136d8c / v0.55.4 in hyprpm.toml.
  hyprgrass = pkgs.hyprlandPlugins.hyprgrass.overrideAttrs (_old: {
    version = "0.8.2-pin-v0.55.4";
    src = pkgs.fetchFromGitHub {
      owner = "horriblename";
      repo = "hyprgrass";
      rev = "d094a3e62f6ecaeb41515982d3e13edefaf8a4e7";
      hash = "sha256-tCt7FNc1RBHou/ym7B0XzoOqqNq8Df+dizEDkAgJ4U0=";
    };
  });

  hyprPluginDir = pkgs.symlinkJoin {
    name = "hyprland-plugins";
    paths = [ hyprgrass ];
  };
in
{
  # Hyprland desktop launched through UWSM.
  services.displayManager.gdm.enable = false;
  services.desktopManager.gnome.enable = false;

  programs.hyprland = {
    enable = true;
    withUWSM = true;
    xwayland.enable = true;
  };

  services.displayManager.sddm.enable = false;
  programs.regreet.enable = false;
  services.displayManager.dms-greeter = {
    enable = true;
    compositor.name = "hyprland";
  };

  xdg.portal = {
    enable = true;
    extraPortals = with pkgs; [
      xdg-desktop-portal-hyprland
      xdg-desktop-portal-gtk
    ];
  };

  systemd.packages = with pkgs; [
    uwsm
  ];

  systemd.user.services.voxtype = {
    description = "Voxtype daemon";
    wantedBy = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    path = [
      unstable.voxtype-onnx
      unstable.quickshell
    ];
    serviceConfig = {
      ExecStart = "${unstable.voxtype-onnx}/bin/voxtype --quiet daemon";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };

  environment.sessionVariables = {
    HYPR_PLUGIN_DIR = hyprPluginDir;
  };
}
