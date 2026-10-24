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
      displayWallpaperRefresh
      hyprland
      python3
      wlr-randr
    ];
    text = builtins.readFile ../scripts/display/display-layout-apply;
  };

  displayLayoutOpen = pkgs.writeShellApplication {
    name = "display-layout-open";
    runtimeInputs = with pkgs; [
      displayLayoutApply
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
      displayWallpaperRefresh
      hyprland
      python3
    ];
    text = builtins.readFile ../scripts/display/display-mode-toggle;
  };

  headlessMode = pkgs.writeShellApplication {
    name = "headless-mode";
    runtimeInputs = with pkgs; [
      coreutils
      displayLayoutApply
      displayModeToggle
      displayWallpaperRefresh
      hyprland
      python3
      quickshell
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
    runtimeInputs = with pkgs; [ coreutils headlessMode hyprland python3 socat util-linux ];
    text = builtins.readFile ../scripts/display/headless-monitor-watch;
  };
in
{
  _module.args = {
    inherit displayLayoutOpen displayModeToggle headlessMonitorWatch;
  };

  # Keep an explicit recovery command available from a terminal on the external
  # display, independently of whether the F7 binding is receiving events.
  home.packages = [ headlessMode ];

  xdg.configFile = {
    "quickshell/display-layout/shell.qml".source =
      ../config/quickshell/display-layout/shell.qml;
    "quickshell/headless-countdown/shell.qml".source =
      ../config/quickshell/headless-countdown/shell.qml;
  };
}
