{ pkgs, unstable, wshowkeys, ... }:

let
  wshowkeysCommand = "wshowkeys -a bottom -F 'Sans Bold 42' -b '#000000DD' -f '#ecd29cff' -s '#B5B520ff' -l 1600 -t 500";

in
{
  programs.wshowkeys = {
    enable = true;
    package = wshowkeys.packages.${pkgs.stdenv.hostPlatform.system}.default;
  };

  environment.shellAliases = {
    wshowkeys = wshowkeysCommand;
  };

  programs.bash.shellAliases = {
    wshowkeys = wshowkeysCommand;
  };

  programs.zsh.shellAliases = {
    wshowkeys = wshowkeysCommand;
  };

  environment.systemPackages = with pkgs; [
    adwaita-icon-theme
    uwsm
    kitty
    slack
    teams-for-linux
    thunderbird
    unstable.zapzap
    bitwarden-desktop
    vivaldi
    playerctl
    waybar
    wofi
    squeekboard
    gsettings-desktop-schemas
    wvkbd
    mako
    wl-clipboard
    wtype
    unstable.voxtype-onnx
    unstable.quickshell
    grim
    slurp
    git
    gh
    vim
  ];
}
