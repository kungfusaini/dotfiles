{
  description = "kiraMBP nix-darwin system flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-25.11-darwin";
    nix-darwin.url = "github:nix-darwin/nix-darwin/nix-darwin-25.11";
    nix-darwin.inputs.nixpkgs.follows = "nixpkgs";
    nix-homebrew.url = "github:zhaofengli/nix-homebrew";
    # Track Homebrew/brew itself closely enough to support current Homebrew Cask DSL.
    # Current casks such as gimp/inkscape/libreoffice use `command_wrapper`, which
    # is newer than the brew release currently pinned by nix-homebrew.
    brew-src.url = "github:Homebrew/brew/master";
    brew-src.flake = false;
    nix-homebrew.inputs.brew-src.follows = "brew-src";
  };

  outputs =
    inputs@{
      self,
      nix-darwin,
      nixpkgs,
      nix-homebrew,
      brew-src,
    }:

    let
      configuration =
        { pkgs, ... }:
        let
          texConf = pkgs.texlive.combine {
            inherit (pkgs.texlive) scheme-small;
            inherit (pkgs.texlive)
              multirow
              latexmk
              contract
              enumitem
              cleveref
              # CV / resume packages
              titlesec
              marvosym
              fontawesome5
              microtype
              ;
          };
        in
        {

          nixpkgs.config = {
            allowUnfree = true;
            permittedInsecurePackages = [
              "electron-39.8.10" # bitwarden-desktop
              "lima-full-1.2.2"
              "lima-additional-guestagents-1.2.2"
            ];
          };
          # List packages installed in system profile. To search by name, run:
          # $ nix-env -qaP | grep wget
          environment.systemPackages = with pkgs; [
            aerospace
            alt-tab-macos
            azure-cli
            atuin
            bat
            blueutil
            biome
            bitwarden-desktop
            bun
            cmake
            colima
            cowsay
            direnv
            docker_29
            fastfetch
            ffmpeg
            fortune
            fzf
            harper
            hidden-bar
            htop
            hugo
            iina
            kitty
            marksman
            mkcert
            neovim
            netlify-cli
            nil
            nix-direnv
            nix-search-cli
            obsidian
            pdftk
            pyenv
            raycast
            sioyek
            slack
            sox
            spotify
            starship
            stow
            tailscale
            taskwarrior3
            taskwarrior-tui
            telegram-desktop
            texConf
            the-unarchiver
            timewarrior
            tldr
            tmux
            tree
            tree-sitter
            unrar
            vscode
            yazi
            zoxide
          ];

          fonts.packages = with pkgs; [
            nerd-fonts.profont
          ];

          # TODO: move this to the readme when I make it	{
          # regular brew packages
          # system services
          # macos appstore apps # mas-cli can help with this (getting ids etc) }
          homebrew = {
            enable = true;
            onActivation.cleanup = "zap"; # Removes all packages apart from the ones below
            onActivation.autoUpdate = true;
            onActivation.upgrade = true;

            taps = [
              "hashicorp/tap"
            ];

            brews = [
              "hashicorp/tap/terraform"
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

          # Necessary for using flakes on this system.
          nix.settings.experimental-features = "nix-command flakes";
          nix.optimise.automatic = true;
          nix.settings.sandbox = false;

          # Auto garbage collect old generations
          nix.gc = {
            automatic = true;
            options = "--delete-older-than 30d";
          };

          # Enable Zsh
          programs.zsh = {
            enable = true;
          };

          services.openssh = {
            enable = true;
          };

          # WORKAROUND: `systemsetup -f -setremotelogin on` requires `Full Disk Access`
          # permission for the Application calling it
          system.activationScripts.extraActivation.text = ''
            if [[ "$(systemsetup -getremotelogin | sed 's/Remote Login: //')" == "Off" ]]; then
              launchctl load -w /System/Library/LaunchDaemons/ssh.plist
            fi
          '';

          # Reverse SSH tunnel LaunchAgent
          launchd = {
            user = {
              agents = {
                reverse-ssh-tunnel = {
                  command = "/usr/bin/ssh -N -R 0.0.0.0:2222:localhost:22 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -i /Users/sumeet/.ssh/id_hetzner root@49.12.43.116";
                  serviceConfig = {
                    KeepAlive = true;
                    RunAtLoad = true;
                    StandardOutPath = "/Users/sumeet/.local/share/reverse-tunnel.out.log";
                    StandardErrorPath = "/Users/sumeet/.local/share/reverse-tunnel.err.log";
                    WorkingDirectory = "/Users/sumeet";
                  };
                };
              };
            };
          };

          # Set Git commit hash for darwin-version.
          system.configurationRevision = self.rev or self.dirtyRev or null;

          # Used for backwards compatibility, please read the changelog before changing.
          # $ darwin-rebuild changelog
          system.stateVersion = 6;

          # homebrew.enable requires this to be set
          # as nix-darwin is moing to system-wide, activations run as root
          # we need this user option, so we must set a primary user
          system.primaryUser = "sumeet";

          # Define the user and their authorized SSH keys
          users.users.sumeet = {
            name = "sumeet";
            home = "/Users/sumeet";
            openssh.authorizedKeys.keys = [
              "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHykhzDDev6Af58WECNPyAs6+5d/CKBAyUg9A80NI2zP kira@flipper"
            ];
          };

          # The platform the configuration will be used on.
          nixpkgs.hostPlatform = "x86_64-darwin";

        };
    in
    {
      # Build darwin flake using:
      # $ darwin-rebuild build --flake .#kiraMBP
      darwinConfigurations."kiraMBP" = nix-darwin.lib.darwinSystem {
        modules = [
          configuration
          nix-homebrew.darwinModules.nix-homebrew # TODO: move this dude to a different locay
          {
            nix-homebrew = {
              # Install Homebrew under the default prefix
              enable = true;
              # User owning the Homebrew prefix, if you change your username, you gotta change this buddy
              user = "sumeet";
            };
          }
        ];
      };
    };
}
