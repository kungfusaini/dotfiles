{ pkgs, unstable, wshowkeys, ... }:

let
  wshowkeysCommand = "wshowkeys -a bottom -F 'Sans Bold 42' -b '#000000DD' -f '#ecd29cff' -s '#B5B520ff' -l 1600 -t 500";

  # Slack's native Wayland huddle preview renders badly under Hyprland, while
  # plain XWayland is blurry at 1.25 fractional scaling. This combo gives the
  # huddle card correct rendering and keeps the UI sharp.
  slackX11 = pkgs.symlinkJoin {
    name = "slack-x11-scaled";
    paths = [ pkgs.slack ];
    nativeBuildInputs = [ pkgs.makeWrapper ];
    postBuild = ''
      rm -f $out/bin/slack
      makeWrapper ${pkgs.slack}/bin/slack $out/bin/slack \
        --add-flags "--ozone-platform=x11 --force-device-scale-factor=1.25"

      # symlinkJoin leaves the desktop file as a symlink into pkgs.slack's
      # read-only store path, so replace it with a writable copy before editing.
      rm -f $out/share/applications/slack.desktop
      cp ${pkgs.slack}/share/applications/slack.desktop $out/share/applications/slack.desktop
      chmod +w $out/share/applications/slack.desktop
      substituteInPlace $out/share/applications/slack.desktop \
        --replace-fail "${pkgs.slack}/bin/slack -s %U" "$out/bin/slack -s %U"
    '';
  };

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

  # Bitwarden's default memfd_secret backend vetoes hibernation kernel-wide.
  # mlock keeps its keys out of normal swap, but a hibernation image can still
  # contain sensitive memory; the current resume partition is not encrypted.
  environment.sessionVariables.SECURE_KEY_CONTAINER_BACKEND = "mlock";

  fonts.packages = with pkgs; [
    font-awesome
    nerd-fonts.symbols-only
  ];

  environment.systemPackages = with pkgs; [
    adwaita-icon-theme
    uwsm
    kitty
    slackX11
    teams-for-linux
    (thunderbird.override {
      # Home Manager owns the mail associations; do not prompt on each launch.
      extraPrefs = ''
        lockPref("mail.shell.checkDefaultClient", false);
      '';
    })
    unstable.zapzap
    bitwarden-desktop
    vivaldi
    krita
    vlc
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
  ];
}
