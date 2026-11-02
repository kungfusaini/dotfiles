{ lib, pkgs, unstable, ... }:

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

  # Portal services are spawned by the user systemd manager, so they inherit
  # whatever WAYLAND_DISPLAY/DISPLAY was last imported into that manager.  If a
  # nested/test Hyprland imports its environment, GTK file choosers and Electron
  # apps can get stuck talking to the wrong compositor.  Do not trust the
  # manager environment here; discover a live Hyprland instance from its lock
  # files, require that hyprctl can talk to it, and derive the matching Xwayland
  # DISPLAY from the compositor's child process.
  portalWithCurrentHyprEnv = name: execPath: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gawk
      pkgs.gnugrep
      unstable.hyprland
      pkgs.procps
    ];
    text = ''
      set -eu

      # Only repair Hyprland sessions. GNOME imports its own environment;
      # never redirect its portals to a leftover or concurrent Hyprland.
      case ":''${XDG_CURRENT_DESKTOP:-}:" in
        *:Hyprland:*|*:hyprland:*) ;;
        *) exec ${execPath} "$@" ;;
      esac

      runtime="''${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
      chosen_sig=""
      chosen_wl=""
      chosen_pid=""

      for lock in "$runtime"/hypr/*/hyprland.lock; do
        [ -r "$lock" ] || continue
        sig="$(basename "$(dirname "$lock")")"
        pid="$(sed -n '1p' "$lock")"
        wl="$(sed -n '2p' "$lock")"
        [ -n "$pid" ] && [ -n "$wl" ] || continue
        [ -S "$runtime/$wl" ] || continue
        kill -0 "$pid" 2>/dev/null || continue

        if env HYPRLAND_INSTANCE_SIGNATURE="$sig" WAYLAND_DISPLAY="$wl" \
            hyprctl monitors >/dev/null 2>&1; then
          chosen_sig="$sig"
          chosen_wl="$wl"
          chosen_pid="$pid"
          break
        fi
      done

      if [ -n "$chosen_sig" ]; then
        export HYPRLAND_INSTANCE_SIGNATURE="$chosen_sig"
        export WAYLAND_DISPLAY="$chosen_wl"
        export XDG_CURRENT_DESKTOP=Hyprland
        export XDG_SESSION_DESKTOP=Hyprland
        export XDG_SESSION_TYPE=wayland

        xdisplay="$(ps --ppid "$chosen_pid" -o args= 2>/dev/null \
          | awk '/^Xwayland / { for (i = 1; i <= NF; i++) if ($i ~ /^:[0-9]+$/) { print $i; exit } }')"
        if [ -n "$xdisplay" ]; then
          export DISPLAY="$xdisplay"
        fi
      fi

      exec ${execPath} "$@"
    '';
  };

  xdgDesktopPortal = portalWithCurrentHyprEnv
    "xdg-desktop-portal-current"
    "${pkgs.xdg-desktop-portal}/libexec/xdg-desktop-portal";

  xdgDesktopPortalGtk = portalWithCurrentHyprEnv
    "xdg-desktop-portal-gtk-current"
    "${pkgs.xdg-desktop-portal-gtk}/libexec/xdg-desktop-portal-gtk";

  xdgDesktopPortalHyprland = portalWithCurrentHyprEnv
    "xdg-desktop-portal-hyprland-current"
    "${unstable.xdg-desktop-portal-hyprland}/libexec/xdg-desktop-portal-hyprland";
in
{
  # Hyprland desktop launched through UWSM.
  services.displayManager.gdm.enable = false;

  programs.hyprland = {
    enable = true;
    package = unstable.hyprland;
    portalPackage = unstable.xdg-desktop-portal-hyprland;
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
    extraPortals = [
      unstable.xdg-desktop-portal-hyprland
      pkgs.xdg-desktop-portal-gtk
    ];
  };

  systemd.packages = with pkgs; [
    uwsm
  ];

  # Make all portal pieces resilient to stale user-manager environment.  The
  # GTK backend is the important one for FileChooser/Save As dialogs used by
  # Vivaldi, Slack and Teams; the Hyprland backend handles screencopy.
  systemd.user.services.xdg-desktop-portal.serviceConfig.ExecStart = lib.mkForce [
    ""
    "${xdgDesktopPortal}/bin/xdg-desktop-portal-current"
  ];

  systemd.user.services.xdg-desktop-portal-gtk.serviceConfig.ExecStart = lib.mkForce [
    ""
    "${xdgDesktopPortalGtk}/bin/xdg-desktop-portal-gtk-current"
  ];

  systemd.user.services.xdg-desktop-portal-hyprland.serviceConfig.ExecStart = lib.mkForce [
    ""
    "${xdgDesktopPortalHyprland}/bin/xdg-desktop-portal-hyprland-current"
  ];

  systemd.user.services.voxtype = {
    description = "Voxtype daemon";
    wantedBy = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];

    # Voxtype reads its configuration only at startup. Tie the unit generation
    # to the declarative config so nixos-rebuild restarts it when that changes.
    restartTriggers = [ ../../../../home/config/voxtype/config.toml ];

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
