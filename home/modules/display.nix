{ pkgs, ... }:

let
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
      gnome-network-displays
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
      exec python3 ${../scripts/display/clamshell-mode.py} "$@"
    '';
  };

  headlessMode = pkgs.writeShellApplication {
    name = "headless-mode";
    runtimeInputs = with pkgs; [
      coreutils
      displayLayoutApply
      displayModeToggle
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
  home.packages = [ clamshellMode headlessMode displayWallpaperRefresh pkgs.gnome-network-displays ];

  xdg.configFile = {
    "quickshell/display-layout/shell.qml".source =
      ../config/quickshell/display-layout/shell.qml;
  };
}
