{ pkgs, ... }:

let
  control = pkgs.callPackage ../packages/hyprland-control { };
  networkDisplays = pkgs.callPackage ../packages/gnome-network-displays { };
  doubletake = pkgs.callPackage ../packages/doubletake { };

  displayWallpaperRefresh = pkgs.writeShellApplication {
    name = "display-wallpaper-refresh";
    runtimeInputs = with pkgs; [ coreutils procps ];
    text = builtins.readFile ../scripts/display/display-wallpaper-refresh;
  };

  displayLayoutApply = pkgs.writeShellApplication {
    name = "display-layout-apply";
    runtimeInputs = with pkgs; [
      coreutils
      hyprland
      python3
      util-linux
      wlr-randr
    ];
    text = builtins.readFile ../scripts/display/display-layout-apply;
  };

  displayLayoutOpen = pkgs.writeShellApplication {
    name = "display-layout-open";
    runtimeInputs = with pkgs; [
      displayLayoutApply
      control
      networkDisplays
      hyprland
      python3
      quickshell
    ];
    text = builtins.readFile ../scripts/display/display-layout-open;
  };

  displayModeToggle = pkgs.writeShellApplication {
    name = "display-mode-toggle";
    runtimeInputs = with pkgs; [
      displayLayoutApply
      control
      hyprland
      python3
      util-linux
    ];
    text = builtins.readFile ../scripts/display/display-mode-toggle;
  };

  clamshellMode = pkgs.writeShellApplication {
    name = "clamshell-mode";
    runtimeInputs = with pkgs; [ hyprland python3 ];
    text = ''
      export PYTHONPATH=${control.pythonPath}:"''${PYTHONPATH:-}"
      exec python3 ${../scripts/display/clamshell-mode.py} "$@"
    '';
  };

  headlessMode = pkgs.writeShellApplication {
    name = "headless-mode";
    runtimeInputs = with pkgs; [
      coreutils
      displayLayoutApply
      displayModeToggle
      control
      hyprland
      python3
      util-linux
      wlr-randr
    ];
    text = builtins.readFile ../scripts/display/headless-mode;
  };

  displayKeyHandler = pkgs.writeShellApplication {
    name = "display-key-handler";
    runtimeInputs = with pkgs; [ coreutils displayModeToggle headlessMode util-linux ];
    text = builtins.readFile ../scripts/display/display-key-handler;
  };

  headlessMonitorWatch = pkgs.writeShellApplication {
    name = "headless-monitor-watch";
    runtimeInputs = with pkgs; [ clamshellMode coreutils displayLayoutApply headlessMode hyprland python3 socat util-linux ];
    text = builtins.readFile ../scripts/display/headless-monitor-watch;
  };
in
{
  _module.args = {
    inherit clamshellMode displayKeyHandler displayLayoutOpen headlessMonitorWatch;
  };

  # Keep an explicit recovery command available from a terminal on the external
  # display, independently of whether the F7 binding is receiving events.
  # Keep wallpaper restart as a manual fallback, never a normal transition.
  # Use the packaged casting client and its bundled GStreamer dependencies.
  # Network discovery and wireless lid policy are separate host-level choices.
  # Experimental AirPlay sender, manual CLI only: no daemon or auto-connect.
  home.packages = [ clamshellMode headlessMode displayWallpaperRefresh networkDisplays control doubletake ];

  # Runtime safety identity, separate from executable Lua text. This avoids a
  # headlessMode ↔ watcher package dependency cycle without parsing config code.
  xdg.configFile."hypr/desktop-policy.json".text = builtins.toJSON {
    version = 1;
    headlessWatcher = "${headlessMonitorWatch}/bin/headless-monitor-watch";
  };

  xdg.configFile = {
    "quickshell/display-layout/shell.qml".source =
      ../config/quickshell/display-layout/shell.qml;
  };
}
