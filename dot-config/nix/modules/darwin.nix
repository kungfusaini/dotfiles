{ pkgs, ... }:

{
  nixpkgs.config.permittedInsecurePackages = [
    "electron-39.8.10" # bitwarden-desktop
    "lima-full-1.2.2"
    "lima-additional-guestagents-1.2.2"
  ];

  environment.systemPackages = with pkgs; [
    aerospace
    alt-tab-macos
    blueutil
    colima
    hidden-bar
    iina
    raycast
    the-unarchiver
  ];

  homebrew = {
    enable = true;
    onActivation.cleanup = "zap"; # Removes all packages apart from the ones below
    onActivation.autoUpdate = true;
    onActivation.upgrade = false;

    taps = [ ];

    brews = [
      "basedpyright"
      "gh"
      "herdr"
      "libpq"
      "lua-language-server"
      "opencode"
      "bitwarden-cli"
      "pi-coding-agent"
      "poppler"
      "pyenv-virtualenv"
      "pngpaste"
      "spotify_player" # was broken in nix
      "tesseract"
      "tesseract-lang"
      "tpm"
    ];

    casks = [
      "activitywatch"
      "brave-browser"
      "calibre"
      "claude-code"
      "gimp"
      "handy"
      "hammerspoon"
      "inkscape"
      "itsycal" # this didn't work in nix as it needs to go into the application folder
      "karabiner-elements" # this didn't work with nix as it didn't ask for permissions correctly
      "libreoffice"
      "linear-linear"
      "monitorcontrol"
      "nordvpn"
      "openemu"
      "openmtp"
      "raspberry-pi-imager"
      "shotcut"
      "slack"
      "stats"
      "stremio"
      "whatsapp"
    ];
  };

  system.defaults = {
    dock.autohide = true;
    dock.wvous-br-corner = 1;
    dock.tilesize = 1;
    finder.FXPreferredViewStyle = "clmv";
    finder.ShowStatusBar = true;
    finder.ShowPathbar = true;
    finder.AppleShowAllExtensions = true;
    finder.FXEnableExtensionChangeWarning = false;
    finder.NewWindowTarget = "Other";
    finder.NewWindowTargetPath = "file:///Users/sumeet";
    trackpad.Clicking = true;
    controlcenter.Bluetooth = true;
    controlcenter.Sound = true;
    controlcenter.BatteryShowPercentage = false;
    menuExtraClock.ShowDate = 2;
    NSGlobalDomain._HIHideMenuBar = false;
    menuExtraClock.IsAnalog = true;

    # Undocumented Settings
    CustomUserPreferences = {
      NSGlobalDomain = {
        AppleHighlightColor = "0.968627 0.831373 1.000000 Purple";
      };
    };
  };

  # Preserve the current Darwin behavior. NixOS can retain its sandbox default.
  nix.settings.sandbox = false;

  # WORKAROUND: `systemsetup -f -setremotelogin on` requires `Full Disk Access`
  # permission for the Application calling it.
  system.activationScripts.extraActivation.text = ''
    if [[ "$(systemsetup -getremotelogin | sed 's/Remote Login: //')" == "Off" ]]; then
      launchctl load -w /System/Library/LaunchDaemons/ssh.plist
    fi
  '';
}
